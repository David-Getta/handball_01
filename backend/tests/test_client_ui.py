"""
Kliens-őrzések: a Flutter-felület olyan tulajdonságai, amiket fordító
nélkül is meg lehet — és meg KELL — követelni.

A gépen nincs Flutter, tehát a kliens nem fordul le a tesztek alatt. A
felület viszont ugyanúgy elromolhat némán, mint a backend: elgépelt
kulcs, ami üres csempét ad; felirat nélküli pörgettyű; nyers kivétel a
képernyőn; olyan ugró-gomb, ami nem talál célt. Ezek a tesztek a Dart
FORRÁSBÓL olvasva zárják ezeket a réseket.

Ami ide tartozik: minden, ami a `client/` alatti fájlok szerkezetéről
vagy szövegéről szól. Ami NEM: a backend rétegeinek regisztrációja —
az a test_layer_registry.py-ban van.

Futtatás:
    python -m pytest tests/test_client_ui.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

# A kliens-csempék beágyazott sor-kulcsai: ezek nem ScoutingReport-
# mezők, hanem lista-elemek belső kulcsai (player_id, frames, ...)
# vagy más térképből olvasott értékek. Zárt lista — új felső szintű
# kulcs ide nem kerülhet.
# Kulcsok, amiket NEM a ScoutingReport mezői adnak: a beágyazott
# sor-szótárak kulcsai, és a `report_to_dict` által számolt, származtatott
# mezők (narrative = a szöveges bevezető, caveat = mennyire hihető a
# jelentés alapanyaga).
_DART_ROW_KEYS = {
    "breaks", "caveat", "chances", "count", "def_frames", "depth_sum_m",
    "frames", "jersey", "narrative", "player_id", "setter_id",
    "shooter_id", "sprints", "takes",
}

def test_kliens_kulcsok_letezo_mezok():
    """A kliens minden csempe-helperje r["..."] kulcsokkal olvassa a
    felderítés-profilt — egy elgépelt kulcs némán üres csempét adna.
    Minden Dart-oldali kulcsnak létező ScoutingReport-mezőnek kell
    lennie (a beágyazott sor-kulcsok zárt listája kivétel)."""
    import dataclasses

    from handball.pipeline import scouting

    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    keys = set(re.findall(r'r\["([a-z0-9_]+)"\]',
                          dart.read_text(encoding="utf-8")))
    assert len(keys) > 400, "a kulcs-olvasás elromlott"
    fields = {f.name for f in dataclasses.fields(scouting.ScoutingReport)}
    unknown = sorted(keys - fields - _DART_ROW_KEYS)
    assert not unknown, (
        f"a kliens nem létező felderítés-mezőket olvas: {unknown}")

def test_kliens_helper_nevek_egyediek():
    """Két azonos nevű Dart-helper az egész osztályban fordítási hibát
    okoz — a zárójel-egyensúly ellenőrzés ezt nem látja, a kiadási
    (Flutter build) csak ott bukik ki. Itt fogjuk meg előbb."""
    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    names = re.findall(
        r'^\s+(?:String\?|Widget|bool|int|double|List<[^>]+>\??)\s+'
        r'(_\w+)\(', dart.read_text(encoding="utf-8"), flags=re.M)
    assert len(names) > 200, "a helper-olvasás elromlott"
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplán deklarált kliens-helperek: {dupes}"

def test_kliens_csempe_cimkek_egyediek():
    """Két azonos című csempe a felderítés-listában
    megkülönböztethetetlen a felhasználónak — a címkéknek egyedieknek
    kell lenniük (a v0.1.23 kiadásnál három ütközés is volt)."""
    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    labels = re.findall(r'\["([^"]+)", _\w+\(r\)!\]',
                        dart.read_text(encoding="utf-8"))
    assert len(labels) > 200, "a címke-olvasás elromlott"
    dupes = sorted({l for l in labels if labels.count(l) > 1})
    assert not dupes, f"ismétlődő csempe-címkék: {dupes}"

def test_kliens_csempe_helperek_leteznek():
    """Minden csempe-sorban hivatkozott Dart-helper legyen deklarálva
    is — a hiányzó helper csak a Flutter-buildnél bukna ki (mint a
    v0.1.23-as kiadásnál a névütközés), itt fogjuk meg előbb."""
    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    src = dart.read_text(encoding="utf-8")
    declared = set(re.findall(
        r'^\s+(?:String\?|Widget|bool|int|double|List<[^>]+>\??)\s+'
        r'(_\w+)\(', src, flags=re.M))
    used = set(re.findall(r'\[\"[^\"]+\", (_\w+)\(r\)!\]', src))
    assert len(used) > 200, "a csempe-olvasás elromlott"
    missing = sorted(used - declared)
    assert not missing, f"csempéből hivatkozott, de hiányzó helperek: {missing}"

def test_kliens_mutato_csoportok_lefedik_a_csempeket():
    """A mutató-fal minden csempéje valódi csoportba essen.

    A felderítés-képernyőn háromszáz körüli mérőszám van; ezek
    csoportosítva és kereshetően jelennek meg. A csoportot a címke
    kulcsszavai döntik el — ha egy ÚJ réteg csempéje egyik kulcsszóra
    sem illeszkedik, csendben az "Egyéb" gyűjtőbe csúszik, és ott
    elveszik. Ez az őr ezt fogja meg: ilyenkor vagy a címkét kell
    beszédesebbre venni, vagy a csoport kulcsszavait bővíteni.
    """
    import re
    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    src = dart.read_text(encoding="utf-8")

    # A csoport-szabályok kiolvasása a Dart forrásból.
    start = src.index("_metricGroups = [")
    end = src.index("\n  ];", start)
    keywords = re.findall(r'"([^"]+)"', src[start:end])
    # Az első idézőjeles elem minden rekordban a csoport NEVE — a
    # kulcsszavak közé az is beleférne, de csak rontaná a lefedést,
    # ezért nem szűrjük ki: a nevek nem illeszkednek címkékre.
    assert len(keywords) > 50, "a csoport-szabályok olvasása elromlott"

    # A csempe-címkék kiolvasása.
    t0 = src.index("final tiles = <List<String>>[")
    t1 = src.index("\n    ];", t0)
    labels = re.findall(r'\["([^"]+)",', src[t0:t1])
    assert len(labels) > 200, "a csempe-olvasás elromlott"

    orphans = sorted({lab for lab in labels
                      if not any(k in lab.lower() for k in keywords)})
    assert not orphans, (
        "ezek a csempék az \"Egyéb\" csoportba esnének (bővítsd a "
        f"_metricGroups kulcsszavait vagy pontosítsd a címkét): {orphans}")

def test_kliens_ikongombok_kapnak_sugobuborekot():
    """Minden csak-ikonos gombnak legyen tooltipje.

    Egy név nélküli ikonról a felhasználó nem tudja kitalálni, mit
    csinál — a kezdőlapon nyolc egyforma szürke ikon sorakozott, és
    három gombnak még súgóbuboréka sem volt. A tooltip a minimum:
    rámutatásra megmondja, mi ez.
    """
    import re
    root = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui")
    if not root.exists():
        pytest.skip("nincs kliens a fában")
    offenders = []
    for path in sorted(root.rglob("*.dart")):
        src = path.read_text(encoding="utf-8")
        # Durva, de elég: egy IconButton(...) blokk a kiegyensúlyozott
        # zárójelig (egy szint beágyazott zárójelet kezel).
        for m in re.finditer(r"IconButton\((?:[^()]|\([^()]*\))*\)", src,
                             flags=re.S):
            if "tooltip:" not in m.group(0):
                line = src[:m.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line}")
    assert not offenders, (
        "tooltip nélküli ikongombok (a felhasználó nem tudja, mit "
        f"csinálnak): {offenders}")

def test_kliens_nem_ir_ki_nyers_kivetelt():
    """A felületen ne jelenjen meg nyers kivétel-szöveg.

    A `SocketException: Connection refused (OS Error: ..., errno = 111),
    address = 127.0.0.1, port = 8000` egy edzőnek semmit nem mond — sem
    azt, mi történt, sem azt, mit tegyen. A kiírás ezért a
    `humanError(e)`-n megy át (`ui/error_text.dart`).

    Kivétel csak ott van, ahol a nyers szöveg LOGIKÁHOZ kell (pl.
    "404"/"401" keresése a hozzáférési hiba felismeréséhez) — az ilyen
    sort a `nyers-hiba-szándékos` megjegyzés jelöli.
    """
    import re
    root = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui")
    if not root.exists():
        pytest.skip("nincs kliens a fában")
    assert (root / "error_text.dart").exists(), "hiányzik a fordító modul"

    offenders = []
    for path in sorted(root.rglob("*.dart")):
        if path.name == "error_text.dart":
            continue  # maga a fordító — ott a nyers szöveg a bemenet
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(),
                                 1):
            if not re.search(r"\$e\b|\$\{e\}", line):
                continue
            if "nyers-hiba-szándékos" in line:
                continue
            offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert not offenders, (
        "nyers kivétel-szöveg a felületen — tedd `humanError(e)`-be, vagy "
        "ha tényleg logikához kell, jelöld a `nyers-hiba-szándékos` "
        f"megjegyzéssel: {offenders}")

def test_kliens_statuszkod_nem_puszta_szam():
    """A státuszkód-mintákat ne puszta számként keressük.

    A "404" előfordulhat fájlnévben (`match_404.mp4`), azonosítóban,
    időbélyegben vagy egy kiadás nevében is. Egy ilyen véletlen találat
    ROSSZABB, mint a nyers üzenet: magabiztosan mond valótlant ("A kért
    elem nincs meg"). Ezért minden státusz-kulcshoz kontextus tartozik
    ("http 404", "404 not found", "status 404").

    A frissítés-ellenőrzés ugyanezekből a listákból dolgozik
    (`looksLikeAccessIssue`), hogy a két hely ne tudjon széttartani.
    """
    import re
    ui = (Path(__file__).resolve().parent.parent.parent
          / "client" / "lib" / "ui")
    if not ui.exists():
        pytest.skip("nincs kliens a fában")
    src = (ui / "error_text.dart").read_text(encoding="utf-8")

    keys = []
    for name in ("kNotFoundKeys", "kForbiddenKeys"):
        m = re.search(r"const List<String> %s = \[(.*?)\];" % name,
                      src, flags=re.S)
        assert m, name
        keys += re.findall(r'"([^"]+)"', m.group(1))
    assert keys, "üres státusz-lista"
    bare = [k for k in keys if re.fullmatch(r"\d{3}", k.strip())]
    assert not bare, (
        f"puszta számként keresett státuszkód (kontextus kell): {bare}")

    dash = (ui / "dashboard_screen.dart").read_text(encoding="utf-8")
    assert "looksLikeAccessIssue(e)" in dash
    assert 'contains("404")' not in dash, (
        "a frissítés-ellenőrzés saját kezűleg illeszt — használja a "
        "közös `looksLikeAccessIssue`-t")

def test_kliens_varakozas_felirattal():
    """Egy egész képernyőt kitöltő pörgettyű ne álljon felirat nélkül.

    A felderítő jelentés több meccsen PERCEKIG fut. Néma pörgettyűnél a
    felhasználó nem tudja eldönteni, dolgozik-e a program vagy megakadt
    — mégegyszer megnyomja, vagy kilép. A `WaitingView` (ui/waiting.dart)
    kiírja, mire várunk, meddig szokott tartani, és mennyi ideje fut.
    """
    import re
    root = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui")
    if not root.exists():
        pytest.skip("nincs kliens a fában")
    assert (root / "waiting.dart").exists(), "hiányzik a várakozó nézet"

    offenders = []
    for path in sorted(root.rglob("*.dart")):
        src = path.read_text(encoding="utf-8")
        # A `Center(child: CircularProgressIndicator())` a néma változat:
        # nincs mellette semmilyen szöveg. A gombokba tett kis pörgettyű
        # (SizedBox + felirattal járó gomb) rendben van.
        for m in re.finditer(
                r"Center\(\s*child:\s*CircularProgressIndicator\(\s*\)\s*\)",
                src, flags=re.S):
            offenders.append(f"{path.name}:{src[:m.start()].count(chr(10)) + 1}")
    assert not offenders, (
        "felirat nélküli teljes képernyős pörgettyű — használd a "
        f"`WaitingView`-t (mire várunk, meddig tart): {offenders}")

def test_kliens_frissites_megmondja_mi_valtozik():
    """A frissítés-ajánló mutassa a kiadás jegyzetét.

    Egy frissítés 200-300 MB letöltés ÉS újraindítás. Ha az ajánló csak
    egy verziószámot mutat, a felhasználó vakon dönt — vagy inkább nem
    frissít. A jegyzet a GitHub-kiadás leírásából jön.
    """
    root = (Path(__file__).resolve().parent.parent.parent / "client" / "lib")
    if not root.exists():
        pytest.skip("nincs kliens a fában")
    svc = (root / "services" / "update_service.dart").read_text("utf-8")
    assert "final String notes;" in svc, "az UpdateInfo-ból hiányzik a jegyzet"
    assert 'body["body"]' in svc, "a jegyzetet a kiadás leírásából kell venni"

    dash = (root / "ui" / "dashboard_screen.dart").read_text("utf-8")
    assert "info.notes" in dash, "az ajánló nem használja a jegyzetet"
    assert "Mi változik?" in dash, "nincs mód megnézni, mi változik"

def test_kliens_jegyzet_nem_nyers_markdown():
    """A frissítés-jegyzet ne nyers markdownként jelenjen meg.

    A jegyzet a CHANGELOG-ból jön, tehát `**félkövér**`, `> idézet`,
    `## cím`, `- felsorolás`. Egy Flutter `Text` ezeket NYERSEN
    rajzolja ki: a felhasználó csillagokat és kettőskereszteket olvas
    éppen abban az ablakban, amit azért nyitott meg, hogy megértse, mi
    változik.
    """
    root = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui")
    if not root.exists():
        pytest.skip("nincs kliens a fában")
    assert (root / "notes_text.dart").exists(), "hiányzik a formázó"

    dash = (root / "dashboard_screen.dart").read_text(encoding="utf-8")
    assert "plainMarkdown(info.notes)" in dash, (
        "a jegyzet formázatlanul kerül a felületre")
    assert 'import "notes_text.dart";' in dash

def test_kliens_ures_panel_megszolal():
    """Panel ne váljon némán üres dobozzá.

    A néma üres panel ugyanaz a hiba, mint a néma pörgettyű: a
    felhasználó nem tudja eldönteni, hogy a program romlott el, vagy
    tényleg nincs adat. A `SizedBox()` mint ág-érték pont ezt csinálja
    ("ha nincs adat, rajzolj a semmit") — helyette `EmptyState` kell,
    ami megmondja, MIÉRT üres.

    A `SizedBox()` más szerepben rendben van (pl. `underline:` egy
    lenyílónál, üres táblázat-cella), ezért csak a feltételes ágakat
    tiltjuk. A kettőt a kettőspont előtti szóköz különbözteti meg: a
    nevesített argumentumnál a kettőspont a névhez TAPAD
    (`underline:`), a feltételes ág kettőspontja előtt szóköz van.
    """
    import re
    root = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui")
    if not root.exists():
        pytest.skip("nincs kliens a fában")
    assert (root / "empty_state.dart").exists(), "hiányzik az üres-állapot"

    branch = re.compile(r"(?:\?|\s:)\s*const SizedBox\(\s*\)")
    offenders = []
    for path in sorted(root.rglob("*.dart")):
        src = path.read_text(encoding="utf-8")
        for m in branch.finditer(src):
            offenders.append(f"{path.name}:{src[:m.start()].count(chr(10)) + 1}")
    assert not offenders, (
        "néma üres doboz feltételes ágban — használd az `EmptyState`-et "
        f"(mi hiányzik, miért): {offenders}")

def test_kliens_szekcio_ugras_celba_er():
    """A felderítő jelentés ugró-csipjei létező szekcióra mutatnak.

    A sáv címkéi és a kártyák `_sectionKey(...)` hívásai KÜLÖN helyen
    állnak; egy elgépelés néma hibát adna (a csip nem csinál semmit,
    mert nincs ilyen kulcs). Ezért itt párosítjuk őket.
    """
    import re
    path = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not path.exists():
        pytest.skip("nincs kliens a fában")
    src = path.read_text(encoding="utf-8")

    bar = re.search(r"final jumps = <\(String, IconData\)>\[(.*?)\n    \];",
                    src, flags=re.S)
    assert bar, "nem találom az ugró-sáv listáját"
    labels = re.findall(r'\("([^"]+)",\s*Icons\.', bar.group(1))
    keys = set(re.findall(r'_sectionKey\("([^"]+)"\)', src))

    assert len(labels) >= 8, labels
    assert len(set(labels)) == len(labels), f"ismétlődő címke: {labels}"
    missing = [lab for lab in labels if lab not in keys]
    assert not missing, (
        f"ezek a csipek nem találnak szekciót (nincs _sectionKey): {missing}")
    unused = sorted(keys - set(labels))
    assert not unused, (
        f"ezekre a szekciókra egyetlen csip sem mutat: {unused}")

def test_kliens_mutato_csempe_birja_a_mondatot():
    """A mutató-csempe mondat-hosszú értékre is olvasható marad.

    A csempék értéke NEM szám: a mutató-helyerek visszatérési szövegei
    túlnyomórészt egész mondatok ("62% elöl · területi nyomás"). Ha a
    csempe ezt szám-méretű betűvel, keskeny dobozban rajzolja, öt sorba
    törik és a fal olvashatatlan lesz. A védelem: sor-korlát,
    elvágás, és súgóbuborék a teljes szöveggel.
    """
    import re
    path = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not path.exists():
        pytest.skip("nincs kliens a fában")
    src = path.read_text(encoding="utf-8")

    # A szignatúra kaphat további NEVESÍTETT paramétert (pl. a keresés
    # kiemeléséhez) — a csempe belsejére vonatkozó elvárás ettől nem
    # változik, ezért a minta a záró zárójelig szabadon illeszkedik.
    m = re.search(r"Widget _metricTile\(String label, String value[^)]*\) \{"
                  r"(.*?)\n  \}", src, flags=re.S)
    assert m, "nem találom a _metricTile-t"
    body = m.group(1)
    for needed, why in [
        ("maxLines:", "sor-korlát nélkül a mondat szétnyomja a csempét"),
        ("TextOverflow.ellipsis", "a levágott szöveget jelölni kell"),
        ("Tooltip(", "a teljes szövegnek elérhetőnek kell maradnia"),
    ]:
        assert needed in body, f"hiányzik a `{needed}` — {why}"

    # A mutató-helyerek tényleg mondatot adnak: ezt itt is rögzítjük,
    # hogy a csempe soha ne váljon vissza "csak szám" feltevésűvé.
    values = re.findall(r'return\s+("(?:[^"\\]|\\.)*"'
                        r'(?:\s*\n?\s*"(?:[^"\\]|\\.)*")*)\s*;', src)
    texts = ["".join(re.findall(r'"((?:[^"\\]|\\.)*)"', v)) for v in values]
    long_ = [t for t in texts if len(re.sub(r"\$\{[^}]*\}", "0000", t)) > 12]
    assert len(long_) > 100, (
        "a mutató-szövegek túlnyomó része mondat — ha ez megváltozott, "
        f"a csempe méretezését is gondold újra ({len(long_)} hosszú)")


def test_kliens_varazslo_lepesei_megmondjak_mi_hianyzik():
    """A varázsló "Tovább" gombja mellett mindig van magyarázat.

    A gomb letiltva marad, amíg a lépés nincs kész (pl. nincs kiválasztva
    videó). Magyarázat nélkül ez néma zsákutca: a felhasználó egy szürke
    gombot néz, és nem tudja, mit kellene tennie. A `_stepNav` ezért
    `hint`-et kap minden hívásnál — vagy azt mondja meg, mi hiányzik,
    vagy azt, mivel jár, ha kihagyja a lépést.
    """
    path = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "upload_screen.dart")
    if not path.exists():
        pytest.skip("nincs kliens a fában")
    src = path.read_text(encoding="utf-8")

    # A definíciót kihagyjuk — csak a HÍVÁSOKAT nézzük.
    calls = [m for m in re.finditer(r"_stepNav\(", src)
             if "Widget _stepNav(" not in src[max(0, m.start() - 20):m.end()]]
    assert len(calls) >= 3, f"a varázsló-lépések olvasása elromlott: {calls}"
    missing = []
    for m in calls:
        # A hívás a kiegyensúlyozott zárójelig tart.
        depth, i = 0, m.end() - 1
        while i < len(src):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = src[m.end():i]
        if "hint:" not in body:
            missing.append(src[:m.start()].count(chr(10)) + 1)
    assert not missing, (
        "varázsló-lépés magyarázat nélkül — a letiltott 'Tovább' így néma "
        f"zsákutca (sorok): {missing}")


def test_minden_posztonkenti_mezo_a_kliensben_is():
    """ŐR: minden *_by_role ScoutingReport-mezőt olvasson a kliens
    felderítő-képernyője is — a réteg-recept 6. lépése (csempe) ne
    maradhasson ki csendben."""
    import dataclasses
    from pathlib import Path

    import pytest

    from handball.pipeline import scouting

    dart = (Path(__file__).resolve().parents[2] / "client" / "lib"
            / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    src = dart.read_text(encoding="utf-8")
    fields = [f.name for f in dataclasses.fields(scouting.ScoutingReport)
              if f.name.endswith("_by_role")]
    assert len(fields) >= 60, fields   # az olvasás elromlott
    arva = [f for f in fields if f'"{f}"' not in src]
    assert not arva, f"kliens-csempe nélküli posztonkénti mezők: {arva}"


def _client_lib() -> "Path":
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "client" / "lib"


def test_fiok_kapu_a_dashboard_ele_kerul():
    """ŐR: a motor elindulása után a FIÓK-KAPU jön, nem egyből a
    dashboard — különben a feltétel-elfogadás megkerülhető lenne."""
    import pytest

    boot = _client_lib() / "ui" / "bootstrap_screen.dart"
    if not boot.exists():
        pytest.skip("nincs kliens a fában")
    src = boot.read_text(encoding="utf-8")
    assert "AccountGate(" in src, "a bootstrap nem a fiók-kapuba lép be"
    assert "DashboardScreen()" not in src, (
        "a bootstrap megkerüli a fiók-kaput, és egyből a dashboardra lép")


def test_fiok_letrehozas_csak_elfogadassal():
    """ŐR: a "Fiók létrehozása" gomb csak a feltételek elfogadásával
    aktív, és a kérésbe is bekerül az elfogadás."""
    import pytest

    scr = _client_lib() / "ui" / "account_screen.dart"
    if not scr.exists():
        pytest.skip("nincs kliens a fában")
    src = scr.read_text(encoding="utf-8")
    assert "(!_registerMode || _acceptTerms)" in src, (
        "a létrehozó gomb elfogadás nélkül is aktív lehet")
    assert "acceptTerms: _acceptTerms" in src, (
        "az elfogadás nem megy át a szervernek")


def test_a_feltetel_szoveg_a_motortol_jon():
    """ŐR: a teljes jogi szöveget a motor adja (GET /legal/terms) — a
    kliensben nincs második, elsodródó másolat."""
    import pytest

    ui = _client_lib() / "ui"
    if not ui.exists():
        pytest.skip("nincs kliens a fában")
    terms = (ui / "terms_screen.dart").read_text(encoding="utf-8")
    assert "fetchTerms()" in terms, "a képernyő nem a motortól kéri a szöveget"
    # A demó (motor nélküli) mód RÖVID tudomásulvétele a kivétel — az is
    # csak egy helyen, a kapuban él, és jelzi, hogy a teljes szöveg a
    # motorral jön.
    gate = (ui / "account_gate.dart").read_text(encoding="utf-8")
    assert gate.count("kOfflineTermsSummary") == 2, (
        "a demó-szöveg nem egy helyen van definiálva és felhasználva")
    assert "szellemi tulajdona" in gate and "fizikai tulajdon" in gate


def test_jelszocsere_elerheto_a_kliensbol():
    """ŐR: a jelszócsere-végpontnak van FELÜLETE is — a fiók-menüből
    nyílik, és a kliens-hívás (changePassword) be van kötve. Backend-
    képesség kliens nélkül = nem létező képesség a felhasználónak."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "changePassword(" in shell, (
        "a jelszócsere API-hívás nincs bekötve a felületről")
    assert "Jelszócsere" in shell, "nincs Jelszócsere menüpont"


def test_elfelejtett_jelszo_utmutato_a_belepon():
    """ŐR: sikertelen belépésnél a képernyő elmondja az elfelejtett
    jelszó őszinte útját (nincs e-mailes visszaállítás — új fiók, a
    meccsek megmaradnak), ne csak a telepítési útmutató tudja."""
    import pytest

    scr = _client_lib() / "ui" / "account_screen.dart"
    if not scr.exists():
        pytest.skip("nincs kliens a fában")
    src = scr.read_text(encoding="utf-8")
    assert "Elfelejtetted a jelszavad?" in src
    assert "megmaradnak" in src


def test_motor_ujraelesztes_ujra_is_indit():
    """ŐR: hálózati hibánál a kliens nem csak KERESI a motort (portok),
    hanem ÚJRA IS INDÍTJA (reviveEngine → BackendLauncher.ensureRunning)
    — a motor-folyamat el is halhat (frissítés, altatás), olyankor a
    port-keresés kevés, és a felhasználót csak a program teljes
    újraindítása mentené meg."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    api = (lib / "services" / "api_client.dart").read_text(encoding="utf-8")
    assert "reviveEngine" in api, "nincs mély öngyógyítás (reviveEngine)"
    assert "ensureRunning" in api, (
        "a revive nem indítja újra a motort, csak portot keres")
    # Mindkét fiók-felület a MÉLY öngyógyítást hívja, nem a puszta
    # port-keresést.
    gate = (lib / "ui" / "account_gate.dart").read_text(encoding="utf-8")
    scr = (lib / "ui" / "account_screen.dart").read_text(encoding="utf-8")
    assert "ApiClient.reviveEngine()" in gate
    assert "ApiClient.reviveEngine()" in scr
    assert "rediscoverEngine()" not in gate
    assert "rediscoverEngine()" not in scr


def test_hibajelentes_lathato_verzioval():
    """ŐR: a fiók-képernyő és a motor-hiba képernyő kiírja a futó kiadás
    számát — egy hibajelentő képernyőképből így azonnal látszik, MELYIK
    verzió adta a hibát (enélkül a támogatás találgat)."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    scr = (lib / "ui" / "account_screen.dart").read_text(encoding="utf-8")
    gate = (lib / "ui" / "account_gate.dart").read_text(encoding="utf-8")
    assert "appVersion" in scr, "a fiók-képernyőn nincs verziószám"
    assert "appVersion" in gate, "a motor-hiba képernyőn nincs verziószám"


def test_motor_hiba_kepernyo_mutatja_a_naplot():
    """ŐR: a motor-hiba képernyő a motor-napló utolsó sorait is
    megmutatja — a kiváltó ok így egyetlen hibajelentő képernyőképen
    elfér, a felhasználónak nem kell fájlok közt keresgélnie."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    launcher = (lib / "services" / "backend_launcher.dart").read_text(
        encoding="utf-8")
    gate = (lib / "ui" / "account_gate.dart").read_text(encoding="utf-8")
    assert "logTail" in launcher, "nincs napló-farok olvasó a motor-indítóban"
    assert "logTail" in gate, "a hiba-képernyő nem mutatja a naplót"
    assert "SelectableText" in gate, (
        "a napló nem kijelölhető szöveg — másolni sem lehetne")


def test_elveszett_valaszu_regisztracio_belepesbe_fut():
    """ŐR: ha az első regisztráció célba ért, de a válasz elveszett (a
    motor épp elhalt), az ismétlés "már van fiók" hibát ad — a kliens
    ilyenkor BELÉPÉSSEL folytatja ugyanazokkal az adatokkal, nem
    hibaüzenettel ijesztget egy élő fiók mellett."""
    import pytest

    scr = _client_lib() / "ui" / "account_screen.dart"
    if not scr.exists():
        pytest.skip("nincs kliens a fában")
    src = scr.read_text(encoding="utf-8")
    assert "már van fiók" in src, "nincs belépés-tartalék a duplikált fiókra"
    assert src.index("már van fiók") > src.index("reviveEngine"), (
        "a tartalék nem az újraélesztett ismétlés ágában van")


def test_motor_orkutya_ujraindit_es_korlatoz():
    """ŐR: a motor-indítónak van őrkutyája — a magától elhalt motort
    újraindítja (a felhasználó észre sem veszi), de korlátozott számú
    próbával (a hibás motort nem pörgeti örökké), és a SZÁNDÉKOS
    leállítást (kilépés, frissítés előtti fájlcsere) békén hagyja."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    src = (lib / "services" / "backend_launcher.dart").read_text(
        encoding="utf-8")
    assert "_watchdog" in src, "nincs őrkutya a motor-indítóban"
    assert "watchdogMaxRestarts" in src, "az őrkutya korlát nélkül pörgetne"
    assert "_stoppedByUs" in src, (
        "az őrkutya nem különbözteti meg a szándékos leállítást")
    # A szándékos leállítás jelzi magát, az őrkutya pedig tiszteli.
    assert src.index("_stoppedByUs = true") > 0
    assert "if (_stoppedByUs) return;" in src


