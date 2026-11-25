# Labda — 1. meccs (labdajelölő címkéi)

184 lövés, klipenként 3 kattintás a labdára: **kézben** (184), **elválik** (az első
kocka, ahol már nem érinti a kezet; 179), **repül** (ahol jól látszik, nem
feltétlenül a repülés eleje; 167). Az ismétlés az élő párjával egy csoportban.

## A címkék minősége

Az elválás kockája a korábbi (meccs-lövésjelölős) elengedés-jelöléssel 65%-ban
pontosan egyezik, 95%-ban legfeljebb 1 kockát tér el → a jelölés következetes.

## Labdafelismerő (első változat)

YOLO11n, a kattintásokból készült 320 px-es kivágásokon tanítva (1260 kép, a
labda doboza = a lövő magasságának 10%-a), CPU-n, 30 korszak (korai leállás).
Kiértékelés: a lövések 20%-a (40 lövés, 110 labdapont) kimaradt a tanításból;
a teljes 640 px-es, lövő köré vágott képen a legbiztosabb jelölt akkor talált,
ha a valódi labdától legfeljebb 1,5 labdaátmérőre van.

| pillanat | eltalálja a labdát |
|---|---|
| kézben | 70% |
| elválik | 56% |
| repül | 44% |
| **összesen** | **57%** |

Kész (COCO) felismerővel ugyanez: ~0% (a nagyobb modellek semmit, a kicsi a
9 m-es vonal csíkjait jelölte).

## Második változat: köztes kockák + követés

- **Köztes kockák:** a három kattintás közti kockákra a labda helye
  vonalasan kitöltve (legfeljebb 8 kocka hézagig) → 2865 tanítókép (1260
  helyett). Ugyanaz a 40 félretett lövés, tehát a számok összevethetők.
- **Követés:** kockánként a 5 legjobb jelöltből a legvalószínűbb, egyenletes
  labdapálya (Viterbi), "nem látszik" állapottal.

| pillanat | v1 | v2 (kockánként) | v2 + követés |
|---|---|---|---|
| kézben | 70% | 62% | 70% |
| elválik | 56% | 69% | **81%** |
| repül | 44% | 59% | 50% |
| **összesen** | **57%** | **64%** | **67%** |

(A v2 a teljes kivágásokon 65%; a táblázat a labdajelölő videóinak kockáin
mér. A követés "nem látszik" árát ugyanezen a 40 lövésen választottuk ki,
ezért a 67% kissé optimista; az eredeti beállítással a követés 55%-ra
rontott.)

## Mit ad a labda — a kézi címkékkel mérve (a felismerő felső korlátja)

| kérdés | eredmény | viszonyítás |
|---|---|---|
| lövőkéz: „melyik csuklóhoz van közelebb a labda” | 71% (egyértelmű esetekben 82%) | mindig „jobb”: 72% |
| lövőkéz: labda–test geometria + fordulás + repülési irány (tanult) | **75% kiegyensúlyozott** | testpontokból: 58% |
| lövőkéz: ImageNet-képjellemzők (tükrözéssel) | 48% | — a jellemzők tükörfüggetlenek, a bal–jobb elvész |
| célzóna lent / fent a repülési irányból | **76% kiegyensúlyozott** | 50% |
| célzóna bal / közép / jobb | 38% | 33% — a kapu helye nélkül nem megy |

## Olvasat

- A labdafelismerő a v2-ben 57%-ról 64%-ra (követéssel 67%-ra) javult; az
  elválás pillanatát 81%-ban találja. A repülő labdát kockánként jobban
  találja (59%), mint a követés (50%): a gyors labdánál a pálya-feltétel még
  túl szigorú. Következő lépés: nagyobb modell
  GPU-n (Kaggle), és öntanítás a jelöletlen kockákon.
- A **lövőkéz** a tévéképről egyetlen lövésből nehéz. Biztos megoldás: a
  játékos felismerése (mezszám) — a lövőkéz játékosonként állandó, a keretből
  ismert.
- A **célzóna** vízszintes harmadához a kapu helye kell a képen → pálya- és
  kapufelismerés (a hosszabb távú terv része).
