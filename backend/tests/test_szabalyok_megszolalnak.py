"""
ŐR: az edzés-szabályok a rétegek SAJÁT teszt-fixture-jein megszólalnak.

Az edzés-fókusz közel ötszáz sorszámozott szabálya mind `try/except`-ben
ül, és mindegyik egy MÁSIK réteg kimenetét olvassa. A recept szerint
minden ilyen szabály mellé kell egy teszt, amely a VALÓDI forrás-réteget
futtatja, és megnézi, hogy a szabály tényleg megszólal — a lefedettség-
mérés szerint viszont a szabályok mintegy kétötöde (190) egyetlen
tesztben sem szólalt meg: a réteg tesztje a réteget nézte a saját
fixture-jén, a szabályt pedig senki nem futtatta rajta.

Ez az őr összeköti a kettőt: a rétegek tesztfájljainak fixture-építőit
(azokat a paraméter nélkül hívható függvényeket, amelyek a réteg
ítéletét kiváltó meccset építik) átadja az edzés-fókusznak, és
megköveteli, hogy a táblában felsorolt szabályok megszólaljanak — a
valódi rétegekkel, a valódi mezőnevekkel, a mondat valódi
formázásával. 37 fixture 324 szabályt szólaltat meg, köztük
65 olyat, amely eddig egyetlen tesztben sem futott le.

A tábla úgy készült, hogy minden paraméter nélküli fixture-építőn
lefutott az edzés-fókusz, és a legkevesebb fixture maradt, amely az
összes megszólaló szabályt lefedi; minden szabály annál az EGY
fixture-nél szerepel, amelyik "felel érte". A megszólalás
determinisztikus (hash-magtól független).

KARBANTARTÁS:
  - Ha egy szabály küszöbét SZÁNDÉKOSAN változtatod, és a fixture-ön
    már nem szólal meg: vedd ki a számát a tábla sorából, vagy tedd át
    egy olyan fixture-höz, amelyen megszólal.
  - Ha egy fixture-építőt átnevezel vagy törölsz, a tábla sorát is
    igazítsd.
  - Új szabályt NEM kötelező ide felvenni — a saját tesztjében
    szólaltasd meg (CLAUDE.md: "A try/except és a néma mezőnév").
Amelyik szabály NINCS a táblában, arra ez az őr semmit sem állít: a
többi (170) szabálynak ma nincs olyan paraméter nélküli fixture-je,
amelyen megszólalna.

Futtatás:
    python -m pytest tests/test_szabalyok_megszolalnak.py -q
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

ITT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ITT))
if ITT not in sys.path:               # a többi tesztfájl fixture-építőihez
    sys.path.insert(0, ITT)

import pytest  # noqa: E402

from handball.models.tracking import Match  # noqa: E402
from handball.pipeline import training  # noqa: E402

# (tesztfájl, fixture-építő, {oldal: [a fixture-ön megszólaló szabályok]})
_TABLA = [
    ("test_court3d", "_kiallitasos_meccs", {
        "home": [7, 12, 37, 89, 95, 97, 112, 113, 123, 124, 133, 145, 166,
                 168, 170, 179, 180, 183, 184, 214, 219, 220, 221, 224, 227,
                 230, 272, 273, 279, 280, 287, 289, 295, 304, 306, 310, 316,
                 317, 326, 331, 335, 350, 352, 368, 370, 372, 374, 378, 393,
                 396, 400, 401, 402, 403, 404, 405, 409, 411, 420, 445, 448,
                 462, 469, 487, 488, 490, 495],
        "away": [1, 9, 22, 31, 34, 36, 39, 44, 48, 78, 88, 90, 107, 125, 135,
                 144, 152, 153, 166, 171, 175, 179, 183, 198, 208, 213, 231,
                 236, 237, 240, 244, 247, 263, 272, 402, 405, 442, 454, 476,
                 489, 491, 493]}),
    ("test_defense", "_conceded_type_match", {
        "home": [5, 46, 82, 122, 149, 200, 223, 266, 270, 292, 305, 322, 328,
                 330, 339, 341, 342, 351, 354, 359, 382, 433, 434, 435, 467],
        "away": [4, 5, 6, 8, 26, 27, 32, 33, 64, 69, 79, 85, 110, 126, 163,
                 177, 203, 206, 239, 241, 269, 382, 399, 478]}),
    ("test_attack_types", "_scy_match", {
        "home": [92, 130, 162, 209, 254, 271, 296, 303, 356, 362, 363, 414,
                 480],
        "away": [47, 102, 218, 238, 243, 390, 424, 436]}),
    ("test_rules", "_psr_match", {
        "home": [42, 51, 132, 138, 165, 192, 215, 248, 253, 299, 329, 355,
                 371, 418, 430, 468],
        "away": [371, 417, 425, 468, 486]}),
    ("test_defense", "_blf_match", {
        "home": [20, 41, 52, 94, 225, 291, 294, 340, 343, 431, 438],
        "away": [13, 408, 415]}),
    ("test_rules", "_pp_pace_match", {
        "home": [116, 128, 147, 364, 375, 394, 449, 479, 483],
        "away": [29, 128, 131, 147, 364, 380, 395, 479]}),
    ("test_xg", "_dbs_match", {
        "home": [81, 146, 233],
        "away": [2, 35, 74, 167, 176, 315, 384, 482]}),
    ("test_defense", "_cds_match", {
        "home": [76, 87, 142, 307, 456],
        "away": [49, 87, 142, 150, 191, 426, 485]}),
    ("test_rules", "_svy_match", {
        "home": [28, 293, 334, 358, 397, 458, 466],
        "away": [65, 211]}),
    ("test_goalkeeper", "_otr_match", {
        "home": [17, 212, 427],
        "away": [72, 228, 383, 413]}),
    ("test_priorities", "_kp_match", {
        "home": [140, 308, 367],
        "away": [277, 297, 302, 308, 349]}),
    ("test_goalkeeper", "_hand_gk_match", {
        "home": [460],
        "away": [50, 178, 385, 453]}),
    ("test_attack_types", "_tbs_match", {
        "home": [10, 232, 376],
        "away": [53, 407]}),
    ("test_attack_types", "_distance_fade_match", {
        "home": [77, 154, 222, 257, 457],
        "away": []}),
    ("test_rules", "_sur_match", {
        "home": [25, 392, 412],
        "away": [187, 226]}),
    ("test_court3d", "_hetes_meccs", {
        "home": [275, 281, 443, 464],
        "away": []}),
    ("test_substitutions", "_sby_match", {
        "home": [158, 186, 323, 419],
        "away": []}),
    ("test_goalkeeper", "_shorthanded_gk_match", {
        "home": [15, 155, 416],
        "away": []}),
    ("test_setplays", "_csp_match", {
        "home": [30, 136, 484],
        "away": []}),
    ("test_goalkeeper", "_clutch_gk_match", {
        "home": [],
        "away": [11, 59, 381]}),
    ("test_momentum", "_clutch_turnover_match", {
        "home": [58, 159, 406],
        "away": [159, 406]}),
    ("test_setplays", "_spd_match", {
        "home": [422, 446],
        "away": []}),
    ("test_goalkeeper", "_ent_match", {
        "home": [19, 410],
        "away": []}),
    ("test_roles", "_rht_match", {
        "home": [84, 117],
        "away": []}),
    ("test_goalkeeper", "_ops_match", {
        "home": [67, 246],
        "away": []}),
    ("test_attack_types", "_bks_match", {
        "home": [252, 379],
        "away": []}),
    ("test_attack_types", "_brf_match", {
        "home": [21, 229],
        "away": []}),
    ("test_roles", "_spc_match", {
        "home": [190],
        "away": [262]}),
    ("test_kozepkezdes", "_meccs", {
        "home": [268],
        "away": [268]}),
    ("test_defense", "_line_score_swing_match", {
        "home": [],
        "away": [129]}),
    ("test_setplays", "_sbs_match", {
        "home": [],
        "away": [60]}),
    ("test_goalkeeper", "_krt_match", {
        "home": [421],
        "away": []}),
    ("test_attack_types", "_crp_match", {
        "home": [444],
        "away": []}),
    ("test_stoppages", "_match", {
        "home": [],
        "away": [210]}),
    ("test_rules", "_ppy_match", {
        "home": [],
        "away": [156]}),
    ("test_player_training", "_terheles_match", {
        "home": [189],
        "away": []}),
    ("test_goalkeeper", "_early_gk_match", {
        "home": [],
        "away": [161]}),
]


# A szövegbe formázott érték nem lehet "None" / "nan" / kapcsos zárójel
# (elrontott f-string) — ez a megszólaló tétel szöveg-épsége.
_ROSSZ_SZOVEG = re.compile(r"\bNone\b|\bnan\b|\binf\b|[{}]")


def _fixture(modul: str, epito: str) -> Match:
    """A `modul` tesztfájl `epito` fixture-építőjének meccse."""
    mod = importlib.import_module(modul)
    fv = getattr(mod, epito, None)
    assert fv is not None, (
        f"a {modul}.py-ban nincs {epito}() — ha átnevezted vagy törölted, "
        "igazítsd a táblát (lásd a modul-docstring KARBANTARTÁS részét)")
    meccs = fv()
    assert isinstance(meccs, Match) and meccs.frames, (modul, epito)
    return meccs


def _megszolalt(meccs: Match, monkeypatch) -> dict:
    """{oldal: {szabály-szám: [tétel, …]}} — MINDEN megszólaló tétel, a
    fókusz ötös korlátja nélkül (a rangsor helyére a nyers lista kerül)."""
    monkeypatch.setattr(training, "rank_focus",
                        lambda items, limit=None: list(items))
    nyers = training.training_focus(meccs)
    ki: dict = {"home": {}, "away": {}}
    for oldal in ki:
        for tetel in nyers[oldal]:
            ki[oldal].setdefault(tetel["_szabaly"], []).append(tetel)
    return ki


@pytest.mark.parametrize("modul, epito, vart", _TABLA,
                         ids=[f"{m}:{e}" for m, e, _ in _TABLA])
def test_a_szabalyok_megszolalnak_a_reteg_fixture_jen(modul, epito, vart,
                                                      monkeypatch):
    """A réteg saját fixture-jén a táblában felsorolt edzés-szabályok
    megszólalnak — a valódi réteggel —, és a tétel szövege ép (terület,
    cím, indoklás, gyakorlat; elrontott formázás nélkül)."""
    kapott = _megszolalt(_fixture(modul, epito), monkeypatch)
    for oldal in ("home", "away"):
        nema = sorted(set(vart[oldal]) - set(kapott[oldal]))
        assert not nema, (
            f"{modul}.{epito}() — {oldal}: ezek a szabályok már nem "
            f"szólalnak meg: {nema} (szándékos küszöb-változásnál igazítsd "
            "a táblát; különben a szabály vagy a réteg romlott el)")
        for szam in vart[oldal]:
            for tetel in kapott[oldal][szam]:
                for mezo in ("area", "title", "why", "drill"):
                    szoveg = tetel.get(mezo)
                    assert isinstance(szoveg, str) and szoveg.strip(), (
                        szam, mezo, tetel)
                    assert not _ROSSZ_SZOVEG.search(szoveg), (szam, mezo,
                                                              szoveg)


def _forras_szabalyai() -> set:
    forras = Path(training.__file__).read_text(encoding="utf-8")
    return {int(m.group(1)) for m in
            re.finditer(r"^\s+_szabaly = (\d+)\s*$", forras, re.M)}


def test_a_tabla_letezo_szabalyokat_sorol_es_nem_uresedik_ki():
    """A tábla minden száma létező szabály, egy szabályért EGY fixture
    felel, minden sor legalább egy szabályt megkövetel, és a tábla a
    szabályok legalább hatvan százalékát lefedi (ha ez alá esik, a tábla
    üresedik — nem a szabályok lettek jobbak)."""
    letezo = _forras_szabalyai()
    felelos: dict = {}
    for modul, epito, vart in _TABLA:
        szamok = set(vart["home"]) | set(vart["away"])
        assert szamok, (modul, epito)
        assert szamok <= letezo, (modul, epito, sorted(szamok - letezo))
        for szam in szamok:
            assert szam not in felelos, (szam, felelos[szam], epito)
            felelos[szam] = f"{modul}.{epito}"
        assert vart["home"] == sorted(set(vart["home"]))
        assert vart["away"] == sorted(set(vart["away"]))
    assert len(felelos) >= 0.6 * len(letezo), (len(felelos), len(letezo))
    assert len({(m, e) for m, e, _ in _TABLA}) == len(_TABLA)


def test_a_nyers_lista_a_fokusz_forrasa(monkeypatch):
    """Ön-teszt: a nyers (korlát nélküli) lista ugyanazokból a tételekből
    áll, amelyekből a valódi fókusz válogat — a fókusz legfeljebb
    MAX_ITEMS tétel, mind a nyers listából, a belső sorszám nélkül."""
    modul, epito, _ = _TABLA[1]
    meccs = _fixture(modul, epito)
    fokusz = training.training_focus(meccs)          # a valódi rangsorral
    nyers = _megszolalt(meccs, monkeypatch)
    for oldal in ("home", "away"):
        osszes = [(t["area"], t["title"], t["why"])
                  for tetelek in nyers[oldal].values() for t in tetelek]
        assert len(fokusz[oldal]) <= training.MAX_ITEMS
        assert len(fokusz[oldal]) == min(training.MAX_ITEMS, len(osszes))
        for tetel in fokusz[oldal]:
            assert "_szabaly" not in tetel
            assert (tetel["area"], tetel["title"], tetel["why"]) in osszes