def test_vendeg_belepes_tudomasulvetellel_es_takaritassal():
    """ŐR: van vendég-belépés (fiók nélkül), de NEM kerüli meg a
    tulajdonjogi tudomásulvételt, és a vendég-munka a következő
    induláskor takarítódik — csak a vendég-belépés UTÁN készült
    meccsek, a korábbiak nem."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    gate = (lib / "ui" / "account_gate.dart").read_text(encoding="utf-8")
    scr = (lib / "ui" / "account_screen.dart").read_text(encoding="utf-8")
    assert "onGuest" in scr, "nincs vendég-belépés gomb a fiók-képernyőn"
    assert "_enterAsGuest" in gate, "a kapu nem ismeri a vendég-utat"
    # A tudomásulvétel nem kerülhető meg: a vendég-út ellenőrzi.
    assert "offlineTermsVersion < kOfflineTermsVersion" in gate, (
        "a vendég-belépés megkerüli a tulajdonjogi tudomásulvételt")
    # A takarítás alapvonal-alapú: csak az újat törli.
    assert "guestBaseline" in gate and "deleteMatch" in gate, (
        "a vendég-takarítás hiányzik vagy nem alapvonal-alapú")


def test_fejlesztoi_mod_vedi_a_vendeg_munkat():
    """ŐR: a fejlesztői mód kapcsolható (fiók-képernyő ÉS fiók-menü), és
    bekapcsolva a vendég-takarítás NEM töröl."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    gate = (lib / "ui" / "account_gate.dart").read_text(encoding="utf-8")
    scr = (lib / "ui" / "account_screen.dart").read_text(encoding="utf-8")
    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    store = (lib / "services" / "session_store.dart").read_text(
        encoding="utf-8")
    assert "setDevMode" in store, "nincs fejlesztői mód a munkamenet-tárban"
    assert "setDevMode" in scr, "a fiók-képernyőről nem kapcsolható"
    assert "setDevMode" in shell, "a fiók-menüből nem kapcsolható"
    # A takarítás tiszteli a fejlesztői módot: előbb kérdez, aztán töröl.
    assert gate.index("SessionStore.devMode") < gate.index("deleteMatch"), (
        "a takarítás nem a fejlesztői mód ellenőrzésével kezdődik")


