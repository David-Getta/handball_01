# Pásztázás-követés — a svenkelő kamera és a kalibráció

Egy rögzített helyről **jobbra-balra forgó** kamera képe elfordul, a
pálya-kalibráció (a 4 sarokból számolt homográfia) viszont EGY
képkockára érvényes. Kompenzálás nélkül a játékosok "odébb csúsznának"
a felülnézeten, pedig csak a kamera mozgott. Ez a lap azt írja le, hogyan
oldja meg a motor, és mit tehet a felhasználó a pontosságért.

## A képlet

```
pálya = H0( G(t) · pixel )
```

- **H0**: a kalibrált (alap) képkocka → pálya leképezés a 4 sarokból.
- **G(t)**: a t-edik kocka → alap-kocka leképezés — a kameramozgás.

A H0 a kalibrálásból jön; a G(t)-t a feldolgozás becsüli minden
feldolgozott kockára (`handball/pipeline/pan_tracking.py`).

## Két becslő — miért kettő?

1. **Lánc** (kockáról kockára). Shi–Tomasi sarokpontok az előző képen,
   Lucas–Kanade optikai áramlás az aktuálisra, RANSAC-os hasonlósági
   transzformáció, a lépések összeszorozva. Gyors, minden kockán megy —
   de a sok kis lépés hibája **összeadódik**: mire a kamera visszafordul a
   kalibrált állásba, a becslés elcsúszott (drift).
2. **Horgony** (a kalibrált képhez mérés). A kalibrált alap-kocka ORB
   jellemzőpontjait ("távpontjait": pályavonalak, lelátó, falak, reklám-
   táblák) eltároljuk, és a futó kockát rendszeresen — alapból minden
   5. feldolgozott kockán, és mindig, ha a lánc elakadt — **közvetlenül
   ehhez** illesztjük: Lowe-arányos párosítás + RANSAC homográfia,
   józansági szűrőkkel (nem zoom, nem tükrözés). Ez abszolút mérés, nem
   halmozódik benne hiba.

A kettő együtt: a horgony ad pontos állást, ahol van elég egyezés; a lánc
hidal át, ahol nincs (távoli svenk, takarás, sötét kép), és a következő
sikeres horgonynál a becslés visszaáll.

## Kulcs-horgonyok és a kalibrált kockák

A távolra elforduló kamera képe már alig fedi az alap-kockát — ott a
horgony nem talál egyezést. Ezért a sikeresen horgonyzott, egymástól elég
távoli (≥150 px) nézetekből **kulcs-horgonyok** készülnek a saját,
horgonyból származó G-jükkel; a futó kocka mindig a legközelebbi pár
horgonyhoz próbál illeszkedni.

**Minden bekalibrált képkocka kötelező horgony.** Ha a felhasználó két
kalibrációt vett fel (külön bal és jobb térfél, akár külön kockán), a
feldolgozás mindkettőt horgonynak veszi, amint eléri — pont azokra a
nézetekre lesz a legpontosabb a visszamérés, amiket ő jelölt be.

## A mozgó emberek kimaszkolása

A detektált játékos-dobozokat egyik becslő sem használja: csak az álló
háttér adja a kamera mozgását. (A RANSAC a kisebbséget amúgy is kiszórná,
de a tömörülésben a játékosok a képpontok jelentős részét adhatják.)

## Mit lát a felhasználó

- A feldolgozás naplója: `pásztázás-követés: N kocka — horgonyzott X,
  lánccal vitt Y, tartott Z; horgonyok: K`.
- A meccs meta-adata: `pan_anchor_pct` — a horgonyzott kockák aránya
  (%). A diagnosztika-JSON is viszi.
- A minőség-jelentés **8% alatt** figyelmeztet, és az első teendő
  megmondja, mit tegyen: a kalibrációt a meccs TIPIKUS kameraállásában,
  az ELSŐ feldolgozott kockára vegye fel (a kalibráló képernyő és a
  feldolgozás kezdőpontja ugyanaz a kocka).

## Tippek a pontos kalibrációhoz

- A 4 sarkot ahhoz a kockához vedd fel, amelyiktől a feldolgozás indul —
  a Meccs-hossz "a kezdőpontot a kalibrált képkocka adja" beállítás ezt
  garantálja.
- Ha a kamera a két térfél közt svenkel, vedd fel **mindkét térfél**
  kalibrációját (a saját kockáján) — mindkettő horgony lesz.
- Kerüld az olyan alap-kockát, ahol a kép nagy részét tömeg vagy egy
  közeli játékos takarja: a horgonynak álló háttér kell.
- A `docs/STRIDE_ERZEKENYSEG.md` szerint a "Pontos" profil (kisebb
  ritkítás) a horgonyt is sűrűbben engedi mérni.

## Tesztek

`backend/tests/test_pan_tracking.py`: ismert eltolás visszamérése, a
lánc halmozása, a horgony visszahozza a kalibrált állást (svenk oda-
vissza → ~egység), horgony közben is helyes az eltolás, a kimaszkolt
dobozokkal is megy a becslés, a kalibrált kocka kötelező horgony.
