# Lövés-profil valódi meccsről — 1. meccs (meccs-lövésjelölő címkéi)

184 kézzel címkézett lövés-klip (108 élő + 76 ismétlés; 1 klip „rossz”):
elengedés kockája, a lövőre kattintás, kartartás, lövőkéz, célzóna, kimenet.
Kartartás edzői besorolással: a fej mellől induló lövés is **oldalt** → két
osztály (fent 121 / oldalt 63). Lövőkéz: jobb 133 / bal 51.

Kiértékelés: 5-szörös csoportosított keresztvalidáció; az ismétlés az élő
párjával egy csoportban (ugyanaz a lövés más szögből nem kerülhet a tanító és
a teszt részbe is). **Egy meccs, ~108 különböző lövés** — iránymutató számok.

## A lövő megtalálása és követése

| változat | lövő végigkövetve | megjegyzés |
|---|---|---|
| teljes képen (1280) futó becslő, követés a kattintástól | 165 / 184 | a túlsó 6-osnál a 60–80 px-es lövőt a tömegben nem találja |
| **ráközelítő követés** (kivágás a lövő körül, 640-re nagyítva) | **184 / 184** | az induló kivágás ≥ 450 px (a kisebb levágta a közeli lövő testét) |

## Eredmények

| feladat | modell | viszonyítás | olvasat |
|---|---|---|---|
| elengedés pillanata | medián 80 ms, 58% ±2 kockán belül | régi szabály: 200 ms, 36% | használható, de a UNIRI-n (21 ms, 84%) jobb volt: ott közeli, éles kép |
| kartartás fent/oldalt (kézi elengedésnél) | 68% kiegyensúlyozott | 50% | gyenge jel |
| kartartás (a talált elengedésnél, élesben) | 64% kiegyensúlyozott | 50% | gyenge jel |
| lövőkéz | 58% kiegyensúlyozott | 50% | **nincs megbízható jel** |
| célzóna (függőleges / vízszintes harmad) | 30% / 31% kiegyensúlyozott | 33% | **nincs jel a testtartásban** |
| ki lő a képen lévők közül | 55% (ahol a teljes képen a lövő észlelve van) | véletlen 10%, legmagasabb kar 29% | az összesből 32%: a teljes képen 76 klipen a lövő nincs is a jelöltek közt |

## Mit tanultunk

1. **A közvetítés képe nehezebb, mint a UNIRI.** A lövő gyakran 60–100 px, a
   6-os előtti tömegben takarva; a testpontok zajosak. Ráközelítés nélkül a
   lövők 10%-a el sem kerül elő.
2. **A lövőkéz a testpontokból nem jön ki megbízhatóan.** Valószínű ok: háttal
   álló (a túlsó kapura lövő) játékosnál a pózbecslő a bal és jobb oldalt
   gyakran felcseréli — a „magasabb csukló = dobókéz” egyszerű szabály is
   csak 70% volt. A kéz eldöntéséhez a **labda** kell (melyik kézben van).
3. **A célzóna a testtartásból nem jósolható** — várható volt: a lövő a
   kapust is cselezi. Ehhez a labda röppályája kell.
4. **A kartartás két osztállyal is csak gyengén tanulható** ennyi mintából;
   a címkék edzői besorolása (a fej feletti, de oldalra hajló kar is „oldalt”)
   finomabb, mint amit a zajos testpontok mutatnak.

## Pályaszűrő a lövésfelismerőhöz (csak élő lövések)

A nézők kiszűrése a láb alatti színből (`hbd/court.py`): a pályán álló
játékosok a padló-színtől 20–36, a nézők 55–140 Lab-távolságra; küszöb 45.

| | felidézés 70%-nál téves/perc | 80%-nál | 90%-nál | „magas kar” szabály téves/perc |
|---|---|---|---|---|
| szűrő nélkül | 0,38 | 0,84 | 1,74 | 12,5 |
| pályaszűrővel | 0,28 | 0,85 | nem érhető el | 5,45 |

A szűrő a szabálynak sokat segít (a szurkolók felemelt karja valóban téves
riasztás volt), a tanított modellnek alig: az eddig is megtanulta nagyrészt
figyelmen kívül hagyni őket.

## Következő lépések

- **Labda-felismerés** (a lövőkéz, az elengedés és a célzóna kulcsa).
- Nagyobb pózmodell GPU-n (Kaggle, yolo11x) a ráközelítő követéshez.
- Második meccs címkézve: tanítás nélküli próba.

**Javított hiba (a fenti számok még előtte készültek):** az eredeti
felvételből olvasó `_orig_frames` pontos ugrásnál néha megduplázta az első
kockát, így a klip-pózok 185-ből 104 klipben 1 kockával (40 ms) késtek. A
javítás (`-fps_mode passthrough`) a következő futásoktól él; az elengedés
±2 kockás pontossága emiatt inkább alul-, mint felülbecsült.

Futtatás: `python -m hbd.match_shots extract|zoom|evaluate` (lásd a modul fejlécét).
