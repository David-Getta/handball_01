"""Kézi elemzés — az edző SAJÁT, kézzel rögzített elemzése egy meccshez.

Két része van, egy dokumentumban:

- **esemény-napló** (`events`): időpont (a videó másodperce), csapat,
  esemény-típus, mezszám, a passz címzettje, kimenetel, megjegyzés;
- **taktikai táblák** (`scenes`): felülnézeti pálya-helyzetek mozgatható
  bábukkal (a pálya méterében, 40×20), és sorszámozott nyilakkal (passz,
  futás, lövés) — így rajzolható meg, ki kinek passzolt.

A dokumentum FÉLKÉSZEN is menthető (`status`: folyamatban / kész), és a
motor a meccs mellett, külön fájlban tárolja (`{id}.annotations.json`).
Az esemény-napló egyben a program mérőrúdja is: a kézzel rögzített
események a felismerés kimenetével összevethetők (CSV-export).

A normalizálás SOSEM dob el felhasználói munkát csendben, ha menthető:
az ismeretlen mezőket elhagyja, a szövegeket levágja, a koordinátákat a
pályára szorítja, a hibás számot alapértékre állítja. Csak a korlátokon
túli darabszámot vágja (egy elszabadult kliens se tölthesse tele a
lemezt).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

ANN_VERSION = 1
# Méret-korlátok (egy teljes meccs kézi naplója bőven elfér alattuk).
ANN_MAX_EVENTS = 5000
ANN_MAX_SCENES = 300
ANN_MAX_TOKENS = 24      # táblánként: 2×7 játékos + cserék + labda
ANN_MAX_ARROWS = 60      # táblánként
ANN_MAX_TEXT = 500       # megjegyzés
ANN_MAX_SHORT = 40       # típus, kimenetel, azonosító
ANN_MAX_LABEL = 4        # bábu-felirat (mezszám)
ANN_MAX_NAME = 80        # tábla neve
# A pálya mérete (méter) — a bábuk ide szorulnak.
ANN_COURT_LENGTH_M = 40.0
ANN_COURT_WIDTH_M = 20.0

ANN_TEAMS = ("home", "away")
ANN_TOKEN_TEAMS = ("home", "away", "ball")
ANN_ARROW_KINDS = ("pass", "run", "shot")
ANN_STATUSES = ("in_progress", "done")

# A kliens által felkínált esemény-típusok (a napló ezekből épül; más
# szöveg is menthető, de a CSV-összevetés ezeket ismeri).
ANN_EVENT_TYPES = (
    "lövés", "passz", "eladás", "szerzés", "kiállítás", "hetes",
    "időkérés", "csere", "szabálytalanság", "egyéb",
)
# A lövés kimenetelei.
ANN_SHOT_OUTCOMES = ("gól", "védés", "mellé", "kapufa", "blokk")


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(
        microsecond=0).isoformat()


def _text(v: Any, limit: int) -> str:
    """Szöveg levágva és szélein megtisztítva; nem-szövegre üres."""
    if v is None:
        return ""
    if not isinstance(v, str):
        v = str(v) if isinstance(v, (int, float)) else ""
    return v.strip()[:limit]


def _num(v: Any, default: Optional[float] = None) -> Optional[float]:
    """Véges szám vagy az alapérték (a NaN/végtelen is alapérték)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return f


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def empty_annotations(match_id: str) -> dict:
    """Az üres (még el nem kezdett) kézi elemzés."""
    return {"version": ANN_VERSION, "match_id": match_id,
            "status": "in_progress", "updated_at": None,
            "events": [], "scenes": []}


def _norm_event(e: Any, idx: int, scene_ids: set) -> Optional[dict]:
    if not isinstance(e, dict):
        return None
    t = _num(e.get("t_s"), 0.0)
    team = e.get("team")
    scene = _text(e.get("scene_id"), ANN_MAX_SHORT)
    return {
        "id": _text(e.get("id"), ANN_MAX_SHORT) or f"e{idx + 1}",
        "t_s": round(max(0.0, t), 1),
        "team": team if team in ANN_TEAMS else "",
        "type": _text(e.get("type"), ANN_MAX_SHORT) or "egyéb",
        "jersey": _text(e.get("jersey"), 6),
        "to_jersey": _text(e.get("to_jersey"), 6),
        "outcome": _text(e.get("outcome"), ANN_MAX_SHORT),
        "note": _text(e.get("note"), ANN_MAX_TEXT),
        "scene_id": scene if scene in scene_ids else "",
    }


def _norm_token(tk: Any, idx: int) -> Optional[dict]:
    if not isinstance(tk, dict):
        return None
    team = tk.get("team")
    if team not in ANN_TOKEN_TEAMS:
        return None
    x = _num(tk.get("x"), ANN_COURT_LENGTH_M / 2)
    y = _num(tk.get("y"), ANN_COURT_WIDTH_M / 2)
    return {
        "id": _text(tk.get("id"), ANN_MAX_SHORT) or f"t{idx + 1}",
        "team": team,
        "label": _text(tk.get("label"), ANN_MAX_LABEL),
        "x": round(_clamp(x, 0.0, ANN_COURT_LENGTH_M), 2),
        "y": round(_clamp(y, 0.0, ANN_COURT_WIDTH_M), 2),
    }


