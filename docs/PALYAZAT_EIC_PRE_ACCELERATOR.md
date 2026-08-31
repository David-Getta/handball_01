# EIC Pre-accelerator pályázat — felkészülési terv a SportMachine-hez

Cél: a SportMachine (egykamerás, MI-alapú kézilabda-elemző) benyújtása az
EU **EIC Pre-accelerator** programjára — ez a "widening" országok
(köztük Magyarország) deep-tech KKV-inak belépő programja, és egyben a
legjobb ugródeszka a nagy EIC Accelerator felé (arról külön terv:
`docs/PALYAZAT_EIC.md`).

Hivatalos oldal:
https://eic.ec.europa.eu/eic-funding-opportunities/eic-pre-accelerator_en

---

## 1. Mit ad a program?

- **Vissza nem térítendő támogatás: 300 000 – 500 000 €** projektenként.
- **Támogatási ráta: az elszámolható költségek 70%-a** — a maradék 30%
  önerő (saját forrás)! Ezt a pénzügyi tervben előre be kell mutatni.
- Futamidő: **legfeljebb 2 év**; a teljes keret ~20 M€.
- Cél: a technológia **TRL 4-ről TRL 5–6-ra** vitele (releváns
  környezetben történő validálás), plusz befektetés- és piac-érettség.
- Ráadás: hozzáférés az **EIC Business Acceleration Services**-hez
  (mentorálás, coaching, befektetői és vevői kapcsolatok) — és a
  program deklarált kimenete a **felkészítés az EIC Acceleratorra**.

## 1/b. A mi célunk: beadás 2027. május 5-től, 500 000 – 1 000 000 €

- **Cél-dátum: 2027. május 5-től pályázunk** — a 2027-re várt
  felhívásra készülünk, minden akcióterv-határidő ehhez igazítva
  (lásd 6. pont).
- **Cél-keret: 500 000 – 1 000 000 € összköltségű projekt.** Fontos a
  program-korlát: a Pre-accelerator **grant-plafonja 500 000 €**, a
  támogatási ráta 70%. A sáv így értelmezhető:
  - **500 k€ grant** (a plafon) + 30% önerő → **~714 k€
    összköltségvetésű projekt** — ez a fő terv;
  - ha a cél az 1 M€ felé nyújtózik, a különbözetet önerő/befektetés
    fedezi, VAGY a nagyobb igényt a következő lépcső, az **EIC
    Accelerator** (max. 2,5 M€ grant — `docs/PALYAZAT_EIC.md`) viszi.
- A pénzügyi tervet (6. pont) a maximális, 500 k€-s grantra és
  ~714 k€ összköltségre méretezzük, 24 hónapra.

## 2. Ki pályázhat? (jogosultsági ellenőrzőlista)

| Feltétel | Állapot nálunk |
|---|---|
| **Egyetlen jogi személy** pályázik (mono-beneficiary, nincs konzorcium) | ✔ illik a helyzethez |
| **Deep-tech KKV vagy small mid-cap**, "widening" országban bejegyezve — **Magyarország a listán van** ✔ | ⬜ **cég kell hozzá** — cégforma nélkül nem adható be |
| A technológia **TRL 4-en validált** (laborban igazolt működés) | 🟡 közel — lásd a 4. pont TRL-önértékelését |
| A szükséges **szellemi tulajdonjogok (IPR)** a pályázónál vannak | ⬜ tisztázandó: a kódbázis és a védjegy a leendő cég tulajdonába kerüljön |
| 30% **önerő** igazolhatóan rendelkezésre áll | ⬜ pénzügyi terv része |

**Első teendő: cégalapítás** (magyar KKV), és a szellemi tulajdon
(kód, név, logó) apportálása/átruházása a cégbe.

## 3. A pályázás menete és állása

- Beadás a **EU Funding & Tenders portálon** (EU Login szükséges), a
  HORIZON-WIDERA munkaprogram alatt futó felhívásra, a portál
  **standard űrlapjával** (Part A adminisztratív adatok + Part B
  szakmai rész).
