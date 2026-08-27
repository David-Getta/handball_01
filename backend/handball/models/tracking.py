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
    # RÉSZLEGES feldolgozás: a detektálás nem ért a videó végére (megszakítás
    # vagy összeomlás utáni checkpoint). A next_start_frame az a forrás-
    # videóbeli kép-index, ahonnan a feldolgozás FOLYTATHATÓ.
    partial: bool = False
    next_start_frame: int = 0
    # A FORRÁSVIDEÓ teljes hossza másodpercben (ha kiolvasható). Ebből
    # derül ki, hogy a feldolgozás a felvétel mekkora részét fedte le —
    # egy megvágott/félbeszakadt feltöltésnél a felhasználó egyébként
    # csak annyit lát, hogy "csak az első félidőt elemezte ki".
    video_seconds: Optional[float] = None
    # Volt-e PÁLYA-KALIBRÁCIÓ a feldolgozáskor. Enélkül a koordináták
    # csak arányos becslések (a képet nyújtjuk a pályára), és a pályán
    # kívüli embereket — kispad, edző, NÉZŐTÉR — nem lehet kiszűrni.
    # A jelentésnek ezt ki kell mondania, különben a felhasználó a
    # számokból nem tudja, mennyire bízhat bennük.
    # None = nem tudjuk (RÉGI mentés, a mező előtti időkből) — ilyenkor
    # nem állítunk semmit; False = biztosan nem volt kalibráció.
    calibrated: Optional[bool] = None
    # AUTOMATIKUS meccs-ablak (game_window.trim_to_game): talált-e a
    # felismerés összefüggő JÁTÉKOT a felvételen, és mennyit vágott le
    # az elejéből/végéből másodpercben. Enélkül a felhasználó nem tudja
    # meg, hogy a bemelegítés és a csapatbemutatás kimaradt-e — pedig
    # ha bennmaradt, az álldogálást a motor eladott labdának látja.
    # None = nem tudjuk (RÉGI mentés, a mezők előttről); False = a
    # felismerés NEM talált elég hosszú összefüggő játékot.
    game_window_found: Optional[bool] = None
    game_trim_head_s: Optional[float] = None
    game_trim_tail_s: Optional[float] = None
    # KÉZI esemény-javítások: amit az edző a felismerésen kijavít.
    # Elemenként {"op": "add"|"remove"|"set_type", "t": kocka,
    # "type": "goal"|"shot", "team": "home"|"away"}. A lövés-felismerés
    # a lista alapján javítja a saját eredményét, tehát a javítás MINDEN
    # rétegen átüt (eredmény, xG, lövő-listák, felderítés).
    #
    # Miért a meta-ban: a felismerés hibája nem a videó hibája — a
    # javítás a MECCS tulajdonsága, nem egy képernyőé, és
    # újrafeldolgozás nélkül is meg kell maradnia.
    event_overrides: list = field(default_factory=list)
    # ÖSSZEFŰZÖTT meccs forrás-szakaszai. Aki darabokban vesz fel (a
    # telefon négy gigánál vagy tíz percnél elvágja a felvételt), hat
    # klipből rak össze egy meccset — az összefűzött meccsnek nincs
    # EGY videófájlja, tehát a `video_path` üres.
    #
    # Enélkül a klipvágás azt mondaná, hogy "a videó nem érhető el",
    # ami félrevezető: a fájl megvan, csak több van belőle. Ez a
    # térkép mondja meg, melyik játékidő melyik fájl melyik
    # kép-indexén van.
    #
    # Elemenként: {"t_from", "t_to" (kizárólagos), "video_path",
    # "start_frame", "stride"} — a t a MERGE UTÁNI játékidő kockákban.
    source_segments: list = field(default_factory=list)


@dataclass
class Match:
    """A teljes Tracking objektum: fejléc + minden frame.

    Ez az, amit a backend kiír JSON-ba, és a Flutter-kliens beolvas.
    A `to_json` / `from_json` adja a kliens-szerződést.
    """
    meta: MatchMeta
    frames: list[Frame] = field(default_factory=list)

    def swap_teams(self) -> None:
        """Felcseréli a két csapatot: minden játékos team-mezőjét átbillenti.

        Akkor kell, ha a csapatszín-klaszterezés fordítva találta el, melyik
        szín a hazai — az edző egy gombbal javíthatja, újrafeldolgozás nélkül.
        A csapatNEVEK maradnak (azokat a felhasználó adta meg helyesen).
        """
        for fr in self.frames:
            for p in fr.players:
                p.team = Team.AWAY if p.team == Team.HOME else Team.HOME

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
