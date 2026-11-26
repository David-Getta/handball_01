# Kész modellek

| fájl | mi ez | tanítás | beállítás |
|---|---|---|---|
| `lovesfelismero_m1.joblib` | lövésfelismerő (HistGradientBoosting a póz-, lendítés- és közvetítés-jellemzőkön) | 1. meccs, 108 élő lövés | pálya-szűrő + közvetítés-jelek; jelölt-küszöb 0,3 (az 1. meccs keresztvalidációjában 81% felidézés, 0,85 téves riasztás/perc) |

A `lovesfelismero_m1.joblib` a 2. meccs VAK jóslatának modellje: a 2. meccs
emberi jelölése előtt került a repóba, a 2. meccsen nem tanult.

    python tools/uj_meccs.py --video meccs2.mp4 --name m2 --model modellek/lovesfelismero_m1.joblib --out m2/
| `lovesfelismero_m1_csakpoz.joblib` | ugyanaz, közvetítés-jelek NÉLKÜL (csak póz + lendítés) | 1. meccs, 108 élő lövés | pálya-szűrő; küszöb 0,1 (1. meccs CV: 81% felidézés, 1,86 téves/perc) |
| `lovesfelismero_m1_kamera.joblib` | póz + KAMERA-jelek, eredményjelző nélkül (`--drop allas_valtozas eredmenyjelzo_latszik`) | 1. meccs, 108 élő lövés | pálya-szűrő; küszöb 0,25 (1. meccs CV: 81% felidézés, 1,16 téves/perc; legjobb F1: 75% / 57%) |
| `eredmenyjelzo_ard_sablon.npy` | az ARD-közvetítés eredményjelzőjének számjegy-sablonjai (14 k-közép klaszter, 16×24 px) | 2. meccs, 387 stabil állapot | címkék: `2,1,9,4,3,7,5,6,8,0,1,2,x,3` (a 12. klaszter két összeolvadt jel) |

    python -m hbd.scoreboard read --crops sb.npy --broadcast m2_broadcast.npz \
        --templates modellek/eredmenyjelzo_ard_sablon.npy --labels 2,1,9,4,3,7,5,6,8,0,1,2,x,3 --out allas.json
