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

## Mit ad a labda — a kézi címkékkel mérve (a felismerő felső korlátja)

| kérdés | eredmény | viszonyítás |
|---|---|---|
| lövőkéz: „melyik csuklóhoz van közelebb a labda” | 71% (egyértelmű esetekben 82%) | mindig „jobb”: 72% |
| lövőkéz: labda–test geometria + fordulás + repülési irány (tanult) | **75% kiegyensúlyozott** | testpontokból: 58% |
| lövőkéz: ImageNet-képjellemzők (tükrözéssel) | 48% | — a jellemzők tükörfüggetlenek, a bal–jobb elvész |
| célzóna lent / fent a repülési irányból | **76% kiegyensúlyozott** | 50% |
| célzóna bal / közép / jobb | 38% | 33% — a kapu helye nélkül nem megy |

## Olvasat

- A labdafelismerő elindult, de még nem megbízható; a kézben lévő labdát
  találja a legjobban. Javítás: több kocka jelölése (a kattintások közti
  kockák a mozgásból kitölthetők), a labda kockáról kockára követése, nagyobb
  modell GPU-n (Kaggle).
- A **lövőkéz** a tévéképről egyetlen lövésből nehéz. Biztos megoldás: a
  játékos felismerése (mezszám) — a lövőkéz játékosonként állandó, a keretből
  ismert.
- A **célzóna** vízszintes harmadához a kapu helye kell a képen → pálya- és
  kapufelismerés (a hosszabb távú terv része).
