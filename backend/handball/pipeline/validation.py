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

# Kézi címkék → belső típus (magyar és angol elfogadva).
_TYPE_MAP = {
    "gól": "goal", "gol": "goal", "goal": "goal", "g": "goal",
    "lövés": "shot", "loves": "shot", "löves": "shot", "shot": "shot",
    "s": "shot",
}


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
    return {
        "tol_s": tol_s,
        "by_type": by_type,
        "overall": _prf(tp, fp, fn),
    }