def test_frissites_a_kapu_elott_is_elerheto():
    """ŐR: a frissítés-keresés a BELÉPŐ képernyőről is elérhető — ha a
    frissítő csak a dashboardon (a fiók-kapu mögött) él, a belépésnél
    elakadt felhasználó régi, hibás verzión ragad, és a javítás sosem
    ér el hozzá."""
    import pytest

    scr = _client_lib() / "ui" / "account_screen.dart"
    if not scr.exists():
        pytest.skip("nincs kliens a fában")
    src = scr.read_text(encoding="utf-8")
    # A folyamat maga a közös update_flow.dart-ba került (a motor-hiba
    # képernyőnek is kell) — az ELVÁRÁS változatlan: a belépő képernyőről
    # keresni ÉS telepíteni is lehessen.
    assert "checkAndInstallUpdate" in src, (
        "a belépő képernyő nem ismeri a frissítőt")
    assert "Frissítés keresése" in src, "nincs frissítés-kereső gomb"
    flow = (_client_lib() / "ui" / "update_flow.dart").read_text(
        encoding="utf-8")
    assert "downloadAndInstall" in flow, (
        "a frissítés-folyamatból csak keresni lehet, telepíteni nem")


def test_vendeg_sav_a_dashboardon():
    """ŐR: vendég-munkamenetben a dashboard sávban jelzi, hogy a munka
    múlandó, és egy kattintással védhetővé tehető (fejlesztői mód) —
    csendben elveszett munka nem lehet."""
    import pytest

    dash = _client_lib() / "ui" / "dashboard_screen.dart"
    if not dash.exists():
        pytest.skip("nincs kliens a fában")
    src = dash.read_text(encoding="utf-8")
    assert "guestMode" in src, "a dashboard nem tud a vendég-munkamenetről"
    assert "törlődik" in src, "a sáv nem mondja ki a múlandóságot"
    assert "setDevMode" in src, "a sávból nem védhető a munka egy kattintással"


