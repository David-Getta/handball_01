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

⬜ Beadás előtt: friss ár-táblázat (listaárak forrással), és a
kézilabda-piacra lépett új szereplők ellenőrzése.
