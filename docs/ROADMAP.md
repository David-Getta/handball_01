# Útiterv (fázisok)

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
- Eseményfelismerés (gól, lövés, passz, labdaeladás). ⏳ (a labda+pozíciókból).
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
- Kézilabda várható-érték modell (EPV/xG).
- Döntéseloszlás játékosonként + szituációnként ("10/7-szer ide passzol").
- Optimális opció vs. tényleges döntés összevetése.
- **Eredmény**: egyéni játékosjelentés a döntéshozatal minőségéről.

## 5. fázis — Szimuláció
- Tanult ellenfélmodell egy adott csapat stílusából.
- Edző által tervezett figura lejátszása az ellenfél ellen.
- **Eredmény**: "próbáld ki a figurádat X csapat védekezése ellen".

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
