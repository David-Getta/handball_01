# Útiterv (fázisok)

> ## Állapot-összefoglaló (frissítve: 2026-08)
>
> **Kész és tesztelt (1891 automata teszt zöld; élő számok:
> `docs/SZAMOK.md`):**
> - Teljes feldolgozó lánc [A]–[H]: YOLO-detektálás, ByteTrack, bíró-szűrő,
>   csapatszín (k-means), 4-sarkos kalibráció + **pásztázás-követés**
>   (kameramozgás-kompenzáció), **képen kívüli becslés** (roster/kiállítások
>   szerint), sötét bevezető auto-kihagyás.
> - Elemző rétegek: taktika (birtoklás/fázis/védőformák/tempó), események
>   (passz/lövés/gól/labdaeladás), játékos-döntések, figura-felismerés,
>   **élő edzői javaslatok**, védelem-tanulás + figura-szimuláció.
> - **Ellenfél-felderítés**: egy- és több-meccses jelentés, lövési zónák,
>   kulcsjátékosok, "hogyan játssz ellenük", nyomtatható HTML-export,
>   **figura-egyezés a mentett playbookkal**.
> - App (Flutter): dashboard/könyvtár, feltöltés+kalibráció+feldolgozás élő
>   állapottal, meccs-elemző (statisztika/összegzés/döntések/események),
>   élő követés, felderítés, figura-tervező **mentés/betöltéssel**,
>   kiállítás-szerkesztő; a motor **automatikus indítása**.
> - Kiadás: PyInstaller-csomagolás + Windows-telepítő + **GitHub Actions
>   automata build** (Releases-re).
>
> **Következő validáció (a fejlesztő gépét igényli):** end-to-end teszt valódi
> meccsvideón (labda+birtoklás élesben), `flutter analyze/run`, első telepítő
> legyártása az Actions-ből. Részletek: TRL-értékelés a beszélgetésben; a
> felvétel-specifikus tudnivalók: `FOOTAGE_NOTES.md`.

Alulról építkezünk: minden fázis önmagában is használható eredményt ad, és a
következő alapja. A "menő" funkciók (VR, élő javaslat) a végén vannak, mert a
megbízható alaprétegre épülnek.

---

## 0. fázis — Alapok (most)
- Repó-struktúra, dokumentáció, fejlesztői környezet.
- Adatmodell rögzítése (`Tracking`).
- **Eredmény**: tiszta projekt, amire építeni lehet. ✅ ez a commit.

## 1. fázis — MVP: Követés videóból  ⭐ következő lépés
**Részletes, döntésekkel rögzített terv: [`MVP_PLAN.md`](MVP_PLAN.md).**

**Cél**: egyetlen (pásztázó-kamerás) meccsvideóból 2D követési adatot (`Tracking`)
előállítani, és felülnézeti taktikai térképen megjeleníteni.
- Játékos- + labdadetektálás (előtanított YOLO-val indul).
- Követés / ID-tartás (ByteTrack) + **ReID** (visszatérő játékos azonosítása).
- Csapatba sorolás mezszín alapján — **mindkét csapat + labda**.
- Pálya-homográfia: kézi referencia-kalibráció + auto propagáció a pásztázáshoz.
- **Teljes csapatkövetés becsléssel**: a látható játékosokat mérjük, a képen
  kívülieket becsüljük (roster + szerepmodell), bizonytalanság-jelöléssel.
- 2D felülnézeti vizualizáció + alap statisztikák (futott táv, sebesség, hőtérkép).
- **Eredmény**: "betöltök egy videót, kapok egy felülnézeti taktikai animációt
  és alap statisztikákat." Ez már önmagában eladható elemzőeszköz.

## 2. fázis — Taktikai értelmezés
- Fázis-szegmentálás (támadás/védekezés/átmenet). ✅ kész és tesztelt (`tactics.py`).
- Védekezési forma felismerése (6-0, 5-1, 3-2-1…). ✅ kész és tesztelt.
- Labdabirtoklás (a labdához legközelebbi csapat). ✅ kész és tesztelt.
- Tempó-metrikák, csapat-stílusprofil. ✅ kész és tesztelt (birtoklások száma,
  átlagos támadás-hossz, átmenet-arány, labda-tempó; `team_style_profile`).
- Eseményfelismerés (gól, lövés, passz, labdaeladás). ✅ heurisztikus felismerés
  kész és tesztelt (`event_detection.py`, API: `/events`); valódi adattal finomítható.
- **Eredmény**: csapatstílus-jelentés ("így védekeznek, ilyen tempóban"). Az
  alapok (fázis, forma, birtoklás) megvannak; az API-n: `/tactics`.

## 3. fázis — Figurák (set play-ek) felismerése
- Trajektória-szekvenciák klaszterezése → visszatérő figurák azonosítása.
  ✅ alap kész és tesztelt: támadás-szegmentálás → mozgás-ujjlenyomat →
  klaszterezés (`setplays.py`, API: `/setplays`).
