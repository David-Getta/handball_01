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


def _defense_bars(dist: dict, empty: str = "Nincs elég védekező minta.") -> str:
    """Megoszlás vízszintes sávokkal (inline szélesség = %) — védőformákra
    és támadás-mixre is."""
    if not dist:
        return f'<p class="empty">{escape(empty)}</p>'
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


def _def_zone_bars(zones: dict) -> str:
    """Kapott lövések zónánként: arány-sáv + "gól/lövés · szabad: n"."""
    if not zones:
        return '<p class="empty">Nincs elég kapott-lövés minta.</p>'
    total = sum(int(rec.get("shots", 0)) for rec in zones.values()) or 1
    out = []
    for zone, rec in zones.items():
        shots = int(rec.get("shots", 0))
        goals = int(rec.get("goals", 0))
        free = int(rec.get("free", 0))
        p = max(0.0, min(100.0, 100.0 * shots / total))
        label = f"{goals}/{shots}" + (f" · szabad: {free}" if free else "")
        out.append(
            f'<div class="bar-row"><span class="bar-label">{escape(str(zone))}</span>'
            f'<span class="bar"><span class="bar-fill gold" style="width:{p:.0f}%"></span></span>'
            f'<span class="bar-pct">{label}</span></div>')
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

    # Szöveges bevezető: hogyan játszanak — mondatokban, a számok elé.
    from .scouting import scouting_narrative
    narrative_html = ""
    try:
        narrative_html = "".join(
            f'<p class="cs"><b>{escape(s["title"])}.</b> {escape(s["body"])}</p>'
            for s in scouting_narrative(rep))
    except Exception:
        pass

    metric_items = [
        _metric("Szervezett támadás", f"{rep.attack_share_pct:.0f}%"),
        _metric("Gyors indítás", f"{rep.fast_break_pct:.0f}%"),
        _metric("Átl. támadáshossz", f"{rep.avg_attack_duration_s:.1f} s"),
        _metric("Labda átlagsebesség", f"{rep.avg_ball_speed_ms:.1f} m/s"),
        _metric("Lövés / gól", f"{rep.shots} / {rep.goals}"),
        _metric("Gólarány", f"{rep.shot_efficiency_pct:.0f}%"),
        # Helyzetminőség: várható gól + befejezés-eltérés (ha számolható).
        *([_metric("Várható gól (xG)", f"{rep.xg:.1f}"),
           _metric("Befejezés (gól−xG)", f"{rep.xg_diff:+.1f}")]
          if getattr(rep, "xg", 0.0) > 0 else []),
        *([_metric("Szabad lövést enged",
                   f"{100.0 * rep.def_free_shots / rep.def_shots_against:.0f}%")]
          if getattr(rep, "def_shots_against", 0) >= 4 else []),
        *([_metric("Cserehullám", str(rep.sub_rotations)),
           _metric("Cserék utáni mérleg",
                   f"{rep.sub_after_for - rep.sub_after_against:+d} gól")]
          if getattr(rep, "sub_rotations", 0) >= 2 else []),
        *([_metric("Irányító-függés",
                   f"{rep.playmaker_dependency}"
                   + (f" (−{100 * rep.playmaker_drop:.0f} pont nélküle)"
                      if rep.playmaker_drop is not None else ""))]
          if getattr(rep, "playmaker_dependency", None) else []),
        _metric("Labdaeladás", str(rep.turnovers)
                + (f" ({100.0 * rep.turnover_front / rep.turnover_total:.0f}"
                   "% elöl)"
                   if getattr(rep, "turnover_total", 0) >= 5 else "")),
        *([_metric("Labdabirtoklás", f"{rep.possession_pct:.0f}%")]
          if getattr(rep, "possession_pct", 0) else []),
        *([_metric("Gólpassz-vezér", f"{rep.top_assist_count} gólpassz")]
          if getattr(rep, "top_assist_count", 0) >= 2 else []),
        *([_metric("Passz-tengely",
                   f"{rep.pass_pairs[0]['from']} → {rep.pass_pairs[0]['to']}"
                   f" ({rep.pass_pairs[0]['passes']}×)")]
          if (getattr(rep, "pass_total", 0) >= 15 and rep.pass_pairs
              and int(rep.pass_pairs[0]["passes"]) >= 5) else []),
        *([_metric("Véd. nyomás", f"{rep.defensive_pressure_m:.1f} m")]
          if getattr(rep, "defensive_pressure_m", 0) else []),
        *([_metric("Hajrá-mérleg",
                   f"{rep.clutch_goals_for - rep.clutch_goals_against:+d} gól")]
          if getattr(rep, "clutch_matches", 0) >= 1 else []),
        *([_metric("Blokkolt lövés", str(rep.blocks))]
          if getattr(rep, "blocks", 0) >= 3 else []),
        *([_metric("Lövés-erő",
                   f"átl. {rep.shot_speed_sum_kmh / rep.shot_speed_n:.0f}"
                   f" · csúcs {rep.shot_speed_max_kmh:.0f} km/h")]
          if getattr(rep, "shot_speed_n", 0) >= 5 else []),
        _metric("Figurák", str(rep.num_figures)),
    ]
    # Az új felismerő-rétegek mutatói — csak ha van mögöttük adat.
    if rep.gk_on_target:
        metric_items.append(_metric(
            "Kapusuk védés%",
            f"{100.0 * rep.gk_saves / rep.gk_on_target:.0f}%"))
    if rep.pp_shots:
        metric_items.append(_metric(
            "Emberelőny-gólarány",
            f"{100.0 * rep.pp_goals / rep.pp_shots:.0f}%"))
    if rep.empty_net_s:
        metric_items.append(_metric("7 a 6 összesen",
                                    f"{rep.empty_net_s:.0f} s"))
    metrics = "".join(metric_items)

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
  p.cs {{ font-size: 13.5px; margin: 8px 0; }}
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

  {narrative_html}

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

  {("<h2>Honnan kapják a lövéseket (védekezésük)</h2>" + _def_zone_bars(rep.def_zones))
   if getattr(rep, "def_zones", None) else ""}

  {("<h2>Ismert figuráik (a könyvtárunkból)</h2>" + _playbook_rows(playbook_match))
   if playbook_match else ""}

  <h2>Támadás-mix (típus szerint)</h2>
  {_defense_bars(rep.attack_mix, empty="Nincs elég támadás-minta.")}

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
    # Szakaszonkénti gól-eloszlás (mikor esnek a gólok) — sáv-táblaként.
    try:
        from .momentum import scoring_timeline
        tl = scoring_timeline(match)["buckets"]
        maxg = max((max(b["home"], b["away"]) for b in tl), default=0)
        if maxg > 0:
            rows = []
            for b in tl:
                lab = f"{int(b['start_s'] // 60)}\u2013{int(b['end_s'] // 60)}'"
                hw = 100.0 * b["home"] / maxg
                aw = 100.0 * b["away"] / maxg
                rows.append(
                    f'<div class="bar-row"><span class="bar-label">{lab}</span>'
                    f'<span class="bar"><span class="bar-fill" '
                    f'style="width:{hw:.0f}%;background:#5AA0FF"></span></span>'
                    f'<span class="bar-pct">{b["home"]}\u2013{b["away"]}</span></div>'
                    f'<div class="bar-row"><span class="bar-label"></span>'
                    f'<span class="bar"><span class="bar-fill" '
                    f'style="width:{aw:.0f}%;background:#FF6B6B"></span></span>'
                    f'<span class="bar-pct"></span></div>')
            goals_html += ('<h3>Mikor estek a g\u00f3lok</h3>'
                           + "".join(rows)
                           + f'<p class="note">fels\u0151 s\u00e1v (k\u00e9k): {escape(home)}'
                             f' \u00b7 als\u00f3 (piros): {escape(away)}</p>')
    except Exception:
        pass

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
    # Azonos mezszámú trackek EGY játékosként (aggregate_by_jersey).
    load_html = ""
    if player_stats:
        from .stats import aggregate_by_jersey
        team_of: dict = {}
        jersey_of: dict = {}
        for fr in match.frames:
            for p in fr.players:
                team_of.setdefault(p.track_id, getattr(p.team, "value", p.team))
                if p.jersey_number is not None:
                    jersey_of.setdefault(p.track_id, p.jersey_number)
        ranked = aggregate_by_jersey(player_stats, team_of, jersey_of,
                                     fps=fps)[:10]
        rows = []
        for g in ranked:
            name = meta.home_team if g["team"] == "home" else meta.away_team
            rows.append(
                f"<tr><td>{escape(g['label'])}</td><td>{escape(name)}</td>"
                f'<td class="num">{g["distance_m"]:.0f} m</td>'
                f'<td class="num">{g["top_speed_ms"] * 3.6:.1f}</td>'
                f'<td class="num">{g["sprint_count"]}</td></tr>')
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

    # Gólpassz-hálózat: a legerősebb gól-párosok (passzoló → lövő).
    try:
        from .event_detection import assist_network
        net = assist_network(match)
        jof = {}
        for fr in match.frames:
            for pp in fr.players:
                if pp.jersey_number is not None:
                    jof.setdefault(pp.track_id, pp.jersey_number)

        def _lab(pid):
            j = jof.get(pid)
            return f"#{j}" if j is not None else f"{pid}."

        gcols = []
        for side, name in (("home", home), ("away", away)):
            pairs = net[side]["pairs"][:6]
            if not pairs:
                continue
            rows = "".join(
                f'<tr><td>{escape(_lab(pr["from"]))} → {escape(_lab(pr["to"]))}</td>'
                f'<td class="num">{pr["goals"]} gól</td></tr>' for pr in pairs)
            gcols.append(f'<div class="col"><b>{escape(name)}</b>'
                         f'<table>{rows}</table></div>')
        if gcols:
            passes_html += ('<h2>Legerősebb gól-párosok</h2>'
                            '<div class="cols">' + "".join(gcols) + "</div>")
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

    # Automatikus edzői összefoglaló: mondatokban, a jelentés elejére.
    summary_html = ""
    try:
        from .coach_summary import coach_summary
        cs = coach_summary(match)
        if cs["sections"]:
            paras = "".join(
                f'<p class="cs"><b>{escape(s["title"])}.</b> '
                f'{escape(s["body"])}</p>' for s in cs["sections"])
            hl = ""
            if cs["highlights"]:
                hl = ('<ul>' + "".join(
                    f"<li>{escape(h)}</li>" for h in cs["highlights"]) + "</ul>")
            summary_html = "<h2>Edzői összefoglaló</h2>" + paras + hl
    except Exception:
        pass

    # Szabály-réteg blokk: támadás-mix, 7a6, kiállítások + emberelőny-
    # hatékonyság, hétméteresek — csak ha van mit mutatni.
    rules_html = ""
    try:
        team_names = {"home": home, "away": away}
        parts_html: list[str] = []

        from .attack_types import attack_mix
        mix = attack_mix(match)
        cols = []
        for key, name in (("home", home), ("away", away)):
            m_ = mix.get(key)
            if m_:
                cols.append(f'<div class="col"><b>{name}</b>'
                            + _defense_bars(m_) + "</div>")
        if cols:
            parts_html.append('<h2>Támadás-mix (típus szerint)</h2>'
                              '<div class="cols">' + "".join(cols) + "</div>")

        # Támadás-hatékonyság: típusonként lövésig/gólig jutás.
        from .attack_types import attack_efficiency
        eff = attack_efficiency(match)
        erows = []
        for key, name in (("home", home), ("away", away)):
            for typ, rec in (eff.get(key) or {}).items():
                if rec["attacks"] < 2:
                    continue
                erows.append(
                    f"<tr><td>{escape(name)}</td><td>{escape(typ)}</td>"
                    f'<td class="num">{rec["attacks"]}</td>'
                    f'<td class="num">{rec["shots"]}</td>'
                    f'<td class="num">{rec["goals"]}</td>'
                    f'<td class="num"><b>{rec["goal_pct"]:.0f}%</b></td></tr>')
        if erows:
            parts_html.append(
                "<h2>Támadás-hatékonyság (típusonként)</h2>"
                "<table><tr><th>Csapat</th><th>Típus</th>"
                '<th class="num">Támadás</th><th class="num">Lövés</th>'
                '<th class="num">Gól</th><th class="num">Gól%</th></tr>'
                + "".join(erows) + "</table>")

        from .goalkeeper import detect_empty_net
        empty = detect_empty_net(match)
        if empty:
            per_en: dict = {}
            for w in empty:
                per_en[w["team"]] = per_en.get(w["team"], 0.0) + w["duration_s"]
            lis = "".join(
                f"<li>{team_names.get(t, t)}: összesen {s_:.0f} mp "
                "lehozott kapussal</li>" for t, s_ in per_en.items())
            parts_html.append("<h2>Hetedik mezőnyjátékos (7 a 6)</h2><ul>"
                              + lis + "</ul>")

        from .rules import (detect_powerplay, detect_seven_meters,
                            powerplay_efficiency)
        pps = detect_powerplay(match)
        if pps:
            fps_ = match.meta.fps if match.meta.fps > 0 else 25.0
            rows = "".join(
                f"<li><b>{_fmt_clock(w['start_frame'] / fps_)}</b> — "
                f"{team_names.get(w['team_down'], w['team_down'])} "
                f"emberhátrányban {w['duration_s']:.0f} mp-ig</li>"
                for w in pps)
            eff = powerplay_efficiency(match)
            eff_rows = ""
            for key, name in (("home", home), ("away", away)):
                rec = eff.get(key)
                if rec and rec["pp_shots"]:
                    eff_rows += (f"<li>{name} emberelőnyben: "
                                 f"{rec['pp_goals']}/{rec['pp_shots']} gól "
                                 f"({rec['pp_eff_pct']:.0f}%)</li>")
            parts_html.append("<h2>Kiállítások és emberelőny</h2><ul>"
                              + rows + eff_rows + "</ul>")

        sevens = detect_seven_meters(match)
        if sevens:
            fps_ = match.meta.fps if match.meta.fps > 0 else 25.0
            lis = "".join(
                f"<li><b>{_fmt_clock(e['t'] / fps_)}</b> — "
                f"{team_names.get(e['team'], e['team'])} hétméterese</li>"
                for e in sevens)
            parts_html.append("<h2>Hétméteresek</h2><ul>" + lis + "</ul>")

        rules_html = "".join(parts_html)
    except Exception:
        pass

    # Helyzetminőség (xG): várható gól vs tényleges + lövő-tábla.
    xg_html = ""
    try:
        from .xg import match_xg
        r = match_xg(match)
        th, ta = r["teams"]["home"], r["teams"]["away"]
        if th["shots"] + ta["shots"] >= 4:
            jersey_of: dict = {}
            team_val: dict = {}
            for fr in match.frames:
                for pp in fr.players:
                    team_val.setdefault(pp.track_id,
                                        getattr(pp.team, "value", pp.team))
                    if pp.jersey_number is not None:
                        jersey_of.setdefault(pp.track_id, pp.jersey_number)

            def _lab(pid):
                j = jersey_of.get(pid)
                return f"#{j}" if j is not None else f"{pid}. játékos"

            srows = []
            for rec in r["shooters"][:8]:
                name = home if rec["team"] == "home" else away
                d = rec["diff"]
                srows.append(
                    f"<tr><td>{escape(_lab(rec['player_id']))}</td>"
                    f"<td>{escape(name)}</td>"
                    f'<td class="num">{rec["shots"]}</td>'
                    f'<td class="num">{rec["goals"]}</td>'
                    f'<td class="num">{rec["xg"]:.1f}</td>'
                    f'<td class="num"><b>{"+" if d > 0 else ""}{d:.1f}</b></td>'
                    "</tr>")
            xg_html = (
                "<h2>Helyzetminőség (várható gól)</h2>"
                "<table><tr><th></th>"
                f'<th class="num">{escape(home)}</th>'
                f'<th class="num">{escape(away)}</th></tr>'
                f'<tr><td>Várható gól (xG)</td>'
                f'<td class="num"><b>{th["xg"]:.1f}</b></td>'
                f'<td class="num"><b>{ta["xg"]:.1f}</b></td></tr>'
                f'<tr><td>Tényleges gól</td>'
                f'<td class="num">{th["goals"]}</td>'
                f'<td class="num">{ta["goals"]}</td></tr>'
                f'<tr><td>Befejezés (gól − xG)</td>'
                f'<td class="num">{th["diff"]:+.1f}</td>'
                f'<td class="num">{ta["diff"]:+.1f}</td></tr></table>'
                + ("<table><tr><th>Lövő</th><th>Csapat</th>"
                   '<th class="num">Lövés</th><th class="num">Gól</th>'
                   '<th class="num">xG</th><th class="num">+/−</th></tr>'
                   + "".join(srows) + "</table>" if srows else "")
                + '<p class="note">Az xG a lövés helyéből számolt '
                  'helyzetérték (kapu-távolság + látott kapuszög). Pozitív '
                  'befejezés-érték: a csapat/játékos a helyzetei felett '
                  'teljesített.</p>')
    except Exception:
        pass  # a jelentés e blokk nélkül is teljes

    # Védekezés: kapott lövések, szabad lövők, lyukas zónák.
    defense_html = ""
    try:
        from .defense import defense_analysis
        dres = defense_analysis(match)
        drows = []
        for side, name in (("home", home), ("away", away)):
            rec = dres[side]
            if rec["shots_against"] < 4:
                continue
            free = (f'{rec["free_pct"]:.0f}%'
                    if rec["free_pct"] is not None else "—")
            worst = rec["worst_zone"] or "—"
            if rec["worst_zone"]:
                wz = rec["zones"][rec["worst_zone"]]
                worst = f'{rec["worst_zone"]} ({wz["goals"]} gól)'
            drows.append(f"<tr><td>{escape(name)}</td>"
                         f'<td class="num">{rec["shots_against"]}</td>'
                         f'<td class="num">{rec["goals_against"]}</td>'
                         f'<td class="num">{rec["xg_against"]:.1f}</td>'
                         f'<td class="num"><b>{free}</b></td>'
                         f"<td>{escape(worst)}</td></tr>")
        dcols = []
        for side, name in (("home", home), ("away", away)):
            rec = dres[side]
            if rec["shots_against"] >= 4 and rec["zones"]:
                dcols.append(f'<div class="col"><b>{escape(name)}</b>'
                             + _def_zone_bars(rec["zones"]) + "</div>")
        if drows:
            defense_html = (
                "<h2>Védekezés (kapott lövések)</h2>"
                "<table><tr><th>Csapat</th>"
                '<th class="num">Kapott lövés</th>'
                '<th class="num">Kapott gól</th>'
                '<th class="num">Engedett xG</th>'
                '<th class="num">Szabad lövő</th>'
                "<th>Leglyukasabb zóna</th></tr>"
                + "".join(drows) + "</table>"
                + (('<div class="cols">' + "".join(dcols) + "</div>")
                   if dcols else "")
                + '<p class="note">Szabad lövő: a lövés pillanatában nem '
                  'volt védő a lövő 2 m-es körzetében — fedezés-hiba, '
                  'érdemes videóról visszanézni.</p>')
    except Exception:
        pass  # a jelentés e blokk nélkül is teljes

    # Csapat-mutatók összefoglaló tábla (birtoklás, véd. nyomás, átmenet).
    team_metrics_html = ""
    try:
        from .defense import (defensive_pressure, transition_defense,
                              turnover_zones)
        from .stats import possession_share, intensity_trend
        ps = possession_share(match)
        dp = defensive_pressure(match)
        td = transition_defense(match)
        it = intensity_trend(match)
        tz = turnover_zones(match)

        def _cell(v, suf=""):
            return f"{v}{suf}" if v is not None else "—"

        def _drop(side):
            d = it[side]["drop_pct"]
            if not it[side]["first_ms"]:
                return "—"
            return f"−{d:.0f}%" if d > 0 else f"+{-d:.0f}%"

        rows = [
            ("Labdabirtoklás",
             _cell(ps["home"]["pct"], "%") if ps["home"]["pct"] else "—",
             _cell(ps["away"]["pct"], "%") if ps["away"]["pct"] else "—"),
            ("Védekezési nyomás (kilépés)",
             _cell(dp["home"]["avg_pressure_m"], " m"),
             _cell(dp["away"]["avg_pressure_m"], " m")),
            ("Átmenet-gól (labdavesztés után)",
             _cell(td["home"]["transition_goals_against"]),
             _cell(td["away"]["transition_goals_against"])),
            ("Tempó-esés a 2. félidőre",
             _drop("home"), _drop("away")),
            ("Labdaeladás a támadó harmadban",
             (f"{tz['home']['front_pct']:.0f}%"
              if tz["home"]["total"] >= 3 else "—"),
             (f"{tz['away']['front_pct']:.0f}%"
              if tz["away"]["total"] >= 3 else "—")),
        ]
        # Elhúzódó (35 mp+) támadások aránya (ha van elég támadás).
        try:
            from .tactics import slow_attacks
            sa = slow_attacks(match)
            if sa["home"]["attacks"] >= 4 or sa["away"]["attacks"] >= 4:
                def _sa(side):
                    rec = sa[side]
                    return (f"{rec['slow_pct']:.0f}%"
                            if rec["attacks"] >= 4 else "—")
                rows.append(("Elhúzódó támadás (35 mp+)",
                             _sa("home"), _sa("away")))
        except Exception:
            pass
        # Blokkolt lövések sora (ha volt blokk).
        try:
            from .defense import detect_blocks
            bl = detect_blocks(match)
            if bl["home"]["blocks"] or bl["away"]["blocks"]:
                rows.append(("Blokkolt lövés",
                             str(bl["home"]["blocks"]),
                             str(bl["away"]["blocks"])))
        except Exception:
            pass
        # Lövés-sebesség sorok (ha van mért lövés).
        try:
            from .event_detection import shot_speeds
            sp = shot_speeds(match)["teams"]

            def _spd(side, key):
                rec = sp[side]
                return f"{rec[key]:.0f} km/h" if rec["n"] else "—"
            rows.append(("Átl. lövés-sebesség",
                         _spd("home", "avg_kmh"), _spd("away", "avg_kmh")))
            rows.append(("Leggyorsabb lövés",
                         _spd("home", "max_kmh"), _spd("away", "max_kmh")))
        except Exception:
            pass
        body = "".join(
            f"<tr><td>{escape(lab)}</td>"
            f'<td class="num">{h}</td><td class="num">{a}</td></tr>'
            for (lab, h, a) in rows)
        team_metrics_html = (
            "<h2>Csapat-mutatók</h2><table>"
            f'<tr><th></th><th class="num">{escape(home)}</th>'
            f'<th class="num">{escape(away)}</th></tr>' + body + "</table>")
    except Exception:
        pass

    # Fejléc-összkép: dátum + xG + szabad lövő-arány egy sávban — a
    # jelentés első pillantásra elmondja a meccs lényegét.
    header_bits = []
    if meta.date:
        header_bits.append(escape(str(meta.date)))
    try:
        from .xg import match_xg
        _tx = match_xg(match)["teams"]
        if _tx["home"]["shots"] + _tx["away"]["shots"] >= 4:
            header_bits.append(
                f'várható gól (xG): {_tx["home"]["xg"]:.1f} – '
                f'{_tx["away"]["xg"]:.1f}')
    except Exception:
        pass
    try:
        from .defense import defense_analysis
        _d = defense_analysis(match)
        if any(_d[s_]["free_pct"] is not None for s_ in ("home", "away")):
            def _fp(side):
                v = _d[side]["free_pct"]
                return f"{v:.0f}%" if v is not None else "—"
            header_bits.append(
                f'szabad lövőt enged: {_fp("home")} / {_fp("away")}')
    except Exception:
        pass
    # Félidei állás a fejlécbe (ha felismerhető a szünet).
    try:
        from .momentum import halftime_score
        _hs = halftime_score(match)
        if _hs is not None:
            header_bits.append(
                f'félidőben: {_hs["home"]} – {_hs["away"]}')
    except Exception:
        pass
    # Labdabirtoklás-sor az esemény-táblához (ha számolható).
    poss_row = ""
    try:
        from .stats import possession_share
        _ps = possession_share(match)
        if _ps["home"]["pct"] or _ps["away"]["pct"]:
            poss_row = (f'<tr><td>Labdabirtoklás</td>'
                        f'<td class="num">{_ps["home"]["pct"]:.0f}%</td>'
                        f'<td class="num">{_ps["away"]["pct"]:.0f}%</td></tr>')
    except Exception:
        pass

    # A meccs íve: fordulatok + legnagyobb előny (ha volt vezetés-váltás).
    prog_line = ""
    try:
        from .momentum import score_progression
        prog = score_progression(match)
        if prog["lead_changes"] >= 1:
            bl = prog["biggest_lead"]
            top = home if bl["home"] >= bl["away"] else away
            top_v = max(bl["home"], bl["away"])
            cb_txt = ""
            cb = prog.get("comeback", {})
            cb_side = max(("home", "away"), key=lambda k: cb.get(k, 0))
            if cb.get(cb_side, 0) >= 3:
                cb_name = home if cb_side == "home" else away
                cb_txt = (f' · {escape(cb_name)} {cb[cb_side]} gólos '
                          'hátrányból fordított')
            cl_txt = ""
            try:
                from .momentum import clutch_performance
                cp = clutch_performance(match)
                if cp.get("available") and cp.get("close"):
                    gh = cp["home"]["goals"]
                    ga = cp["away"]["goals"]
                    if abs(gh - ga) >= 2:
                        wname = home if gh > ga else away
                        cl_txt = (f' · a hajrát {escape(wname)} nyerte '
                                  f'{max(gh, ga)}–{min(gh, ga)}-ra')
            except Exception:
                pass
            prog_line = (f'<div class="sub">A meccs {prog["lead_changes"]}-szor '
                         f'fordult · legnagyobb előny: {escape(top)} +{top_v}'
                         f'{cb_txt}{cl_txt}</div>')
    except Exception:
        pass
    header_extra = (
        (f'<div class="sub">{" · ".join(header_bits)}</div>'
         if header_bits else "") + prog_line)

    # Kapus-teljesítmény (ha van kapus-jelölés a meccsen).
    gk_html = ""
    try:
        from .goalkeeper import goalkeeper_stats
        gstats = goalkeeper_stats(match)
        rows = []
        for key, name in (("home", home), ("away", away)):
            rec = gstats.get(key)
            if not rec or not rec["on_target"]:
                continue
            zones = ", ".join(f"{z}: {n}" for z, n in
                              sorted(rec["conceded_zones"].items(),
                                     key=lambda kv: -kv[1])) or "—"
            seven = (f"{rec.get('seven_saved', 0)}/{rec.get('seven_faced', 0)}"
                     if rec.get("seven_faced") else "—")
            # Leggyengébb zóna: a legalacsonyabb védés%-ú, legalább 2 lövést
            # kapott zóna — ide üt a legjobban a kapus ellen.
            weak = "—"
            zsp = rec.get("zone_save_pct", {})
            otz = rec.get("on_target_zones", {})
            cand = [(z, p) for z, p in zsp.items() if otz.get(z, 0) >= 2]
            if cand:
                z, p = min(cand, key=lambda kv: kv[1])
                weak = f"{z} ({p:.0f}%)"
            rows.append(f"<tr><td>{name}</td>"
                        f"<td class='num'>{rec['on_target']}</td>"
                        f"<td class='num'>{rec['saves']}</td>"
                        f"<td class='num'>{rec['conceded']}</td>"
                        f"<td class='num'><b>{rec['save_pct']:.0f}%</b></td>"
                        f"<td class='num'>{seven}</td>"
                        f"<td>{escape(zones)}</td>"
                        f"<td>{escape(weak)}</td></tr>")
        if rows:
            gk_html = ("<h2>Kapus-teljesítmény</h2><table>"
                       "<tr><th>Csapat</th><th class='num'>Kapura</th>"
                       "<th class='num'>Védés</th><th class='num'>Kapott</th>"
                       "<th class='num'>Védés%</th>"
                       "<th class='num'>7 m-es (fogott/kapott)</th>"
                       "<th>Kapott gólok zónái</th>"
                       "<th>Leggyengébb zóna</th></tr>"
                       + "".join(rows) + "</table>")
    except Exception:
        pass

    # Edzés-fókusz: a meccs gyengeségeiből következő gyakorlás-javaslatok.
    training_html = ""
    try:
        from .training import training_focus
        tf = training_focus(match)
        tparts = []
        for side, name in (("home", home), ("away", away)):
            items = tf.get(side) or []
            if not items:
                continue
            lis = "".join(
                f"<li><b>{escape(it['title'])}</b> ({escape(it['area'])}) — "
                f"{escape(it['why'])}.<br>"
                f"<span class='note'>Gyakorlat: {escape(it['drill'])}.</span></li>"
                for it in items)
            tparts.append(f"<h3>{escape(name)}</h3><ul>{lis}</ul>")
        if tparts:
            training_html = ("<h2>Edzés-fókusz a meccs alapján</h2>"
                             + "".join(tparts)
                             + '<p class="note">Szabály-alapú javaslatok — '
                               'minden pont mögött a meccs kiszámolt adata '
                               'áll.</p>')
    except Exception:
        pass  # a jelentés e blokk nélkül is teljes

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
  p.cs {{ font-size: 13.5px; margin: 8px 0; }}
  .cols {{ display: flex; gap: 22px; }}
  .col {{ flex: 1; }}
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
    {header_extra}
  </header>

  {summary_html}

  <h2>Mutatók</h2>
  <div class="metrics">{metrics}</div>

  <h2>Esemény-összesítő</h2>
  <table>
    <tr><th></th><th class="num">{home}</th><th class="num">{away}</th></tr>
    <tr><td>Gól</td><td class="num"><b>{goals_h}</b></td><td class="num"><b>{goals_a}</b></td></tr>
    <tr><td>Lövés</td><td class="num">{shots_h}</td><td class="num">{shots_a}</td></tr>
    <tr><td>Labdaeladás</td><td class="num">{to_h}</td><td class="num">{to_a}</td></tr>
    {poss_row}
  </table>

  <h2>Játékfázisok</h2>
  {_phase_bars(phases, meta.home_team, meta.away_team)}

  <h2>Védekezési formák</h2>
  <table>
    <tr><th>Csapat</th><th>Leggyakoribb védekezés</th></tr>
    <tr><td>{home}</td><td><b>{escape(str(defense.get('home', '—')))}</b></td></tr>
    <tr><td>{away}</td><td><b>{escape(str(defense.get('away', '—')))}</b></td></tr>
  </table>

  {xg_html}

  {defense_html}

  {team_metrics_html}

  {training_html}

  {gk_html}

  {rules_html}

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
