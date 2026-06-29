# 1. fázis — MVP részletes terv

> Ez a dokumentum a `ROADMAP.md` 1. fázisának finomított, döntésekkel rögzített
> változata. A felvételi és scope-döntések a projekt tulajdonosával egyeztetve.

## Rögzített döntések

| Téma | Döntés |
|------|--------|
| **Kamera** | Rögzített pozíciójú, balra-jobbra **pásztázó** kamera (fix helyről forog) |
| **Követési scope** | **Teljes csapatkövetés becsléssel** — a látható játékosokat mérjük, a képen kívülieket becsüljük, explicit bizonytalansággal |
| **Kit követünk** | **Mindkét csapat + labda** (mezszín alapján szétválasztva) |
| **Kimenet** | Felülnézeti taktikai animáció + alap statisztikák (futott táv, sebesség, hőtérkép) |

## Miért speciális a pásztázó kamera

Mivel a kamera **helyben marad** és csak forog, a képkockák egymáshoz tiszta
**homográfiával** köthetők (fix pozíció → nincs parallaxis). Ez két dolgot jelent:

1. **Kalibráció egyszer, propagáció automatikusan.** Egyszer kézzel kalibrálunk
   egy referencia-nézetet a pálya valós koordinátáira, majd minden képkocka
   homográfiáját a referenciához illesztjük (jellemzőpont-illesztés / pályavonal-
   felismerés). A pásztázás így végig követhető egyetlen kézi kalibrációból.
2. **Részleges láthatóság.** A kamera jellemzően a labda oldalát mutatja, nem
   mindenkit egyszerre. A támadási fázis általában teljesen látszik; a túloldali,
   labda nélküli játékosok időnként kicsúsznak → őket becsülni kell.

## Pipeline (1. fázis)

```
videó
  │
  ├─[A] Kalibráció ──────────────────────────────────────────────┐
  │     - kézi referencia-kalibráció (pályavonal-metszéspontok)   │
  │     - frame→referencia homográfia (auto)                      │
  │                                                                ▼
  ├─[B] Detektálás ──→ [C] Követés ──→ [D] Csapatba sorolás ──→ [E] Pálya-koord.
  │     YOLO            ByteTrack         mezszín-klaszter        homográfiával
  │     (játékos+labda) + ReID                                    (m-ben)
  │                                                                │
  ├─[F] Képen kívüli becslés ◄────────────────────────────────────┤
  │     - dinamikus létszám-állapot (5/6/7 fő, nem fix!)           │
  │     - kiállítás / 7. mezőnyjátékos kezelése                    │
  │     - szerep-/formációmodell + mozgáspredikció                 │
  │     - bizonytalanság-jelölés                                   │
  │                                                                ▼
  └─[G] Tracking objektum ──→ [H] Statisztikák ──→ [I] 2D vizualizáció
        (lásd ARCHITECTURE)      táv/sebesség/hőtérkép   felülnézeti animáció
```

## Komponensek részletei

### [A] Kalibráció
- **Kézi lépés** (egyszeri): kis UI, ahol a referencia-képen rákattintunk a
  pálya ismert pontjaira (vonalmetszések, kapuk, középvonal). Ebből homográfia a
  valós pálya (40×20 m) koordinátáira.
  - **Állapot: a homográfia-matematika KÉSZ és tesztelt** (tiszta Python, lásd
    `backend/handball/pipeline/_homography.py` és `calibration.py`). A pálya
    ismert pontjai: `standard_court_landmarks()`. Hátravan: a kattintós UI a
    Flutter-kliensben.
- **Auto propagáció**: minden frame homográfiája a referencia-nézethez
  jellemzőpont-illesztéssel (ORB/SIFT) vagy pályavonal-illesztéssel. Pásztázásnál
  ez folyamatos. *(Ez a videós rész még TODO — OpenCV kell hozzá.)*

### [B] Detektálás
- Előtanított YOLO (Ultralytics) játékos- és labdaosztályra. Finomhangolás
  kézilabda-adattal később.
- **Belógó / pályán kívüli dolgok kiszűrése** (KÉSZ és tesztelt, lásd
  `backend/handball/pipeline/roi.py`): amit nem szabad játékosnak venni —
  - **kép-térben**: fix *kizárási zónák* a belógó tárgyakra (pl. a pálya fölé
    lógó kosárpalánk, lógó kamera, reklámtábla); az ezekbe eső detektálást
    eldobjuk;
  - **méter-térben**: a *játéktér-régió* (40×20 m + tűréssáv); ami ezen kívülre
    vetül (lelátó, kispad, nézők), azt eldobjuk.
  A program ezeket úgy kezeli, mintha ott sem lennének.

