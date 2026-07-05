# Kézilabda szabályok — a rendszer szempontjából releváns kivonat

> A **követést, létszámot és kalibrációt** befolyásoló szabályok strukturált
> kivonata, amit a rendszer logikája használ. NEM a teljes szabálykönyv.
>
> **Forrás:** *A kézilabdázás játékszabályai* (magyar kiadás, 2025.07.01 verzió).
> A szabályszámok (pl. `4:1`) az IHF/MKSZ szabálykönyv pontjaira hivatkoznak.
> A teljes (szerzői jogvédett) szövegét nem tároljuk a repóban.

## 1. Pálya geometria (kalibrációhoz) — 1. szabály
- Játéktér: **40 m hosszú × 20 m széles** (1:1).
- Biztonsági zóna: oldalvonalnál min. **1 m**, alapvonal mögött **2 m** (1:1).
- Kapu: **2 m magas × 3 m széles** (1:6). Kapufa 8×8 cm, két elütő színnel festve
  → jól detektálható vizuális referencia.
- Vonalvastagság: **5 cm** (a kapufák közti gólvonal 8 cm).
- **Kapuelőtér-vonal (6 m)**: 3 m egyenes a kapu előtt, 6 m-re a gólvonaltól, két
  oldalt 6 m sugarú negyedkörrel az alapvonalig (1:4, 6. szabály). Ide csak a
  kapus léphet.
- **Szabaddobási vonal (9 m)**: szaggatott, a kapuelőtér-vonaltól 3 m-re (= 9 m),
  15 cm-es vonalrészek (1:5).
- **7 m-es vonal**: 1 m hosszú, 7 m-re a gólvonaltól (1:7).
- **Kapushatárvonal (4 m)**: 15 cm, 4 m-re a gólvonaltól (1:7).
- **Cserevonal**: az oldalvonalon a középvonaltól 4,5 m-ig (1:9).
- Középvonal, oldalvonalak, alapvonalak/gólvonalak.
- → Ezek a vonalak, ívek és metszéspontok a homográfia-kalibráció referenciái.

## 2. Létszám — 4. szabály
- Keret: **16 játékos** (4:1). Szövetségek eltérhetnek, de **max. 16**.
- Pályán egyszerre csapatonként: **max. 7 fő** (6 mezőny + 1 kapus) (4:1).
- A mérkőzést **legalább 5 játékossal** kell kezdeni (4:1 magyarázat).
- A pályán lévő tényleges szám **változó** (lásd kiállítás, kapus nélküli játék).
- Pozíciós szerepek (becsléshez, nem szabálykönyvi): bal szélső, bal átlövő,
  irányító, jobb átlövő, jobb szélső, beálló, kapus.

## 3. Cserék — 4. szabály
- **Bármikor, korlátlanul**, a saját **cserezónán** keresztül, bejelentés nélkül,
  miután a lecserélt játékos már elhagyta a játékteret ("repülő csere") (4:4).
- Következmény a követésre: játékosok eltűnhetnek/megjelenhetnek a cserevonalnál —
  ezt el kell különíteni a kiállítástól és a képen kívüliségtől.

## 4. Kapus — 4. szabály
- Csapatonként **egyszerre csak 1 kapus** lehet a pályán (4:3).
- A kapus bármikor mezőnyjátékossá válhat és vissza; mezőnyjátékos kapus lehet,
  ha **kapusként megkülönböztethető** (4:4).
- **Kapus nélküli játék**: ekkor a pályán **7 mezőnyjátékos** tartózkodhat (4:7).
  Jellemző "üres kapus" helyzetek: 7 a 6 ellen, 6 a 6 ellen, egyéb.
- **Mezszín-szabály (17:3, 4:8)**: a csapat kapusainak mezszíne egyezzen egymással
  és **különbözzön a saját mezőnyjátékosokétól ÉS az ellenfél kapusaiétól**.
  → Megbízható jelzés a csapat-szétválasztáshoz és a kapus azonosításához; a
  kapus-szín eltűnése a pályáról = kapus nélküli (7 mezőnyjátékos) állapot.

## 5. Mezszámok — 4. szabály
- Háton min. **20 cm**, mellen min. **10 cm**, **1–99** közötti szám, az
  öltözéktől jól megkülönböztethető színnel (4:9).
- → **Mezszám-OCR** lehetséges, ami erősíti a ReID-et (visszatérő/képbe belépő
  játékos azonosítása) — kulcs a részleges láthatóság kezeléséhez.

## 6. Kiállítások / kizárás — 16. szabály
- **Időleges kiállítás: 2 perc** (16:5). Ekkor a csapatból egy játékosnak el kell
  hagynia a játékteret 2 percre.
- **Több játékos lehet egyidejűleg kiállítva** → a létszám több fővel is
  csökkenhet egyszerre.
- Ugyanazon játékos **3. kiállítása → kizárás** (16:6 d).
- **Kizárás (piros lap)**: a játékos véglegesen kiáll, a csapat létszáma 1 fővel
  csökken — **2 percre**, DE **4 percre**, ha a kizárás a **16:9 b–d** szerinti
  súlyos szabálytalanság miatt történt (16:8). → ez a "4 perc" esete.
- Modell: **kiállítás-intervallumok listája** csapatonként (kezdet + 2/4 perc),
  átfedés megengedett. Pillanatnyi létszám = alap − épp aktív kiállítások.

## 7. Időkezelés — 2. szabály
- Játékidő (16 év felett): **2 × 30 perc**, félidei szünet **10 perc** (max 15)
  (2:1). Fiatalabb: 8–12 év 2×20, 12–16 év 2×25.
- Hosszabbítás: 5 perc szünet után **2 × 5 perc** (1 perc szünet + térfélcsere);
  ha kell, második 2×5 perc (2:2).
- **Csapatidőkérés**: **1 perc**; félidőnként 1 (vagy versenykiírás szerint
  összesen **3/meccs**, félidőnként max. 2). Az utolsó 5 percben max. 1/csapat
  (2:10).
- → Ezek tagolják az idővonalat és a fázis-szegmentálást.

## Hogyan használja ezt a rendszer
| Komponens | Felhasznált szabály |
|-----------|---------------------|
| Kalibráció [A] | 1. szakasz (pálya-geometria) |
| Csapat-szétválasztás [D] + kapus | 4. szakasz (mezszín-szabály) |
| Követés/ReID [C] | 5. szakasz (mezszám-OCR) |
| Létszám-állapot [F] | 2., 4., 6. szakasz |
| Esemény-idővonal | 3., 6., 7. szakasz (csere, kiállítás, időkérés, félidő) |

A meccs-esemény idővonal (csere, kiállítás, kapuscsere, időkérés, félidő) MVP-ben
kézzel felvíve, a 2. fázisban automatikusan felismerve.
