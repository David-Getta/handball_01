"""
[F] Képen kívüli játékosok becslése — a "teljes csapatkövetés" magja.

Feladata: pásztázó kameránál a képből kicsúszott játékosok pozíciójának BECSLÉSE,
hogy a felülnézeti nézeten a TELJES csapat látszódjon — de a becsült játékosok
egyértelműen megjelölve (source=ESTIMATED, csökkenő confidence).

Hogyan tudjuk, hány játékost kell becsülni:
- a RosterTimeline (lásd models/events.py) megmondja, hány játékos VAN a pályán
  csapatonként az adott pillanatban (a kiállításokat is figyelembe véve),
- ebből kivonva a ténylegesen LÁTOTT (mért) játékosokat kapjuk, hányat kell becsülni.

Hogyan becsüljük a pozíciót:
- az utoljára látott hely + mozgásirány (egyszerű mozgásmodell),
- a játékos pozíciós SZEREPE szerinti tipikus hely (formációmodell),
- a confidence az eltelt idővel csökken (minél régebb óta nem láttuk, annál bizonytalanabb).

Ez a váz a felelősséget és a be-/kimenetet rögzíti; a tényleges becslés TODO.
"""

from __future__ import annotations

from ..models.tracking import PlayerPosition, PositionSource, Team
from ..models.events import RosterTimeline


class OffScreenEstimator:
    """A képen kívüli játékosok pozícióját becsli, és kiegészíti a mért listát.

    Állapotot tart: az egyes track_id-k utoljára látott pozícióját és idejét, hogy
    a képen kívüli időszakra extrapolálni tudjon.
    """

    def __init__(self, roster: RosterTimeline):
        # A létszám-állapot (kiállítások, kapus nélküli játék) forrása.
        self.roster = roster
        # track_id -> (utolsó látott PlayerPosition, utolsó látott t). TODO: feltöltés.
        self._last_seen: dict[int, tuple[PlayerPosition, int]] = {}

    def update_seen(self, t: int, measured: list[PlayerPosition]) -> None:
        """Frissíti a "utoljára látott" nyilvántartást a mért játékosokkal.

        Ezt minden frame-en meghívjuk a mért pozíciókkal, hogy a későbbi
        becsléshez legyen mire támaszkodni.
        """
        for p in measured:
            self._last_seen[p.track_id] = (p, t)

    def estimate_missing(self, t: int, measured: list[PlayerPosition]) -> list[PlayerPosition]:
        """Visszaadja a HIÁNYZÓ (képen kívüli) játékosok BECSÜLT pozícióit.

        Lépések:
        1. csapatonként megnézzük, hány játékosnak KELLENE látszania
           (roster.on_court_count) vs. hány mértet látunk,
        2. a hiányzókra a `_last_seen`-ből extrapolálunk (mozgás + szerep),
        3. source=ESTIMATED, és a confidence az eltelt idővel csökken.

        TODO: a tényleges extrapoláció és formációmodell. Most placeholder: üres
        lista (azaz a váz még nem becsül, csak a mértet adja tovább a pipeline).
        """
        estimated: list[PlayerPosition] = []
        # TODO: valódi becslés. A váz a szerkezetet és a roster-lekérdezést mutatja:
        for team in (Team.HOME, Team.AWAY):
            needed = self.roster.on_court_count(team, t)
            seen = sum(1 for p in measured if p.team == team)
            missing = max(0, needed - seen)
            # TODO: `missing` darab becsült PlayerPosition előállítása (source=ESTIMATED).
            _ = missing
        return estimated
