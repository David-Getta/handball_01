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
        # Leggyengébb sarok: a legalacsonyabb védés%-ú, min. 2 lövést
        # kapott zóna — konkrét támadási irány az ellenfélnek.
        zsp = rec.get("zone_save_pct", {})
        otz = rec.get("on_target_zones", {})
        cand = [(z, p) for z, p in zsp.items() if otz.get(z, 0) >= 2]
        if cand:
            z, p = min(cand, key=lambda kv: kv[1])
            sent += f"; leggyengébb zónája: {z} ({p:.0f}% védés)"
        parts.append(sent)
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


def coach_summary(match: Match) -> dict:
    """A meccs automatikus edzői összefoglalója.

    Visszatérés: {"sections": [{"title", "body"}, ...],
                  "highlights": ["figyelemfelhívó mondat", ...]}
    — a sections a leíró rész, a highlights a "mire nézz rá" lista.
    """
    home, away = _team_names(match)
    sections: list[dict] = []
    highlights: list[str] = []

    for build in (_events_section, _xg_section, _style_section):
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
            sections.append({
                "title": "Hetedik mezőnyjátékos",
                "body": ("7 a 6 elleni játék: " + "; ".join(parts) +
                         f" ({len(windows)} szakasz)."),
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
