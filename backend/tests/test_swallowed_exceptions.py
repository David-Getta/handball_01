"""
Tesztek az elnyelt-kivétel jelentés szkriptjére
(scripts/swallowed_exceptions.py).

A szkript percekig fut (minden réteg + az API), ezért a csomag eddig
csak a jelentés-építőjét tesztelte — a nyomkövető (_Gyujto), a mérés
(measure) és a main egyszer sem futott. Itt kicsiben: a nyomkövető egy
próba-modulon, a mérés két-három réteggel és egy mini-alkalmazással.

A jelentés-építő tesztje és a beírt jelentés őre a
tests/test_nema_kivetelek.py-ban él.

Futtatás:
    python -m pytest tests/test_swallowed_exceptions.py -q
"""

from __future__ import annotations

import importlib.util
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from scripts import swallowed_exceptions as se  # noqa: E402

_PROBA_MODUL = '''
def tiszta():
    return 1


def elnyelo():
    try:
        raise ValueError("ezt valaki lenyeli")
    except ValueError:
        return None


def belso():
    raise KeyError("mélyről jön")


def kulso():
    try:
        belso()
    except KeyError:
        return "elnyelve"


def bukik():
    raise RuntimeError("x" * 500)


def nem_hiba():
    try:
        next(iter(()))
    except StopIteration:
        pass
    try:
        open("/nincs/ilyen/fajl/sehol.txt")
    except FileNotFoundError:
        pass

    def gen():
        yield 1
    g = gen()
    next(g)
    g.close()
    return "rendben"
'''


@pytest.fixture
def nyomkoveto():
    """A teszt után az eredeti nyomkövető áll vissza (a szkript a sajátját
    None-ra állítja — más eszköz követőjét nem hagyhatjuk kikapcsolva)."""
    regi = sys.gettrace()
    yield
    sys.settrace(regi)


