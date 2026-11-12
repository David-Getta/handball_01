"""
Tesztek a csapatba sorolóra (teams.py, TeamClassifier).

A besoroló a MECCS-PROFIL színeihez rendeli a követett játékos domináns
mezszínét: hazai / vendég / kapus / bíró. A színek meccsenként változnak,
ezért két KÜLÖNBÖZŐ profillal is nézzük. A "kevés minta" itt a hiányzó
profil vagy a hiányzó szín: ilyenkor a besoroló nem találgat (nincs kapus,
nincs bíró), a csapat pedig a dokumentált placeholder (HOME).

Futtatás:
    python -m pytest tests/test_teams.py -q
"""

from __future__ import annotations

from handball.models.tracking import Team
from handball.pipeline.appearance import AppearanceLabel, AppearanceProfile
from handball.pipeline.detection import Detection, DetectionClass
from handball.pipeline.teams import TeamClassifier
from handball.pipeline.tracking_step import Track


def _track(color, track_id=1):
    """Egy követett játékos a megadott domináns mezszínnel."""
    det = Detection(DetectionClass.PLAYER, 100.0, 50.0, 140.0, 170.0)
    return Track(track_id=track_id, detection=det, dominant_color=color)


def _profil():
    """Fehér hazai, fekete vendég, zöld kapus, sárga bíró."""
    return AppearanceProfile(
        home=(240, 240, 240), away=(20, 20, 20),
        goalkeeper=[(30, 160, 60)], referee=[(230, 210, 40)])


def test_classify_a_profil_legkozelebbi_csapatat_adja():
    """A fehérhez közeli mez hazai, a feketéhez közeli vendég."""
    tc = TeamClassifier(_profil())
    assert tc.classify(_track((250, 245, 235))) == Team.HOME
    assert tc.classify(_track((12, 18, 25))) == Team.AWAY


def test_classify_mas_szinkeszlettel_is_mukodik():
    """Nincs bedrótozott szín: piros hazai / kék vendég profillal ugyanaz a
    logika a piros mezt hazainak, a kéket vendégnek sorolja."""
    tc = TeamClassifier(AppearanceProfile(home=(200, 30, 30),
                                          away=(30, 60, 200)))
    assert tc.classify(_track((210, 40, 25))) == Team.HOME
    assert tc.classify(_track((25, 70, 210))) == Team.AWAY


def test_classify_profil_vagy_szin_nelkul_placeholder_home():
    """Nincs profil, nincs szín, vagy a szín a küszöbnél messzebb esik
    minden referenciától → a dokumentált placeholder (HOME), nem kivétel."""
    assert TeamClassifier().classify(_track((12, 18, 25))) == Team.HOME
    tc = TeamClassifier(_profil())
    assert tc.classify(_track(None)) == Team.HOME
    szuk = AppearanceProfile(home=(240, 240, 240), away=(20, 20, 20),
                             match_threshold=10.0)
    assert TeamClassifier(szuk).classify(_track((120, 120, 120))) == Team.HOME


def test_classify_a_kapus_es_a_biro_nem_lesz_vendeg():
    """A kapus- és bíró-szín nem csapat-címke: a classify ezekre a
    placeholder ágra esik (HOME) — a külön kérdést az is_goalkeeper /
    is_referee válaszolja meg."""
    tc = TeamClassifier(_profil())
    assert tc.classify(_track((40, 170, 70))) == Team.HOME
    assert tc.classify(_track((235, 205, 30))) == Team.HOME


def test_is_goalkeeper_csak_a_kapus_szinre_igaz():
    """A zöld mez kapus; a mezőnyjátékos és a bíró nem az."""
    tc = TeamClassifier(_profil())
    assert tc.is_goalkeeper(_track((40, 170, 70))) is True
    assert tc.is_goalkeeper(_track((250, 250, 250))) is False
    assert tc.is_goalkeeper(_track((12, 18, 25))) is False
    assert tc.is_goalkeeper(_track((235, 205, 30))) is False


def test_is_goalkeeper_tobb_kapus_szin_es_hianyzo_adat():
    """A két csapat kapusa eltérő színű lehet — mindkettő kapus. Profil
    vagy szín nélkül senki sem kapus (nem találgatunk)."""
    prof = AppearanceProfile(home=(240, 240, 240), away=(20, 20, 20),
                             goalkeeper=[(30, 160, 60), (240, 140, 20)])
    tc = TeamClassifier(prof)
    assert tc.is_goalkeeper(_track((35, 150, 65))) is True
    assert tc.is_goalkeeper(_track((235, 150, 30))) is True
    assert tc.is_goalkeeper(_track(None)) is False
    assert TeamClassifier().is_goalkeeper(_track((35, 150, 65))) is False
    # Kapus-szín nélküli profil: a zöld mez legfeljebb ismeretlen.
    csak_csapat = AppearanceProfile(home=(240, 240, 240), away=(20, 20, 20),
                                    match_threshold=60.0)
    assert TeamClassifier(csak_csapat).is_goalkeeper(
        _track((35, 150, 65))) is False


def test_is_referee_a_profil_biro_szinere_igaz():
    """A bíró színe is a meccs-profilból jön: az egyik meccsen sárga, a
    másikon fekete — a játékos-mez egyiken sem bíró."""
    sarga = TeamClassifier(_profil())
    assert sarga.is_referee(_track((235, 205, 30))) is True
    assert sarga.is_referee(_track((250, 250, 250))) is False
    assert sarga.is_referee(_track((40, 170, 70))) is False

    fekete = TeamClassifier(AppearanceProfile(
        home=(200, 30, 30), away=(30, 60, 200), referee=[(15, 15, 15)]))
    assert fekete.is_referee(_track((20, 20, 25))) is True
    assert fekete.is_referee(_track((210, 40, 25))) is False


def test_is_referee_profil_vagy_szin_nelkul_hamis():
    """Hiányzó profil / szín / bíró-szín → senkit sem szűrünk ki bíróként."""
    assert TeamClassifier().is_referee(_track((235, 205, 30))) is False
    assert TeamClassifier(_profil()).is_referee(_track(None)) is False
    nincs_biro = AppearanceProfile(home=(240, 240, 240), away=(20, 20, 20))
    assert TeamClassifier(nincs_biro).is_referee(
        _track((235, 205, 30))) is False


def test_fit_megtartja_a_megadott_profilt_es_uresbol_is_fut():
    """A fit a már beállított profilt nem írja felül; profil nélkül üres
    profilt állít be, amivel a besorolás a placeholder ágon fut tovább."""
    prof = _profil()
    tc = TeamClassifier(prof)
    assert tc.fit([_track((250, 250, 250))]) is prof

    ures = TeamClassifier()
    tanult = ures.fit([])
    assert isinstance(tanult, AppearanceProfile)
    assert ures.profile is tanult
    assert tanult.labeled_colors() == []
    assert ures.classify(_track((12, 18, 25))) == Team.HOME
    assert ures.is_goalkeeper(_track((40, 170, 70))) is False
    assert ures._label_for(_track((40, 170, 70))) is None


def test_label_for_a_legkozelebbi_cimket_adja():
    """A belső címkéző a négy címke bármelyikét visszaadhatja."""
    tc = TeamClassifier(_profil())
    assert tc._label_for(_track((250, 250, 250))) == AppearanceLabel.HOME
    assert tc._label_for(_track((10, 10, 15))) == AppearanceLabel.AWAY
    assert tc._label_for(_track((40, 170, 70))) == AppearanceLabel.GOALKEEPER
    assert tc._label_for(_track((235, 205, 30))) == AppearanceLabel.REFEREE
