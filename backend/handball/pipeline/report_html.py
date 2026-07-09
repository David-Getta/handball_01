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


def scouting_report_html(rep: ScoutingReport) -> str:
    """A jelentés teljes, önálló HTML-je (nyomtatható; böngészőből PDF)."""
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
  .cols {{ display: flex; gap: 22px; }}
  .col {{ flex: 1; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 14px 26px; }}
  .metric .mv {{ font-size: 20px; font-weight: 700; color: #12988a; }}
  .metric .ml {{ font-size: 11px; color: #4A5768; }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin: 5px 0; font-size: 13px; }}
  .bar-label {{ width: 120px; font-weight: 600; }}
  .bar {{ flex: 1; height: 9px; background: #edf1f6; border-radius: 5px; overflow: hidden; }}
  .bar-fill {{ display: block; height: 100%; background: #12988a; border-radius: 5px; }}
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
