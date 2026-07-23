"""Pontosság-validáció valós felvételen: a felismert események összevetése
KÉZI ground-truth-tal (nem szimulációval).

A benchmark.py a szimulált igazsághoz mér; ez az eszköz egy EMBER által
annotált eseménylistához (gólok/lövések időbélyeggel) hasonlítja a motor
kimenetét, és precizitás / visszahívás / F1 értéket ad esemény-típusonként.
Ez a piaci validáció sarokköve: "egyezik-e a motor a valósággal?"

A ground-truth egyszerű, edző által is kitölthető formátum:
    [{"t_s": 42.0, "type": "gól", "team": "home"}, ...]
- t_s: az esemény ideje másodpercben,
- type: "gól"/"goal" vagy "lövés"/"shot" (magyar és angol címke is jó),
- team: "home"/"away" — opcionális; ha hiányzik, csak típus+idő alapján
  párosítunk.

A párosítás mohó, egy-az-egyhez, TOL_S másodperc idő-tűréssel.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match
from .tactics import TacticsConfig

# Egy felismert és egy kézi esemény ennyi másodpercen belül számít egyezőnek.
VALIDATION_TOL_S = 3.0

# Cél-küszöbök az ítélethez (a stratégia kill-kritériuma): efölött a motor
# eseményfelismerése "elég a taktikai döntéshez".
VALIDATION_TARGET_RECALL = 0.90
VALIDATION_TARGET_PRECISION = 0.85

# Kézi címkék → belső típus (magyar és angol elfogadva).
_TYPE_MAP = {
    "gól": "goal", "gol": "goal", "goal": "goal", "g": "goal",
    "lövés": "shot", "loves": "shot", "löves": "shot", "shot": "shot",
    "s": "shot",
}

# Csapat-címkék (magyar és angol) → belső oldal.
_TEAM_MAP = {
    "hazai": "home", "home": "home", "h": "home",
    "vendég": "away", "vendeg": "away", "away": "away", "a": "away",
}


def _parse_time(s: str):
    """Idő másodpercben: elfogad tizedes mp-et (42.0) és óra:perc:mp
    alakot is (1:23, 01:23, 1:02:03). Hibás/üres → None."""
    s = (s or "").strip()
    if not s:
        return None
    if ":" in s:
        bits = s.split(":")
        try:
            total = 0.0
            for b in bits:
                total = total * 60.0 + float(b)
            return total
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_truth_csv(text: str) -> list:
    """Kézi ground-truth beolvasása CSV/TSV szövegből — az edzők
    táblázatból dolgoznak, nem JSON-ból.

    Soronként: `idő, típus[, csapat]` (vessző, pontosvessző vagy tab
    elválasztóval). Az idő tizedes mp vagy mm:ss; a típus és a csapat
    magyarul és angolul is jó. A fejléc-sor (nem-szám első cella) és a
    `#`-kezdetű sorok kimaradnak.

    Visszatérés: validate_events-nek átadható lista
    [{"t_s", "type", "team"}].
    """
    import re

    out: list = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [c.strip() for c in re.split(r"[;,\t]", line)]
        if len(parts) < 2:
            continue
        t = _parse_time(parts[0])
        if t is None:  # fejléc vagy hibás sor
            continue
        if _TYPE_MAP.get(parts[1].strip().lower()) is None:
            continue
        team = None
        if len(parts) >= 3 and parts[2].strip():
            team = _TEAM_MAP.get(parts[2].strip().lower())
        out.append({"t_s": t, "type": parts[1].strip(), "team": team})
    return out


def _prf(tp: int, fp: int, fn: int) -> dict:
    """Precizitás / visszahívás / F1 egy TP-FP-FN hármasból."""
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    if prec is not None and rec is not None and (prec + rec) > 0:
        f1 = 2 * prec * rec / (prec + rec)
    elif prec is not None or rec is not None:
        f1 = 0.0
    else:
        f1 = None
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(prec, 3) if prec is not None else None,
        "recall": round(rec, 3) if rec is not None else None,
        "f1": round(f1, 3) if f1 is not None else None,
    }


def _verdict(overall: dict) -> dict:
    """Edző-olvasható ítélet az összesített precizitás/visszahívásból, a
    cél-küszöbökhöz mérve. {"pass": bool|None, "text": "..."}."""
    prec = overall["precision"]
    rec = overall["recall"]
    if prec is None and rec is None:
        return {"pass": None,
                "text": "Nincs elég adat az ítélethez (üres a minta)."}
    ok_rec = rec is not None and rec >= VALIDATION_TARGET_RECALL
    ok_prec = prec is not None and prec >= VALIDATION_TARGET_PRECISION
    passed = bool(ok_rec and ok_prec)
    parts = []
    if rec is not None:
        parts.append(f"visszahívás {rec * 100:.0f}% "
                     f"(cél ≥{VALIDATION_TARGET_RECALL * 100:.0f}%)")
    if prec is not None:
        parts.append(f"precizitás {prec * 100:.0f}% "
                     f"(cél ≥{VALIDATION_TARGET_PRECISION * 100:.0f}%)")
    status = ("MEGFELEL — a felismerés elég a taktikai döntéshez" if passed
              else "GYENGE — a felismerés még nem elég megbízható")
    return {"pass": passed, "text": status + ": " + ", ".join(parts) + "."}


def validate_events(match: Match, truth: list,
                    tol_s: float = VALIDATION_TOL_S,
                    config: Optional[TacticsConfig] = None) -> dict:
    """A felismert gólok/lövések összevetése a kézi ground-truth-tal.

    Visszatérés:
      {"tol_s", "by_type": {"goal": {...}, "shot": {...}},
       "overall": {...}} — minden blokk {tp, fp, fn, precision, recall, f1}.
    tp: helyesen felismert (párosított), fp: téves (felismert, de nincs a
    kézi listában), fn: kimaradt (a kézi listában van, de nem ismerte fel).
    """
    from .event_detection import detect_events

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0

    # Kézi lista normalizálása.
    tru: list = []
    for e in truth or []:
        ty = _TYPE_MAP.get(str(e.get("type", "")).strip().lower())
        if ty is None or "t_s" not in e:
            continue
        team = e.get("team")
        team = team.strip().lower() if isinstance(team, str) else None
        tru.append({"t_s": float(e["t_s"]), "type": ty, "team": team})

    # Felismert gólok + lövések (idő másodpercben).
    det: list = []
    for ev in detect_events(match, config):
        v = getattr(ev.type, "value", ev.type)
        if v in ("goal", "shot"):
            det.append({"t_s": ev.t / fps, "type": v,
                        "team": getattr(ev.team, "value", ev.team)})

    def _match_type(dtype: str) -> dict:
        d_list = sorted((d for d in det if d["type"] == dtype),
                        key=lambda x: x["t_s"])
        t_list = sorted((t for t in tru if t["type"] == dtype),
                        key=lambda x: x["t_s"])
        used: set = set()
        tp = 0
        for t in t_list:
            best_i = None
            best_dt = tol_s + 1.0
            for i, d in enumerate(d_list):
                if i in used:
                    continue
                # Ha a kézi rekord megadja a csapatot, egyeznie kell.
                if t["team"] and d["team"] != t["team"]:
                    continue
                dt = abs(d["t_s"] - t["t_s"])
                if dt <= tol_s and dt < best_dt:
                    best_i, best_dt = i, dt
            if best_i is not None:
                used.add(best_i)
                tp += 1
        fp = len(d_list) - len(used)
        fn = len(t_list) - tp
        return _prf(tp, fp, fn)

    by_type = {ty: _match_type(ty) for ty in ("goal", "shot")}
    tp = sum(by_type[t]["tp"] for t in by_type)
    fp = sum(by_type[t]["fp"] for t in by_type)
    fn = sum(by_type[t]["fn"] for t in by_type)
    overall = _prf(tp, fp, fn)
    return {
        "tol_s": tol_s,
        "by_type": by_type,
        "overall": overall,
        "verdict": _verdict(overall),
    }


def validation_report_html(res: dict, home_team: str = "",
                           away_team: str = "") -> str:
    """A validáció eredményéből megosztható, nyomtatható HTML-oldal — a
    pilot go/no-go döntéshez. Ítélet-sáv + esemény-típusonkénti tábla."""
    from html import escape

    v = res.get("verdict") or {}
    passed = v.get("pass")
    banner_bg = ("#12683f" if passed
                 else "#8f2f2f" if passed is False else "#4a4a4a")

    def _pct(x):
        return "—" if x is None else f"{x * 100:.0f}%"

    _labels = {"goal": "Gól", "shot": "Lövés"}
    rows = []
    for ty in ("goal", "shot"):
        r = (res.get("by_type") or {}).get(ty) or {}
        rows.append(
            f"<tr><td>{escape(_labels[ty])}</td>"
            f'<td class="num">{r.get("tp", 0)}</td>'
            f'<td class="num">{r.get("fp", 0)}</td>'
            f'<td class="num">{r.get("fn", 0)}</td>'
            f'<td class="num">{_pct(r.get("precision"))}</td>'
            f'<td class="num">{_pct(r.get("recall"))}</td>'
            f'<td class="num">{_pct(r.get("f1"))}</td></tr>')
    ov = res.get("overall") or {}
    rows.append(
        f'<tr class="tot"><td>Összesen</td>'
        f'<td class="num">{ov.get("tp", 0)}</td>'
        f'<td class="num">{ov.get("fp", 0)}</td>'
        f'<td class="num">{ov.get("fn", 0)}</td>'
        f'<td class="num">{_pct(ov.get("precision"))}</td>'
        f'<td class="num">{_pct(ov.get("recall"))}</td>'
        f'<td class="num">{_pct(ov.get("f1"))}</td></tr>')

    teams = (f"{escape(home_team)} – {escape(away_team)}"
             if home_team or away_team else "")
    return (
        "<!DOCTYPE html><html lang=\"hu\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, "
        "initial-scale=1\"><title>Pontosság-validáció</title><style>"
        "body{font-family:system-ui,Arial,sans-serif;max-width:720px;"
        "margin:2rem auto;padding:0 1rem;color:#1c2530;}"
        "h1{font-size:1.4rem;}"
        ".teams{color:#666;margin:-.4rem 0 1.2rem;}"
        f".banner{{background:{banner_bg};color:#fff;padding:1rem 1.2rem;"
        "border-radius:10px;font-weight:600;margin:1rem 0 1.4rem;}"
        "table{border-collapse:collapse;width:100%;font-size:.95rem;}"
        "th,td{padding:.55rem .7rem;border-bottom:1px solid #e2e2e2;"
        "text-align:left;}"
        "th{font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;"
        "color:#777;}"
        ".num{text-align:right;font-variant-numeric:tabular-nums;}"
        ".tot{font-weight:700;background:#f6f4ee;}"
        ".foot{color:#888;font-size:.8rem;margin-top:1.4rem;}"
        "</style></head><body>"
        "<h1>Pontosság-validáció</h1>"
        + (f'<div class="teams">{teams}</div>' if teams else "")
        + f'<div class="banner">{escape(v.get("text", ""))}</div>'
        "<table><tr><th>Esemény</th><th class=\"num\">Talált (TP)</th>"
        "<th class=\"num\">Téves (FP)</th><th class=\"num\">Kimaradt (FN)</th>"
        "<th class=\"num\">Precizitás</th><th class=\"num\">Visszahívás</th>"
        "<th class=\"num\">F1</th></tr>"
        + "".join(rows)
        + "</table>"
        f'<div class="foot">Idő-tűrés: {res.get("tol_s", "")} mp. '
        "A TP a kézi listával párosított felismerés; az FP téves felismerés; "
        "az FN a kimaradt (kézi listában van, de nem ismerte fel).</div>"
        "</body></html>")
