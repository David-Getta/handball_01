# 2. meccs — kiolvasható-e a lövő mezszáma? (első próba)

Kiértékelő halmaz emberi munka nélkül: a ticker (`meccs2_ticker.md`) minden
gólnál megadja a szerzőt, a keret a mezszámát. Kód: `hbd/jersey.py`.

**Módszer.** A gól előtti 6 s (−6 … −0,5 s az állásváltozás előtt) póz-kockáin
(5 Hz) minden ember törzsét (váll–csípő, legalább 35 px magas) kivágjuk, és
előtanított OCR-rel (EasyOCR, csak számjegy, 1–2 jegy) olvassuk. A gólt szerző
csapat keretében szereplő számokat a megbízhatóság összege szerint
rangsoroljuk. A csapatszín változatban csak a csapat mezszínén olvasott számok
számítanak. A színcsoportot a keret-számok olvasata rendeli a csapathoz; a
szerzőt ehhez nem használja.

| 68 gól | a szerző száma egyáltalán olvasva | 1. helyen | top-3 | véletlennel 1. (az olvasott gólokon) |
|---|---|---|---|---|
| csapatszín nélkül | 45 | 16 | 33 | ~10 |
| csapatszínnel | 30 | 19 | 29 | ~13 |
| csak felismerő, szövegkeresés nélkül (`--fast`) | 22 | 1 | 15 | — |

## Olvasat

- **A számok olvashatók.** A gólok kétharmadánál (45/68) a szerző száma a
  gól előtti 6 s-ban legalább egyszer kiolvasható. Szemmel a törzs-kivágások
  nagy részén is olvasható a szám.
- **A lövőt viszont így nem azonosítja.** A rangsor első helye alig jobb a
  véletlennél (16 vs ~10; csapatszínnel 19 vs ~13). Az ok egyszerű: a módszer
  MINDEN ember számát olvassa a képen, és a 6 s alatt a társak és a védők
  száma ugyanannyiszor látszik, mint a lövőé.
- **A csapatszín-szűrés** kevés jelöltre szűkít (átlag 2,5), de a gólok
  felénél (38/68) a szerzőt is kidobja. A színcsoportok (Lab medián, 4
  csoport) a fehér vendégmezen és az árnyékos törzseken még bizonytalanok.

## Következő lépés

A számot a LÖVŐ törzsén kell olvasni, nem mindenkién: a lövő kiválasztása
(`shooter_ball`: testpont + labda, a lövő helye 72%) és a lövés pillanata (a
lövésfelismerő jelöltje) adja meg, kinek a hátát nézzük. Az OCR-t ezután
lehet a tickerből gyűjtött példákon finomhangolni (a gól → szerző → szám
párok ingyen vannak minden HBL-meccsre).

## Futtatás

    python -m hbd.jersey --video meccs.mp4 --pose m2_pose.npz --ticker cimkek/meccs2_ticker.json \
        --roster cimkek/meccs2_keret.json --cache jersey_cache --out mezszam.json

(CPU-n ~45 s/gól; az első változat ffmpeg-hibája miatt ~23 perc volt.)
