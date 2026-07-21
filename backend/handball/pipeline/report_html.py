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


def scouting_report_html(rep: ScoutingReport,
                         playbook_match: dict | None = None,
                         matchup: list[str] | None = None) -> str:
    """A jelentés teljes, önálló HTML-je (nyomtatható; böngészőből PDF).

    `playbook_match` (opcionális): a mentett figurákkal való egyezés
    ({total_attacks, matched, unmatched}) — külön szakaszként kerül be.
    `matchup` (opcionális): a meccsterv-illesztés mondatai — "a kettőnk
    párosítása" szakaszként kerül be.
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

    # Szerep-tábla: a több meccsből összegzett játékos-profilok — a
    # csempékkel és a kulcsokkal azonos küszöbökkel.
    roles_html = ""
    try:
        role_rows = []

        def _role(role, pid, detail):
            role_rows.append(f"<tr><td>{escape(role)}</td>"
                             f"<td>{pid}. játékos</td>"
                             f"<td>{escape(detail)}</td></tr>")

        per_sh: dict = {}
        for rec_sz in (rep.shooter_zones or []):
            per_sh[rec_sz["player_id"]] = (
                per_sh.get(rec_sz["player_id"], 0) + int(rec_sz["shots"]))
        if per_sh:
            pid, n_sh = max(per_sh.items(), key=lambda kv: kv[1])
            if n_sh >= 3:
                _role("Fő lövő", pid, f"{n_sh} azonosított lövés")
        bl = rep.blockers or []
        if bl and bl[0]["blocks"] >= 3:
            _role("A fal kulcsa", bl[0]["player_id"],
                  f"{bl[0]['blocks']} blokk")
        sv = rep.seven_takers or []
        if sv and sv[0]["attempts"] >= 2:
            _role("Hetes-dobó", sv[0]["player_id"],
                  f"{sv[0]['goals']}/{sv[0]['attempts']} gól")
        fb = rep.fb_finishers or []
        if fb and fb[0]["goals"] >= 2:
            _role("Kontra-befejező", fb[0]["player_id"],
                  f"{fb[0]['goals']} kontra-gól")
        ot = rep.gk_outlet_targets or []
        if (ot and rep.gk_outlets >= 2 and ot[0]["n"] >= 2
                and ot[0]["n"] / rep.gk_outlets >= 0.5):
            _role("Indítás-célpont", ot[0]["player_id"],
                  f"{ot[0]['n']}/{rep.gk_outlets} indítás")
        if role_rows:
            roles_html = ("<h2>Kikre készülj (szerepek)</h2><table>"
                          "<tr><th>Szerep</th><th>Játékos</th>"
                          "<th>Mérleg</th></tr>"
                          + "".join(role_rows) + "</table>")
        # Hetes-dobóik irány-táblája — a kapus egy pillantásra látja,
        # ki hová szokta lőni (csak mért iránnyal rendelkező dobóknál).
        from .rules import SEVEN_DIR_HU as hu_dir
        seven_rows = []
        for t7 in (rep.seven_takers or []):
            if t7.get("attempts", 0) < 2:
                continue
            dirs7 = t7.get("dirs") or {}
            dir_txt = " · ".join(
                f"{hu_dir.get(d, d)} {n}×"
                for d, n in sorted(dirs7.items(),
                                   key=lambda kv: -kv[1])) or "—"
            seven_rows.append(
                f"<tr><td>{t7['player_id']}. játékos</td>"
                f'<td class="num">{t7["goals"]}/{t7["attempts"]}</td>'
                f"<td>{escape(dir_txt)}</td></tr>")
        if seven_rows:
            roles_html += ("<h2>Hetes-dobóik (irányokkal)</h2><table>"
                           "<tr><th>Dobó</th>"
                           '<th class="num">Gól/kísérlet</th>'
                           "<th>Merre lövi</th></tr>"
                           + "".join(seven_rows) + "</table>")
        # Emberfogóik: ki milyen szorosan őriz — a laza oldal a
        # támadható, a tapadó ellen elzárás kell (top 4, 50+ kocka).
        mark_rows = []
        for mk8 in sorted((rep.markers or []),
                          key=lambda m8: -m8["frames"])[:4]:
            if mk8["frames"] < 50:
                continue
            avg8 = mk8["dist_sum"] / mk8["frames"]
            tag8 = (" · LAZA" if avg8 >= 2.5
                    else " · tapadó" if avg8 <= 1.5 else "")
            mark_rows.append(
                f"<tr><td>{mk8['player_id']}. játékos</td>"
                f'<td class="num">{mk8["frames"]}</td>'
                f'<td class="num">{avg8:.1f} m{tag8}</td></tr>')
        if mark_rows:
            roles_html += ("<h2>Emberfogóik (átlagtávval)</h2><table>"
                           "<tr><th>Védő</th>"
                           '<th class="num">Őrzés-kocka</th>'
                           '<th class="num">Átl. táv</th></tr>'
                           + "".join(mark_rows) + "</table>")
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
        *([_metric("Támadás-oldal",
                   " · ".join(
                       f"{k} {100.0 * v / max(1, sum(rep.side_frames.values())):.0f}%"
                       for k, v in rep.side_frames.items()))]
          if sum(getattr(rep, "side_frames", {}).values() or [0]) >= 250
          else []),
        *([_metric("Hosszú támadás hozama",
                   f"{100.0 * rep.duration_eff['hosszú (35 mp+)']['goals'] / rep.duration_eff['hosszú (35 mp+)']['attacks']:.0f}% gól")]
          if (getattr(rep, "duration_eff", {}).get("hosszú (35 mp+)",
                                                   {}).get("attacks", 0) >= 4)
          else []),
        *([_metric("Leggyengébb forma ellenük",
                   min(((f_, v) for f_, v in rep.vs_formation.items()
                        if v["shots"] >= 4),
                       key=lambda kv: kv[1]["goals"] / kv[1]["shots"])[0])]
          if sum(1 for v in getattr(rep, "vs_formation", {}).values()
                 if v["shots"] >= 4) >= 2 else []),
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

  {roles_html}

  {("<h2>Meccsterv (a kettőnk párosítása)</h2><ul>"
     + "".join(f"<li>{escape(p_)}</li>" for p_ in matchup) + "</ul>")
    if matchup else ""}

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
    # Ha felismerhető a szünet, FÉLIDŐ-jelölő vágja ketté a listát.
    ht_t = None
    try:
        from .halftime import detect_halftime
        ht_t = detect_halftime(match)
    except Exception:
        pass
    goal_rows = []
    ht_marked = False
    run_h = run_a = 0
    for e in events:
        typ = getattr(e.type, "value", e.type)
        if typ != "goal":
            continue
        team = getattr(e.team, "value", e.team)
        if (ht_t is not None and not ht_marked and e.t >= ht_t):
            goal_rows.append(
                f"<li><b>— FÉLIDŐ ({run_h} – {run_a}) —</b></li>")
            ht_marked = True
        if team == "home":
            run_h += 1
        else:
            run_a += 1
        name = meta.home_team if team == "home" else meta.away_team
        scorer = ""
        pid = getattr(e, "player_id", None)
        if pid is None and isinstance(e, dict):
            pid = e.get("player_id")
        if pid is not None:
            scorer = f" · {pid}. játékos"
        goal_rows.append(
            f"<li><b>{_fmt_clock(e.t / fps)}</b> — GÓL · {escape(name)}"
            f"{scorer}</li>")
    if ht_t is not None and goal_rows and not ht_marked:
        # Minden gól az első félidőben esett — a jelölő a lista végére.
        goal_rows.append(
            f"<li><b>— FÉLIDŐ ({run_h} – {run_a}) —</b></li>")
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
        # Játékos-fáradás: 2. félidei tempó-esés trackenként (ha mérhető) —
        # a mezszám-csoport esése a trackek közül a legnagyobb.
        fatigue_of: dict = {}
        try:
            from .stats import player_fatigue
            for r_ in player_fatigue(match):
                fatigue_of[r_["track_id"]] = r_["drop_pct"]
        except Exception:
            pass
        # Poszt-becslés a track-ekhez (ha van elég minta).
        post_of: dict = {}
        try:
            from .roles import estimate_positions
            est_all = estimate_positions(match)
            for side_ in ("home", "away"):
                for tid_, r_ in est_all.get(side_, {}).items():
                    post_of[tid_] = r_["poszt"]
        except Exception:
            pass
        # Játék-mérleg trackenként (gól/lövés + gól−xG) — a fizikai és
        # a játék-teljesítmény így egy sorban olvasható.
        shooter_of: dict = {}
        try:
            from .xg import match_xg
            for r_sh in match_xg(match).get("shooters", []):
                shooter_of[r_sh["player_id"]] = r_sh
        except Exception:
            pass
        rows = []
        for g in ranked:
            name = meta.home_team if g["team"] == "home" else meta.away_team
            poszt = next((post_of[t] for t in g["track_ids"]
                          if t in post_of), "—")
            drops = [fatigue_of[t] for t in g["track_ids"]
                     if t in fatigue_of]
            if drops:
                d = max(drops)
                fade = (f"−{d:.0f}%" if d > 0 else f"+{-d:.0f}%")
            else:
                fade = "—"
            g_goals = sum(shooter_of.get(t, {}).get("goals", 0)
                          for t in g["track_ids"])
            g_shots = sum(shooter_of.get(t, {}).get("shots", 0)
                          for t in g["track_ids"])
            g_diff = sum(shooter_of.get(t, {}).get("diff", 0.0)
                         for t in g["track_ids"])
            game = f"{g_goals}/{g_shots}" if g_shots else "—"
            diff_txt = f"{g_diff:+.1f}" if g_shots else "—"
            rows.append(
                f"<tr><td>{escape(g['label'])}</td><td>{escape(name)}</td>"
                f"<td>{escape(poszt)}</td>"
                f'<td class="num">{g["distance_m"]:.0f} m</td>'
                f'<td class="num">{g["top_speed_ms"] * 3.6:.1f}</td>'
                f'<td class="num">{g["sprint_count"]}</td>'
                f'<td class="num">{game}</td>'
                f'<td class="num">{diff_txt}</td>'
                f'<td class="num">{fade}</td></tr>')
        if rows:
            load_html = ('<h2>Játékos-terhelés (top 10 táv szerint)</h2>'
                         '<table><tr><th>Játékos</th><th>Csapat</th>'
                         '<th>Poszt</th>'
                         '<th class="num">Táv</th><th class="num">Max km/h</th>'
                         '<th class="num">Sprint</th>'
                         '<th class="num">Gól/lövés</th>'
                         '<th class="num">Gól−xG</th>'
                         '<th class="num">2. félidei tempó</th></tr>'
                         + "".join(rows) + "</table>")

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

        from .attack_types import attack_origins
        ao_rep = attack_origins(match)
        orows = []
        for side, name in (("home", home), ("away", away)):
            for origin, rec in sorted((ao_rep.get(side) or {}).items(),
                                      key=lambda kv: -kv[1]["attacks"]):
                orows.append(
                    f"<tr><td>{escape(name)}</td>"
                    f"<td>{escape(origin)}</td>"
                    f'<td class="num">{rec["attacks"]}</td>'
                    f'<td class="num">{rec["goals"]}</td></tr>')
        if orows:
            parts_html.append(
                "<h2>Támadás-eredet (miből indul)</h2>"
                "<table><tr><th>Csapat</th><th>Eredet</th>"
                '<th class="num">Támadás</th>'
                '<th class="num">Gól</th></tr>'
                + "".join(orows) + "</table>")

        from .goalkeeper import detect_empty_net
        empty = detect_empty_net(match)
        if empty:
            per_en: dict = {}
            for w in empty:
                per_en[w["team"]] = per_en.get(w["team"], 0.0) + w["duration_s"]
            # Mérleg: dobott vs üres kapura kapott gólok a 7 a 6 alatt.
            try:
                from .goalkeeper import empty_net_goals
                eng = empty_net_goals(match)
            except Exception:
                eng = {}

            try:
                from .goalkeeper import empty_net_context
                enc_all = empty_net_context(match)
            except Exception:
                enc_all = {}

            def _en_bal(t):
                r = eng.get(t) or {}
                sc = r.get("scored_7v6", 0)
                co = r.get("conceded_empty", 0)
                extra = ""
                if sc or co:
                    extra = (f" (mérleg: +{sc} dobott, "
                             f"\u2212{co} kapott üres kapura)")
                # Időzítés-minta: jellemzően hátrányban nyúlnak hozzá?
                enc = enc_all.get(t) or {}
                if (enc.get("windows", 0) >= 2
                        and enc.get("trailing", 0) / enc["windows"] >= 0.7):
                    extra += " — jellemzően hátrányban indítva"
                return extra
            lis = "".join(
                f"<li>{team_names.get(t, t)}: összesen {s_:.0f} mp "
                f"lehozott kapussal{_en_bal(t)}</li>"
                for t, s_ in per_en.items())
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
            # Kimenetel + dobó + kiharcoló, ha azonosítható.
            out_by_t: dict = {}
            try:
                from .rules import seven_meter_outcomes
                for sm in seven_meter_outcomes(match):
                    out_by_t[sm["t"]] = sm
            except Exception:
                pass

            def _seven_extra(e):
                sm = out_by_t.get(e["t"])
                if not sm:
                    return ""
                bits = []
                if sm.get("shooter_id") is not None:
                    bits.append(f"dobó: {sm['shooter_id']}.")
                if sm.get("outcome") and sm["outcome"] != "ismeretlen":
                    bits.append(sm["outcome"])
                if sm.get("irany"):
                    from .rules import SEVEN_DIR_HU
                    bits.append(SEVEN_DIR_HU[sm["irany"]])
                return f" ({', '.join(bits)})" if bits else ""
            lis = "".join(
                f"<li><b>{_fmt_clock(e['t'] / fps_)}</b> — "
                f"{team_names.get(e['team'], e['team'])} hétméterese"
                f"{_seven_extra(e)}</li>"
                for e in sevens)
            parts_html.append("<h2>Hétméteresek</h2><ul>" + lis + "</ul>")

        rules_html = "".join(parts_html)
    except Exception:
        pass

    # Figura-hatékonyság: melyik begyakorolt támadás hozott gólt.
    setplays_html = ""
    try:
        from .setplays import setplay_efficiency
        eff_sp = setplay_efficiency(match)
        sp_rows = []
        for side, name in (("home", home), ("away", away)):
            for r_sp in (eff_sp.get(side) or [])[:4]:
                sp_rows.append(
                    f"<tr><td>{escape(name)}</td>"
                    f'<td class="num">{r_sp["figure"] + 1}.</td>'
                    f'<td class="num">{r_sp["attacks"]}</td>'
                    f'<td class="num">{r_sp["shots"]}</td>'
                    f'<td class="num">{r_sp["goals"]}</td>'
                    f'<td class="num">{r_sp["goal_pct"]:.0f}%</td></tr>')
        if sp_rows:
            setplays_html = (
                "<h2>Figurák (visszatérő támadás-minták)</h2>"
                "<table><tr><th>Csapat</th>"
                '<th class="num">Figura</th>'
                '<th class="num">Támadás</th>'
                '<th class="num">Lövés</th>'
                '<th class="num">Gól</th>'
                '<th class="num">Gól-arány</th></tr>'
                + "".join(sp_rows) + "</table>"
                + '<p class="note">A figura: azonos mozgás-mintázatú, '
                  'legalább kétszer játszott támadás — a magas gól-arányú '
                  'figura a csapat kenyere, arra érdemes készülni.</p>')
    except Exception:
        pass

    # A meccs gerince: a kulcs-pillanatok időrendi listája — ugyanaz a
    # réteg, mint az app kártyája és a csomag kulcs_pillanatok.txt-je.
    moments_html = ""
    try:
        from .momentum import key_moments
        kms = key_moments(match)
        if kms:
            lis_km = "".join(
                f"<li><b>{_fmt_clock(km['t_s'])}</b> — "
                f"{escape(km['label'])}</li>"
                for km in kms)
            moments_html = ("<h2>A meccs gerince (kulcs-pillanatok)</h2>"
                            "<ul>" + lis_km + "</ul>")
    except Exception:
        pass
    rules_html = moments_html + setplays_html + rules_html

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

            # Ziccer-mérleg (xG >= 0,5): csapatonként és lövőnként
            # [gól, nagy helyzet] — a küszöb a többi felülettel azonos.
            from .xg import BIG_CHANCE_XG
            big = {"home": [0, 0], "away": [0, 0]}
            bigp: dict = {}
            for sh in r.get("shots", []):
                if sh.get("xg", 0.0) < BIG_CHANCE_XG:
                    continue
                big[sh["team"]][1] += 1
                big[sh["team"]][0] += int(sh.get("outcome") == "goal")
                if sh.get("player_id") is not None:
                    pr = bigp.setdefault(sh["player_id"], [0, 0])
                    pr[1] += 1
                    pr[0] += int(sh.get("outcome") == "goal")
            big_row = ""
            if big["home"][1] + big["away"][1] >= 1:
                big_row = (
                    "<tr><td>Ziccer (gól / nagy helyzet)</td>"
                    f'<td class="num">{big["home"][0]}/{big["home"][1]}</td>'
                    f'<td class="num">{big["away"][0]}/{big["away"][1]}'
                    "</td></tr>")

            srows = []
            for rec in r["shooters"][:8]:
                name = home if rec["team"] == "home" else away
                d = rec["diff"]
                bz = bigp.get(rec["player_id"])
                bz_cell = (f'<td class="num">{bz[0]}/{bz[1]}</td>'
                           if bz else '<td class="num">–</td>')
                srows.append(
                    f"<tr><td>{escape(_lab(rec['player_id']))}</td>"
                    f"<td>{escape(name)}</td>"
                    f'<td class="num">{rec["shots"]}</td>'
                    f'<td class="num">{rec["goals"]}</td>'
                    f'<td class="num">{rec["xg"]:.1f}</td>'
                    f'<td class="num"><b>{"+" if d > 0 else ""}{d:.1f}</b></td>'
                    + bz_cell + "</tr>")
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
                f'<td class="num">{ta["diff"]:+.1f}</td></tr>'
                + big_row + "</table>"
                + ("<table><tr><th>Lövő</th><th>Csapat</th>"
                   '<th class="num">Lövés</th><th class="num">Gól</th>'
                   '<th class="num">xG</th><th class="num">+/−</th>'
                   '<th class="num">Ziccer</th></tr>'
                   + "".join(srows) + "</table>" if srows else "")
                + '<p class="note">Az xG a lövés helyéből számolt '
                  'helyzetérték (kapu-távolság + látott kapuszög). Pozitív '
                  'befejezés-érték: a csapat/játékos a helyzetei felett '
                  'teljesített. Ziccer: legalább 0,5 xG értékű helyzet '
                  '(gól / összes).</p>')
            # Ítélet: a helyzetek alapján is az nyert-e, aki a táblán?
            try:
                from .coach_summary import _xg_verdict
                verdict = _xg_verdict(th, ta, home, away)
                if verdict:
                    xg_html += (f'<p class="note"><b>{escape(verdict.strip())}'
                                "</b></p>")
            except Exception:
                pass
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
            # A fal kulcsembere: a legtöbb blokkot jegyző védő (2+ blokk).
            try:
                from .defense import detect_blocks
                blk = detect_blocks(match)
                tops = []
                for side, name in (("home", home), ("away", away)):
                    bl = blk[side].get("blockers") or []
                    if bl and bl[0]["blocks"] >= 2:
                        tops.append(f"{name}: {bl[0]['player_id']}. játékos "
                                    f"({bl[0]['blocks']} blokk)")
                if tops:
                    defense_html += ('<p class="note">A fal kulcsembere — '
                                     + escape(" · ".join(tops)) + "</p>")
            except Exception:
                pass
        # Egyéni védekezés: blokk + labdaszerzés + őrzés egy táblában
        # — ki mennyit tett hozzá a védekezéshez, játékosonként.
        try:
            from .defense import ball_winners, detect_blocks, marking_pairs
            blk_pd = detect_blocks(match)
            bw_pd = ball_winners(match)
            mk_pd = marking_pairs(match)
            fps_pd = match.meta.fps if match.meta.fps > 0 else 25.0
            jersey_pd: dict = {}
            for fr_ in match.frames:
                for p_ in fr_.players:
                    if (p_.jersey_number is not None
                            and p_.track_id not in jersey_pd):
                        jersey_pd[p_.track_id] = p_.jersey_number
            pd_rows = []
            for side, name in (("home", home), ("away", away)):
                acc_pd: dict = {}

                def _rec(tid):
                    return acc_pd.setdefault(
                        tid, {"blocks": 0, "steals": 0,
                              "mark_s": 0.0, "mark_d": None})
                for e_ in blk_pd[side].get("events", []):
                    if e_.get("player_id") is not None:
                        _rec(e_["player_id"])["blocks"] += 1
                for w_ in bw_pd[side]["players"]:
                    _rec(w_["player_id"])["steals"] += w_["steals"]
                for d_ in mk_pd[side]["defenders"]:
                    r_ = _rec(d_["defender"])
                    r_["mark_s"] += d_["frames"] / fps_pd
                    r_["mark_d"] = d_["avg_dist_m"]
                ranked = sorted(
                    acc_pd.items(),
                    key=lambda kv: -(kv[1]["blocks"] * 2
                                     + kv[1]["steals"] * 2
                                     + kv[1]["mark_s"] / 60.0))[:4]
                for tid, r_ in ranked:
                    if (not r_["blocks"] and not r_["steals"]
                            and r_["mark_s"] < 10.0):
                        continue
                    j_ = jersey_pd.get(tid)
                    lab_ = (f"{j_}-es" if j_ is not None
                            else f"{tid}. játékos")
                    mark_c = (f'{r_["mark_s"]:.0f} mp'
                              + (f' · {r_["mark_d"]:.1f} m'
                                 if r_["mark_d"] is not None else "")
                              if r_["mark_s"] >= 10.0 else "—")
                    pd_rows.append(
                        f"<tr><td>{escape(name)}</td>"
                        f"<td>{escape(lab_)}</td>"
                        f'<td class="num">{r_["blocks"] or "—"}</td>'
                        f'<td class="num">{r_["steals"] or "—"}</td>'
                        f'<td class="num">{mark_c}</td></tr>')
            if pd_rows:
                defense_html += (
                    "<h2>Egyéni védekezés</h2>"
                    "<table><tr><th>Csapat</th><th>Játékos</th>"
                    '<th class="num">Blokk</th>'
                    '<th class="num">Labdaszerzés</th>'
                    '<th class="num">Őrzés (idő · átl. táv)</th></tr>'
                    + "".join(pd_rows) + "</table>"
                    + '<p class="note">A védekezés három egyéni jele '
                      'egy helyen: blokk, labdaszerzés és emberfogás. '
                      'Csapatonként a legaktívabb négy védő.</p>')
        except Exception:
            pass
        # Őrzési párok: ki kit fogott, milyen szorosan (védőnként a
        # leggyakoribb őrzött, max 4 pár csapatonként) — akkor is van
        # értelme, ha kapott lövésből kevés volt.
        try:
            from .defense import marking_pairs
            mk = marking_pairs(match)
            mrows = []
            for side, name in (("home", home), ("away", away)):
                for pr_ in mk[side]["pairs"][:4]:
                    dj = pr_["defender_jersey"]
                    aj = pr_["attacker_jersey"]
                    dlab = (f"{dj}-es" if dj is not None
                            else f"{pr_['defender']}. játékos")
                    alab = (f"{aj}-es" if aj is not None
                            else f"{pr_['attacker']}. játékos")
                    mrows.append(
                        f"<tr><td>{escape(name)}</td>"
                        f"<td>{escape(dlab)}</td>"
                        f"<td>{escape(alab)}</td>"
                        f'<td class="num">{pr_["share_pct"]:.0f}%</td>'
                        f'<td class="num">{pr_["avg_dist_m"]:.1f} m'
                        "</td></tr>")
            if mrows:
                defense_html += (
                    "<h2>Őrzési párok (ki kit fogott)</h2>"
                    "<table><tr><th>Védekező csapat</th><th>Védő</th>"
                    "<th>Őrzött támadó</th>"
                    '<th class="num">Idő-arány</th>'
                    '<th class="num">Átl. táv</th></tr>'
                    + "".join(mrows) + "</table>"
                    + '<p class="note">Idő-arány: a védő őrzés-'
                      'idejének hány %-a jutott erre a támadóra; '
                      'átl. táv: átlagosan milyen messze állt tőle. '
                      '2,5 m felett laza az őrzés.</p>')
        except Exception:
            pass
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
        # Betörés-folyosó sora: hol jön be ellenük a labdás ember
        # (a védekező oszlopában az ELLENFÉL fő betörő-sávja).
        try:
            from .defense import breakthrough_lanes
            _bl = breakthrough_lanes(match)
            def _bl_txt(def_side):
                att = "away" if def_side == "home" else "home"
                r = _bl[att]
                if r["entries"] < 5 or not r["top_lane"]:
                    return "—"
                top = r["lanes"][r["top_lane"]]
                return (f'{r["top_lane"]} '
                        f'({100.0 * top["entries"] / r["entries"]:.0f}%)')
            if _bl_txt("home") != "—" or _bl_txt("away") != "—":
                rows.append(("Betörés-folyosó (ellenük)",
                             _bl_txt("home"), _bl_txt("away")))
        except Exception:
            pass
        # Rotáció sora: bevetett játékosok (alapemberek) csapatonként.
        try:
            from .stats import rotation_depth
            _rd = rotation_depth(match)
            if any(_rd[s_]["used"] >= 6 for s_ in ("home", "away")):
                def _rd_txt(side):
                    r = _rd[side]
                    if r["used"] < 6:
                        return "—"
                    return f'{r["used"]} ({r["regulars"]} alapember)'
                rows.append(("Bevetett játékos",
                             _rd_txt("home"), _rd_txt("away")))
        except Exception:
            pass
        # Passz-lánc sora: átlagos passz-szám támadásonként.
        try:
            from .attack_types import pass_chains
            _pc = pass_chains(match)
            if any(_pc[s_]["attacks"] >= 5
                   and _pc[s_]["avg_passes"] is not None
                   for s_ in ("home", "away")):
                def _pc_txt(side):
                    r = _pc[side]
                    if r["attacks"] < 5 or r["avg_passes"] is None:
                        return "—"
                    txt = f'{r["avg_passes"]:.1f}'
                    if r["best_bucket"]:
                        txt += f' (top: {r["best_bucket"]})'
                    return txt
                rows.append(("Passz / támadás",
                             _pc_txt("home"), _pc_txt("away")))
        except Exception:
            pass
        # Beállós támadás sora: a támadások hányada megy a beállón át.
        try:
            from .attack_types import pivot_usage
            _pu = pivot_usage(match)
            if any(_pu[s_]["attacks"] >= 5
                   and _pu[s_]["pivot_share_pct"] is not None
                   for s_ in ("home", "away")):
                def _pu_txt(side):
                    r = _pu[side]
                    if r["attacks"] < 5 or r["pivot_share_pct"] is None:
                        return "—"
                    txt = f'{r["pivot_share_pct"]:.0f}%'
                    if r["pivot_goal_pct"] is not None:
                        txt += f' (gól {r["pivot_goal_pct"]:.0f}%)'
                    return txt
                rows.append(("Beállós támadás",
                             _pu_txt("home"), _pu_txt("away")))
        except Exception:
            pass
        # Támadás-szélesség sora: szélesen vagy szűken támadnak-e.
        try:
            from .attack_types import attack_width
            _aw = attack_width(match)
            if any(_aw[s_]["avg_width_m"] is not None
                   for s_ in ("home", "away")):
                def _aw_txt(side):
                    v = _aw[side]["avg_width_m"]
                    return f"{v:.1f} m" if v is not None else "—"
                rows.append(("Támadás-szélesség (átlag)",
                             _aw_txt("home"), _aw_txt("away")))
        except Exception:
            pass
        # Gólcsend sora: a leghosszabb saját gól nélküli időszak, ha
        # legalább az egyik oldalon érdemi (5+ perc).
        try:
            from .momentum import goal_droughts
            _dr = goal_droughts(match)
            if any(_dr[s_]["longest_s"] >= 300.0
                   for s_ in ("home", "away")):
                def _dr_txt(side):
                    r = _dr[side]
                    if r["longest_s"] < 300.0:
                        return "—"
                    return (f'{r["longest_s"] / 60:.0f} perc '
                            f'({_fmt_clock(r["start_s"])}–'
                            f'{_fmt_clock(r["end_s"])})')
                rows.append(("Leghosszabb gólcsend",
                             _dr_txt("home"), _dr_txt("away")))
        except Exception:
            pass
        # Előny-kezelés sora: támadás-hossz vezetve/hátrányban.
        try:
            from .attack_types import pace_by_score
            _pb = pace_by_score(match)

            def _pb_txt(side):
                rec_l = _pb[side]["leading"]
                rec_t = _pb[side]["trailing"]
                if rec_l["avg_s"] is None or rec_t["avg_s"] is None:
                    return "—"
                return (f'{rec_l["avg_s"]:.0f} / {rec_t["avg_s"]:.0f}'
                        " mp")
            if _pb_txt("home") != "—" or _pb_txt("away") != "—":
                rows.append(("Támadás-hossz vezetve / hátrányban",
                             _pb_txt("home"), _pb_txt("away")))
        except Exception:
            pass
        # Kiállítás-mérleg sora (ha volt emberhátrány) — a kiülőkkel.
        try:
            from .rules import detect_powerplay, suspended_players
            _pp = detect_powerplay(match)
            if _pp:
                n_pp = {"home": 0, "away": 0}
                for w_ in _pp:
                    n_pp[w_["team_down"]] += 1
                sp_ = suspended_players(match)

                def _pp_txt(side):
                    who = " · ".join(
                        f"{e_['player_id']}."
                        for e_ in (sp_.get(side) or [])[:2])
                    base = str(n_pp[side])
                    return f"{base} ({who})" if who else base
                rows.append(("Kiállítás (2 perc)",
                             _pp_txt("home"), _pp_txt("away")))
        except Exception:
            pass
        # Hétméteres-mérleg sora (ha volt büntető).
        try:
            from .rules import seven_meter_summary
            _sm = seven_meter_summary(match)
            if any(_sm[s_]["attempts"] for s_ in ("home", "away")):
                def _sm_txt(side):
                    r = _sm[side]
                    return (f"{r['goals']}/{r['attempts']}"
                            if r["attempts"] else "—")
                rows.append(("Hétméteres (gól/kísérlet)",
                             _sm_txt("home"), _sm_txt("away")))
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
        # Visszarendeződés: labdavesztés után hány mp a felálló védelem.
        try:
            from .defense import transition_recovery
            _tr = transition_recovery(match)
            if any(_tr[s_]["transitions"] >= 4 for s_ in ("home", "away")):
                def _tr_txt(side):
                    r = _tr[side]
                    return (f'{r["avg_s"]:.1f} mp'
                            if r["transitions"] >= 4 else "—")
                rows.append(("Visszarendeződés (átlag)",
                             _tr_txt("home"), _tr_txt("away")))
        except Exception:
            pass
        # Megmentett gólok (GSAx): kapott gól a helyzet-minőséghez mérve.
        try:
            from .xg import xg_prevented
            _xp = xg_prevented(match)
            if (_xp["home"]["faced_xg"] + _xp["away"]["faced_xg"]) > 0:
                rows.append(("Megmentett gól (GSAx)",
                             f'{_xp["home"]["prevented"]:+.1f}',
                             f'{_xp["away"]["prevented"]:+.1f}'))
        except Exception:
            pass
        # Csapatonkénti tempó: támadás/perc (elég hosszú felvételen).
        try:
            from .attack_types import match_pace
            _pcr = match_pace(match)
            if _pcr.get("available") and _pcr["duration_min"] > 0:
                dm = _pcr["duration_min"]
                rows.append(("Támadás / perc",
                             f"{_pcr['home_attacks'] / dm:.1f}",
                             f"{_pcr['away_attacks'] / dm:.1f}"))
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
    # Meccs-tempó a fejlécbe (támadás/perc, ha elég hosszú a felvétel).
    try:
        from .attack_types import match_pace
        _pc = match_pace(match)
        if _pc.get("available"):
            header_bits.append(
                f'tempó: {_pc["per_min"]:.1f} támadás/perc '
                f'({_pc["label"]})')
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
            tp_txt = ""
            try:
                from .momentum import win_probability
                tp = win_probability(match).get("turning_point")
                if tp is not None and abs(tp["to_p"] - tp["from_p"]) >= 0.2:
                    tp_txt = (f' · fordulópont: {int(tp["t_s"] // 60)}. perc '
                              f'({100 * tp["from_p"]:.0f}% → '
                              f'{100 * tp["to_p"]:.0f}%)')
            except Exception:
                pass
            prog_line = (f'<div class="sub">A meccs {prog["lead_changes"]}-szor '
                         f'fordult · legnagyobb előny: {escape(top)} +{top_v}'
                         f'{cb_txt}{cl_txt}{tp_txt}</div>')
    except Exception:
        pass
    # A meccs története egy bekezdésben — ugyanaz a szöveg, mint az
    # edzői összefoglaló nyitó-szekciója.
    story_html = ""
    try:
        from .coach_summary import _story_section
        st = _story_section(match, home, away)
        if st:
            story_html = ('<p class="cs"><b>A meccs története.</b> '
                          + escape(st["body"]) + "</p>")
    except Exception:
        pass
    header_extra = (
        (f'<div class="sub">{" · ".join(header_bits)}</div>'
         if header_bits else "") + prog_line + story_html)

    # Kapus-teljesítmény (ha van kapus-jelölés a meccsen).
    gk_html = ""
    try:
        from .goalkeeper import OUTLET_FAST_S, goalkeeper_stats, outlet_speed
        gstats = goalkeeper_stats(match)
        try:
            from .xg import xg_saved
            xsaved = xg_saved(match)
        except Exception:
            xsaved = {}
        try:
            outlets = outlet_speed(match)
        except Exception:
            outlets = {}
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
            # Zóna-védés% (a legalább 2 lövést kapott zónákra, kapura
            # tartó lövésszám szerint rendezve) — a kapus teljes térképe.
            zsp_txt = " · ".join(
                f"{z} {rec['zone_save_pct'][z]:.0f}%"
                for z, _n in sorted(otz.items(), key=lambda kv: -kv[1])
                if otz.get(z, 0) >= 2 and z in rec.get("zone_save_pct", {})
            ) or "—"
            # Indítás: védés utáni felhozatal a felezőig (ha mérhető).
            orec = outlets.get(key) or {}
            if orec.get("outlets"):
                o_txt = (f"{orec['avg_s']:.0f} mp átlag "
                         f"({orec['fast']}/{orec['outlets']} gyors)")
            else:
                o_txt = "—"
            rows.append(f"<tr><td>{name}</td>"
                        f"<td class='num'>{rec['on_target']}</td>"
                        f"<td class='num'>{rec['saves']}</td>"
                        f"<td class='num'>{rec['conceded']}</td>"
                        f"<td class='num'><b>{rec['save_pct']:.0f}%</b></td>"
                        f"<td class='num'>{seven}</td>"
                        f"<td>{escape(zones)}</td>"
                        f"<td>{escape(zsp_txt)}</td>"
                        f"<td>{escape(weak)}</td>"
                        f"<td>{escape(o_txt)}</td>"
                        f"<td class='num'>{xsaved.get(key, 0.0):.1f}</td>"
                        "</tr>")
        if rows:
            gk_html = ("<h2>Kapus-teljesítmény</h2><table>"
                       "<tr><th>Csapat</th><th class='num'>Kapura</th>"
                       "<th class='num'>Védés</th><th class='num'>Kapott</th>"
                       "<th class='num'>Védés%</th>"
                       "<th class='num'>7 m-es (fogott/kapott)</th>"
                       "<th>Kapott gólok zónái</th>"
                       "<th>Zóna-védés%</th>"
                       "<th>Leggyengébb zóna</th>"
                       "<th>Indítás (felezőig)</th>"
                       "<th class='num'>Hárított xG</th></tr>"
                       + "".join(rows) + "</table>"
                       + '<p class="note">Indítás: védés után ennyi idő '
                         "alatt ért át a labda a felezőn; gyors = "
                         f"{OUTLET_FAST_S:.0f} mp-en belül. Hárított xG: "
                         "a fogott lövések helyzet-értékének összege — a "
                         "nehéz védéseket díjazza.</p>")
            # Kapus-csere jegyzet (ha volt): mikor és milyen mérleggel.
            try:
                from .goalkeeper import goalkeeper_timeline
                tl_all = goalkeeper_timeline(match)
                notes_gk = []
                for key, name in (("home", home), ("away", away)):
                    tl = tl_all.get(key) or {}
                    if not tl.get("changes"):
                        continue
                    mins = int(tl["changes"][0] // 60)
                    pk = tl.get("per_keeper", {})
                    def _gk_bal(r) -> str:
                        # GSAx kapusonként, ha mérhető (3+ lövésnél).
                        if r.get("on_target", 0) >= 3 and \
                                "prevented" in r:
                            return f", {r['prevented']:+.1f} xG"
                        return ""

                    per = " · ".join(
                        f"{st['track_id']}. játékos "
                        f"{pk[st['track_id']]['saves']}/"
                        f"{pk[st['track_id']]['on_target']} védés"
                        f"{_gk_bal(pk[st['track_id']])}"
                        for st in tl.get("stints", [])[:2]
                        if st["track_id"] in pk
                        and pk[st["track_id"]]["on_target"])
                    note = f"{name}: kapus-csere a {mins}. perc körül"
                    if per:
                        note += f" ({per})"
                    notes_gk.append(note)
                if notes_gk:
                    gk_html += ('<p class="note">'
                                + escape(" — ".join(notes_gk)) + "</p>")
            except Exception:
                pass
    except Exception:
        pass

    # Felállások: a becsült posztok csapatonként, egy-egy sorban.
    lineups_html = ""
    try:
        from .roles import estimate_positions
        est_lu = estimate_positions(match)
        lu_rows = []
        order_lu = ["irányító", "átlövő", "beálló", "szélső"]
        for side, name in (("home", home), ("away", away)):
            by_post: dict = {}
            for tid, r_ in sorted(est_lu.get(side, {}).items()):
                by_post.setdefault(r_["poszt"], []).append(f"{tid}.")
            if not by_post:
                continue
            parts_lu = [f"{p_}: {', '.join(by_post[p_])}"
                        for p_ in order_lu if p_ in by_post]
            lu_rows.append(f"<tr><td>{escape(name)}</td>"
                           f"<td>{escape(' · '.join(parts_lu))}</td></tr>")
        if lu_rows:
            lineups_html = (
                "<h2>Felállások (becsült posztok)</h2><table>"
                "<tr><th>Csapat</th><th>Posztok</th></tr>"
                + "".join(lu_rows) + "</table>"
                + '<p class="note">A poszt a támadó-fázis átlag-helyéből '
                  "becsült címke (min. 4 mp-nyi minta játékosonként).</p>")
    except Exception:
        pass

    # Kulcsemberek: a játékos-profil rétegek egy kompakt táblában —
    # a közös match_key_players rétegből (azonos küszöbök a felderítéssel).
    keyplayers_html = ""
    try:
        from .scouting import match_key_players
        kp = match_key_players(match)
        rows_kp = []
        for side, name in (("home", home), ("away", away)):
            for it in kp.get(side, []):
                rows_kp.append(
                    f"<tr><td>{escape(name)}</td>"
                    f"<td>{escape(it['role'])}</td>"
                    f"<td>{it['player_id']}. játékos</td>"
                    f"<td>{escape(it['detail'])}</td></tr>")
        if rows_kp:
            keyplayers_html = (
                "<h2>Kulcsemberek</h2><table>"
                "<tr><th>Csapat</th><th>Szerep</th><th>Játékos</th>"
                "<th>Mérleg</th></tr>" + "".join(rows_kp) + "</table>"
                + '<p class="note">A meccs játékos-profiljai egy '
                  "helyen — a felderítési kulcsok ugyanezekből a "
                  "számokból készülnek.</p>")
    except Exception:
        pass  # a jelentés e blokk nélkül is teljes

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

  {lineups_html}

  {keyplayers_html}

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


def player_report_html(match, track_id: int) -> str:
    """Játékos-lap: egy játékos meccs-riportja kiosztható, egyoldalas
    HTML-ben — játék-mérleg + fizikai mutatók, a meccs rétegeiből.

    A track_id a játékos bármelyik trackje lehet: a mezszám-összevonás
    után a teljes track-csoport adatai kerülnek a lapra. ValueError,
    ha a track nem szerepel a meccsen.
    """
    from .stats import aggregate_by_jersey, compute_player_stats

    meta = match.meta
    fps = meta.fps if meta.fps > 0 else 25.0
    stats = compute_player_stats(match)
    team_of: dict = {}
    jersey_of: dict = {}
    for fr in match.frames:
        for p in fr.players:
            team_of.setdefault(p.track_id,
                               getattr(p.team, "value", p.team))
            if p.jersey_number is not None:
                jersey_of.setdefault(p.track_id, p.jersey_number)
    row = next((g for g in aggregate_by_jersey(stats, team_of,
                                               jersey_of, fps=fps)
                if track_id in g["track_ids"]), None)
    if row is None:
        raise ValueError("ismeretlen track a meccsen")
    tids = set(row["track_ids"])
    team_name = (meta.home_team if row["team"] == "home"
                 else meta.away_team)

    # Kapus-e a játékos? A kapus lapján a védés-mérleg a főszereplő.
    is_gk = False
    gk_side = None
    for fr in match.frames:
        for p in fr.players:
            if p.track_id in tids and p.role == "kapus":
                is_gk = True
                gk_side = getattr(p.team, "value", p.team)
                break
        if is_gk:
            break

    gk_items: list[str] = []
    if is_gk:
        try:
            from .goalkeeper import (OUTLET_FAST_S, goalkeeper_stats,
                                     goalkeeper_timeline, outlet_speed)
            tlk = goalkeeper_timeline(match).get(gk_side) or {}
            pk = tlk.get("per_keeper", {})
            rec_gk = next((pk[t_] for t_ in tids if t_ in pk), None)
            if rec_gk and rec_gk.get("on_target"):
                gk_items.append(_metric("Kapura tartó lövés",
                                        str(rec_gk["on_target"])))
                gk_items.append(_metric(
                    "Védés",
                    f"{rec_gk['saves']} "
                    f"({rec_gk['save_pct']:.0f}%)"))
                if "prevented" in rec_gk:
                    gk_items.append(_metric(
                        "Mérleg a helyzetekhez képest (GSAx)",
                        f"{rec_gk['prevented']:+.1f}"))
            # Ha ő az egyetlen kapus, a csapat-szintű kapus-számok is
            # az övéi: hetes-mérleg és indítás-átlag.
            if len(pk) <= 1:
                gs = goalkeeper_stats(match).get(gk_side) or {}
                if gs.get("seven_faced"):
                    gk_items.append(_metric(
                        "Hetes-védés",
                        f"{gs['seven_saved']}/{gs['seven_faced']}"))
                orec = outlet_speed(match).get(gk_side) or {}
                if orec.get("outlets", 0) >= 2 \
                        and orec.get("avg_s") is not None:
                    lab = ("gyors" if orec["avg_s"] <= OUTLET_FAST_S
                           else "átlagos")
                    gk_items.append(_metric(
                        "Indítás (átlag a felezőig)",
                        f"{orec['avg_s']:.1f} s · {lab}"))
                # A kapott hetesek irány-képe: merre lőtték ellened.
                try:
                    from .rules import (SEVEN_DIR_HU as hu_d,
                                        seven_meter_outcomes)
                    dcnt: dict = {}
                    for sm in seven_meter_outcomes(match):
                        if sm.get("team") == gk_side:
                            continue  # a sajátjaik dobták, nem ellened
                        if sm.get("irany"):
                            dcnt[sm["irany"]] = \
                                dcnt.get(sm["irany"], 0) + 1
                    if dcnt:
                        gk_items.append(_metric(
                            "Hetesek ellened (irányok)",
                            " · ".join(
                                f"{hu_d.get(d_, d_)} {n_}×"
                                for d_, n_ in sorted(
                                    dcnt.items(),
                                    key=lambda kv: -kv[1]))))
                except Exception:
                    pass
        except Exception:
            pass

    game_items: list[str] = []
    # Játék-mérleg: gól/lövés, xG, ziccer — a meccs xG-rétegéből.
    try:
        from .xg import BIG_CHANCE_XG, match_xg
        r_all = match_xg(match)
        goals = shots = 0
        xg_sum = diff_sum = 0.0
        for r_ in r_all.get("shooters", []):
            if r_["player_id"] in tids:
                goals += r_["goals"]
                shots += r_["shots"]
                xg_sum += r_["xg"]
                diff_sum += r_["diff"]
        if shots:
            game_items.append(_metric("Gól / lövés", f"{goals}/{shots}"))
            game_items.append(_metric("Várható gól (xG)",
                                      f"{xg_sum:.1f}"))
            game_items.append(_metric("Befejezés (gól−xG)",
                                      f"{diff_sum:+.1f}"))
        big_g = big_n = 0
        for sh in r_all.get("shots", []):
            if sh.get("player_id") in tids \
                    and sh.get("xg", 0.0) >= BIG_CHANCE_XG:
                big_n += 1
                big_g += int(sh.get("outcome") == "goal")
        if big_n:
            game_items.append(_metric("Ziccer (gól/össz)",
                                      f"{big_g}/{big_n}"))
    except Exception:
        pass
    try:
        from .defense import detect_blocks
        blk = detect_blocks(match)
        n_blk = sum(1 for side in ("home", "away")
                    for e_ in blk[side].get("events", [])
                    if e_.get("player_id") in tids)
        if n_blk:
            game_items.append(_metric("Blokk", str(n_blk)))
    except Exception:
        pass
    # Emberfogásod: mennyit őriztél, milyen szorosan, és kit fogtál
    # a leggyakrabban — az őrzési párok rétegből.
    try:
        from .defense import marking_pairs
        mk_pr = marking_pairs(match)
        rec_m = next((d_ for d_ in mk_pr[row["team"]]["defenders"]
                      if d_["defender"] in tids), None)
        if rec_m:
            game_items.append(_metric(
                "Emberfogás (őrzés-idő)",
                f"{rec_m['frames'] / fps:.0f} s · átl. "
                f"{rec_m['avg_dist_m']:.1f} m"))
            pr_m = next((p_ for p_ in mk_pr[row["team"]]["pairs"]
                         if p_["defender"] in tids), None)
            if pr_m is not None:
                aj_m = pr_m["attacker_jersey"]
                alab_m = (f"{aj_m}-es" if aj_m is not None
                          else f"{pr_m['attacker']}. játékos")
                game_items.append(_metric(
                    "Leggyakoribb őrzötted",
                    f"{alab_m} ({pr_m['share_pct']:.0f}%)"))
    except Exception:
        pass
    # Labdaszerzés: a játékos szerzett labdái (birtokos-váltásból).
    try:
        from .defense import ball_winners
        bw_pl = ball_winners(match)[row["team"]]
        n_bw = sum(p_["steals"] for p_ in bw_pl["players"]
                   if p_["player_id"] in tids)
        if n_bw:
            game_items.append(_metric("Labdaszerzés", str(n_bw)))
    except Exception:
        pass
    # Beálló-szerep: ha a játékos a becsült beálló, a csapat beállós
    # támadás-mérlege az ő lapjára tartozik.
    try:
        from .attack_types import pivot_usage
        pu_pl = pivot_usage(match)[row["team"]]
        if (set(pu_pl["pivot_ids"]) & tids
                and pu_pl["attacks"] >= 5
                and pu_pl["pivot_share_pct"] is not None):
            val_pl = (f"{pu_pl['pivot_attacks']} támadás "
                      f"({pu_pl['pivot_share_pct']:.0f}%), "
                      f"{pu_pl['pivot_goals']} gól")
            game_items.append(_metric("Beállós támadás (rajtad át)",
                                      val_pl))
    except Exception:
        pass
    seven_dirs: dict = {}
    try:
        from .rules import seven_meter_outcomes
        sv_a = sv_g = 0
        for sm in seven_meter_outcomes(match):
            if sm.get("shooter_id") in tids:
                sv_a += 1
                sv_g += int(sm["outcome"] == "gól")
                if sm.get("irany"):
                    seven_dirs[sm["irany"]] = \
                        seven_dirs.get(sm["irany"], 0) + 1
        if sv_a:
            game_items.append(_metric("Hetes (gól/kísérlet)",
                                      f"{sv_g}/{sv_a}"))
        if seven_dirs:
            from .rules import SEVEN_DIR_HU as hu_d7
            game_items.append(_metric(
                "Heteseid irányai",
                " · ".join(f"{hu_d7.get(d_, d_)} {n_}×"
                           for d_, n_ in sorted(
                               seven_dirs.items(),
                               key=lambda kv: -kv[1]))))
    except Exception:
        pass
    try:
        from .rules import seven_meter_earners, suspension_earners
        e7 = sum(e_["earned"] for side in ("home", "away")
                 for e_ in seven_meter_earners(match)[side]
                 if e_["player_id"] in tids)
        if e7:
            game_items.append(_metric("Kiharcolt hetes", str(e7)))
        e2 = sum(e_["earned"] for side in ("home", "away")
                 for e_ in suspension_earners(match)[side]
                 if e_["player_id"] in tids)
        if e2:
            game_items.append(_metric("Kiharcolt 2 perc", str(e2)))
    except Exception:
        pass
    try:
        from .attack_types import fast_break_finishers
        fbg = sum(f_["goals"] for side in ("home", "away")
                  for f_ in fast_break_finishers(match)[side]
                  if f_["player_id"] in tids)
        if fbg:
            game_items.append(_metric("Kontra-gól", str(fbg)))
    except Exception:
        pass

    poszt = ""
    try:
        from .roles import estimate_positions
        est = estimate_positions(match)
        poszt = next((r_["poszt"] for side in ("home", "away")
                      for tid_, r_ in est.get(side, {}).items()
                      if tid_ in tids), "")
    except Exception:
        pass

    fade = ""
    try:
        from .stats import player_fatigue
        drops = [r_["drop_pct"] for r_ in player_fatigue(match)
                 if r_["track_id"] in tids]
        if drops:
            d = max(drops)
            fade = f"−{d:.0f}%" if d > 0 else f"+{-d:.0f}%"
    except Exception:
        pass

    zones = row["zone_seconds"]
    phys_items = [
        _metric("Táv", f"{row['distance_m']:.0f} m"),
        _metric("Átl. sebesség", f"{row['avg_speed_ms']:.1f} m/s"),
        _metric("Max sebesség",
                f"{row['top_speed_ms'] * 3.6:.1f} km/h"),
        _metric("Sprint", str(row["sprint_count"])),
        _metric("Sprint-táv", f"{row['sprint_distance_m']:.0f} m"),
        _metric("Sprintben töltött idő",
                f"{zones.get('sprint', 0.0):.0f} s"),
    ]
    if fade:
        phys_items.append(_metric("2. félidei tempó", fade))

    game_html = ("".join(game_items)
                 or '<p class="empty">Nincs mért játék-esemény '
                    '(lövés, blokk, hetes) ennél a játékosnál.</p>')

    # Mire figyelj: legfeljebb 3 személyes, tényeken álló javaslat —
    # ugyanazokkal a küszöbökkel, mint a csapat-szintű rétegek.
    tips: list[str] = []
    try:
        from .xg import BIG_CHANCE_XG, match_xg
        r_tip = match_xg(match)
        t_goals = t_shots = 0
        t_diff = 0.0
        big_missed_n = 0
        for r_ in r_tip.get("shooters", []):
            if r_["player_id"] in tids:
                t_goals += r_["goals"]
                t_shots += r_["shots"]
                t_diff += r_["diff"]
        for sh in r_tip.get("shots", []):
            if sh.get("player_id") in tids \
                    and sh.get("xg", 0.0) >= BIG_CHANCE_XG \
                    and sh.get("outcome") != "goal":
                big_missed_n += 1
        if big_missed_n >= 2:
            tips.append(
                f"Ziccer-befejezés: {big_missed_n} nagy helyzet maradt "
                "kihasználatlan — a heti edzésbe férjen bele ziccer-"
                "sorozat fáradt lábbal is.")
        elif t_shots >= 3 and t_diff <= -1.0:
            tips.append(
                f"Befejezés: a helyzeteid alatt teljesítettél "
                f"({t_diff:+.1f} gól a várhatóhoz képest) — a lövés-"
                "kiválasztáson és a nyugodt befejezésen múlik.")
    except Exception:
        pass
    try:
        from .stats import player_fatigue
        drops_t = [r_["drop_pct"] for r_ in player_fatigue(match)
                   if r_["track_id"] in tids]
        if drops_t and max(drops_t) >= 20.0:
            tips.append(
                f"Erőnlét/rotáció: a 2. félidőre −{max(drops_t):.0f}% "
                "tempó — beszélj az edződdel a csere-időzítésről, vagy "
                "célzott állóképesség-blokk jöhet.")
    except Exception:
        pass
    try:
        from .rules import suspended_players
        n_susp_t = sum(e_["suspensions"]
                       for side in ("home", "away")
                       for e_ in suspended_players(match)[side]
                       if e_["player_id"] in tids)
        if n_susp_t >= 1:
            tips.append(
                f"Fegyelem: {n_susp_t} kiállítás — a betörőt tested "
                "helyzetével lassítsd, ne fogással: a következő 2 perc "
                "a csapatnak gólokba kerül.")
    except Exception:
        pass
    try:
        from .defense import MARK_LOOSE_M, marking_pairs
        rec_mk = next((d_ for d_ in
                       marking_pairs(match)[row["team"]]["defenders"]
                       if d_["defender"] in tids), None)
        if rec_mk and rec_mk["frames"] >= 50                 and rec_mk["avg_dist_m"] >= MARK_LOOSE_M:
            tips.append(
                f"Emberfogás: átlag {rec_mk['avg_dist_m']:.1f} m-re "
                "álltál az őrzöttedtől — egy-egy ellen tapadj "
                "karnyújtásnyira, a lövőt ne engedd felugrani.")
    except Exception:
        pass
    try:
        from .rules import seven_meter_outcomes
        sv_a2 = sv_g2 = 0
        for sm in seven_meter_outcomes(match):
            if sm.get("shooter_id") in tids:
                sv_a2 += 1
                sv_g2 += int(sm["outcome"] == "gól")
        if sv_a2 >= 2 and sv_g2 / sv_a2 <= 0.5:
            tips.append(
                f"Hetes-rutin: {sv_g2}/{sv_a2} a mérleged — nyomás "
                "alatti hetes-sorozatok edzésen, kapussal.")
        # Kiszámíthatóság: ha a mért heteseid nagy része egy sávba
        # megy, a kapusok előbb-utóbb rád tanulnak.
        n_d7 = sum(seven_dirs.values())
        if n_d7 >= 2 and max(seven_dirs.values()) / n_d7 >= 0.75:
            tips.append(
                "Hetes-irány: kiszámítható vagy — a mért heteseid "
                "nagy része ugyanabba a sávba megy; edzésen tudatosan "
                "váltogasd az irányt.")
    except Exception:
        pass
    # Kapus-javaslatok: forma-jel és a leggyengébb zóna — csak kapusnak.
    if is_gk:
        try:
            from .goalkeeper import goalkeeper_stats, goalkeeper_timeline
            pk_t = (goalkeeper_timeline(match).get(gk_side)
                    or {}).get("per_keeper", {})
            rec_t = next((pk_t[t_] for t_ in tids if t_ in pk_t), None)
            if rec_t and rec_t.get("on_target", 0) >= 3 \
                    and rec_t.get("prevented", 0.0) <= -2.0:
                tips.append(
                    f"Forma-jel: a helyzetekhez képest "
                    f"{rec_t['prevented']:+.1f} a mérleged — nézd vissza "
                    "a kapott gólokat: helyezkedés vagy időzítés?")
            if len(pk_t) <= 1:
                gs_t = goalkeeper_stats(match).get(gk_side) or {}
                zsp = gs_t.get("zone_save_pct", {})
                otz = gs_t.get("on_target_zones", {})
                cand = [(z_, p_) for z_, p_ in zsp.items()
                        if otz.get(z_, 0) >= 2]
                if cand:
                    z_, p_ = min(cand, key=lambda kv: kv[1])
                    if p_ <= 40.0:
                        tips.append(
                            f"Leggyengébb zónád: {z_} ({p_:.0f}% "
                            "védés) — célzott helyezkedés-gyakorlás "
                            "erre a sarokra, lövő-sorozattal.")
        except Exception:
            pass
    tips_html = ""
    if tips:
        tips_html = ("<h2>Mire figyelj</h2><ul>"
                     + "".join(f"<li>{escape(t_)}</li>"
                               for t_ in tips[:3]) + "</ul>")
    sub = f"{meta.home_team} vs {meta.away_team}"
    if meta.date:
        sub += f" · {meta.date}"
    if is_gk:
        sub += " · kapus"
    elif poszt:
        sub += f" · becsült poszt: {poszt}"
    gk_html = (f'<h2>Kapus-mérleg</h2><div class="metrics">'
               f'{"".join(gk_items)}</div>' if gk_items else "")
    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="utf-8">
<title>Játékos-lap — {escape(row['label'])}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI",
         Arial, sans-serif; color: #101722; background: #fff;
         line-height: 1.5; }}
  .page {{ max-width: 640px; margin: 0 auto; padding: 36px 32px 48px; }}
  header {{ border-bottom: 3px solid #12988a; padding-bottom: 14px;
           margin-bottom: 22px; }}
  .brand {{ font-size: 11px; letter-spacing: .22em;
           text-transform: uppercase; color: #8492A6; }}
  h1 {{ margin: 6px 0 2px; font-size: 26px; }}
  .sub {{ color: #4A5768; font-size: 13px; }}
  h2 {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
       color: #12988a; margin: 26px 0 10px; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  .metric {{ border: 1px solid #E3E8EF; border-radius: 10px;
            padding: 10px 14px; min-width: 120px; }}
  .mv {{ font-size: 20px; font-weight: 700; }}
  .ml {{ font-size: 11px; color: #8492A6; }}
  .empty {{ color: #8492A6; font-size: 13px; }}
  ul {{ margin: 8px 0 0; padding-left: 20px; }}
  li {{ font-size: 13px; margin-bottom: 6px; }}
  footer {{ margin-top: 30px; font-size: 11px; color: #8492A6; }}
</style>
</head>
<body><div class="page">
<header>
  <div class="brand">SPORT MACHINE · JÁTÉKOS-LAP</div>
  <h1>{escape(row['label'])} — {escape(team_name)}</h1>
  <div class="sub">{escape(sub)}</div>
</header>
{gk_html}
<h2>Játék-mérleg</h2>
<div class="metrics">{game_html}</div>
<h2>Fizikai mutatók</h2>
<div class="metrics">{"".join(phys_items)}</div>
{tips_html}
<footer>A számok a pálya-koordinátás követésből és a magyarázható
elemzési rétegekből jönnek — azonos küszöbökkel, mint a
meccsjelentésben.</footer>
</div></body></html>"""


