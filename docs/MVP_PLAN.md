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
  │     - roster constraint (7 fő/csapat)                          │
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
- **Auto propagáció**: minden frame homográfiája a referencia-nézethez
  jellemzőpont-illesztéssel (ORB/SIFT) vagy pályavonal-illesztéssel. Pásztázásnál
  ez folyamatos.

### [B] Detektálás
- Előtanított YOLO (Ultralytics) játékos- és labdaosztályra. Finomhangolás
  kézilabda-adattal később.

### [C] Követés + ReID
- ByteTrack/BoT-SORT a stabil ID-khez.
- **ReID**: megjelenés-embedding, hogy a képbe visszatérő játékos visszakapja az
  ID-ját (a részleges láthatóság miatt kulcsfontosságú).

### [D] Csapatba sorolás
- Mezszín-klaszterezés (k-means a bbox színhisztogramján), kapus külön kezelve.

### [E] Pálya-koordináta
- A homográfiával minden detektált játékos láb-pontját pálya-koordinátára (m)
  képezzük.

### [F] Képen kívüli becslés (a "teljes csapat" döntés magja)
- **Roster constraint**: csapatonként 7 fő pályán → mindig tudjuk, hányan
  hiányoznak a képből.
- **Szerep-/formációmodell**: a hiányzó játékost a szerepe szokásos pozíciója +
  utolsó látott hely + mozgásirány alapján becsüljük.
- **Bizonytalanság**: a becsült pozíció megbízhatósága az idővel csökken; a
  vizualizációban halványítva, hibakörrel jelenik meg. Mért ≠ becsült.

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
