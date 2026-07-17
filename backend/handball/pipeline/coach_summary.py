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
    return {"title": "Játékkép és tempó", "body": body}


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
        parts.append(sent)
    if not parts:
        return None
    return {"title": "Kapusok", "body": "; ".join(parts).capitalize() + "."}


def _momentum_section(match: Match, home: str, away: str) -> tuple[dict | None, list[str]]:
    """Gól-sorozatok: válasz nélküli szériák, játékóra-idővel, állással és
    a felismert LEHETSÉGES OKOKKAL (emberelőny, 7 a 6, védekezés-váltás,
    tempó-esés)."""
    from .momentum import annotate_runs
    runs = annotate_runs(match)
    if not runs:
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
    return {"title": "Sorozatok", "body": "; ".join(parts).capitalize() + "."}, highlights


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

    try:
        s, hl = _defense_section(match, home, away)
        if s:
            sections.append(s)
        highlights.extend(hl)
    except Exception:
        pass

    try:
        s, hl = _intensity_section(match, home, away)
        if s:
            sections.append(s)
        highlights.extend(hl)
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
