"""
Tracking adatmodell — a RENDSZER KÖZPONTI SZERZŐDÉSE.

Ez az a JSON-ra szerializálható adatszerkezet, amit a Python backend előállít egy
videóból, és amit a Flutter-kliens beolvas és megjelenít (felülnézeti taktikai
nézet, statisztikák). MINDEN további elemzés (taktika, döntések, szimuláció)
ebből az objektumból dolgozik.

Tervezési elvek:
- TISZTA STDLIB (dataclasses + json), külső függőség nélkül → mindig fut és
  tesztelhető, és a kimenet stabil JSON, amit bármilyen kliens (Flutter, web) olvas.
- Minden játékos-pozícióhoz tartozik egy `source` (mért vagy becsült) és egy
  `confidence` mező, mert pásztázó kameránál a képen kívüli játékosokat BECSÜLJÜK,
  és ezt a kliensnek is jeleznie kell (pl. halványítva). Lásd docs/MVP_PLAN.md [F].
- A pálya-koordináták MÉTERBEN értendők (a 40 x 20 m-es pálya valós rendszerében),
  nem képpixelben — a homográfia (lásd pipeline/calibration.py) már átszámolta őket.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Team(str, Enum):
    """Melyik csapathoz tartozik egy játékos.

    `str`-ből származik, hogy a JSON-ban olvasható szövegként ("home"/"away")
    jelenjen meg, ne számként.
    """
    HOME = "home"   # hazai / "saját" csapat
    AWAY = "away"   # vendég / ellenfél csapat


class PositionSource(str, Enum):
    """Honnan ered egy játékos adott frame-beli pozíciója.

    Ez kulcsfontosságú a pásztázó kamera miatt: amit a kamera lát, azt MÉRJÜK,
    a képből kicsúszott játékost pedig BECSÜLJÜK (szerep + mozgás alapján).
    A kliens a kettőt különbözőképpen jeleníti meg (mért = tele pont,
    becsült = halvány + hibakör).
    """
    MEASURED = "measured"     # a kamera ténylegesen látta és detektálta
    ESTIMATED = "estimated"   # képen kívül volt → becsült pozíció


@dataclass
class PlayerPosition:
    """Egyetlen játékos egyetlen frame-en, a pálya valós koordinátáin.

    Mezők:
    - track_id:      a követő (ByteTrack) által adott stabil azonosító. Ugyanaz a
                     valós játékos végig ugyanazt az id-t kapja (ReID + mezszám segít).
    - team:          melyik csapat (Team.HOME / Team.AWAY).
    - x, y:          pálya-koordináta MÉTERBEN. Origó a pálya egyik sarka,
                     x a hosszú (40 m), y a rövid (20 m) tengely mentén.
    - source:        mért vagy becsült (lásd PositionSource).
    - confidence:    megbízhatóság 0..1. Mért pozíciónál jellemzően magas,
                     becsültnél az idővel csökken (minél régebb óta nem láttuk).
    - jersey_number: ha a mezszám-OCR (docs/RULES.md 5. szakasz) kiolvasta, ide kerül.
                     Ez a legerősebb azonosító jel; None, ha nem olvasható.
    - role:          opcionális pozíciós szerep (pl. "beallo", "iranyito"), ha már
                     meghatároztuk. Az MVP-ben még lehet None.
    """
    track_id: int
    team: Team
    x: float
    y: float
    source: PositionSource = PositionSource.MEASURED
    confidence: float = 1.0
    jersey_number: Optional[int] = None
    role: Optional[str] = None


@dataclass
class Ball:
    """A labda pozíciója egy frame-en, pálya-koordinátán (méter).

    `confidence`: a labda gyakran takarásban van, ezért külön megbízhatóságot
    tartunk. Ha a labda egyáltalán nem látszik, a Frame.ball None.
    """
    x: float
    y: float
    confidence: float = 1.0


@dataclass
class Frame:
    """A meccs egy időpillanata (egy feldolgozott videó-képkocka).

    - t:        idő. Az MVP-ben a frame sorszáma (index); később lehet másodperc.
    - players:  az adott pillanatban a pályán lévő játékosok (mért + becsült).
    - ball:     a labda pozíciója, vagy None, ha nem ismert.
    """
    t: int
    players: list[PlayerPosition] = field(default_factory=list)
    ball: Optional[Ball] = None


@dataclass
class MatchMeta:
    """A meccs alapadatai (a Tracking "fejléce").

    - match_id:        egyedi azonosító.
    - home_team / away_team: csapatnevek (megjelenítéshez).
    - fps:             a feldolgozott videó képkocka/másodperc értéke → ebből lehet
                       a frame-indexből valós időt és sebességet (m/s) számolni.
    - frame_width/height: az eredeti videó felbontása (pixel) — diagnosztikához.
    - date:            a meccs dátuma (ISO szöveg), opcionális.
    - video_path:      az EREDETI videófájl útja a feldolgozó gépen — a kliens
                       ebből tudja lejátszani a jelenetet (lokális mód).
    - start_frame:     a feldolgozás első kép-indexe az eredeti videóban.
    - stride:          mintavétel (minden hányadik képkockát dolgoztuk fel).
                       FIGYELEM: az `fps` a TRACKING képrátája (az eredeti
                       videóé osztva a stride-dal). Az i. tracking-frame ideje
                       a videóban: start_frame/(fps*stride) + i/fps másodperc.
    """
    match_id: str
    home_team: str
    away_team: str
    fps: float
    frame_width: int = 0
    frame_height: int = 0
    date: Optional[str] = None
    video_path: Optional[str] = None
    start_frame: int = 0
    stride: int = 1


@dataclass
class Match:
    """A teljes Tracking objektum: fejléc + minden frame.

    Ez az, amit a backend kiír JSON-ba, és a Flutter-kliens beolvas.
    A `to_json` / `from_json` adja a kliens-szerződést.
    """
    meta: MatchMeta
    frames: list[Frame] = field(default_factory=list)

    # ---- Szerializáció: Python objektum -> JSON szöveg -------------------------

    def to_dict(self) -> dict:
        """Beágyazott szótárrá alakít (Enumokat is szöveggé old fel).

        Az `asdict` rekurzívan bejárja a dataclass-okat; az Enum értékeket utána
        a `_enums_to_str` cseréli olvasható szövegre, hogy a JSON tiszta legyen.
        """
        return _enums_to_str(asdict(self))

    def to_json(self, indent: Optional[int] = None) -> str:
        """JSON szöveggé alakít. `indent=2`-vel ember által olvasható."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    # ---- Deszerializáció: JSON -> Python objektum ------------------------------

    @classmethod
    def from_dict(cls, d: dict) -> "Match":
        """Szótárból (pl. beolvasott JSON-ból) építi vissza a Match objektumot.

        Kézzel járjuk be a szerkezetet, hogy az Enumokat és a beágyazott
        dataclass-okat helyesen állítsuk vissza.
        """
        # Csak az ismert mezőket vesszük át — így a régebbi/újabb JSON-ok is
        # gond nélkül betölthetők (előre- és visszafelé kompatibilitás).
        known = MatchMeta.__dataclass_fields__.keys()
        meta = MatchMeta(**{k: v for k, v in d["meta"].items() if k in known})
        frames: list[Frame] = []
        for fr in d.get("frames", []):
            players = [
                PlayerPosition(
                    track_id=p["track_id"],
                    team=Team(p["team"]),
                    x=p["x"],
                    y=p["y"],
                    source=PositionSource(p.get("source", "measured")),
                    confidence=p.get("confidence", 1.0),
                    jersey_number=p.get("jersey_number"),
                    role=p.get("role"),
                )
                for p in fr.get("players", [])
            ]
            ball_d = fr.get("ball")
            ball = Ball(**ball_d) if ball_d is not None else None
            frames.append(Frame(t=fr["t"], players=players, ball=ball))
        return cls(meta=meta, frames=frames)

    @classmethod
    def from_json(cls, text: str) -> "Match":
        """JSON szövegből épít Match objektumot."""
        return cls.from_dict(json.loads(text))


def _enums_to_str(obj):
    """Rekurzívan végigjárja a szótár/lista szerkezetet, és minden Enum értéket a
    szöveges értékére cserél. Így az `asdict` kimenetéből tiszta, JSON-barát
    szótár lesz (pl. Team.HOME -> "home").
    """
    if isinstance(obj, dict):
        return {k: _enums_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_enums_to_str(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj
