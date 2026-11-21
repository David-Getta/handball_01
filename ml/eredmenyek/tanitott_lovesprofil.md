> Kaggle-pózok (yolo11x) + 343 kézi jelölés a lövésjelölő oldalról, 2026-11-17.
>
> Kartartás: a fent/oldalt megkülönböztetés a testpontokból nem tanulható meg megbízhatóan (kiegyensúlyozott pontosság ~58–62%, a véletlen 50%); a kar szögét is kipróbáltuk, nem javított. Valószínű ok: a ~110 px-es játékoson a csukló/könyök helye zajos. Következő lépés: a kivágott kép közvetlen tanítása (videó-modell), vagy nagyobb felbontású felvétel.

# Tanított lövés-profil (kézi jelölésből)

Klipek: 337 (a „rossz” klipek nélkül); 5-szörös, jelenet szerint csoportosított keresztvalidáció. A kartartást és a lövőkezet a MODELL által talált elengedésnél mérjük, ahogy élesben futna.

Osztályok: kartartás {'fent': 257, 'oldalt/lent': 80}, lövőkéz {'jobb': 306, 'bal': 31}.

## Elengedés pillanata

| | átlagos hiba (kocka) | medián hiba | ±2 kockán belül | 100 ms-on belül |
|---|---|---|---|---|
| tanított modell | 1.9 | 21 ms | 84.3% | 92.9% |
| régi szabály | 9.7 | 125 ms | 22.3% | 37.7% |

## Kartartás (fent / oldalt)

| | pontosság | kiegyensúlyozott |
|---|---|---|
| tanított modell | 60.8% | 58.0% |
| modell a kézi elengedésnél | 63.2% | 61.7% |
| régi szabály | 37.7% | 56.1% |
| mindig „fent” | 76.3% | 50.0% |

## Lövőkéz (jobb / bal)

| | pontosság | kiegyensúlyozott |
|---|---|---|
| tanított modell | 90.2% | 85.9% |
| régi szabály | 59.6% | 53.1% |
| mindig „jobb” | 90.8% | 50.0% |