- Értékelés: **3 független szakértő**, három kritérium mentén:
  - **Excellence** — technológiai újdonság + kereskedelmi potenciál,
  - **Impact** — hitelesség, skálázási potenciál, EU-hozzáadott érték,
  - **Implementation** — csapat, mérföldkövek, KPI-k, kockázatkezelés,
    erőforrás-allokáció.
- Határidők: a legutóbbi felhívás **2025. november 18-án** zárult; a
  2026–27-es munkaprogram-tervezet szerint a következő felhívás
  **2027-ben** várható. Ez nekünk jó: van idő a TRL-bizonyítékok és a
  cég felépítésére. A felhívás-figyelést az NKFIH NCP hírlevelével és a
  Funding & Tenders portál értesítőjével oldjuk meg.

## 4. TRL-önértékelés — hol tartunk, mit kell igazolni

A Pre-accelerator belépője a **validált TRL 4**, a projekt vége TRL 5–6.

| TRL | Jelentés | SportMachine-bizonyíték ma |
|---|---|---|
| TRL 3 | kísérleti proof-of-concept | ✔ a teljes pipeline szimulált meccseken end-to-end működik |
| **TRL 4** | **laborban validált technológia** | 🟡 erős alap: 2197 automata teszt (élő szám: `docs/SZAMOK.md`), reprodukálható benchmark (`python -m scripts.benchmark`), beépített validációs modul (precision/recall/F1 az eseményfelismerésre — `pipeline/validation.py`), minőség-önellenőrzés. **Hiányzik: kézzel annotált VALÓS meccsfelvételeken mért, dokumentált pontosság.** |
| TRL 5 | releváns környezetben validált | ⬜ a projekt tárgya: valós felvételek + pilot-klubok |
| TRL 6 | releváns környezetben demonstrált | ⬜ a projekt tárgya: több klubos, szezonon átívelő pilot |

**A beadás előtti kulcs-feladat a TRL 4 lezárása valós adaton:**

1. ⬜ **Annotált valós-videó teszthalmaz**: 3–5 teljes meccs felvétele,
   kézi esemény-annotációval (gól, lövés, hetes, kiállítás, csere).
2. ⬜ A meglévő validációs modul lefuttatása ezeken → **publikálható
   precision/recall tábla** verziónként (a benchmark-infrastruktúra
   már megvan, csak valós adat kell alá).
3. ✅ **Lövő-hozzárendelés kapu-felé torzítása — javítva.** Mért,
   ismert korlát volt: a lövés-eseményt a labda kapu-megközelítésekor
   jelöljük, ezért a puszta "legközelebbi játékos" szabály a távolról
   elengedett lövéseket a kapuhoz közeli játékoshoz írta (szimulált
   ellenőrzésben 12 méterről elengedett lövések MIND a 6 méteren álló
   játékoshoz kerültek). A visszakeresés mostantól kihagyja azokat a
   kockákat, ahol a labda sebessége lövés-szintű — így az elengedés
   pillanatát találja meg, és a lövés a valódi lövőhöz kerül. A
   javítás a JÁTÉKOS- és POSZT-bontású lövés-rétegek mindegyikét
   érinti; a csapat-szintű számok változatlanok. Valós videón a
   pontosságát a fenti annotált teszthalmazon kell megmérni.
4. ⬜ Az eredmények beépítése a `docs/FOOTAGE_NOTES.md` /
   `MVP_PLAN.md` vonalába, dátumozott mérési jegyzőkönyvként.

## 5. A pályázati sztori (Excellence / Impact / Implementation)

**Excellence — miért deep-tech és miért új:**
- egyetlen pásztázó kamerából teljes taktikai elemzés (kalibráció +
  képen kívüli becslés + egykamerás labdakövetés kombináció);
- **szabály-értő réteg**: a bírói döntések (kiállítás, hetes, passzív)
  lenyomatának felismerése követési adatból — a piacon egyedülálló;
- **magyarázható MI-lánc**: minden ítélet mögött kimondott küszöb és
  visszakövethető szabály (AI Act / GDPR szempontból is érv);
- **503 elemző réteg** és **2197 automata teszt** — mérhető, verziók
  közt összevethető minőség ("kevés minta → nincs ítélet" elv). A
  számok a kódbázisból generáltak és őr-teszttel frissen tartottak:
  `docs/SZAMOK.md` (tény-lap) + `docs/RETEG_KATALOGUS.md`
  (rétegenkénti tételes lista) — az értékelő ellenőrizni tudja.

