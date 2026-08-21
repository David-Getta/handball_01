# CLAUDE.md — fejlesztési recept

Ez a fájl a leggyorsabb fejlesztési út leírása. Új elemző réteg
hozzáadásakor NE a kódbázisból derítsd vissza a mintát — kövesd az
alábbi checklistet, és minta gyanánt nézd meg a legutóbbi
"…: egy réteg, sok felület" commitot (`git log --oneline`).

## A projekt egy mondatban

Kézilabda videó-elemző: Python backend (`backend/handball/`, FastAPI +
pipeline-rétegek a `Tracking`/`Match` adatmodellen) + Flutter kliens
(`client/`). Minden elemzés magyar edzői nyelven indokol.

## Parancsok

```bash
# Teljes backend teszt (kb. 5 perc, 1300+ teszt) — commit előtt kötelező:
cd backend && python3 -m pytest -q

# Gyors kör fejlesztés közben (csak az érintett fájlok):
cd backend && python3 -m pytest tests/test_xg.py -q

# Dart-ellenőrzés (nincs Flutter a gépen — zárójel-egyensúly):
awk 'BEGIN{b=0} {n=gsub(/\{/,"x"); m=gsub(/\}/,"x"); b+=n-m} \
  END{print "braces: "b}' client/lib/ui/scouting_screen.dart   # 0 a jó
```

## Új réteg receptje: "egy réteg, sok felület"

Egy réteg = egy commit. A commit-üzenet mintája a git-történetben.
Sorrendben (kb. 200–280 sor összesen):

1. **Motor** — új függvény a témába vágó pipeline-modulban
   (`xg.py`, `attack_types.py`, `defense.py`, `goalkeeper.py`, …).
   - Küszöbök modul-szintű NAGYBETŰS konstansban, magyar kommenttel.
   - Magyar docstring: mit mér, mit jelent edzőileg, mit ad vissza.
   - Csapatonkénti dict: `{"home": {...}, "away": {...}}`; kevés
     mintánál `None` ítélet (sose hallgatólagos 0).
2. **API** (`api/app.py`) — KÉT helyre:
   - `/analyze` válasz: `try/except` blokk, `res["reteg_nev"] = ...`,
   - meccs-csomag: `_layer("reteg_nev", lambda: fn(match))`.
3. **Edzői összefoglaló** (`pipeline/coach_summary.py`,
   `_style_section`) — egy mondat `try/except`-ben, a motor
   konstansával azonos küszöb.
4. **Felderítés** (`pipeline/scouting.py`) — ÖT pont:
   - `ScoutingReport` mezők: CSAK darabszám/összeg alapú tárolás
     (arány sose), hogy meccsek közt pontosan összegződjön,
   - `_coach_keys`: edzői kulcs (mit tegyen ellene a saját csapat),
   - `scout_team`: mezők kitöltése a motorból,
   - `matchup_plan`: új sorszámozott páros szabály (az ő gyengéjük ×
     a ti erősségetek) — a KÖVETKEZŐ szám: 441,
   - `combine_reports`: a mezők összegzése.
5. **Edzés-fókusz** (`pipeline/training.py`, `training_focus`) — új
   sorszámozott szabály, az újak felülre — a KÖVETKEZŐ szám: 461.
6. **Kliens** (`client/lib/ui/scouting_screen.dart`) — `_xxx(r)`
   helper (a backenddel azonos küszöbök, kommentben jelezve) + csempe
   a listában.
7. **Teszt** (`backend/tests/test_<modul>.py`) — legalább egy: a
   pozitív eset + a "kevés minta → None" eset.
8. **CHANGELOG.md** — bejegyzés a "Kiadatlan" lista TETEJÉRE, a
   meglévő stílusban (mit mér, edzői olvasat, felület-lista).

A helyi importok (`from .xg import ...` a függvényen belül) és a
`try/except`-tel izolált felületek szándékosak: egy réteg hibája nem
viheti el a többit. Tartsd ezt a stílust.

## Számláló-frissítés (recept végén)

Réteg-commit után frissítsd ITT: meccsterv-szabály következő száma,
edzés-szabály következő száma. ÉS generáld újra a két generált
dokumentumot (őr-teszt ellenőrzi mindkettőt):

```bash
cd backend && python3 -m scripts.layer_catalog   # docs/RETEG_KATALOGUS.md
cd backend && python3 -m scripts.project_facts   # docs/SZAMOK.md
```

A `project_facts` a pályázati doksikba ÍRT réteg-/teszt-számokat is
igazítja (executive summary, Part B, pitch deck, EIC-terv, útiterv és
a README) — őr-teszt ellenőrzi, hogy egyeznek a tény-lappal. A README
"Hol tartunk" számát tehát nem kell külön kézzel frissíteni.

A sorrend-függés jelentése (`docs/SORREND_FUGGES.md`) lassú (percek),
ezért NINCS őr-tesztje — kiadás előtt futtasd (a tükrözés-őrrel
együtt, lásd lejjebb):

```bash
cd backend && python3 -m scripts.order_sensitivity
```

A lista jelenleg ÜRES, és annak is kell maradnia. A sorrend-függés oka
a kapus-jelölés volt: a `primitive_cache` hatókör nyitása azóta
elvégzi (tehát a termék minden összeállítása sorrend-független), a
felismerés pedig holtversenynél a kaputól mért távolság alapján dönt
(korábban a beolvasás sorrendje szerint, ami a fal védőjét jelölte
kapusnak). Ha a jelentésben mégis megjelenik egy réteg, az REGRESSZIÓ
— ne a listát fogadd el, hanem keresd meg, mi írja felül a szerepeket.

A tükrözés-őr (`docs/TUKROZES.md`) ugyanígy jelentés-szintű (fél perc):

```bash
cd backend && python3 -m scripts.mirror_sides
```

Amit néz: a pálya hossztengelyére tükrözött meccsen minden
oldal-megnevezésnek ("bal szél" → "jobb szél") meg kell fordulnia. Aki
a nyers y-ból nevez oldalt, az a VÉDEKEZŐ csapatról fordítva állít —
a két csapat szemben áll. Ha új réteged oldal-címkét ad, a védekező
oldal nézőpontjából nevezd (minta: defensive_gaps, conceded_side_bias),
és futtasd le ezt kiadás előtt. A hibás-lista ÜRES, maradjon is az.

A stride-érzékenység jelentése (`docs/STRIDE_ERZEKENYSEG.md`) szintén
jelentés-szintű (~1,5 perc):

```bash
cd backend && python3 -m scripts.stride_sensitivity
```

Amit néz: ugyanaz a meccs a termék alap-ritkításával (stride=3,
effektív fps = fps/3) másképp ítél-e. Az eltérés nem feltétlenül hiba
(kevesebb minta → óvatosabb ítélet), de kocka-küszöbű új rétegnél
tudd: a küszöböd valós időben HÁROMSZOROSÁT követeli a termékben.

## Commit-stílus

- Cím: `<Réteg magyar neve>: egy réteg, sok felület`.
- Törzs: Új réteg (mit mér + edzői olvasat), Motor, Felületek
  (felsorolás), Teszt + "A teljes backend csomag zöld (N teszt)."
- Commit előtt: teljes pytest zöld + Dart zárójel-egyensúly 0.
- A munkaág: `claude/handball-ai-analysis-9dq1a2` — oda push.