def _norm_arrow(a: Any, token_ids: set) -> Optional[dict]:
    """Nyíl: `from` bábuból `to` bábuhoz (passz), vagy egy PONTHOZ
    (`x`, `y` — futás, lövés). A nem létező bábura mutató nyíl elesik;
    a bábu nélküli passz ponthoz mutat, ha van pontja."""
    if not isinstance(a, dict):
        return None
    kind = a.get("kind")
    if kind not in ANN_ARROW_KINDS:
        return None
    src = _text(a.get("from"), ANN_MAX_SHORT)
    if src not in token_ids:
        return None
    dst = _text(a.get("to"), ANN_MAX_SHORT)
    x = _num(a.get("x"))
    y = _num(a.get("y"))
    if dst and dst in token_ids and dst != src:
        return {"kind": kind, "from": src, "to": dst}
    if x is None or y is None:
        return None
    return {"kind": kind, "from": src, "to": "",
            "x": round(_clamp(x, 0.0, ANN_COURT_LENGTH_M), 2),
            "y": round(_clamp(y, 0.0, ANN_COURT_WIDTH_M), 2)}


def _norm_scene(s: Any, idx: int) -> Optional[dict]:
    if not isinstance(s, dict):
        return None
    tokens: list = []
    seen: set = set()
    for i, tk in enumerate((s.get("tokens") or [])[:ANN_MAX_TOKENS]
                           if isinstance(s.get("tokens"), list) else []):
        n = _norm_token(tk, i)
        if n is None or n["id"] in seen:
            continue
        seen.add(n["id"])
        tokens.append(n)
    arrows = []
    for a in ((s.get("arrows") or [])[:ANN_MAX_ARROWS]
              if isinstance(s.get("arrows"), list) else []):
        n = _norm_arrow(a, seen)
        if n is not None:
            arrows.append(n)
    t = _num(s.get("t_s"))
    return {
        "id": _text(s.get("id"), ANN_MAX_SHORT) or f"s{idx + 1}",
        "name": _text(s.get("name"), ANN_MAX_NAME) or f"Tábla {idx + 1}",
        "t_s": None if t is None else round(max(0.0, t), 1),
        "note": _text(s.get("note"), ANN_MAX_TEXT),
        "tokens": tokens,
        "arrows": arrows,
    }


def normalize_annotations(doc: Any, match_id: str) -> dict:
    """A kliens által küldött kézi elemzés tisztított, menthető alakja.

    Hibás alak (nem szótár) esetén ValueError — a hívó 400-at ad. Minden
    más hibát a mezők szintjén javítunk (lásd a modul-docstringet). Az
    eseményeket időrendbe tesszük (azonos időn belül a beküldés sorrendje
    marad), a táblák sorrendje a felhasználóé.
    """
    if not isinstance(doc, dict):
        raise ValueError("a kézi elemzés alakja hibás (objektum kell)")
    scenes: list = []
    seen_s: set = set()
    raw_s = doc.get("scenes") if isinstance(doc.get("scenes"), list) else []
    for i, s in enumerate(raw_s[:ANN_MAX_SCENES]):
        n = _norm_scene(s, i)
        if n is None or n["id"] in seen_s:
            continue
        seen_s.add(n["id"])
        scenes.append(n)
    events: list = []
    seen_e: set = set()
    raw_e = doc.get("events") if isinstance(doc.get("events"), list) else []
    for i, e in enumerate(raw_e[:ANN_MAX_EVENTS]):
        n = _norm_event(e, i, seen_s)
        if n is None:
            continue
        if n["id"] in seen_e:          # ütköző azonosító: újat kap
            n["id"] = f"e{i + 1}_{len(events)}"
        seen_e.add(n["id"])
        events.append(n)
    events.sort(key=lambda e: e["t_s"])       # stabil: az azonos idejűek
    status = doc.get("status")
    return {
        "version": ANN_VERSION,
        "match_id": match_id,
        "status": status if status in ANN_STATUSES else "in_progress",
        "updated_at": _now_iso(),
        "events": events,
        "scenes": scenes,
    }


def summarize_annotations(doc: dict) -> dict:
    """Rövid összkép (lista-nézethez): hány esemény, hány tábla, kész-e."""
    return {"status": doc.get("status", "in_progress"),
            "events": len(doc.get("events") or []),
            "scenes": len(doc.get("scenes") or []),
            "updated_at": doc.get("updated_at")}


def _mmss(t_s: float) -> str:
    t = int(round(max(0.0, float(t_s or 0.0))))
    return f"{t // 60:02d}:{t % 60:02d}"


def annotations_csv(doc: dict, home: str = "hazai",
                    away: str = "vendég") -> str:
    """Az esemény-napló CSV-ben (pontosvesszővel, Excelben nyitható).

    Oszlopok: ido (a videó ideje, pp:mm), ido_mp (másodperc), csapat,
    esemeny, mez, kinek, kimenetel, megjegyzes, tabla — ez a program
    kimenetével való összevetés alap-formátuma.
    """
    import csv
    import io

    names = {"home": home, "away": away, "": ""}
    tablak = {s["id"]: s.get("name", "") for s in (doc.get("scenes") or [])}
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["ido", "ido_mp", "csapat", "esemeny", "mez", "kinek",
                "kimenetel", "megjegyzes", "tabla"])
    for e in doc.get("events") or []:
        w.writerow([_mmss(e.get("t_s", 0.0)),
                    f"{float(e.get('t_s', 0.0)):.1f}".replace(".", ","),
                    names.get(e.get("team", ""), ""),
                    e.get("type", ""), e.get("jersey", ""),
                    e.get("to_jersey", ""), e.get("outcome", ""),
                    e.get("note", ""), tablak.get(e.get("scene_id", ""), "")])
    return buf.getvalue()
