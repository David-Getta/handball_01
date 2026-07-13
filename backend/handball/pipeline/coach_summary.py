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
    return {"title": "Gólok és lövések", "body": body}


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
        parts.append(f"a(z) {name} kapusára {rec['on_target']} kapura tartó "
                     f"lövés érkezett, ebből {rec['saves']} védés "
                     f"({rec['save_pct']:.0f}%)")
    if not parts:
        return None
    return {"title": "Kapusok", "body": "; ".join(parts).capitalize() + "."}


def coach_summary(match: Match) -> dict:
    """A meccs automatikus edzői összefoglalója.

    Visszatérés: {"sections": [{"title", "body"}, ...],
                  "highlights": ["figyelemfelhívó mondat", ...]}
    — a sections a leíró rész, a highlights a "mire nézz rá" lista.
    """
    home, away = _team_names(match)
    sections: list[dict] = []
    highlights: list[str] = []

    for build in (_events_section, _style_section):
        try:
            s = build(match, home, away)
            if s:
                sections.append(s)
        except Exception:
            pass  # egy hiányzó elemzés ne vigye el az egész összefoglalót

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