def _trend_metrics_table(tr: dict) -> str:
    """A trend-mutatók táblája (régi/új/irány) — a fejlődés- és a
    szezon-riport közös építőeleme."""
    rows = []
    for m_ in tr.get("metrics", []):
        better = m_.get("better")
        cls = ("up" if better is True
               else "down" if better is False else "")
        arrow = ("▲" if better is True
                 else "▼" if better is False else "–")
        unit = m_.get("unit", "")
        rows.append(
            f"<tr><td>{escape(str(m_.get('label', '')))}</td>"
            f'<td class="num">{m_.get("older", 0):.1f}{escape(unit)}'
            "</td>"
            f'<td class="num">{m_.get("newer", 0):.1f}{escape(unit)}'
            "</td>"
            f'<td class="num {cls}">{arrow} '
            f'{m_.get("delta", 0):+.1f}{escape(unit)}</td></tr>')
    return ("<table><tr><th>Mutató</th>"
            '<th class="num">Régebbi</th><th class="num">Újabb</th>'
            '<th class="num">Változás</th></tr>'
            + "".join(rows) + "</table>") if rows else         '<p class="empty">Nincs összevethető mutató.</p>'


def trend_report_html(tr: dict) -> str:
    """Fejlődés-riport: a két időszak trend-összevetése nyomtatható
    HTML-ben — mutatónként régi/új érték és irány, plusz az összegző
    mondatok. A /scouting/trend kimenetét rendereli.
    """
    name = tr.get("team_name") or "Csapat"
    table = _trend_metrics_table(tr)
    summary = "".join(f"<li>{escape(s_)}</li>"
                      for s_ in tr.get("summary", []))
    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="utf-8">
