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

## Követés: sebesség és összefésülés (v2 felismerővel)

Hol a hiba a repülő labdánál? A félretett lövéseken a valódi labda a kocka 5
legjobb jelöltje közt: kézben 78%, elválik 92%, **repül csak 65%**. A gyors,
elmosódott labdát a felismerő sokszor jelöltnek sem adja → ezt követés nem
javíthatja, csak jobb felismerő. A követés a repülő labdánál 18%-ban
"nem látszik"-ot mondott.

Kipróbált változatok (a paramétereket kétfelé osztott lövéseken választva,
a másik felén mérve, 50 véletlen felosztás átlaga = **keresztvalidált**; a
"mindenen hangolva" szám ugyanazon a 40 lövésen választott, optimista):

| módszer | keresztvalidált | mindenen hangolva | kézben / elválik / repül (hangolva) |
|---|---|---|---|
| elsőrendű követés (ugrás-büntetés) | 64% | 69% | 72 / 83 / 50% |
| másodrendű követés (sebesség-jóslat) | 65% | 70% | 75 / 81 / 53% |
| **elsőrendű + összefésülés** | **69%** | 71% | 70 / 86 / 56% |

- **Másodrendű követés:** az állapot két egymást követő jelölt, így a labda
  sebessége ismert, és a következő helytől való eltérés büntetett (nem az
  ugrás). Gyakorlatilag nem jobb (65% vs 64%) — a szűk keresztmetszet a
  felismerő, nem a pálya. Összevetésre megmaradt (`track2`).
- **Összefésülés (alapértelmezés):** ahol a követés "nem látszik"-ot mond,
  vagy a kocka legjobb jelöltje legalább 3× biztosabb a követettnél, azt
  vesszük. Ez segít: **64% → 69% keresztvalidálva**; a 3–10 közti arányok
  mind hasonlóak, tehát nem egy szerencsés beállítás.

## Öntanítás (v3): nem javított

A v2 felismerő + követés + összefésülés a TANÍTÓ lövések összes kockáján
gépi labdapontot ad, ahol a választott jelölt legalább 0,15 biztos (a
félretett lövéseken 0,1 fölött 89%, 0,2 fölött 90% a valódi labda). Eredmény:
1043 gépi pont 144 lövésen → 4628 tanítókép (a gépi pont csak pozitív
kivágást kap, "nincs labda" kivágást nem). A félretett 40 lövés érintetlen
(egyetlen kiértékelő kép sincs a tanító halmazban), a kiértékelő halmaz
bájtra azonos. YOLO11n, 30 korszak CPU-n (~100 perc).

| a félretett 40 lövésen | v2 | v3 (öntanított) |
|---|---|---|
| kockánként | 64% | 66% (kézben 73 / elválik 64 / repül 59%) |
| követés | 67% | 64% |
| másodrendű követés | 70% | 66% |
| összefésülés (hangolva) | 71% | 66% |

**Olvasat:** az öntanítás érdemben nem segített. Kockánként +1–2 pont
(110 ponton ez 1–2 találat, a zajon belül), a követéssel együtt inkább
romlott. A gépi pontok jórészt a KÖNNYŰ kockák (kézben lévő, éles labda),
amiket a v2 is megtalált — a nehéz, elmosódott repülő labdához nem ad új
példát. A v2 marad az alapértelmezés. Ami segíthet: nagyobb modell vagy
nagyobb felbontás GPU-n, és célzott kézi címke a repülő labdára. A lépések
megismételhetők:

    python -m hbd.ball pseudo --ball-dir m1ball2 --labels cimkek/meccs1_labda_cimkek.json \
        --clips m1web/manifest.json --weights labda2/best.pt --out pseudo.json
    python -m hbd.ball build ... --pseudo pseudo.json --out balldata3
    python -m hbd.ball train --data balldata3 --epochs 30

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
  túl szigorú. Az öntanítás a jelöletlen kockákon kipróbálva nem javított
  (v3, fent); következő lépés: nagyobb modell / felbontás GPU-n (Kaggle).
- A **lövőkéz** a tévéképről egyetlen lövésből nehéz. Biztos megoldás: a
  játékos felismerése (mezszám) — a lövőkéz játékosonként állandó, a keretből
  ismert.
- A **célzóna** vízszintes harmadához a kapu helye kell a képen → pálya- és
  kapufelismerés (a hosszabb távú terv része).
