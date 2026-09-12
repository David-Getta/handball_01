"""
Kliens-őrzés: a detektálás-próba a TÚL SOK embert is kimondja.

Miért: az éles meccsen a kalibráció a lelátót is a játéktérre
vetítette, és emiatt 27 "játékos" került a pályára. A próbakockán ez
egy pillanat alatt látszott volna — de a felület csak a KEVÉS
észlelést ismerte hibaként ("persons >= 8"), a sokat nem. Így az
egyórás feldolgozás után derült ki, hogy semmi sem használható.

Futtatás:
    python -m pytest tests/test_client_calib_check.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _upload_src() -> str:
    return (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "upload_screen.dart").read_text(encoding="utf-8")


def test_probakocka_jelzi_a_tul_sok_embert():
    """A pályára eső 14+ ember a kalibráció hibája — mondjuk ki ott."""
    src = _upload_src()
    assert "tulSok" in src, "a próbakocka nem nézi a felső határt"
    assert "onCourt != null && onCourt > 18" in src, (
        "a küszöbnek a motoréval kell egyeznie (TOO_MANY_PLAYERS = 18)")
    assert "fél-pálya kalibrációt" in src, (
        "a figyelmeztetés mondja meg a teendőt is")


def test_a_verdikt_nem_lehet_jo_tul_sok_embernel():
    """A régi 'persons >= 8' önmagában a hibás esetet is átengedte."""
    src = _upload_src()
    assert "final ok = !tulSok && persons >= 8;" in src


def test_kezi_meccsablak_mezoi_leteznek():
    """A bemelegítés levágásának végső menekülőútja a kézi ablak."""
    src = _upload_src()
    assert "_matchWindowFields" in src
    assert "Meccs kezdete" in src
    assert "startS:" in src and "endS:" in src, (
        "a megadott ablak nem jut el a motorhoz")


def _calib_src() -> str:
    return (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "calibration_screen.dart").read_text(encoding="utf-8")


def test_sarok_javaslat_elerheto_a_kalibralo_kepernyon():
    """A motor ad négyszög-javaslatot — legyen mivel betölteni.

    A javaslat (`suggested_quad`) régóta megvolt a `/broadcast/lines`
    válaszában, de a kliens csak SZÖVEGBEN említette ("van javaslat"),
    használni nem lehetett. Nulláról jelölni a 4 sarkot sokkal
    nehezebb, a rosszul jelölt sarok pedig az egész elemzést elviszi.
    """
    src = _calib_src()
    assert "_suggestCorners" in src
    assert "suggested_quad" in src, "a javaslat nem jut el a sarkokhoz"
    assert "Sarkok javaslata" in src, "nincs gomb, amivel betölthető"


def test_a_javaslat_ellenorzesre_szolit():
    """A javaslat segítség, nem garancia — ezt ki kell mondani."""
    src = _calib_src()
    assert "ELLENŐRIZD" in src


def test_kalibracio_nelkul_rakerdez_az_inditas():
    """Fél-egy órás munka nem indulhat el némán kalibráció nélkül."""
    src = _upload_src()
    assert "_askNoCalibration" in src
    assert "Nincs pálya-kalibráció" in src
    # Nem tiltás: a felhasználó dönthet úgy, hogy így is elindítja.
    assert "Indítás kalibráció nélkül" in src


def _match_src() -> str:
    return (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "match_screen.dart").read_text(encoding="utf-8")


def test_a_jelentesbol_inditható_az_ujrafeldolgozas():
    """A jelentés megmondja a bajt — legyen ott a javítás gombja is.

    Az újrafeldolgozás gombja eddig CSAK a hibára futott munkákon
    látszott a kezdőlapon. A felhasználó esete viszont az volt, hogy a
    feldolgozás LEFUTOTT, csak használhatatlan lett — ott nem volt
    honnan újraindítani a javított kalibrációval.
    """
    src = _match_src()
    assert "_reprocessThisMatch" in src
    assert "Újrafeldolgozás a friss kalibrációval" in src


def test_elso_teendo_kiemelve_a_jelentesben():
    """Négy-hat figyelmeztetésnél az EGY teendő ne vesszen el."""
    src = _match_src()
    assert "next_action" in src
    assert "ELSŐ TEENDŐ" in src


def test_inditas_elotti_ellenorzo_lista():
    """A három buktató EGY helyen, MIELŐTT az óra elindulna.

    Az első éles meccs úgy ment el, hogy a felhasználó mindháromba
    belelépett egyszerre: kalibráció nélkül/rosszul indult, a
    bemelegítés bekerült az elemzésbe, és mindez csak egy óra múlva
    derült ki.
    """
    src = _upload_src()
    assert "_preStartChecklist" in src
    assert "INDÍTÁS ELŐTT" in src
    # Mindhárom pont szerepel, élő állapottal.
    assert "Pálya-kalibráció" in src
    assert "Detektálás-próba" in src
    assert "Meccs időablaka" in src
    # A próba eredménye eltárolódik — enélkül a lista nem tudná, futott-e.
    assert "_previewOk" in src and "_previewOnCourt" in src


def test_az_ujrafeldolgozas_megmondja_mit_visz_es_mit_nem():
    """A gomb a KALIBRÁCIÓT frissíti — a többit az eredetiből viszi.

    Ha a baj éppen az volt, hogy a bemelegítés bekerült az elemzésbe,
    ez a gomb nem oldja meg: azt az Új elemzés lapon kell megadni. Egy
    fél-egy órás munkát nem indítunk el ilyen félreértéssel.
    """
    src = _match_src()
    assert "meccs időablakát" in src
    assert "EREDETI indításból" in src
    assert "Indítás így" in src and "Mégse" in src


def test_a_megbizhatosag_a_jelentes_folott_latszik():
    """A figyelmeztetés az összefoglaló FÖLÖTT áll, más formában.

    Az edzői jelentés minden mondata magabiztosan fogalmaz — így is kell
    írni. De ha a feldolgozás gyenge volt, ezek a mondatok zajról
    szólnak, és ezt az edzőnek az első pillantásra tudnia kell, nem egy
    külön ablakban, amit nem biztos, hogy megnyit.
    """
    src = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
           / "ui" / "summary_panel.dart").read_text(encoding="utf-8")
    assert '"caveat"' in src
    assert "MENNYIRE BÍZHATSZ EBBEN" in src
    # A figyelmeztetés a szekciók ELŐTT álljon a listában.
    assert src.index("MENNYIRE BÍZHATSZ EBBEN") < src.index(
        "EDZŐI ÖSSZEFOGLALÓ")


def test_az_illeszkedes_merheto_a_kalibralo_kepernyorol():
    """A gépi ellenőrzés MÉG az indítás előtt: a szem a néhány képpontos
    csúszást elnézi, pedig a játékos-helyek azon múlnak. A kliensnek
    legyen gombja a méréshez, és a javasolt eltolást is tudja
    alkalmazni (mind a négy sarkot ugyanannyival — ez pontosan a rajz
    eltolása)."""
    src = _calib_src()
    assert "_measureFit" in src, "nincs mérés-hívás"
    assert "Illeszkedés ellenőrzése" in src, "nincs gomb a méréshez"
    assert "_applyFitShift" in src, "a javaslat nem alkalmazható"
    # Az összenézetben (két térfél, két kocka) is mérhető — mindkét fél.
    assert "_measureFineFit" in src and "(mindkét fél)" in src, (
        "az összenézetben nincs mérés")
    assert 'region: region,' in src.split("_measureFineFit()")[1][:2500], (
        "az összenézet-mérés nem a saját térfél vonalain mér")
    assert "Igazítsd rá" in src
    api = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
           / "services" / "api_client.dart").read_text(encoding="utf-8")
    assert "fetchCalibScore" in api and "/calib-score" in api


def test_az_elavult_illeszkedes_meres_nem_hazudik_frisset():
    """Ha a mérés után elmozdul egy sarok, a kiírt szám már NEM a
    képernyőn látható rajzé — a kliens ezt mondja is meg (különben a
    felhasználó egy rossz kalibrációra hivatkozó jó számot lát)."""
    src = _calib_src()
    assert "_fitElavult" in src
    assert "azóta mozdultak" in src


def test_mentes_elott_gepileg_is_ellenorizzuk_a_kalibraciot():
    """A négyszög lehet szabályos, és mégis a valódi pályavonalak
    MELLETT — a kezdő ezt nem veszi észre, a feldolgozás viszont eleve
    elcsúszott helyekkel indulna. Mentés előtt tehát megmérjük, és
    gyenge illeszkedésnél rákérdezünk (de nem tiltjuk: a mérés nem
    csalhatatlan, és a motor elérhetetlensége se blokkolhassa a
    kalibrálást)."""
    src = _calib_src()
    ment = src.split("Future<void> _save()")[1][:2600]
    assert "_measureFit" in ment, "mentés előtt nincs gépi ellenőrzés"
    assert '"gyenge"' in ment, "nem a gyenge ítéletnél kérdez rá"
    assert "Mentés így is" in ment, "nem lehet mégis menteni"


def test_a_visszatero_figurak_rajzzal_latszanak_a_felderitesen():
    """A figura-könyvtár nem csak egy mondat: a felderítő képernyő és a
    nyomtatható jelentés RAJZOLJA az alakot (mini pálya), mert egy
    "bal oldal, a kapuelőtér előtt" felirat kevesebb, mint a kép."""
    src = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
           / "ui" / "scouting_screen.dart").read_text(encoding="utf-8")
    assert "_figureLibraryCard" in src and "_FigureShapePainter" in src
    assert 'r["setplay_library"]' in src
    assert '("Visszatérő figuráik", Icons.replay_outlined)' in src, (
        "a szakasz nincs az ugró-sávban")


def test_a_visszatero_figura_klip_tipus_mindket_oldalon_letezik():
    """A "visszatérő figura" klip-típus: a kliens kínálja, a motor vágja —
    ha csak az egyik oldal tudna róla, a gomb üres csomagot adna."""
    gyoker = Path(__file__).resolve().parent.parent.parent
    dart = (gyoker / "client" / "lib" / "ui"
            / "clips_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "backend" / "handball" / "api"
           / "app.py").read_text(encoding="utf-8")
    assert '("recurring_figure", "A visszatérő figura"' in dart
    assert '"recurring_figure" in types' in api
    assert "recurring_figure_starts(" in api


def test_az_elo_nezet_figura_riasztast_ad():
    """Az élő követés időzített jelzései közé a visszatérő figura is
    bekerül — a kliens a /figure-alerts végpontot kérdezi."""
    gyoker = Path(__file__).resolve().parent.parent.parent
    live = (gyoker / "client" / "lib" / "ui"
            / "live_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "client" / "lib" / "services"
           / "api_client.dart").read_text(encoding="utf-8")
    assert "fetchFigureAlerts" in live and '"figura"' in live
    assert "/figure-alerts" in api


def test_frissites_utan_egyszer_megmutatja_az_ujdonsagokat():
    """A kezdőlap az új verzió első indításakor megmutatja, mi változott
    (a kiadás leírásából), és a látott verziót elmenti — másodszor már
    nem zavar; friss telepítésnél és fejlesztői buildnél nem mutatja."""
    gyoker = Path(__file__).resolve().parent.parent.parent
    dash = (gyoker / "client" / "lib" / "ui"
            / "dashboard_screen.dart").read_text(encoding="utf-8")
    store = (gyoker / "client" / "lib" / "services"
             / "session_store.dart").read_text(encoding="utf-8")
    upd = (gyoker / "client" / "lib" / "services"
           / "update_service.dart").read_text(encoding="utf-8")
    assert "_showWhatsNewIfUpdated" in dash and "Újdonságok a" in dash
    torzs = dash.split("Future<void> _showWhatsNewIfUpdated()")[1][:2000]
    assert 'appVersion.contains("-dev")' in torzs
    assert "seen.isEmpty" in torzs, "friss telepítésnél nem szabad mutatni"
    assert "setLastSeenVersion(appVersion)" in torzs
    assert "last_seen_version" in store and "setLastSeenVersion" in store
    assert "notesFor(" in upd and "releases/tags/v" in upd