def test_belepes_vendegbol_megtartja_a_munkat():
    """ŐR: a vendég a fiók-menüből el tud jutni a belépéshez, a belépési
    szándékú kapu nem takarít, sikeres belépésnél pedig a
    vendég-munkamenet úgy zárul le, hogy a munka MEGMARAD (fiókot
    csinált — magáénak vallotta)."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    gate = (lib / "ui" / "account_gate.dart").read_text(encoding="utf-8")
    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "Belépés / fiók létrehozása" in shell, (
        "a vendég nem jut el a belépéshez a fiók-menüből")
    assert "preserveGuestWork: true" in shell, (
        "a belépési szándékú kapu takarítana")
    assert "preserveGuestWork" in gate
    # Sikeres belépésnél a vendég-jelző lezárul takarítás NÉLKÜL.
    i = gate.index('if (me == null)')
    assert "endGuest" in gate[i:], (
        "belépés után a vendég-munkamenet nem zárul le")


def test_fel_frissult_telepites_lathato():
    """ŐR: a kliens a /health-ből olvassa a motor verzióját, és a
    dashboard kimondja, ha az app és a motor verziója eltér — a
    fél-frissült telepítés ne rejtélyes hibaként jelentkezzen."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    api = (lib / "services" / "api_client.dart").read_text(encoding="utf-8")
    dash = (lib / "ui" / "dashboard_screen.dart").read_text(
        encoding="utf-8")
    assert "engineVersion" in api, "a kliens nem olvassa a motor verzióját"
    assert "engineVersion" in dash and "eltér" in dash, (
        "a dashboard nem jelzi a verzió-eltérést")
    assert "Releases" in dash, "a sáv nem adja meg a megoldást"


def test_palya_szabalykonyvi_elemei_a_rajzolon():
    """ŐR: a felülnézeti pálya a SZABÁLYKÖNYVI elemeket rajzolja — 6 m-es
    kapuelőtér, 9 m-es (szaggatott) szabaddobási vonal, 7 m-es és 4 m-es
    vonal, kapu. Ezek nélkül a kép "sematikus doboz", és az edző nem
    tudja hova tenni a látottakat."""
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    geom = (lib / "ui" / "court_geometry.dart").read_text(encoding="utf-8")
    painter = (lib / "ui" / "court_painter.dart").read_text(encoding="utf-8")
    for name in ("goalAreaRadius", "freeThrowRadius", "sevenMeterX",
                 "keeperLineX"):
        assert name in geom, f"hiányzó pálya-méret: {name}"
    assert "freeThrowBoundary" in geom and "freeThrowBoundary" in painter, (
        "a 9 m-es szabaddobási vonal nincs kirajzolva")
    assert "sevenMeterX" in painter, "a hetes-vonal nincs kirajzolva"
    assert "keeperLineX" in painter, "a 4 m-es kapus-vonal nincs kirajzolva"


def test_hotérkep_nem_cellankent_elmosott():
    """ŐR (teljesítmény): a hőtérkép 200 cellája NEM cellánkénti
    elmosással (MaskFilter.blur) lágyul, hanem sugaras színátmenettel —
    a cellánkénti elmosás külön rajz-réteget kényszerítene ki, és
    gyengébb gépen akadozna a kép."""
    import pytest

    hp = _client_lib() / "ui" / "heatmap_painter.dart"
    if not hp.exists():
        pytest.skip("nincs kliens a fában")
    src = hp.read_text(encoding="utf-8")
    assert "RadialGradient" in src, "a lágy hőfolt nem gradienssel készül"
    assert "maskFilter" not in src, (
        "cellánkénti elmosás a hőtérképen — ez akadozó rajzolást okoz")


def test_a_felhasznaloi_szoveg_nem_beszel_fejlesztoi_nyelven():
    """ŐR (nyelv): a felhasználónak MOTORT mondunk, nem "backendet" és
    végképp nem "uvicornt".

    A motor-elérhetetlenség a leggyakoribb élő hiba; a képernyő eddig
    azt mondta rá, hogy "indítsd el a lokális szervert (uvicorn)". Ez
    egy edzőnek, aki asztali alkalmazást telepített, nem utasítás,
    hanem zsargon. A kódban a "backend" szó maradhat (fájlnév, import,
    komment) — a MEGJELENÍTETT szövegekben nem.
    """
    import re

    import pytest

    ui = _client_lib() / "ui"
    if not ui.exists():
        pytest.skip("nincs kliens a fában")

    # Csak a magyar mondatokat nézzük: legalább 12 karakter és van
    # benne szóköz — az import-utak és az azonosítók így kiesnek.
    rossz = []
    for f in sorted(ui.glob("*.dart")):
        src = f.read_text(encoding="utf-8")
        for line in src.splitlines():
            if line.lstrip().startswith("//"):
                continue  # komment: ott szabad
            for lit in re.findall(r'"([^"\\]{12,})"', line):
                if " " not in lit:
                    continue
                low = lit.lower()
                if "uvicorn" in low or "backend" in low:
                    rossz.append(f"{f.name}: {lit}")
    assert not rossz, (
        "fejlesztői zsargon a felhasználói szövegben: " + "; ".join(rossz))


