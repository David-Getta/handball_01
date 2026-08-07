"""Meccs utáni automatikus edzői összefoglaló — magyarul, mondatokban.

A feldolgozott meccs elemzés-eredményeiből (események, tempó, védekezési
formák, intenzitás, játékos-terhelés) rövid, emberi nyelvű összefoglalót
állít össze: mi történt, mi volt feltűnő, mire érdemes ránézni. Ez kerül
a meccs-nézet összegző paneljére és a nyomtatható jelentésbe is.

Szándékosan sablon-alapú (nem nyelvi modell): minden mondat mögött
kiszámolt szám áll, így a szöveg ellenőrizhető és determinisztikus.
"""

from __future__ import annotations

import re

from ..models.tracking import Match, Team
from .event_detection import EventType, detect_shots
from .stats import compute_intensity_timeline, compute_player_stats
from .tactics import TacticsConfig, team_style_profile

# Az intenzitás-esés e fölött kap külön figyelmeztetést (hajrá vs kezdés).
INTENSITY_DROP_WARN_PCT = 12.0


def _team_names(match: Match) -> tuple[str, str]:
    home = match.meta.home_team or "Hazai"
    away = match.meta.away_team or "Vendég"
    return home, away


def _jersey_of_track(match: Match) -> dict[int, int]:
    """track_id → mezszám (az első ismert érték trackenként)."""
    out: dict[int, int] = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None and p.track_id not in out:
                out[p.track_id] = p.jersey_number
    return out


def _team_of_track(match: Match) -> dict[int, Team]:
    out: dict[int, Team] = {}
    for f in match.frames:
        for p in f.players:
            if p.track_id not in out:
                out[p.track_id] = p.team
    return out


def _player_label(track_id: int, team_of: dict, jersey_of: dict,
                  home: str, away: str) -> str:
    side = home if team_of.get(track_id) == Team.HOME else away
    jersey = jersey_of.get(track_id)
    return f"{side} #{jersey}" if jersey is not None else f"{side} ({track_id}. játékos)"


def _events_section(match: Match, home: str, away: str) -> dict | None:
    goals_h = goals_a = shots = saves = 0
    for e in detect_shots(match):
        if e.type == EventType.GOAL:
            if e.team == Team.HOME:
                goals_h += 1
            else:
                goals_a += 1
        elif e.type == EventType.SHOT:
            shots += 1
            if (e.detail or {}).get("outcome") == "save":
                saves += 1
    attempts = goals_h + goals_a + shots
    if attempts == 0:
        return None
    body = (f"A rendszer {goals_h + goals_a} gól-eseményt és {shots} további "
            f"kapura tartó lövést ismert fel ({home} {goals_h} : {goals_a} {away}).")
    if saves:
        body += f" Ebből {saves} lövést a kapusok hárítottak."
    # Félidei állás (csak ha a szünet ténylegesen felismerhető).
    try:
        from .momentum import halftime_score
        hs = halftime_score(match)
        if hs is not None and (goals_h + goals_a):
            body += f" Félidőben {hs['home']} – {hs['away']} volt az állás."
    except Exception:
        pass
    if attempts >= 5:
        eff = 100.0 * (goals_h + goals_a) / attempts
        body += f" A felismert kísérletek {eff:.0f}%-a végződött gólban."
    # Gólpasszok: a detect_events a gólokhoz assist_id-t rendel (ha van) —
    # a legtöbb gólpasszt adó játékos külön említést kap.
    try:
        from .event_detection import detect_events
        assists: dict[int, int] = {}
        for e in detect_events(match):
            aid = (e.detail or {}).get("assist_id")
            if e.type == EventType.GOAL and aid is not None:
                assists[aid] = assists.get(aid, 0) + 1
        if assists:
            top_id, top_n = max(assists.items(), key=lambda kv: kv[1])
            label = _player_label(top_id, _team_of_track(match),
                                  _jersey_of_track(match), home, away)
            total = sum(assists.values())
            body += (f" {total} gól előtt gólpassz is azonosítható; "
                     f"a legtöbbet {label} adta ({top_n}).")
            # A legerősebb gól-páros (ha van bejáratott kapcsolat).
            from .event_detection import assist_network
            net = assist_network(match)
            best = None
            for side in ("home", "away"):
                for pr in net[side]["pairs"]:
                    if best is None or pr["goals"] > best["goals"]:
                        best = pr
            if best and best["goals"] >= 2:
                tof, jof = _team_of_track(match), _jersey_of_track(match)
                lf = _player_label(best["from"], tof, jof, home, away)
                lt = _player_label(best["to"], tof, jof, home, away)
                body += (f" A legerősebb gól-páros: {lf} → {lt} "
                         f"({best['goals']} gól).")
    except Exception:
        pass
    # Leggyorsabb lövés: látványos, könnyen kommunikálható adat (ha mérhető
    # és reális tartományban van).
    try:
        from .event_detection import shot_speeds
        sp = shot_speeds(match)
        fastest = sp.get("fastest")
        if fastest and fastest["speed_kmh"] >= 60.0:
            label = _player_label(fastest["player_id"],
                                  _team_of_track(match),
                                  _jersey_of_track(match), home, away) \
                if fastest.get("player_id") is not None else None
            who = f" ({label})" if label else ""
            body += (f" A leggyorsabb lövés {fastest['speed_kmh']:.0f} "
                     f"km/h volt{who}.")
    except Exception:
        pass
    return {"title": "Gólok és lövések", "body": body}


def _xg_verdict(th: dict, ta: dict, home: str, away: str) -> str | None:
    """Ítélet: a helyzetek alapján is az nyert-e, aki a táblán?

    Csak akkor szólal meg, ha van győztes ÉS az xG-különbség érdemi
    (>= 1.0) — döntetlennél vagy kiegyenlített helyzetképnél nincs mit
    kimondani.
    """
    gh, ga = th["goals"], ta["goals"]
    if gh == ga or abs(th["xg"] - ta["xg"]) < 1.0:
        return None
    won_home = gh > ga
    wname = home if won_home else away
    if won_home == (th["xg"] > ta["xg"]):
        return (f" A(z) {wname} győzelme a helyzetek alapján is "
                "megérdemelt.")
    return (f" A helyzetek alapján a másik oldal állt jobban — a(z) "
            f"{wname} győzelmét a kapusteljesítmény és a hatékony "
            "befejezés hozta.")


def _xg_section(match: Match, home: str, away: str) -> dict | None:
    """Helyzetminőség: várható gól (xG) vs tényleges — befejezés-hatékonyság."""
    from .xg import match_xg
    r_all = match_xg(match)
    th, ta = r_all["teams"]["home"], r_all["teams"]["away"]
    if th["shots"] + ta["shots"] < 4:  # kevés lövésből nincs értelmes kép
        return None
    body = (f"A kidolgozott helyzetek értéke (várható gól) {home} "
            f"{th['xg']:.1f} – {ta['xg']:.1f} {away}, a tényleges gólok: "
            f"{th['goals']} : {ta['goals']}.")
    for rec, name in ((th, home), (ta, away)):
        if rec["shots"] < 3:
            continue
        q = rec.get("avg_xg_per_shot", 0.0)
        if q >= 0.45:
            body += (f" A(z) {name} jó helyzeteket alakított ki "
                     f"(átlag {q:.2f} xG/lövés).")
        elif q and q <= 0.28:
            body += (f" A(z) {name} sok kis esélyű lövést vállalt "
                     f"(átlag {q:.2f} xG/lövés).")
        if rec["diff"] >= 0.8:
            body += (f" A(z) {name} a helyzeteinél többet ért el "
                     f"(+{rec['diff']:.1f}) — pontos befejezés.")
        elif rec["diff"] <= -0.8:
            body += (f" A(z) {name} elpuskázott helyzeteket "
                     f"({rec['diff']:.1f}) — a befejezésen érdemes dolgozni.")
    verdict = _xg_verdict(th, ta, home, away)
    if verdict:
        body += verdict
    # Lövőnkénti kép: a helyzetei felett/alatt teljesítő játékosok
    # (legalább 3 lövéssel — egy-egy lövésből nincs értelmes kép).
    pool = [r for r in r_all.get("shooters", []) if r["shots"] >= 3]
    if pool:
        team_of, jersey_of = _team_of_track(match), _jersey_of_track(match)

        def lab(rec):
            return _player_label(rec["player_id"], team_of, jersey_of,
                                 home, away)
        best = max(pool, key=lambda r: r["diff"])
        worst = min(pool, key=lambda r: r["diff"])
        if best["diff"] >= 0.5:
            body += (f" A helyzetei felett teljesített: {lab(best)} "
                     f"({best['goals']} gól, várható {best['xg']:.1f}).")
        if worst is not best and worst["diff"] <= -0.5:
            body += (f" A legtöbb kihagyott nagy helyzet: {lab(worst)} "
                     f"({worst['goals']} gól, várható {worst['xg']:.1f}).")
    return {"title": "Helyzetminőség", "body": body}


def _defense_section(match: Match, home: str, away: str) -> tuple[dict | None, list[str]]:
    """Védekezés: szabadon hagyott lövők + a leglyukasabb zóna."""
    from .defense import defense_analysis
    d = defense_analysis(match)
    parts: list[str] = []
    highlights: list[str] = []
    for side, name in (("home", home), ("away", away)):
        rec = d[side]
        if rec["shots_against"] < 4:
            continue
        sent = (f"a(z) {name} {rec['shots_against']} lövést kapott "
                f"({rec['goals_against']} gól, engedett helyzet-érték "
                f"{rec['xg_against']:.1f})")
        if rec["free_pct"] is not None and rec["free_pct"] >= 40.0:
            sent += (f"; a lövők {rec['free_pct']:.0f}%-a SZABADON állt "
                     "a lövésnél")
            highlights.append(
                f"{name}: a kapott lövések {rec['free_pct']:.0f}%-ánál nem "
                "volt védő a lövő 2 m-es körzetében — a fedezés-hibákat "
                "érdemes visszanézni.")
        if rec["worst_zone"]:
            wz = rec["zones"][rec["worst_zone"]]
            if wz["goals"] >= 2:
                sent += (f"; a legtöbb kapott gól innen: {rec['worst_zone']} "
                         f"({wz['goals']})")
        parts.append(sent)
    # Védekezési nyomás: szoros vagy laza fal (ha mérhető).
    try:
        from .defense import defensive_pressure
        dp = defensive_pressure(match)
        for side, name in (("home", home), ("away", away)):
            pr = dp[side]["avg_pressure_m"]
            if pr is not None and dp[side]["frames"] >= 50:
                how = ("szorosan, előretolva" if pr <= 1.3
                       else "lazán, mélyen" if pr >= 2.5 else "közepesen")
                parts.append(f"a(z) {name} {how} védekezett (a labdásra átlag "
                             f"{pr:.1f} m-re lépett ki)")
    except Exception:
        pass

    # Védekezési vonal magassága: mély (passzív) vagy felfutó (agresszív) fal.
    try:
        from .defense import defensive_line_height
        dlh = defensive_line_height(match)
        for side, name in (("home", home), ("away", away)):
            rec_dlh = dlh[side]
            if rec_dlh["style"] in ("felfutó (agresszív)", "mély (passzív)"):
                parts.append(
                    f"a(z) {name} {rec_dlh['style']} falat húzott "
                    f"(átlag {rec_dlh['avg_height_m']:.1f} m-re a kaputól)")
    except Exception:
        pass

    # Védelmi tömörség: tömör (szélek nyitva) vagy széthúzott (közép nyitva).
    try:
        from .defense import defensive_width
        dw = defensive_width(match)
        for side, name in (("home", home), ("away", away)):
            rec_dw = dw[side]
            if rec_dw["style"] in ("tömör (szélek nyitva)",
                                   "széthúzott (közép nyitva)"):
                parts.append(
                    f"a(z) {name} fala {rec_dw['style']} "
                    f"(átlag {rec_dw['avg_width_m']:.0f} m széles)")
    except Exception:
        pass

    # Átmenet-védekezés: gyors kapott gólok labdavesztés után (visszazárás).
    try:
        from .defense import transition_defense
        td = transition_defense(match)
        for side, name in (("home", home), ("away", away)):
            rec = td[side]
            if rec["turnovers"] >= 4 and rec["transition_goals_against"] >= 2:
                parts.append(
                    f"a(z) {name} {rec['transition_goals_against']} gyors gólt "
                    f"kapott labdavesztés után ({rec['pct']:.0f}%) — "
                    "a visszazárás gyenge pontja")
                highlights.append(
                    f"{name}: {rec['transition_goals_against']} átmenet-gólt "
                    "kapott labdaeladás után — gyorsabb visszazárás kell.")
    except Exception:
        pass
    # Blokkok: az aktív fal jele — dicséret a védekezésnek.
    try:
        from .defense import detect_blocks
        bl = detect_blocks(match)
        for side, name in (("home", home), ("away", away)):
            rec = bl[side]
            if rec["blocks"] >= 2:
                sent = (f"a(z) {name} védői {rec['blocks']} lövést "
                        "blokkoltak — aktív a fal")
                top = rec["blockers"][0] if rec["blockers"] else None
                if top and top["blocks"] >= 2:
                    sent += (f" (a legtöbbet a(z) {top['player_id']}. "
                             f"játékos: {top['blocks']})")
                parts.append(sent)
    except Exception:
        pass
    # Betörés-folyosók: melyik sávban jönnek be ellenük (a VÉDEKEZŐ
    # olvasat: az ellenfél betörési képe = a mi falunk lyuka).
    try:
        from .defense import breakthrough_lanes
        bl_att = breakthrough_lanes(match)
        for att_side, def_name in (("home", away), ("away", home)):
            rec_bl = bl_att[att_side]
            if rec_bl["entries"] < 5 or not rec_bl["top_lane"]:
                continue
            top_bl = rec_bl["lanes"][rec_bl["top_lane"]]
            share_bl = 100.0 * top_bl["entries"] / rec_bl["entries"]
            if share_bl >= 40.0:
                parts.append(
                    f"a(z) {def_name} ellen a betörések "
                    f"{share_bl:.0f}%-a a(z) {rec_bl['top_lane']} "
                    f"sávban jött ({top_bl['entries']}/"
                    f"{rec_bl['entries']}, {top_bl['goals']} gól)")
                if top_bl["goals"] >= 2:
                    highlights.append(
                        f"{def_name}: a(z) {rec_bl['top_lane']} sáv "
                        f"átjáróház — {top_bl['goals']} gól az ott "
                        "bejövő betörésekből; oda kell a segítő védő.")
    except Exception:
        pass
    # Labdaszerzők: ki a védekezés motorja (a szerzések harmadát hozza).
    try:
        from .defense import ball_winners
        bw = ball_winners(match)
        for side, name in (("home", home), ("away", away)):
            rec_bw = bw[side]
            if rec_bw["total"] < 4 or not rec_bw["players"]:
                continue
            top_bw = rec_bw["players"][0]
            if (top_bw["steals"] >= 3
                    and top_bw["steals"] / rec_bw["total"] >= 0.34):
                who_bw = (f"{top_bw['jersey']}-es"
                          if top_bw["jersey"] is not None
                          else f"{top_bw['player_id']}. játékos")
                parts.append(
                    f"a(z) {name} labdaszerzéseinek motorja a(z) "
                    f"{who_bw} ({top_bw['steals']} a csapat "
                    f"{rec_bw['total']} szerzéséből)")
    except Exception:
        pass
    # Labdaeladók: kinek a leggyengébb a labdabiztonsága.
    try:
        from .defense import turnover_players
        tp = turnover_players(match)
        for side, name in (("home", home), ("away", away)):
            rec_tp = tp[side]
            if rec_tp["total"] < 4 or not rec_tp["players"]:
                continue
            top_tp = rec_tp["players"][0]
            if top_tp["losses"] >= 4:
                who_tp = (f"{top_tp['jersey']}-es"
                          if top_tp["jersey"] is not None
                          else f"{top_tp['player_id']}. játékos")
                parts.append(
                    f"a(z) {name} leggyengébb labdabiztonságú játékosa a(z) "
                    f"{who_tp} ({top_tp['losses']} eladás)")
    except Exception:
        pass
    # Hajrá-emberek: ki szerzi a gólokat a meccs végén.
    try:
        from .momentum import clutch_scorers
        cs = clutch_scorers(match)
        for side, name in (("home", home), ("away", away)):
            rec_cs = cs[side]
            if rec_cs["total"] < 2 or not rec_cs["players"]:
                continue
            top_cs = rec_cs["players"][0]
            if top_cs["goals"] >= 2:
                who_cs = (f"{top_cs['jersey']}-es"
                          if top_cs["jersey"] is not None
                          else f"{top_cs['player_id']}. játékos")
                parts.append(
                    f"a(z) {name} hajrá-embere a(z) {who_cs} "
                    f"({top_cs['goals']} gól az utolsó percekben)")
    except Exception:
        pass
    # Őrzési párok: a legstabilabb pár + a laza őrzés figyelmeztetése.
    try:
        from .defense import MARK_LOOSE_M, marking_pairs
        mk = marking_pairs(match)

        def _mklab(jersey_no, track_id):
            return (f"{jersey_no}-es" if jersey_no is not None
                    else f"{track_id}. játékos")

        for side, name in (("home", home), ("away", away)):
            pairs = mk[side]["pairs"]
            if not pairs:
                continue
            top = pairs[0]
            parts.append(
                f"a(z) {name} legstabilabb őrzési párja: a(z) "
                f"{_mklab(top['defender_jersey'], top['defender'])} fogta "
                f"a(z) {_mklab(top['attacker_jersey'], top['attacker'])} "
                f"támadót ({top['share_pct']:.0f}%, átlag "
                f"{top['avg_dist_m']:.1f} m)")
            lo = mk[side]["loosest"]
            if lo and lo["avg_dist_m"] >= MARK_LOOSE_M:
                highlights.append(
                    f"{name}: a(z) "
                    f"{_mklab(lo['defender_jersey'], lo['defender'])} átlag "
                    f"{lo['avg_dist_m']:.1f} m-ről őrizte a(z) "
                    f"{_mklab(lo['attacker_jersey'], lo['attacker'])} "
                    "támadót — laza őrzés, érdemes visszanézni.")
    except Exception:
        pass
    # Labdaeladás helye: sok elöl (támadó harmadban) vesztett labda könnyű
    # kontrát ad az ellenfélnek.
    try:
        from .defense import turnover_zones
        tz = turnover_zones(match)
        for side, name in (("home", home), ("away", away)):
            rec = tz[side]
            if rec["total"] >= 5 and rec["front_pct"] >= 50.0:
                parts.append(
                    f"a(z) {name} a labdaeladásainak {rec['front_pct']:.0f}%-át "
                    "a támadó harmadban követte el — ez üresen hagyja a "
                    "védelmet a kontra ellen")
    except Exception:
        pass
    if not parts:
        return None, highlights
    return {"title": "Védekezés",
            "body": ("; ".join(parts) + ".").capitalize()}, highlights


