"""
[Felderítő jelentés exportja] — nyomtatható, önálló HTML a ScoutingReport-ból.

Az edző a jelentést kimenti/kinyomtatja (böngészőben Ctrl+P → PDF), és odaadja a
stábnak vagy a játékosoknak. Ezért:
- ÖNÁLLÓ fájl: minden stílus inline, nincs külső betöltés (offline is jó),
- NYOMTATÓBARÁT: világos alap, takarékos tinta, A4-re tördelve,
- edzői nyelven, magyarul — a "Hogyan játssz ellenük" kulcsokkal legelöl.

Tiszta stdlib (html.escape), függőség nélkül → egyszerűen tesztelhető.
"""

from __future__ import annotations

from html import escape

from .scouting import ScoutingReport


def _rows(items: list, empty: str) -> str:
    """Felsorolás <li>-kbe, escape-elve; üres listánál szürke tájékoztató sor."""
    if not items:
        return f'<li class="empty">{escape(empty)}</li>'
    return "".join(f"<li>{escape(str(s))}</li>" for s in items)


def _metric(label: str, value: str) -> str:
    return (f'<div class="metric"><div class="mv">{escape(value)}</div>'
            f'<div class="ml">{escape(label)}</div></div>')


def _defense_bars(dist: dict) -> str:
    """Védőforma-megoszlás vízszintes sávokkal (inline szélesség = %)."""
    if not dist:
        return '<p class="empty">Nincs elég védekező minta.</p>'
    out = []
    for label, pct in dist.items():
        p = max(0.0, min(100.0, float(pct)))
        out.append(
            f'<div class="bar-row"><span class="bar-label">{escape(str(label))}</span>'
            f'<span class="bar"><span class="bar-fill" style="width:{p:.0f}%"></span></span>'
            f'<span class="bar-pct">{p:.0f}%</span></div>')
    return "".join(out)


def _shot_zone_bars(zones: dict) -> str:
    """Lövési zónák sávokkal: zóna, lövésszám-arány, "gól/lövés" felirat."""
    if not zones:
        return '<p class="empty">Nincs elég lövés-minta.</p>'
    total = sum(int(rec.get("shots", 0)) for rec in zones.values()) or 1
    out = []
    for zone, rec in zones.items():
        shots = int(rec.get("shots", 0))
        goals = int(rec.get("goals", 0))
        p = max(0.0, min(100.0, 100.0 * shots / total))
        out.append(
            f'<div class="bar-row"><span class="bar-label">{escape(str(zone))}</span>'
            f'<span class="bar"><span class="bar-fill gold" style="width:{p:.0f}%"></span></span>'
            f'<span class="bar-pct">{goals}/{shots}</span></div>')
    return "".join(out)


def _playbook_rows(pm: dict) -> str:
    """Figura-egyezés sorai: melyik MENTETT figurát hányszor játszották."""
    matched = pm.get("matched") or {}
    total = int(pm.get("total_attacks", 0))
    unmatched = int(pm.get("unmatched", 0))
    if total == 0:
        return '<p class="empty">Nincs felismert támadás-szakasz.</p>'
    if not matched:
        return (f'<p class="empty">Egyik támadásuk sem egyezik mentett figurával '
                f'({total} támadás).</p>')
    rows = "".join(
        f'<div class="bar-row"><span class="bar-label" style="width:220px">'
        f'{escape(str(name))}</span><span class="bar-pct" style="width:auto">'
        f'{int(n)}×</span></div>'
        for name, n in matched.items())
    return rows + (f'<p class="note">{total} támadásból {unmatched} ismeretlen '
                   f'mintájú.</p>')