def test_a_kepkockankent_ujrarajzolt_feluletek_nem_elmosnak():
    """ŐR (teljesítmény): a LEJÁTSZÁS ALATT minden képkockán újrarajzolt
    felületeken nincs MaskFilter.blur.

    A hőtérkép-őr a statikus rajzot védi; ez a kettő ennél rosszabb eset:
    a felülnézeti pálya és a meccs-sztori sávja a lejátszófej minden
    lépésénél újrarajzolódik. Tizennégy játékos árnyéka, illetve
    gólonként egy-egy elmosott pötty képkockánként tucatnyi külön
    rajz-menetet jelentene — a lágyságot ezért sugaras/lineáris
    színátmenet adja.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    # A pálya és a sztori-sáv a lejátszófejjel, a két grafikon pedig a
    # betöltő berajzolás-animáció alatt rajzolódik újra képkockánként.
    for name in ("court_painter.dart", "story_timeline.dart",
                 "score_chart.dart", "shot_map_painter.dart"):
        src = (lib / "ui" / name).read_text(encoding="utf-8")
        assert "maskFilter" not in src, (
            f"{name}: elmosás a képkockánként újrarajzolt felületen")
        assert "_softGlow" in src, (
            f"{name}: nincs meg az elmosás-mentes ragyogás-segéd")


def test_az_animaciok_tiszteletben_tartjak_a_csokkentett_mozgast():
    """ŐR (hozzáférhetőség): a közös animációs elemek megnézik, kért-e
    a felhasználó CSÖKKENTETT MOZGÁST.

    Az app tele van úszó, pörgő és növekvő elemekkel. Akinél a
    rendszerben be van kapcsolva a mozgás-csökkentés, annál ez nem
    díszítés, hanem rosszullét — és mivel a kapcsoló egy helyről
    kiszolgálható, elemenként elfelejteni is egy helyen lehet.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    anim = (lib / "ui" / "anim.dart").read_text(encoding="utf-8")
    assert "disableAnimations" in anim, (
        "az anim.dart nem kérdezi le a rendszer mozgás-beállítását")
    assert "bool reduceMotion(" in anim, "nincs közös reduceMotion segéd"
    # A négy közös elem mindegyikének hivatkoznia kell rá.
    for elem in ("FadeSlideIn", "CountUp", "HoverLift", "AnimatedBar"):
        assert elem in anim, f"hiányzó animációs elem: {elem}"
    assert anim.count("reduceMotion(context)") >= 4, (
        "nem mindegyik közös animációs elem nézi a mozgás-csökkentést")

    # A betöltő berajzolás-animációk (grafikonok) és a FOLYAMATOS,
    # sosem álló mozgások (forgó lépés-ikon, lélegző pörgettyű) is
    # nézzék — a végtelen mozgás a legrosszabb fajta.
    for name in ("score_chart.dart", "intensity_chart.dart",
                 "trend_screen.dart", "match_screen.dart",
                 "upload_screen.dart", "waiting.dart"):
        src = (lib / "ui" / name).read_text(encoding="utf-8")
        assert "reduceMotion(context)" in src, (
            f"{name}: a berajzolás-animáció nem nézi a mozgás-csökkentést")


def test_a_frissito_motor_es_fiok_nelkul_is_elerheto():
    """ŐR: a frissítés-gomb ott van MINDEN olyan képernyőn, ahol a
    felhasználó a motor hiánya miatt elakadhat.

    Ez a termék legsúlyosabb zárt köre volt: régi verzió → a motor el
    sem indul → a fiók-kapu a MOTOR-HIBA képernyőn áll meg → onnan nem
    vezetett út a frissítőhöz (az a fiók-képernyőn ült, ami a motor
    nélkül el sem érhető) → a felhasználó SOHA nem jut olyan verzióra,
    amelyikben a hiba javítva van. Csak kézi újratelepítéssel lehetett
    kiszabadulni.

    A frissítéshez se fiók, se motor nem kell (a kiadásokat a GitHub
    adja), ezért mindhárom elakadási ponton ott kell lennie.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    flow = lib / "ui" / "update_flow.dart"
    assert flow.exists(), "nincs közös frissítés-folyamat (update_flow.dart)"
    assert "checkAndInstallUpdate" in flow.read_text(encoding="utf-8")

    for name in ("account_gate.dart",      # motor-hiba képernyő
                 "bootstrap_screen.dart",  # a motor el sem indult
                 "account_screen.dart"):   # a kapu (fiók nélkül)
        src = (lib / "ui" / name).read_text(encoding="utf-8")
        assert "checkAndInstallUpdate" in src, (
            f"{name}: innen nem érhető el a frissítő — a régi verzión "
            "ragadt felhasználó nem tud kiszabadulni")


def test_a_diagnosztika_minden_elakadasi_ponton_ott_van():
    """ŐR: a "Diagnosztika másolása" gomb ott van minden képernyőn, ahol
    a motor hiánya megállítja a felhasználót.

    A naplófájl önmagában kevés: ha a motor-program meg sem található,
    vagy az adatmappa nem írható, akkor NAPLÓ SINCS — a felhasználó
    pedig csak annyit tud mondani, hogy "nem megy". A jelentésnek ezért
    a hiányzó FELTÉTELEKET is ki kell mondania.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    launcher = (lib / "services" / "backend_launcher.dart").read_text(
        encoding="utf-8")
    assert "static Future<String> diagnostics(" in launcher, (
        "nincs diagnosztika-jelentés a motor-indítóban")
    for kell in ("engineCandidates",   # hol kerestük a motort
                 "adatmappa",          # írható-e
                 "portok",             # válaszol-e bármelyik
                 "logTail"):           # a napló vége
        assert kell in launcher, f"a diagnosztikából hiányzik: {kell}"

    for name in ("account_gate.dart",       # motor-hiba képernyő
                 "bootstrap_screen.dart",   # a motor el sem indult
                 "dashboard_screen.dart"):  # a motor menet közben halt el
        src = (lib / "ui" / name).read_text(encoding="utf-8")
        assert "DiagnosticsButton" in src, (
            f"{name}: innen nem lehet diagnosztikát másolni")


def test_a_motor_naplo_utf8_kent_olvasodik():
    """ŐR: a motor kimenetét UTF-8-ként dekódoljuk.

    A motor MAGYARUL naplóz. A String.fromCharCodes bájtonként képez
    karaktert, tehát az ékezeteket összetöri ("Ã¡") — pont azt a naplót,
    amit a felhasználótól hibakereséshez kérünk.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    src = (lib / "services" / "backend_launcher.dart").read_text(
        encoding="utf-8")
    assert "utf8.decode" in src, "a motor-napló nem UTF-8-ként olvasódik"
    # Csak a VÉGREHAJTOTT sorok számítanak: a kommentben magyarázatként
    # szerepelhet a régi, hibás hívás neve.
    kod = [ln for ln in src.splitlines()
           if not ln.lstrip().startswith("//")]
    assert not any("String.fromCharCodes" in ln for ln in kod), (
        "bájtonkénti dekódolás a motor kimenetén — összetöri az ékezeteket")


def test_a_lejart_var_ido_nem_oli_meg_az_indulo_motort():
    """ŐR: az indulási időtúllépés NEM állíthatja le a még élő motrot.

    A becsomagolt motor negyedmilliárd bájt, és a víruskereső az első
    futásnál végigolvassa. Ha ilyenkor a lejárt idő kilövi a
    folyamatot, a felhasználó újrapróbál — és az átvizsgálás elölről
    kezdődik: a hiba önmagát tartja életben. A még élő folyamatot ezért
    futni kell hagyni; a port-tartomány végigfésülése úgyis megtalálja,
    amint válaszol.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    src = (lib / "services" / "backend_launcher.dart").read_text(
        encoding="utf-8")

    # A várakozó ág (az ensureRunning vége) a health-várakozástól a
    # visszatérésig: ebben nem lehet stop() hívás.
    start = src.index("final ok = await _waitForHealth(")
    end = src.index("return BackendStatus(BackendPhase.failed, why);", start)
    ag = [ln for ln in src[start:end].splitlines()
          if not ln.lstrip().startswith("//")]
    assert not any("stop();" in ln for ln in ag), (
        "az időtúllépés leállítja a még induló motrot — a felhasználó "
        "újrapróbálásakor az egész átvizsgálás elölről kezdődik")

    # És legyen bőven idő az első, átvizsgált indulásra.
    m = re.search(r"_waitForHealth\(const Duration\(seconds: (\d+)\)", src)
    assert m, "nem találom az indulási várakozás hosszát"
    assert int(m.group(1)) >= 150, (
        "túl rövid indulási várakozás — az első futás víruskereső-"
        f"átvizsgálással ennél tovább tart ({m.group(1)} mp)")