def _style_section(match: Match, home: str, away: str) -> dict | None:
    prof = team_style_profile(match)
    tempo = prof.get("tempo", {})
    poss = tempo.get("possessions", 0)
    if not poss:
        return None
    # Labdabirtoklás-arány (ha érdemben eltér az 50-50-től).
    poss_line = ""
    try:
        from .stats import possession_share
        ps = possession_share(match)
        if ps["home"]["pct"] and abs(ps["home"]["pct"] - 50.0) >= 5.0:
            poss_line = (f" Labdabirtoklás: {home} {ps['home']['pct']:.0f}% – "
                         f"{ps['away']['pct']:.0f}% {away}.")
    except Exception:
        pass
    avg_atk = tempo.get("avg_attack_duration_s", 0.0)
    trans = tempo.get("transition_pct", 0.0)
    body = (f"A felvételen {poss} labdabirtoklási szakasz látszik, egy támadás "
            f"átlagosan {avg_atk:.0f} másodpercig tartott.")
    if trans >= 25.0:
        body += (f" Az idő {trans:.0f}%-a átmenet (visszarendeződés/indítás) volt "
                 "— gyors, fel-le hullámzó játék.")
    elif trans > 0:
        body += f" Az átmenetek aránya {trans:.0f}% — inkább felállt védelem elleni játék."
    forms = prof.get("defense_formations", {})
    known = [(name, forms.get(key, "—"))
             for key, name in (("home", home), ("away", away))
             if forms.get(key, "—") != "—"]
    if known:
        body += (" Leggyakoribb védekezési forma — "
                 + ", ".join(f"{n}: {f}" for n, f in known) + ".")
    # Támadás-szélesség: kirívóan széles vagy szűk támadójáték.
    try:
        from .attack_types import attack_width
        aw_all = attack_width(match)
        for side, name in (("home", home), ("away", away)):
            v = aw_all[side]["avg_width_m"]
            if v is None:
                continue
            if v >= 14.0:
                body += (f" A(z) {name} szélesen támadott (átlag "
                         f"{v:.0f} m-re széthúzva).")
            elif v <= 9.0:
                body += (f" A(z) {name} szűken, közép-központúan "
                         f"támadott (átlag {v:.0f} m).")
    except Exception:
        pass
    # Beálló-terhelés: mennyit megy a játék a beállón át, és megéri-e.
    try:
        from .attack_types import pivot_usage
        pu = pivot_usage(match)
        for side, name in (("home", home), ("away", away)):
            rec_pu = pu[side]
            if rec_pu["attacks"] < 5 or rec_pu["pivot_share_pct"] is None:
                continue
            if rec_pu["pivot_share_pct"] >= 40.0:
                body += (f" A(z) {name} támadásainak "
                         f"{rec_pu['pivot_share_pct']:.0f}%-a a beállón "
                         "át ment")
                if (rec_pu["pivot_goal_pct"] is not None
                        and rec_pu["other_goal_pct"] is not None):
                    jobb = (rec_pu["pivot_goal_pct"]
                            - rec_pu["other_goal_pct"])
                    if jobb >= 15.0:
                        body += (f" — és megérte: gólarány "
                                 f"{rec_pu['pivot_goal_pct']:.0f}% a "
                                 f"beállóval, {rec_pu['other_goal_pct']:.0f}% "
                                 "nélküle")
                    elif jobb <= -15.0:
                        body += (f" — pedig nem érte meg: gólarány "
                                 f"{rec_pu['pivot_goal_pct']:.0f}% a "
                                 f"beállóval, {rec_pu['other_goal_pct']:.0f}% "
                                 "nélküle")
                body += "."
    except Exception:
        pass
    # Átmenet-támadás: labdaszerzés → gyors gól hatékonysága.
    try:
        from .attack_types import transition_offense
        to_ = transition_offense(match)
        for side, name in (("home", home), ("away", away)):
            rec_to = to_[side]
            if rec_to["steals"] >= 3 and rec_to["quick_goals"] >= 2:
                body += (f" A(z) {name} a labdaszerzéseit gyorsan "
                         f"gólra váltja ({rec_to['quick_goals']}/"
                         f"{rec_to['steals']}, átlag "
                         f"{rec_to['avg_s']:.0f} mp a szerzéstől a "
                         "gólig) — erős kontra-játék.")
    except Exception:
        pass
    # Lövés-távolság: honnan lő a csapat, és megéri-e (gólarány sávonként).
    try:
        from .attack_types import shot_ranges
        sr = shot_ranges(match)
        _sr_label = {"close": "közelről", "mid": "közép-távból",
                     "far": "távolról"}
        for side, name in (("home", home), ("away", away)):
            rec_sr = sr[side]
            if rec_sr["total_shots"] < 5 or rec_sr["dominant"] is None:
                continue
            dom = rec_sr["dominant"]
            b_sr = rec_sr[dom]
            share = round(100.0 * b_sr["shots"] / rec_sr["total_shots"])
            sent_sr = (f" A(z) {name} lövéseinek {share}%-a "
                       f"{_sr_label[dom]} esett")
            if b_sr["goal_pct"] is not None:
                sent_sr += f" ({b_sr['goal_pct']:.0f}% gólarány)"
            # Ha távolról lő sokat, de gyenge a gólarány, ez fogódzó a
            # védekező félnek (kifelé zárni) és a támadónak (jobb helyzet).
            if dom == "far" and b_sr["goal_pct"] is not None \
                    and b_sr["goal_pct"] < 25.0:
                sent_sr += " — az átlövés gólarány gyenge, jobb helyzeteket"\
                    " érdemes keresni"
            body += sent_sr + "."
    except Exception:
        pass
    # Kapus távolság szerint: melyik sávból sebezhető (védési arány).
    try:
        from .goalkeeper import GK_RANGE_MIN_FACED, gk_save_ranges
        gsr = gk_save_ranges(match)
        _gsr_label = {"close": "közeli", "mid": "közép-távoli",
                      "far": "távoli"}
        for side, name in (("home", home), ("away", away)):
            rec_gsr = gsr[side]
            wb = rec_gsr["weak_band"]
            if wb is None:
                continue
            b_gsr = rec_gsr[wb]
            if b_gsr["faced"] < GK_RANGE_MIN_FACED \
                    or b_gsr["save_pct"] is None:
                continue
            body += (f" A(z) {name} kapusa a(z) {_gsr_label[wb]} "
                     f"lövésekre a leggyengébb "
                     f"({b_gsr['save_pct']:.0f}% védés, "
                     f"{b_gsr['saves']}/{b_gsr['faced']}).")
    except Exception:
        pass
    # Kapu-sarok: hova mennek a gólok (bal/közép/jobb) — kiszámíthatóság.
    try:
        from .attack_types import PLACEMENT_MIN_GOALS, goal_placement
        gp = goal_placement(match)
        for side, name in (("home", home), ("away", away)):
            rec_gp = gp[side]
            dom = rec_gp["dominant"]
            if dom is None or rec_gp["goals"] < PLACEMENT_MIN_GOALS:
                continue
            share = round(100.0 * rec_gp[dom] / rec_gp["goals"])
            if share >= 50:
                body += (f" A(z) {name} góljainak {share}%-a a(z) {dom} "
                         "kapuoldalra ment — a kapus erre készülhet.")
    except Exception:
        pass
    # Szélső-befejezés: mennyire veszélyesek a szélső (éles) szögből.
    try:
        from .attack_types import wing_finishing
        wf = wing_finishing(match)
        for side, name in (("home", home), ("away", away)):
            rec_wf = wf[side]
            if rec_wf["shots"] < 3 or rec_wf["goal_pct"] is None:
                continue
            if rec_wf["goal_pct"] >= 55.0:
                body += (f" A(z) {name} szélső-játéka veszélyes "
                         f"({rec_wf['goals']}/{rec_wf['shots']}, "
                         f"{rec_wf['goal_pct']:.0f}% szélső-gólarány).")
            elif rec_wf["goal_pct"] <= 25.0:
                body += (f" A(z) {name} szélsői gyengén fejeznek be "
                         f"({rec_wf['goals']}/{rec_wf['shots']}, "
                         f"{rec_wf['goal_pct']:.0f}%).")
    except Exception:
        pass
    # Kapus-forma félidőnként: esik vagy formába lendül a 2. félidőre.
    try:
        from .goalkeeper import GK_FADE_DROP_PP, gk_save_fade
        gfc = gk_save_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_gf = gfc[side]
            if rec_gf["drop_pp"] is None:
                continue
            _gf_fh = 100.0 * rec_gf["fh_saves"] / rec_gf["fh_faced"]
            _gf_sh = 100.0 * rec_gf["sh_saves"] / rec_gf["sh_faced"]
            if rec_gf["drop_pp"] >= GK_FADE_DROP_PP:
                body += (f" A(z) {name} kapusa a 2. félidőre esett "
                         f"({_gf_fh:.0f}% → {_gf_sh:.0f}% védés).")
            elif rec_gf["drop_pp"] <= -GK_FADE_DROP_PP:
                body += (f" A(z) {name} kapusa a 2. félidőre lendült "
                         f"formába ({_gf_fh:.0f}% → {_gf_sh:.0f}% védés).")
    except Exception:
        pass
    # Tempó-esés: a támadás-ütem érdemi lassulása a 2. félidőre.
    try:
        from .attack_types import PACE_FADE_DROP_PER_MIN, team_pace_fade
        tpfc = team_pace_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_tp = tpfc[side]
            if rec_tp["drop_per_min"] is None \
                    or rec_tp["drop_per_min"] < PACE_FADE_DROP_PER_MIN:
                continue
            _tp_fh = rec_tp["fh_attacks"] / rec_tp["fh_min"]
            _tp_sh = rec_tp["sh_attacks"] / rec_tp["sh_min"]
            body += (f" A(z) {name} tempója a 2. félidőre esett "
                     f"({_tp_fh:.1f} → {_tp_sh:.1f} támadás/perc) — "
                     "elfogyott a láb.")
    except Exception:
        pass
    # Kihagyott ziccer ára: a kihagyás után fél percen belül jött a
    # büntetés a túloldalon.
    try:
        from .xg import miss_punishment
        mpc = miss_punishment(match)
        for side, name in (("home", home), ("away", away)):
            rec_mp = mpc[side]
            if rec_mp["punished"] >= 2:
                body += (f" A(z) {name} kihagyott ziccerei megbosszulták "
                         f"magukat: {rec_mp['misses']} kihagyásból "
                         f"{rec_mp['punished']} után fél percen belül a "
                         "túloldalon volt a labda a kapuban.")
    except Exception:
        pass
    # Ritmus-egyhangúság: belső órán járó, kiszámítható támadás-hossz.
    try:
        from .attack_types import RHYTHM_CV_LOW, attack_rhythm
        arc = attack_rhythm(match)
        for side, name in (("home", home), ("away", away)):
            rec_ar = arc[side]
            if rec_ar["cv"] is None or rec_ar["cv"] > RHYTHM_CV_LOW:
                continue
            body += (f" A(z) {name} belső órán támadott (átlag "
                     f"{rec_ar['avg_s']:.0f} mp, ±{rec_ar['sd_s']:.0f}) "
                     "— a ritmusa kiszámítható volt.")
    except Exception:
        pass
    # Hajrá-lövésválasztás: elkapkodták-e a végén a befejezést.
    try:
        from .momentum import clutch_shot_quality
        csq = clutch_shot_quality(match)
        if csq.get("available"):
            for side, name in (("home", home), ("away", away)):
                rec_cs = csq[side]
                if rec_cs["verdict"] is None:
                    continue
                if rec_cs["verdict"] == "elkapkodja":
                    body += (f" A(z) {name} a hajrában elkapkodta a "
                             f"befejezést: a lövéseik helyzetértéke "
                             f"{rec_cs['early_avg']:.2f}-ről "
                             f"{rec_cs['clutch_avg']:.2f}-re esett.")
                else:
                    body += (f" A(z) {name} a hajrában kidolgozta a "
                             f"helyzeteket (a lövések helyzetértéke "
                             f"{rec_cs['early_avg']:.2f}-ről "
                             f"{rec_cs['clutch_avg']:.2f}-re nőtt).")
    except Exception:
        pass
    # Játékos-mérleg: kinek a pályán léte alatt ment jobban a játék.
    try:
        from .stats import player_plus_minus
        pmm = player_plus_minus(match)
        for side, name in (("home", home), ("away", away)):
            best_pm = pmm[side]["best"]
            if best_pm is None:
                continue
            jn = _jersey_of_track(match).get(best_pm["player_id"])
            who = (f"{jn}-es mezszámú játékosával" if jn is not None
                   else f"{best_pm['player_id']} azonosítójú "
                        "játékosával")
            body += (f" A(z) {name} {who} a pályán ment a legjobban: "
                     f"{best_pm['for']}-{best_pm['against']} a mérleg "
                     f"{best_pm['minutes']:.0f} perc alatt.")
    except Exception:
        pass
    # Célba vett védő: melyik védő előtt fejezte be az ellenfél a
    # legtöbbször, és hol lett belőle gól is.
    try:
        from .defense import targeted_defenders
        tdf = targeted_defenders(match)
        for side, name in (("home", home), ("away", away)):
            tgt = tdf[side]["weak"] or tdf[side]["target"]
            if tgt is None:
                continue
            jn = tgt["jersey"] or _jersey_of_track(match).get(
                tgt["player_id"])
            who = (f"{jn}-es mezszámú védője" if jn is not None
                   else f"{tgt['player_id']} azonosítójú védője")
            body += (f" A(z) {name} védekezésében a(z) {who} előtt "
                     f"fejeztek be a legtöbbször: {tgt['shots']} lövés, "
                     f"{tgt['goals']} gól.")
    except Exception:
        pass
    # Védekezés-váltás: egy rendszert játszottak, vagy váltogattak.
    try:
        from .tactics import formation_switching
        fsw = formation_switching(match)
        for side, name in (("home", home), ("away", away)):
            rec_fs = fsw[side]
            if rec_fs["verdict"] is None:
                continue
            if rec_fs["verdict"] == "váltogatós":
                body += (f" A(z) {name} védekezésben váltogatott "
                         f"(a védekezett támadások "
                         f"{rec_fs['switch_pct']:.0f}%-ánál más fal "
                         f"volt, a fő forma a {rec_fs['main']}).")
            else:
                body += (f" A(z) {name} végig egy rendszert játszott "
                         f"védekezésben ({rec_fs['main']}, a "
                         f"védekezett támadások "
                         f"{rec_fs['main_pct']:.0f}%-ában).")
    except Exception:
        pass
    # Labdatartás-idő: kinél állt meg a labda a csapatátlaghoz képest.
    try:
        from .decisions import hold_time_players
        htp = hold_time_players(match)
        for side, name in (("home", home), ("away", away)):
            slow = htp[side]["slowest"]
            if slow is None:
                continue
            jn = slow["jersey"] or _jersey_of_track(match).get(
                slow["player_id"])
            who = (f"{jn}-es mezszámú játékosánál" if jn is not None
                   else f"{slow['player_id']} azonosítójú játékosánál")
            body += (f" A(z) {name} {who} állt meg a leginkább a "
                     f"labda: átlag {slow['avg_s']:.1f} mp-et tartotta "
                     f"({slow['holds']} labdás szakasz, a csapatátlag "
                     f"{htp[side]['avg_s']:.1f} mp).")
    except Exception:
        pass
    # Csere-blokkok: egyesével cseréltek, vagy egységekben.
    try:
        from .substitutions import substitution_blocks
        sbl = substitution_blocks(match)
        for side, name in (("home", home), ("away", away)):
            rec_sb = sbl[side]
            if rec_sb["verdict"] is None:
                continue
            if rec_sb["verdict"] == "blokkos csere":
                body += (f" A(z) {name} egységekben cserélt "
                         f"({rec_sb['waves']} hullámból "
                         f"{rec_sb['block_waves']} volt 2+ fős, "
                         f"átlag {rec_sb['avg_size']:.1f} ember).")
            else:
                body += (f" A(z) {name} egyesével cserélt "
                         f"({rec_sb['waves']} hullám, átlag "
                         f"{rec_sb['avg_size']:.1f} ember).")
    except Exception:
        pass
    # Páros-mérleg: melyik kettősük ment a legjobban együtt.
    try:
        from .stats import pair_plus_minus
        prm = pair_plus_minus(match)
        for side, name in (("home", home), ("away", away)):
            best_pr = prm[side]["best"]
            if best_pr is None:
                continue
            jm = _jersey_of_track(match)
            who = " és ".join(
                (f"{jm[pid]}-es" if jm.get(pid) is not None
                 else f"{pid} azonosítójú")
                for pid in best_pr["players"])
            body += (f" A(z) {name} legjobb párosa {who} volt: "
                     f"{best_pr['for']}-{best_pr['against']} a mérleg "
                     f"{best_pr['minutes']:.0f} közös perc alatt.")
    except Exception:
        pass
    # Időkérés-időzítés: hány kapott gól után nyúltak a korongért.
    try:
        from .stoppages import timeout_timing
        tot = timeout_timing(match)
        for side, name in (("home", home), ("away", away)):
            rec_tt = tot[side]
            if rec_tt["verdict"] is None:
                continue
            if rec_tt["verdict"] == "gyors fék":
                body += (f" A(z) {name} korán fékezett: átlag "
                         f"{rec_tt['avg_before']:.1f} kapott gól után "
                         f"kért időt ({rec_tt['timeouts']} időkérés).")
            else:
                body += (f" A(z) {name} hagyta elszaladni a "
                         f"sorozatokat: átlag "
                         f"{rec_tt['avg_before']:.1f} kapott gól után "
                         f"kért időt ({rec_tt['timeouts']} időkérés).")
    except Exception:
        pass
    # Kapus-bevonás: mennyire játszottak vissza a kapusnak.
    try:
        from .goalkeeper import keeper_involvement
        kiv = keeper_involvement(match)
        for side, name in (("home", home), ("away", away)):
            rec_kiv = kiv[side]
            if rec_kiv["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_kiv['verdict']}: a "
                     f"birtoklásaik {rec_kiv['share_pct']:.0f}%-ában "
                     "megjárta a labda a kapust.")
    except Exception:
        pass
    # Indítás-állás: vezetve lassítják-e a kapus-indítást.
    try:
        from .goalkeeper import outlet_pace_by_score
        ops = outlet_pace_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_ops = ops[side]
            if rec_ops["verdict"] is None:
                continue
            body += (f" A(z) {name} kihozataláról kiderült: "
                     f"{rec_ops['verdict']} (átlag "
                     f"{rec_ops['lead']['avg_s']:.1f} mp vezetve, "
                     f"{rec_ops['rest']['avg_s']:.1f} mp egyébként).")
    except Exception:
        pass
    # Csere-állás: vezetve forgatnak-e.
    try:
        from .substitutions import subs_by_score
        sbs = subs_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_sbs = sbs[side]
            if rec_sbs["verdict"] is None:
                continue
            body += (f" A(z) {name} csere-rendjéről kiderült: "
                     f"{rec_sbs['verdict']} "
                     f"({rec_sbs['lead_subs']} cserehullám vezetve, "
                     f"{rec_sbs['rest_subs']} egyébként).")
    except Exception:
        pass
    # Előny-védekezés: leül-e a fal, amikor vezetnek.
    try:
        from .xg import defense_by_score
        dbs = defense_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_dbs = dbs[side]
            if rec_dbs["verdict"] is None:
                continue
            body += (f" A(z) {name} faláról kiderült: "
                     f"{rec_dbs['verdict']} (kapott átlag-xG "
                     f"vezetve {rec_dbs['leading']['avg_xg']:.2f}, "
                     f"egyébként {rec_dbs['rest']['avg_xg']:.2f}).")
    except Exception:
        pass
    # Hiba-állás: hátrányban szórják-e a labdát.
    try:
        from .attack_types import turnovers_by_score
        tbs = turnovers_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_tbs = tbs[side]
            if rec_tbs["verdict"] is None:
                continue
            tr_tbs = rec_tbs["trailing"]
            body += (f" A(z) {name} hátrány-viselkedéséről kiderült: "
                     f"{rec_tbs['verdict']} "
                     f"({tr_tbs['turnovers']}/{tr_tbs['attacks']} "
                     "hátrányban futott támadás zárult eladással).")
    except Exception:
        pass
    # Lepattanó-poszt: ki viszi a második rohamot.
    try:
        from .attack_types import second_chance_roles
        scr = second_chance_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_scr = scr[side]
            if rec_scr["verdict"] is None:
                continue
            body += (f" A(z) {name} második rohamát a(z) "
                     f"{rec_scr['main_role']} viszi "
                     f"({rec_scr['share_pct']:.0f}%, "
                     f"{rec_scr['second_shots']} második lövésből) — a "
                     "lövés zárása után az első dolog őt kivenni a "
                     "lepattanóból.")
    except Exception:
        pass
    # Labdaszerző-poszt: melyik posztjuk nyeri a labdákat.
    try:
        from .defense import role_steal_sources
        rsw = role_steal_sources(match)
        for side, name in (("home", home), ("away", away)):
            rec_rsw = rsw[side]
            if rec_rsw["verdict"] is None:
                continue
            body += (f" A(z) {name} labdaszerzése egy poszton áll: a "
                     f"szerzéseik {rec_rsw['share_pct']:.0f}%-a a(z) "
                     f"{rec_rsw['main_role']} posztról jön "
                     f"({rec_rsw['steals']} szerzésből) — az ő sávjába "
                     "csak biztonsági passz mehet.")
    except Exception:
        pass
    # Blokkolt-poszt: melyik posztjuk lövéseit blokkolják.
    try:
        from .defense import blocked_shooter_roles
        bsr = blocked_shooter_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_bsr = bsr[side]
            if rec_bsr["verdict"] is None:
                continue
            body += (f" A(z) {name} falba lőtt labdái a(z) "
                     f"{rec_bsr['main_role']} posztról jönnek "
                     f"({rec_bsr['share_pct']:.0f}%, "
                     f"{rec_bsr['blocks']} blokkból) — a fal ellene "
                     "bátran zárhat.")
    except Exception:
        pass
    # Hetesdobó-poszt: melyik posztjuk áll oda a hetesekhez.
    try:
        from .rules import seven_taker_roles
        stk = seven_taker_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_stk = stk[side]
            if rec_stk["verdict"] is None:
                continue
            body += (f" A(z) {name} heteseit {rec_stk['share_pct']:.0f}"
                     f"%-ban a(z) {rec_stk['main_role']} posztja "
                     f"dobja ({rec_stk['attempts']} hetesből) — a "
                     "kapus az ő szokás-irányaira készüljön.")
    except Exception:
        pass
    # Újrakezdő-poszt: melyik posztjuk viszi a szünet utáni rajtot.
    try:
        from .momentum import second_start_roles
        ssr = second_start_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_ssr = ssr[side]
            if rec_ssr["verdict"] is None:
                continue
            body += (f" A(z) {name} szünet utáni rajtja a(z) "
                     f"{rec_ssr['main_role']} posztra épül "
                     f"({rec_ssr['share_pct']:.0f}%, "
                     f"{rec_ssr['goals']} gól a második félidő első"
                     " tíz percében) — a szünet után őt kell "
                     "megfogni.")
    except Exception:
        pass
    # Elzárt-poszt: melyik védőjük akad el az elzárásokban.
    try:
        from .defense import screened_defender_roles
        sdr = screened_defender_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_sdr = sdr[side]
            if rec_sdr["verdict"] is None:
                continue
            body += (f" A(z) {name} védelmében az elzárások a(z) "
                     f"{rec_sdr['main_role']} poszton lévő védőt "
                     f"találják meg ({rec_sdr['share_pct']:.0f}%, "
                     f"{rec_sdr['screens']} elakadásból) — az ő "
                     "oldalán tisztán marad a lövő.")
    except Exception:
        pass
    # Kettőzött-poszt: melyik posztjukra érkezik a kettőzés.
    try:
        from .defense import doubled_target_roles
        dtr = doubled_target_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_dtr = dtr[side]
            if rec_dtr["verdict"] is None:
                continue
            body += (f" A(z) {name} ellen a kettőzések a(z) "
                     f"{rec_dtr['main_role']} posztra járnak "
                     f"({rec_dtr['share_pct']:.0f}%-a a kettőzött "
                     "labdás időnek) — a minta bevált recept.")
    except Exception:
        pass
    # Fáradó-poszt: melyik posztjuk esik vissza a második félidőre.
    try:
        from .stats import fatigue_roles
        ftr = fatigue_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_ftr = ftr[side]
            if rec_ftr["verdict"] is None:
                continue
            body += (f" A(z) {name} tempója a(z) "
                     f"{rec_ftr['main_role']} poszton esik vissza a "
                     f"második félidőre (−{rec_ftr['drop_pct']:.0f}"
                     "%) — a szünet után az ő sávjában érdemes "
                     "támadni.")
    except Exception:
        pass
    # Passzív-poszt: melyik posztjuknál hal el a felállt támadás.
    try:
        from .rules import passive_holder_roles
        pvr = passive_holder_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_pvr = pvr[side]
            if rec_pvr["verdict"] is None:
                continue
            body += (f" A(z) {name} terméketlen támadásai a(z) "
                     f"{rec_pvr['main_role']} posztnál halnak el "
                     f"({rec_pvr['share_pct']:.0f}%-a a lövés "
                     "nélküli hosszú támadások labdás idejének) — "
                     "passzív jelzésnél őt kell nyomás alá tenni.")
    except Exception:
        pass
    # Rajt-poszt: melyik posztjuk viszi a meccs elejét.
    try:
        from .momentum import opening_scorer_roles
        osr = opening_scorer_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_osr = osr[side]
            if rec_osr["verdict"] is None:
                continue
            body += (f" A(z) {name} rajtja a(z) "
                     f"{rec_osr['main_role']} posztra épül "
                     f"({rec_osr['share_pct']:.0f}%, "
                     f"{rec_osr['goals']} gól az első tíz percben) —"
                     " a meccs elején őt kell megfogni.")
    except Exception:
        pass
    # Kiszolgált-poszt: melyik posztjuk fejezi be a bejátszásokat.
    try:
        from .roles import assisted_scorer_roles
        asr = assisted_scorer_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_asr = asr[side]
            if rec_asr["verdict"] is None:
                continue
            body += (f" A(z) {name} kiszolgált góljait a(z) "
                     f"{rec_asr['main_role']} posztja fejezi be "
                     f"({rec_asr['share_pct']:.0f}%, "
                     f"{rec_asr['assisted']} asszisztos gólból) — őt"
                     " a felé futó passz elvágásával kell éheztetni.")
    except Exception:
        pass
    # Hajrákéz-poszt: melyik poszt kezén fut a végjátékuk.
    try:
        from .momentum import clutch_hog_roles
        chg = clutch_hog_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_chg = chg[side]
            if rec_chg["verdict"] is None:
                continue
            body += (f" A(z) {name} végjátéka a(z) "
                     f"{rec_chg['main_role']} poszt kezén fut "
                     f"({rec_chg['share_pct']:.0f}%-a az utolsó öt "
                     "perc labdás idejének) — a hajrá-kettőzés ezt a"
                     " kezet fogja, nem a lövőt.")
    except Exception:
        pass
    # Lágypassz-poszt: melyik posztjuk passzol lágyan.
    try:
        from .decisions import soft_pass_roles
        sps = soft_pass_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_sps = sps[side]
            if rec_sps["verdict"] is None:
                continue
            body += (f" A(z) {name} lágy passzai a(z) "
                     f"{rec_sps['main_role']} posztról jönnek "
                     f"({rec_sps['share_pct']:.0f}%, "
                     f"{rec_sps['soft']} lágy passzból) — az ő "
                     "labdáiba bele lehet nyúlni.")
    except Exception:
        pass
    # Sprint-poszt: melyik posztjuk futja a sprinteket.
    try:
        from .stats import sprint_threat_roles
        spr = sprint_threat_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_spr = spr[side]
            if rec_spr["verdict"] is None:
                continue
            body += (f" A(z) {name} kontráját a(z) "
                     f"{rec_spr['main_role']} posztja futja "
                     f"({rec_spr['share_pct']:.0f}%, "
                     f"{rec_spr['sprints']} sprintből) — "
                     "labdavesztésnél az ő útja zárandó először.")
    except Exception:
        pass
    # Középkezdő-poszt: melyik posztjuknál indul a középkezdés.
    try:
        from .momentum import restart_taker_roles
        rtr = restart_taker_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_rtr = rtr[side]
            if rec_rtr["verdict"] is None:
                continue
            body += (f" A(z) {name} középkezdése a(z) "
                     f"{rec_rtr['main_role']} posztnál indul "
                     f"({rec_rtr['share_pct']:.0f}%, "
                     f"{rec_rtr['takes']} átvételből) — a gól utáni "
                     "letámadásnak posztra szóló célpontja van.")
    except Exception:
        pass
    # Forró-poszt: melyik posztjuk lövi a gólsorozatokat.
    try:
        from .momentum import hot_hand_roles
        hhr = hot_hand_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_hhr = hhr[side]
            if rec_hhr["verdict"] is None:
                continue
            body += (f" A(z) {name} gólsorozatait a(z) "
                     f"{rec_hhr['main_role']} posztja lövi "
                     f"({rec_hhr['share_pct']:.0f}%, "
                     f"{rec_hhr['streak_goals']} sorozat-gólból) — az"
                     " első gólja után azonnal reagálni kell.")
    except Exception:
        pass
    # Hajráhiba-poszt: melyik posztjuk adja el a labdát a hajrában.
    try:
        from .momentum import clutch_turnover_roles
        ctr = clutch_turnover_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_ctr = ctr[side]
            if rec_ctr["verdict"] is None:
                continue
            body += (f" A(z) {name} hajrá-eladásai a(z) "
                     f"{rec_ctr['main_role']} posztnál történnek "
                     f"({rec_ctr['share_pct']:.0f}%, "
                     f"{rec_ctr['turnovers']} eladás az utolsó öt "
                     "percben) — a záró percekben oda jön a pressz.")
    except Exception:
        pass
    # Eltűnő-poszt: melyik posztjuk tűnik el a második félidőre.
    try:
        from .momentum import fading_scorer_roles
        fdp = fading_scorer_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_fdp = fdp[side]
            if rec_fdp["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_fdp['main_role']} posztja "
                     f"az első félidőben él ({rec_fdp['fh']} "
                     f"gól-részvétel), a másodikra eltűnik "
                     f"({rec_fdp['sh']}) — az első 30 percben kell "
                     "megfogni.")
    except Exception:
        pass
    # Csendtörő-poszt: melyik posztjuk töri meg a gólcsendet.
    try:
        from .momentum import drought_breaker_roles
        gct = drought_breaker_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_gct = gct[side]
            if rec_gct["verdict"] is None:
                continue
            body += (f" A(z) {name} válság-posztja a(z) "
                     f"{rec_gct['main_role']}: a gólcsendjeik "
                     f"{rec_gct['share_pct']:.0f}%-át ő töri meg "
                     f"({rec_gct['breaks']} csend-törő gólból) — az "
                     "ellenfél sorozata alatt őt kell fogni.")
    except Exception:
        pass
    # Pressz-poszt: melyik posztjuk ejti a labdát szorításban.
    try:
        from .decisions import press_sensitive_roles
        psr = press_sensitive_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_psr = psr[side]
            if rec_psr["verdict"] is None:
                continue
            body += (f" A(z) {name} szorításban a(z) "
                     f"{rec_psr['main_role']} posztnál veszíti a "
                     f"labdát ({rec_psr['share_pct']:.0f}%, "
                     f"{rec_psr['press_to']} nyomott eladásból) — a "
                     "kettőzést oda kell küldeni.")
    except Exception:
        pass
    # Labdatartó-poszt: melyik posztjuknál áll meg a labda.
    try:
        from .decisions import hold_time_roles
        htr = hold_time_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_htr = htr[side]
            if rec_htr["verdict"] is None:
                continue
            body += (f" A(z) {name} játéka a(z) "
                     f"{rec_htr['main_role']} posztnál lassul: a mért"
                     f" labdatartásuk {rec_htr['share_pct']:.0f}%-a "
                     f"nála telik ({rec_htr['seconds']:.0f} mp-ből) —"
                     " a kettőzést rá kell időzíteni.")
    except Exception:
        pass
    # Ziccer-poszt: melyik posztjuknál alakul ki a nagy helyzet.
    try:
        from .xg import big_chance_roles
        bcr = big_chance_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_bcr = bcr[side]
            if rec_bcr["verdict"] is None:
                continue
            body += (f" A(z) {name} ziccerei egy posztnál alakulnak "
                     f"ki: a nagy helyzeteik {rec_bcr['share_pct']:.0f}"
                     f"%-a a(z) {rec_bcr['main_role']} posztnál jön "
                     f"létre ({rec_bcr['chances']} ziccerből) — ott a "
                     "helyzetet a kialakulása előtt kell megfogni.")
    except Exception:
        pass
    # Pazarló-poszt: melyik posztjuk lövi mellé a lövéseit.
    try:
        from .xg import wasteful_shooter_roles
        wsr = wasteful_shooter_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_wsr = wsr[side]
            if rec_wsr["verdict"] is None:
                continue
            body += (f" A(z) {name} pontatlansága egy posztra "
                     f"sűrűsödik: a kaput elkerülő lövéseik "
                     f"{rec_wsr['share_pct']:.0f}%-a a(z) "
                     f"{rec_wsr['main_role']} posztról jön "
                     f"({rec_wsr['off_target']} mellé/blokkolt "
                     "lövésből) — az ő lövését rá lehet engedni.")
    except Exception:
        pass
    # Felzárkózás-poszt: melyik posztjuk hozza őket vissza.
    try:
        from .momentum import comeback_carrier_roles
        cbr = comeback_carrier_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_cbr = cbr[side]
            if rec_cbr["verdict"] is None:
                continue
            body += (f" A(z) {name} mentőjátéka egy posztra épül: "
                     f"hátrányból {rec_cbr['share_pct']:.0f}%-ban a(z)"
                     f" {rec_cbr['main_role']} hozza őket vissza "
                     f"({rec_cbr['trailing']} részvételből) — az ő "
                     "kivétele a hátrányukat beragasztja.")
    except Exception:
        pass
    # Hajrá-poszt: melyik posztjuk viszi a végjátékot.
    try:
        from .momentum import clutch_scorer_roles
        csr = clutch_scorer_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_csr = csr[side]
            if rec_csr["verdict"] is None:
                continue
            body += (f" A(z) {name} végjátéka egy posztra fut ki: a "
                     f"hajrá-góljaik {rec_csr['share_pct']:.0f}%-a "
                     f"a(z) {rec_csr['main_role']} poszté "
                     f"({rec_csr['goals']} hajrá-gólból) — az utolsó "
                     "öt percben őt kell fogni.")
    except Exception:
        pass
    # Emberhátrány-poszt: melyik posztjuk vállal be öt emberrel.
    try:
        from .rules import shorthanded_shooter_roles
        shr = shorthanded_shooter_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_shr = shr[side]
            if rec_shr["verdict"] is None:
                continue
            body += (f" A(z) {name} öt emberrel is kiszámítható: a "
                     f"hátrány-lövéseik {rec_shr['share_pct']:.0f}%-a "
                     f"a(z) {rec_shr['main_role']} poszté "
                     f"({rec_shr['shots']} lövésből) — emberelőnyben "
                     "az ő oldalán kell a labdabiztonság.")
    except Exception:
        pass
    # Emberelőny-poszt: melyik posztjuk fejez be a két perc alatt.
    try:
        from .rules import powerplay_shooter_roles
        ppr = powerplay_shooter_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_ppr = ppr[side]
            if rec_ppr["verdict"] is None:
                continue
            body += (f" A(z) {name} emberelőnye egy posztra fut ki: "
                     f"a lövéseik {rec_ppr['share_pct']:.0f}%-a a(z) "
                     f"{rec_ppr['main_role']} poszté "
                     f"({rec_ppr['shots']} emberelőny-lövésből) — "
                     "hátrányban az ő sávját kell tartani.")
    except Exception:
        pass
    # Kiosztás-poszt: melyik posztra jár a betörés utáni labda.
    try:
        from .attack_types import kickout_target_roles
        kor = kickout_target_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_kor = kor[side]
            if rec_kor["verdict"] is None:
                continue
            body += (f" A(z) {name} betörései utáni labda egy posztra "
                     f"jár: {rec_kor['share_pct']:.0f}%-ban a(z) "
                     f"{rec_kor['main_role']} kapja "
                     f"({rec_kor['kickouts']} kiosztásból) — a védője "
                     "előre elmozdulhat a passzsávba.")
    except Exception:
        pass
    # Kettőző-poszt: melyik posztjuk lép ki kettőzni.
    try:
        from .defense import doubling_defender_roles
        ddr = doubling_defender_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_ddr = ddr[side]
            if rec_ddr["verdict"] is None:
                continue
            body += (f" A(z) {name} kettőzése kiolvasható: "
                     f"{rec_ddr['share_pct']:.0f}%-ban a(z) "
                     f"{rec_ddr['main_role']} posztról érkezik — a "
                     "kettőzés pillanatában az ő elhagyott embere az "
                     "üres ember.")
    except Exception:
        pass
    # Kockáztató-poszt: melyik posztjuk szórja el a hosszú labdákat.
    try:
        from .attack_types import risky_passer_roles
        rpr = risky_passer_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_rpr = rpr[side]
            if rec_rpr["verdict"] is None:
                continue
            body += (f" A(z) {name} hazárd hosszú labdái egy posztról "
                     f"jönnek: {rec_rpr['share_pct']:.0f}%-uk a(z) "
                     f"{rec_rpr['main_role']} poszté "
                     f"({rec_rpr['turnovers']} elszórt hosszúból) — az"
                     " ő passzsávjába kell beállni.")
    except Exception:
        pass
    # Vasember-poszt: melyik posztjuk játszik végig csere nélkül.
    try:
        from .stats import iron_man_roles
        irm = iron_man_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_irm = irm[side]
            if rec_irm["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_irm['main_role']} posztja "
                     f"végigjátssza a meccset "
                     f"({rec_irm['share_pct']:.0f}% jelenlét) — a "
                     "hajrában oda kell vinni a tempót.")
    except Exception:
        pass
    # Bejátszó-poszt: melyik posztjuk játssza be a beállót.
    try:
        from .attack_types import pivot_feeder_roles
        pfr = pivot_feeder_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_pfr = pfr[side]
            if rec_pfr["verdict"] is None:
                continue
            body += (f" A(z) {name} beálló-játéka egy posztról fut: a "
                     f"beadásaik {rec_pfr['share_pct']:.0f}%-a a(z) "
                     f"{rec_pfr['main_role']} poszté "
                     f"({rec_pfr['feeds']} beadásból) — az ő kezén "
                     "kell a beálló-vonalba lépni.")
    except Exception:
        pass
    # Indítás-vadász poszt: melyik posztjuk vadássza az indítást.
    try:
        from .goalkeeper import outlet_hunter_roles
        ohr = outlet_hunter_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_ohr = ohr[side]
            if rec_ohr["verdict"] is None:
                continue
            body += (f" A(z) {name} indítás-vadászata egy poszton "
                     f"fut: a rablásaik {rec_ohr['share_pct']:.0f}%-a "
                     f"a(z) {rec_ohr['main_role']} poszté "
                     f"({rec_ohr['steals']} elrabolt indításból) — a "
                     "kapus-indítás a másik oldalon nyisson.")
    except Exception:
        pass
    # Kulcs-poszt: hány réteg mutat ugyanarra a posztra.
    try:
        from .priorities import key_post
        kp = key_post(match)
        for side, name in (("home", home), ("away", away)):
            rec_kp = kp[side]
            if rec_kp["verdict"] is None:
                continue
            body += (f" A(z) {name} kulcs-posztja a(z) "
                     f"{rec_kp['top']}: "
                     f"{rec_kp['posts'][rec_kp['top']]} réteg ítélete "
                     "fut ki rá — az ő kezelése a meccsterv első "
                     "lapja.")
    except Exception:
        pass
    # Elzáró-poszt: melyik posztjuk áll elzárásba.
    try:
        from .attack_types import screen_setter_roles
        sc2 = screen_setter_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_sc2 = sc2[side]
            if rec_sc2["verdict"] is None:
                continue
            body += (f" A(z) {name} elzárás-játéka egy posztra épül: "
                     f"az elzárásaik {rec_sc2['share_pct']:.0f}%-a "
                     f"a(z) {rec_sc2['main_role']} poszté "
                     f"({rec_sc2['screens']} elzárásból) — az ő "
                     "oldalán hangos váltás kell.")
    except Exception:
        pass
    # Átvert-poszt: melyik posztjuk mögött esnek a kapott gólok.
    try:
        from .defense import beaten_defender_roles
        btr = beaten_defender_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_btr = btr[side]
            if rec_btr["verdict"] is None:
                continue
            body += (f" A(z) {name} kapott góljai egy poszton esnek: "
                     f"{rec_btr['share_pct']:.0f}%-uk a(z) "
                     f"{rec_btr['main_role']} párharc-vereségéből jön "
                     f"({rec_btr['goals']} védőhöz rendelt gólból) — "
                     "oda kell vinni az 1v1-et.")
    except Exception:
        pass
    # Visszafutás-poszt: ki marad le a visszarendeződésben.
    try:
        from .defense import slow_retreat_roles
        rtr = slow_retreat_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_rtr = rtr[side]
            if rec_rtr["verdict"] is None:
                continue
            body += (f" A(z) {name} visszarendeződése a(z) "
                     f"{rec_rtr['main_role']} poszton szakad el "
                     f"({rec_rtr['share_pct']:.0f}%, {rec_rtr['breaks']}"
                     " kontrából ő maradt elöl) — a kontrát az ő "
                     "sávjába kell vezetni.")
    except Exception:
        pass
    # Kiülő-poszt: melyik posztjuk gyűjti a kétperceket.
    try:
        from .rules import suspended_roles
        sup = suspended_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_sup = sup[side]
            if rec_sup["verdict"] is None:
                continue
            body += (f" A(z) {name} kétpercei egy posztra járnak: a "
                     f"kiállításaik {rec_sup['share_pct']:.0f}%-a a(z) "
                     f"{rec_sup['main_role']} poszté "
                     f"({rec_sup['suspensions']} kiállításból) — a "
                     "meccs elején oda érdemes vezetni a játékot.")
    except Exception:
        pass
    # Hetes-okozó poszt: melyik sávjuk szakad be hetessel.
    try:
        from .rules import seven_conceder_roles
        svr = seven_conceder_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_svr = svr[side]
            if rec_svr["verdict"] is None:
                continue
            body += (f" A(z) {name} hetesei egy sávban szakadnak be: "
                     f"az okozott heteseik {rec_svr['share_pct']:.0f}"
                     f"%-a a(z) {rec_svr['main_role']} poszté "
                     f"({rec_svr['sevens']} hetesből) — oda érdemes "
                     "betörést vezetni.")
    except Exception:
        pass
    # 7a6-befejező poszt: kire fut ki a hetedik ember játéka.
    try:
        from .goalkeeper import seven_six_finisher_roles
        en7 = seven_six_finisher_roles(match)
        for side, name in (("home", home), ("away", away)):
            rec_en7 = en7[side]
            if rec_en7["verdict"] is None:
                continue
            body += (f" A(z) {name} 7 a 6-a kiszámítható: a lövéseik "
                     f"{rec_en7['share_pct']:.0f}%-a a(z) "
                     f"{rec_en7['main_role']} posztról jön "
                     f"({rec_en7['shots']} lövésből) — a lehozott "
                     "kapus felismerésekor oda kell sűríteni.")
    except Exception:
        pass
    # Blokk-poszt: melyik posztjuk blokkolja a lövéseket.
    try:
        from .defense import role_block_sources
        rbk = role_block_sources(match)
        for side, name in (("home", home), ("away", away)):
            rec_rbk = rbk[side]
            if rec_rbk["verdict"] is None:
                continue
            body += (f" A(z) {name} blokk-munkája egy poszton áll: a "
                     f"blokkjaik {rec_rbk['share_pct']:.0f}%-a a(z) "
                     f"{rec_rbk['main_role']} poszttól jön "
                     f"({rec_rbk['blocks']} blokkból) — az ő sávjába "
                     "csak elmozgatás után szabad lőni.")
    except Exception:
        pass
    # Gólpassz-poszt: kinek a kezéből indulnak a gólok.
    try:
        from .roles import role_assist_sources
        ras = role_assist_sources(match)
        for side, name in (("home", home), ("away", away)):
            rec_ras = ras[side]
            if rec_ras["verdict"] is None:
                continue
            body += (f" A(z) {name} góljai a(z) {rec_ras['main_role']} "
                     f"kezéből indulnak ({rec_ras['share_pct']:.0f}%, "
                     f"{rec_ras['assists']} gólpasszból) — tőle a "
                     "passzt kell elvenni, nem a lövést zárni.")
    except Exception:
        pass
    # Hetes-oldal: merre dobják a heteseiket.
    try:
        from .rules import seven_shot_directions
        svd = seven_shot_directions(match)
        for side, name in (("home", home), ("away", away)):
            rec_svd = svd[side]
            if rec_svd["verdict"] is None:
                continue
            body += (f" A(z) {name} hetesei kiszámíthatók: "
                     f"{rec_svd['share_pct']:.0f}%-uk "
                     f"{rec_svd['dominant']} oldalra megy "
                     f"({rec_svd['attempts']} mérhető dobásból) — "
                     "hetesnél a kapus tudatosan arra vetődhet.")
    except Exception:
        pass
    # Kontra-poszt: kit kell először felvenni visszafutásnál.
    try:
        from .roles import role_fast_breaks
        rfb = role_fast_breaks(match)
        for side, name in (("home", home), ("away", away)):
            rec_rfb = rfb[side]
            if rec_rfb["verdict"] is None:
                continue
            body += (f" A(z) {name} lerohanásai a(z) "
                     f"{rec_rfb['main_role']} poszton záródnak "
                     f"({rec_rfb['share_pct']:.0f}%, "
                     f"{rec_rfb['shots']} kontra-lövésből) — "
                     "visszafutásnál őt kell először felvenni.")
    except Exception:
        pass
    # Lövésválasztás: felnéznek-e a lövés előtt.
    try:
        from .decisions import shot_choice_quality
        scq = shot_choice_quality(match)
        for side, name in (("home", home), ("away", away)):
            rec_scq = scq[side]
            if rec_scq["verdict"] is None or rec_scq["pct"] is None:
                continue
            body += (f" A(z) {name} lövésválasztásáról: "
                     f"{rec_scq['verdict']} "
                     f"({rec_scq['better_options']}/{rec_scq['shots']} "
                     "lövés).")
    except Exception:
        pass
    # Időkérés-befejező: az időkérés után kire játszanak.
    try:
        from .stoppages import timeout_finisher
        tof = timeout_finisher(match)
        for side, name in (("home", home), ("away", away)):
            rec_tof = tof[side]
            if rec_tof["verdict"] is None:
                continue
            body += (f" A(z) {name} időkérés után a(z) "
                     f"{rec_tof['main_role']} posztra játszik: az "
                     f"újraindítás utáni lövéseik "
                     f"{rec_tof['share_pct']:.0f}%-a onnan jött "
                     f"({rec_tof['shots']} lövésből, "
                     f"{rec_tof['timeouts']} időkérés után) — a "
                     "megbeszélésen ő kapja az embert.")
    except Exception:
        pass
    # Figura-befejező: melyik figurájuk kire fut ki.
    try:
        from .setplays import setplay_finishers
        spf = setplay_finishers(match)
        for side, name in (("home", home), ("away", away)):
            tel_spf = spf[side]["telegraphed"]
            if tel_spf is None:
                continue
            body += (f" A(z) {name} {tel_spf['figure']}. figurája "
                     f"kiszámítható befejezésű: a lövéseinek "
                     f"{tel_spf['share_pct']:.0f}%-a a(z) "
                     f"{tel_spf['poszt']} posztra fut ki "
                     f"({tel_spf['shots']} lövésből) — a falnak már a "
                     "figura indulásakor arra az oldalra kell csúsznia.")
    except Exception:
        pass
    # Poszt-nyomás: kire kell kilépni, kit kell kizárni.
    try:
        from .roles import role_pressure_finish
        rpf = role_pressure_finish(match)
        for side, name in (("home", home), ("away", away)):
            rec_rpf = rpf[side]
            cold_rpf = rec_rpf["coldblooded"]
            if cold_rpf is None:
                continue
            body += (f" A(z) {name} nyomás alatt is befejező posztja a(z) "
                     f"{cold_rpf['poszt']}: a fedezett lövéseik "
                     f"{cold_rpf['covered_pct']:.0f}%-át belövi "
                     f"({cold_rpf['covered_shots']} lövésből) — őt ki "
                     "kell zárni, a puszta kilépés nála kevés.")
    except Exception:
        pass
    # Poszt-kapuoldal: melyik sarokra állhat rá a kapus.
    try:
        from .roles import role_goal_placement
        rgp = role_goal_placement(match)
        for side, name in (("home", home), ("away", away)):
            rec_rgp = rgp[side]
            pred = rec_rgp["predictable"]
            if pred is None:
                continue
            body += (f" A(z) {name} legkiszámíthatóbb befejezője a(z) "
                     f"{pred['poszt']} posztjuk: a góljaik "
                     f"{pred['share_pct']:.0f}%-át {pred['dominant']} "
                     f"oldalra lövik ({pred['goals']} gólból) — a kapus "
                     "arra az oldalra állhat rá, a fal a másikat zárja.")
    except Exception:
        pass
    # Poszt-lövéserő: melyik posztra készüljön a kapus.
    try:
        from .roles import role_shot_power
        rsp = role_shot_power(match)
        for side, name in (("home", home), ("away", away)):
            rec_rsp = rsp[side]
            hard = rec_rsp["hardest"]
            if hard is None:
                continue
            body += (f" A(z) {name} legkeményebb befejezője a(z) "
                     f"{hard['poszt']} posztjuk: átlag "
                     f"{hard['avg_kmh']:.0f} km/h {hard['shots']} "
                     f"lövésen, a csapat-átlaguk "
                     f"{rec_rsp['team_avg_kmh']:.0f} km/h — ellene a "
                     "kapus korábban induljon, a fal szöget zárjon.")
    except Exception:
        pass
    # Poszt-lövésidőzítés: ki lő korán, ki vár ki.
    try:
        from .roles import role_shot_timing
        rst = role_shot_timing(match)
        for side, name in (("home", home), ("away", away)):
            rec_rst = rst[side]
            if rec_rst["verdict"] is None:
                continue
            early, late = rec_rst["earliest"], rec_rst["latest"]
            if early is not None:
                body += (f" A(z) {name} befejezéseiből a(z) "
                         f"{early['poszt']} jön a leghamarabb "
                         f"(átl. {early['avg_s']:.1f} mp {early['shots']} "
                         f"lövésen, a csapat-átlaguk "
                         f"{rec_rst['team_avg_s']:.1f} mp) — rá a "
                         "visszarendeződésnél kell embert rendelni.")
            elif late is not None:
                body += (f" A(z) {name} legkésőbbi befejezője a(z) "
                         f"{late['poszt']} (átl. {late['avg_s']:.1f} mp "
                         f"{late['shots']} lövésen) — az ő labdája a "
                         "kivárás végén jön, ott kell a koncentráció.")
    except Exception:
        pass
    # Poszt-lövéstávolság: kire lépj ki, kire lehet ráengedni.
    try:
        from .roles import role_shot_distance
        rsd = role_shot_distance(match)
        for side, name in (("home", home), ("away", away)):
            rec_rsd = rsd[side]
            if rec_rsd["verdict"] is None:
                continue
            near, far = rec_rsd["closest"], rec_rsd["farthest"]
            if near is not None:
                body += (f" A(z) {name} befejezéseiből a(z) "
                         f"{near['poszt']} jön be a legközelebb "
                         f"(átl. {near['avg_m']:.1f} m {near['shots']} "
                         f"lövésen, a csapat-átlaguk "
                         f"{rec_rsd['team_avg_m']:.1f} m) — őt ki kell "
                         "zárni, mert onnan a kapusnak alig van esélye.")
            elif far is not None:
                body += (f" A(z) {name} legtávolabbi befejezője a(z) "
                         f"{far['poszt']} (átl. {far['avg_m']:.1f} m "
                         f"{far['shots']} lövésen) — rá inkább rá lehet "
                         "engedni, a passzsáv zárása többet ér.")
    except Exception:
        pass
    # Poszt-eladási zóna: kinek az eladása hív kontrát.
    try:
        from .roles import role_turnover_zones
        rtz = role_turnover_zones(match)
        for side, name in (("home", home), ("away", away)):
            rec_rtz = rtz[side]
            if rec_rtz["verdict"] is None:
                continue
            rk = rec_rtz["riskiest"]
            body += (f" A(z) {name} eladásai közül a(z) {rk['poszt']} "
                     f"posztjáé a legveszélyesebb: "
                     f"{rk['front']}/{rk['turnovers']} eladása "
                     f"({rk['front_pct']:.0f}%) a támadó harmadban "
                     f"történt, a csapat-átlaguk "
                     f"{rec_rtz['team_front_pct']:.0f}% — onnan indul a "
                     "kontra.")
    except Exception:
        pass
    # Poszt-labdatartás: melyik posztnál áll meg a labda.
    try:
        from .roles import role_hold_time
        rht = role_hold_time(match)
        for side, name in (("home", home), ("away", away)):
            rec_rht = rht[side]
            if rec_rht["verdict"] is None:
                continue
            sl = rec_rht["slowest"]
            body += (f" A(z) {name} labdajáratásában "
                     f"{rec_rht['verdict']} — a csapat-átlaguk "
                     f"{rec_rht['team_avg_s']:.1f} mp, tehát "
                     f"{sl['gap_s']:.1f} mp-cel tovább; ő a kettőzés "
                     "célpontja.")
    except Exception:
        pass
    # Poszt-átvételi zóna: hol kapja meg a labdát az egyes posztjuk.
    try:
        from .roles import role_receive_zones
        rrz = role_receive_zones(match)
        for side, name in (("home", home), ("away", away)):
            rec_rrz = rrz[side]
            if rec_rrz["verdict"] is None:
                continue
            body += (f" A(z) {name} átvételi zónáiról kiderült: "
                     f"{rec_rrz['verdict']} "
                     f"(csapat-átlaguk {rec_rrz['team_avg_m']:.1f} m, "
                     f"{rec_rrz['receptions']} mért átvételből).")
    except Exception:
        pass
    # Poszt-passzháló: melyik vonalon jár a legtöbb passzuk.
    try:
        from .roles import role_pass_map
        rpm = role_pass_map(match)
        for side, name in (("home", home), ("away", away)):
            rec_rpm = rpm[side]
            if rec_rpm["verdict"] is None:
                continue
            top_rpm = rec_rpm["top"]
            body += (f" A(z) {name} labdajáratásának legterheltebb "
                     f"vonala a(z) {top_rpm['from']} → {top_rpm['to']}: "
                     f"a poszthoz kötött passzaik "
                     f"{top_rpm['share_pct']:.0f}%-a "
                     f"({top_rpm['passes']}/{rec_rpm['passes_total']}) "
                     "megy erre — az elfogás is itt a legvalószínűbb.")
    except Exception:
        pass
    # Poszt-birtoklás: melyik poszt tartja a labdát a támadásaikban.
    try:
        from .roles import role_possession_share
        rps = role_possession_share(match)
        for side, name in (("home", home), ("away", away)):
            rec_rps = rps[side]
            if rec_rps["verdict"] is None:
                continue
            body += (f" A(z) {name} szervezett támadásaiban "
                     f"{rec_rps['verdict']} — a letámadás címzettje "
                     "tehát adott.")
    except Exception:
        pass
    # Poszt-állás: melyik poszton keresztül fejeznek be hátrányban.
    try:
        from .roles import role_share_by_score
        rbs = role_share_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_rbs = rbs[side]
            if rec_rbs["verdict"] is None:
                continue
            sh_rbs = rec_rbs["shift"]
            body += (f" A(z) {name} hátrány-befejezése: "
                     f"{rec_rbs['verdict']} "
                     f"({sh_rbs['trailing_pct']:.0f}% hátrányban vs "
                     f"{sh_rbs['rest_pct']:.0f}% egyébként; "
                     f"{rec_rbs['trailing_total']}/"
                     f"{rec_rbs['rest_total']} poszthoz kötött gól).")
    except Exception:
        pass
    # Eladás-ár poszt szerint: melyik poszt eladása kerül gólba.
    try:
        from .roles import RTC_QUICK_S, role_turnover_cost
        rtc = role_turnover_cost(match)
        for side, name in (("home", home), ("away", away)):
            rec_rtc = rtc[side]
            worst_rtc = rec_rtc.get("worst")
            if worst_rtc is None:
                continue
            body += (f" A(z) {name} eladásainak ára a(z) "
                     f"{worst_rtc['poszt']} posztnál a legnagyobb: "
                     f"{worst_rtc['punished']}/"
                     f"{worst_rtc['turnovers']} eladásukat "
                     f"({worst_rtc['rate_pct']:.0f}%) {RTC_QUICK_S:.0f} "
                     "mp-en belüli kapott gól követte.")
    except Exception:
        pass
    # Poszt-váltás a szünetre: melyik posztra állnak rá a második
    # félidőben.
    try:
        from .roles import role_share_shift
        rss = role_share_shift(match)
        for side, name in (("home", home), ("away", away)):
            rec_rss = rss[side]
            if rec_rss["verdict"] is None:
                continue
            sh = rec_rss["shift"]
            body += (f" A(z) {name} befejezése átrendeződik a szünetre: "
                     f"{rec_rss['verdict']} "
                     f"({sh['first_pct']:.0f}% → {sh['second_pct']:.0f}% "
                     f"a poszthoz kötött góljaikból; "
                     f"{rec_rss['first_total']}/"
                     f"{rec_rss['second_total']} gól a két félidőben).")
    except Exception:
        pass
    # Gólpassz-tengely: melyik vonalon esnek a góljaik.
    try:
        from .roles import assist_role_pairs
        arp = assist_role_pairs(match)
        for side, name in (("home", home), ("away", away)):
            rec_arp = arp[side]
            top_arp = rec_arp.get("top")
            if top_arp is None:
                continue
            body += (f" A(z) {name} gólpassz-tengelye a(z) "
                     f"{top_arp['from']} → {top_arp['to']} vonal: a "
                     f"poszthoz kötött gólpasszos góljaik "
                     f"{top_arp['share_pct']:.0f}%-a innen jött "
                     f"({top_arp['goals']}/{rec_arp['pairs_total']}) — "
                     "ezt az egy vonalat kell elvágni, nem két embert "
                     "külön fogni.")
    except Exception:
        pass
    # Poszt-hatékonyság: melyik posztról érdemes engedni a lövést.
    try:
        from .roles import SER_GAP_PP, shot_efficiency_by_role
        ser = shot_efficiency_by_role(match)
        for side, name in (("home", home), ("away", away)):
            rec_ser = ser[side]
            worst = rec_ser.get("worst")
            if worst is None:
                continue
            body += (f" A(z) {name} befejezésében a(z) {worst['poszt']} "
                     f"a leggyengébb: {worst['pct']:.0f}% "
                     f"({worst['goals']}/{worst['shots']} lövés), a "
                     f"csapat-átlaguk {rec_ser['team_pct']:.0f}% — "
                     f"{abs(worst['gap_pp']):.0f} százalékpont a "
                     f"különbség ({SER_GAP_PP:.0f} fölött érdemi).")
    except Exception:
        pass
    # Kiosztás-célpont: kihez megy a labda a betörés után.
    try:
        from .attack_types import KOT_CONCENTRATION_PCT, kickout_targets
        kot = kickout_targets(match)
        for side, name in (("home", home), ("away", away)):
            rec_kot = kot[side]
            if rec_kot["verdict"] is None:
                continue
            who = rec_kot["top"]
            label = (f"{who['jersey']} mezszámú" if who.get("jersey")
                     is not None else f"{who['player_id']} azonosítójú")
            body += (f" A(z) {name} betörés utáni kiosztása: "
                     f"{rec_kot['verdict']} — a labda "
                     f"{rec_kot['top_pct']:.0f}%-ban a(z) {label} "
                     f"játékoshoz megy ({who['count']}/"
                     f"{rec_kot['kickouts']} kiosztás; "
                     f"{KOT_CONCENTRATION_PCT:.0f}% fölött "
                     "kiszámítható).")
    except Exception:
        pass
    # Teendő-rangsor: mivel foglalkozzon a jövő héten.
    try:
        from .priorities import priority_findings
        prf = priority_findings(match)
        for side, name in (("home", home), ("away", away)):
            rec_prf = prf[side]
            if not rec_prf["top"]:
                continue
            first = rec_prf["top"][0]
            body += (f" A(z) {name} jövő heti fő fókusza a rangsor "
                     f"tetejéről: {first['label']} — "
                     f"{first['verdict']} (összesen "
                     f"{rec_prf['total']} megszólaló jelzés).")
    except Exception:
        pass
    # Befejező-váltás: ugyanaz fejez-e be sorozatban.
    try:
        from .xg import finisher_rotation
        frt = finisher_rotation(match)
        for side, name in (("home", home), ("away", away)):
            rec_frt = frt[side]
            if rec_frt["verdict"] is None:
                continue
            body += (f" A(z) {name} befejezés-sorrendje: "
                     f"{rec_frt['verdict']} "
                     f"({rec_frt['repeat_pct']:.0f}% ismétlés "
                     f"{rec_frt['shots']} lövésből).")
    except Exception:
        pass
    # Gól-minta: ugyanazt a gólt lövik-e.
    try:
        from .xg import goal_patterns
        gpt = goal_patterns(match)
        for side, name in (("home", home), ("away", away)):
            rec_gpt = gpt[side]
            if rec_gpt["verdict"] is None:
                continue
            body += (f" A(z) {name} góljai egy képre járnak: "
                     f"{rec_gpt['verdict']} — egy fal-igazítás a "
                     "gólforrásuk nagyját elzárja.")
    except Exception:
        pass
    # Kettős emberhátrány: mit kezdenek négy mezőnyjátékossal.
    try:
        from .rules import double_shorthand
        dsh = double_shorthand(match)
        for side, name in (("home", home), ("away", away)):
            rec_dsh = dsh[side]
            if rec_dsh["verdict"] is None:
                continue
            body += (f" A(z) {name} kettős emberhátrányban is "
                     f"vizsgázott: {rec_dsh['verdict']} "
                     f"({rec_dsh['seconds']:.0f} mp négy "
                     f"mezőnyjátékossal, {rec_dsh['conceded']} "
                     "kapott gól).")
    except Exception:
        pass
    # Létszám-hiba: csere-átfedésben hetedik ember a pályán.
    try:
        from .rules import excess_players
        xsp = excess_players(match)
        for side, name in (("home", home), ("away", away)):
            rec_xsp = xsp[side]
            if rec_xsp["verdict"] is None:
                continue
            body += (f" A(z) {name} cseréi átfednek: "
                     f"{rec_xsp['windows']} ablakban volt hetedik "
                     "mezőnyjátékosuk a pályán — ez ingyen "
                     "kiállítást érhet.")
    except Exception:
        pass
    # Felzárkózás-húzó: kin keresztül jönnek vissza hátrányból.
    try:
        from .momentum import comeback_carriers
        cbc = comeback_carriers(match)
        for side, name in (("home", home), ("away", away)):
            rec_cbc = cbc[side]
            if rec_cbc["verdict"] is None:
                continue
            body += (f" A(z) {name} mentőembere is megvan: "
                     f"{rec_cbc['verdict']} — bajban rajta keresztül "
                     "játszanak.")
    except Exception:
        pass
    # Eltűnő védő: kinek a zónája nyílik ki a hajrára.
    try:
        from .defense import fading_defenders
        fdd = fading_defenders(match)
        for side, name in (("home", home), ("away", away)):
            rec_fdd = fdd[side]
            if rec_fdd["verdict"] is None:
                continue
            body += (f" A(z) {name} védekezéséről kiderült: "
                     f"{rec_fdd['verdict']} — a hajrában az ő zónája "
                     "nyílik ki.")
    except Exception:
        pass
    # Sprint-állás: hátrányban sprintbe menekülés.
    try:
        from .stats import sprints_by_score
        spb = sprints_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_spb = spb[side]
            if rec_spb["verdict"] is None:
                continue
            body += (f" A(z) {name} futás-képe árulkodó: "
                     f"{rec_spb['verdict']} "
                     f"({rec_spb['trailing']['sprints']} sprint "
                     "hátrányban) — ez a hajrára elfogyó láb "
                     "leggyorsabb útja.")
    except Exception:
        pass
    # Eltűnő ember: aki az első félidőben él, a másodikra elhal.
    try:
        from .momentum import fading_scorers
        fdr = fading_scorers(match)
        for side, name in (("home", home), ("away", away)):
            rec_fdr = fdr[side]
            if rec_fdr["verdict"] is None:
                continue
            body += (f" A(z) {name} kulcsemberéről kiderült: "
                     f"{rec_fdr['verdict']} — az ellenfélnek az első "
                     "30 perc a meccs ellene.")
    except Exception:
        pass
    # Fekete ötperc: melyik öt perc süllyed el.
    try:
        from .momentum import black_window
        blw = black_window(match)
        for side, name in (("home", home), ("away", away)):
            rec_blw = blw[side]
            if rec_blw["verdict"] is None:
                continue
            body += (f" A(z) {name} meccsének volt egy fekete lyuka: "
                     f"{rec_blw['verdict']} — ide tervezett "
                     "csere-blokk és időkérés-készenlét kell.")
    except Exception:
        pass
    # Oldal-váltás a szünetre: másik szárnyra kerül-e a súlypont.
    try:
        from .tactics import attack_side_shift
        sds = attack_side_shift(match)
        for side, name in (("home", home), ("away", away)):
            rec_sds = sds[side]
            if rec_sds["verdict"] is None:
                continue
            body += (f" A(z) {name} szárny-játékáról kiderült: "
                     f"{rec_sds['verdict']} — a fal súlypontját a "
                     "szünet után át kell tenni.")
    except Exception:
        pass
    # Fal-váltás a szünetre: más falat hoznak-e a 2. félidőre.
    try:
        from .tactics import defense_form_shift
        dfs = defense_form_shift(match)
        for side, name in (("home", home), ("away", away)):
            rec_dfs = dfs[side]
            if rec_dfs["verdict"] is None \
                    or "falat váltanak" not in rec_dfs["verdict"]:
                continue
            body += (f" A(z) {name} védekezéséről kiderült: "
                     f"{rec_dfs['verdict']} — ellene a támadó-tervet "
                     "is váltani kell a szünetben.")
    except Exception:
        pass
    # Passz-hossz-állás: mikor váltanak hosszú labdákra.
    try:
        from .event_detection import pass_length_by_score
        pls = pass_length_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_pls = pls[side]
            if rec_pls["verdict"] is None:
                continue
            body += (f" A(z) {name} passz-képe az állást követi: "
                     f"{rec_pls['verdict']} "
                     f"({rec_pls['trailing']['long']} hosszú passz "
                     f"{rec_pls['trailing']['passes']} hátrányban "
                     "adottból) — ezek a labdák elfoghatók.")
    except Exception:
        pass
    # Kapus-gólpassz: a kapus keze gólt indít.
    try:
        from .goalkeeper import gk_assists
        gka = gk_assists(match)
        for side, name in (("home", home), ("away", away)):
            rec_gka = gka[side]
            if rec_gka["verdict"] is None:
                continue
            body += (f" A(z) {name} leggyorsabb fegyvere a kapus keze: "
                     f"{rec_gka['assists']} gólpasszt ért az indítása — "
                     "az ellenfélnek a lövés pillanatában kell "
                     "hátraindulnia.")
    except Exception:
        pass
    # Passz-irány-állás: merre jár a labda az állás szerint.
    try:
        from .attack_types import pass_direction_by_score
        pds = pass_direction_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_pds = pds[side]
            if rec_pds["verdict"] is None:
                continue
            body += (f" A(z) {name} labdajáratása az állást követi: "
                     f"{rec_pds['verdict']}.")
    except Exception:
        pass
    # Szünet-váltás: átrendezik-e a támadójátékot a szünet után.
    try:
        from .attack_types import attack_mix_shift
        ams = attack_mix_shift(match)
        for side, name in (("home", home), ("away", away)):
            rec_ams = ams[side]
            if rec_ams["verdict"] is None:
                continue
            body += (f" A(z) {name} szünet-képe: {rec_ams['verdict']} "
                     f"(a támadás-mix {rec_ams['shift_pp']:.0f} "
                     "százalékpontot rendeződött át).")
    except Exception:
        pass
    # Lepattanó-esés: melyik félidőben él a második roham.
    try:
        from .attack_types import second_chance_fade
        scf = second_chance_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_scf = scf[side]
            if rec_scf["verdict"] is None:
                continue
            body += (f" A(z) {name} lepattanó-képe: "
                     f"{rec_scf['verdict']} (visszaharcolt lepattanó "
                     f"{rec_scf['fh_won']}/{rec_scf['fh_misses']} → "
                     f"{rec_scf['sh_won']}/{rec_scf['sh_misses']}).")
    except Exception:
        pass
    # Gólpassz-esés: megáll-e a labda a hajrára.
    try:
        from .attack_types import assist_fade
        asf = assist_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_asf = asf[side]
            if rec_asf["verdict"] is None:
                continue
            body += (f" A(z) {name} előkészítés-képe: "
                     f"{rec_asf['verdict']} (gólpasszos gól az 1. "
                     f"félidőben {rec_asf['fh_assisted']}/"
                     f"{rec_asf['fh_goals']}, a másodikban "
                     f"{rec_asf['sh_assisted']}/{rec_asf['sh_goals']}).")
    except Exception:
        pass
    # Kapus-sorozat: rákapó, sorozatban védő kapus.
    try:
        from .goalkeeper import gk_save_streaks
        gst = gk_save_streaks(match)
        for side, name in (("home", home), ("away", away)):
            rec_gst = gst[side]
            if rec_gst["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusáról kiderült: "
                     f"{rec_gst['verdict']} ({rec_gst['streaks']} "
                     f"hármas védés-sorozat, a leghosszabb "
                     f"{rec_gst['longest']}) — ellene a lövés-képet "
                     "kell váltani, nem a lövőt.")
    except Exception:
        pass
    # 7a6-állás: mikor vállalják az üres kaput.
    try:
        from .goalkeeper import empty_net_by_score
        ens = empty_net_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_ens = ens[side]
            if rec_ens["verdict"] is None:
                continue
            _ens_n = (rec_ens["trailing"] + rec_ens["leading"]
                      + rec_ens["level"])
            body += (f" A(z) {name} 7a6-szokása kirajzolódott: "
                     f"{rec_ens['verdict']} ({_ens_n} üres-kapus "
                     f"szakaszból {rec_ens['trailing']} jött "
                     "hátrányban).")
    except Exception:
        pass
    # Kontra-állás: mikor futják a lerohanásaikat.
    try:
        from .attack_types import breaks_by_score
        bks = breaks_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_bks = bks[side]
            if rec_bks["verdict"] is None:
                continue
            body += (f" A(z) {name} kontra-képe az állást követi: "
                     f"{rec_bks['verdict']} "
                     f"({rec_bks['trailing']['breaks']} lerohanás "
                     f"hátrányban, {rec_bks['leading']['breaks']} "
                     "vezetésnél).")
    except Exception:
        pass
    # Hetes-állás: mikor harcolják ki a heteseket.
    try:
        from .rules import sevens_by_score
        svs = sevens_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_svs = svs[side]
            if rec_svs["verdict"] is None:
                continue
            _svs_n = (rec_svs["trailing"] + rec_svs["leading"]
                      + rec_svs["level"])
            body += (f" A(z) {name} hetes-képe árulkodó: "
                     f"{rec_svs['verdict']} ({rec_svs['trailing']}/"
                     f"{_svs_n}) — hátrányban a betörés és a kontakt "
                     "a menekülő-fegyverük.")
    except Exception:
        pass
    # Fegyelem-állás: mikor jönnek a kiállítások az állás szerint.
    try:
        from .rules import suspensions_by_score
        sps = suspensions_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_sps = sps[side]
            if rec_sps["verdict"] is None:
                continue
            _sps_n = (rec_sps["trailing"] + rec_sps["leading"]
                      + rec_sps["level"])
            body += (f" A(z) {name} fegyelem-képe az állást követi: "
                     f"{rec_sps['verdict']} ({rec_sps['trailing']}/"
                     f"{_sps_n} kiállításuk hátrányban jött).")
    except Exception:
        pass
    # Kidobott labda: oldalvonalon elajándékozott labdák.
    try:
        from .attack_types import balls_out
        obt = balls_out(match)
        for side, name in (("home", home), ("away", away)):
            rec_obt = obt[side]
            if rec_obt["verdict"] is None:
                continue
            body += (f" A(z) {name} olcsón adott el: {rec_obt['out']} "
                     "labdát dobtak ki az oldalvonalon — ehhez ellenfél "
                     "sem kellett.")
    except Exception:
        pass
    # Elhúzódó támadás ára: megéri-e a hosszú akció.
    try:
        from .tactics import slow_attack_cost
        sac = slow_attack_cost(match)
        for side, name in (("home", home), ("away", away)):
            rec_sac = sac[side]
            if rec_sac["verdict"] is None:
                continue
            body += (f" A(z) {name} hosszú akcióiról kiderült: "
                     f"{rec_sac['verdict']} ({rec_sac['scored']}/"
                     f"{rec_sac['slow']} elhúzódó támadás ért gólt).")
    except Exception:
        pass
    # Indítás-hiba ára: gólba kerülnek-e az elszórt indítások.
    try:
        from .goalkeeper import outlet_punishment
        olp = outlet_punishment(match)
        for side, name in (("home", home), ("away", away)):
            rec_olp = olp[side]
            if rec_olp["verdict"] is None:
                continue
            body += (f" A(z) {name} kihozataláról kiderült: "
                     f"{rec_olp['verdict']} ({rec_olp['punished']}/"
                     f"{rec_olp['lost']} elveszett indítást követett"
                     " gyors ellenfél-gól).")
    except Exception:
        pass
    # Kihagyás-büntetés: megbüntetik-e a kihagyott ziccereiket.
    try:
        from .momentum import punished_misses
        pmb = punished_misses(match)
        for side, name in (("home", home), ("away", away)):
            rec_pmb = pmb[side]
            if rec_pmb["verdict"] is None:
                continue
            body += (f" A(z) {name} kihagyásairól kiderült: "
                     f"{rec_pmb['verdict']} ({rec_pmb['punished']}/"
                     f"{rec_pmb['misses']} kihagyott ziccert követett"
                     " fél percen belüli ellenfél-gól).")
    except Exception:
        pass
    # Kilépés-büntetés: a kilépésük mögé betalálnak-e.
    try:
        from .defense import stepout_punishment
        sop = stepout_punishment(match)
        for side, name in (("home", home), ("away", away)):
            rec_sop = sop[side]
            if rec_sop["verdict"] is None:
                continue
            body += (f" A(z) {name} kilépéseiről kiderült: "
                     f"{rec_sop['verdict']} "
                     f"({rec_sop['behind_stepout']}/{rec_sop['goals']}"
                     " kapott gólnál volt kiugró védő a sorban).")
    except Exception:
        pass
    # Kettőzés-büntetés: mögé betalálnak-e a kettőzésnek.
    try:
        from .defense import double_punishment
        dbp = double_punishment(match)
        for side, name in (("home", home), ("away", away)):
            rec_dbp = dbp[side]
            if rec_dbp["verdict"] is None:
                continue
            body += (f" A(z) {name} kettőzéséről kiderült: "
                     f"{rec_dbp['verdict']} ({rec_dbp['conceded_after']}"
                     " gól esett közvetlenül kettőzés után).")
    except Exception:
        pass
    # Olvasó kapus: előre olvassa-e a lövéseket a kapus.
    try:
        from .goalkeeper import reading_keeper
        rdk = reading_keeper(match)
        for side, name in (("home", home), ("away", away)):
            rec_rdk = rdk[side]
            if rec_rdk["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusáról kiderült: "
                     f"{rec_rdk['verdict']} ({rec_rdk['read']}/"
                     f"{rec_rdk['saves']} védésnél indult előre a "
                     "labda oldalára).")
    except Exception:
        pass
    # Becsapott kapus: elmozdítják-e a kapust a gólok előtt.
    try:
        from .goalkeeper import wrongfooted_keeper
        wfk = wrongfooted_keeper(match)
        for side, name in (("home", home), ("away", away)):
            rec_wfk = wfk[side]
            if rec_wfk["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusáról kiderült: "
                     f"{rec_wfk['verdict']} ({rec_wfk['fooled']}/"
                     f"{rec_wfk['goals']} kapott gólnál mozdult "
                     "ellenirányba).")
    except Exception:
        pass
    # Lendület-gólok: mozgásból érkező lövőktől kapják-e a gólokat.
    try:
        from .defense import conceded_momentum
        cgm = conceded_momentum(match)
        for side, name in (("home", home), ("away", away)):
            rec_cgm = cgm[side]
            if rec_cgm["verdict"] is None:
                continue
            body += (f" A(z) {name} kapott góljairól kiderült: "
                     f"{rec_cgm['verdict']} ({rec_cgm['running']}/"
                     f"{rec_cgm['goals']} gólnál lendületből "
                     "érkezett a lövő).")
    except Exception:
        pass
    # Bontó tempó: a járatás szedi-e szét a védekezésüket.
    try:
        from .defense import conceded_tempo
        ctm = conceded_tempo(match)
        for side, name in (("home", home), ("away", away)):
            rec_ctm = ctm[side]
            if rec_ctm["verdict"] is None:
                continue
            body += (f" A(z) {name} védekezéséről kiderült: "
                     f"{rec_ctm['verdict']} (a kapott gólok előtt "
                     f"átlag {rec_ctm['avg_passes']:.1f} passz ment "
                     "8 másodpercen belül).")
    except Exception:
        pass
    # Folyosó-gólok: nyitott folyosón kapják-e a gólokat.
    try:
        from .defense import corridor_goals
        crg = corridor_goals(match)
        for side, name in (("home", home), ("away", away)):
            rec_crg = crg[side]
            if rec_crg["verdict"] is None:
                continue
            body += (f" A(z) {name} kapott góljairól kiderült: "
                     f"{rec_crg['verdict']} ({rec_crg['open']}/"
                     f"{rec_crg['goals']} gól előtt nem állt senki "
                     "a lövésvonalban).")
    except Exception:
        pass
    # Csere-büntetés: gólba kerülnek-e a csere-lyukak.
    try:
        from .substitutions import gap_punishment
        gpn = gap_punishment(match)
        for side, name in (("home", home), ("away", away)):
            rec_gpn = gpn[side]
            if rec_gpn["verdict"] is None:
                continue
            body += (f" A(z) {name} cseréiről kiderült: "
                     f"{rec_gpn['verdict']} ({rec_gpn['conceded']} "
                     f"kapott gól {rec_gpn['gap_s']:.0f} mp öt fős "
                     "játék alatt).")
    except Exception:
        pass
    # Zavartalan előkészítők: hagyják-e dolgozni a gólpassz-adót.
    try:
        from .defense import unpressured_assists
        upa = unpressured_assists(match)
        for side, name in (("home", home), ("away", away)):
            rec_upa = upa[side]
            if rec_upa["verdict"] is None:
                continue
            body += (f" A(z) {name} védekezéséről kiderült: "
                     f"{rec_upa['verdict']} "
                     f"({rec_upa['unpressured']}/{rec_upa['assisted']}"
                     " gólpassz jött zavartalan kiadásból).")
    except Exception:
        pass
    # Átvert védők: ki mögött esnek a kapott gólok.
    try:
        from .defense import beaten_defenders
        btn = beaten_defenders(match)
        for side, name in (("home", home), ("away", away)):
            top_btn = btn[side]["top"]
            if top_btn is None:
                continue
            mez_btn = (f"{top_btn['jersey']} mezszámú"
                       if top_btn["jersey"] is not None
                       else f"{top_btn['player_id']} azonosítójú")
            body += (f" A(z) {name} kapott góljainál rendre a(z) "
                     f"{mez_btn} védő veszítette a párharcot "
                     f"({top_btn['beaten']}/{btn[side]['goals']}).")
    except Exception:
        pass
    # Kettőző emberek: ki jön másodiknak a labdásra.
    try:
        from .defense import doubling_defenders
        dtp = doubling_defenders(match)
        for side, name in (("home", home), ("away", away)):
            top_dtp = dtp[side]["top"]
            if top_dtp is None:
                continue
            mez_dtp = (f"{top_dtp['jersey']} mezszámú"
                       if top_dtp["jersey"] is not None
                       else f"{top_dtp['player_id']} azonosítójú")
            body += (f" A(z) {name} kettőzése kiszámítható: a "
                     f"kettőzött kockák {top_dtp['share_pct']:.0f}"
                     f"%-ában a(z) {mez_dtp} játékos a második "
                     "ember.")
    except Exception:
        pass
    # Szélső-mélység: milyen mélyről lőnek a szélsők.
    try:
        from .attack_types import wing_shot_depth
        wsd = wing_shot_depth(match)
        for side, name in (("home", home), ("away", away)):
            rec_wsd = wsd[side]
            if rec_wsd["verdict"] is None:
                continue
            body += (f" A(z) {name} szélső-játékáról kiderült: "
                     f"{rec_wsd['verdict']} (átlag "
                     f"{rec_wsd['avg_m']:.1f} m-ről eresztik el).")
    except Exception:
        pass
    # Kontra-esés: melyik félidőben kontráznak.
    try:
        from .attack_types import break_share_fade
        brf = break_share_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_brf = brf[side]
            if rec_brf["verdict"] is None:
                continue
            body += (f" A(z) {name} kontra-játékáról kiderült: "
                     f"{rec_brf['verdict']} "
                     f"({rec_brf['fh_breaks']}/{rec_brf['fh_attacks']}"
                     f" lerohanás az elsőben, "
                     f"{rec_brf['sh_breaks']}/{rec_brf['sh_attacks']}"
                     " a másodikban).")
    except Exception:
        pass
    # Felhozatal-posztok: melyik posztra hozzák fel a labdát.
    try:
        from .goalkeeper import outlet_target_roles
        otr = outlet_target_roles(match)
        for side, name in (("home", home), ("away", away)):
            top_otr = otr[side]["top"]
            if top_otr is None:
                continue
            body += (f" A(z) {name} felhozatala jellemzően a(z) "
                     f"{top_otr['poszt']} posztra épül "
                     f"({top_otr['count']}/{otr[side]['outlets']} "
                     "indítás-célpont).")
    except Exception:
        pass
    # Falba lövő posztok: melyik poszt lő rendre a falba.
    try:
        from .defense import blocked_by_role
        bbr = blocked_by_role(match)
        for side, name in (("home", home), ("away", away)):
            top_bbr = bbr[side]["top"]
            if top_bbr is None:
                continue
            body += (f" A(z) {name} falba lőtt lövései jellemzően "
                     f"a(z) {top_bbr['poszt']} posztról jönnek "
                     f"({top_bbr['blocked']}/{bbr[side]['blocked']} "
                     "lefogott lövés).")
    except Exception:
        pass
    # Kiállítás-posztok: melyik poszt hozza a kétperceseket.
    try:
        from .rules import susp_earner_roles
        sur = susp_earner_roles(match)
        for side, name in (("home", home), ("away", away)):
            top_sur = sur[side]["top"]
            if top_sur is None:
                continue
            body += (f" A(z) {name} a kétperceseket jellemzően a(z) "
                     f"{top_sur['poszt']} posztról hozza "
                     f"({top_sur['count']}/{sur[side]['suspensions']} "
                     "kiharcolt kiállítás).")
    except Exception:
        pass
    # Gólpassz-posztok: melyik poszt készíti elő a gólokat.
    try:
        from .roles import assists_by_role
        abr = assists_by_role(match)
        for side, name in (("home", home), ("away", away)):
            top_abr = abr[side]["top"]
            if top_abr is None:
                continue
            body += (f" A(z) {name} góljait jellemzően a(z) "
                     f"{top_abr['poszt']} posztról készítik elő "
                     f"({top_abr['assists']}/{abr[side]['assists']} "
                     "gólpassz).")
    except Exception:
        pass
    # Lefogott lövők: kinek a lövését viszi el rendre a fal.
    try:
        from .defense import blocked_shooters
        bsh = blocked_shooters(match)
        for side, name in (("home", home), ("away", away)):
            top_bsh = bsh[side]["top"]
            if top_bsh is None:
                continue
            mez_bsh = (f"{top_bsh['jersey']} mezszámú"
                       if top_bsh["jersey"] is not None
                       else f"{top_bsh['player_id']} azonosítójú")
            body += (f" A(z) {name} lövéseit rendre a fal vitte el: "
                     f"a lefogott lövések {top_bsh['share_pct']:.0f}"
                     f"%-a a(z) {mez_bsh} játékosé "
                     f"({top_bsh['blocked']}/{bsh[side]['blocked']}).")
    except Exception:
        pass
    # Kontra-elszökés: előre szökött emberrel vagy együtt kontráznak.
    try:
        from .attack_types import fast_break_headstart
        fbh = fast_break_headstart(match)
        for side, name in (("home", home), ("away", away)):
            rec_fbh = fbh[side]
            if rec_fbh["verdict"] is None:
                continue
            body += (f" A(z) {name} kontra-felfutásáról kiderült: "
                     f"{rec_fbh['verdict']} "
                     f"({rec_fbh['ahead']}/{rec_fbh['breaks']} "
                     "lerohanás indult elszökött emberrel).")
    except Exception:
        pass
    # Kontra-hullámok: az első ember vagy a befutó fejezi be.
    try:
        from .attack_types import fast_break_waves
        fbw = fast_break_waves(match)
        for side, name in (("home", home), ("away", away)):
            rec_fbw = fbw[side]
            if rec_fbw["verdict"] is None:
                continue
            body += (f" A(z) {name} kontráiról kiderült: "
                     f"{rec_fbw['verdict']} "
                     f"({rec_fbw['second']}/{rec_fbw['breaks']} "
                     "lerohanás zárult a befutó lövésével).")
    except Exception:
        pass
    # Beálló-futtatás: mozgásból vagy állva kapja-e a beálló.
    try:
        from .attack_types import pivot_service
        psv = pivot_service(match)
        for side, name in (("home", home), ("away", away)):
            rec_psv = psv[side]
            if rec_psv["verdict"] is None:
                continue
            body += (f" A(z) {name} beállójáról kiderült: "
                     f"{rec_psv['verdict']} "
                     f"({rec_psv['running']}/{rec_psv['receptions']} "
                     "átvétel mozgásból).")
    except Exception:
        pass
    # Keresztjáték: mennyit kereszteznek a hátsó sorban.
    try:
        from .attack_types import crossing_runs
        crx = crossing_runs(match)
        for side, name in (("home", home), ("away", away)):
            rec_crx = crx[side]
            if rec_crx["verdict"] is None:
                continue
            body += (f" A(z) {name} hátsó soráról kiderült: "
                     f"{rec_crx['verdict']} (támadásonként átlag "
                     f"{rec_crx['per_attack']:.1f} keresztezés).")
    except Exception:
        pass
    # Szélső-futtatás: lendületből vagy állva kapják-e a szélsők.
    try:
        from .attack_types import wing_service
        wsv = wing_service(match)
        for side, name in (("home", home), ("away", away)):
            rec_wsv = wsv[side]
            if rec_wsv["verdict"] is None:
                continue
            body += (f" A(z) {name} széljátékáról kiderült: "
                     f"{rec_wsv['verdict']} "
                     f"({rec_wsv['running']}/{rec_wsv['receptions']} "
                     "átvétel jött mozgásból).")
    except Exception:
        pass
    # Csere-lyukak: mennyi ideig játszanak öten csere közben.
    try:
        from .substitutions import sub_gaps
        sbg = sub_gaps(match)
        for side, name in (("home", home), ("away", away)):
            rec_sbg = sbg[side]
            if rec_sbg["verdict"] != "lyukas a cseréjük":
                continue
            body += (f" A(z) {name} cseréi lyukasak voltak: összesen "
                     f"{rec_sbg['gap_s']:.0f} másodpercig játszottak "
                     "öt mezőnyjátékossal csere közben.")
    except Exception:
        pass
    # Gólpassz-hossz: hosszú indításokból vagy rövid kombinációkból.
    try:
        from .event_detection import assist_ranges
        asr = assist_ranges(match)
        for side, name in (("home", home), ("away", away)):
            rec_asr = asr[side]
            if rec_asr["verdict"] is None:
                continue
            body += (f" A(z) {name} góljairól kiderült: "
                     f"{rec_asr['verdict']} "
                     f"({rec_asr['long']}/{rec_asr['assisted']} "
                     "gólpassz jött 8 méteren túlról).")
    except Exception:
        pass
    # Kapus-kipattanó: fogja vagy kiüti a labdát.
    try:
        from .goalkeeper import gk_rebound_control
        grc = gk_rebound_control(match)
        for side, name in (("home", home), ("away", away)):
            rec_grc = grc[side]
            if rec_grc["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusáról kiderült: "
                     f"{rec_grc['verdict'].replace(' a kapusuk', '')} "
                     f"({rec_grc['caught']}/{rec_grc['saves']} védés "
                     "maradt nála).")
    except Exception:
        pass
    # Kivárás-csapda: mi lesz a hosszú támadásaikból.
    try:
        from .attack_types import long_attack_outcomes
        lao = long_attack_outcomes(match)
        for side, name in (("home", home), ("away", away)):
            rec_lao = lao[side]
            if rec_lao["verdict"] is None:
                continue
            body += (f" A(z) {name} hosszú támadásairól kiderült: "
                     f"{rec_lao['verdict']} "
                     f"({rec_lao['died']}/{rec_lao['long_attacks']} "
                     "halt el lövés nélkül).")
    except Exception:
        pass
    # Felfutási létszám: hány emberrel támadnak.
    try:
        from .attack_types import attack_headcount
        ahc = attack_headcount(match)
        for side, name in (("home", home), ("away", away)):
            rec_ahc = ahc[side]
            if rec_ahc["verdict"] is None:
                continue
            body += (f" A(z) {name} támadásaiban {rec_ahc['verdict']}"
                     f": átlag {rec_ahc['avg_up']:.1f} mezőnyjátékos "
                     "volt fent a támadó térfélen.")
    except Exception:
        pass
    # Blokk-lepattanó: a blokk után ki szerzi meg a labdát.
    try:
        from .defense import block_recoveries
        brc = block_recoveries(match)
        for side, name in (("home", home), ("away", away)):
            rec_brc = brc[side]
            if rec_brc["verdict"] is None:
                continue
            body += (f" A(z) {name} blokkjairól kiderült: "
                     f"{rec_brc['verdict']} "
                     f"({rec_brc['recovered']}/{rec_brc['blocks']} "
                     "lepattanó lett az övék).")
    except Exception:
        pass
    # Ziccer-befejezők: ki értékesíti a nagy helyzeteket.
    try:
        from .xg import big_chance_finishers
        bcf = big_chance_finishers(match)
        for side, name in (("home", home), ("away", away)):
            rec_bcf = bcf[side]
            if rec_bcf["safe"] is not None:
                sf = rec_bcf["safe"]
                body += (f" A(z) {name} ziccer-biztos befejezője a(z) "
                         f"{sf['player_id']} azonosítójú "
                         f"({sf['goals']}/{sf['chances']} nagy "
                         "helyzet).")
            if rec_bcf["shaky"] is not None:
                sk = rec_bcf["shaky"]
                body += (f" A(z) {name} nagy helyzeteit a(z) "
                         f"{sk['player_id']} azonosítójú rendre "
                         f"kihagyta ({sk['goals']}/{sk['chances']}).")
    except Exception:
        pass
    # Hetes utáni percek: leragadnak-e az adott hetes után.
    try:
        from .rules import post_seven_lapses
        psl = post_seven_lapses(match)
        for side, name in (("home", home), ("away", away)):
            rec_psl = psl[side]
            if rec_psl["verdict"] is None:
                continue
            body += (f" A(z) {name} a hetes utáni percben is kapott "
                     f"rá: {rec_psl['sevens_against']} adott hetesük "
                     f"után {rec_psl['extra_conceded']} további gól "
                     "esett.")
    except Exception:
        pass
    # Labda-forgatás iránya: merre járatják a labdát.
    try:
        from .attack_types import circulation_direction
        cir = circulation_direction(match)
        for side, name in (("home", home), ("away", away)):
            rec_cir = cir[side]
            if rec_cir["verdict"] is None:
                continue
            body += (f" A(z) {name} támadásban {rec_cir['verdict']}: "
                     f"{rec_cir['left']} balra és {rec_cir['right']} "
                     "jobbra tartó oldalpassz.")
    except Exception:
        pass
    # Elzárás-páros: ki zár kinek.
    try:
        from .attack_types import screen_pairs
        scp = screen_pairs(match)
        for side, name in (("home", home), ("away", away)):
            top_scp = scp[side]["top"]
            if top_scp is None:
                continue
            body += (f" A(z) {name} bejáratott elzárás-párosa: a(z) "
                     f"{top_scp['setter_id']} azonosítójú zárt a(z) "
                     f"{top_scp['shooter_id']} azonosítójúnak "
                     f"({top_scp['shots']} közös lövés).")
    except Exception:
        pass
    # Szélső-kifutás: időben érnek-e ki a szélső lövéseire.
    try:
        from .defense import wing_closeouts
        wco = wing_closeouts(match)
        for side, name in (("home", home), ("away", away)):
            rec_wco = wco[side]
            if rec_wco["verdict"] is None:
                continue
            body += (f" A(z) {name} védekezéséről kiderült: "
                     f"{rec_wco['verdict']} (átlag "
                     f"{rec_wco['avg_m']:.1f} m-re volt a legközelebbi "
                     "védő a lövő szélsőtől).")
    except Exception:
        pass
    # Csend-törők: ki dobja a gólcsendet megtörő gólt.
    try:
        from .momentum import drought_breakers
        drb = drought_breakers(match)
        for side, name in (("home", home), ("away", away)):
            top_drb = drb[side]["top"]
            if top_drb is None:
                continue
            body += (f" A(z) {name} válság-lövője a(z) "
                     f"{top_drb['player_id']} azonosítójú volt: "
                     f"{top_drb['breaks']} gólcsendet tört meg.")
    except Exception:
        pass
    # Forró kéz: van-e sorozatlövőjük.
    try:
        from .momentum import hot_hands
        hh = hot_hands(match)
        for side, name in (("home", home), ("away", away)):
            top_hh = hh[side]["top"]
            if top_hh is None:
                continue
            body += (f" A(z) {name} sorozatlövője a(z) "
                     f"{top_hh['player_id']} azonosítójú volt: "
                     f"{top_hh['streaks']} gólsorozat, a leghosszabb "
                     f"{top_hh['longest']} egymás utáni gól.")
    except Exception:
        pass
    # Kapus-hidegedés: hideg kézzel beesik-e a védése.
    try:
        from .goalkeeper import gk_cold_streaks
        gcs = gk_cold_streaks(match)
        for side, name in (("home", home), ("away", away)):
            rec_gcs = gcs[side]
            if rec_gcs["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusáról kiderült: "
                     f"{rec_gcs['verdict'].replace(' a kapusuk', '')} "
                     f"(hosszú csend után {rec_gcs['cold']['save_pct']:.0f}%, "
                     f"ritmusban {rec_gcs['warm']['save_pct']:.0f}% a "
                     "védés-aránya).")
    except Exception:
        pass
    # Fal-magasság elleni játék: megbüntetik-e a felfutó falat.
    try:
        from .attack_types import attack_vs_wall_height
        avw = attack_vs_wall_height(match)
        for side, name in (("home", home), ("away", away)):
            rec_avw = avw[side]
            if rec_avw["verdict"] is None:
                continue
            body += (f" A(z) {name} ellen kiderült: "
                     f"{rec_avw['verdict']} (felfutó fal ellen "
                     f"{rec_avw['high']['goal_pct']:.0f}%, mély ellen "
                     f"{rec_avw['deep']['goal_pct']:.0f}% a "
                     "gólarányuk).")
    except Exception:
        pass
    # Kontra-forrás: miből indul a lerohanásuk.
    try:
        from .attack_types import break_sources
        bsrc = break_sources(match)
        for side, name in (("home", home), ("away", away)):
            top_bsrc = bsrc[side]["top"]
            if top_bsrc is None:
                continue
            body += (f" A(z) {name} kontráinak fő forrása a(z) "
                     f"{top_bsrc['source']} volt "
                     f"({top_bsrc['breaks']}/{bsrc[side]['breaks']} "
                     "lerohanás).")
    except Exception:
        pass
    # Kapus-gól veszély: rádob-e a kapusuk az üres kapura.
    try:
        from .goalkeeper import gk_goal_threat
        gkg = gk_goal_threat(match)
        for side, name in (("home", home), ("away", away)):
            rec_gkg = gkg[side]
            if rec_gkg["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusa gólveszélyes: "
                     f"{rec_gkg['attempts']} kapura dobásából "
                     f"{rec_gkg['goals']} gól lett.")
    except Exception:
        pass
    # Hosszú állás utáni játék: kizökkenti-e őket a megszakítás.
    try:
        from .stoppages import long_break_response
        lbr = long_break_response(match)
        for side, name in (("home", home), ("away", away)):
            rec_lbr = lbr[side]
            if rec_lbr["verdict"] is None:
                continue
            body += (f" A(z) {name} csapatát a hosszú megszakítások "
                     f"{'meglódítják' if 'meglódulnak' in rec_lbr['verdict'] else 'kizökkentik'}"
                     f": az állások utáni mérlegük "
                     f"{rec_lbr['goals_for']}-"
                     f"{rec_lbr['goals_against']}.")
    except Exception:
        pass
    # Hajrá-labdabirtoklás: egy kézben van-e a végjátékuk.
    try:
        from .momentum import clutch_ball_hogs
        cbh = clutch_ball_hogs(match)
        for side, name in (("home", home), ("away", away)):
            top_cbh = cbh[side]["top"]
            if top_cbh is None:
                continue
            body += (f" A(z) {name} végjátéka egy kézben volt: a "
                     f"hajrá labdás idejének nagy részét a(z) "
                     f"{top_cbh['player_id']} azonosítójú vitte "
                     f"({top_cbh['frames']}/{cbh[side]['frames']} "
                     "kocka).")
    except Exception:
        pass
    # Negyedóra-profil: melyik meccs-szakasz az övék.
    try:
        from .momentum import quarter_profile
        qp = quarter_profile(match)
        for side, name in (("home", home), ("away", away)):
            best_qp = qp[side]["best"]
            if best_qp is None:
                continue
            body += (f" A(z) {name} erős negyedórája a(z) "
                     f"{best_qp['quarter']}. volt "
                     f"(+{best_qp['diff']} a gólkülönbségük ott).")
    except Exception:
        pass
    # Beálló-őr: ki őrzi az ellenfél beállóját.
    try:
        from .defense import pivot_guards
        pvg = pivot_guards(match)
        for side, name in (("home", home), ("away", away)):
            top_pvg = pvg[side]["top"]
            if top_pvg is None:
                continue
            body += (f" A(z) {name} beálló-őrzése egy emberen áll: "
                     f"a(z) {top_pvg['player_id']} azonosítójú vitte "
                     f"az őrzés-idő nagy részét "
                     f"({top_pvg['frames']}/{pvg[side]['frames']} "
                     "kocka).")
    except Exception:
        pass
    # Időkérés-csomag: az időkérés cserével jár-e.
    try:
        from .stoppages import timeout_sub_combo
        tsc = timeout_sub_combo(match)
        for side, name in (("home", home), ("away", away)):
            rec_tsc = tsc[side]
            if rec_tsc["verdict"] is None:
                continue
            body += (f" A(z) {name} csapatánál {rec_tsc['verdict']} "
                     f"({rec_tsc['with_subs']}/{rec_tsc['timeouts']} "
                     "időkérés járt cserével).")
    except Exception:
        pass
    # Lövés-választás állás szerint: hátrányban elkapkodják-e.
    try:
        from .xg import shot_quality_by_score
        sqs = shot_quality_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_sqs = sqs[side]
            if rec_sqs["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_sqs['verdict']}: a lövéseik "
                     f"átlagos helyzet-értéke {rec_sqs['other_avg_xg']:.2f}"
                     f"-ról {rec_sqs['trail_avg_xg']:.2f}-ra változott "
                     "hátrányban.")
    except Exception:
        pass
    # Kapus állás szerint: hátrányban feljavul-e.
    try:
        from .goalkeeper import gk_saves_by_score
        gks = gk_saves_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_gks = gks[side]
            if rec_gks["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusa állás-érzékeny: "
                     f"{rec_gks['verdict'].replace(' a kapusuk', '')} "
                     f"(hátrányban {rec_gks['trail']['save_pct']:.0f}%, "
                     f"egyébként {rec_gks['other']['save_pct']:.0f}% a "
                     "védés-aránya).")
    except Exception:
        pass
    # Szorult játék: hátrányban mennyire húzzák szét a pályát.
    try:
        from .attack_types import width_by_score
        wbs = width_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_wbs = wbs[side]
            if rec_wbs["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_wbs['verdict']}: a támadásuk "
                     f"terjedelme {rec_wbs['other_avg_m']:.0f} m-ről "
                     f"{rec_wbs['trail_avg_m']:.0f} m-re változott "
                     "hátrányban.")
    except Exception:
        pass
    # Visszaállás: mi történik a kiállítás letelte után.
    try:
        from .rules import post_powerplay
        ppp = post_powerplay(match)
        for side, name in (("home", home), ("away", away)):
            rec_ppp = ppp[side]
            if rec_ppp["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_ppp['verdict']}: a "
                     "kiállítás letelte utáni perc mérlege "
                     f"{rec_ppp['goals_for']}-"
                     f"{rec_ppp['goals_against']}.")
    except Exception:
        pass
    # Poszt-hibák: melyik poszt veszíti el a labdát.
    try:
        from .roles import turnovers_by_role
        tbr = turnovers_by_role(match)
        for side, name in (("home", home), ("away", away)):
            top_tbr = tbr[side]["top"]
            if top_tbr is None:
                continue
            body += (f" A(z) {name} labdaeladásainak "
                     f"{top_tbr['share_pct']:.0f}%-a a(z) "
                     f"{top_tbr['poszt']} posztról jött "
                     f"({top_tbr['turnovers']} eladás).")
    except Exception:
        pass
    # Futás-mérleg: melyik csapat futja túl a másikat.
    try:
        from .stats import distance_battle
        dbt = distance_battle(match)
        for side, name in (("home", home), ("away", away)):
            rec_dbt = dbt[side]
            if rec_dbt["verdict"] != "túlfutják az ellenfelüket":
                continue
            body += (f" A(z) {name} túlfutotta az ellenfelét "
                     f"({rec_dbt['distance_m']:.0f} m a mezőny-"
                     "futásmennyiségük).")
    except Exception:
        pass
    # Egyirányú játékosok: váltott sorokkal játszanak-e.
    try:
        from .roles import phase_specialists
        phs = phase_specialists(match)
        for side, name in (("home", home), ("away", away)):
            rec_phs = phs[side]
            if rec_phs["verdict"] is None:
                continue
            d_ids = ", ".join(str(r["player_id"])
                              for r in rec_phs["def_specialists"][:2])
            a_ids = ", ".join(str(r["player_id"])
                              for r in rec_phs["atk_specialists"][:2])
            body += (f" A(z) {name} váltott sorokkal játszik: a(z) "
                     f"{d_ids} azonosítójú(ak) csak védekeznek, a(z) "
                     f"{a_ids} azonosítójú(ak) csak támadnak.")
    except Exception:
        pass
    # Sprint-veszély: ki viszi a kontrát.
    try:
        from .stats import sprint_threats
        spt = sprint_threats(match)
        for side, name in (("home", home), ("away", away)):
            top_spt = spt[side]["top"]
            if top_spt is None:
                continue
            body += (f" A(z) {name} kontráit a(z) "
                     f"{top_spt['player_id']} azonosítójú viszi: a "
                     f"csapat {spt[side]['team_sprints']} sprintjéből "
                     f"{top_spt['sprints']} az övé.")
    except Exception:
        pass
    # Hetesre cserélt kapus: hoznak-e specialistát a büntetőkre.
    try:
        from .goalkeeper import seven_keeper_swaps
        svk = seven_keeper_swaps(match)
        for side, name in (("home", home), ("away", away)):
            rec_svk = svk[side]
            if rec_svk["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_svk['verdict']}: az ellenük "
                     f"ítélt {rec_svk['sevens_against']} hetesből "
                     f"{rec_svk['swaps']}-t frissen beállt kapus "
                     "várt.")
    except Exception:
        pass
    # Kilépő védő: van-e előretolt ember a falban.
    try:
        from .defense import advanced_defender
        adv = advanced_defender(match)
        for side, name in (("home", home), ("away", away)):
            top_adv = adv[side]["top"]
            if top_adv is None:
                continue
            body += (f" A(z) {name} falában kilépő védő játszik: a(z) "
                     f"{top_adv['player_id']} azonosítójú átlag "
                     f"{top_adv['avg_depth_m']:.1f} m-en, "
                     f"{adv[side]['gap_m']:.1f} méterrel a társai "
                     "előtt.")
    except Exception:
        pass
    # Középkezdés-átvevő: kinél indul újra a játék a kapott gól után.
    try:
        from .momentum import restart_targets
        rst = restart_targets(match)
        for side, name in (("home", home), ("away", away)):
            top_rst = rst[side]["top"]
            if top_rst is None:
                continue
            body += (f" A(z) {name} középkezdése olvasható: a kapott "
                     f"gól után a(z) {top_rst['player_id']} "
                     f"azonosítójú vette át a labdát "
                     f"({top_rst['takes']}/{rst[side]['restarts']} "
                     "újraindítás).")
    except Exception:
        pass
    # Váltópárok: ki kit vált a cseréknél.
    try:
        from .substitutions import swap_pairs
        swp = swap_pairs(match)
        for side, name in (("home", home), ("away", away)):
            top_swp = swp[side]["top"]
            if top_swp is None:
                continue
            body += (f" A(z) {name} cseréje kiszámítható: a(z) "
                     f"{top_swp['out_id']} azonosítójút "
                     f"{top_swp['count']} alkalommal is a(z) "
                     f"{top_swp['in_id']} azonosítójú váltotta.")
    except Exception:
        pass
    # Visszahozott támadások: lezárják vagy újrajáratják a betörést.
    try:
        from .attack_types import pullback_rate
        pb = pullback_rate(match)
        for side, name in (("home", home), ("away", away)):
            rec_pb = pb[side]
            if rec_pb["verdict"] is None:
                continue
            body += (f" A(z) {name} támadásban {rec_pb['verdict']}: "
                     f"{rec_pb['entries']} betörésükből "
                     f"{rec_pb['pullbacks']} végződött lövés nélküli "
                     "visszahozással.")
    except Exception:
        pass
    # Szerzés utáni indítás: azonnal előre megy-e a szerzett labda.
    try:
        from .defense import steal_launch
        stl = steal_launch(match)
        for side, name in (("home", home), ("away", away)):
            rec_stl = stl[side]
            if rec_stl["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_stl['verdict']}: "
                     f"{rec_stl['steals']} szerzésükből "
                     f"{rec_stl['forward']} után ment azonnal előre a "
                     "labda.")
    except Exception:
        pass
    # Hetes-fáradás: mikor adják a heteseket.
    try:
        from .rules import sevens_fade
        s7f = sevens_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_s7f = s7f[side]
            if rec_s7f["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_s7f['verdict']} "
                     f"({rec_s7f['fh']} az elsőben, {rec_s7f['sh']} a "
                     "másodikban).")
    except Exception:
        pass
    # Fal-fáradás: melyik félidőben nyílik ki a fal.
    try:
        from .xg import wall_fade
        wf = wall_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_wf = wf[side]
            if rec_wf["verdict"] is None:
                continue
            body += (f" A(z) {name} falánál {rec_wf['verdict']}: a "
                     f"kapott lövések átlagos helyzet-értéke "
                     f"{rec_wf['fh_avg_xga']:.2f}-ról "
                     f"{rec_wf['sh_avg_xga']:.2f}-ra változott a "
                     "szünet után.")
    except Exception:
        pass
    # Pad-gólok: a kispad is termel-e, vagy csak a kezdők.
    try:
        from .momentum import bench_scoring
        ben = bench_scoring(match)
        for side, name in (("home", home), ("away", away)):
            rec_ben = ben[side]
            if rec_ben["verdict"] is None:
                continue
            body += (f" A(z) {name} támadójátékában {rec_ben['verdict']}"
                     f": {rec_ben['goals']} lövőhöz köthető góljukból "
                     f"{rec_ben['bench_goals']} jött a padról.")
    except Exception:
        pass
    # Labdaszerzés-típus: elfogják vagy leszerelik a labdát.
    try:
        from .defense import steal_types
        stt = steal_types(match)
        for side, name in (("home", home), ("away", away)):
            rec_stt = stt[side]
            if rec_stt["verdict"] is None:
                continue
            body += (f" A(z) {name} védekezésben {rec_stt['verdict']}"
                     f": {rec_stt['steals']} labdaszerzésükből "
                     f"{rec_stt['interceptions']} röptében elfogott "
                     "passz.")
    except Exception:
        pass
    # Kapott helyzetek minősége: milyen lövéseket enged a fal.
    try:
        from .xg import conceded_chance_quality
        ccq = conceded_chance_quality(match)
        for side, name in (("home", home), ("away", away)):
            rec_ccq = ccq[side]
            if rec_ccq["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_ccq['verdict']}: a rájuk "
                     f"jövő {rec_ccq['shots']} lövés átlagos "
                     f"helyzet-értéke {rec_ccq['avg_xga']:.2f}.")
    except Exception:
        pass
    # Félidő-zárás: mit kezdenek az utolsó labdával.
    try:
        from .momentum import closing_attacks
        clo = closing_attacks(match)
        for side, name in (("home", home), ("away", away)):
            rec_clo = clo[side]
            if rec_clo["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_clo['verdict']}: a félidők "
                     f"utolsó percében {rec_clo['attacks']} "
                     f"támadásukból {rec_clo['goals']} lett gól.")
    except Exception:
        pass
    # Lerohanás-hatékonyság: mennyi lesz gól a kontrákból.
    try:
        from .attack_types import fast_break_conversion
        fbc = fast_break_conversion(match)
        for side, name in (("home", home), ("away", away)):
            rec_fbc = fbc[side]
            if rec_fbc["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_fbc['verdict']}: "
                     f"{rec_fbc['breaks']} lerohanásból "
                     f"{rec_fbc['goals']} lett gól "
                     f"({rec_fbc['share_pct']:.0f}%).")
    except Exception:
        pass
    # Félidő-nyitás: hogyan indulnak a félidők első 5 percében.
    try:
        from .momentum import half_openings
        hop = half_openings(match)
        for side, name in (("home", home), ("away", away)):
            rec_hop = hop[side]
            if rec_hop["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_hop['verdict']}: a félidők "
                     f"első öt percében {rec_hop['goals_for']}-"
                     f"{rec_hop['goals_against']} a mérlegük.")
    except Exception:
        pass
    # Időkérés utáni védekezés: megáll-e a fal a megszakítás után.
    try:
        from .stoppages import timeout_first_defense
        tfd = timeout_first_defense(match)
        for side, name in (("home", home), ("away", away)):
            rec_tfd = tfd[side]
            if rec_tfd["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_tfd['verdict']}: az "
                     f"időkéréseik {rec_tfd['share_pct']:.0f}%-a után "
                     "az ellenfél első rohamából gól esett "
                     f"({rec_tfd['timeouts']} időkérés).")
    except Exception:
        pass
    # Gól utáni letámadás: saját gól után feljebb megy-e a fal.
    try:
        from .defense import press_after_goal
        pag = press_after_goal(match)
        for side, name in (("home", home), ("away", away)):
            rec_pag = pag[side]
            if rec_pag["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_pag['verdict']}: saját gól "
                     f"után {rec_pag['after_m']:.1f} m-en áll a fal a "
                     f"szokásos {rec_pag['base_m']:.1f} m helyett.")
    except Exception:
        pass
    # Felhozatal-idő: milyen gyorsan érnek a támadó térfélre.
    try:
        from .attack_types import buildup_time, BUT_SLOW_S
        but = buildup_time(match)
        for side, name in (("home", home), ("away", away)):
            rec_but = but[side]
            if rec_but["verdict"] is None:
                continue
            hint = ("van idő rendezetten felállni ellenük"
                    if rec_but["avg_s"] >= BUT_SLOW_S
                    else "a lövés pillanatában indulni kell hátra")
            body += (f" A(z) {name} {rec_but['verdict']}: átlag "
                     f"{rec_but['avg_s']:.1f} mp alatt érnek át a "
                     f"támadó térfélre — {hint}.")
    except Exception:
        pass
    # Fedezetten lövők: ki húzta el a ravaszt nyomás alatt is.
    try:
        from .defense import covered_shooters
        cov = covered_shooters(match)
        for side, name in (("home", home), ("away", away)):
            top_cov = cov[side]["top"]
            if top_cov is None:
                continue
            jn = (top_cov["jersey"]
                  or _jersey_of_track(match).get(top_cov["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_cov['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} fedezetten is lőtt "
                     f"({top_cov['covered']}/{top_cov['shots']} "
                     "lövése volt fedezett).")
    except Exception:
        pass
    # Pressz-érzékeny játékosok: ki veszítette el a labdát szorításban.
    try:
        from .decisions import pressure_sensitive_players
        psp = pressure_sensitive_players(match)
        for side, name in (("home", home), ("away", away)):
            top_psp = psp[side]["top"]
            if top_psp is None:
                continue
            jn = (top_psp["jersey"]
                  or _jersey_of_track(match).get(top_psp["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_psp['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} veszítette el a labdát a "
                     f"legtöbbször szorításban "
                     f"({top_psp['press_to']}/"
                     f"{top_psp['press_events']} nyomott döntés).")
    except Exception:
        pass
    # Elöl szerző védők: ki szedte a labdát a támadó térfélen.
    try:
        from .defense import high_steal_players
        hsp = high_steal_players(match)
        for side, name in (("home", home), ("away", away)):
            top_hsp = hsp[side]["top"]
            if top_hsp is None:
                continue
            jn = (top_hsp["jersey"]
                  or _jersey_of_track(match).get(top_hsp["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_hsp['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} elöl szedte a labdákat "
                     f"({top_hsp['high']}/{top_hsp['steals']} "
                     "szerzés a támadó térfélen).")
    except Exception:
        pass
    # Pontatlan lövők: kinek a lövései kerülték el a kaput.
    try:
        from .xg import wasteful_shooters
        wst = wasteful_shooters(match)
        for side, name in (("home", home), ("away", away)):
            top_wst = wst[side]["top"]
            if top_wst is None:
                continue
            jn = (top_wst["jersey"]
                  or _jersey_of_track(match).get(top_wst["player_id"]))
            who = (f"{jn}-es mezszámú játékosának" if jn is not None
                   else f"{top_wst['player_id']} azonosítójú "
                        "játékosának")
            body += (f" A(z) {name} a {who} lövései kerülték el a "
                     f"leggyakrabban a kaput "
                     f"({top_wst['off_target']}/{top_wst['shots']}).")
    except Exception:
        pass
    # Kezdő hatos: kikkel kezdték a meccset.
    try:
        from .momentum import opening_lineup
        opl = opening_lineup(match)
        for side, name in (("home", home), ("away", away)):
            core = opl[side]["core"]
            if len(core) < 4:
                continue
            jerseys = _jersey_of_track(match)
            names = []
            for row in core[:6]:
                jn = row["jersey"] or jerseys.get(row["player_id"])
                names.append(str(jn) if jn is not None
                             else f"#{row['player_id']}")
            body += f" A(z) {name} kezdő emberei: {', '.join(names)}."
    except Exception:
        pass
    # Hetes-kiharcolás poszt szerint: honnan jönnek a hetesek.
    try:
        from .rules import seven_earner_roles
        ser = seven_earner_roles(match)
        for side, name in (("home", home), ("away", away)):
            top_ser = ser[side]["top"]
            if top_ser is None:
                continue
            body += (f" A(z) {name} heteseinek "
                     f"{top_ser['share_pct']:.0f}%-át a "
                     f"{top_ser['poszt']} posztról harcolták ki "
                     f"({top_ser['count']}/{ser[side]['sevens']}).")
    except Exception:
        pass
    # Időkérés utáni első támadás: volt-e kész figurájuk.
    try:
        from .stoppages import timeout_first_attack
        tfa = timeout_first_attack(match)
        for side, name in (("home", home), ("away", away)):
            rec_tfa = tfa[side]
            if rec_tfa["verdict"] is None:
                continue
            body += (f" A(z) {name} időkérései után az első támadás "
                     f"{rec_tfa['share_pct']:.0f}%-ban gólt hozott "
                     f"({rec_tfa['goals']}/{rec_tfa['timeouts']}).")
    except Exception:
        pass
    # Kockázatos passzolók: kinek a hosszú labdái vesztek el.
    try:
        from .attack_types import risky_passers
        rsk = risky_passers(match)
        for side, name in (("home", home), ("away", away)):
            top_rsk = rsk[side]["top"]
            if top_rsk is None:
                continue
            jn = (top_rsk["jersey"]
                  or _jersey_of_track(match).get(top_rsk["player_id"]))
            who = (f"{jn}-es mezszámú játékosának" if jn is not None
                   else f"{top_rsk['player_id']} azonosítójú "
                        "játékosának")
            body += (f" A(z) {name} a {who} hosszú labdái vesztek el "
                     f"a leggyakrabban "
                     f"({top_rsk['turnovers']}/{top_rsk['tries']}).")
    except Exception:
        pass
    # Elzárók: ki állt elzárásba a lövőik előtt.
    try:
        from .attack_types import screen_setters
        scs = screen_setters(match)
        for side, name in (("home", home), ("away", away)):
            top_scs = scs[side]["top"]
            if top_scs is None:
                continue
            jn = (top_scs["jersey"]
                  or _jersey_of_track(match).get(top_scs["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_scs['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} elzárásait jórészt a {who} "
                     f"állította ({top_scs['screens']} elzárás).")
    except Exception:
        pass
    # Kapus-bemelegedés: hogyan védett a meccs első tíz percében.
    try:
        from .goalkeeper import gk_early_saves
        gke = gk_early_saves(match)
        for side, name in (("home", home), ("away", away)):
            rec_gke = gke[side]
            if rec_gke["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusa {rec_gke['verdict']}: az "
                     f"első tíz percben "
                     f"{rec_gke['early']['save_pct']:.0f}%-ot fogott, "
                     f"utána {rec_gke['rest']['save_pct']:.0f}%-ot.")
    except Exception:
        pass
    # Emberhátrány-lövők: ki vállalta a befejezést öt emberrel.
    try:
        from .rules import shorthanded_shooters
        shs = shorthanded_shooters(match)
        for side, name in (("home", home), ("away", away)):
            top_shs = shs[side]["top"]
            if top_shs is None:
                continue
            jn = (top_shs["jersey"]
                  or _jersey_of_track(match).get(top_shs["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_shs['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} emberhátrányban a {who} vállalta "
                     f"a befejezést ({top_shs['shots']} lövés, "
                     f"{top_shs['goals']} gól).")
    except Exception:
        pass
    # Hajrá-hibázók: kinél ment el a labda a végén.
    try:
        from .momentum import clutch_turnover_players
        ctp = clutch_turnover_players(match)
        for side, name in (("home", home), ("away", away)):
            top_ctp = ctp[side]["top"]
            if top_ctp is None:
                continue
            jn = (top_ctp["jersey"]
                  or _jersey_of_track(match).get(top_ctp["player_id"]))
            who = (f"{jn}-es mezszámú játékosánál" if jn is not None
                   else f"{top_ctp['player_id']} azonosítójú "
                        "játékosánál")
            body += (f" A(z) {name} a hajrában a {who} veszítette el "
                     f"a labdát a legtöbbször "
                     f"({top_ctp['turnovers']} eladás).")
    except Exception:
        pass
    # Csere-kiváltók: kapott gól után cseréltek-e.
    try:
        from .substitutions import substitution_triggers
        stg = substitution_triggers(match)
        for side, name in (("home", home), ("away", away)):
            rec_stg = stg[side]
            if rec_stg["verdict"] != "kapott gólra cserélnek":
                continue
            body += (f" A(z) {name} reaktívan cserélt: a cseréik "
                     f"{rec_stg['share_pct']:.0f}%-a kapott gól után "
                     f"jött ({rec_stg['after_conceded']}/"
                     f"{rec_stg['subs']}).")
    except Exception:
        pass
    # Falépítés-idő: mennyi idő alatt állt fel a fal.
    try:
        from .defense import defense_setup_time
        dst = defense_setup_time(match)
        for side, name in (("home", home), ("away", away)):
            rec_dst = dst[side]
            if rec_dst["verdict"] is None:
                continue
            body += (f" A(z) {name} fala {rec_dst['verdict']}: átlag "
                     f"{rec_dst['avg_s']:.1f} másodperc a rendezett "
                     f"falig ({rec_dst['cases']} mért birtokváltás).")
    except Exception:
        pass
    # Kapus emberhátrányban: nőtt-e a kapus a két perc alatt.
    try:
        from .goalkeeper import gk_shorthanded_saves
        gsh = gk_shorthanded_saves(match)
        for side, name in (("home", home), ("away", away)):
            rec_gsh = gsh[side]
            if rec_gsh["verdict"] is None:
                continue
            body += (f" A(z) {name} kapusa {rec_gsh['verdict']}: "
                     f"emberhátrányban "
                     f"{rec_gsh['sh']['save_pct']:.0f}%-ot fogott, "
                     f"egyenlő létszámnál "
                     f"{rec_gsh['eq']['save_pct']:.0f}%-ot.")
    except Exception:
        pass
    # Emberelőny-lövők: kire ment a befejezés a két perc alatt.
    try:
        from .rules import powerplay_shooters
        pps = powerplay_shooters(match)
        for side, name in (("home", home), ("away", away)):
            top_pps = pps[side]["top"]
            if top_pps is None:
                continue
            jn = (top_pps["jersey"]
                  or _jersey_of_track(match).get(top_pps["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_pps['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} emberelőnyben a {who} fejezett be "
                     f"a legtöbbször ({top_pps['shots']} lövés, "
                     f"{top_pps['goals']} gól).")
    except Exception:
        pass
    # Lövés-távolság esése: kifelé szorultak-e a hajrára.
    try:
        from .attack_types import shot_distance_fade
        sdf = shot_distance_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_sdf = sdf[side]
            if rec_sdf["verdict"] != "kifelé szorulnak":
                continue
            body += (f" A(z) {name} a hajrára kifelé szorult: a "
                     f"lövéseik átlagos távolsága "
                     f"{rec_sdf['fh_avg_m']:.1f} m-ről "
                     f"{rec_sdf['sh_avg_m']:.1f} m-re nőtt.")
    except Exception:
        pass
    # Kapott gólok támadás-típus szerint: melyik műfajból szivárogtak.
    try:
        from .defense import conceded_by_attack_type
        cat = conceded_by_attack_type(match)
        for side, name in (("home", home), ("away", away)):
            top_cat = cat[side]["top"]
            if top_cat is None:
                continue
            body += (f" A(z) {name} kapott góljainak "
                     f"{top_cat['share_pct']:.0f}%-a "
                     f"{top_cat['type']}-ból jött "
                     f"({top_cat['goals']}/{cat[side]['goals']}).")
    except Exception:
        pass
    # Áttörő játékosok: ki vitte be a labdát a falba.
    try:
        from .attack_types import breakthrough_players
        btp = breakthrough_players(match)
        for side, name in (("home", home), ("away", away)):
            top_btp = btp[side]["top"]
            if top_btp is None:
                continue
            jn = (top_btp["jersey"]
                  or _jersey_of_track(match).get(top_btp["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_btp['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} tört be a legtöbbször a "
                     f"falba ({top_btp['entries']} betörés, ebből "
                     f"{top_btp['goals']} gólos támadás).")
    except Exception:
        pass
    # Két beállós játék: hány emberrel dolgoztak a 6 m-en.
    try:
        from .attack_types import double_pivot_usage
        dpv = double_pivot_usage(match)
        for side, name in (("home", home), ("away", away)):
            rec_dpv = dpv[side]
            if rec_dpv["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_dpv['verdict']}: a "
                     f"támadásaik {rec_dpv['share_pct']:.0f}%-ában "
                     f"volt két emberük a 6 m-es zónában "
                     f"({rec_dpv['attacks']} támadás).")
    except Exception:
        pass
    # Hajrá-ötös: kik voltak a pályán a döntő szakaszban.
    try:
        from .momentum import clutch_lineup
        cll = clutch_lineup(match)
        for side, name in (("home", home), ("away", away)):
            core = cll[side]["core"]
            if not core:
                continue
            jerseys = _jersey_of_track(match)
            names = []
            for row in core[:6]:
                jn = row["jersey"] or jerseys.get(row["player_id"])
                names.append(str(jn) if jn is not None
                             else f"#{row['player_id']}")
            body += (f" A(z) {name} hajrá-emberei: "
                     f"{', '.join(names)}.")
    except Exception:
        pass
    # Kontra-kíséret: hányan futottak fel a lerohanásoknál.
    try:
        from .attack_types import fast_break_support
        fbs = fast_break_support(match)
        for side, name in (("home", home), ("away", away)):
            rec_fbs = fbs[side]
            if rec_fbs["verdict"] is None:
                continue
            body += (f" A(z) {name} lerohanásai {rec_fbs['verdict']}-t "
                     f"mutattak: átlag {rec_fbs['avg_runners']:.1f} "
                     f"felfutó ember ({rec_fbs['breaks']} lerohanás).")
    except Exception:
        pass
    # Kapus-hetesvédés iránya: melyik sarok volt a gyengéje.
    try:
        from .rules import gk_seven_directions
        g7d = gk_seven_directions(match)
        for side, name in (("home", home), ("away", away)):
            weak = g7d[side]["weak_dir"]
            if weak is None:
                continue
            body += (f" A(z) {name} kapusa a {weak['irany']} sarokba "
                     f"menő heteseknél volt gyenge: onnan "
                     f"{weak['save_pct']:.0f}%-ot fogott "
                     f"({weak['faced']} hetes).")
    except Exception:
        pass
    # Kihozatal-oldal: melyik oldalon indították a támadásokat.
    try:
        from .attack_types import buildup_side
        bus = buildup_side(match)
        for side, name in (("home", home), ("away", away)):
            rec_bus = bus[side]
            if rec_bus["dominant"] in (None, "közép"):
                continue
            body += (f" A(z) {name} a {rec_bus['dominant']} oldalon "
                     f"hozta fel a labdát: a támadásaik "
                     f"{rec_bus['share_pct']:.0f}%-a onnan indult.")
    except Exception:
        pass
    # Lepattanó-szerzők: ki nyerte a kipattanókat.
    try:
        from .attack_types import rebound_winners
        rbw = rebound_winners(match)
        for side, name in (("home", home), ("away", away)):
            top_off = rbw[side]["top_off"]
            if top_off is None:
                continue
            jn = (top_off["jersey"]
                  or _jersey_of_track(match).get(top_off["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_off['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} gyűjtötte a támadó "
                     f"lepattanókat ({top_off['rebounds']} "
                     "visszaszerzett kipattanó).")
    except Exception:
        pass
    # Lövő-távolság: ki lőtt távolról, ki fejezett be közelről.
    try:
        from .attack_types import shooter_ranges
        shr = shooter_ranges(match)
        for side, name in (("home", home), ("away", away)):
            far = shr[side]["far"]
            if far is None:
                continue
            jn = (far["jersey"]
                  or _jersey_of_track(match).get(far["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{far['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} távolról lőtt: átlag "
                     f"{far['avg_dist_m']:.1f} m-ről "
                     f"({far['shots']} lövés).")
    except Exception:
        pass
    # Emberhátrány-forma: milyen falat húztak öt emberrel.
    try:
        from .rules import shorthanded_shape
        shs = shorthanded_shape(match)
        for side, name in (("home", home), ("away", away)):
            rec_shs = shs[side]
            if rec_shs["main"] is None:
                continue
            body += (f" A(z) {name} emberhátrányban {rec_shs['main']}-s "
                     f"falat húzott (a mért kockák "
                     f"{rec_shs['main_pct']:.0f}%-ában).")
    except Exception:
        pass
    # Emberelőny-tempó: elnyújtották vagy kapkodták az emberelőnyt.
    try:
        from .rules import powerplay_pace
        ppp = powerplay_pace(match)
        for side, name in (("home", home), ("away", away)):
            rec_ppp = ppp[side]
            if rec_ppp["verdict"] is None:
                continue
            body += (f" A(z) {name} {rec_ppp['verdict']}: "
                     f"{rec_ppp['pp_avg_s']:.0f} mp-es támadások "
                     f"emberelőnyben, {rec_ppp['eq_avg_s']:.0f} mp "
                     f"egyenlő létszámnál ({rec_ppp['pp_attacks']} "
                     "emberelőnyös támadás).")
    except Exception:
        pass
    # Effektív játékidő: milyen ritmusú volt a meccs.
    try:
        from .stoppages import playing_time_profile
        ptp = playing_time_profile(match)["home"]
        if ptp["verdict"] is not None:
            body += (f" A meccs {ptp['verdict']} volt: az effektív "
                     f"játékidő {ptp['effective_pct']:.0f}% "
                     f"({ptp['stoppages']} megszakítás, "
                     f"{ptp['stopped_s'] / 60.0:.1f} perc holt idő).")
    except Exception:
        pass
    # Védekezés-keménység: mennyi büntetést hozott a faluk.
    try:
        from .defense import defensive_aggression
        agr = defensive_aggression(match)
        for side, name in (("home", home), ("away", away)):
            rec_agr = agr[side]
            if rec_agr["verdict"] is None:
                continue
            body += (f" A(z) {name} fala {rec_agr['verdict']} volt: a "
                     f"védekezett támadásaik {rec_agr['pct']:.0f}%-a "
                     f"végződött hetessel vagy kiállítással "
                     f"({rec_agr['sevens']} hetes, "
                     f"{rec_agr['suspensions']} kiállítás "
                     f"{rec_agr['attacks']} támadásból).")
    except Exception:
        pass
    # Visszaérés-fegyelem: ki nem futott vissza védekezni.
    try:
        from .defense import recovery_discipline
        rcd = recovery_discipline(match)
        for side, name in (("home", home), ("away", away)):
            worst = rcd[side]["worst"]
            if worst is None:
                continue
            jn = (worst["jersey"]
                  or _jersey_of_track(match).get(worst["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{worst['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} lógott elöl: a védekezett "
                     f"időnek csak {worst['share_pct']:.0f}%-ában volt "
                     "a saját térfelén.")
    except Exception:
        pass
    # Kapus-védés lövés-tempó szerint: bombák vagy helyezett lövések.
    try:
        from .goalkeeper import gk_saves_by_speed
        gsp = gk_saves_by_speed(match)
        for side, name in (("home", home), ("away", away)):
            weak_gsp = gsp[side]["weak_band"]
            if weak_gsp is None:
                continue
            band = "placed" if weak_gsp == "helyezett" else "hard"
            other = "hard" if band == "placed" else "placed"
            body += (f" A(z) {name} kapusa a {weak_gsp} lövések ellen "
                     f"volt sebezhető: azokból "
                     f"{gsp[side][band]['save_pct']:.0f}%-ot fogott "
                     f"({gsp[side][band]['faced']} lövés), a másik "
                     f"sávban {gsp[side][other]['save_pct']:.0f}%-ot.")
    except Exception:
        pass
    # Álló támadók: ki mozgott labda nélkül a legkevesebbet.
    try:
        from .tactics import static_attackers
        sta = static_attackers(match)
        for side, name in (("home", home), ("away", away)):
            rec_sta = sta[side]["static"]
            if rec_sta is None:
                continue
            jn = (rec_sta["jersey"]
                  or _jersey_of_track(match).get(rec_sta["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{rec_sta['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} alig mozgott a támadásban: "
                     f"{rec_sta['avg_mps']:.2f} m/s a csapatátlag "
                     f"{sta[side]['team_avg_mps']:.2f} m/s helyett.")
    except Exception:
        pass
    # Szélső-befejezés oldalanként: melyik szélsőjük volt veszélyes.
    try:
        from .attack_types import wing_finishing_by_side
        wfs = wing_finishing_by_side(match)
        for side, name in (("home", home), ("away", away)):
            rec_wfs = wfs[side]
            if rec_wfs["strong"] is None:
                continue
            strong = rec_wfs[rec_wfs["strong"]]
            weak = rec_wfs[rec_wfs["weak"]]
            body += (f" A(z) {name} {rec_wfs['strong']} szélsője volt "
                     f"a veszélyes: {strong['goal_pct']:.0f}% "
                     f"({strong['goals']}/{strong['shots']}), míg a "
                     f"{rec_wfs['weak']} oldalon "
                     f"{weak['goal_pct']:.0f}% "
                     f"({weak['goals']}/{weak['shots']}).")
    except Exception:
        pass
    # Beálló-oldal: melyik oldalon dolgozott a beállójuk.
    try:
        from .attack_types import pivot_side
        pvs = pivot_side(match)
        for side, name in (("home", home), ("away", away)):
            rec_pvs = pvs[side]
            if rec_pvs["dominant"] in (None, "közép"):
                continue
            body += (f" A(z) {name} beállója a {rec_pvs['dominant']} "
                     f"oldalon dolgozott: a mért kockák "
                     f"{rec_pvs['share_pct']:.0f}%-ában ott állt be.")
    except Exception:
        pass
    # Fal-csúszás: milyen gyorsan igazodott a faluk az oldalváltáshoz.
    try:
        from .defense import defensive_shift_lag
        dsl = defensive_shift_lag(match)
        for side, name in (("home", home), ("away", away)):
            rec_dsl = dsl[side]
            if rec_dsl["verdict"] is None:
                continue
            body += (f" A(z) {name} fala {rec_dsl['verdict']}: "
                     f"{rec_dsl['lag_s']:.1f} mp késéssel követte a "
                     "labda oldalváltásait.")
    except Exception:
        pass
    # Passz-sebesség: éles vagy lágy volt a labdajáratásuk.
    try:
        from .decisions import pass_speed
        psp = pass_speed(match)
        for side, name in (("home", home), ("away", away)):
            rec_psp = psp[side]
            if rec_psp["label"] in (None, "vegyes"):
                continue
            body += (f" A(z) {name} labdajáratása {rec_psp['label']} "
                     f"volt: átlag {rec_psp['avg_ms']:.1f} m/s "
                     f"passz-sebesség ({rec_psp['passes']} mért "
                     "passz).")
    except Exception:
        pass
    # Beálló-kiszolgálók: kin keresztül él a beállójuk.
    try:
        from .attack_types import pivot_feeders
        pfd = pivot_feeders(match)
        for side, name in (("home", home), ("away", away)):
            top_pf = pfd[side]["top"]
            if top_pf is None:
                continue
            jn = (top_pf["jersey"]
                  or _jersey_of_track(match).get(top_pf["player_id"]))
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top_pf['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} beállóját jórészt egy ember "
                     f"szolgálta ki: a {who} adta a beadások "
                     f"{top_pf['share_pct']:.0f}%-át "
                     f"({top_pf['feeds']}/{pfd[side]['feeds']}).")
    except Exception:
        pass
    # Hetes-okozó védők: kinél szakadt meg a védekezés hetessel.
    try:
        from .rules import seven_meter_conceders
        smc = seven_meter_conceders(match)
        for side, name in (("home", home), ("away", away)):
            top_smc = smc[side]["top"]
            if top_smc is None:
                continue
            jn = _jersey_of_track(match).get(top_smc["player_id"])
            who = (f"{jn}-es mezszámú védője" if jn is not None
                   else f"{top_smc['player_id']} azonosítójú védője")
            body += (f" A(z) {name} {who} {top_smc['conceded']} hetest "
                     "okozott.")
    except Exception:
        pass
    # Támadás-mélység: milyen messze álltak a kaputól.
    try:
        from .attack_types import attack_depth
        adp = attack_depth(match)
        for side, name in (("home", home), ("away", away)):
            rec_adp = adp[side]
            if rec_adp["style"] in (None, "kiegyensúlyozott"):
                continue
            body += (f" A(z) {name} felállása {rec_adp['style']} volt: "
                     f"a támadóik átlagosan "
                     f"{rec_adp['avg_depth_m']:.1f} m-re álltak a "
                     "kaputól.")
    except Exception:
        pass
    # Szélső-bevonás: eljutott-e a labda a szélre.
    try:
        from .attack_types import wing_involvement
        wi = wing_involvement(match)
        for side, name in (("home", home), ("away", away)):
            rec_wi = wi[side]
            if rec_wi["verdict"] is None:
                continue
            if rec_wi["verdict"] == "széthúzzák a támadást":
                body += (f" A(z) {name} széthúzta a támadást: a "
                         f"támadásaik {rec_wi['share_pct']:.0f}%-ában "
                         f"kiment a labda a szélre "
                         f"({rec_wi['with_wing']}/{rec_wi['attacks']}).")
            else:
                body += (f" A(z) {name} közép-központú volt: a "
                         f"támadásaiknak csak "
                         f"{rec_wi['share_pct']:.0f}%-ában jutott ki a "
                         f"labda a szélre ({rec_wi['attacks']} "
                         "támadás).")
    except Exception:
        pass
    # Védekezési mélység állás szerint: mikor jött a nyomásuk.
    try:
        from .defense import line_height_by_score
        lhs = line_height_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_lhs = lhs[side]
            if rec_lhs["verdict"] is None:
                continue
            if rec_lhs["verdict"] == "hátrányban feljebb lépnek":
                body += (f" A(z) {name} fala hátrányban feljebb "
                         f"lépett: {rec_lhs['trailing']['avg_height_m']:.1f} "
                         f"m-en védekezett hátrányban és "
                         f"{rec_lhs['leading']['avg_height_m']:.1f} "
                         "m-en vezetve.")
            else:
                body += (f" A(z) {name} vezetve is fent maradt: "
                         f"{rec_lhs['leading']['avg_height_m']:.1f} "
                         f"m-en védekezett előnyben és "
                         f"{rec_lhs['trailing']['avg_height_m']:.1f} "
                         "m-en hátrányban.")
    except Exception:
        pass
    # Támadás-kimenetel: eljutottak-e egyáltalán a befejezésig.
    try:
        from .attack_types import attack_outcomes
        ao_ = attack_outcomes(match)
        for side, name in (("home", home), ("away", away)):
            rec_ao = ao_[side]
            if rec_ao["verdict"] is None:
                continue
            if rec_ao["verdict"] == "lövés nélkül halnak el":
                body += (f" A(z) {name} támadásainak "
                         f"{rec_ao['turnover_pct']:.0f}%-a lövés "
                         f"nélkül, eladással halt el "
                         f"({rec_ao['attacks']} támadás).")
            else:
                body += (f" A(z) {name} szinte mindent befejezett: a "
                         f"támadásaik {rec_ao['shot_pct']:.0f}%-a "
                         f"lövéssel zárult ({rec_ao['attacks']} "
                         "támadás).")
    except Exception:
        pass
    # Kapus-védés posztonként: melyik szögből volt sebezhető a kapus.
    try:
        from .goalkeeper import gk_saves_by_role
        gsr = gk_saves_by_role(match)
        for side, name in (("home", home), ("away", away)):
            weak_gsr = gsr[side]["weak"]
            if weak_gsr is None:
                continue
            body += (f" A(z) {name} kapusa a {weak_gsr['poszt']} "
                     f"posztról volt sebezhető: onnan "
                     f"{weak_gsr['save_pct']:.0f}%-ot fogott "
                     f"({weak_gsr['faced']} kapura tartó lövés).")
    except Exception:
        pass
    # Hiba-sorozatok: egymás után jöttek-e az eladások.
    try:
        from .defense import turnover_clusters
        tc = turnover_clusters(match)
        for side, name in (("home", home), ("away", away)):
            rec_tc = tc[side]
            if rec_tc["verdict"] != "sorozatban hibáznak":
                continue
            body += (f" A(z) {name} sorozatban hibázott: az "
                     f"eladásaik {rec_tc['share_pct']:.0f}%-a egy "
                     f"percen belül követte az előzőt "
                     f"({rec_tc['clustered']}/{rec_tc['turnovers']}, "
                     f"{rec_tc['clusters']} sorozat).")
    except Exception:
        pass
    # Kapott gólok posztonként: melyik poszt ellen szivárgott a faluk.
    try:
        from .defense import conceded_by_role
        cbr = conceded_by_role(match)
        for side, name in (("home", home), ("away", away)):
            top_cbr = cbr[side]["top"]
            if top_cbr is None:
                continue
            body += (f" A(z) {name} fala egy poszt ellen szivárgott: a "
                     f"kapott góljaik {top_cbr['share_pct']:.0f}%-a a "
                     f"{top_cbr['poszt']} posztról jött "
                     f"({top_cbr['goals']}/{cbr[side]['goals']}).")
    except Exception:
        pass
    # Poszt szerinti gólmegoszlás: melyik posztra épült a befejezésük.
    try:
        from .roles import goals_by_role
        gbr = goals_by_role(match)
        for side, name in (("home", home), ("away", away)):
            top_gbr = gbr[side]["top"]
            if top_gbr is None:
                continue
            body += (f" A(z) {name} befejezése egy posztra épült: a "
                     f"góljaik {top_gbr['share_pct']:.0f}%-a a "
                     f"{top_gbr['poszt']} posztról jött "
                     f"({top_gbr['goals']}/{gbr[side]['goals']}).")
    except Exception:
        pass
    # Gólpassz-zónák: melyik vonalról jöttek az előkészítések.
    try:
        from .event_detection import assist_zones
        az = assist_zones(match)
        for side, name in (("home", home), ("away", away)):
            top_az = az[side]["top"]
            if top_az is None:
                continue
            body += (f" A(z) {name} gólpasszai jórészt egy vonalról "
                     f"jöttek: {top_az['zone']} érkezett az "
                     f"előkészítések {top_az['share_pct']:.0f}%-a "
                     f"({top_az['goals']}/{az[side]['assists']}).")
    except Exception:
        pass
    # Támadás-indítók: egy ember hozta-e fel a labdák nagy részét.
    try:
        from .attack_types import attack_starters
        st = attack_starters(match)
        for side, name in (("home", home), ("away", away)):
            top = st[side]["top"]
            if top is None:
                continue
            jn = _jersey_of_track(match).get(top["player_id"])
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{top['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} támadásait jórészt egy ember "
                     f"indította: a {who} hozta fel a labdát a "
                     f"támadások {top['share_pct']:.0f}%-ában "
                     f"({top['starts']}/{st[side]['attacks']}).")
    except Exception:
        pass
    # Lövő-erő: volt-e a csapatátlag felett bombázó befejezőjük.
    try:
        from .event_detection import shooter_power
        spw = shooter_power(match)
        for side, name in (("home", home), ("away", away)):
            cannon = spw[side]["cannon"]
            if cannon is None:
                continue
            jn = _jersey_of_track(match).get(cannon["player_id"])
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{cannon['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} bombázott: "
                     f"{cannon['avg_kmh']:.0f} km/h átlagsebesség "
                     f"({cannon['shots']} mért lövés, csapatátlag "
                     f"{spw[side]['avg_kmh']:.0f} km/h).")
    except Exception:
        pass
    # Lövő-kapuoldal: volt-e kiszámítható befejezőjük.
    try:
        from .attack_types import shooter_placement
        shp = shooter_placement(match)
        for side, name in (("home", home), ("away", away)):
            pred = shp[side]["predictable"]
            if pred is None:
                continue
            jn = _jersey_of_track(match).get(pred["player_id"])
            who = (f"{jn}-es mezszámú játékosa" if jn is not None
                   else f"{pred['player_id']} azonosítójú játékosa")
            body += (f" A(z) {name} {who} kiszámítható a "
                     f"befejezésben: a {pred['goals']} góljából "
                     f"{pred['share_pct']:.0f}% a "
                     f"{pred['dominant']} oldalra ment.")
    except Exception:
        pass
    # Szélső-védekezés: bírta-e a fal a szélső lövéseket.
    try:
        from .defense import wing_defense
        wdf = wing_defense(match)
        for side, name in (("home", home), ("away", away)):
            rec_wd = wdf[side]
            if rec_wd["verdict"] is None:
                continue
            if rec_wd["verdict"] == "szélen nyitott":
                body += (f" A(z) {name} fala a szélen nyitott volt: a "
                         f"szélső lövések {rec_wd['wing_pct']:.0f}%-a "
                         f"gól, középről csak "
                         f"{rec_wd['center_pct']:.0f}%.")
            else:
                body += (f" A(z) {name} a szélső lövéseket zárta "
                         f"({rec_wd['wing_pct']:.0f}% gólarány, "
                         f"középről {rec_wd['center_pct']:.0f}%).")
    except Exception:
        pass
    # Drága eladók: kinek az eladásaiból lett kapott gól.
    try:
        from .defense import costly_turnover_players
        ctp = costly_turnover_players(match)
        for side, name in (("home", home), ("away", away)):
            worst = ctp[side]["worst"]
            if worst is None:
                continue
            jn = _jersey_of_track(match).get(worst["player_id"])
            who = (f"{jn}-es mezszámú játékoshoz" if jn is not None
                   else f"{worst['player_id']} azonosítójú játékoshoz")
            body += (f" A(z) {name} legdrágább eladásai a {who} "
                     f"kötődnek: "
                     f"{worst['turnovers']} eladásából "
                     f"{worst['punished']} lett fél percen belüli "
                     "kapott gól.")
    except Exception:
        pass
    # Emberelőny-védekezés: emberelőnyben is kaptak-e gólt.
    try:
        from .rules import powerplay_defense
        ppd = powerplay_defense(match)
        for side, name in (("home", home), ("away", away)):
            rec_pd = ppd[side]
            if rec_pd["verdict"] is None:
                continue
            if rec_pd["verdict"] == "szivárog":
                body += (f" A(z) {name} emberelőnyben is szivárgott: "
                         f"{rec_pd['pp_conceded']} kapott gól "
                         f"{rec_pd['pp_seconds'] / 60:.1f} perc alatt "
                         f"({rec_pd['pp_per_min']:.2f} gól/perc, "
                         f"egyenlő létszámnál "
                         f"{rec_pd['eq_per_min']:.2f}).")
            else:
                body += (f" A(z) {name} emberelőnyben fegyelmezetten "
                         f"védekezett ({rec_pd['pp_per_min']:.2f} "
                         f"kapott gól/perc, egyenlő létszámnál "
                         f"{rec_pd['eq_per_min']:.2f}).")
    except Exception:
        pass
    # Kapus szabad lövés ellen: a fal nélkül is védett-e.
    try:
        from .goalkeeper import gk_free_shot_saves
        gkf = gk_free_shot_saves(match)
        for side, name in (("home", home), ("away", away)):
            rec_gf = gkf[side]
            if rec_gf["verdict"] is None:
                continue
            if rec_gf["verdict"] == "falfüggő":
                body += (f" A(z) {name} kapusa a fal mögött védett: "
                         f"fedezett lövésnél "
                         f"{rec_gf['covered_save_pct']:.0f}%, szabad "
                         f"lövésnél csak "
                         f"{rec_gf['free_save_pct']:.0f}% védés.")
            else:
                body += (f" A(z) {name} kapusa a szabad lövéseket is "
                         f"fogta ({rec_gf['free_save_pct']:.0f}% "
                         f"védés, fedezett lövésnél "
                         f"{rec_gf['covered_save_pct']:.0f}%).")
    except Exception:
        pass
    # Kettőzés: rálépett-e a második védő is a labdásra.
    try:
        from .defense import double_teams
        dbl = double_teams(match)
        for side, name in (("home", home), ("away", away)):
            rec_db = dbl[side]
            if rec_db["verdict"] is None:
                continue
            if rec_db["verdict"] == "kettőz":
                body += (f" A(z) {name} sokat kettőzött a labdáson "
                         f"(a labdás kockák "
                         f"{rec_db['doubled_pct']:.0f}%-ában két védő "
                         f"is rálépett, {rec_db['forced_turnovers']} "
                         "eladást kikényszerítve).")
            else:
                body += (f" A(z) {name} 1v1-et hagyott a labdáson "
                         f"(csak {rec_db['doubled_pct']:.0f}%-ban "
                         "lépett rá második védő).")
    except Exception:
        pass
    # Kapus-indítás iránya: egyoldalúan nyitott-e a kapus.
    try:
        from .goalkeeper import gk_outlet_side
        gos = gk_outlet_side(match)
        for side, name in (("home", home), ("away", away)):
            rec_go = gos[side]
            if rec_go["side"] is None:
                continue
            pct = (rec_go["left_pct"] if rec_go["side"] == "bal"
                   else 100.0 - rec_go["left_pct"])
            body += (f" A(z) {name} kapusa szinte mindig a "
                     f"{rec_go['side']} oldalra indított "
                     f"({pct:.0f}%, {rec_go['outlets']} indításból).")
    except Exception:
        pass
    # Hajrá-eladás: nyomás alatt megőrizték-e a labdát.
    try:
        from .momentum import clutch_turnovers
        cto = clutch_turnovers(match)
        if cto.get("available"):
            for side, name in (("home", home), ("away", away)):
                rec_ct = cto[side]
                if rec_ct["verdict"] is None:
                    continue
                if rec_ct["verdict"] == "hajrá-hibázó":
                    body += (f" A(z) {name} a hajrában szétesett a "
                             f"labdakezelésben: az eladás-ütemük "
                             f"{rec_ct['early_per_min']:.2f}-ről "
                             f"{rec_ct['clutch_per_min']:.2f} "
                             "eladás/percre ugrott.")
                else:
                    body += (f" A(z) {name} a hajrában hidegvérű "
                             f"maradt (az eladás-ütemük "
                             f"{rec_ct['early_per_min']:.2f}-ről "
                             f"{rec_ct['clutch_per_min']:.2f}-re "
                             "csökkent).")
    except Exception:
        pass
    # Hátrány-támadás: emberhátrányban is támadtak-e.
    try:
        from .rules import shorthanded_attack
        sha = shorthanded_attack(match)
        for side, name in (("home", home), ("away", away)):
            rec_sh = sha[side]
            if rec_sh["verdict"] is None:
                continue
            if rec_sh["verdict"] == "megbénul":
                body += (f" A(z) {name} emberhátrányban megbénult: "
                         f"{rec_sh['sh_goals']} gól "
                         f"{rec_sh['sh_seconds'] / 60:.1f} perc alatt "
                         f"({rec_sh['sh_per_min']:.2f} gól/perc, "
                         f"egyenlő létszámnál "
                         f"{rec_sh['eq_per_min']:.2f}).")
            else:
                body += (f" A(z) {name} emberhátrányban is támadott "
                         f"({rec_sh['sh_goals']} gól "
                         f"{rec_sh['sh_seconds'] / 60:.1f} perc "
                         "kiállítás alatt).")
    except Exception:
        pass
    # Fölény-befejezés: fölényben vagy felállt fal ellen szereztek-e gólt.
    try:
        from .attack_types import overload_finishing
        ovl = overload_finishing(match)
        for side, name in (("home", home), ("away", away)):
            rec_ov = ovl[side]
            if rec_ov["verdict"] is None:
                continue
            if rec_ov["verdict"] == "fölény-függő":
                body += (f" A(z) {name} létszámfölényben volt igazán "
                         f"eredményes ({rec_ov['overload_pct']:.0f}% "
                         f"gólarány, felállt fal ellen csak "
                         f"{rec_ov['set_pct']:.0f}%).")
            else:
                body += (f" A(z) {name} a felállt falat is törte "
                         f"({rec_ov['set_pct']:.0f}% gólarány, "
                         f"fölényben {rec_ov['overload_pct']:.0f}%).")
    except Exception:
        pass
    # Ellen-press: az eladás után visszaszerezték-e azonnal a labdát.
    try:
        from .defense import counter_press
        cpr = counter_press(match)
        for side, name in (("home", home), ("away", away)):
            rec_cp = cpr[side]
            if rec_cp["verdict"] is None:
                continue
            if rec_cp["verdict"] == "visszatámad":
                body += (f" A(z) {name} az eladás után azonnal "
                         f"visszatámadt: az eladásaik "
                         f"{rec_cp['rate_pct']:.0f}%-a után 6 mp-en "
                         "belül visszaszerezték a labdát.")
            else:
                body += (f" A(z) {name} beletörődött az eladásokba: "
                         f"csak {rec_cp['rate_pct']:.0f}%-uk után "
                         "szerezték vissza gyorsan a labdát.")
    except Exception:
        pass
    # Passz-kockázat: a hosszú passzok vesztek-e el gyakrabban.
    try:
        from .attack_types import pass_risk
        prk = pass_risk(match)
        for side, name in (("home", home), ("away", away)):
            rec_pr = prk[side]
            if rec_pr["verdict"] is None:
                continue
            if rec_pr["verdict"] == "kockázatos":
                body += (f" A(z) {name} hosszú passzai kockázatosak "
                         f"voltak: {rec_pr['long_to_pct']:.0f}%-uk "
                         f"veszett el, a rövideknek csak "
                         f"{rec_pr['short_to_pct']:.0f}%-a.")
            else:
                body += (f" A(z) {name} a hosszú passzokat is "
                         f"biztosan kezelte "
                         f"({rec_pr['long_to_pct']:.0f}% eladás, a "
                         f"rövideknél {rec_pr['short_to_pct']:.0f}%).")
    except Exception:
        pass
    # Elzárás-védekezés: bírta-e a fal az ellenfél elzárásait.
    try:
        from .defense import screen_defense
        scd = screen_defense(match)
        for side, name in (("home", home), ("away", away)):
            rec_sd = scd[side]
            if rec_sd["verdict"] is None:
                continue
            if rec_sd["verdict"] == "gyenge":
                body += (f" A(z) {name} váltása gyenge volt az "
                         f"elzárások ellen: elzárásos lövésekből "
                         f"{rec_sd['screened_pct']:.0f}%, elzárás "
                         f"nélküliekből {rec_sd['open_pct']:.0f}% gól "
                         "esett ellenük.")
            else:
                body += (f" A(z) {name} jól váltott az elzárásokon "
                         f"(elzárásos lövésekből csak "
                         f"{rec_sd['screened_pct']:.0f}% gól ellenük, "
                         f"elzárás nélküliekből "
                         f"{rec_sd['open_pct']:.0f}%).")
    except Exception:
        pass
    # Elzárás-használat: elzárásból lőttek vagy tisztán, 1v1-ből.
    try:
        from .attack_types import screen_usage
        scu = screen_usage(match)
        for side, name in (("home", home), ("away", away)):
            rec_su = scu[side]
            if rec_su["style"] is None:
                continue
            if rec_su["style"] == "elzárásos":
                body += (f" A(z) {name} elzárásokból lőtt: az őrzött "
                         f"lövéseik {rec_su['screen_pct']:.0f}%-ánál "
                         "társ zárta el a lövő őrzőjét.")
            else:
                body += (f" A(z) {name} elzárás nélkül lőtt (az őrzött "
                         f"lövéseik csak {rec_su['screen_pct']:.0f}"
                         "%-ánál volt elzárás) — a lövőik magukra "
                         "voltak hagyva.")
    except Exception:
        pass
    # Oldalváltás: széthúzó keresztpasszok vagy egy-oldalas játék.
    try:
        from .attack_types import side_switching
        ssw = side_switching(match)
        for side, name in (("home", home), ("away", away)):
            rec_sw = ssw[side]
            if rec_sw["style"] is None:
                continue
            if rec_sw["style"] == "oldalváltó":
                body += (f" A(z) {name} oldalváltásokkal húzta szét a "
                         f"falat: a támadó passzaik "
                         f"{rec_sw['switch_pct']:.0f}%-a keresztpassz "
                         "volt.")
            else:
                body += (f" A(z) {name} egy oldalon ragadt: a támadó "
                         f"passzaik csak {rec_sw['switch_pct']:.0f}"
                         "%-a volt oldalváltás.")
    except Exception:
        pass
    # Lerohanás-védés: hogy védett a kapus gyorsindítás ellen.
    try:
        from .goalkeeper import gk_break_response
        gbr = gk_break_response(match)
        for side, name in (("home", home), ("away", away)):
            rec_gbr = gbr[side]
            if rec_gbr["verdict"] is None:
                continue
            if rec_gbr["verdict"] == "érzékeny":
                body += (f" A(z) {name} kapusa a lerohanásokra "
                         f"érzékeny volt: gyorsindítás ellen "
                         f"{rec_gbr['fast_pct']:.0f}%, rendezett "
                         f"támadás ellen {rec_gbr['set_pct']:.0f}% "
                         "védés.")
            else:
                body += (f" A(z) {name} kapusa lerohanás-fogó volt: "
                         f"gyorsindítás ellen "
                         f"{rec_gbr['fast_pct']:.0f}% védés (rendezett "
                         f"ellen {rec_gbr['set_pct']:.0f}%).")
    except Exception:
        pass
    # Gól-előkészítés hossza: direkt vagy kombinatív gólok.
    try:
        from .attack_types import goal_buildup
        gbc = goal_buildup(match)
        for side, name in (("home", home), ("away", away)):
            rec_gb = gbc[side]
            if rec_gb["style"] is None:
                continue
            if rec_gb["style"] == "direkt":
                body += (f" A(z) {name} góljai direktek voltak: "
                         f"{rec_gb['short_pct']:.0f}%-uk legfeljebb "
                         "két passzból született.")
            else:
                body += (f" A(z) {name} góljai kombinatívak voltak: "
                         f"{rec_gb['long_pct']:.0f}%-uk 5+ passzos "
                         "akció végén esett.")
    except Exception:
        pass
    # Előkészítő-függés: egy emberre épül-e a gólpassz-termelés.
    try:
        from .attack_types import assist_concentration
        acc = assist_concentration(match)
        for side, name in (("home", home), ("away", away)):
            rec_ac = acc[side]
            if not rec_ac["concentrated"]:
                continue
            body += (f" A(z) {name} előkészítése egy emberen múlt: a "
                     f"gólpasszaik {100.0 * rec_ac['share']:.0f}%-a "
                     f"({rec_ac['top_assists']}/{rec_ac['assists']}) "
                     f"a(z) {rec_ac['top_player_id']}. játékostól "
                     "jött.")
    except Exception:
        pass
    # Középkezdés-tempó: kapott gól után lerohanós vagy lassú indítás.
    try:
        from .momentum import restart_speed
        rsc = restart_speed(match)
        for side, name in (("home", home), ("away", away)):
            rec_rs = rsc[side]
            if rec_rs["style"] is None:
                continue
            if rec_rs["style"] == "lerohanós":
                body += (f" A(z) {name} a kapott gólok után is "
                         f"lerohant: az újraindításaik "
                         f"{rec_rs['fast_pct']:.0f}%-ánál 12 mp-en "
                         "belül átért a labda.")
            else:
                body += (f" A(z) {name} lassan indított középről "
                         f"(átlag {rec_rs['avg_s']:.0f} mp a kapott "
                         "gól után a térfél-átlépésig).")
    except Exception:
        pass
    # Elsütés-idő: kapásból lőttek vagy sokáig fogták a labdát.
    try:
        from .xg import shot_release
        src = shot_release(match)
        for side, name in (("home", home), ("away", away)):
            rec_sr = src[side]
            if rec_sr["style"] is None:
                continue
            if rec_sr["style"] == "kapásból":
                body += (f" A(z) {name} kapásból lőtt: a lövéseik "
                         f"{rec_sr['quick_pct']:.0f}%-a 0,6 mp-en "
                         "belüli elsütés volt.")
            else:
                body += (f" A(z) {name} lövői sokáig fogták a labdát "
                         f"(csak {rec_sr['quick_pct']:.0f}% gyors "
                         f"elsütés, átlag {rec_sr['avg_hold_s']:.1f} "
                         "mp birtoklás a lövés előtt).")
    except Exception:
        pass
    # Beálló-védekezés: bírta-e a fal az ellenfél beállóját.
    try:
        from .defense import pivot_defense
        pdc = pivot_defense(match)
        for side, name in (("home", home), ("away", away)):
            rec_pd = pdc[side]
            if rec_pd["verdict"] is None:
                continue
            if rec_pd["verdict"] == "gyenge":
                body += (f" A(z) {name} beálló-őrzése gyenge volt: az "
                         f"ellene vezetett beállós támadások "
                         f"{rec_pd['pivot_goal_pct']:.0f}%-a lett gól, "
                         f"a beálló nélkülieknek csak "
                         f"{rec_pd['other_goal_pct']:.0f}%-a.")
            else:
                body += (f" A(z) {name} bírta a beállót: az ellene "
                         f"vezetett beállós támadásokból csak "
                         f"{rec_pd['pivot_goal_pct']:.0f}% gól lett "
                         f"(beálló nélkül "
                         f"{rec_pd['other_goal_pct']:.0f}%).")
    except Exception:
        pass
    # Indítás-biztonság: elcsíphető volt-e a kapus-indítás.
    try:
        from .goalkeeper import GK_OUTLET_LOST_PCT, gk_outlet_security
        gsc = gk_outlet_security(match)
        for side, name in (("home", home), ("away", away)):
            rec_gs = gsc[side]
            if rec_gs["lost_pct"] is None \
                    or rec_gs["lost_pct"] < GK_OUTLET_LOST_PCT:
                continue
            body += (f" A(z) {name} kapus-indításai elcsíphetők "
                     f"voltak: {rec_gs['outlets']} indításból "
                     f"{rec_gs['lost']} az ellenfélnél kötött ki "
                     f"({rec_gs['lost_pct']:.0f}%).")
    except Exception:
        pass
    # Támadó-mozgás: álló vagy mozgásos volt a szervezett támadás.
    try:
        from .tactics import attack_motion
        amc = attack_motion(match)
        for side, name in (("home", home), ("away", away)):
            rec_am = amc[side]
            if rec_am["style"] is None:
                continue
            if rec_am["style"] == "álló":
                body += (f" A(z) {name} támadása állt: szervezett "
                         f"támadásban átlag {rec_am['avg_mps']:.1f} "
                         "m/s-mal mozogtak — labda nélkül alig volt "
                         "elfutás.")
            else:
                body += (f" A(z) {name} támadása mozgásos volt "
                         f"(átlag {rec_am['avg_mps']:.1f} m/s "
                         "szervezett támadásban).")
    except Exception:
        pass
    # Fal-rés: réses volt-e a rendezett fal.
    try:
        from .defense import WALL_GAP_M, WALL_GAP_SHARE_PCT, wall_gaps
        wgc = wall_gaps(match)
        for side, name in (("home", home), ("away", away)):
            rec_wg = wgc[side]
            if rec_wg["share_pct"] is None \
                    or rec_wg["share_pct"] < WALL_GAP_SHARE_PCT:
                continue
            body += (f" A(z) {name} fala réses volt: a rendezett "
                     f"védekezésük kockáinak {rec_wg['share_pct']:.0f}"
                     f"%-ában {WALL_GAP_M:.1f} m-nél nagyobb rés "
                     "tátongott a szomszéd védők között.")
    except Exception:
        pass
    # Gólcsend-anatómia: kihagyós vagy néma volt a leghosszabb csend.
    try:
        from .momentum import drought_anatomy
        dac = drought_anatomy(match)
        for side, name in (("home", home), ("away", away)):
            rec_da = dac[side]
            if rec_da["verdict"] is None:
                continue
            _da_min = rec_da["drought_s"] / 60.0
            if rec_da["verdict"] == "kihagyós":
                body += (f" A(z) {name} leghosszabb gólcsendje "
                         f"({_da_min:.0f} perc) kihagyós volt: közben "
                         f"{rec_da['shots']} lövésig eljutottak, csak "
                         "nem ment be.")
            else:
                body += (f" A(z) {name} leghosszabb gólcsendje "
                         f"({_da_min:.0f} perc) néma volt: közben "
                         "lövésig is alig jutottak — a támadásuk "
                         "szervezése állt le.")
    except Exception:
        pass
    # Engedett-oldal: a fal egyik oldala átjárható.
    try:
        from .defense import conceded_side_bias
        csc = conceded_side_bias(match)
        for side, name in (("home", home), ("away", away)):
            rec_cs = csc[side]
            if rec_cs["weak_side"] is None:
                continue
            body += (f" A(z) {name} falának a(z) {rec_cs['weak_side']} "
                     f"oldala volt átjárható: a kapott szélső-sávos "
                     f"lövések {rec_cs['weak_pct']:.0f}%-a arról "
                     "jött.")
    except Exception:
        pass
    # Eladás-büntetés: az eladott labda gyors gólba kerül.
    try:
        from .defense import TO_PUNISH_HIGH_PCT, turnover_punishment
        tpc = turnover_punishment(match)
        for side, name in (("home", home), ("away", away)):
            rec_tp = tpc[side]
            if rec_tp["rate_pct"] is None \
                    or rec_tp["rate_pct"] < TO_PUNISH_HIGH_PCT:
                continue
            body += (f" A(z) {name} eladásai drágák voltak: "
                     f"{rec_tp['turnovers']} eladásából "
                     f"{rec_tp['punished']} után fél percen belül gól "
                     "volt a kapujában.")
    except Exception:
        pass
    # Kapus-indítás hossza: egysíkú (kiszámítható) kihozatal.
    try:
        from .goalkeeper import gk_outlet_length
        goc = gk_outlet_length(match)
        for side, name in (("home", home), ("away", away)):
            rec_go = goc[side]
            if rec_go["style"] is None:
                continue
            if rec_go["style"] == "hosszú":
                body += (f" A(z) {name} kapusa szinte csak hosszút "
                         f"indított (a kapus-passzai "
                         f"{rec_go['long_pct']:.0f}%-a 15 m feletti).")
            else:
                body += (f" A(z) {name} kapusa mindent rövidre hozott "
                         f"ki (a kapus-passzai csak "
                         f"{rec_go['long_pct']:.0f}%-a volt 15 m "
                         "feletti).")
    except Exception:
        pass
    # Területi-fölény-esés: a 2. félidőre hátracsúszó birtoklás.
    try:
        from .tactics import TILT_FADE_DROP_PP, tilt_fade
        tfc = tilt_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_tf = tfc[side]
            if rec_tf["drop_pp"] is None \
                    or rec_tf["drop_pp"] < TILT_FADE_DROP_PP:
                continue
            _tf_fh = 100.0 * rec_tf["fh_opp"] / rec_tf["fh_frames"]
            _tf_sh = 100.0 * rec_tf["sh_opp"] / rec_tf["sh_frames"]
            body += (f" A(z) {name} területi fölénye a 2. félidőre "
                     f"elveszett ({_tf_fh:.0f}% → {_tf_sh:.0f}% az "
                     "ellenfél térfelén) — fáradtan hátracsúszott a "
                     "játéka.")
    except Exception:
        pass
    # Asszist-függés: kollektív (kiadásból élő) vs egyéni befejezés.
    try:
        from .attack_types import assist_reliance
        adc = assist_reliance(match)
        for side, name in (("home", home), ("away", away)):
            rec_ad = adc[side]
            if rec_ad["style"] is None:
                continue
            if rec_ad["style"] == "kollektív":
                body += (f" A(z) {name} góljai kiadásból születtek "
                         f"({rec_ad['assisted']}/{rec_ad['goals']} "
                         "gólpasszos) — kollektív befejezés-stílus.")
            else:
                body += (f" A(z) {name} góljai zöme egyéni megoldás "
                         f"volt (csak {rec_ad['assisted']}/"
                         f"{rec_ad['goals']} gólpasszos).")
    except Exception:
        pass
    # Lepattanó-fal: a második hullámot visszaengedő védekezés.
    try:
        from .defense import SC_ALLOW_HIGH_PCT, second_chance_allowed
        scac = second_chance_allowed(match)
        for side, name in (("home", home), ("away", away)):
            rec_sca = scac[side]
            if rec_sca["allowed_pct"] is None \
                    or rec_sca["allowed_pct"] < SC_ALLOW_HIGH_PCT:
                continue
            body += (f" A(z) {name} fala nem zárt a lövések után: az "
                     f"ellenfél a kimaradt lövései "
                     f"{rec_sca['allowed_pct']:.0f}%-ánál újra lőhetett "
                     f"({rec_sca['allowed']}/{rec_sca['opp_misses']}).")
    except Exception:
        pass
    # Pressz-tűrés: rászorított védőnél megugró eladás-arány.
    try:
        from .decisions import (PRESS_TO_RISE_PP,
                                pass_security_under_pressure)
        psc = pass_security_under_pressure(match)
        for side, name in (("home", home), ("away", away)):
            rec_ps = psc[side]
            if rec_ps["rise_pp"] is None \
                    or rec_ps["rise_pp"] < PRESS_TO_RISE_PP:
                continue
            body += (f" A(z) {name} passzjátéka nyomás alatt megtört: "
                     f"testközeli védőnél az eladás-aránya "
                     f"{rec_ps['press_to_pct']:.0f}% volt, szabadon "
                     f"csak {rec_ps['free_to_pct']:.0f}%.")
    except Exception:
        pass
    # Eladás-időzítés: a korai eladás a letámadás-érzékenység jele.
    try:
        from .defense import TO_EARLY_S, TO_EARLY_SHARE, turnover_timing
        ttc = turnover_timing(match)
        for side, name in (("home", home), ("away", away)):
            rec_tt = ttc[side]
            if rec_tt["early_pct"] is None \
                    or rec_tt["early_pct"] < 100.0 * TO_EARLY_SHARE:
                continue
            body += (f" A(z) {name} az eladásai {rec_tt['early_pct']:.0f}"
                     f"%-át a birtoklás első {TO_EARLY_S:.0f} "
                     "másodpercében követte el — a kihozatala érzékeny "
                     "volt a letámadásra.")
    except Exception:
        pass
    # Kapus-gyengeoldal: egy oldalra kapott gólok — kész lövő-terv.
    try:
        from .goalkeeper import gk_weak_side
        gwc = gk_weak_side(match)
        for side, name in (("home", home), ("away", away)):
            rec_gw = gwc[side]
            if rec_gw["weak_side"] is None:
                continue
            body += (f" A(z) {name} kapuja a(z) {rec_gw['weak_side']} "
                     f"oldalán volt átjárható: oda ment a bekapott "
                     f"gólok {100.0 * rec_gw['share']:.0f}%-a "
                     f"({rec_gw[rec_gw['weak_side']]}/{rec_gw['goals']}, "
                     "a kapus szemszögéből).")
    except Exception:
        pass
    # Lövő-koncentráció: egy emberre épülő lövés-terhelés.
    try:
        from .xg import shot_concentration
        scc = shot_concentration(match)
        for side, name in (("home", home), ("away", away)):
            rec_sc = scc[side]
            if not rec_sc["concentrated"]:
                continue
            body += (f" A(z) {name} lövés-terhelése egy emberre épült: "
                     f"a fő lövője adta a lövéseik "
                     f"{100.0 * rec_sc['share']:.0f}%-át "
                     f"({rec_sc['top_shots']}/{rec_sc['shots']}) — "
                     "ellene a személyre szabott kettőzés rövidítés.")
    except Exception:
        pass
    # Oldal-részrehajlás: fél-oldalas támadás — eltolható fal.
    try:
        from .attack_types import attack_side_bias
        sbc = attack_side_bias(match)
        for side, name in (("home", home), ("away", away)):
            rec_sb = sbc[side]
            if rec_sb["bias_side"] is None:
                continue
            body += (f" A(z) {name} támadása fél-oldalas volt: a "
                     f"szélső-sávos lövések {rec_sb['bias_pct']:.0f}%-a "
                     f"a {rec_sb['bias_side']} oldalról jött.")
    except Exception:
        pass
    # Célzás-pontosság: a sok mellé lövés a legolcsóbb támadás-halál.
    try:
        from .xg import ACCURACY_LOW_PCT, shot_accuracy
        sac = shot_accuracy(match)
        for side, name in (("home", home), ("away", away)):
            rec_sa = sac[side]
            if rec_sa["pct"] is None or rec_sa["pct"] > ACCURACY_LOW_PCT:
                continue
            body += (f" A(z) {name} lövéseinek csak {rec_sa['pct']:.0f}%-a "
                     f"tartott kapura ({rec_sa['attempts']} kísérletből "
                     f"{rec_sa['on_target']}) — a mellé lőtt labda "
                     "ajándék-kidobás volt az ellenfélnek.")
    except Exception:
        pass
    # Befejezés-esés: a gólra váltás érdemi romlása a 2. félidőre.
    try:
        from .xg import FINISH_FADE_DROP_PP, finish_fade
        ffc = finish_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_ff = ffc[side]
            if rec_ff["drop_pp"] is None \
                    or rec_ff["drop_pp"] < FINISH_FADE_DROP_PP:
                continue
            _ff_fh = 100.0 * rec_ff["fh_goals"] / rec_ff["fh_shots"]
            _ff_sh = 100.0 * rec_ff["sh_goals"] / rec_ff["sh_shots"]
            body += (f" A(z) {name} befejezése a 2. félidőre esett "
                     f"({_ff_fh:.0f}% → {_ff_sh:.0f}% gólra váltás) — "
                     "fáradtan már nem ült a lövés.")
    except Exception:
        pass
    # Bravúr utáni lendület: a nagy védés gólt ért a túloldalon.
    try:
        from .xg import big_save_momentum
        bsmc = big_save_momentum(match)
        for side, name in (("home", home), ("away", away)):
            rec_bs = bsmc[side]
            if rec_bs["sparked"] >= 2:
                body += (f" A(z) {name} bravúrjai lendületet adtak: "
                         f"{rec_bs['saves']} nagy védésből "
                         f"{rec_bs['sparked']} után fél percen belül gól "
                         "lett elöl.")
    except Exception:
        pass
    # Kapuscsere-hatás: fordított-e a csere.
    try:
        from .goalkeeper import GK_CHANGE_DELTA_PP, gk_change_effect
        gce = gk_change_effect(match)
        for side, name in (("home", home), ("away", away)):
            rec_gc = gce[side]
            if rec_gc["delta_pp"] is None:
                continue
            _gc_pre = 100.0 * rec_gc["pre_saves"] / rec_gc["pre_faced"]
            _gc_post = 100.0 * rec_gc["post_saves"] / rec_gc["post_faced"]
            if rec_gc["delta_pp"] >= GK_CHANGE_DELTA_PP:
                body += (f" A(z) {name} kapuscseréje fordított "
                         f"({_gc_pre:.0f}% → {_gc_post:.0f}% védés a "
                         "csere után).")
            elif rec_gc["delta_pp"] <= -GK_CHANGE_DELTA_PP:
                body += (f" A(z) {name} kapuscseréje sem segített "
                         f"({_gc_pre:.0f}% → {_gc_post:.0f}% védés a "
                         "csere után).")
    except Exception:
        pass
    # Hetes-védés: a 2+ fogott hetes külön említést érdemel.
    try:
        from .rules import seven_meter_defense
        s7d = seven_meter_defense(match)
        for side, name in (("home", home), ("away", away)):
            rec_s7 = s7d[side]
            if rec_s7["saved"] >= 2:
                body += (f" A(z) {name} kapusa {rec_s7['saved']} hetest "
                         f"is megfogott ({rec_s7['faced']} kapura tartóból) "
                         "— extra mentések a legnagyobb nyomás alatt.")
    except Exception:
        pass
    # Félidő-zárás: ki nyerte a szünet előtti perceket.
    try:
        from .halftime import first_half_close
        fhc = first_half_close(match)
        if fhc is not None and abs(fhc["home"] - fhc["away"]) >= 2:
            names = {"home": home, "away": away}
            w_fhc = "home" if fhc["home"] > fhc["away"] else "away"
            body += (f" A szünet előtti perceket a(z) {names[w_fhc]} "
                     f"nyerte ({max(fhc['home'], fhc['away'])}–"
                     f"{min(fhc['home'], fhc['away'])}) — lendülettel "
                     "mentek az öltözőbe.")
    except Exception:
        pass
    # Szoros meccs: az 1-2 gólos vége a hajrá-részleteken múlt.
    try:
        from .momentum import close_game_record
        cgc = close_game_record(match)
        v_cg = cgc["home"]["verdict"]
        if v_cg in ("szoros győzelem", "szoros vereség"):
            body += (" A vége 1-2 gólos volt — az ilyen meccset a "
                     "hajrá-részletek döntik el: az utolsó támadások, az "
                     "időkérés és a higgadtság.")
    except Exception:
        pass
    # Félidei hátrányból fordítás: aki hátrányból nyerte meg.
    try:
        from .momentum import halftime_comeback
        htcc = halftime_comeback(match)
        for side, name in (("home", home), ("away", away)):
            rec_htc = htcc[side]
            if rec_htc["verdict"] == "fordította":
                body += (f" A(z) {name} félidei {-rec_htc['ht_margin']} "
                         "gólos hátrányból fordított — a második félidő "
                         "az övék volt.")
    except Exception:
        pass
    # Holtpont-mérleg: az egál-pillanatokat ki vitte el.
    try:
        from .momentum import parity_breaks
        pbc = parity_breaks(match)
        for side, name in (("home", home), ("away", away)):
            rec_pb = pbc[side]
            if rec_pb["rate_pct"] is not None and rec_pb["won"] >= 3 \
                    and rec_pb["rate_pct"] >= 75.0:
                body += (f" A holtpontokat a(z) {name} nyerte "
                         f"({rec_pb['ties']} döntetlen-állásból "
                         f"{rec_pb['won']}-szor ők léptek el).")
    except Exception:
        pass
    # Sorozat-törés: akinél az ellenfél sorozatai elfutottak.
    try:
        from .momentum import (RUN_CONTAIN_LONG, RUN_CONTAIN_MIN,
                               run_containment)
        rcc = run_containment(match)
        for side, name in (("home", home), ("away", away)):
            rec_rc = rcc[side]
            if rec_rc["avg_len"] is None \
                    or rec_rc["suffered"] < RUN_CONTAIN_MIN \
                    or rec_rc["avg_len"] < RUN_CONTAIN_LONG:
                continue
            body += (f" A(z) {name} ellen a sorozatok elfutottak "
                     f"({rec_rc['suffered']} sorozat, átlag "
                     f"{rec_rc['avg_len']:.1f} gól) — a sorozat-törés "
                     "nem működött.")
    except Exception:
        pass
    # Gól utáni elalvás: a saját gólra rendre azonnali válasz érkezik.
    try:
        from .momentum import post_goal_lapses
        pglc = post_goal_lapses(match)
        for side, name in (("home", home), ("away", away)):
            rec_pg = pglc[side]
            if rec_pg["rate_pct"] is not None and rec_pg["rate_pct"] >= 40.0 \
                    and rec_pg["quick_replies"] >= 2:
                body += (f" A(z) {name} góljaira rendre azonnali válasz "
                         f"jött ({rec_pg['goals']} góljából "
                         f"{rec_pg['quick_replies']} után fél percen belül) "
                         "— a középkezdés utáni visszarendeződés hagyott "
                         "kívánnivalót.")
    except Exception:
        pass
    # Fegyelem-esés: a kiállítások félidőnkénti sűrűsödése.
    try:
        from .rules import discipline_fade
        dfc = discipline_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_df = dfc[side]
            if rec_df["verdict"] == "hajrában szabálytalankodnak":
                body += (f" A(z) {name} kiállításai a 2. félidőre "
                         f"sűrűsödtek ({rec_df['fh_susp']} → "
                         f"{rec_df['sh_susp']}) — fáradtan "
                         "szabálytalankodnak.")
            elif rec_df["verdict"] == "az elején kemények":
                body += (f" A(z) {name} kiállításai az 1. félidőben "
                         f"jöttek ({rec_df['fh_susp']} → "
                         f"{rec_df['sh_susp']}) — kemény kezdés után "
                         "megszelídültek.")
    except Exception:
        pass
    # Labdabiztonság-esés: az eladás-ütem változása a 2. félidőre.
    try:
        from .defense import TURNOVER_FADE_RISE_PER_MIN, turnover_fade
        tfc = turnover_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_tf = tfc[side]
            if rec_tf["rise_per_min"] is None:
                continue
            if rec_tf["rise_per_min"] >= TURNOVER_FADE_RISE_PER_MIN:
                body += (f" A(z) {name} eladás-üteme a 2. félidőre megnőtt "
                         f"({rec_tf['fh_per_min']:.1f} → "
                         f"{rec_tf['sh_per_min']:.1f} eladás/perc) — "
                         "fáradtan kiengedett a keze.")
    except Exception:
        pass
    # Védekezés-fellazulás: a fal szorossága a 2. félidőre.
    try:
        from .defense import PRESSURE_FADE_LOOSEN_M, pressure_fade
        pfc = pressure_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_pf = pfc[side]
            if rec_pf["loosen_m"] is None:
                continue
            if rec_pf["loosen_m"] >= PRESSURE_FADE_LOOSEN_M:
                body += (f" A(z) {name} védekezése a 2. félidőre fellazult "
                         f"(átlag {rec_pf['fh_m']:.1f} → {rec_pf['sh_m']:.1f} "
                         "m a labdástól) — a hajrában nyíltak a rések.")
            elif rec_pf["loosen_m"] <= -PRESSURE_FADE_LOOSEN_M:
                body += (f" A(z) {name} a 2. félidőre szorosabbra húzta a "
                         f"védekezést ({rec_pf['fh_m']:.1f} → "
                         f"{rec_pf['sh_m']:.1f} m).")
    except Exception:
        pass
    # Lövés-időzítés: első hullámból lövő vagy kiváró csapat.
    try:
        from .attack_types import (SHTIM_EARLY_PCT, SHTIM_LATE_AVG_S,
                                   shot_timing)
        shc = shot_timing(match)
        for side, name in (("home", home), ("away", away)):
            rec_sh = shc[side]
            if rec_sh["early_pct"] is None:
                continue
            if rec_sh["early_pct"] >= SHTIM_EARLY_PCT:
                body += (f" A(z) {name} lövéseinek {rec_sh['early_pct']:.0f}%-a "
                         "a támadás első 8 mp-éből jött — első hullámból "
                         "élő csapat.")
            elif rec_sh["avg_s"] is not None \
                    and rec_sh["avg_s"] >= SHTIM_LATE_AVG_S:
                body += (f" A(z) {name} kivárt a lövésekkel (átlag "
                         f"{rec_sh['avg_s']:.0f} mp a támadásban) — a "
                         "felállt fal hibájára játszott.")
    except Exception:
        pass
    # Passz-hossz: direkt (hosszú) vagy rövid kombinációs passzjáték.
    try:
        from .event_detection import PLEN_LONG_PCT, pass_length
        plc = pass_length(match)
        for side, name in (("home", home), ("away", away)):
            rec_pl = plc[side]
            if rec_pl["long_pct"] is None:
                continue
            if rec_pl["long_pct"] >= PLEN_LONG_PCT:
                body += (f" A(z) {name} passzainak {rec_pl['long_pct']:.0f}%-a "
                         f"hosszú (átlag {rec_pl['avg_m']:.0f} m) — direkt, "
                         "kockázatos passzjáték.")
    except Exception:
        pass
    # Szerzés-magasság: hol születtek a labdaszerzések (letámadás-jel).
    try:
        from .defense import STEAL_HIGH_PCT, steal_height
        stc = steal_height(match)
        for side, name in (("home", home), ("away", away)):
            rec_st = stc[side]
            if rec_st["high_pct"] is None:
                continue
            if rec_st["high_pct"] >= STEAL_HIGH_PCT:
                body += (f" A(z) {name} szerzéseinek "
                         f"{rec_st['high_pct']:.0f}%-a elöl, letámadásból "
                         f"született ({rec_st['high_steals']}/"
                         f"{rec_st['steals']}) — a présük élő fegyver.")
    except Exception:
        pass
    # Falba lövés: a lövés-kísérletek blokkon elakadó hányada.
    try:
        from .defense import (BLOCKED_HIGH_PCT, BLOCKED_MIN,
                              blocked_shot_rate)
        brc = blocked_shot_rate(match)
        for side, name in (("home", home), ("away", away)):
            rec_br = brc[side]
            if rec_br["blocked"] < BLOCKED_MIN \
                    or rec_br["blocked_pct"] is None:
                continue
            if rec_br["blocked_pct"] >= BLOCKED_HIGH_PCT:
                body += (f" A(z) {name} lövés-kísérleteinek "
                         f"{rec_br['blocked_pct']:.0f}%-a blokkon akadt el "
                         f"({rec_br['blocked']}/{rec_br['attempts']}) — "
                         "kényszerű, rosszul előkészített lövések.")
    except Exception:
        pass
    # Passz-tempó: pörgetett vagy álló labdajáratás.
    try:
        from .tactics import PT_FAST_PER_MIN, PT_SLOW_PER_MIN, pass_tempo
        ptc = pass_tempo(match)
        for side, name in (("home", home), ("away", away)):
            rec_pt = ptc[side]
            if rec_pt["per_min"] is None:
                continue
            if rec_pt["per_min"] >= PT_FAST_PER_MIN:
                body += (f" A(z) {name} pörgette a labdát (átlag "
                         f"{rec_pt['per_min']:.0f} passz/perc) — a mozgó "
                         "labda folyamatosan dolgoztatta a falat.")
            elif rec_pt["per_min"] <= PT_SLOW_PER_MIN:
                body += (f" A(z) {name} állva járatta a labdát "
                         f"({rec_pt['per_min']:.0f} passz/perc) — a "
                         "védelem békében felállhatott ellene.")
    except Exception:
        pass
    # Területi fölény: hol zajlott a birtoklás (elöl nyomás / hátul ragadás).
    try:
        from .tactics import TILT_HIGH_PCT, TILT_LOW_PCT, field_tilt
        ft = field_tilt(match)
        for side, name in (("home", home), ("away", away)):
            rec_ft = ft[side]
            if rec_ft["tilt_pct"] is None:
                continue
            if rec_ft["tilt_pct"] >= TILT_HIGH_PCT:
                body += (f" A(z) {name} birtoklásának "
                         f"{rec_ft['tilt_pct']:.0f}%-a az ellenfél térfelén "
                         "zajlott — területi fölényben játszott.")
            elif rec_ft["tilt_pct"] <= TILT_LOW_PCT:
                body += (f" A(z) {name} birtoklása a saját térfelén ragadt "
                         f"(csak {rec_ft['tilt_pct']:.0f}% elöl) — a "
                         "kihozatal akadozott.")
    except Exception:
        pass
    # Támogatás-távolság: magára marad-e a labdás (prés-sebezhetőség).
    try:
        from .decisions import SUPPORT_ISO_M, support_distance
        sd = support_distance(match)
        for side, name in (("home", home), ("away", away)):
            rec_sd = sd[side]
            if rec_sd["avg_m"] is None:
                continue
            if rec_sd["avg_m"] >= SUPPORT_ISO_M or rec_sd["iso_pct"] >= 35.0:
                body += (f" A(z) {name} labdás játékosa gyakran magára marad "
                         f"(a legközelebbi társ átlag {rec_sd['avg_m']:.1f} "
                         f"m-re) — a prés működhet ellene.")
    except Exception:
        pass
    # Gól-koncentráció: egy emberre épül-e a gólszerzés.
    try:
        from .event_detection import goal_concentration
        gc = goal_concentration(match)
        for side, name in (("home", home), ("away", away)):
            rec_gc = gc[side]
            if not rec_gc["concentrated"]:
                continue
            top_gc = rec_gc["scorers"][0]
            body += (f" A(z) {name} góljainak {rec_gc['top_share_pct']:.0f}%-a "
                     f"egy játékostól (a {top_gc['player_id']}. jelűtől) jön "
                     "— az ő kikapcsolása az egész támadójátékot megfojtja.")
    except Exception:
        pass
    # Második roham: mennyire harcolnak a lepattanóért (offenzív lepattanó).
    try:
        from .attack_types import SECOND_CHANCE_MIN, second_chance
        sc = second_chance(match)
        for side, name in (("home", home), ("away", away)):
            rec_sc = sc[side]
            if rec_sc["misses"] < SECOND_CHANCE_MIN \
                    or rec_sc["rebound_pct"] is None:
                continue
            if rec_sc["rebound_pct"] >= 25.0:
                body += (f" A(z) {name} harcol a lepattanóért "
                         f"({rec_sc['second_chances']}/{rec_sc['misses']} "
                         f"kimaradás után újra lő, "
                         f"{rec_sc['rebound_pct']:.0f}%) — a lövés után is "
                         "le kell fogni a beállót és tisztázni a lepattanót.")
            elif rec_sc["rebound_pct"] <= 8.0:
                body += (f" A(z) {name} a kimaradt lövések után nem megy a "
                         f"lepattanóra ({rec_sc['rebound_pct']:.0f}%) — a "
                         "gyors indítás ellenük kifizetődő.")
    except Exception:
        pass
    # Passz-irány: vertikális (előre) vs türelmes (oldalra) játék.
    try:
        from .attack_types import pass_direction
        pd = pass_direction(match)
        for side, name in (("home", home), ("away", away)):
            rec_pd = pd[side]
            if rec_pd["passes"] < 12 or rec_pd["forward_pct"] is None:
                continue
            if rec_pd["forward_pct"] >= 45.0:
                body += (f" A(z) {name} vertikálisan játszik "
                         f"({rec_pd['forward_pct']:.0f}% előre-passz) — "
                         "gyorsan kell visszazárni.")
            elif rec_pd["forward_pct"] <= 20.0:
                body += (f" A(z) {name} türelmesen körözteti a labdát "
                         f"({rec_pd['forward_pct']:.0f}% előre-passz) — a "
                         "beállóra és az elzárásokra kell figyelni.")
    except Exception:
        pass
    # Gólpassz-forrás: honnan készítik elő a gólokat (szél/közép/hátsó).
    try:
        from .attack_types import ASSIST_SOURCE_MIN, assist_sources
        asr = assist_sources(match)
        _asr_label = {"szél": "a szélről (beadás)",
                      "közép": "középről (beálló/betörés)",
                      "hátsó": "a hátsó sorból (átlövő-kiadás)"}
        for side, name in (("home", home), ("away", away)):
            rec_asr = asr[side]
            dom = rec_asr["dominant"]
            if dom is None or rec_asr["assists"] < ASSIST_SOURCE_MIN:
                continue
            share = round(100.0 * rec_asr[dom] / rec_asr["assists"])
            if share >= 50:
                body += (f" A(z) {name} góljainak előkészítése {share}%-ban "
                         f"{_asr_label[dom]} jön.")
    except Exception:
        pass
    # Passz-lánc: átlagos passz-szám + a legjobb lánc-hossz ítélete.
    try:
        from .attack_types import pass_chains
        pc = pass_chains(match)
        for side, name in (("home", home), ("away", away)):
            rec_pc = pc[side]
            if rec_pc["attacks"] < 5 or rec_pc["avg_passes"] is None:
                continue
            sent_pc = (f" A(z) {name} átlag {rec_pc['avg_passes']:.1f} "
                       "passzból építette a támadásait")
            best_pc = rec_pc["best_bucket"]
            if best_pc is not None:
                b_pc = rec_pc["buckets"][best_pc]
                sent_pc += (f"; a legjobb gólarányt a(z) {best_pc} "
                            f"hozta ({b_pc['goals']}/{b_pc['attacks']}, "
                            f"{b_pc['goal_pct']:.0f}%)")
            body += sent_pc + "."
    except Exception:
        pass
    # Figura-hatékonyság: melyik begyakorolt támadás hozott gólt.
    try:
        from .setplays import setplay_efficiency
        eff_sp = setplay_efficiency(match)
        for side, name in (("home", home), ("away", away)):
            rows_sp = eff_sp.get(side) or []
            best_sp = max(rows_sp, key=lambda r: r["goals"], default=None)
            if best_sp and best_sp["attacks"] >= 3 \
                    and best_sp["goals"] >= 2:
                body += (f" A(z) {name} legjobb figurája "
                         f"{best_sp['attacks']} támadásból "
                         f"{best_sp['goals']} gólt hozott "
                         f"({best_sp['goal_pct']:.0f}%).")
    except Exception:
        pass
    # Előny-kezelés: időhúzás vezetve / kapkodás hátrányban (8+ mp).
    try:
        from .attack_types import pace_by_score
        pbs_all = pace_by_score(match)
        for side, name in (("home", home), ("away", away)):
            rec_l = pbs_all[side]["leading"]
            rec_t = pbs_all[side]["trailing"]
            if rec_l["avg_s"] is None or rec_t["avg_s"] is None:
                continue
            if rec_l["avg_s"] - rec_t["avg_s"] >= 8.0:
                body += (f" A(z) {name} vezetésnél átlag "
                         f"{rec_l['avg_s']:.0f} mp-re nyújtotta a "
                         f"támadásait (hátrányban {rec_t['avg_s']:.0f}) "
                         "— tudatos időhúzás.")
            elif rec_t["avg_s"] - rec_l["avg_s"] >= 8.0:
                body += (f" A(z) {name} hátrányban jóval rövidebb, "
                         f"kapkodó támadásokat vállalt (átlag "
                         f"{rec_t['avg_s']:.0f} mp, vezetve "
                         f"{rec_l['avg_s']:.0f}).")
    except Exception:
        pass
    # Passzív-veszély: a támadások jelentős része húzódik 35 mp fölé.
    try:
        from .tactics import slow_attacks
        sa = slow_attacks(match)
        for side, name in (("home", home), ("away", away)):
            rec = sa[side]
            if rec["attacks"] >= 4 and rec["slow_pct"] >= 30.0:
                body += (f" A(z) {name} támadásainak {rec['slow_pct']:.0f}%-a "
                         f"35 mp fölé húzódott (leghosszabb: "
                         f"{rec['longest_s']:.0f} mp) — passzív-veszély, "
                         "korábbi befejezés kell.")
    except Exception:
        pass
    # A játékszervezés tengelye: a leggyakoribb passz-páros (ha bejáratott).
    pass_line = ""
    try:
        from .event_detection import pass_network
        pn = pass_network(match)
        tof, jof = _team_of_track(match), _jersey_of_track(match)
        for side, name in (("home", home), ("away", away)):
            rec = pn[side]
            if rec["total_passes"] >= 10 and rec["pairs"]:
                pr = rec["pairs"][0]
                if pr["passes"] >= 4:
                    lf = _player_label(pr["from"], tof, jof, home, away)
                    lt = _player_label(pr["to"], tof, jof, home, away)
                    pass_line += (f" A(z) {name} játékának tengelye a "
                                  f"{lf} – {lt} kapcsolat "
                                  f"({pr['passes']} passz).")
    except Exception:
        pass
    return {"title": "Játékkép és tempó", "body": body + poss_line + pass_line}


def _rotation_sentence(match: Match, home: str, away: str) -> str:
    """Rotáció-mélység mondat: szűk vagy széles paddal ment-e a meccs."""
    out = ""
    try:
        from .stats import rotation_depth
        rd = rotation_depth(match)
        for side, name in (("home", home), ("away", away)):
            rec = rd[side]
            if rec["used"] < 6:
                continue
            if rec["used"] <= 8:
                out += (f" A(z) {name} szűk rotációval játszott "
                        f"({rec['used']} bevetett játékos, "
                        f"{rec['regulars']} alapember) — a hajrában "
                        "fáradás jöhet.")
            elif rec["used"] >= 11:
                out += (f" A(z) {name} széles paddal forgatott "
                        f"({rec['used']} bevetett játékos).")
    except Exception:
        pass
    return out


def _intensity_section(match: Match, home: str, away: str) -> tuple[dict | None, list[str]]:
    """Kezdés vs hajrá: az első és utolsó harmad átlag-intenzitása csapatonként."""
    windows = compute_intensity_timeline(match)
    usable = [w for w in windows if w["home_avg_ms"] > 0 or w["away_avg_ms"] > 0]
    if len(usable) < 3:
        return None, []
    third = max(1, len(usable) // 3)
    highlights: list[str] = []
    parts: list[str] = []
    for key, name in (("home_avg_ms", home), ("away_avg_ms", away)):
        start = [w[key] for w in usable[:third] if w[key] > 0]
        end = [w[key] for w in usable[-third:] if w[key] > 0]
        if not start or not end:
            continue
        s_avg = sum(start) / len(start)
        e_avg = sum(end) / len(end)
        if s_avg <= 0:
            continue
        change = 100.0 * (e_avg - s_avg) / s_avg
        if change <= -INTENSITY_DROP_WARN_PCT:
            parts.append(f"a(z) {name} intenzitása a hajrára {-change:.0f}%-kal "
                         f"esett ({s_avg:.2f} → {e_avg:.2f} m/s)")
            highlights.append(
                f"{name}: jelentős intenzitás-esés a meccs végére "
                f"({-change:.0f}%) — érdemes a cserék időzítésére ránézni.")
        elif change >= INTENSITY_DROP_WARN_PCT:
            parts.append(f"a(z) {name} a hajrában {change:.0f}%-kal pörgött fel "
                         f"({s_avg:.2f} → {e_avg:.2f} m/s)")
        else:
            parts.append(f"a(z) {name} tempója végig kiegyensúlyozott volt "
                         f"(~{s_avg:.2f} m/s)")
    if not parts:
        return None, highlights
    body = "Kezdés és hajrá összevetése: " + "; ".join(parts) + "."
    # Lövőerő-esés: a lövés-sebesség félidők közti változása (fáradás-jel,
    # a futás-intenzitástól független második mérőszám).
    try:
        from .event_detection import FADE_DROP_PCT, shot_speed_fade
        fade = shot_speed_fade(match)
        for side, name in (("home", home), ("away", away)):
            rec_f = fade[side]
            if rec_f["drop_pct"] is None:
                continue
            if rec_f["drop_pct"] >= FADE_DROP_PCT:
                body += (f" A(z) {name} lövőereje a 2. félidőre "
                         f"{rec_f['drop_pct']:.0f}%-ot esett "
                         f"({rec_f['fh_avg_kmh']:.0f} → "
                         f"{rec_f['sh_avg_kmh']:.0f} km/h) — a hajrában "
                         "puhábbak a lövései.")
            elif rec_f["drop_pct"] <= -FADE_DROP_PCT:
                body += (f" A(z) {name} lövőereje a 2. félidőben nőtt "
                         f"({rec_f['fh_avg_kmh']:.0f} → "
                         f"{rec_f['sh_avg_kmh']:.0f} km/h) — frissen "
                         "pörgetik a hajrát.")
    except Exception:
        pass
    body += _rotation_sentence(match, home, away)
    return {"title": "Intenzitás", "body": body}, highlights


def _players_section(match: Match, home: str, away: str) -> dict | None:
    stats = compute_player_stats(match)
    # Csak érdemi mintával rendelkező játékosok (ne a bíró/zajos track vezessen).
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    min_frames = max(int(10 * fps), 1)  # legalább ~10 mp mért jelenlét
    pool = {t: s for t, s in stats.items() if s.measured_frames >= min_frames}
    if not pool:
        return None
    team_of = _team_of_track(match)
    jersey_of = _jersey_of_track(match)

    def label(tid: int) -> str:
        return _player_label(tid, team_of, jersey_of, home, away)

    top_dist = max(pool.items(), key=lambda kv: kv[1].distance_m)
    top_speed = max(pool.items(), key=lambda kv: kv[1].top_speed_ms)
    top_sprint = max(pool.items(), key=lambda kv: kv[1].sprint_count)
    sentences = [
        f"Legtöbbet futott: {label(top_dist[0])} "
        f"({top_dist[1].distance_m:.0f} m).",
        f"Legnagyobb sebesség: {label(top_speed[0])} "
        f"({top_speed[1].top_speed_ms * 3.6:.1f} km/h).",
    ]
    if top_sprint[1].sprint_count > 0:
        sentences.append(
            f"Legtöbb sprint: {label(top_sprint[0])} "
            f"({top_sprint[1].sprint_count}×).")
    # Játékos-szintű fáradás: a legnagyobb 2. félidei tempó-visszaesés.
    try:
        from .stats import player_fatigue
        rows = [r for r in player_fatigue(match) if r["drop_pct"] >= 20.0]
        if rows:
            top = rows[0]
            sent_f = (
                f"A legnagyobb tempó-visszaesés: {label(top['track_id'])} "
                f"({top['first_ms']:.1f} → {top['second_ms']:.1f} m/s, "
                f"−{top['drop_pct']:.0f}%)")
            # Ha le sem cserélték, a jelzés erősebb: késő csere.
            try:
                from .substitutions import late_sub_flags
                late = {f_["track_id"] for f_ in late_sub_flags(match)}
                if top["track_id"] in late:
                    sent_f += (" — végig a pályán maradt: hasonló "
                               "meccsen korábbi csere segíthet")
                else:
                    sent_f += " — hasonló meccsnél korábbi csere segíthet"
            except Exception:
                sent_f += " — hasonló meccsnél korábbi csere segíthet"
            sentences.append(sent_f + ".")
    except Exception:
        pass
    return {"title": "Kiugró játékosok", "body": " ".join(sentences)}


def _goalkeepers_section(match: Match, home: str, away: str) -> dict | None:
    from .goalkeeper import goalkeeper_stats
    stats = goalkeeper_stats(match)
    parts: list[str] = []
    for key, name in (("home", home), ("away", away)):
        rec = stats.get(key)
        if not rec or not rec["on_target"]:
            continue
        sent = (f"a(z) {name} kapusára {rec['on_target']} kapura tartó "
                f"lövés érkezett, ebből {rec['saves']} védés "
                f"({rec['save_pct']:.0f}%)")
        if rec.get("seven_faced"):
            sent += (f"; hétméteresből {rec['seven_saved']}/"
                     f"{rec['seven_faced']}-t fogott meg")
        # Hárított xG: a védések nehézség-súlyozott értéke (ha érdemi).
        try:
            from .xg import xg_saved
            xs = xg_saved(match)[key]
            if xs >= 1.0:
                sent += f"; hárított xG: {xs:.1f}"
        except Exception:
            pass
        # Megmentett gólok: a kapott gólok a helyzet-minőséghez mérve.
        try:
            from .xg import xg_prevented
            xp = xg_prevented(match)[key]["prevented"]
            if abs(xp) >= 1.0:
                sent += (f"; a helyzetekhez képest {xp:+.1f} gól a "
                         "mérlege (GSAx)")
        except Exception:
            pass
        # Bravúr-védések: hány ziccert fogott a kapus (ha volt ilyen).
        try:
            from .xg import big_saves
            n_big = sum(1 for bs in big_saves(match)
                        if bs["team"] != key)  # a lövő az ellenfél
            if n_big >= 2:
                sent += f"; ebből {n_big} ziccert fogott (bravúr-védés)"
        except Exception:
            pass
        # Kapus-indítás: gyors felhozatal védés után (2+ mért indításnál).
        try:
            from .goalkeeper import OUTLET_FAST_S, outlet_speed
            orec = outlet_speed(match)[key]
            if orec["outlets"] >= 2 and orec["avg_s"] is not None \
                    and orec["avg_s"] <= OUTLET_FAST_S:
                sent += (f"; az indítása gyors: védés után átlag "
                         f"{orec['avg_s']:.0f} mp alatt ér át a labda "
                         "a felezőn")
        except Exception:
            pass
        # Kapus-csere: ha volt, a két kapus mérlegével együtt mondjuk el.
        try:
            from .goalkeeper import goalkeeper_timeline
            tl = goalkeeper_timeline(match)[key]
            if tl["changes"] and len(tl["stints"]) >= 2:
                mins = int(tl["changes"][0] // 60)
                pk = tl["per_keeper"]
                parts_gk = []
                for st in tl["stints"][:2]:
                    r = pk.get(st["track_id"])
                    if r and r["on_target"]:
                        parts_gk.append(
                            f"{st['track_id']}. játékos "
                            f"{r['saves']}/{r['on_target']} védés")
                sent += (f"; a(z) {name} a {mins}. perc körül kapust "
                         "cserélt")
                if parts_gk:
                    sent += " (" + ", ".join(parts_gk) + ")"
                # Bejött-e a csere? A két kapus a helyzetek nehézségén
                # át összemérve (GSAx), 3+ kapott lövésnél.
                cmp_ = [(st["track_id"], pk[st["track_id"]])
                        for st in tl["stints"][:2]
                        if pk.get(st["track_id"], {}).get(
                            "on_target", 0) >= 3]
                if len(cmp_) == 2:
                    (t1, r1), (t2, r2) = cmp_
                    d = r2["prevented"] - r1["prevented"]
                    if d >= 1.0:
                        sent += (f"; a csere bejött: a második kapus "
                                 f"({t2}.) mérlege {r2['prevented']:+.1f}"
                                 f" xG, az elsőé {r1['prevented']:+.1f}")
                    elif d <= -1.0:
                        sent += (f"; a csere nem hozott javulást: az "
                                 f"első kapus ({t1}.) mérlege volt a "
                                 f"jobb ({r1['prevented']:+.1f} xG, a "
                                 f"másodiké {r2['prevented']:+.1f})")
        except Exception:
            pass
        # Leggyengébb sarok: a legalacsonyabb védés%-ú, min. 2 lövést
        # kapott zóna — konkrét támadási irány az ellenfélnek.
        zsp = rec.get("zone_save_pct", {})
        otz = rec.get("on_target_zones", {})
        cand = [(z, p) for z, p in zsp.items() if otz.get(z, 0) >= 2]
        if cand:
            z, p = min(cand, key=lambda kv: kv[1])
            sent += f"; leggyengébb zónája: {z} ({p:.0f}% védés)"
        parts.append(sent)
    # Kimozdulás-stílus: kint álló vagy vonalon maradó kapus.
    try:
        from .goalkeeper import gk_positioning
        gp = gk_positioning(match)
        for key, name in (("home", home), ("away", away)):
            rec_gp = gp.get(key) or {}
            if rec_gp.get("style") in ("kint álló", "vonalon maradó"):
                parts.append(
                    f"a(z) {name} kapusa {rec_gp['style']} típus "
                    f"(átlag {rec_gp['avg_depth_m']:.1f} m-re a "
                    "gólvonaltól)")
    except Exception:
        pass
    if not parts:
        return None
    return {"title": "Kapusok", "body": "; ".join(parts).capitalize() + "."}


def _momentum_section(match: Match, home: str, away: str) -> tuple[dict | None, list[str]]:
    """Gól-sorozatok: válasz nélküli szériák, játékóra-idővel, állással és
    a felismert LEHETSÉGES OKOKKAL (emberelőny, 7 a 6, védekezés-váltás,
    tempó-esés)."""
    from .momentum import annotate_runs, score_progression
    runs = annotate_runs(match)
    prog = None
    try:
        prog = score_progression(match)
    except Exception:
        prog = None
    if not runs and not (prog and prog["lead_changes"]):
        return None, []
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    names = {"home": home, "away": away}

    def clock(frame: int) -> str:
        sec = frame / fps
        return f"{int(sec // 60)}:{int(sec % 60):02d}"

    parts: list[str] = []
    highlights: list[str] = []
    for r in runs:
        name = names.get(r["team"], r["team"])
        h, a = r["score_after"]
        why = f" — {', '.join(r['context'])}" if r.get("context") else ""
        parts.append(f"{name} {r['length']} gólos sorozata a {clock(r['start_frame'])}"
                     f"–{clock(r['end_frame'])} között (állás utána {h}–{a}){why}")
    # A leghosszabb sorozat külön "mire nézz rá" jelzést kap.
    top = max(runs, key=lambda r: r["length"])
    tname = names.get(top["team"], top["team"])
    highlights.append(
        f"{tname} {top['length']} gólos sorozatot futott — nézd vissza, mi "
        "működött, és a másik oldalon hol akadt el a játék (időkérés, "
        "védekezés-váltás).")
    body = "; ".join(parts).capitalize() + "." if parts else ""
    if prog and prog["lead_changes"] >= 1:
        names = {"home": home, "away": away}
        bl = prog["biggest_lead"]
        top_side = "home" if bl["home"] >= bl["away"] else "away"
        body += (f" A meccs {prog['lead_changes']}-szor fordult; a legnagyobb "
                 f"előny {names[top_side]} javára {bl[top_side]} gól.")
    # Válasz-idő: milyen gyorsan felelnek a kapott gólra (3+ válasznál).
    try:
        from .momentum import goal_responses
        gr = goal_responses(match)
        names = {"home": home, "away": away}
        for side in ("home", "away"):
            rec = gr[side]
            if rec["responses"] >= 3 and rec["avg_s"] is not None:
                if rec["avg_s"] <= 60.0:
                    body += (f" A(z) {names[side]} átlag "
                             f"{rec['avg_s']:.0f} mp alatt válaszolt a "
                             "kapott gólokra — stabil fejben.")
                elif rec["avg_s"] >= 150.0:
                    body += (f" A(z) {names[side]} lassan válaszol a "
                             f"kapott gólokra (átlag {rec['avg_s']:.0f} mp) "
                             "— egy-egy kapott gól után megtorpannak.")
    except Exception:
        pass
    # Gólcsend: 8+ perces saját gól nélküli szakasz külön említést kap —
    # ott állt le a támadójáték, azt kell visszanézni.
    try:
        from .momentum import goal_droughts
        dr = goal_droughts(match)
        names = {"home": home, "away": away}
        for side in ("home", "away"):
            rec = dr[side]
            if rec["longest_s"] >= 480.0:
                m0 = int(rec["start_s"] // 60)
                m1 = int(rec["end_s"] // 60)
                body += (f" A(z) {names[side]} leghosszabb gólcsendje "
                         f"{rec['longest_s'] / 60:.0f} perc volt "
                         f"({m0}.–{m1}. perc) — érdemes visszanézni, mi "
                         "fogta meg a támadójátékot.")
    except Exception:
        pass
    # Hajrá-mérleg: szoros állásról induló hajrában ki bírta jobban.
    try:
        from .momentum import clutch_performance
        cp = clutch_performance(match)
        if cp.get("available") and cp.get("close"):
            names = {"home": home, "away": away}
            gh, ga = cp["home"]["goals"], cp["away"]["goals"]
            if abs(gh - ga) >= 2:
                winner = "home" if gh > ga else "away"
                mins = int(cp["window_s"] // 60)
                body += (f" A szoros hajrát (utolsó {mins} perc) a(z) "
                         f"{names[winner]} nyerte {max(gh, ga)}–"
                         f"{min(gh, ga)}-ra.")
    except Exception:
        pass
    # A meccs fordulópontja: a legnagyobb esély-ugrás pillanata (csak
    # érdemi ugrásnál — a sima gólváltásokat nem nevezzük fordulópontnak).
    try:
        from .momentum import win_probability
        wp = win_probability(match)
        tp = wp.get("turning_point")
        if tp is not None and abs(tp["to_p"] - tp["from_p"]) >= 0.2:
            mins = int(tp["t_s"] // 60)
            body += (f" A meccs fordulópontja a {mins}. perc körül volt "
                     f"(a hazai esély {100 * tp['from_p']:.0f}%-ról "
                     f"{100 * tp['to_p']:.0f}%-ra ugrott).")
    except Exception:
        pass
    # Nagy fordítás: 3+ gólos hátrányból vezetésbe — külön említés és
    # kiemelés (mentális erő / a másik oldalon elengedett előny).
    if prog:
        names = {"home": home, "away": away}
        for side in ("home", "away"):
            cb = prog.get("comeback", {}).get(side, 0)
            if cb >= 3:
                other = names["away" if side == "home" else "home"]
                body += (f" A(z) {names[side]} {cb} gólos hátrányból "
                         "fordított.")
                highlights.append(
                    f"{other}: {cb} gólos előny ment el — nézd vissza, hol "
                    "fordult a meccs (időkérés, cserék, védekezés-váltás).")
    # Elengedett vezetés fordulás nélkül (a végén döntetlen, vagy a
    # hátrányból egalizáló csapat nem került vezetésbe) — a fordítás-ág
    # ezt nem említi, pedig edzői tanulság.
    try:
        from .momentum import lead_protection
        lp = lead_protection(match)
        names = {"home": home, "away": away}
        for side in ("home", "away"):
            rec_lp = lp[side]
            other_cb = (prog or {}).get("comeback", {}).get(
                "away" if side == "home" else "home", 0)
            if rec_lp["blown"] and other_cb < 3:
                vege = ("döntetlen lett a vége"
                        if rec_lp["final_margin"] == 0
                        else "a végén mégis kikapott")
                body += (f" A(z) {names[side]} {rec_lp['max_lead']} gólos "
                         f"vezetést engedett el — {vege}.")
    except Exception:
        pass
    return {"title": "Sorozatok", "body": body.strip()}, highlights


def _story_section(match: Match, home: str, away: str) -> dict | None:
    """A meccs története egy bekezdésben: eredmény, félidő, fordulópont,
    legnagyobb előny — a meglévő rétegek számaiból, mondatokban."""
    from .momentum import halftime_score, score_progression, win_probability
    prog = score_progression(match)
    gh, ga = prog["final"]
    if gh + ga < 2:
        return None
    if gh > ga:
        opener = (f"A(z) {home} nyert {gh}–{ga}-ra a(z) {away} ellen")
    elif ga > gh:
        opener = (f"A(z) {away} nyert {ga}–{gh}-ra a(z) {home} ellen")
    else:
        opener = f"Döntetlen: {gh}–{ga}"
    body = opener
    try:
        hs = halftime_score(match)
        if hs is not None:
            body += f" (félidőben {hs['home']}–{hs['away']})"
    except Exception:
        pass
    body += "."
    # A nyitány: ki szerezte az első gólt és milyen volt a korai állás.
    try:
        from .momentum import opening_profile
        op = opening_profile(match)
        oh = op["home"]
        if oh["scores_first"] is not None and oh["early_goals_seen"] >= 4:
            first_name = home if oh["scores_first"] else away
            d_open = oh["early_for"] - oh["early_against"]
            if abs(d_open) >= 2:
                hi_o = max(oh["early_for"], oh["early_against"])
                lo_o = min(oh["early_for"], oh["early_against"])
                lead_name = home if d_open > 0 else away
                body += (f" A(z) {first_name} szerezte az első gólt, és a "
                         f"korai szakasz a(z) {lead_name} kezében volt "
                         f"({hi_o}–{lo_o}).")
            else:
                body += (f" A(z) {first_name} szerezte az első gólt, de a "
                         "nyitány kiegyenlített volt.")
    except Exception:
        pass
    bl = prog.get("biggest_lead") or {}
    top_lead = max(bl.get("home", 0), bl.get("away", 0))
    if top_lead >= 3:
        lead_name = home if bl.get("home", 0) >= bl.get("away", 0) else away
        body += (f" A legnagyobb különbség {top_lead} gól volt "
                 f"({lead_name}).")
    if prog.get("lead_changes", 0) >= 3:
        body += (f" A vezetés {prog['lead_changes']}× cserélt gazdát — "
                 "végig szoros meccs volt.")
    try:
        tp = win_probability(match).get("turning_point")
        if tp is not None:
            body += (f" A fordulópont a {int(tp['t_s'] // 60)}. perc "
                     "környékén jött, ekkor billent el a győzelmi "
                     "esély.")
            # A billenés oka: ha egy gól-sorozat hozta, elmondjuk.
            try:
                from .momentum import annotate_runs
                fps = match.meta.fps if match.meta.fps > 0 else 25.0
                tp_frame = tp["t_s"] * fps
                for r_ in annotate_runs(match):
                    if r_["start_frame"] <= tp_frame <= r_["end_frame"]:
                        cause = (f" ({r_['context'][0]})"
                                 if r_.get("context") else "")
                        body += (f" A billenést egy {r_['length']} gólos "
                                 f"sorozat hozta{cause}.")
                        break
            except Exception:
                pass
    except Exception:
        pass
    # A szünet utáni kezdés: ha az első 5 perc egyoldalú volt (2+ gól
    # különbség), a történet is elmondja, ki ütött először.
    try:
        from .halftime import second_half_start
        shs = second_half_start(match)
        if shs is not None and abs(shs["home"] - shs["away"]) >= 2:
            first_name = home if shs["home"] > shs["away"] else away
            hi = max(shs["home"], shs["away"])
            lo = min(shs["home"], shs["away"])
            body += (f" A második félidőt a(z) {first_name} kezdte "
                     f"jobban ({hi}–{lo} az első öt percben).")
    except Exception:
        pass
    # A meccs embere: a legeredményesebb azonosított lövő (3+ gólnál).
    try:
        from .xg import match_xg
        best_sc = None
        for rec in match_xg(match).get("shooters", []):
            if best_sc is None or rec["goals"] > best_sc["goals"]:
                best_sc = rec
        if best_sc is not None and best_sc["goals"] >= 3:
            name_sc = home if best_sc["team"] == "home" else away
            body += (f" A meccs embere a(z) {best_sc['player_id']}. "
                     f"játékos ({name_sc}) {best_sc['goals']} góllal.")
    except Exception:
        pass
    return {"title": "A meccs története", "body": body}


def coach_summary(match: Match) -> dict:
    """A meccs automatikus edzői összefoglalója.

    Visszatérés: {"sections": [{"title", "body"}, ...],
                  "highlights": ["figyelemfelhívó mondat", ...]}
    — a sections a leíró rész, a highlights a "mire nézz rá" lista.

    Az összefoglaló több tucat réteget olvas, azok pedig ugyanazokat az
    alap-méréseket kérik újra és újra — ezért a futás egy
    `primitive_cache` hatókörben zajlik (lásd a modult). Az eredmény
    változatlan, csak az alap-mérések futnak egyszer.
    """
    from .primitive_cache import primitive_cache
    with primitive_cache(match):
        return _coach_summary_cached(match)


def _coach_summary_cached(match: Match) -> dict:
    """Az összefoglaló tényleges felépítése (lásd `coach_summary`)."""
    home, away = _team_names(match)
    sections: list[dict] = []
    highlights: list[str] = []

    for build in (_story_section, _events_section, _xg_section,
                  _style_section):
        try:
            s = build(match, home, away)
            if s:
                sections.append(s)
        except Exception:
            pass  # egy hiányzó elemzés ne vigye el az egész összefoglalót

    # Támadás-hatékonyság: melyik támadás-típus mennyire eredményes.
    try:
        from .attack_types import attack_efficiency
        eff = attack_efficiency(match)
        bits = []
        for side, name in (("home", home), ("away", away)):
            best = None
            for typ, rec in eff[side].items():
                if rec["attacks"] >= 3 and (best is None
                                            or rec["goal_pct"] > best[1]["goal_pct"]):
                    best = (typ, rec)
            if best:
                bits.append(f"{name} leghatékonyabb támadás-típusa a "
                            f"{best[0]} ({best[1]['goals']}/{best[1]['attacks']} "
                            f"gól, {best[1]['goal_pct']:.0f}%)")
        if bits:
            sections.append({"title": "Támadás-hatékonyság",
                             "body": ("; ".join(bits) + ".").capitalize()})
    except Exception:
        pass

    try:
        s, hl = _defense_section(match, home, away)
        if s:
            sections.append(s)
        highlights.extend(hl)
    except Exception:
        pass

    try:
        from .substitutions import substitution_impact
        si = substitution_impact(match)
        parts = []
        for side, name in (("home", home), ("away", away)):
            rec = si["teams"][side]
            if not rec["rotations"]:
                continue
            parts.append(
                f"a(z) {name} {rec['rotations']} cserehullámot futott; a "
                f"cseréket követő másfél percben {rec['goals_for_after']} "
                f"dobott és {rec['goals_against_after']} kapott gól")
        if parts:
            sections.append({"title": "Cserék",
                             "body": ("; ".join(parts) + ".").capitalize()})
    except Exception:
        pass

    try:
        from .stoppages import timeout_effects
        stops = timeout_effects(match)
        touts = [s_ for s_ in stops if s_["kind"] == "időkérés"]
        if touts:
            names = {"home": home, "away": away}
            bits = []
            for s_ in touts:
                who = names.get(s_["likely_team"] or "", "")
                bit = (f"{s_['duration_s']:.0f} mp"
                       + (f" (valószínűleg {who})" if who else ""))
                # Működött-e: a kapott gólok üteme az időkérés előtt/után.
                if s_["verdict"]:
                    bit += (f" — {s_['verdict']} "
                            f"({s_['conceded_before']} kapott gól előtte, "
                            f"{s_['conceded_after']} utána)")
                bits.append(bit)
            sections.append({
                "title": "Időkérések",
                "body": (f"{len(touts)} időkérés-szerű játékmegszakítás: "
                         + "; ".join(bits) + ". A megszakítás körüli "
                         "jeleneteket a sztori-sávról érdemes visszanézni.")})
    except Exception:
        pass

    try:
        s, hl = _intensity_section(match, home, away)
        if s:
            sections.append(s)
        highlights.extend(hl)
    except Exception:
        pass

    # Edzés-fókusz: a meccs gyengeségeiből következő gyakorlás (top 3).
    try:
        from .training import training_focus
        tf = training_focus(match)
        parts = []
        for side, name in (("home", home), ("away", away)):
            items = tf.get(side) or []
            if items:
                parts.append(f"{name}: " + "; ".join(
                    f"{it['title'].lower()} ({it['why']})"
                    for it in items[:3]))
        if parts:
            sections.append({
                "title": "Edzés-fókusz a meccs alapján",
                "body": ". ".join(parts) + "."})
    except Exception:
        pass

    try:
        s = _players_section(match, home, away)
        if s:
            sections.append(s)
    except Exception:
        pass

    try:
        s = _goalkeepers_section(match, home, away)
        if s:
            sections.append(s)
    except Exception:
        pass

    try:
        s, hl = _momentum_section(match, home, away)
        if s:
            sections.append(s)
        highlights.extend(hl)
    except Exception:
        pass

    # Szabály-értő réteg: kiállítások (emberhátrány), hétméteresek,
    # passzív-játék kockázat — csak ha van mit mondani.
    try:
        from .rules import detect_powerplay, detect_seven_meters, passive_play_risks
        names = {"home": home, "away": away}
        pps = detect_powerplay(match)
        sevens = detect_seven_meters(match)
        passive = passive_play_risks(match)
        parts: list[str] = []
        if pps:
            per: dict[str, float] = {}
            for w in pps:
                per[w["team_down"]] = per.get(w["team_down"], 0.0) + w["duration_s"]
            parts.append("emberhátrány: " + "; ".join(
                f"a(z) {names.get(t, t)} összesen {s_:.0f} mp-et játszott "
                "kevesebb emberrel" for t, s_ in per.items()))
            # Ki ült ki és ki harcolta ki — ha a trackekből kiolvasható.
            from .rules import suspended_players, suspension_earners
            sp = suspended_players(match)
            for t in ("home", "away"):
                who = [f"{e['player_id']}. játékos"
                       + (f" ({e['suspensions']}×)"
                          if e["suspensions"] > 1 else "")
                       for e in (sp.get(t) or [])]
                if who:
                    parts.append(f"a(z) {names[t]} kiülői: "
                                 + ", ".join(who))
            se = suspension_earners(match)
            for t in ("home", "away"):
                el = se.get(t) or []
                if el and el[0]["earned"] >= 2:
                    parts.append(
                        f"a(z) {names[t]} kiállításait a(z) "
                        f"{el[0]['player_id']}. játékos harcolta ki "
                        f"({el[0]['earned']}×)")
        if sevens:
            from .rules import seven_meter_summary
            summ7 = seven_meter_summary(match)
            bits = []
            for t in ("home", "away"):
                rec7 = summ7[t]
                if not rec7["attempts"]:
                    continue
                extra = []
                if rec7["goals"]:
                    extra.append(f"{rec7['goals']} gól")
                if rec7["saved"]:
                    extra.append(f"{rec7['saved']} védés")
                if rec7["missed"]:
                    extra.append(f"{rec7['missed']} kihagyva")
                bits.append(f"{names.get(t, t)} {rec7['attempts']}"
                            + (f" ({', '.join(extra)})" if extra else ""))
            parts.append("hétméteres: " + ", ".join(bits))
        # Emberelőny-hatékonyság: mire váltotta a csapat a kiállításokat.
        from .rules import powerplay_efficiency
        eff = powerplay_efficiency(match)
        for key, name in (("home", home), ("away", away)):
            rec = eff.get(key)
            if not rec or not rec["pp_shots"]:
                continue
            parts.append(
                f"a(z) {name} emberelőnyben {rec['pp_goals']} gólt dobott "
                f"{rec['pp_shots']} kapura tartó lövésből "
                f"({rec['pp_eff_pct']:.0f}%)")
            if (rec["pp_shots"] >= 3 and rec["eq_shots"] >= 3
                    and rec["pp_eff_pct"] < rec["eq_eff_pct"]):
                highlights.append(
                    f"{name}: az emberelőny nem hozott jobb gólarányt "
                    f"({rec['pp_eff_pct']:.0f}% vs {rec['eq_eff_pct']:.0f}% "
                    "egyenlő létszámnál) — érdemes a létszámfölényes "
                    "figurákat gyakorolni.")
        if parts:
            sections.append({"title": "Kiállítások és hétméteresek",
                             "body": (" · ".join(parts)).capitalize() + "."})
        if passive:
            highlights.append(
                f"{len(passive)} hosszú, lövés nélküli felállt támadás volt "
                "(passzív-játék kockázat) — nézd vissza, hol akadt el a játék.")
    except Exception:
        pass

    # Felállások: a becsült posztok csapatonként egy-egy mondatban.
    try:
        from .roles import estimate_positions
        est_cs = estimate_positions(match)
        names_lu = {"home": home, "away": away}
        order_lu = ["irányító", "átlövő", "beálló", "szélső"]
        parts_lu = []
        for side in ("home", "away"):
            by_post: dict = {}
            for tid, r_ in sorted(est_cs.get(side, {}).items()):
                by_post.setdefault(r_["poszt"], []).append(f"{tid}.")
            if by_post:
                inner = " · ".join(f"{p_}: {', '.join(by_post[p_])}"
                                   for p_ in order_lu if p_ in by_post)
                parts_lu.append(f"{names_lu[side]} — {inner}")
        if parts_lu:
            sections.append({
                "title": "Felállások (becsült posztok)",
                "body": "; ".join(parts_lu) + ".",
            })
    except Exception:
        pass

    # Kulcsemberek: kinél dőlt el a meccs — szereponként egy név.
    try:
        from .scouting import match_key_players
        kp = match_key_players(match)
        names_kp = {"home": home, "away": away}
        parts_kp = []
        for side in ("home", "away"):
            items = kp.get(side) or []
            if items:
                inner = ", ".join(
                    f"{it['role'].lower()}: {it['player_id']}. játékos "
                    f"({it['detail']})" for it in items)
                parts_kp.append(f"{names_kp[side]} — {inner}")
        if parts_kp:
            sections.append({"title": "Kulcsemberek",
                             "body": "; ".join(parts_kp) + "."})
    except Exception:
        pass

    # Meccs-tempó: támadás/perc — a meccs karaktere egy számban.
    try:
        from .attack_types import match_pace
        pc = match_pace(match)
        if pc.get("available"):
            flavor = {"gyors": "oda-vissza játék — a kontra-védekezés és "
                               "a cserék frissessége döntött",
                      "lassú": "türelmes építkezés — a felállt fal elleni "
                               "megoldások döntöttek",
                      "közepes": "kiegyensúlyozott tempó"}[pc["label"]]
            body_pc = (f"{pc['label'].capitalize()} tempójú meccs: "
                       f"{pc['per_min']:.1f} támadás/perc "
                       f"({pc['home_attacks']} + {pc['away_attacks']} "
                       f"támadás {pc['duration_min']:.0f} perc alatt) — "
                       + flavor + ".")
            # Félidei bontás: érdemi (20%+) tempó-változásnál mondjuk el.
            hv = pc.get("halves")
            if hv and hv["first_per_min"] > 0:
                change = (hv["second_per_min"] - hv["first_per_min"]) \
                    / hv["first_per_min"]
                if change <= -0.2:
                    body_pc += (f" A tempó a második félidőben esett: "
                                f"{hv['first_per_min']:.1f} → "
                                f"{hv['second_per_min']:.1f} támadás/perc.")
                elif change >= 0.2:
                    body_pc += (f" A meccs a második félidőben pörgött "
                                f"fel: {hv['first_per_min']:.1f} → "
                                f"{hv['second_per_min']:.1f} támadás/perc.")
            sections.append({"title": "Meccs-tempó", "body": body_pc})
    except Exception:
        pass

    # 7 a 6 elleni (üres kapus) szakaszok — ha voltak, külön szekció + jelzés.
    try:
        from .goalkeeper import detect_empty_net
        windows = detect_empty_net(match)
        if windows:
            per_team: dict[str, float] = {}
            for w in windows:
                per_team[w["team"]] = per_team.get(w["team"], 0.0) + w["duration_s"]
            names = {"home": home, "away": away}
            parts = [f"a(z) {names.get(t, t)} összesen "
                     f"{s_:.0f} másodpercet játszott lehozott kapussal"
                     for t, s_ in per_team.items()]
            body = ("7 a 6 elleni játék: " + "; ".join(parts) +
                    f" ({len(windows)} szakasz).")
            # Az ára: üres kapura kapott gólok (ha voltak).
            try:
                from .goalkeeper import empty_net_goals
                eng = empty_net_goals(match)
                gains = [f"a(z) {names.get(t, t)} {r['scored_7v6']} "
                         "gólt dobott 7 a 6-ban"
                         for t, r in eng.items() if r.get("scored_7v6")]
                if gains:
                    body += " Hozama: " + "; ".join(gains) + "."
                costs = [f"a(z) {names.get(t, t)} {r['conceded_empty']} "
                         "gólt kapott üres kapura"
                         for t, r in eng.items() if r["conceded_empty"]]
                if costs:
                    body += " Az ára: " + "; ".join(costs) + "."
                # Ítélet: megérte-e a vállalás (hozam − ár csapatonként).
                for t, r in eng.items():
                    net = r.get("scored_7v6", 0) - r["conceded_empty"]
                    if not (r.get("scored_7v6") or r["conceded_empty"]):
                        continue
                    if net >= 2:
                        body += (f" A(z) {names.get(t, t)} vállalása "
                                 f"összességében megérte ({net:+d} gól).")
                    elif net <= -2:
                        body += (f" A(z) {names.get(t, t)} vállalása "
                                 f"ráfizetés volt ({net:+d} gól) — "
                                 "érdemes újragondolni, mikor jön a "
                                 "hetedik mezőnyjátékos.")
            except Exception:
                pass
            sections.append({
                "title": "Hetedik mezőnyjátékos",
                "body": body,
            })
            highlights.append(
                "Üres kapu ellen a labdaszerzés utáni azonnali kapura dobás "
                "gólt érhet — gyakorold a hosszú indítást.")
    except Exception:
        pass

    # Mezszám-lefedettség: ha alacsony, maga az összefoglaló hívja fel rá a
    # figyelmet — a játékos-mondatok mezszámmal sokkal használhatóbbak.
    try:
        jersey_of = _jersey_of_track(match)
        team_of = _team_of_track(match)
        field_tracks = [t for t in team_of
                        if team_of[t] in (Team.HOME, Team.AWAY)]
        if field_tracks:
            cov = 100.0 * sum(1 for t in field_tracks if t in jersey_of) / len(field_tracks)
            if cov < 50.0:
                highlights.append(
                    "A játékosok többségéhez még nincs mezszám rendelve — a "
                    "meccs-nézetben egy kattintással pótolható, és utána a "
                    "szezon-követés is működik.")
    except Exception:
        pass

    # A szakaszok MONDATOKRA bontva is elmennek. A "Játékkép és tempó"
    # szakasz a rétegekkel négyezer karakteres, negyvenmondatos
    # bekezdéssé nőtt — úgy olvashatatlan. A `body` változatlan marad
    # (a meglévő fogyasztók miatt), a felületek a `lines`-ból tudnak
    # felsorolást építeni.
    for sec in sections:
        sec["lines"] = split_sentences(sec.get("body", ""))
    return {"sections": sections, "highlights": highlights}


# Mondathatár: pont/felkiáltó/kérdőjel UTÁN álló szóköz, amit nagybetű
# vagy szám követ. A tizedes-pont (pl. "3.9 m") így nem téveszt meg,
# mert utána nincs szóköz.
_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÖŐÚÜŰ0-9])")


def split_sentences(body: str) -> list[str]:
    """Egy összefoglaló-szakasz szövege mondatokra bontva.

    Nem nyelvtani elemzés, hanem megjelenítési segédlet: a felületek
    ebből tudnak felsorolást építeni a tömbszerű bekezdés helyett. Ha
    a bontás valahol téved, a szöveg akkor is hiánytalanul megvan —
    csak a tördelés lesz más.
    """
    text = (body or "").strip()
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT.split(text)
            if part.strip()]


def coach_summary_text(match: Match) -> str:
    """Az összefoglaló sima szövegként (jelentésbe/vágólapra)."""
    data = coach_summary(match)
    lines: list[str] = []
    for s in data["sections"]:
        lines.append(f"{s['title']}: {s['body']}")
    if data["highlights"]:
        lines.append("Mire nézz rá: " + " ".join(data["highlights"]))
    return "\n".join(lines)
