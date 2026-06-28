"""
Meccs-esemény idővonal — a DINAMIKUS LÉTSZÁM-állapot forrása.

A pályán lévő játékosok száma NEM állandó (lásd docs/RULES.md 6. szakasz):
- kiállítás (2 vagy 4 perc), akár több egyszerre → kevesebb játékos,
- kapus nélküli játék (7. mezőnyjátékos) → nincs kapus, de 7 mezőnyjátékos,
- csere → játékos eltűnik/megjelenik a cserevonalnál.

Ezt az idővonalat az MVP-ben KÉZZEL viszi fel az edző (mert pásztázó kameránál a
kiállítás vs. "képen kívül van" automatikusan nehezen megkülönböztethető), a
2. fázisban pedig automatikusan ismerjük fel. A becslő lépés ([F],
pipeline/estimation.py) ezt használja, hogy tudja, hány játékost KELL keresnie/
becsülnie csapatonként egy adott pillanatban.

Az idő itt frame-indexben értendő, hogy közvetlenül illeszkedjen a Tracking
frame-jeihez (a Match.meta.fps-ből számolható másodpercre).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tracking import Team


# A szabálykönyvből (docs/RULES.md):
BASE_ON_COURT = 7        # normál esetben 7 fő van pályán (6 mezőny + 1 kapus)
MIN_ON_COURT = 5         # a meccset legalább 5 fővel kell játszani (alsó korlát)


@dataclass
class Suspension:
    """Egy kiállítás: egy csapat egy fővel kevesebb egy adott időszakra.

    - team:       melyik csapatot sújtja.
    - start_t:    mikor kezdődik (frame-index).
    - duration_t: meddig tart (frame-ben). 2 perc vagy 4 perc * fps.
                  (4 perc = súlyos kizárás, 16:9 b-d; lásd RULES.md.)

    Több Suspension lehet ÁTFEDÉSBEN ugyanannál a csapatnál → a létszám több
    fővel is csökkenhet egyszerre.
    """
    team: Team
    start_t: int
    duration_t: int

    def is_active(self, t: int) -> bool:
        """Igaz, ha a `t` frame-en ez a kiállítás épp aktív."""
        return self.start_t <= t < self.start_t + self.duration_t


@dataclass
class RosterTimeline:
    """Csapatonkénti létszám-állapot az idő függvényében.

    Tartalma:
    - suspensions:   kiállítások listája (mindkét csapatra).
    - gk_absent_home / gk_absent_away: igaz, ha az adott csapat épp kapus nélkül
      játszik (7. mezőnyjátékossal). Ez a LÉTSZÁMOT nem csökkenti, de jelzi, hogy
      nincs kapus → a becslő/megjelenítő ennek megfelelően kezeli (a kapus-szín
      eltűnése a pályáról ennek a jele, lásd RULES.md 4. szakasz).

    Az MVP-ben ezeket kézzel töltjük fel; később automatikus eseményfelismerésből.
    """
    suspensions: list[Suspension] = field(default_factory=list)
    gk_absent_home: bool = False
    gk_absent_away: bool = False

    def on_court_count(self, team: Team, t: int) -> int:
        """Hány játékos van a pályán az adott csapatból a `t` frame-en.

        = alaplétszám (7) − az épp aktív kiállítások száma, de legalább 5.
        A becslő lépés ezt használja: ha pl. 6-ot kell látnia, de csak 4-et lát a
        képen, akkor tudja, hogy 2 játékost kell becsülnie (vagy ők ki vannak állítva).
        """
        active = sum(1 for s in self.suspensions if s.team == team and s.is_active(t))
        return max(MIN_ON_COURT, BASE_ON_COURT - active)

    def has_goalkeeper(self, team: Team, t: int) -> bool:
        """Van-e kapus a pályán az adott csapatnál a `t` frame-en.

        (Az MVP-ben egyszerű bool-flag csapatonként; ha később idő-intervallumos
        kapus-csere kell, ez intervallum-listává bővíthető.)
        """
        return not (self.gk_absent_home if team == Team.HOME else self.gk_absent_away)
