# Lövésfelismerés két meccsen — mennyit ad a második meccs?

1. meccs: Veszprém–Flensburg (EHF BL, 25 fps), 108 élő lövés. 2. meccs:
Magdeburg–Füchse Berlin (HBL, ARD, 50 fps), 128 élő lövés. Mindkettő a
Meccsjelölővel jelölve; az ismétlések itt nem számítanak. Kód:
`tools/meccsek_kozt.py`.

Három tanítási mód, mindig ugyanazon a teszt-meccsen:

- **csak a másik meccs:** a teszt-meccsből semmi nincs a tanításban (vak átvitel);
- **csak ez a meccs:** 5 időblokkos keresztvalidáció a teszt-meccsen;
- **a másik + ez:** ugyanaz a blokkos CV, de a másik meccs egésze is mindig a
  tanításban.

A számok a küszöb-görbéről utólag választva (legjobb F1, illetve a 80%-os
felidézéshez tartozó pont): a módok összevetésére jók, nem egy rögzített
működési pontra. (A rögzített küszöbös vak eredmény: `meccs2_osszevetes.md`.)

## Póz + kamera (az eredményjelző-jelek nélkül)

| teszt | tanítás | legjobb F1 (felidézés / pontosság) | 80% felidézésnél: pontosság | téves / perc |
|---|---|---|---|---|
| 2. meccs | csak az 1. meccs | 0,67 (78% / 58%) | 56% | 0,87 |
| 2. meccs | csak a 2. meccs | **0,80** (77% / 83%) | **77%** | **0,33** |
| 2. meccs | 1. + 2. meccs | 0,79 (80% / 78%) | 73% | 0,41 |
| 1. meccs | csak a 2. meccs | 0,65 (67% / 63%) | 80% nem érhető el | – |
| 1. meccs | csak az 1. meccs | 0,65 (75% / 57%) | 47% | 1,16 |
| 1. meccs | 2. + 1. meccs | **0,73** (79% / 68%) | **59%** | **0,71** |

## Csak póz

| teszt | tanítás | legjobb F1 | 80%-nál pontosság | téves / perc |
|---|---|---|---|---|
| 2. meccs | csak az 1. meccs | 0,61 (70% / 54%) | 39% | 1,75 |
| 2. meccs | csak a 2. meccs | 0,78 (82% / 73%) | 75% | 0,38 |
| 2. meccs | 1. + 2. meccs | **0,80** (81% / 79%) | **79%** | **0,30** |
| 1. meccs | csak a 2. meccs | 0,55 (47% / 65%) | – | – |
| 1. meccs | csak az 1. meccs | 0,55 (71% / 45%) | 36% | 1,86 |
| 1. meccs | 2. + 1. meccs | **0,64** (68% / 61%) | 40% | 1,53 |

## Olvasat

- **A több meccs segít.** Az 1. meccsen a 2. meccs hozzáadása F1 0,65 → 0,73,
  és 80%-os felidézésnél a téves riasztás 1,16 → 0,71 / perc. A
  2. meccsen, ahol a saját adat már jó, a hozzáadott 1. meccs nem árt (0,80 →
  0,79, csak pózzal 0,78 → 0,80).
- **A vak átvitel mindkét irányban működik** (F1 0,65–0,67), de egy kicsit
  gyengébb, mint a saját meccsen tanulás: a meccsek közti különbség (közvetítő,
  fps, csarnok) még számít. Minden új meccs jelölése csökkenti ezt.
- **A 2. meccs könnyebb** (saját CV-ben F1 0,80 vs 0,65): 50 fps, élesebb kép,
  nagyobb játékosok a képen. Az 1. meccsen a 25 fps-es, kisebb felbontású
  póz a szűk keresztmetszet.
- **A kamera-jelek** mindkét meccsen javítanak a csak pózhoz képest, főleg a
  pontosságon (a lövés utáni követő svenkelés).

## Végleges modell a 3. meccshez

`modellek/lovesfelismero_m12_kamera.joblib`: póz + kamera, mindkét meccs
összes élő lövésén (236) tanítva; a jelölt-küszöb a kombinált CV-ben mindkét
meccsen legalább 80% felidézést adó küszöbök kisebbike.

    python tools/uj_meccs.py --video meccs3.mp4 --name m3 --model modellek/lovesfelismero_m12_kamera.joblib --out m3/
