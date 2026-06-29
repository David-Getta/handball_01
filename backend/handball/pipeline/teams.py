"""
[D] Csapatba sorolás — melyik játékos melyik csapatban van (+ kapus felismerés).

Feladata: a követett játékosokat két csapatra osztani a MEZSZÍN alapján, és
felismerni a kapus(oka)t.

Miért működik a szín (lásd docs/RULES.md 4. szakasz):
- A két csapat mezőnyjátékosainak színe egymástól jól megkülönböztethető.
- A kapus mezszíne KÜLÖNBÖZIK a saját mezőnyjátékosoktól ÉS az ellenfél kapusától
  → a kapus külön (harmadik/negyedik) színklaszterként jelenik meg.
- Ha a kapus-szín ELTŰNIK a pályáról, az a "7. mezőnyjátékos / kapus nélküli
  játék" jele (lásd events.RosterTimeline.has_goalkeeper).

FONTOS: a színek MECCSENKÉNT változnak (csapatok, kapusok, bírók, pálya) — sehol
nem feltételezünk fix színeket. Minden meccshez egy `AppearanceProfile` tartozik
(lásd appearance.py), amit a meccs elejéből TANULUNK vagy a felhasználó állít be.
A besoroló a profil referenciaszíneihez a LEGKÖZELEBBIT rendeli.

Módszer (valódi): a játékos-dobozok domináns mezszínét kinyerjük, és a meccs-profil
referenciacímkéihez soroljuk. A domináns szín KINYERÉSE pixelből még TODO (képadat
kell), de a hozzárendelés logikája (appearance.nearest_label) már valódi és tesztelt.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Team
from .tracking_step import Track
from .appearance import AppearanceProfile, AppearanceLabel, nearest_label


class TeamClassifier:
    """A követett játékosokat csapatokba sorolja a MECCS-PROFIL színei alapján.

    A `profile` a meccs színkészlete (tanult vagy kézzel beállított). Ha nincs
    megadva, a `fit` tölti fel a meccs elejéből. A besorolás szín-agnosztikus:
    bármilyen meccs-színkészlettel ugyanúgy működik.
    """

    def __init__(self, profile: Optional[AppearanceProfile] = None):
        # A meccs színkészlete. None, amíg nincs betanítva/beállítva.
        self.profile = profile

    def fit(self, sample_tracks: list[Track], frames=None) -> AppearanceProfile:
        """Megtanulja a meccs színkészletét néhány minta-frame alapján.

        TODO: a dobozok domináns színeit klaszterezni (k-means), a két legnagyobb
        klaszter = a két csapat, a külön álló kisebb klaszterek = kapus(ok)/bíró(k),
        és ebből AppearanceProfile-t építeni. A klaszter→címke hozzárendelést a
        felhasználó meg is erősítheti (kattintás egy-egy mintajátékosra).
        Most placeholder: üres profilt állít be (a pipeline így is fut).
        """
        self.profile = self.profile or AppearanceProfile()
        return self.profile

    def _label_for(self, track: Track) -> Optional[AppearanceLabel]:
        """A track domináns színéhez a meccs-profil címkéjét adja (vagy None).

        TODO: a domináns szín kinyerése a track bbox-ából (képadatból). Amíg ez
        nincs, és nincs profil, None-t ad — a besorolás a placeholder ágra esik.
        """
        if self.profile is None or track.dominant_color is None:
            return None
        return nearest_label(track.dominant_color, self.profile)

    def classify(self, track: Track) -> Team:
        """Egy követett játékoshoz csapatot rendel a meccs-profil alapján.

        A domináns színt a profil legközelebbi csapatcímkéjéhez sorolja. Ha nem
        besorolható (nincs profil/szín), placeholderként HOME-ot ad, hogy a
        pipeline fusson.
        """
        label = self._label_for(track)
        if label == AppearanceLabel.AWAY:
            return Team.AWAY
        if label == AppearanceLabel.HOME:
            return Team.HOME
        return Team.HOME  # placeholder, amíg nincs profil/szín

    def is_goalkeeper(self, track: Track) -> bool:
        """Igaz, ha a játékos a meccs-profil KAPUS-színéhez esik a legközelebb."""
        return self._label_for(track) == AppearanceLabel.GOALKEEPER

    def is_referee(self, track: Track) -> bool:
        """Igaz, ha a detektált személy BÍRÓ (nem játékos), és ki kell szűrni.

        A bírók színe is a MECCS-PROFILBÓL jön (nem fix sárga) — egy meccsen lehet
        más is. Ha a domináns szín a profil bíró-színéhez esik a legközelebb,
        kiszűrjük (a pipeline átugorja). Lásd docs/FOOTAGE_NOTES.md.
        """
        return self._label_for(track) == AppearanceLabel.REFEREE
