# EIC Accelerator pályázat — felkészülési terv a SportMachine-hez

Cél: a SportMachine (egykamerás, MI-alapú kézilabda-elemző) benyújtása az
EU **EIC Accelerator** programjára.
Hivatalos oldal: https://eic.ec.europa.eu/eic-funding-opportunities/eic-accelerator_en

---

## 1. Mit ad a program?

- **Vissza nem térítendő támogatás (grant): max. 2,5 M€** — a TRL 6–8
  fejlesztési szakaszra (prototípustól a piacra vihető termékig).
- **Opcionális tőkebefektetés (equity): 1–10 M€** az EIC Fund-tól —
  összesen (blended finance) akár ~12,5 M€.
- Három forma: csak grant · grant + tőke (blended) · csak tőke.
- Plusz: Business Acceleration Services (coaching, partnerkeresés, vevő-
  és befektetői kapcsolatok).

## 2. Ki pályázhat? (jogosultsági ellenőrzőlista)

| Feltétel | Állapot nálunk |
|---|---|
| **Bejegyzett, profitorientált KKV** (max. 250 fő) EU-tagállamban vagy társult országban (Magyarország ✔) | ⬜ **cég kell hozzá** — egyéni fejlesztés cégforma nélkül NEM pályázhat |
| Egyetlen cég pályázik (nem konzorcium) | ✔ illik a helyzethez |
| A technológia **TRL 5-öt teljesített** (releváns környezetben igazolt) — a pénz a TRL 6–8-ra megy | ⬜ pilot-igazolások kellenek (lásd 5. pont) |
| „Nem banki finanszírozható" (high risk) breakthrough innováció | ⬜ ki kell dolgozni az érvelést |

**Első teendő, ha még nincs: cégalapítás** (a 2. lépcső beadásáig
mindenképp meg kell lennie).

## 3. A pályázás menete (2 lépcső + zsűri)

1. **Rövid pályázat (Step 1)** — folyamatosan beadható, havonta
   (minden hónap első keddjén) értékelik:
   - ~5 oldalas űrlap (mi a termék, miért áttörés, piac, csapat),
   - **pitch deck** (max. 10 dia),
   - **max. 3 perces videó** (a csapat mutatja be a víziót).
   - 4 értékelő GO/NO-GO döntése → GO esetén mehet a teljes pályázat.
2. **Teljes pályázat (Step 2)** — fix beadási határidőkkel. 2026-ban:
   **január 7., március 4., május 6., július 8., szeptember 2.,
   november 4.** (17:00 brüsszeli idő).
   - ~20 oldalas üzleti terv-szerű űrlap, megvalósítási terv,
     pénzügyi adatok/terv, szándéknyilatkozatok (LOI) vevőktől,
     **FTO-elemzés** (szabadalmi mozgástér), pitch deck, 3 perces videó.
3. **Zsűri-interjú** — a Step 2-n átjutók személyes/online pitch-e
   EIC-zsűri előtt (befektetők, vállalkozók). Itt dől el a támogatás.

Értékelési szempontok mindhárom körben: **Excellence** (áttörés-jelleg,
időzítés), **Impact** (piaci potenciál, skálázhatóság, EU-érdek),
**Implementation** (csapat, mérföldkövek, pénzügyi terv realitása).

## 4. Miért lehet erős a SportMachine sztorija?

- **Egyetlen pásztázó kamerából** teljes taktikai és terhelés-elemzés —
  a piaci megoldások (Veo, Hudl, Spiideo, Catapult) többkamerás fix
  telepítést, drága hardvert vagy viselhető szenzort igényelnek.
  A miénk: **nulla extra hardver**, egy edző telefonja/kamerája elég.
- **Megfizethető az amatőr/utánpótlás szegmensnek** — a sportanalitika
  ma a profi kluboké; a hosszú farok (iskolák, egyesületek, NB II –
  megye) kiszolgálatlan. Ez az EU-ban több százezer csapat.
- **Helyben futó MI** (nincs felhő-függés, nincs videófeltöltés) —
  adatvédelem (kiskorú játékosok!), GDPR-barát, alacsony költség.
- Kézilabdával indulunk (EU-erős sport, HU-referenciákkal), de a
  pipeline sportfüggetlen: kosárlabda, futsal, jégkorong ugyanazzal a
  motorral — skálázási történet.

- **Reprodukálható validációs benchmark** a repóban
  (`python -m scripts.benchmark`): a kalibráció, a képen kívüli becslés, az
  eseményfelismerés és a zaj-robusztusság számszerű, verziónként
  összevethető metrikái — az Excellence-kritérium "mérhető innováció"
  bizonyítéka, és egyben regresszió-őr a fejlesztésben.

**Gyenge pontok, amiket a zsűri kérdezni fog** (készüljünk):
- Mennyire „deep tech" ez a versenytársakhoz képest? → a válasz a
  pásztázó-kamerás kalibráció + képen kívüli becslés + egykamerás
  labdakövetés kombinációja (publikálható/szabadalmaztatható elemek).
- Bevétel-modell és eddigi trakció (fizető pilot, LOI-k).
- Miért nem finanszírozza bank/VC (non-bankability érv).

## 5. Teendők a beadásig (akcióterv)

1. ⬜ **Cégalapítás** (ha még nincs) — a Step 2-ig kötelező.
2. ⬜ **Pilot-program dokumentálása**: 3–5 klub/egyesület használja
   igazolhatóan (ez a TRL 5–6 bizonyíték) + **szándéknyilatkozatok
   (LOI)** tőlük. (Lásd: docs/PILOT_PLAN.md.)
3. ⬜ **Pitch deck** (10 dia): probléma → megoldás → demó → piac
   (TAM/SAM/SOM) → versenytárs-tábla → üzleti modell → csapat →
   pénzügyi terv → mire kell a pénz (use of funds) → mérföldkövek.
4. ⬜ **3 perces videó**: a csapat + élő termék-demó (a mostani app
   képernyőfelvételei: feltöltés → elemzés → jelentés).
5. ⬜ **FTO-elemzés** (szabadalmi ütközés-vizsgálat) — EU-s szolgáltatóval.
6. ⬜ **Pénzügyi terv** 3–5 évre (árazás, előfizetés-modell, költségek).
7. ⬜ Step 1 beadása a Funding & Tenders portálon (folyamatos) →
   GO esetén Step 2 a következő elérhető határidőre.

## 6. Reális ütemterv

- Step 1 anyagok (deck + videó + űrlap): ~1 hónap intenzív munka.
- Step 1 értékelés: ~havonta; GO után Step 2 kidolgozás: 2–3 hónap.
- Realisztikus cél-határidő a Step 2-re: **2026. november 4.** vagy a
  2027-es első cut-off — előtte pilot-referenciák gyűjtése.

## 7. Segítség

- Hivatalos pályázói útmutató (Version 6.0, 2025. nov.):
  https://eic.ec.europa.eu/document/download/9d96fbf3-4d85-4ad0-9483-c77ce348111d_en?filename=EIC+Accelerator+guide+for+applicants_WP26.pdf
- Nemzeti Kapcsolattartó Pont (NCP) Magyarországon: ingyenes
  pályázat-előkészítési tanácsadás (NKFIH — Horizont Európa NCP).
- A beadás a EU Funding & Tenders portálon történik (EU Login kell).