def test_a_motor_sajat_naploja_is_latszik():
    """ŐR: a hiba-képernyők a motor SAJÁT naplóját is megmutatják.

    A becsomagolt motor ablak nélküli programként fut (console=False a
    PyInstaller-recepetben). Windowson ilyenkor a Pythonnak nincs
    stdout/stderr-je, tehát a kliens csövébe SEMMI nem érkezik — a motor
    a saját üzeneteit egy KÜLÖN fájlba írja (engine.log), az indító
    naplója (engine-app.log) mellé. Ha a kliens csak a sajátját olvassa,
    a felhasználó pont a MIÉRT-et nem látja: csak azt, hogy
    "elindítottam" és "leállt".
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    src = (lib / "services" / "backend_launcher.dart").read_text(
        encoding="utf-8")
    assert "engine.log" in src, (
        "a kliens nem olvassa a motor saját naplóját (engine.log)")
    # És tényleg a logTail fűzze össze — ne csak valahol szerepeljen.
    start = src.index("static Future<String?> logTail(")
    end = src.index("\n  }", start)
    torzs = src[start:end]
    assert "_engineOwnLogFile" in torzs and "_logFile" in torzs, (
        "a logTail nem fűzi össze a motor és az indító naplóját")


def test_a_szerver_magyarazata_eljut_a_felhasznaloig():
    """ŐR: a kliens a szerver EMBERI hibaüzenetét mutassa, ne a kódot.

    A motor sok hibára pontos, magyar mondatot ad — például hogy a videó
    útvonalában ékezet van, és mit tegyen a felhasználó. Ez a kliensben
    elveszett: minden hiba "HTTP 400" alakban csapódott le, tehát a
    legjobb magyarázatunk sosem jutott el odáig, ahol elolvassák.
    """
    import re

    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")
    src = (lib / "services" / "api_client.dart").read_text(encoding="utf-8")

    assert "static String serverDetail(" in src, (
        "nincs segéd a szerver magyarázatának kibontására")
    # Csupasz státuszkód-dobás nem maradhat: minden hibaüzenetnek a
    # közös segéden kell átmennie.
    csupasz = re.findall(
        r'throw Exception\(\s*"[^"]*HTTP \$\{(?:resp|r)\.statusCode\}',
        src)
    assert not csupasz, (
        f"{len(csupasz)} helyen csak a státuszkódot dobjuk — a szerver "
        "magyarázata elveszik")


def test_a_futo_feldolgozasok_barhonnan_visszatalalhatok():
    """ŐR: van külön Feldolgozások képernyő, és a menü ÉLŐ jelvénnyel
    mutatja, hány elemzés fut.

    Egy meccs feldolgozása percekig fut. A haladás korábban csak a
    kezdőlapon látszott, és csak amíg a felhasználó ott állt: aki közben
    átment a felderítésre vagy a figura-tervezőbe, elvesztette szem elől
    — és nem volt hová visszamennie.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "NavId.jobs" in shell, "nincs Feldolgozások menüpont"
    assert "Feldolgozások" in shell, "a menüpontnak nincs neve"
    assert "_JobsBadge" in shell, (
        "a menüpont nem mutat élő darabszámot — a futó munka nem "
        "látszik más képernyőkről")

    assert (lib / "ui" / "jobs_screen.dart").exists(), (
        "nincs Feldolgozások képernyő")

    # A figyelő KÖZÖS: egyetlen kérdezgető járjon, ne képernyőnként külön.
    monitor = (lib / "services" / "jobs_monitor.dart").read_text(
        encoding="utf-8")
    assert "static final JobsMonitor instance" in monitor, (
        "a feldolgozás-figyelő nem közös példány")
    for name in ("jobs_screen.dart", "dashboard_screen.dart"):
        src = (lib / "ui" / name).read_text(encoding="utf-8")
        assert "JobsMonitor" in src, f"{name}: nem a közös figyelőt használja"


def test_az_alvas_gatlas_a_feldolgozas_ideje_alatt_el():
    """ŐR: a motor alvás-gátló zárat fog a feldolgozás idejére, és
    MINDIG feloldja.

    A feldolgozás percekig-órákig tart, és közben a felhasználó nem a
    képernyőt nézi. Zár nélkül a rendszer tétlenségi alvásra vált, és a
    számítás megáll. Feloldás nélkül viszont a gép a munka után is ébren
    maradna, és enné az akkumulátort.
    """
    from pathlib import Path

    app = (Path(__file__).resolve().parent.parent
           / "handball" / "api" / "app.py").read_text(encoding="utf-8")
    fo = app.index("def _run_job(")
    veg = app.index("_log_job(job)", fo)
    torzs = app[fo:veg]
    assert "KeepAwake" in torzs, (
        "a feldolgozás nem fog alvás-gátló zárat")
    assert "finally:" in torzs and "_awake.stop()" in torzs, (
        "a zár nem oldódik fel minden ágon — a gép a munka után is "
        "ébren maradna")


# ---- Küszöb-egyezés: a kliens kézzel másolt számai és a motor --------------

# Kivételek: olyan helper-blokkok, ahol a hivatkozott konstans SZÁMA
# szándékosan nem jelenik meg a Dart-törzsben. Mindegyikhez tartozik
# indoklás — kivételt csak ezzel együtt szabad felvenni.
_KUSZOB_KIVETELEK = {
    # A figura-szűrést MÁR A MOTOR elvégzi: a spf_telegraphed /
    # spo_telegraphed csak a részarány-küszöböt elért figurákat
    # számolja, a kliensnek nincs mit újra ellenőriznie.
    ("_setplayFinisher", "SPF_SHARE_PCT"),
    ("_setplayOpener", "SPO_SHARE_PCT"),
}


