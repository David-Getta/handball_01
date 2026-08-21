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

    m = re.search(r"Widget _metricTile\(String label, String value\) \{"
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
