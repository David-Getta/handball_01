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