def _motor_konstansok():
    """A pipeline modul-szintű NAGYBETŰS szám-konstansai.

    Egy név TÖBB modulban is előfordulhat eltérő értékkel (pl. a
    PSR_SHARE_PCT a rules.py-ban 20.0, a decisions.py-ban 60.0), ezért
    névhez az ÖSSZES előforduló értéket gyűjtjük — a kliens bármelyiket
    tükrözheti. Az `X = Y` alakú aliasokat feloldjuk.
    """
    import ast
    import re as _re

    ertekek: dict[str, set] = {}
    aliasok: list[tuple[str, str]] = []
    pipeline = Path(__file__).resolve().parent.parent / "handball" / "pipeline"
    for py in sorted(pipeline.glob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for t in node.targets:
                if not isinstance(t, ast.Name):
                    continue
                if not _re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", t.id):
                    continue
                try:
                    val = ast.literal_eval(node.value)
                except Exception:
                    if isinstance(node.value, ast.Name):
                        aliasok.append((t.id, node.value.id))
                    continue
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    continue
                ertekek.setdefault(t.id, set()).add(float(val))
    for _ in range(3):          # láncolt aliasok feloldása
        for nev, cel in aliasok:
            if cel in ertekek:
                ertekek.setdefault(nev, set()).update(ertekek[cel])
    return ertekek


def _dart_helper_blokkok(dart_szoveg: str):
    """(helper-név, komment-blokk, törzs) hármasok a Dart-fájlból."""
    sorok = dart_szoveg.split("\n")
    ki = []
    i = 0
    fej = re.compile(
        r"\s*(?:String\?|Widget|List<[^>]*>\??|Map<[^>]*>\??|double\?|int\?"
        r"|bool)\s+(_\w+)\(")
    while i < len(sorok):
        m = fej.match(sorok[i])
        if not m:
            i += 1
            continue
        j = i - 1
        komment = []
        while j >= 0 and sorok[j].strip().startswith("//"):
            komment.insert(0, sorok[j])
            j -= 1
        melyseg = 0
        torzs = []
        k = i
        while k < len(sorok):
            torzs.append(sorok[k])
            melyseg += sorok[k].count("{") - sorok[k].count("}")
            if melyseg <= 0 and k > i:
                break
            k += 1
        ki.append((m.group(1), "\n".join(komment), "\n".join(torzs)))
        i = k + 1
    return ki


def test_kliens_kuszobok_egyeznek_a_motorral():
    """A kliens-csempék küszöbei KÉZZEL másolt számok a motorból.

    Minden helper kommentje megnevezi, melyik motor-konstansokat
    tükrözi ("a backenddel azonos küszöbök: ATV_MIN_ATTACKS, …") — de
    eddig semmi nem ellenőrizte, hogy a szám tényleg ugyanaz. Egy
    elcsúszás azt jelentené, hogy a csempe olyat állít, amit a motor
    nem mondana ki (vagy hallgat ott, ahol a motor beszél), és ez a
    fajta hiba némán él évekig.

    Az ellenőrzés megengedő az ÁBRÁZOLÁSSAL szemben (a Dart néha törtet
    használ a százalék helyett, vagy kockát a perc helyett), de szigorú
    a NÉVVEL szemben: nem létező konstansra hivatkozni tilos, mert
    akkor a következő olvasó rossz helyen módosít.
    """
    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    konst = _motor_konstansok()
    assert len(konst) > 500, "a konstans-olvasás elromlott"

    blokkok = _dart_helper_blokkok(dart.read_text(encoding="utf-8"))
    assert len(blokkok) > 300, "a helper-olvasás elromlott"

    ismeretlen: list = []
    elteres: list = []
    ellenorzott = 0
    for nev, komment, torzs in blokkok:
        hivatkozott = set(re.findall(r"\b([A-Z][A-Z0-9]{2,}_[A-Z0-9_]+)\b",
                                     komment))
        if not hivatkozott:
            continue
        szamok = {float(x) for x in re.findall(r"\d+(?:\.\d+)?", torzs)}
        for c in sorted(hivatkozott):
            if (nev, c) in _KUSZOB_KIVETELEK:
                continue
            if c not in konst:
                ismeretlen.append(f"{nev}: {c}")
                continue
            varhato = set()
            for v in konst[c]:
                # Ugyanaz a szám; százalék↔tört; perc↔kocka (25 fps).
                varhato.update({v, v / 100.0, v * 100.0, v * 60.0 * 25.0})
            if not any(any(abs(w - s) < 1e-6 for s in szamok)
                       for w in varhato):
                elteres.append(f"{nev}: {c}={sorted(konst[c])} "
                               f"nincs a törzs számai közt")
            ellenorzott += 1

    assert not ismeretlen, (
        "a kliens NEM LÉTEZŐ motor-konstansra hivatkozik (a következő "
        "olvasó rossz helyen módosítana): " + "; ".join(ismeretlen))
    assert not elteres, (
        "a kliens küszöbe eltér a motorétól — a csempe mást állítana, "
        "mint a motor: " + "; ".join(elteres))
    assert ellenorzott > 300, (
        f"csak {ellenorzott} küszöböt ellenőriztünk — az olvasás elromlott")


def test_a_tobbi_kliens_kepernyo_kuszobei_is_egyeznek():
    """A felderítő képernyőn kívül is vannak kézzel másolt küszöbök.

    Kevés, de fontos: az indítás előtti detektálás-próba a motoréval
    AZONOS küszöbnél mondja ki, hogy túl sok ember esik a pályára
    (TOO_MANY_PLAYERS) — ez az a jelzés, ami egy elrontott kalibráció
    esetén megspórol egy órát. Ha a két szám elcsúszik, a próba
    átengedi azt a feldolgozást, amit a motor utólag használhatatlannak
    minősít.

    Ezek a képernyők nem csempe-helperekből állnak, ezért itt
    FÁJL-szinten ellenőrzünk: a hivatkozott konstansnak léteznie kell,
    és az értékének elő kell fordulnia a fájlban.
    """
    konst = _motor_konstansok()
    gyoker = (Path(__file__).resolve().parent.parent.parent
              / "client" / "lib" / "ui")
    baj: list = []
    ellenorzott = 0
    for nev in ("upload_screen.dart", "match_screen.dart",
                "summary_panel.dart", "calibration_screen.dart"):
        f = gyoker / nev
        if not f.exists():
            continue
        sorok = f.read_text(encoding="utf-8").split("\n")
        for i, sor in enumerate(sorok):
            for c in sorted(set(re.findall(
                    r"\b([A-Z][A-Z0-9]{2,}_[A-Z0-9_]+)\b", sor))):
                if c not in konst:
                    baj.append(f"{nev}:{i + 1}: nem létező konstans — {c}")
                    continue
                # A hivatkozás KÖRNYEZETÉBEN keressük az értéket (a
                # fájl egésze túl laza lenne: egy 18-as tördelési szám
                # véletlenül "igazolna" egy elcsúszott küszöböt).
                ablak = "\n".join(sorok[max(0, i - 3):i + 12])
                szamok = {float(x) for x in
                          re.findall(r"\d+(?:\.\d+)?", ablak)}
                varhato = set()
                for v in konst[c]:
                    varhato.update({v, v / 100.0, v * 100.0})
                if not any(any(abs(w - s) < 1e-6 for s in szamok)
                           for w in varhato):
                    baj.append(f"{nev}:{i + 1}: {c}={sorted(konst[c])} "
                               "nincs a hivatkozás környezetében")
                ellenorzott += 1
    assert not baj, "kliens-küszöb eltérés: " + "; ".join(baj)
    assert ellenorzott >= 1, "a konstans-hivatkozások olvasása elromlott"


# A pipeline-ban TÖBB modulban is előforduló, AZONOS nevű konstansok.
# Nem hiba önmagában (a nevek modulonként külön névtérben élnek), de
# csapda: a kliens- és doksi-kommentek NÉVRE hivatkoznak, és a
# következő olvasó a rossz modulban módosít. Új ütközést ezért csak
# tudatosan, ide felvéve szabad bevezetni.
_ISMERT_UTKOZO_KONSTANSOK = {
    # rules.py: 20.0 (pressz-poszt kiállításnál) · decisions.py: 60.0
    "PSR_SHARE_PCT",
    "PSR_MIN_TO",
    # attack_types.py: 60.0 (elzáró-páros) · decisions.py: 50.0 (lágy passz)
    "SPP_SHARE_PCT",
    "SPP_MIN_SHOTS",
    # event_detection.py: 5 (gólpassz-hossz) · roles.py: 3 (kiszolgált poszt)
    "ASR_MIN_ASSISTED",
    # goalkeeper.py: 6.8 (a 6 m-es vonal + ráhagyás, mert a kapus kilép)
    # · play_simulation.py: 6.0 (a VALÓDI szabálykönyvi hatos)
    "GOAL_AREA_RADIUS_M",
}


def test_nem_no_a_duplan_hasznalt_konstansnevek_szama():
    """Ugyanaz a konstansnév két modulban, ELTÉRŐ értékkel: csapda.

    A kliens-csempék és a doksik NÉVRE hivatkoznak a küszöbökre ("a
    backenddel azonos küszöb: PSR_SHARE_PCT"), és ha ugyanaz a név két
    helyen mást jelent, a következő olvasó a rossz modulban módosít —
    a hiba pedig némán él tovább, mert mindkét szám "helyes valahol".

    A meglévő négy ütközés dokumentálva van; újat csak tudatosan, a
    lista bővítésével szabad bevezetni.
    """
    import ast
    import re as _re
    from collections import defaultdict

    hol = defaultdict(dict)
    pipeline = Path(__file__).resolve().parent.parent / "handball" / "pipeline"
    for py in sorted(pipeline.glob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for t in node.targets:
                if not isinstance(t, ast.Name):
                    continue
                if not _re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", t.id):
                    continue
                try:
                    val = ast.literal_eval(node.value)
                except Exception:
                    continue
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    continue
                hol[t.id][py.name] = float(val)

    utkozo = {nev: modulok for nev, modulok in hol.items()
              if len(set(modulok.values())) > 1}
    ujak = sorted(set(utkozo) - _ISMERT_UTKOZO_KONSTANSOK)
    assert not ujak, (
        "új, KÉTSZER definiált konstansnév eltérő értékkel — a "
        "kliens/doksi kommentek névre hivatkoznak, tehát a következő "
        "olvasó a rossz modulban módosítana: "
        + "; ".join(f"{n} ({utkozo[n]})" for n in ujak))


def test_a_csapat_menucsoport_hazat_ad_az_egesz_szezonnak():
    """A csapat-szintű munkának SAJÁT menüpont jár.

    Az edzésterv, a szezon-toplisták és a nyomtatható szezon-riportok
    mind készen voltak a motorban, a felületen viszont a kezdőlap
    mélyén (illetve egy meccs összefoglalójában) laktak: aki nem
    görgetett odáig, nem is tudott róluk. Az edző munkarendjében ez
    önálló feladat ("mit gyakorolunk a héten", "hol tartunk a
    szezonban"), a játékos pedig a toplistán keresi magát.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert '"CSAPAT"' in shell, "nincs CSAPAT menücsoport"
    for nav, nev, fajl in (("NavId.training", "Edzésterv",
                            "training_plan_screen.dart"),
                           ("NavId.season", "Szezon", "season_screen.dart")):
        assert nav in shell, f"nincs {nev} menüpont"
        assert f'"{nev}"' in shell, f"a {nav} menüpontnak nincs neve"
        assert (lib / "ui" / fajl).exists(), f"nincs {nev} képernyő"

    # A menü minden elemének jár gyorsbillentyű: tíz elemnél a 0 a
    # tizedik. Ha a menü bővül, ez a sor mondja meg, hogy a kiosztás
    # elfogyott — némán ne szakadjon meg.
    elemek = shell.count("(NavId.")
    # (a navTo switch-ágai nem "(NavId." alakúak, csak a menü-lista)
    assert elemek >= 10, elemek
    assert "LogicalKeyboardKey.digit0" in shell, (
        "a tizedik menüpontnak nincs gyorsbillentyűje")

    # A két új képernyő a KÖNYVTÁR-szintű végpontokat használja (nem egy
    # meccsét): ez a különbség köztük és a meccs-elemző között.
    terv = (lib / "ui" / "training_plan_screen.dart").read_text(
        encoding="utf-8")
    assert "fetchLibraryTrainingFocus" in terv, (
        "az edzésterv nem a visszatérő (szezon-szintű) fókuszokat kéri")
    assert "fetchTraining" in terv, (
        "az edzéstervből nem kérhető le EGY meccs fókusza")

    szezon = (lib / "ui" / "season_screen.dart").read_text(encoding="utf-8")
    for hivas in ("fetchLibrarySummary", "fetchLibraryLeaders",
                  "fetchSeasonReport", "fetchHeadToHead"):
        assert hivas in szezon, f"a szezon-lapról hiányzik: {hivas}"
    # A toplista mezszám-alapú: aki nincs beszámozva, kimarad — ezt ki
    # kell mondani, különben hiányzó teljesítménynek olvassa a játékos.
    assert "MEZSZÁM" in szezon or "mezszám" in szezon, (
        "a toplista nem mondja meg, miért maradhat ki valaki")


def test_a_meccsterv_sajat_menupontot_kap():
    """A meccs előtti este EGY kérdése: hogyan verjük meg ŐKET.

    A meccsterv-illesztés (a mi profilunk × az ő profiljuk) készen volt,
    de csak a felderítő jelentés egyik kártyájaként: hozzá kézzel kellett
    kijelölni MINDEN meccset, amelyiken az ellenfél játszott, és külön a
    sajátjainkat is. Saját menüpontból két csapatnév elég — a meccseket
    a képernyő gyűjti össze a könyvtárból.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "NavId.matchup" in shell, "nincs Meccsterv menüpont"
    assert '"Meccsterv"' in shell, "a menüpontnak nincs neve"
    assert (lib / "ui" / "matchup_screen.dart").exists(), (
        "nincs Meccsterv képernyő")

    kepernyo = (lib / "ui" / "matchup_screen.dart").read_text(
        encoding="utf-8")
    assert "fetchMatchup" in kepernyo, (
        "a Meccsterv nem a meccsterv-illesztést kéri")
    # A lényeg, amiért saját képernyőt kapott: a meccseket NEM a
    # felhasználó kattintja össze, hanem a csapatnévből épülnek.
    assert "_itemsOf" in kepernyo, (
        "a képernyő nem gyűjti össze magától a csapat meccseit")
    assert "listMatches" in kepernyo, (
        "a képernyő nem a könyvtárból dolgozik")


def test_a_klipek_menupont_szabadon_kombinalhato_csomagokat_ad():
    """A videó-dosszié összeállítása önálló munka.

    A klipvágás eddig csak a meccs-elemző eszköztárában élt, és ott is
    EGY csomag egyszerre: aki a gólokat ÉS a kihagyott ziccereket is
    akarta, kétszer vágatott, két zip-be. Az edzés előtt viszont pont
    az a kérdés, mit viszünk le a pályára — a csomagokat szabadon kell
    tudni kombinálni, és nem kell hozzá megnyitni a meccset.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "NavId.clips" in shell, "nincs Klipek menüpont"
    assert '"Klipek"' in shell, "a menüpontnak nincs neve"
    assert (lib / "ui" / "clips_screen.dart").exists(), (
        "nincs Klipek képernyő")

    kepernyo = (lib / "ui" / "clips_screen.dart").read_text(
        encoding="utf-8")
    assert "startClipExport" in kepernyo and "fetchClipsZip" in kepernyo
    # A lényeg: TÖBB típus egyszerre, egy exportban.
    assert "_selected.toList()" in kepernyo, (
        "a képernyő nem több kijelölt csomagot ad át")

    # A felkínált klip-típusoknak LÉTEZNIÜK kell a motorban: egy
    # elgépelt kulcs némán üres csomagot adna (a backend ismeretlen
    # típusra egyszerűen nem vág semmit).
    import re as _re

    from pathlib import Path as _Path

    app = (_Path(__file__).resolve().parents[1] / "handball" / "api"
           / "app.py").read_text(encoding="utf-8")
    esemeny = {"goal", "shot", "turnover"}  # a detect_events alap-típusai
    ismert = esemeny | set(_re.findall(r'if "(\w+)" in types', app))
    kinalt = set(_re.findall(r'\("(\w+)", "', kepernyo))
    hianyzo = kinalt - ismert
    assert not hianyzo, f"a kliens nem létező klip-típust kínál: {hianyzo}"


def test_a_csapat_fejlodes_egy_csapatnevbol_indul():
    """A "fejlődünk-e?" kérdést nem szabad húsz kattintással kérdezni.

    A fejlődés-követés (két időszak összevetése) eddig csak a kezdőlap
    egyik gombja volt, és két párbeszéd-ablakon át KÉZZEL kellett
    kijelölni, melyik meccs melyik időszakba tartozik — meccsenként azt
    is, hogy a figyelt csapat melyik oldalon játszott. Saját
    menüpontból egy csapatnév elég: a meccseket a képernyő szedi össze
    és vágja ketté, a vágópont húzható.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "NavId.teamTrend" in shell, "nincs Csapat-fejlődés menüpont"
    assert '"Csapat-fejlődés"' in shell, "a menüpontnak nincs neve"
    assert (lib / "ui" / "team_trend_screen.dart").exists(), (
        "nincs Csapat-fejlődés képernyő")

    kepernyo = (lib / "ui" / "team_trend_screen.dart").read_text(
        encoding="utf-8")
    assert "_ofTeam" in kepernyo, (
        "a képernyő nem szedi össze magától a csapat meccseit")
    assert "Slider(" in kepernyo, "a vágópont nem húzható"
    # Az összevetést a MEGLÉVŐ fejlődés-nézet rajzolja — ne szülessen
    # belőle második, széttartó megjelenítés.
    assert "TrendScreen(" in kepernyo, (
        "a képernyő nem a meglévő fejlődés-nézetet használja")

    # A fejlődés-nézet kijelölése a saját menüpontján álljon, akárhonnan
    # nyílt meg (korábban a kezdőlapot jelölte).
    trend = (lib / "ui" / "trend_screen.dart").read_text(encoding="utf-8")
    assert "NavId.teamTrend" in trend, (
        "a fejlődés-nézet még mindig más menüpontot jelöl aktívnak")


def test_a_keret_lap_mindenkit_mutat_nem_csak_a_top_otot():
    """A játékos a SAJÁT sorát keresi, nem a gólkirályt.

    A szezon-toplisták az öt legjobbat adják; a mezszám-alapú összegek
    viszont mindenkire megvannak a motorban, csak nem jutottak ki a
    felületre. A keret-lap ezt a metszetet adja: a csapat minden
    mezszáma egy táblában, meccs-darabszámmal — enélkül egy alacsony
    gólszám félrevezet (kevés játék vagy gyenge forma?).
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "NavId.roster" in shell, "nincs Keret menüpont"
    assert '"Keret"' in shell, "a menüpontnak nincs neve"
    assert (lib / "ui" / "roster_screen.dart").exists(), (
        "nincs Keret képernyő")

    kepernyo = (lib / "ui" / "roster_screen.dart").read_text(
        encoding="utf-8")
    assert "fetchTeamRoster" in kepernyo, "a keret-lap nem a keretet kéri"
    # A meccs-darabszám oszlop nem elhagyható: ez adja a többi szám
    # olvasatát.
    assert '("matches", "Meccs")' in kepernyo, (
        "a keret-lapról hiányzik a meccs-darabszám oszlop")
    # Egy sorra koppintva a játékos görbéje nyíljon — ELŐRE KITÖLTVE,
    # ne egy üres űrlap (különben a kattintás semmit nem takarít meg).
    assert "initialJersey" in kepernyo, (
        "a keret-lap nem tölti ki előre a játékos-görbét")

    trend = (lib / "ui" / "player_trend_screen.dart").read_text(
        encoding="utf-8")
    assert "initialJersey" in trend and "initialTeam" in trend, (
        "a játékos-görbe nem fogad előre kitöltött játékost")

    # A kliens által kért végpontnak léteznie kell a motorban.
    from pathlib import Path as _Path

    app = (_Path(__file__).resolve().parents[1] / "handball" / "api"
           / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/library/roster")' in app, (
        "a kliens olyan végpontot hív, ami nincs a motorban")


def test_a_jegyzetek_egy_listat_alkotnak_es_visszanezhetok():
    """A jegyzetelés eddig egyirányú volt.

    A meccs közben meg lehetett jelölni egy pillanatot, de utána csak
    ANNAK a meccsnek a lejátszójában lehetett megtalálni. Az edző
    fejében viszont a jegyzetek egyetlen listát alkotnak — "amit vissza
    akarok nézni" —, és a hét közbeni munka ebből indul.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    shell = (lib / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "NavId.notes" in shell, "nincs Jegyzetek menüpont"
    assert '"Jegyzetek"' in shell, "a menüpontnak nincs neve"
    assert (lib / "ui" / "notes_screen.dart").exists(), (
        "nincs Jegyzetek képernyő")

    kepernyo = (lib / "ui" / "notes_screen.dart").read_text(
        encoding="utf-8")
    assert "fetchLibraryNotes" in kepernyo, (
        "a lap nem a könyvtár-szintű jegyzeteket kéri")
    # A visszanézés a lényeg: a meccs A MEGJELÖLT pillanatnál nyíljon.
    assert "initialFrame" in kepernyo, (
        "a jegyzetre koppintva nem a megjelölt pillanat nyílik")

    meccs = (lib / "ui" / "match_screen.dart").read_text(encoding="utf-8")
    assert "initialFrame" in meccs, (
        "a meccs-elemző nem fogad kezdő-képkockát")
    # A kért képkockát HATÁROK KÖZÉ kell szorítani: egy régi jegyzet
    # mutathat a meccs hosszán túlra (újravágott videó).
    assert "clamp(0, utolso)" in meccs, (
        "a kezdő-képkocka nincs a meccs hosszához igazítva")

    from pathlib import Path as _Path

    app = (_Path(__file__).resolve().parents[1] / "handball" / "api"
           / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/library/notes")' in app, (
        "a kliens olyan végpontot hív, ami nincs a motorban")


def test_a_jatekosok_nevet_kapnak_nem_csak_szamot():
    """Az egész termék "#7"-et mondott.

    Az edző nem számokban gondolkodik, a játékos pedig a saját nevét
    keresi. A név a CSAPATHOZ és a mezszámhoz tartozik (a mezszám a
    szezonban stabil, a track-azonosító nem), ezért egy helyen kell
    tudni megadni — és ott kell látszania, ahol a játékosról szó van.
    """
    import pytest

    lib = _client_lib()
    if not lib.exists():
        pytest.skip("nincs kliens a fában")

    keret = (lib / "ui" / "roster_screen.dart").read_text(encoding="utf-8")
    assert "setPlayerName" in keret, "a keret-lapon nem adható meg név"
    assert '"NÉV"' in keret, "a keret-lapon nincs név-oszlop"

    # Ahol a játékosról szó van, ott a névnek is látszania kell —
    # különben az egyik lapon Kovács, a másikon #7 szerepel.
    szezon = (lib / "ui" / "season_screen.dart").read_text(encoding="utf-8")
    assert '"name"' in szezon, (
        "a toplistákon nem látszik a felvitt név")
    trend = (lib / "ui" / "player_trend_screen.dart").read_text(
        encoding="utf-8")
    assert '"name"' in trend, (
        "a játékos-görbén nem látszik a felvitt név")

    from pathlib import Path as _Path

    app = (_Path(__file__).resolve().parents[1] / "handball" / "api"
           / "app.py").read_text(encoding="utf-8")
    assert '@app.post("/library/players")' in app
    # A névjegyzék NEM a meccs-mappába való: a betöltő minden ottani
    # *.json-t meccsnek próbál olvasni.
    assert '_data_dir.parent / "players.json"' in app, (
        "a névjegyzék a meccs-mappában landolna")