<title>Fejlődés-riport — {escape(name)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI",
         Arial, sans-serif; color: #101722; background: #fff;
         line-height: 1.5; }}
  .page {{ max-width: 720px; margin: 0 auto; padding: 36px 32px 48px; }}
  header {{ border-bottom: 3px solid #12988a; padding-bottom: 14px;
           margin-bottom: 22px; }}
  .brand {{ font-size: 11px; letter-spacing: .22em;
           text-transform: uppercase; color: #8492A6; }}
  h1 {{ margin: 6px 0 2px; font-size: 26px; }}
  .sub {{ color: #4A5768; font-size: 13px; }}
  h2 {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
       color: #12988a; margin: 26px 0 10px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ padding: 7px 10px; border-bottom: 1px solid #E3E8EF;
           text-align: left; }}
  th.num, td.num {{ text-align: right; }}
  td.up {{ color: #0B7A45; font-weight: 600; }}
  td.down {{ color: #B42318; font-weight: 600; }}
  ul {{ margin: 8px 0 0; padding-left: 20px; }}
  li {{ font-size: 13px; margin-bottom: 6px; }}
  .empty {{ color: #8492A6; font-size: 13px; }}
  footer {{ margin-top: 30px; font-size: 11px; color: #8492A6; }}
</style>
</head>
<body><div class="page">
<header>
  <div class="brand">SPORT MACHINE · FEJLŐDÉS-RIPORT</div>
  <h1>{escape(name)}</h1>
  <div class="sub">Régebbi időszak: {tr.get("older_matches", 0)} meccs ·
  Újabb időszak: {tr.get("newer_matches", 0)} meccs — a darabszám-mutatók
  meccsenkénti átlagra normálva.</div>
</header>
<h2>Mutatók</h2>
{table}
<h2>Összegzés</h2>
<ul>{summary}</ul>
<footer>▲ javulás · ▼ romlás · – semleges irányú mutató. A nem mért
időszakok mutatói kimaradnak, hogy ne látsszanak hamis változásnak.
</footer>
</div></body></html>"""


def player_season_html(team: str, jersey: int, points: list[dict]) -> str:
    """Szezon játékos-lap: egy játékos meccsről meccsre, nyomtatható
    HTML-ben — a /players/trend pontjaiból (összesítő + meccs-tábla).
    """
    n = len(points)
    goals = sum(p_.get("goals", 0) for p_ in points)
    shots = sum(p_.get("shots", 0) for p_ in points)
    xg_vals = [p_["xg"] for p_ in points if p_.get("xg") is not None]
    xg_sum = round(sum(xg_vals), 1) if xg_vals else None
    minutes = round(sum(p_.get("minutes", 0.0) for p_ in points), 1)
    dist_km = round(sum(p_.get("distance_m", 0.0)
                        for p_ in points) / 1000.0, 1)
    sprints = sum(p_.get("sprint_count", 0) for p_ in points)
    top_kmh = round(max((p_.get("top_speed_ms", 0.0) for p_ in points),
                        default=0.0) * 3.6, 1)

    totals = [
        _metric("Meccs", str(n)),
        _metric("Gól / lövés", f"{goals}/{shots}"),
    ]
    if xg_sum is not None:
        totals.append(_metric("Várható gól (xG)", f"{xg_sum:.1f}"))
        totals.append(_metric("Befejezés (gól−xG)",
                              f"{goals - xg_sum:+.1f}"))
    totals += [
        _metric("Játékperc (mért)", f"{minutes:.0f}"),
        _metric("Táv összesen", f"{dist_km:.1f} km"),
        _metric("Sprint", str(sprints)),
        _metric("Csúcssebesség", f"{top_kmh:.1f} km/h"),
    ]
    # Kapus-összesítő: ha a mezszám kapusé, a védés-mérleg is a lapon.
    is_gk_season = any(p_.get("gk_on_target") for p_ in points)
    if is_gk_season:
        gk_on_sum = sum(p_.get("gk_on_target") or 0 for p_ in points)
        gk_sv_sum = sum(p_.get("gk_saves") or 0 for p_ in points)
        gk_prev_sum = sum(p_.get("gk_prevented") or 0.0
                          for p_ in points)
        if gk_on_sum:
            totals.append(_metric(
                "Védés összesen",
                f"{gk_sv_sum}/{gk_on_sum} "
                f"({100.0 * gk_sv_sum / gk_on_sum:.0f}%)"))
            totals.append(_metric("GSAx összesen",
                                  f"{gk_prev_sum:+.1f}"))

    # Emberfogás-összesítő és oszlopok: ha van mért őrzése a szezonban.
    has_marking = any(p_.get("mark_s") for p_ in points)
    if has_marking:
        mark_pts = [p_ for p_ in points if p_.get("mark_s")]
        m_total_s = sum(p_["mark_s"] for p_ in mark_pts)
        m_avg = (sum((p_.get("mark_dist") or 0.0) * p_["mark_s"]
                     for p_ in mark_pts) / m_total_s
                 if m_total_s else 0.0)
        totals.append(_metric("Őrzés összesen",
                              f"{m_total_s:.0f} mp · átl. "
                              f"{m_avg:.1f} m"))

    rows = []
    for p_ in points:
        when = p_.get("date") or p_.get("match_id", "")
        opp = p_.get("opponent") or "—"
        game = (f"{p_.get('goals', 0)}/{p_.get('shots', 0)}"
                if p_.get("shots") else "—")
        xg_c = (f"{p_['xg']:.1f}" if p_.get("xg") is not None else "—")
        diff_c = (f"{p_['xg_diff']:+.1f}"
                  if p_.get("xg_diff") is not None else "—")
        gk_cells = ""
        if is_gk_season:
            if p_.get("gk_on_target"):
                gk_cells = (
                    f'<td class="num">{p_.get("gk_saves", 0)}/'
                    f'{p_["gk_on_target"]}</td>'
                    f'<td class="num">'
                    f'{(p_.get("gk_prevented") or 0.0):+.1f}</td>')
            else:
                gk_cells = ('<td class="num">—</td>'
                            '<td class="num">—</td>')
        mark_cells = ""
        if has_marking:
            if p_.get("mark_s"):
                mark_cells = (
                    f'<td class="num">{p_["mark_s"]:.0f} mp · '
                    f'{(p_.get("mark_dist") or 0.0):.1f} m</td>')
            else:
                mark_cells = '<td class="num">—</td>'
        rows.append(
            f"<tr><td>{escape(str(when))}</td><td>{escape(opp)}</td>"
            f'<td class="num">{p_.get("minutes", 0):.0f}</td>'
            f'<td class="num">{game}</td>'
            f'<td class="num">{xg_c}</td>'
            f'<td class="num">{diff_c}</td>'
            + gk_cells + mark_cells +
            f'<td class="num">{p_.get("distance_m", 0):.0f} m</td>'
            f'<td class="num">{p_.get("sprint_count", 0)}</td></tr>')
    gk_heads = ('<th class="num">Védés</th><th class="num">GSAx</th>'
                if is_gk_season else "")
    mark_heads = ('<th class="num">Őrzés</th>' if has_marking else "")
    table = ("<table><tr><th>Dátum</th><th>Ellenfél</th>"
             '<th class="num">Perc</th><th class="num">Gól/lövés</th>'
             '<th class="num">xG</th><th class="num">+/−</th>'
             + gk_heads + mark_heads +
             '<th class="num">Táv</th><th class="num">Sprint</th></tr>'
             + "".join(rows) + "</table>")

    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="utf-8">
<title>Szezon-lap — #{jersey} ({escape(team)})</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI",
         Arial, sans-serif; color: #101722; background: #fff;
         line-height: 1.5; }}
  .page {{ max-width: 760px; margin: 0 auto; padding: 36px 32px 48px; }}
  header {{ border-bottom: 3px solid #12988a; padding-bottom: 14px;
           margin-bottom: 22px; }}
  .brand {{ font-size: 11px; letter-spacing: .22em;
           text-transform: uppercase; color: #8492A6; }}
  h1 {{ margin: 6px 0 2px; font-size: 26px; }}
  .sub {{ color: #4A5768; font-size: 13px; }}
  h2 {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
       color: #12988a; margin: 26px 0 10px; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  .metric {{ border: 1px solid #E3E8EF; border-radius: 10px;
            padding: 10px 14px; min-width: 110px; }}
  .mv {{ font-size: 20px; font-weight: 700; }}
  .ml {{ font-size: 11px; color: #8492A6; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; }}
  th, td {{ padding: 6px 9px; border-bottom: 1px solid #E3E8EF;
           text-align: left; }}
  th.num, td.num {{ text-align: right; }}
  footer {{ margin-top: 30px; font-size: 11px; color: #8492A6; }}
</style>
</head>
<body><div class="page">
<header>
  <div class="brand">SPORT MACHINE · SZEZON-LAP</div>
  <h1>#{jersey} — {escape(team)}</h1>
  <div class="sub">{n} elemzett meccs, időrendben.</div>
</header>
<h2>Szezon-összesítő</h2>
<div class="metrics">{"".join(totals)}</div>
<h2>Meccsről meccsre</h2>
{table}
<footer>A mezszám-hozzárendelés utáni track-csoportok összegzett
számai; a "—" azt jelzi, az adott meccsen nem volt mérhető adat.
</footer>
</div></body></html>"""


def season_report_html(team: str, tr: dict, focuses: list[dict],
                       n_matches: int,
                       timeline: list[dict] | None = None,
                       venue: dict | None = None,
                       leaders: dict | None = None,
                       opponents: list[dict] | None = None) -> str:
    """Szezon-riport: a csapat szezonja egy oldalon — automatikus
    időszak-bontású fejlődés-tábla + visszatérő edzés-fókuszok.
    """
    table = _trend_metrics_table(tr)
    summary = "".join(f"<li>{escape(s_)}</li>"
                      for s_ in tr.get("summary", []))
    timeline_html = ""
    if timeline:
        rows_tl = "".join(
            f"<tr><td>{escape(str(e.get('date') or ''))}</td>"
            f"<td>{escape(str(e.get('opponent') or ''))}</td>"
            f"<td>{escape(str(e.get('headline') or '—'))}</td></tr>"
            for e in timeline)
        timeline_html = (
            "<h2>A szezon meccsről meccsre</h2>"
            "<table><tr><th>Dátum</th><th>Ellenfél</th>"
            "<th>Mi történt</th></tr>" + rows_tl + "</table>")
    venue_html = ""
    if venue:
        def _vrow(label, v):
            if not v or not v.get("matches"):
                return (f"<tr><td>{label}</td>"
                        '<td class="num">—</td><td class="num">—</td>'
                        '<td class="num">—</td></tr>')
            return (f"<tr><td>{label}</td>"
                    f'<td class="num">{v["matches"]}</td>'
                    f'<td class="num">{v["w"]} / {v["d"]} / {v["l"]}'
                    "</td>"
                    f'<td class="num">{v["gf"]} – {v["ga"]}</td></tr>')
        venue_html = (
            "<h2>Hazai vs idegen</h2>"
            "<table><tr><th>Pálya</th><th class=\"num\">Meccs</th>"
            '<th class="num">Gy / D / V</th>'
            '<th class="num">Gólok</th></tr>'
            + _vrow("Hazai", venue.get("home"))
            + _vrow("Idegen", venue.get("away"))
            + "</table>")
    opponents_html = ""
    if opponents:
        opp_rows = "".join(
            f"<tr><td>{escape(str(o.get('opponent') or ''))}</td>"
            f'<td class="num">{o["matches"]}</td>'
            f'<td class="num">{o["w"]} / {o["d"]} / {o["l"]}</td>'
            f'<td class="num">{o["gf"]} – {o["ga"]}</td></tr>'
            for o in opponents)
        opponents_html = (
            "<h2>Ellenfél-mérleg</h2>"
            "<table><tr><th>Ellenfél</th>"
            '<th class="num">Meccs</th>'
            '<th class="num">Gy / D / V</th>'
            '<th class="num">Gólok</th></tr>' + opp_rows + "</table>")
    leaders_html = ""
    if leaders:
        cats_ld = (("goals", "Gólkirály", "gól"),
                   ("assists", "Gólpassz-vezér", "gólpassz"),
                   ("saves", "Védés-vezér", "védés"),
                   ("blocks", "Fal kulcsa", "blokk"),
                   ("steals", "Labdaszerző", "szerzés"))
        ld_rows = []
        for key_ld, title_ld, unit_ld in cats_ld:
            rows_ld = leaders.get(key_ld) or []
            if not rows_ld:
                continue
            names_ld = " · ".join(
                f'#{e["jersey"]} ({e["value"]} {unit_ld})'
                for e in rows_ld)
            ld_rows.append(f"<tr><td>{title_ld}</td>"
                           f"<td>{escape(names_ld)}</td></tr>")
        if ld_rows:
            leaders_html = (
                "<h2>A szezon játékosai</h2>"
                "<table><tr><th>Kategória</th><th>Top 3</th></tr>"
                + "".join(ld_rows) + "</table>")
    focus_html = ""
    if focuses:
        items = "".join(
            f"<li><b>{escape(str(f_.get('title', '')))}</b> "
            f"({escape(str(f_.get('area', '')))}) — "
            f"{f_.get('count', 0)} meccsen; gyakorlat: "
            f"{escape(str(f_.get('drill', '')))}</li>"
            for f_ in focuses)
        focus_html = ("<h2>Visszatérő edzés-fókuszok</h2><ul>"
                      + items + "</ul>")
    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="utf-8">
<title>Szezon-riport — {escape(team)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI",
         Arial, sans-serif; color: #101722; background: #fff;
         line-height: 1.5; }}
  .page {{ max-width: 720px; margin: 0 auto; padding: 36px 32px 48px; }}
  header {{ border-bottom: 3px solid #12988a; padding-bottom: 14px;
           margin-bottom: 22px; }}
  .brand {{ font-size: 11px; letter-spacing: .22em;
           text-transform: uppercase; color: #8492A6; }}
  h1 {{ margin: 6px 0 2px; font-size: 26px; }}
  .sub {{ color: #4A5768; font-size: 13px; }}
  h2 {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
       color: #12988a; margin: 26px 0 10px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ padding: 7px 10px; border-bottom: 1px solid #E3E8EF;
           text-align: left; }}
  th.num, td.num {{ text-align: right; }}
  td.up {{ color: #0B7A45; font-weight: 600; }}
  td.down {{ color: #B42318; font-weight: 600; }}
  ul {{ margin: 8px 0 0; padding-left: 20px; }}
  li {{ font-size: 13px; margin-bottom: 6px; }}
  .empty {{ color: #8492A6; font-size: 13px; }}
  footer {{ margin-top: 30px; font-size: 11px; color: #8492A6; }}
</style>
</head>
<body><div class="page">
<header>
  <div class="brand">SPORT MACHINE · SZEZON-RIPORT</div>
  <h1>{escape(team)}</h1>
  <div class="sub">{n_matches} elemzett meccs — az első és a második
  fele automatikusan összevetve ({tr.get("older_matches", 0)} vs
  {tr.get("newer_matches", 0)} meccs).</div>
</header>
{timeline_html}
{venue_html}
{opponents_html}
{leaders_html}
<h2>Fejlődés a szezonon belül</h2>
{table}
<h2>Összegzés</h2>
<ul>{summary}</ul>
{focus_html}
<footer>▲ javulás · ▼ romlás · – semleges irányú mutató; a darabszám-
mutatók meccsenkénti átlagra normálva. A visszatérő fókusz: ami
legalább két meccsen előjött — nem egyszeri kisiklás.</footer>
</div></body></html>"""


def h2h_report_html(team_a: str, team_b: str, stats: dict,
                    timeline: list[dict],
                    matchup: list[str] | None = None,
                    scorers: dict | None = None) -> str:
    """Egymás ellen: a két csapat egymás elleni mérlege a könyvtárból
    — győzelmi mérleg, gól-mérleg és meccs-lista főcímekkel.
    """
    rows = "".join(
        f"<tr><td>{escape(str(e.get('date') or ''))}</td>"
        f'<td class="num">{escape(str(e.get("score") or ""))}</td>'
        f"<td>{escape(str(e.get('headline') or '—'))}</td></tr>"
        for e in timeline)
    scorers_html = ""
    if scorers:
        sc_rows = []
        for tname, rows_sc in scorers.items():
            names_sc = " · ".join(
                f'#{e["jersey"]} ({e["goals"]} gól)' for e in rows_sc)
            sc_rows.append(f"<tr><td>{escape(str(tname))}</td>"
                           f"<td>{escape(names_sc)}</td></tr>")
        scorers_html = (
            "<h2>Ki viszi a meccseket (a közös meccsek "
            "gólfelelősei)</h2>"
            "<table><tr><th>Csapat</th><th>Top gólszerzők</th></tr>"
            + "".join(sc_rows) + "</table>")
    matchup_html = ""
    if matchup:
        items = "".join(f"<li>{escape(p_)}</li>" for p_ in matchup)
        matchup_html = (
            f"<h2>Meccsterv a visszavágóra ({escape(team_a)} "
            "szemszögéből, a legutóbbi meccs profiljából)</h2>"
            "<ul>" + items + "</ul>")
    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="utf-8">
<title>Egymás ellen — {escape(team_a)} vs {escape(team_b)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI",
         Arial, sans-serif; color: #101722; background: #fff;
         line-height: 1.5; }}
  .page {{ max-width: 720px; margin: 0 auto; padding: 36px 32px 48px; }}
  header {{ border-bottom: 3px solid #12988a; padding-bottom: 14px;
           margin-bottom: 22px; }}
  .brand {{ font-size: 11px; letter-spacing: .22em;
           text-transform: uppercase; color: #8492A6; }}
  h1 {{ margin: 6px 0 2px; font-size: 26px; }}
  .sub {{ color: #4A5768; font-size: 13px; }}
  h2 {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
       color: #12988a; margin: 26px 0 10px; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  .metric {{ border: 1px solid #E3E8EF; border-radius: 10px;
            padding: 10px 14px; min-width: 120px; }}
  .mv {{ font-size: 20px; font-weight: 700; }}
  .ml {{ font-size: 11px; color: #8492A6; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ padding: 7px 10px; border-bottom: 1px solid #E3E8EF;
           text-align: left; }}
  th.num, td.num {{ text-align: right; white-space: nowrap; }}
  ul {{ margin: 8px 0 0; padding-left: 20px; }}
  li {{ font-size: 13px; margin-bottom: 6px; }}
  footer {{ margin-top: 30px; font-size: 11px; color: #8492A6; }}
</style>
</head>
<body><div class="page">
<header>
  <div class="brand">SPORT MACHINE · EGYMÁS ELLEN</div>
  <h1>{escape(team_a)} vs {escape(team_b)}</h1>
  <div class="sub">{stats.get("matches", 0)} elemzett egymás elleni
  meccs a könyvtárból.</div>
</header>
<h2>Mérleg ({escape(team_a)} szemszögéből)</h2>
<div class="metrics">
  {_metric("Győzelem", str(stats.get("wins_a", 0)))}
  {_metric("Döntetlen", str(stats.get("draws", 0)))}
  {_metric("Vereség", str(stats.get("wins_b", 0)))}
  {_metric("Gól-mérleg",
           f"{stats.get('goals_a', 0)} – {stats.get('goals_b', 0)}")}
</div>
<h2>Meccsről meccsre</h2>
<table><tr><th>Dátum</th><th class="num">Eredmény</th>
<th>Mi történt</th></tr>{rows}</table>
{scorers_html}
{matchup_html}
<footer>A visszavágó-készüléshez: a legutóbbi meccs csomagjában ott a
meccsterv.txt, a felderítő képernyőn pedig a több-meccses
ellenfél-profil.</footer>
</div></body></html>"""
