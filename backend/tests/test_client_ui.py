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
_DART_ROW_KEYS = {
    "breaks", "chances", "count", "def_frames", "depth_sum_m",
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
