# Lövésfelismerés a teljes meccsen — 1. meccs

Kérdés: a teljes közvetítésből (85 perc, 25 369 mintakocka, 0,2 s-onként) meg
tudja-e mondani a gép, MIKOR van lövés? Igazság: a meccsjelölővel kézzel
jelölt 108 élő lövés és 77 ismétlés.

Kiértékelés: a meccs 5 egymást követő idő-blokkja, mindig a többi négyen
tanítva (a blokkhatár körüli 5 s kimarad a tanításból). Egy jelölt akkor
talált, ha 1,5 s-on belül van valódi lövés. **Egyetlen meccs** — a számok
iránymutatók, a második meccs dönti el, mennyire általánosít.

## Mit adtunk hozzá

| jellemző-csoport | mi ez |
|---|---|
| v0 póz | kockánként összesítve: hány ember, mekkorák, van-e magasra emelt kar, mennyit változik a kép |
| + követés | ki kicsoda az előző mintakockán (0,2 s) → a csukló sebessége a vállhoz képest, a fentről lecsapó kar (a dobás lendítése) |
| + közvetítés | eredményjelző: látszik-e (ismétléskor eltűnik), változik-e az állás (gól után átlag 4,6 s-mal); a kamera úszása és fordulása (fázis-korreláció) |

Az eredményjelző önmagában: a 76 észlelt állásváltozásból a gólok 98%-a
után 20 s-on belül jön egy (medián késés 4,6 s).

## Eredmény — csak élő lövések (108)

| jellemzők | legjobb F1 | felidézés | pontosság | téves / perc | téves/perc 50%-os felidézésnél | 80%-nál | 90%-nál |
|---|---|---|---|---|---|---|---|
| v0 póz | 0,50 | 60% | 43% | 1,02 | 0,77 | 3,03 | 4,33 |
| + követés | 0,58 | 71% | 49% | 0,95 | 0,56 | 1,66 | – |
| + közvetítés | 0,74 | 67% | 84% | 0,17 | 0,13 | 0,96 | – |
| **mind** | **0,72** | **62%** | **86%** | **0,13** | **0,13** | **0,84** | **1,74** |

## Eredmény — élő + ismétlés (185)

| jellemzők | legjobb F1 | felidézés | pontosság | téves / perc | 50%-nál | 80%-nál | 90%-nál |
|---|---|---|---|---|---|---|---|
| v0 póz | 0,60 | 61% | 59% | 0,92 | 0,64 | 3,56 | – |
| + követés | 0,64 | 74% | 56% | 1,27 | 0,56 | 1,89 | 4,49 |
| + közvetítés | 0,69 | 67% | 70% | 0,63 | 0,39 | 1,47 | 3,37 |
| **mind** | **0,70** | **69%** | **71%** | **0,63** | **0,25** | **1,66** | **3,18** |

Viszonyítás — a legegyszerűbb szabály („valakinek magasan a karja”): 87%
felidézés, de 8% pontosság, 12,5 téves riasztás percenként.

## Mit jelent ez a gyakorlatban

- **Klip-ajánló, ami a lövések 80%-át hozza**: percenként kevesebb mint egy
  téves jelölt (0,84) — egy 60 perces meccsen ~50 fölösleges klip a ~100
  valódi mellett. Ez már kézi átválogatásra kész "nyersanyag".
- **Szigorú üzemmód**: a lövések 62%-a, és a jelöltek 86%-a valódi lövés
  (egy meccsen ~11 téves).
- A 90%-os felidézés csak az összes jellemzővel érhető el (1,74 téves/perc).
- A követés a MOZDULATOT hozza (a lövések nagyobb részét megtalálja), a
  közvetítés a BIZONYOSSÁGOT (a gól utáni állásváltozás, a kamera fordulása
  kiszűri a lövés-szerű, de nem lövés mozdulatokat).

## Korlátok és következő lépések

- Egy meccs, egy közvetítési grafika (EHF BL). Az eredményjelző helye más
  közvetítésnél más (`--sb-static`, `--sb-score`); amatőr felvételen nincs
  eredményjelző és vágás, ott a póz + követés ág számít.
- Ritkított minta (0,2 s): a dobókar lendítése 0,1–0,15 s, a követés így is
  látja, de GPU-n `--stride 1`-gyel élesebb lenne.
- A mentés és a mellé lövés nem vált ki állásváltozást — ezeknél a póz és a
  kamera dönt; a hibák nagy része itt van.
- **Második meccs kell**: azon a modellt tanítás NÉLKÜL kell kipróbálni.

Futtatás: `ml/README.md` → „Teljes meccs: hol vannak a lövések?”.
