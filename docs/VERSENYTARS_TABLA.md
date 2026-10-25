# Versenytárs-tábla — kvalitatív összevetés

A pitch deck 7. diájának alapja (`docs/PITCH_DECK_VAZLAT.md`).
Szándékosan KVALITATÍV: az árak és funkciók gyorsan változnak, ezért a
beadás előtt friss ár-ellenőrzés kell (⬜) — itt a szerkezeti
különbségek vannak rögzítve, amik nem változnak könnyen.

| Szempont | Veo | Hudl (Sportscode/Focus) | Spiideo | Catapult | **SportMachine** |
|---|---|---|---|---|---|
| Fő szegmens | amatőr/félprofi foci-fókusz | profi klubok, elemzők | profi/felsőházi klubok | profi, viselhető szenzor | **amatőr/utánpótlás kézilabda (hosszú farok)** |
| Hardver-igény | saját kamera kötelező | kamera + elemzői munka | telepített kamera-rendszer | szenzor-mellény játékosonként | **nulla — meglévő telefon/kamera** |
| Felhő-függés | videó felhőbe megy | jellemzően felhő | felhő | felhő | **helyben fut, nincs feltöltés** |
| Kiskorú-adatvédelem | feltöltés-függő | feltöltés-függő | feltöltés-függő | személyes szenzoradat | **eszközön marad (GDPR-barát)** |
| Kézilabda-specifikus szabály-értés (kiállítás, hetes, passzív, 7a6) | nincs | kézi címkézéssel | nincs | nincs | **automatikus, követési adatból** |
| Taktikai kimenet | klipek, alap-statok | elemzői munkaeszköz | klipek, statok | terhelés-adatok | **kész edzői ítéletek: meccsterv, felderítés, edzés-fókusz** |
| Elemzői munkaigény | edző vágja | dedikált elemző kell | elemző kell | sporttudós kell | **nulla — a jelentés magától készül** |
| Magyarázhatóság | fekete doboz | emberi elemzés | fekete doboz | nyers adat | **minden ítélet mögött kimondott küszöb** |
| Nyelv | EN | EN | EN | EN | **magyar edzői nyelv (EN bővítés tervben)** |

**A pozicionálás egy mondatban:** a versenytársak videót vagy nyers
adatot adnak, amihez elemző kell — a SportMachine kész edzői
döntés-támogatást ad ott, ahol elemzőre soha nem lesz keret.

**Védhető különbségek** (Excellence-érv): egykamerás pásztázó
kalibráció + képen kívüli becslés; szabály-értő réteg (bírói döntések
lenyomata követésből); teljesen helyi, magyarázható lánc; "kevés minta
→ nincs ítélet" megbízhatósági elv.

## Frissítés (2026. október): a kézilabda-piac szereplői

A fenti tábla az általános (főleg futball-) szereplőkkel vet össze. A
kézilabdában közben megjelentek a SZAKÁGI szereplők — közülük több a mi
"automatikus kézilabda-elemzés" ígéretünkhöz közelebb van, mint a Veo
vagy a Hudl. A forrás többnyire a cégek saját közleménye (független
mérést nem találtunk); árat egyik sem közöl nyilvánosan.

| Szereplő | Mit ad | Kinek / hol | Mihez kell |
|---|---|---|---|
| **Handball.ai** | automatikus videó-címkézés, esemény-felismerés, statisztika | EHF-partner (EURO, Bajnokok Ligája, 2026/27-ig), lengyel Superliga | profi szint, felhő |
| **Spiideo AutoData (kézilabda)** | bármilyen forrású videóból <24 óra alatt adatbontás (lövés, gól, pozíció, kiállítás) | izlandi szövetség: 20 csarnok, 50+ AI-kamera | Spiideo-platform, felhő |
| **Pixellot** | több kamerás AI-közvetítés + alap elemzés | portugál szövetség felső ligái; Magyarországon a jégkorong-szövetség (2021) | telepített kamera |
| **Sideline Sports — XPS Network** | videó-elemzés, statisztika, edzéstervezés (elemzői munkaeszköz) | MINDEN HBL-klub (18 + 13), svéd liga (2025/26-tól), lengyel Superliga, japán és macedón szövetség | elemző / edzői munka |
| **Kinexon** | szenzoros játékos- és labdakövetés | a HBL összes meccse (2028/29-ig), EHF EURO-k | telepített rendszer + szenzor |
| **Veo / XbotGo** | panoráma vagy követő AI-kamera | amatőr klubok (Veo focira hangolt) | saját kamera |
| **Nacsport, Once Sport Analyser, Hudl Sportscode, Dartfish, LongoMatch, Kinovea** | kézi címkézés, klipek (Once: automatikus követés is) | klubelemzők | elemzői munka |

