# Vízió — Kézilabda elemző AI

## Mit akarunk építeni

Egy videó- (és később LiDAR-) alapú elemző platform kézilabdára, amely:

1. **Csapatstílust tanul** — videók alapján megérti, hogy egy csapat milyen
   figurákat (set play-eket) játszik, hogyan védekezik (6-0, 5-1, 3-2-1 stb.),
   milyen tempóban játszik, mennyi a lerohanások aránya.
2. **Játékosokat elemez egyenként** — döntéshozatal: adott szituációban a játékos
   hányszor passzol/lő/cselez, és mi lett volna a *legjobb* megoldás (várható
   értékek alapján).
3. **Szimulál** — az edző megtervez egy figurát, és a program lejátssza egy adott
   ellenfél tanult stílusa ellen.
4. **3D / VR** — LiDAR-ral felvett meccs 3D-ben bejárható, akár VR-ban a csapat
   "bemehet" a pályára, az edző a helyszínen mutatja a szituációt.
5. **Élő meccskövetés** — valós idejű elemzés és javaslatok az edzőnek
   (mit játsszon, kit cseréljen).

## Miért nehéz (őszintén)

Ez nem egy projekt, hanem 5-6 egymásra épülő termék. A sorrend kritikus, mert
mindegyik az előzőre épül:

- A **3D/VR és az élő javaslat a csúcs** — de értelmetlen addig, amíg nincs
  megbízható 2D követés és eseményfelismerés.
- A legnagyobb akadály nem a modell, hanem az **adat**: címkézett kézilabda
  videó, pálya-kalibráció, esemény-annotáció. Cold start probléma.
- A "mi lett volna a legjobb döntés" kérdéshez egy **kézilabdára szabott
  várható-érték modell** kell (mint a futballban az xG/EPV), ami önmagában
  kutatási feladat.

Ezért az útiterv (lásd `ROADMAP.md`) alulról építkezik: előbb a megbízható
észlelés, aztán a taktikai értelmezés, és csak a végén a szimuláció és VR.

## Célfelhasználó

Elsősorban **edzők** és **elemzők**. A felület nyelve a taktika: figurák,
védekezési formák, pozíciók, döntések — nem nyers koordináták.

## Mit tud majd a szoftver — teljes funkció-lista

Az alapító összefoglalója (2026. november). Ez a VÉGCÉL leírása, nem a
mostani állapoté — a sorrendet a `ROADMAP.md` adja. Alapelv: **minden adat
mögött ott a klip** — az edző nem csak számot lát, hanem egy kattintással
meg is nézi, mi történt (később 3D-ben és VR-ban is).

1. **Meccs-feldolgozás** — a meccs felvételéből automatikusan statisztikát
   készít; kiválogatja és kivágja a lövéseket és a fontos játékhelyzeteket.
2. **Játékos-adatbázis — minden játékosnak saját lapja** (pl. "a 23-as"):
   - lövések: honnan lőtt, a kapu melyik részére, melyik kézzel, milyen
     lövőcselből;
   - ziccerek: milyen lövőcselből és hova lőtt, amikor ziccerbe került;
   - cselek: hol, milyen csellel, melyik védő ellen ment át, és hol nem
     sikerült (párharc: támadó × védő);
   - védekezés: hogyan védekezik, mennyire agresszív;
   - minden tételhez klip.
3. **Kapus-adatbázis** — minden kapott gól és védés klippel, szöveges
   leírással: hogyan kapta a gólt, hogyan védett.
4. **Figura-könyvtár** — az AI felismeri a csapat figuráit; minden figurán
   belül külön látszik az összes változat, ahogy lejátsszák, és a
   végkimenetele (gól, védés, eladott labda, hetes) — minden esethez klip.
   Pl. "Kereszt: 10-szer, 4 változatban; 1. változat: beálló-befejezés →
   3 gól, 1 védés (4 klip)".
5. **Játékos- és csapatszimuláció** — sok meccsből megtanulja, melyik
   játékos milyen helyzetben hogyan dönt; szimulálja az egyes játékosokat és
   az egész csapatot. Az edző kipróbálhatja a taktikáját egy adott ellenfél
   ellen; megmutatja az ellenfél erősségeit, gyengeségeit, játékstílusát.
   (Szimulátor, nem meccsterv: a döntés az edzőé.)
6. **Élő segítség** — a mérkőzés közben javaslatot ad az edzőnek.
7. **3D és VR** — a jeleneteket 3D-ben újraépíti, és **bármelyik poszt
   szemével** megnézhetők VR-ban (pl. a kapus látja, hogyan lő egy ellenfél,
   milyen magasra ugrik, mennyit vár ki; a játékos előre átélheti a meccset,
   a szimulációt). A játékos-lapok, a kapus-adatbázis és a figura-könyvtár
   klipjei is megnézhetők 3D-ben és VR-ban.
8. **Játékvezetői videózás** — bármilyen szögből visszanézhető eset, így
   megszűnik a rossz kameraszög gondja. A pálya köré több kamera és
   LiDAR-szenzor kerül.
9. **Más sportágak** — a rendszer kiterjeszthető más sportokra is.