- Figura-könyvtár csapatonként. ⏳ (finomabb trajektória-modell későbbi bővítés).
- **Eredmény**: "ez a csapat ezt a N figurát játssza, ilyen gyakorisággal" — az
  alap-felismerés megvan; a pontosság a valódi adattal és finomabb leíróval nő.

## 4. fázis — Játékos-döntéselemzés
- Kézilabda várható-érték modell (EPV/xG). ✅ egyszerű heurisztika kész
  (`decisions.py`: `shot_value`, `pass_completion`); később tanult modellre cserélhető.
- Döntéseloszlás játékosonként ("10/7-szer ide passzol"). ✅ `pass_distribution`.
- Optimális opció vs. tényleges döntés összevetése. ✅ `optimal_rate`, `avg_value_gap`.
- **Eredmény**: egyéni játékosjelentés a döntéshozatalról. Az alap kész és tesztelt
  (API: `/players/{id}/decisions`); a pontosság valódi adattal és tanult EPV-vel nő.

## 5. fázis — Szimuláció
- Tanult ellenfélmodell egy adott csapat stílusából. ✅ alap kész és tesztelt
  (`DefenseModel.learn`: védőszám + vonalmélység + oldalkövetés).
- Edző által tervezett figura lejátszása az ellenfél ellen. ✅ `simulate_setplay`
  + `evaluate_setplay` (a teremtett lövőhelyzet pontozása); API: `/simulate-setplay`.
- **Eredmény**: "próbáld ki a figurádat X csapat védekezése ellen" — az alap megvan;
  a védekezési modell később finomabb (tanult) változatra cserélhető.

## 6. fázis — 3D & LiDAR
- LiDAR ingest, 3D rekonstrukció, pontfelhő-alapú követés.
- 3D bejárható nézet (web, Three.js).

## 7. fázis — VR
- VR kliens (Unity), a csapat bejár a pályára, edző mutatja a szituációt.

## 8. fázis — Élő meccskövetés
- Valós idejű pipeline (streaming inferencia).
- Élő dashboard + javaslatok (mit játssz, kit cserélj).

---

## Kockázatok / nyitott kérdések
- **Adat**: honnan lesz címkézett kézilabda videó? Saját felvételek? Klubpartner?
- **Kamera**: fix taktikai kamera (felülről) sokkal könnyebb, mint broadcast vágás.
- **Kalibráció**: kézi keypoint az MVP-hez elég; automatikus vonalfelismerés később.
- **EPV-modell**: kevés nyilvános kézilabda-adat van — ez a legkutatás-igényesebb rész.
- **Birtoklás-váltás billegése — MEGOLDVA.** A birtokos a labdához
  LEGKÖZELEBBI játékos, és a váltás egyetlen képkockából eldőlt.
  Tömörülésnél (és zajos labda-észlelésnél) ez kockánként ide-oda
  billegett, és minden billenésből passz vagy ELADOTT LABDA lett — az
  első éles meccsen ez a meccs ELŐTTI felállásnál is eladásokat
  gyártott.

  A megoldás három nekifutásból állt össze. (1) Minimális tartás
  MINDEN birtoklás-váltásra: működik, de globálisan megváltoztatja a
  szemantikát, és 16+ fixture épít az egy-kockás váltásra. (2)
  Pattanás-szűrő (A → B → A): nem járható, mert a fixture-ök szerint
  ugyanez legitim oda-vissza passzolás is lehet — a kettőt CSAK az
  időtartam különbözteti meg. (3) **A járható út: a kitartást csak az
  ELADOTT LABDÁRA követeljük meg**, a csapaton belüli passzra nem. A
  passz kisebb állítás (a labda nem hagyta el a csapatot); az eladott
  labdához viszont a labdának oda kell érnie az ellenfélhez, és neki
  uralnia is kell.

  A megvalósítás CSAPAT-futamokon dolgozik, nem játékosonként: ha az
  ellenfél megszerzi a labdát és rögtön tovább is passzolja, az attól
  még valódi szerzés — játékosonkénti méréssel az ő passzaik elnyelnék
  a jelöltet. A `TURNOVER_MIN_HOLD_S = 0,3` a termék alap-ritkításával
  (stride=3) ~0,36 másodpercnyi valós idő; ennél gyorsabban valódi
  labdaszerzés sem stabilizálódik. A felvétel VÉGÉN álló, meg nem
  erősített futam nem ad eseményt.

  A 18 érintett fixture átírva valósághű birtoklás-hosszra (a
  kockánként váltó birtokos valódi meccsen nem fordul elő); a teljes
  csomag zöld. A minőség-jelentés `TURNOVER_RATE_MAX_PER_MIN` jelzése
  megmarad hátsó védvonalnak: ha az eladás-ütem így is hihetetlen, azt
  kimondja.
