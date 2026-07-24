"""Meccs utáni automatikus edzői összefoglaló — magyarul, mondatokban.

A feldolgozott meccs elemzés-eredményeiből (események, tempó, védekezési
formák, intenzitás, játékos-terhelés) rövid, emberi nyelvű összefoglalót
állít össze: mi történt, mi volt feltűnő, mire érdemes ránézni. Ez kerül
a meccs-nézet összegző paneljére és a nyomtatható jelentésbe is.

Szándékosan sablon-alapú (nem nyelvi modell): minden mondat mögött
kiszámolt szám áll, így a szöveg ellenőrizhető és determinisztikus.
"""

from __future__ import annotations

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
    """
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

    return {"sections": sections, "highlights": highlights}


def coach_summary_text(match: Match) -> str:
    """Az összefoglaló sima szövegként (jelentésbe/vágólapra)."""
    data = coach_summary(match)
    lines: list[str] = []
    for s in data["sections"]:
        lines.append(f"{s['title']}: {s['body']}")
    if data["highlights"]:
        lines.append("Mire nézz rá: " + " ".join(data["highlights"]))
    return "\n".join(lines)