**Mit jelent ez nekünk.**

- A profi szint FOGLALT: a felső ligákat a szövetségi szerződések
  (Kinexon, Handball.ai, XPS, Pixellot) lefedik. Oda nem érdemes
  belépni.
- Az "AI kézilabda-elemzés" már NEM egyedi állítás (Handball.ai,
  Spiideo AutoData). A megkülönböztetés a SZEGMENS és a MŰKÖDÉS:
  amatőr / utánpótlás / NB II–III, nulla hardver (meglévő telefon vagy
  kamera), helyben fut (a kiskorúak videója nem megy felhőbe), magyar
  edzői nyelvű kész ítélet (meccsterv, felderítés, edzés-fókusz), és
  minden ítélet mögött kimondott küszöb.
- A Spiideo AutoData "bármilyen forrású videó" ígérete a mi "meglévő
  kamera" érvünk közvetlen párja — a különbség a felhő és az ár (és
  hogy ott emberi utófeldolgozás is lehet a 24 órában). Ezt a
  pályázatban ki kell mondani, nem elhallgatni.
- Az XPS a klubok MUNKAESZKÖZE (naptár, edzésterv, videó). Ellenfélnél
  hasznosabb partnernek látni: a mi kimenetünk (klip-csomagok, jelentés)
  XPS-be exportálva a meglévő munkafolyamatba illeszkedhet.
- Magyarországon az MKSZ-nek nyilvános automata-kamera vagy elemző
  szerződését nem találtuk — a hazai alsóbb osztályok nyitottak.

## Árszegmensek (2026. október, nyilvános források)

Tájékoztató: sok szereplő csak egyedi ajánlatot ad; a régi adatok
évszámmal; ÁFA nélkül, vegyes pénznemben.

| Szegmens | Szereplők | Ár (ahol nyilvános) |
|---|---|---|
| **Prémium** — telepített rendszer, szövetségi/liga-szerződés | Kinexon, Handball.ai, Spiideo (kamera + AutoData), Pixellot (több kamerás) | egyedi ajánlat; Pixellot-egység az USA-iskolákban 2018–21: ~2 500–4 950 $ egyszeri |
| **Felső-közép** — elemzői munkaeszköz | Hudl Sportscode (csak éves licenc, macOS), Sideline XPS, Dartfish, Nacsport Pro/Elite | ajánlatra |
| **Közép** — automata kamera előfizetéssel, amatőr klub | Veo (Starter / Team / Club), Hudl csapat-videó, Nacsport Scout, Once Sport Analyser | Veo 119 / 199 / 239 $/hó (+ kamera); Hudl Bronze 400 $/csapat/év; Nacsport Scout 595 £/év |
| **Alsó** — ingyenes – pár száz € | Kinovea, Nacsport Basic / Basic+, XbotGo | Kinovea ingyenes; Nacsport 125 / 240 £/év; XbotGo Falcon ~600 $ egyszeri |

**A rés:** automatikus, kézilabda-specifikus elemzést és kész edzői
ítéletet ma csak a PRÉMIUM szint ad; az alsó és a közép szegmens
kamerát vagy kézi címkéző eszközt ad (a munka az edzőnél marad). A
SportMachine helye: alsó–közép ár, prémium tartalom — új hardver és
elemző nélkül.

⬜ Beadás előtt: ajánlatkérés a Handball.ai-tól és a Spiideótól (a két
legközelebbi szereplő, áruk nem nyilvános), és kipróbálásuk egy NB
II-es meccsfelvételen.
