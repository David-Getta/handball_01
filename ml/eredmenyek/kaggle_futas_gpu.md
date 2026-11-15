> Kaggle-futás: GPU (2× T4), yolo11x-pose (a legnagyobb pózmodell), 808 klip, 2026-11-15.
>
> Megjegyzés a kapus-profilhoz: a lövések 91%-ában a csukló valamikor a fej fölé ér, mégis sok a "lent" ítélet. Ok: az elengedés kockáját a leggyorsabb csukló jelöli ki, és ez gyakran a lövés UTÁNI lecsapásra esik. A kartartás- és lövőkéz-ítélet ezért még nem megbízható; javítás: kézi jelölés + tanított modell.

# UNIRI-HBD — mozdulatfelismerés testpontokból

Klipek: 808; felosztás: 5-szörös, jelenet szerint csoportosítva (ugyanaz a jelenet sosem tanító és teszt egyszerre).

A `majority` a viszonyítási alap: ami nem jobb nála, az nem tanult semmit.

## Feladat: binary

Osztályok és darabszámok: nem_loves = 465, loves = 343

| modell | pontosság | kiegy. pontosság | makró-F1 | felidézés osztályonként |
|---|---|---|---|---|
| majority | 0.575 | 0.500 | 0.365 | nem_loves: 1.00, loves: 0.00 |
| logreg | 0.879 | 0.878 | 0.876 | nem_loves: 0.88, loves: 0.87 |
| hgb | 0.917 | 0.915 | 0.915 | nem_loves: 0.93, loves: 0.90 |
| tcn | 0.933 | 0.932 | 0.932 | nem_loves: 0.94, loves: 0.92 |

Tévesztési mátrix (tcn; sor = valódi, oszlop = jósolt):

| | nem_loves | loves |
|---|---|---|
| **nem_loves** | 438 | 27 |
| **loves** | 27 | 316 |

## Feladat: shot3

Osztályok és darabszámok: egyeb = 465, felugrasos = 248, helybol = 95

| modell | pontosság | kiegy. pontosság | makró-F1 | felidézés osztályonként |
|---|---|---|---|---|
| majority | 0.575 | 0.333 | 0.244 | egyeb: 1.00, felugrasos: 0.00, helybol: 0.00 |
| logreg | 0.811 | 0.807 | 0.773 | egyeb: 0.82, felugrasos: 0.80, helybol: 0.80 |
| hgb | 0.910 | 0.867 | 0.880 | egyeb: 0.95, felugrasos: 0.89, helybol: 0.76 |
| tcn | 0.948 | 0.929 | 0.937 | egyeb: 0.97, felugrasos: 0.93, helybol: 0.88 |

Tévesztési mátrix (tcn; sor = valódi, oszlop = jósolt):

| | egyeb | felugrasos | helybol |
|---|---|---|---|
| **egyeb** | 451 | 11 | 3 |
| **felugrasos** | 15 | 231 | 2 |
| **helybol** | 8 | 3 | 84 |

## Feladat: all7

Osztályok és darabszámok: crossing = 250, defence = 35, dribbling = 26, jump-shot = 248, passing = 141, running = 13, shot = 95

| modell | pontosság | kiegy. pontosság | makró-F1 | felidézés osztályonként |
|---|---|---|---|---|
| majority | 0.298 | 0.138 | 0.104 | crossing: 0.58, defence: 0.00, dribbling: 0.00, jump-shot: 0.38, passing: 0.00, running: 0.00, shot: 0.00 |
| logreg | 0.751 | 0.644 | 0.617 | crossing: 0.82, defence: 0.54, dribbling: 0.50, jump-shot: 0.76, passing: 0.76, running: 0.38, shot: 0.75 |
| hgb | 0.827 | 0.597 | 0.622 | crossing: 0.95, defence: 0.20, dribbling: 0.38, jump-shot: 0.88, passing: 0.87, running: 0.15, shot: 0.74 |
| tcn | 0.895 | 0.788 | 0.808 | crossing: 0.95, defence: 0.77, dribbling: 0.65, jump-shot: 0.92, passing: 0.88, running: 0.46, shot: 0.88 |

Tévesztési mátrix (tcn; sor = valódi, oszlop = jósolt):

| | crossing | defence | dribbling | jump-shot | passing | running | shot |
|---|---|---|---|---|---|---|---|
| **crossing** | 237 | 1 | 2 | 5 | 2 | 0 | 3 |
| **defence** | 3 | 27 | 0 | 3 | 1 | 0 | 1 |
| **dribbling** | 2 | 0 | 17 | 1 | 6 | 0 | 0 |
| **jump-shot** | 4 | 1 | 3 | 228 | 6 | 1 | 5 |
| **passing** | 6 | 1 | 2 | 7 | 124 | 0 | 1 |
| **running** | 1 | 0 | 1 | 2 | 3 | 6 | 0 |
| **shot** | 4 | 0 | 2 | 2 | 2 | 1 | 84 |

## Kapus-profil (lövésenként, címke nélkül)

Lövések: 343, ebből profil készült: 343.

- Felugrás-ítélet a címkéhez mérve (jump-shot vs shot): pontosság 0.813, AUC 0.892; felugrásosból felismert 0.90, helyből lövésnél tévesen felugrásnak mondott 0.42.
- Kartartás az elengedéskor: {'oldalt': 149, 'fent': 61, 'lent': 133}
- Lövőkéz: {'bal': 137, 'jobb': 206}
- A kartartásra NINCS címke az adathalmazban: kézi mintán kell ellenőrizni (`kapus_profilok.csv`).

## Mentett végső modellek

- `model_binary_hgb.joblib`
- `model_binary_tcn.pt`
- `model_shot3_hgb.joblib`
- `model_shot3_tcn.pt`
- `model_all7_hgb.joblib`
- `model_all7_tcn.pt`
