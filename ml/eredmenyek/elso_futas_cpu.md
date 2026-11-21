> Első futás: CPU, yolo11n-pose (a legkisebb pózmodell), 808 klip, 2026-11-15. A Kaggle-futás a nagyobb (yolo11x) modellel ezt váltja.

# UNIRI-HBD — mozdulatfelismerés testpontokból

Klipek: 808; felosztás: 5-szörös, jelenet szerint csoportosítva (ugyanaz a jelenet sosem tanító és teszt egyszerre).

A `majority` a viszonyítási alap: ami nem jobb nála, az nem tanult semmit.

## Feladat: binary

Osztályok és darabszámok: nem_loves = 465, loves = 343

| modell | pontosság | kiegy. pontosság | makró-F1 | felidézés osztályonként |
|---|---|---|---|---|
| majority | 0.575 | 0.500 | 0.365 | nem_loves: 1.00, loves: 0.00 |
| logreg | 0.845 | 0.846 | 0.843 | nem_loves: 0.84, loves: 0.85 |
| hgb | 0.902 | 0.896 | 0.899 | nem_loves: 0.94, loves: 0.86 |
| tcn | 0.927 | 0.923 | 0.925 | nem_loves: 0.95, loves: 0.90 |

Tévesztési mátrix (tcn; sor = valódi, oszlop = jósolt):

| | nem_loves | loves |
|---|---|---|
| **nem_loves** | 442 | 23 |
| **loves** | 36 | 307 |

## Feladat: shot3

Osztályok és darabszámok: egyeb = 465, felugrasos = 248, helybol = 95

| modell | pontosság | kiegy. pontosság | makró-F1 | felidézés osztályonként |
|---|---|---|---|---|
| majority | 0.575 | 0.333 | 0.244 | egyeb: 1.00, felugrasos: 0.00, helybol: 0.00 |
| logreg | 0.759 | 0.745 | 0.710 | egyeb: 0.77, felugrasos: 0.75, helybol: 0.72 |
| hgb | 0.881 | 0.821 | 0.840 | egyeb: 0.94, felugrasos: 0.85, helybol: 0.67 |
| tcn | 0.917 | 0.882 | 0.896 | egyeb: 0.95, felugrasos: 0.89, helybol: 0.80 |

Tévesztési mátrix (tcn; sor = valódi, oszlop = jósolt):

| | egyeb | felugrasos | helybol |
|---|---|---|---|
| **egyeb** | 444 | 16 | 5 |
| **felugrasos** | 24 | 221 | 3 |
| **helybol** | 12 | 7 | 76 |

## Feladat: all7

Osztályok és darabszámok: crossing = 250, defence = 35, dribbling = 26, jump-shot = 248, passing = 141, running = 13, shot = 95

| modell | pontosság | kiegy. pontosság | makró-F1 | felidézés osztályonként |
|---|---|---|---|---|
| majority | 0.309 | 0.143 | 0.068 | crossing: 1.00, defence: 0.00, dribbling: 0.00, jump-shot: 0.00, passing: 0.00, running: 0.00, shot: 0.00 |
| logreg | 0.712 | 0.637 | 0.602 | crossing: 0.77, defence: 0.46, dribbling: 0.65, jump-shot: 0.71, passing: 0.74, running: 0.46, shot: 0.67 |
| hgb | 0.809 | 0.641 | 0.668 | crossing: 0.91, defence: 0.34, dribbling: 0.35, jump-shot: 0.84, passing: 0.87, running: 0.46, shot: 0.72 |
| tcn | 0.871 | 0.753 | 0.762 | crossing: 0.94, defence: 0.71, dribbling: 0.62, jump-shot: 0.88, passing: 0.87, running: 0.38, shot: 0.87 |

Tévesztési mátrix (tcn; sor = valódi, oszlop = jósolt):

| | crossing | defence | dribbling | jump-shot | passing | running | shot |
|---|---|---|---|---|---|---|---|
| **crossing** | 234 | 3 | 1 | 4 | 3 | 2 | 3 |
| **defence** | 1 | 25 | 0 | 4 | 3 | 0 | 2 |
| **dribbling** | 4 | 0 | 16 | 2 | 4 | 0 | 0 |
| **jump-shot** | 8 | 2 | 0 | 219 | 16 | 1 | 2 |
| **passing** | 3 | 2 | 4 | 6 | 122 | 2 | 2 |
| **running** | 1 | 0 | 3 | 1 | 3 | 5 | 0 |
| **shot** | 0 | 1 | 0 | 6 | 4 | 1 | 83 |

## Kapus-profil (lövésenként, címke nélkül)

Lövések: 343, ebből profil készült: 343.

- Felugrás-ítélet a címkéhez mérve (jump-shot vs shot): pontosság 0.837, AUC 0.896; felugrásosból felismert 0.94, helyből lövésnél tévesen felugrásnak mondott 0.43.
- Kartartás az elengedéskor: {'oldalt': 116, 'lent': 157, 'fent': 70}
- Lövőkéz: {'bal': 144, 'jobb': 199}
- A kartartásra NINCS címke az adathalmazban: kézi mintán kell ellenőrizni (`kapus_profilok.csv`).

## Mentett végső modellek

- `model_binary_hgb.joblib`
- `model_binary_tcn.pt`
- `model_shot3_hgb.joblib`
- `model_shot3_tcn.pt`
- `model_all7_hgb.joblib`
- `model_all7_tcn.pt`