**Impact — piac és skálázás:**
- a sportanalitika ma a profi kluboké (Veo, Hudl, Spiideo, Catapult:
  többkamerás/szenzoros, drága); a **hosszú farok** (utánpótlás,
  iskolák, alsóbb osztályok — EU-szerte több százezer csapat)
  kiszolgálatlan;
- nulla extra hardver (egy telefon/kamera), **helyben futó MI** —
  nincs videófeltöltés, kiskorú-adatvédelem, alacsony költség;
- kézilabdával indulunk (EU-erős sport, magyar referenciákkal), a
  pipeline sportfüggetlen → kosárlabda, futsal, jégkorong skálázás;
- widening-érv: magyar deep-tech KKV, amely EU-szintű piacra visz
  exportképes sporttechnológiát.

**Implementation — a 2 éves projekt váza (300–500 k€, 70%):**
1. év: valós-videós validáció lezárása (TRL 4→5), pilot 3–5 magyar
klubbal, követés-robusztusság éles csarnok-körülmények közt;
2. év: szezonon átívelő, több klubos demonstráció (TRL 6), termékesítés
(telepítő, licenc, támogatás), első fizető ügyfelek + felkészülés az
EIC Acceleratorra (pitch, FTO, LOI-k). KPI-k: annotált pontosság-célok,
pilot-klubok száma, elemzett meccsek száma, fizető licencek.

## 6. Teendők a beadásig (akcióterv)

1. ⬜ **Cégalapítás** (magyar KKV) + IPR a cégbe.
2. ⬜ **TRL 4 lezárása valós adaton** (4. pont 1–3. lépése) — ez a
   legfontosabb szakmai feltétel.
3. ⬜ **Pilot-előkészítés**: 3–5 klub megkeresése, szándéknyilatkozat
   (LOI) sablonnal (lásd `docs/PILOT_PLAN.md`).
4. ⬜ **30% önerő terve** (tagi kölcsön / árbevétel / befektető).
5. ⬜ **Part B vázlat** angolul az Excellence/Impact/Implementation
   szerkezetben (az 5. pont a magja; angol összefoglaló:
   `docs/EXECUTIVE_SUMMARY_EN.md`).
6. ⬜ **Pénzügyi terv** 2 évre, munkacsomagokkal és KPI-kkal.
7. ⬜ Felhívás-figyelés (NKFIH NCP + Funding & Tenders értesítő), és
   **beadás 2027. május 5-től** az akkor nyitott felhívásra.

**Visszafelé ütemezve a 2027. május 5-i cél-dátumtól:**

| Mikorra | Mi legyen kész |
|---|---|
| 2026 Q4 | cégalapítás + IPR a cégben; annotált valós-videó mérések futnak (mérési jegyzőkönyv telik) |
| 2027 Q1 | TRL 4 lezárva valós adaton; 3–5 pilot-klub LOI aláírva (`docs/LOI_SABLON.md`) |
| 2027. március | Part B kész angolul (`docs/PART_B_VAZLAT_EN.md` kitöltve), pénzügyi terv 500 k€ grantra + önerő-igazolás |
| 2027. április | NCP-vel átnézetés, portál-regisztráció (EU Login, PIC-szám), próba-feltöltés |
| **2027. május 5.** | **beadás** |

## 7. Kapcsolódó dokumentumok és források

- EIC Accelerator terv (a következő lépcső): `docs/PALYAZAT_EIC.md`
- Pilot-terv: `docs/PILOT_PLAN.md` · MVP-terv: `docs/MVP_PLAN.md`
- Angol projekt-összefoglaló: `docs/EXECUTIVE_SUMMARY_EN.md`
- Hivatalos program-oldal:
  https://eic.ec.europa.eu/eic-funding-opportunities/eic-pre-accelerator_en
- Program-GYIK:
  https://eic.ec.europa.eu/eic-frequently-asked-questions/faqs-eic-pre-accelerator_en
- Magyar NCP (NKFIH, Horizont Európa): ingyenes pályázat-előkészítési
  tanácsadás.
