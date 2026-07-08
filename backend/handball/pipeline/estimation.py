"""
[F] Képen kívüli játékosok becslése — a "teljes csapatkövetés" magja.

Feladata: pásztázó kameránál a képből kicsúszott játékosok pozíciójának BECSLÉSE,
hogy a felülnézeti nézeten a TELJES csapat látszódjon — de a becsült játékosok
egyértelműen megjelölve (source=ESTIMATED, csökkenő confidence).

Hogyan tudjuk, hány játékost kell becsülni:
- a RosterTimeline (lásd models/events.py) megmondja, hány játékos VAN a pályán
  csapatonként az adott pillanatban (a kiállításokat is figyelembe véve),
- ebből kivonva a ténylegesen LÁTOTT (mért) játékosokat kapjuk, hányat kell becsülni.

Hogyan becsüljük a pozíciót (ez a modul VALÓDI, tesztelt logikája):
- minden látott játékosról megjegyezzük az utolsó pozícióját, idejét és a
  SEBESSÉGÉT (két egymás utáni látásból),
- amíg a játékos képen kívül van, az utolsó pozícióból a sebességgel
  EXTRAPOLÁLUNK (egyenes vonalú mozgásmodell), a pálya határaira vágva,
- a sebesség hatása egy idő után "elfogy" (a játékos nem mozoghat örökké egyenesen),
- a confidence az eltelt idővel exponenciálisan csökken (felezési idő) → a kliens
  ezt halványítva/hibakörrel jeleníti meg. Mért ≠ becsült.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.tracking import Match, PlayerPosition, PositionSource, Team
from ..models.events import RosterTimeline
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M

# Hangolható paraméterek (frame-ben, ill. arányban):
CONFIDENCE_HALFLIFE_FRAMES = 25.0   # ennyi frame után FELEZŐDIK a becslés megbízhatósága
VELOCITY_FADE_FRAMES = 50.0         # a sebesség eddig hat; utána "megáll" a becsült játékos
MIN_CONFIDENCE = 0.05               # ennél kisebb megbízhatóságot már nem közlünk


def _clamp(value: float, low: float, high: float) -> float:
    """A `value`-t a [low, high] tartományba vágja (a pálya szélein tartja a becslést)."""
    return max(low, min(high, value))


@dataclass
class _SeenRecord:
    """Egy játékosról utoljára LÁTOTT (mért) információ — az extrapoláció alapja.

    - track_id:      a játékos azonosítója.
    - x, y:          utoljára látott pálya-pozíció (méter).
    - t:             mikor láttuk utoljára (frame-index).
    - vx, vy:        becsült sebesség (méter / frame) az utolsó két látásból.
    - team:          melyik csapat.
    - jersey_number, role: az azonosítás/megjelenítés átviteléhez.
    - confidence:    az utolsó MÉRT megbízhatóság (ebből indul a csökkenés).
    """
    track_id: int
    x: float
    y: float
    t: int
    vx: float
    vy: float
    team: Team
    jersey_number: int | None
    role: str | None
    confidence: float


class OffScreenEstimator:
    """A képen kívüli játékosok pozícióját becsli, és kiegészíti a mért listát.

    Állapotot tart: az egyes track_id-k utoljára látott adatait (`_last_seen`),
    hogy a képen kívüli időszakra extrapolálni tudjon.
    """

    def __init__(self, roster: RosterTimeline):
        # A létszám-állapot (kiállítások, kapus nélküli játék) forrása.
        self.roster = roster
        # track_id -> utoljára látott adat.
        self._last_seen: dict[int, _SeenRecord] = {}

    def update_seen(self, t: int, measured: list[PlayerPosition]) -> None:
        """Frissíti a "utoljára látott" nyilvántartást a mért játékosokkal.

        Ezt minden frame-en meghívjuk a MÉRT pozíciókkal. Ha a játékost korábban
        is láttuk, a két pozícióból sebességet (méter/frame) számolunk, amit a
        későbbi extrapolációhoz használunk.
        """
        for p in measured:
            prev = self._last_seen.get(p.track_id)
            if prev is not None and t > prev.t:
                dtf = t - prev.t
                vx = (p.x - prev.x) / dtf
                vy = (p.y - prev.y) / dtf
            else:
                vx, vy = 0.0, 0.0  # első látás: még nincs sebesség
            self._last_seen[p.track_id] = _SeenRecord(
                track_id=p.track_id, x=p.x, y=p.y, t=t, vx=vx, vy=vy,
                team=p.team, jersey_number=p.jersey_number, role=p.role,
                confidence=p.confidence,
            )

    def estimate_missing(self, t: int, measured: list[PlayerPosition]) -> list[PlayerPosition]:
        """Visszaadja a HIÁNYZÓ (képen kívüli) játékosok BECSÜLT pozícióit.

        Lépések:
        1. csapatonként megnézzük, hány játékosnak KELLENE látszania
           (roster.on_court_count) vs. hány mértet látunk → ennyit kell becsülni,
        2. a hiányzókat a korábban LÁTOTT, de épp nem látszó játékosokból töltjük
           fel (a legutóbb látottak előbb, mert azokban bízunk jobban),
        3. mindegyikre extrapolálunk az utolsó pozícióból a sebességgel, a pálya
           határaira vágva, és a confidence-et az eltelt idővel csökkentjük.
        """
        measured_ids = {p.track_id for p in measured}
        estimated: list[PlayerPosition] = []

        for team in (Team.HOME, Team.AWAY):
            needed = self.roster.on_court_count(team, t)
            seen = sum(1 for p in measured if p.team == team)
            missing = max(0, needed - seen)
            if missing == 0:
                continue

            # Jelöltek: ezt a csapatot játszó, korábban látott, de most NEM látszó játékosok.
            candidates = [
                rec for rec in self._last_seen.values()
                if rec.team == team and rec.track_id not in measured_ids
            ]
            # A legutóbb látottak előbb (azok a legmegbízhatóbbak).
            candidates.sort(key=lambda r: r.t, reverse=True)

            for rec in candidates[:missing]:
                estimated.append(self._extrapolate(rec, t))

        return estimated

    def _extrapolate(self, rec: _SeenRecord, t: int) -> PlayerPosition:
        """Egy korábban látott játékos becsült pozíciója a `t` frame-en.

        - a sebességgel előrevetítünk, de a sebesség hatása legfeljebb
          VELOCITY_FADE_FRAMES frame-ig tart (utána a játékos "megáll"),
        - a pozíciót a pálya (40 x 20 m) határaira vágjuk,
        - a confidence felezési idővel csökken az eltelt idő arányában.
        """
        elapsed = t - rec.t
        # A sebesség csak korlátozott ideig hat (nem mozoghat örökké egyenesen).
        eff = min(float(elapsed), VELOCITY_FADE_FRAMES)
        ex = _clamp(rec.x + rec.vx * eff, 0.0, COURT_LENGTH_M)
        ey = _clamp(rec.y + rec.vy * eff, 0.0, COURT_WIDTH_M)
        # Exponenciális csökkenés: minden CONFIDENCE_HALFLIFE_FRAMES alatt feleződik.
        conf = rec.confidence * (0.5 ** (elapsed / CONFIDENCE_HALFLIFE_FRAMES))
        conf = max(MIN_CONFIDENCE, conf)
        return PlayerPosition(
            track_id=rec.track_id,
            team=rec.team,
            x=ex,
            y=ey,
            source=PositionSource.ESTIMATED,
            confidence=conf,
            jersey_number=rec.jersey_number,
            role=rec.role,
        )


def augment_match_with_estimates(match: Match,
                                 roster: RosterTimeline | None = None) -> int:
    """A kész Match frame-jeit kiegészíti a képen kívüli játékosok becslésével.

    A valódi feldolgozó (scripts/process_video) UTÓLAG hívja: minden frame-en a
    MÉRT játékosokból frissíti a "utoljára látott" nyilvántartást, majd a
    hiányzókat (roster szerint kellene, de nem látszanak) becsléssel pótolja —
    ezek source=ESTIMATED-del és csökkenő confidence-szel kerülnek a frame-be,
    így a kliens halványítva rajzolja őket. Visszaadja, hány becsült pozíció
    került be összesen (napló/diagnosztika).
    """
    roster = roster or RosterTimeline()
    estimator = OffScreenEstimator(roster)
    added = 0
    for frame in match.frames:
        measured = [p for p in frame.players if p.source == PositionSource.MEASURED]
        estimator.update_seen(frame.t, measured)
        estimated = estimator.estimate_missing(frame.t, measured)
        frame.players.extend(estimated)
        added += len(estimated)
    return added