@pytest.fixture
def proba(tmp_path):
    """Egy próba-"csomag" a tmp mappában: a gyűjtő csak az `hb` gyökér
    alatti fájlok kivételeit követi."""
    fajl = tmp_path / "kis.py"
    fajl.write_text(_PROBA_MODUL, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("sm_proba_kis", fajl)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, se._Gyujto(str(tmp_path))


def test_gyujto_megtalalja_az_elnyelt_kivetelt(proba, nyomkoveto):
    """A lenyelt kivétel hellyel (típus, fájl, sor, függvény), darabbal,
    üzenettel és a felülettel kerül a találatok közé — miközben a felület
    maga nem bukott el (None)."""
    mod, gy = proba
    assert gy.futtat("felület-1", mod.elnyelo) is None
    assert len(gy.talalat) == 1
    (tipus, fajl, sor, fv), rec = next(iter(gy.talalat.items()))
    assert (tipus, fajl, fv) == ("ValueError", "kis.py", "elnyelo")
    assert sor == _PROBA_MODUL.splitlines().index(
        '        raise ValueError("ezt valaki lenyeli")') + 1
    assert rec == {"n": 1, "uzenet": "ezt valaki lenyeli",
                   "feluletek": ["felület-1"]}


def test_gyujto_tiszta_feluleten_es_vezerlo_kiveteleknel_ures(proba,
                                                              nyomkoveto):
    """Hibátlan futásnál nincs találat; a bejárás vége, a generátor
    lezárása és a fájl-hiány (NEM_HIBA) vezérlés, nem elnyelt hiba."""
    mod, gy = proba
    assert gy.futtat("tiszta", mod.tiszta) is None
    assert gy.futtat("vezérlés", mod.nem_hiba) is None
    assert gy.talalat == {}
    assert {"StopIteration", "GeneratorExit",
            "FileNotFoundError", "HTTPException"} <= se.NEM_HIBA


def test_gyujto_egy_kivetelt_egyszer_szamol_a_szuletese_helyen(proba,
                                                               nyomkoveto):
    """A több kereten átutazó kivétel EGY találat, a SZÜLETÉSE helyén
    (a belső függvényben) — nem ott, ahol végül lenyelték."""
    mod, gy = proba
    assert gy.futtat("felület", mod.kulso) is None
    assert [(k[0], k[3], rec["n"]) for k, rec in gy.talalat.items()] == [
        ("KeyError", "belso", 1)]


def test_gyujto_ugyanaz_a_hely_tobb_feluletrol_osszeadodik(proba,
                                                            nyomkoveto):
    """Ugyanaz a hely több futásból: a darabszám nő, a felületek listája
    ismétlés nélkül bővül."""
    mod, gy = proba
    gy.futtat("összefoglaló", mod.elnyelo)
    gy.futtat("felderítés", mod.elnyelo)
    gy.futtat("felderítés", mod.elnyelo)
    (rec,) = gy.talalat.values()
    assert rec["n"] == 3
    assert rec["feluletek"] == ["összefoglaló", "felderítés"]


def test_gyujto_az_elbukott_feluletet_is_jelzi(proba, nyomkoveto):
    """Ha a felület maga bukik el, a futtat a hiba (levágott) szövegét
    adja vissza — és a kivétel a találatok közt is ott van."""
    mod, gy = proba
    hiba = gy.futtat("bukó felület", mod.bukik)
    assert hiba.startswith("RuntimeError: xxx") and len(hiba) == 200
    (kulcs, rec), = gy.talalat.items()
    assert kulcs[0] == "RuntimeError" and kulcs[3] == "bukik"
    assert len(rec["uzenet"]) == 160
    assert rec["feluletek"] == ["bukó felület"]


def test_gyujto_csak_a_sajat_gyoker_alatti_kodot_koveti(proba, nyomkoveto):
    """A gyökéren KÍVÜLI kód (itt: maga a tesztfájl) lenyelt kivétele nem
    találat — a jelentés a handball-kódról szól, nem a könyvtárakról."""
    _, gy = proba

    def kulso_kod():
        try:
            raise ValueError("a teszt saját kivétele")
        except ValueError:
            return None

    assert gy.futtat("külső", kulso_kod) is None
    assert gy.talalat == {}


def test_gyujto_a_futas_utan_lekapcsolja_a_nyomkovetot(proba, nyomkoveto):
    """A követő a futtatás végén lekapcsol — akkor is, ha a felület
    elbukott —, hogy a következő (követés nélküli) kód ne lassuljon."""
    mod, gy = proba
    gy.futtat("jó", mod.tiszta)
    assert sys.gettrace() is None
    gy.futtat("bukó", mod.bukik)
    assert sys.gettrace() is None


def test_kotelezo_a_parameter_jelzojet_mindket_alakban_olvassa():
    """A lekérdezés-paraméter kötelező volta a FastAPI-változattól függően
    a `required` mezőben vagy a `field_info.is_required()`-ben él."""
    assert se._kotelezo(SimpleNamespace(required=True)) is True
    assert se._kotelezo(SimpleNamespace(required=False)) is False
    assert se._kotelezo(SimpleNamespace(
        field_info=SimpleNamespace(is_required=lambda: True))) is True
    assert se._kotelezo(SimpleNamespace(
        field_info=SimpleNamespace(is_required=lambda: False))) is False


def test_kotelezo_a_valodi_fastapi_utvonalon():
    """A telepített FastAPI valódi útvonalán: a kötelező lekérdezés-
    paraméter igaz, az alapértékes hamis."""
    fastapi = pytest.importorskip("fastapi")
    from fastapi.routing import APIRoute

    app = fastapi.FastAPI()

    def vegpont(match_id: str, team: str, limit: int = 5):
        return {}

    vegpont.__annotations__ = {"match_id": str, "team": str, "limit": int}
    app.get("/matches/{match_id}/x")(vegpont)
    (ut,) = [r for r in app.routes if isinstance(r, APIRoute)]
    jelzok = {q.name: se._kotelezo(q) for q in ut.dependant.query_params}
    assert jelzok == {"team": True, "limit": False}


def test_meccs_datummal_mezszammal_megismetelhetoen():
    """A mérés próba-meccse: a megadott dátummal, minden játékoson
    mezszámmal (1..14), és ugyanazzal a maggal ugyanaz."""
    m = se._meccs(6.0, 5, "2026-01-15")
    assert m.meta.date == "2026-01-15"
    assert m.frames
    for f in m.frames[:50]:
        for p in f.players:
            assert p.jersey_number == (p.track_id % 14) + 1
            assert 1 <= p.jersey_number <= 14
    ujra = se._meccs(6.0, 5, "2026-01-15")
    assert len(ujra.frames) == len(m.frames)
    assert [(p.x, p.y) for p in ujra.frames[10].players] == \
        [(p.x, p.y) for p in m.frames[10].players]
    masik = se._meccs(6.0, 11, "2026-02-15")
    assert masik.meta.date == "2026-02-15"


def _mini_app(szamlalo):
    """Mini-alkalmazás a méréshez: egy meccs-szintű GET (ami a handball
    kódjában született kivételt nyel le), egy kötelező paraméteres és egy
    útvonal-paraméter nélküli végpont (ezeket a mérés kihagyja)."""
    from fastapi import FastAPI

    from handball.pipeline._homography import homography_from_points

    app = FastAPI()

    def proba(match_id: str):
        szamlalo.append(match_id)
        try:
            homography_from_points([], [])
        except ValueError:
            pass
        return {"id": match_id}

    def kell(match_id: str, team: str):
        szamlalo.append("kell")
        return {}

    def health():
        szamlalo.append("health")
        return {}

    proba.__annotations__ = {"match_id": str}
    kell.__annotations__ = {"match_id": str, "team": str}
    app.get("/matches/{match_id}/proba")(proba)
    app.get("/matches/{match_id}/kell")(kell)
    app.get("/health")(health)
    return app


def _kis_meres(monkeypatch, retegek, szamlalo):
    """A mérés kicsiben: a megadott rétegekkel és a mini-alkalmazással."""
    pytest.importorskip("fastapi")
    import handball.api.app as api_mod
    from scripts import order_sensitivity

    monkeypatch.setattr(order_sensitivity, "_layer_functions",
                        lambda: retegek)
    monkeypatch.setattr(api_mod, "create_app", lambda: _mini_app(szamlalo))
    return se.measure(seconds=6.0)


def test_measure_tiszta_retegeken_ures_lista(monkeypatch, nyomkoveto):
    """Hibátlan rétegekkel és felületekkel a találat-lista ÜRES (ezt őrzi
    a beírt jelentés), semmi sem bukik el; a mérés a rétegeket, a négy
    nagy felületet, a meccs-szintű GET-et és a több meccses felületeket
    számolja — a kötelező paraméteres és a meccs nélküli végpontot nem."""
    import threading

    from handball.pipeline import xg

    monkeypatch.setattr(xg, "_proba_tiszta", lambda match: {"home": {}},
                        raising=False)
    szamlalo: list = []
    regi_env = os.environ.get("HANDBALL_DATA_DIR")
    res = _kis_meres(monkeypatch, [("xg", "xg", "match_xg"),
                                   ("tiszta", "xg", "_proba_tiszta")],
                     szamlalo)
    assert res["elbukott"] == []
    # 2 réteg + 3 nagy felület + 1 meccs-szintű GET + 9 több meccses.
    assert res["feluletek"] == 2 + 3 + 1 + 9
    assert szamlalo == ["sim-5"]             # csak a meccs-szintű GET futott
    # A mini-alkalmazás GET-je a handball kódjában született kivételt
    # nyel le — a mérés a végpont SZÁLÁN is követ, és megtalálja.
    assert [(k[0], k[1], k[3]) for k in res["talalat"]] == [
        ("ValueError", os.path.join("pipeline", "_homography.py"),
         "homography_from_points")]
    (rec,) = res["talalat"].values()
    assert rec["feluletek"] == ["GET /matches/{match_id}/proba"]
    # A mérés rendet hagy maga után: a környezet és a követők visszaállnak.
    assert os.environ.get("HANDBALL_DATA_DIR") == regi_env
    assert sys.gettrace() is None and threading.gettrace() is None


def test_measure_megnevezi_az_elnyelo_es_az_elbuko_reteget(monkeypatch,
                                                           nyomkoveto):
    """Egy réteg, amely a handball kódjában született kivételt nyel le,
    a találatok közé kerül a réteg nevével; egy réteg, amely maga bukik
    el, az "elbukott" listára a hiba szövegével."""
    from handball.pipeline import xg
    from handball.pipeline._homography import homography_from_points

    def elnyelo(match):
        try:
            homography_from_points([(0, 0)], [(0, 0)])
        except ValueError:
            return {"home": None, "away": None}

    def bukik(match):
        return homography_from_points([], [])

    monkeypatch.setattr(xg, "_proba_elnyelo", elnyelo, raising=False)
    monkeypatch.setattr(xg, "_proba_bukik", bukik, raising=False)
    res = _kis_meres(monkeypatch, [("elnyelő", "xg", "_proba_elnyelo"),
                                   ("bukó", "xg", "_proba_bukik")], [])

    assert [n for n, _ in res["elbukott"]] == ["réteg:bukó"]
    assert res["elbukott"][0][1].startswith("ValueError: legalább 4 pont")
    (kulcs, rec), = res["talalat"].items()
    assert kulcs[0] == "ValueError" and kulcs[3] == "homography_from_points"
    assert rec["n"] == 3                     # elnyelő + bukó + a mini-GET
    assert rec["feluletek"] == ["réteg:elnyelő", "réteg:bukó",
                                "GET /matches/{match_id}/proba"]
    # A jelentés ebből a javítandó listát és az elbukott felületet írja.
    szoveg = se.build_report(res, 6.0)
    assert "## Elnyelt kivételek (JAVÍTANDÓ)" in szoveg
    assert "réteg:elnyelő" in szoveg
    assert "## Elbukott felületek" in szoveg and "réteg:bukó: ValueError" in szoveg


def test_main_kiirja_a_jelentest_es_az_osszegzest(monkeypatch, tmp_path,
                                                  capsys):
    """A main a mérés eredményéből megírja a jelentés-fájlt, és a
    kimenetre összegez (felület-szám, találatok hellyel, elbukottak) —
    a teszt a jelentést a tmp mappába irányítja, a doksit nem írja át."""
    jelentes = tmp_path / "ELNYELT_KIVETELEK.md"
    kert: dict = {}

    def kamu_meres(seconds):
        kert["seconds"] = seconds
        return {"feluletek": 12, "elbukott": [("GET /x", "KeyError: 'a'")],
                "talalat": {("ValueError", "pipeline/xg.py", 42, "match_xg"):
                            {"n": 2, "uzenet": "rossz",
                             "feluletek": ["összefoglaló", "edzés-fókusz"]}}}

    monkeypatch.setattr(se, "measure", kamu_meres)
    monkeypatch.setattr(se, "_REPORT", jelentes)
    assert se.main(["--seconds", "30"]) == 0
    assert kert["seconds"] == 30.0

    szoveg = jelentes.read_text(encoding="utf-8")
    assert szoveg == se.build_report(kamu_meres(30.0), 30.0)
    assert "(30 mp, félidővel, lövésekkel)" in szoveg
    ki = capsys.readouterr().out
    assert f"Elnyelt-kivétel jelentés kiírva: {jelentes}" in ki
    assert "átvizsgált felület: 12" in ki
    assert "elnyelt kivétel (hely): 1" in ki
    assert "- ValueError pipeline/xg.py:42 (match_xg) 2× — " \
           "összefoglaló, edzés-fókusz" in ki
    assert "elbukott felület: 1" in ki and "- GET /x: KeyError: 'a'" in ki


def test_main_ures_meresnel_az_ures_lista_jelentese(monkeypatch, tmp_path,
                                                    capsys):
    """Találat nélkül a jelentés az "üres lista" mondatot írja (ezt
    keresi az őr-teszt), és az alap-hosszal (120 mp) mér."""
    jelentes = tmp_path / "jelentes.md"
    kert: dict = {}

    def kamu_meres(seconds):
        kert["seconds"] = seconds
        return {"feluletek": 3, "elbukott": [], "talalat": {}}

    monkeypatch.setattr(se, "measure", kamu_meres)
    monkeypatch.setattr(se, "_REPORT", jelentes)
    assert se.main([]) == 0
    assert kert["seconds"] == se.DEFAULT_SECONDS == 120.0
    szoveg = jelentes.read_text(encoding="utf-8")
    assert "Az elnyelt-kivétel lista üres" in szoveg
    assert "JAVÍTANDÓ" not in szoveg and "Elbukott felületek" not in szoveg
    ki = capsys.readouterr().out
    assert "elnyelt kivétel (hely): 0" in ki and "elbukott felület: 0" in ki
