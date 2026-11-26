# Kész modellek

| fájl | mi ez | tanítás | beállítás |
|---|---|---|---|
| `lovesfelismero_m1.joblib` | lövésfelismerő (HistGradientBoosting a póz-, lendítés- és közvetítés-jellemzőkön) | 1. meccs, 108 élő lövés | pálya-szűrő + közvetítés-jelek; jelölt-küszöb 0,3 (az 1. meccs keresztvalidációjában 81% felidézés, 0,85 téves riasztás/perc) |

A `lovesfelismero_m1.joblib` a 2. meccs VAK jóslatának modellje: a 2. meccs
emberi jelölése előtt került a repóba, a 2. meccsen nem tanult.

    python tools/uj_meccs.py --video meccs2.mp4 --name m2 --model modellek/lovesfelismero_m1.joblib --out m2/