### [C] Követés + ReID
- ByteTrack/BoT-SORT a stabil ID-khez.
- **ReID**: megjelenés-embedding, hogy a képbe visszatérő játékos visszakapja az
  ID-ját (a részleges láthatóság miatt kulcsfontosságú).
- **Mezszám-OCR** (a szabálykönyv szerint háton min. 20 cm, 1–99): ahol olvasható
  a szám, az a legerősebb ReID-jel — a megjelenés-embedding mellett ezt is
  használjuk a visszatérő játékos azonosításához.

### [D] Csapatba sorolás
- Mezszín-klaszterezés (k-means a bbox színhisztogramján), kapus külön kezelve.

### [E] Pálya-koordináta
- A homográfiával minden detektált játékos láb-pontját pálya-koordinátára (m)
  képezzük.

### [F] Képen kívüli becslés (a "teljes csapat" döntés magja)
- **Dinamikus létszám-állapot** (NEM fix 7 fő): az aktuális pályán lévő létszámot
  csapatonként követjük, mert ez változik:
  - **Kiállítás**: a csapat ideiglenesen kevesebb. Általános eset, NEM egy
    ki-be kapcsoló:
    - **több játékos** is lehet egyszerre kiállítva (a létszám több fővel is
      csökkenhet egyidejűleg),
    - a büntetés **2 vagy 4 perc** (a 4 perc két 2 perc; piros lap esetén a
      játékos véglegesen kiáll, de a csapat 2 percig hiányos).
    - Modellben: **kiállítás-intervallumok listája** csapatonként (kezdet +
      időtartam 2/4 perc), akár átfedéssel. A pillanatnyi létszám = alaplétszám
      − épp aktív kiállítások (alsó korlát: a meccset min. 5 fővel kell játszani).
    - Megkülönböztetni a "képen kívül van" esettől nehéz pásztázó kameránál,
      ezért MVP-ben **kézi/külső jelölés** oldja fel (felviszed a kiállítás
      kezdetét és hosszát); auto-felismerés a 2. fázisban (eseményfelismerés).
  - **7. mezőnyjátékos a kapus helyett**: nincs kapus, helyette 7 mezőnyjátékos
    (üres kapu). Jelzés: a **kapus mezszíne** eltűnik a pályáról (a kapus eltérő
    színt visel, ezt a csapatba sorolás úgyis külön kezeli) + 7 mezőnyjátékos.
  - A létszám csak ezen evidenciák ismeretében ad korlátot a becsléshez — nem
    feltételezünk fix 7-et.
- **Mozgásmodell**: a hiányzó játékost az utolsó látott helye + becsült sebessége
  alapján extrapoláljuk, a pálya határaira vágva.
- **Bizonytalanság**: a becsült pozíció megbízhatósága az idővel (felezési idővel)
  csökken; a vizualizációban halványítva, hibakörrel jelenik meg. Mért ≠ becsült.
- **Állapot: a mozgásmodell-alapú becslés KÉSZ és tesztelt** (egyenes vonalú
  extrapoláció + sebesség-elhalás + confidence-csökkenés + határvágás; lásd
  `backend/handball/pipeline/estimation.py`). Hátravan: a szerep-/formációmodell
  (a tipikus pozíció szerinti finomítás) — későbbi bővítés.

### [G] Tracking objektum
- A központi adatmodell (`ARCHITECTURE.md`), most kiegészítve mezőkkel:
  `players[].source ∈ {measured, estimated}` és `players[].confidence`.

### [H] Statisztikák
- Futott táv, pillanatnyi/átlag sebesség, hőtérkép — játékosonként és csapatonként.
- A becsült szakaszok a statisztikákban megjelölve (hogy ne hamisítsák az adatot).

### [I] 2D vizualizáció
- Felülnézeti pálya, mozgó pontok (mért = tele, becsült = halvány), labda,
  lejátszható idővonal.

## Sikerkritérium (mikor kész az MVP)
Egy pásztázó-kamerás meccsvideóból:
1. mindkét csapat + labda felülnézeti animációja lejátszható,
2. a látható játékosok követése stabil (ID-tartás ReID-del),
3. a képen kívüli játékosok becsült pozíciója megjelenik bizonytalanság-jelöléssel,
4. alap statisztikák (táv, sebesség, hőtérkép) generálódnak.

## Nyitott kérdések a megvalósítás előtt
- **Nyelv/stack véglegesítése**: Python + Ultralytics + OpenCV (javasolt).
- **Tesztvideó**: kell egy konkrét pásztázó-kamerás meccsfelvétel a fejlesztéshez.
- **Kalibráló UI formája**: különálló kis eszköz vs. notebook-cella (MVP-hez
  notebook/egyszerű script is elég).
