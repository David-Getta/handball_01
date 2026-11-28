# 2. meccs — gépi címkék a nyilvános élő szöveges közvetítésből

Forrás: a sportschau.de liveticker (HBL, 26. forduló, SC Magdeburg – Füchse
Berlin 35:33) és a meccs kerete (mezszám, poszt). Kód: `hbd/ticker.py`;
kimenet: `cimkek/meccs2_ticker.json`, `cimkek/meccs2_keret.json`. A szabad
szöveg nincs a repóban, csak a belőle kinyert kategória és a kulcsszó.

## Párosítás a videóval

A ticker minden gólnál megadja az állást („Tor für SC Magdeburg, 35:33 durch
Lukas Mertens”). Az eredményjelzőből gépileg kiolvasott idővonalon
(`meccs2_allas.md`) a hazai csapat k-adik gólja ugyanaz, mint a tickerben,
így a párosításhoz nem kell sem játékóra, sem ticker-idő.

- **68/68 gól párosítva, 0 eltérés az állásban.** Ez független megerősítése
  a képből olvasott idővonalnak is: mind a 68 gól a helyes csapathoz, a
  helyes sorrendben került, és a gólok idejének bizonytalansága mediánban 0,4 s.
- A ticker falióra-ideje (perc pontosság) **félidőnként** egyenest ad a
  videóidőhöz. A két félidő eltolása ~930 s-mal tér el: a felvételből kimaradt
  a szünet nagy része. Mind a 68 gól az egyenesen van, a maradék mediánban
  18–19 s (a ticker-bejegyzés késése). Ezzel a nem-gól események ideje is
  becsülhető, de csak ±20–30 s pontossággal.

## Mit ad ingyen

| címke | mennyi | megjegyzés |
|---|---|---|
| gól ideje a videóban | 68 | az eredményjelzőből, ~0,4 s |
| gól szerzője, csapata | 68 | a tickerből |
| a szerző mezszáma, posztja | 68 | a keretből (mind a 68 név megtalálva) |
| lövéshelyzet a szövegből | 52/68 | átlövés 20, beálló 12, indítás 8, szélső 8, hetes 4 |
| kihagyott hetes (gól nélküli lövés) | 6 | szerző, csapat, idő ±20–30 s |

- A szöveges helyzet és a keret-poszt a helyhez kötött kategóriáknál
  (átlövés, beálló, szélső) 40-ből 31-szer egyezik (78%). Az eltérés
  többnyire valódi: az átlövő a beálló helyéről is lő („Kristjánsson setzt
  sich am Kreis durch”). A poszt tehát csak tartalék.
- A védéseket és a mellé lövéseket a ticker NEM sorolja fel. A teljes
  lövéslistát továbbra is a kézi jelölés adja; a ticker a gólok és a
  hetesek címkéje.

## A vak jóslat a gólok helyzete szerint

Ugyanaz a mérés, mint a `meccs2_vak_josolat.md`-ben: van-e jelölt a gólt
megelőző 5 s-ban (az állásváltozás előtt). Zárójelben azok a gólok, ahol a
szöveg nem mond helyzetet, és a kategória a keret-posztból jön.

| helyzet | gól | póz + közvetítés | csak póz | póz + kamera |
|---|---|---|---|---|
| átlövés | 20 (+11) | 19 (+10) | 18 (+10) | 19 (+10) |
| beálló | 12 (+2) | 11 (+2) | 11 (+1) | 12 (+2) |
| szélső | 8 (+3) | 8 (+3) | 7 (+3) | 8 (+2) |
| indítás | 8 | 7 | 7 | 6 |
| hetes | 4 | 4 | **1** | 4 |
| **összes** | 68 | 64 | 58 | 63 |

(A póz + kamera változat itt 63/68; a korábbi összefoglaló 62/68-at írt,
az ablak határának kezelése miatt.)

- Egyik helyzetnél sincs nagy lyuk; a minták kicsik.
- A **csak póz** modell a 4 hetesgólból 1-et talál. A hetes mozgása más:
  helyből, felugrás nélkül, a jelenetben álló emberekkel. Ez tanító
  adatként hiányzik: az 1. meccs címkéi nem jelölik a hetest.
- **A kihagyott hetesek:** a teljes modell legközelebbi jelöltje 23–116 s-ra
  van, tehát egyiket sem jelzi (a gól nélküli lövést ez a modell nem látja,
  lásd a vak jóslat olvasatát). A másik kettőnek 2–32 s-on belül van
  jelöltje, de a ±20–30 s-os időbizonytalanság mellett ez a véletlennél
  (87–94%) nem jobb. Ezt a kézi jelölés dönti el.

## Mire jó ez tovább

- **Minden HBL-meccsre megvan ugyanez** (a sportschau.de minden meccsről
  vezet tickert), tehát a gól-pillanatok, a szerzők és a helyzetek emberi
  munka nélkül címkézhetők. Ez a lövés- és a helyzet-modell tanító adatának
  skálázható forrása.
- **A szerző mezszáma** minden gólnál ismert. Ez kész tanító és kiértékelő
  adat egy mezszám-felismerőhöz. A mezszámból jön a játékos, belőle pedig a
  lövőkéz (játékosonként állandó) és a lövő szokásai — a kapus szempontjából
  ez a legfontosabb.

## Futtatás

    python -m hbd.ticker --ticker ticker.md --scoreboard eredmenyek/meccs2_allas_gepi.json \
        --home "SC Magdeburg" --roster cimkek/meccs2_keret.json --out cimkek/meccs2_ticker.json

(A ticker oldala markdownként mentve, pl. bármely weboldal → markdown
eszközzel; a modul a sportschau.de formátumát olvassa.)