def _players(key_players: list) -> str:
    if not key_players:
        return '<p class="empty">Több meccs felderítése pontosítja a játékos-profilt.</p>'
    rows = []
    for p in key_players:
        rows.append(
            f'<tr><td class="pid">#{escape(str(p.get("track_id", "?")))}</td>'
            f'<td>{escape(str(p.get("role", "játékos")))}</td>'
            f'<td class="num">{escape(str(p.get("possession_frames", 0)))}</td>'
            f'<td class="num">{escape(str(p.get("distance_m", 0)))} m</td></tr>')
    return ('<table><thead><tr><th>Játékos</th><th>Szerep</th>'
            '<th class="num">Birtoklás (frame)</th><th class="num">Megtett táv</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def scouting_report_html(rep: ScoutingReport, playbook_match: dict | None = None) -> str:
    """A jelentés teljes, önálló HTML-je (nyomtatható; böngészőből PDF).

    `playbook_match` (opcionális): a mentett figurákkal való egyezés
    ({total_attacks, matched, unmatched}) — külön szakaszként kerül be.
    """
    name = escape(rep.team_name)
    matches = f"{rep.matches} meccs alapján" if rep.matches > 1 else "1 meccs alapján"

    metrics = "".join([
        _metric("Szervezett támadás", f"{rep.attack_share_pct:.0f}%"),
        _metric("Gyors indítás", f"{rep.fast_break_pct:.0f}%"),
        _metric("Átl. támadáshossz", f"{rep.avg_attack_duration_s:.1f} s"),
        _metric("Labda átlagsebesség", f"{rep.avg_ball_speed_ms:.1f} m/s"),
        _metric("Lövés / gól", f"{rep.shots} / {rep.goals}"),
        _metric("Gólarány", f"{rep.shot_efficiency_pct:.0f}%"),
        _metric("Labdaeladás", str(rep.turnovers)),
        _metric("Figurák", str(rep.num_figures)),
    ])

    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="utf-8">
<title>Felderítés — {name}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
         color: #101722; background: #fff; line-height: 1.5; }}
  .page {{ max-width: 800px; margin: 0 auto; padding: 36px 32px 48px; }}
  header {{ border-bottom: 3px solid #12988a; padding-bottom: 14px; margin-bottom: 22px; }}
  .brand {{ font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: #8492A6; }}
  h1 {{ margin: 6px 0 2px; font-size: 26px; }}
  .sub {{ color: #4A5768; font-size: 13px; }}
  h2 {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
        color: #12988a; margin: 26px 0 10px; }}
  .keys {{ border: 1.5px solid #9d7526; border-radius: 10px; padding: 14px 18px; background: #fdf9f0; }}
  .keys h2 {{ color: #9d7526; margin: 0 0 8px; }}
  ul {{ margin: 0; padding-left: 20px; }}
  li {{ margin: 4px 0; font-size: 13.5px; }}
  li.empty, p.empty {{ color: #8492A6; list-style: none; margin-left: -20px; font-size: 12.5px; }}
  p.note {{ color: #4A5768; font-size: 12px; margin: 8px 0 0; }}
  .cols {{ display: flex; gap: 22px; }}
  .col {{ flex: 1; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 14px 26px; }}
  .metric .mv {{ font-size: 20px; font-weight: 700; color: #12988a; }}
  .metric .ml {{ font-size: 11px; color: #4A5768; }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin: 5px 0; font-size: 13px; }}
  .bar-label {{ width: 120px; font-weight: 600; }}
  .bar {{ flex: 1; height: 9px; background: #edf1f6; border-radius: 5px; overflow: hidden; }}
  .bar-fill {{ display: block; height: 100%; background: #12988a; border-radius: 5px; }}
  .bar-fill.gold {{ background: #9d7526; }}
  .bar-pct {{ width: 42px; text-align: right; color: #4A5768; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e4e9f0; }}
  th {{ font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #4A5768; }}
  td.pid {{ font-weight: 700; }}
  .num {{ text-align: right; }}
  footer {{ margin-top: 34px; padding-top: 12px; border-top: 1px solid #e4e9f0;
            color: #8492A6; font-size: 11px; display: flex; justify-content: space-between; }}
  @media print {{
    .page {{ padding: 0; max-width: none; }}
    .keys {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="page">
  <header>
    <div class="brand">Sport Machine · Felderítő jelentés</div>
    <h1>{name}</h1>
    <div class="sub">{escape(matches)} · fő védekezés: <b>{escape(rep.defense_main)}</b></div>
  </header>

  <div class="keys">
    <h2>Hogyan játssz ellenük</h2>
    <ul>{_rows(rep.keys_to_game, "Kevés a minta — több meccs felderítése pontosít.")}</ul>
  </div>

  <div class="cols">
    <div class="col">
      <h2>Erősségeik</h2>
      <ul>{_rows(rep.strengths, "Nincs kiemelkedő erősség a mintában.")}</ul>
    </div>
    <div class="col">
      <h2>Gyengeségeik</h2>
      <ul>{_rows(rep.weaknesses, "Nincs kiemelkedő gyengeség a mintában.")}</ul>
    </div>
  </div>

  <h2>Mutatók</h2>
  <div class="metrics">{metrics}</div>

  <h2>Honnan lőnek (gól/lövés)</h2>
  {_shot_zone_bars(rep.shot_zones)}

  {("<h2>Ismert figuráik (a könyvtárunkból)</h2>" + _playbook_rows(playbook_match))
   if playbook_match else ""}

  <h2>Védekezésük (amikor ők védenek)</h2>
  {_defense_bars(rep.defense_distribution)}

  <h2>Kulcsjátékosaik</h2>
  {_players(rep.key_players)}

  <footer>
    <span>Készült a Sport Machine kézilabda-elemzővel</span>
    <span>Nyomtatás: Ctrl+P → Mentés PDF-ként</span>
  </footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# MECCS-JELENTÉS — a teljes meccs egyoldalas, nyomtatható összefoglalója.
# (A felderítő jelentés az ELLENFÉLRŐL szól; ez a meccsről magáról.)
# ---------------------------------------------------------------------------

def _fmt_clock(seconds: float) -> str:
    """Másodperc → 'p:mm' játékóra-formátum (pl. 83.4 → '1:23')."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def _phase_bars(phases: dict, home: str, away: str) -> str:
    """A játékfázis-megoszlás sávjai (hazai támadás / vendég támadás / átmenet)."""
    rows = []
    for key, label, gold in [("home_attack", f"{home} támadás", False),
                             ("away_attack", f"{away} támadás", False),
                             ("transition", "Átmenet (fel-/visszarendeződés)", True)]:
        pct = float(phases.get(key, 0.0))
        cls = " gold" if gold else ""
        rows.append(
            f'<div class="bar-row"><span class="bar-label">{escape(label)}</span>'
            f'<span class="bar"><span class="bar-fill{cls}" style="width:{pct:.0f}%"></span></span>'
            f'<span class="bar-pct">{pct:.0f}%</span></div>')
    return "".join(rows)


def _heatmap_svg(hm, color: str = "#12988a", width: int = 360) -> str:
    """Egy csapat-hőtérkép önálló SVG-je a jelentésbe (nincs külső függőség).

    A pálya 2:1 arányú; a cellák átlátszósága a látogatottsággal arányos.
    A `hm` a compute_team_heatmap eredménye (bins_x/bins_y/grid/total).
    """
    height = width // 2
    peak = max((v for row in hm.grid for v in row), default=0.0)
    cells = []
    if peak > 0:
        cw = width / hm.bins_x
        ch = height / hm.bins_y
        for iy, row in enumerate(hm.grid):
            for ix, v in enumerate(row):
                if v <= 0:
                    continue
                a = 0.08 + 0.72 * (v / peak)
                cells.append(
                    f'<rect x="{ix * cw:.1f}" y="{iy * ch:.1f}" '
                    f'width="{cw:.1f}" height="{ch:.1f}" fill="{color}" '
                    f'fill-opacity="{a:.2f}"/>')
    mid = width / 2
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="8" '
        f'fill="#f4f7fa" stroke="#c9d3de"/>'
        + "".join(cells) +
        f'<line x1="{mid}" y1="0" x2="{mid}" y2="{height}" stroke="#8492A6" '
        f'stroke-width="1"/>'
        f'</svg>')


def _shot_positions(match, events) -> list[tuple[float, float, str, bool]]:
    """A lövés/gól események helye (x, y méter, csapat, gól-e) — a lövő
    pozíciójából az esemény kockáján, annak híján a labdáéból."""
    by_t = {f.t: f for f in match.frames}
    out = []
    for e in events:
        typ = getattr(getattr(e, "type", None), "value", None) or \
            (e.get("type") if isinstance(e, dict) else None)
        if typ not in ("shot", "goal"):
            continue
        t = getattr(e, "t", None) if not isinstance(e, dict) else e.get("t")
        frame = by_t.get(int(t or 0))
        if frame is None:
            continue
        team = getattr(getattr(e, "team", None), "value", None) or \
            (e.get("team") if isinstance(e, dict) else "")
        pid = getattr(e, "player_id", None) if not isinstance(e, dict) \
            else e.get("player_id")
        x = y = None
        if pid is not None:
            for p in frame.players:
                if p.track_id == pid:
                    x, y = p.x, p.y
                    break
        if x is None and frame.ball is not None:
            x, y = frame.ball.x, frame.ball.y
        if x is None:
            continue
        out.append((x, y, str(team), typ == "goal"))
    return out


def _shot_map_svg(shots, width: int = 480) -> str:
    """Lövéstérkép-SVG a jelentésbe: pálya + lövés-pontok (gól = arany
    körvonal, kimaradt = halványabb), a csapatok a jelentés színeivel."""
    height = width // 2
    sx, sy = width / 40.0, height / 20.0
    colors = {"home": "#2f6fb2", "away": "#b2453a"}
    dots = []
    for (x, y, team, goal) in shots:
        c = colors.get(team, "#8492A6")
        extra = ' stroke="#9d7526" stroke-width="2.5"' if goal else ""
        dots.append(
            f'<circle cx="{x * sx:.1f}" cy="{y * sy:.1f}" r="5" fill="{c}" '
            f'fill-opacity="{1.0 if goal else 0.45}"{extra}/>')
    mid = width / 2
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="8" '
        f'fill="#f4f7fa" stroke="#c9d3de"/>'
        f'<line x1="{mid}" y1="0" x2="{mid}" y2="{height}" stroke="#8492A6" '
        f'stroke-width="1"/>' + "".join(dots) + "</svg>")


def _intensity_svg(windows, total_frames: int, fps: float,
                   width: int = 720, height: int = 150) -> str:
    """Tempó-alakulás SVG: a két csapat átlagsebessége idő-ablakonként."""
    if len(windows) < 2 or total_frames < 2:
        return ""
    pad_l, pad_r, pad_t, pad_b = 30, 10, 8, 22
    peak = max(max(w["home_avg_ms"], w["away_avg_ms"]) for w in windows)
    peak = peak * 1.15 if peak > 0 else 1.0

    def x(frame):
        return pad_l + (width - pad_l - pad_r) * frame / (total_frames - 1)

    def y(ms):
        return height - pad_b - (height - pad_t - pad_b) * ms / peak

    def center(i):
        nxt = windows[i + 1]["start_frame"] if i + 1 < len(windows) else total_frames
        return (windows[i]["start_frame"] + nxt) / 2

    parts = []
    step = 0.5 if peak <= 2 else 1.0
    v = 0.0
    while v <= peak:
        parts.append(f'<line x1="{pad_l}" y1="{y(v):.1f}" x2="{width - pad_r}" '
                     f'y2="{y(v):.1f}" stroke="#e4e9f0" stroke-width="1"/>'
                     f'<text x="4" y="{y(v) + 3:.1f}" font-size="9" '
                     f'fill="#8492A6">{v:g}</text>')
        v += step
    dur_min = total_frames / fps / 60.0
    parts.append(f'<text x="{pad_l}" y="{height - 6}" font-size="9" '
                 f'fill="#8492A6">0\'</text>'
                 f'<text x="{width - pad_r - 16}" y="{height - 6}" font-size="9" '
                 f'fill="#8492A6">{dur_min:.0f}\'</text>')
    for key, color in (("home_avg_ms", "#2f6fb2"), ("away_avg_ms", "#b2453a")):
        pts = " ".join(f"{x(center(i)):.1f},{y(w[key]):.1f}"
                       for i, w in enumerate(windows))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" '
                     f'stroke-width="2"/>')
    return (f'<svg viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(parts) + "</svg>")


def _pass_pairs(match, events, team_value: str, top: int = 5):
    """Egy csapat passz-összegzése: (összes passz, top párok listája
    [(A-label, B-label, darab), ...]) — mezszámmal, ha ismert."""
    jersey = {}
    for fr in match.frames:
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    def label(tid):
        j = jersey.get(tid)
        return f"#{j}" if j is not None else f"id {tid}"

    pairs: dict[tuple, int] = {}
    total = 0
    for e in events:
        typ = getattr(getattr(e, "type", None), "value", None) or \
            (e.get("type") if isinstance(e, dict) else None)
        team = getattr(getattr(e, "team", None), "value", None) or \
            (e.get("team") if isinstance(e, dict) else "")
        if typ != "pass" or team != team_value:
            continue
        pid = getattr(e, "player_id", None) if not isinstance(e, dict) \
            else e.get("player_id")
        detail = (getattr(e, "detail", None) if not isinstance(e, dict)
                  else e.get("detail")) or {}
        rid = detail.get("receiver_id")
        if pid is None or rid is None or pid == rid:
            continue
        total += 1
        key = (min(pid, rid), max(pid, rid))
        pairs[key] = pairs.get(key, 0) + 1
    ranked = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return total, [(label(a), label(b), n) for (a, b), n in ranked]


def match_report_html(match, tactics: dict, events: list, quality: dict | None,
                      heatmaps: dict | None = None,
                      player_stats: dict | None = None,
                      notes: list | None = None) -> str:
    """A meccs egyoldalas edzői jelentése (önálló HTML; böngészőből PDF).

    Bemenetek: a Match objektum + a taktikai profil (team_style_profile),
    a felismert események (detect_events), a minőség-önellenőrzés
    (compute_quality_report, lehet None), opcionálisan a csapat-hőtérképek
    ({"home": Heatmap, "away": Heatmap}), a játékos-statisztikák
    (compute_player_stats — terhelés-tábla) és az edzői jegyzetek.
    Minden szakasz hiányzó adatnál is értelmes szöveget ad — a jelentés
    sosem "törik el".
    """
    meta = match.meta
    home, away = escape(meta.home_team), escape(meta.away_team)
    fps = meta.fps if meta.fps > 0 else 25.0
    dur_s = len(match.frames) / fps

    # Esemény-összesítés csapatonként (gól/lövés/labdaeladás).
    def _count(team_value: str, type_value: str) -> int:
        n = 0
        for e in events:
            team = getattr(e.team, "value", e.team)
            typ = getattr(e.type, "value", e.type)
            if team == team_value and typ == type_value:
                n += 1
        return n

    goals_h, goals_a = _count("home", "goal"), _count("away", "goal")
    shots_h, shots_a = _count("home", "shot"), _count("away", "shot")
    to_h, to_a = _count("home", "turnover"), _count("away", "turnover")

    tempo = tactics.get("tempo", {}) if isinstance(tactics, dict) else {}
    phases = tactics.get("phase_percentages", {}) if isinstance(tactics, dict) else {}
    defense = tactics.get("defense_formations", {}) if isinstance(tactics, dict) else {}

    metrics = "".join([
        _metric("Elemzett játékidő", f"{dur_s / 60:.1f} perc"),
        _metric("Támadások", str(tempo.get("possessions", "—"))),
        _metric("Átl. támadáshossz", f"{tempo.get('avg_attack_duration_s', 0):.1f} s"),
        _metric("Labda átlagsebesség", f"{tempo.get('avg_ball_speed_ms', 0):.1f} m/s"),
        _metric("Átmenet-arány", f"{tempo.get('transition_pct', 0):.0f}%"),
    ])

    # Gól-idővonal: minden gól játékidővel, csapat szerint (a lényeg egy pillantásra).
    goal_rows = []
    for e in events:
        typ = getattr(e.type, "value", e.type)
        if typ != "goal":
            continue
        team = getattr(e.team, "value", e.team)
        name = meta.home_team if team == "home" else meta.away_team
        goal_rows.append(
            f"<li><b>{_fmt_clock(e.t / fps)}</b> — GÓL · {escape(name)}</li>")
    goals_html = ("<ul>" + "".join(goal_rows) + "</ul>") if goal_rows else \
        '<p class="empty">Nincs felismert gól az elemzett szakaszban.</p>'

    # Csapat-hőtérképek (ha vannak): hol tartózkodtak a játékosok.
    hm_html = ""
    if heatmaps:
        cols = []
        for key, color, name in [("home", "#2f6fb2", meta.home_team),
                                 ("away", "#b2453a", meta.away_team)]:
            hm = heatmaps.get(key)
            if hm is None:
                continue
            cols.append(f'<div class="col" style="text-align:center">'
                        f'{_heatmap_svg(hm, color)}'
                        f'<div class="ml" style="margin-top:4px">{escape(name)}</div>'
                        f'</div>')
        if cols:
            hm_html = ('<h2>Területi lefedettség (hőtérkép)</h2>'
                       '<div class="cols">' + "".join(cols) + "</div>")

    # Játékos-terhelés (ha van): a legtöbbet dolgozó játékosok táblája.
    load_html = ""
    if player_stats:
        team_of: dict = {}
        jersey_of: dict = {}
        for fr in match.frames:
            for p in fr.players:
                team_of.setdefault(p.track_id, getattr(p.team, "value", p.team))
                if p.jersey_number is not None:
                    jersey_of.setdefault(p.track_id, p.jersey_number)
        ranked = sorted(player_stats.items(),
                        key=lambda kv: kv[1].distance_m, reverse=True)[:10]
        rows = []
        for tid, s in ranked:
            name = meta.home_team if team_of.get(tid) == "home" else meta.away_team
            jersey = jersey_of.get(tid)
            label = f"#{jersey}" if jersey is not None else f"id {tid}"
            rows.append(
                f"<tr><td>{escape(label)}</td><td>{escape(name)}</td>"
                f'<td class="num">{s.distance_m:.0f} m</td>'
                f'<td class="num">{s.top_speed_ms * 3.6:.1f}</td>'
                f'<td class="num">{s.sprint_count}</td></tr>')
        if rows:
            load_html = ('<h2>Játékos-terhelés (top 10 táv szerint)</h2>'
                         '<table><tr><th>Játékos</th><th>Csapat</th>'
                         '<th class="num">Táv</th><th class="num">Max km/h</th>'
                         '<th class="num">Sprint</th></tr>' + "".join(rows)
                         + "</table>")

    # Lövéstérkép (ha van lövés/gól esemény): honnan lőttek és mi lett belőle.
    shots_html = ""
    try:
        shots = _shot_positions(match, events)
        if shots:
            shots_html = ('<h2>Lövéstérkép</h2>'
                          '<div style="text-align:center">'
                          + _shot_map_svg(shots) +
                          '<p class="note">arany körvonal = gól · halvány = '
                          'kimaradt lövés · kék = ' + home + ' · piros = '
                          + away + '</p></div>')
    except Exception:
        pass  # a jelentés lövéstérkép nélkül is teljes

    # Tempó-alakulás (fáradás): csapatonkénti átlagsebesség idő-ablakonként.
    intensity_html = ""
    try:
        from .stats import compute_intensity_timeline
        windows = compute_intensity_timeline(match)
        svg = _intensity_svg(windows, len(match.frames), fps)
        if svg:
            intensity_html = ('<h2>Tempó-alakulás (fáradás)</h2>' + svg +
                              '<p class="note">átlagos mozgás-sebesség (m/s) '
                              'idő-ablakonként · kék = ' + home + ' · piros = '
                              + away + '</p>')
    except Exception:
        pass

    # Passz-kapcsolatok: csapatonként a legerősebb párok.
    passes_html = ""
    try:
        cols = []
        for team_value, name in (("home", meta.home_team),
                                 ("away", meta.away_team)):
            total, ranked = _pass_pairs(match, events, team_value)
            if total == 0:
                continue
            rows = "".join(
                f'<tr><td>{escape(a)} ↔ {escape(b)}</td>'
                f'<td class="num">{n}×</td></tr>' for a, b, n in ranked)
            cols.append(f'<div class="col"><b>{escape(name)}</b> '
                        f'({total} passz)<table>{rows}</table></div>')
        if cols:
            passes_html = ('<h2>Legerősebb passz-kapcsolatok</h2>'
                           '<div class="cols">' + "".join(cols) + "</div>")
    except Exception:
        pass

    # Edzői jegyzetek (ha vannak): időbélyeggel, idő szerint rendezve.
    notes_html = ""
    if notes:
        items = sorted(notes, key=lambda n: n.get("frame", 0))
        lis = "".join(
            f"<li><b>{_fmt_clock(n.get('frame', 0) / fps)}</b> — "
            f"{escape(str(n.get('text', '')))}</li>" for n in items)
        notes_html = "<h2>Edzői jegyzetek</h2><ul>" + lis + "</ul>"

    # Minőség-önellenőrzés (ha van): pontszám + figyelmeztetések.
    q_html = ""
    if quality:
        warns = quality.get("warnings") or []
        w_html = ("<ul>" + "".join(f"<li>{escape(str(w))}</li>" for w in warns) + "</ul>") \
            if warns else '<p class="note">Nincs figyelmeztetés — az elemzés megbízható.</p>'
        ball_cov = "{:.0f}%".format(quality.get("ball_coverage_pct", 0))
        measured = "{:.1f}".format(quality.get("avg_measured_players", 0))
        q_html = ('<h2>Elemzés megbízhatósága</h2><div class="metrics">'
                  + _metric("Minőség-pontszám", str(quality.get("score", "—")) + "/100")
                  + _metric("Labda-lefedettség", ball_cov)
                  + _metric("Mért játékos/kocka", measured)
                  + "</div>" + w_html)

    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="utf-8">
<title>Meccsjelentés — {home} vs {away}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
         color: #101722; background: #fff; line-height: 1.5; }}
  .page {{ max-width: 800px; margin: 0 auto; padding: 36px 32px 48px; }}
  header {{ border-bottom: 3px solid #12988a; padding-bottom: 14px; margin-bottom: 22px; }}
  .brand {{ font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: #8492A6; }}
  h1 {{ margin: 6px 0 2px; font-size: 26px; }}
  .sub {{ color: #4A5768; font-size: 13px; }}
  h2 {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
        color: #12988a; margin: 26px 0 10px; }}
  ul {{ margin: 0; padding-left: 20px; }}
  li {{ margin: 4px 0; font-size: 13.5px; }}
  p.empty {{ color: #8492A6; font-size: 12.5px; }}
  p.note {{ color: #4A5768; font-size: 12px; margin: 8px 0 0; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 14px 26px; }}
  .metric .mv {{ font-size: 20px; font-weight: 700; color: #12988a; }}
  .metric .ml {{ font-size: 11px; color: #4A5768; }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin: 5px 0; font-size: 13px; }}
  .bar-label {{ width: 210px; font-weight: 600; }}
  .bar {{ flex: 1; height: 9px; background: #edf1f6; border-radius: 5px; overflow: hidden; }}
  .bar-fill {{ display: block; height: 100%; background: #12988a; border-radius: 5px; }}
  .bar-fill.gold {{ background: #9d7526; }}
  .bar-pct {{ width: 42px; text-align: right; color: #4A5768; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e4e9f0; }}
  th {{ font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #4A5768; }}
  .num {{ text-align: right; }}
  footer {{ margin-top: 34px; padding-top: 12px; border-top: 1px solid #e4e9f0;
            color: #8492A6; font-size: 11px; display: flex; justify-content: space-between; }}
  @media print {{ .page {{ padding: 0; max-width: none; }} }}
</style>
</head>
<body>
<div class="page">
  <header>
    <div class="brand">Sport Machine · Meccsjelentés</div>
    <h1>{home} <span style="color:#8492A6">vs</span> {away}</h1>
    <div class="sub">Elemzett szakasz: {dur_s / 60:.1f} perc · felismert gólok: {goals_h}–{goals_a}</div>
  </header>

  <h2>Mutatók</h2>
  <div class="metrics">{metrics}</div>

  <h2>Esemény-összesítő</h2>
  <table>
    <tr><th></th><th class="num">{home}</th><th class="num">{away}</th></tr>
    <tr><td>Gól</td><td class="num"><b>{goals_h}</b></td><td class="num"><b>{goals_a}</b></td></tr>
    <tr><td>Lövés</td><td class="num">{shots_h}</td><td class="num">{shots_a}</td></tr>
    <tr><td>Labdaeladás</td><td class="num">{to_h}</td><td class="num">{to_a}</td></tr>
  </table>

  <h2>Játékfázisok</h2>
  {_phase_bars(phases, meta.home_team, meta.away_team)}

  <h2>Védekezési formák</h2>
  <table>
    <tr><th>Csapat</th><th>Leggyakoribb védekezés</th></tr>
    <tr><td>{home}</td><td><b>{escape(str(defense.get('home', '—')))}</b></td></tr>
    <tr><td>{away}</td><td><b>{escape(str(defense.get('away', '—')))}</b></td></tr>
  </table>

  <h2>Gól-idővonal</h2>
  {goals_html}

  {load_html}

  {shots_html}

  {intensity_html}

  {passes_html}

  {notes_html}

  {hm_html}

  {q_html}

  <footer>
    <span>Készült a Sport Machine kézilabda-elemzővel</span>
    <span>Nyomtatás: Ctrl+P / ⌘P → Mentés PDF-ként</span>
  </footer>
</div>
</body>
</html>
"""
