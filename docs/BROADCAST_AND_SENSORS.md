# Bemenet-jövőkép: telepített szenzor-rendszer és TV-közvetítés

A SportMachine elemző „agya" a **pálya-koordinátákon (méterben)** dolgozik,
nem a kamera pixelein. Ezért szenzor-független: minden bővítés csak a
BEMENETET cseréli, a teljes elemzési lánc (események, xG, védekezés,
szabályok, momentum, edzés-fókusz) változatlanul fut rajta. Két bővítési
út, mindkettő lépcsőnként is értéket ad.

## A. Telepített csarnok-rendszer (saját pálya)

Cél: a takarás és a labdakövetés megoldása, a pásztázás megszüntetése.

1. **1 pásztázó kamera** — ez működik ma; teljes elemzés egyetlen
   felvételből.
2. **2 oldalvonali kamera** (szemből) — a takarás gyakorlatilag megszűnik:
   amit az egyik nem lát, a másik igen; a track-szakadás ritkul.
3. **+2 alapvonali kamera** — a kapu előtti döntő zóna élesben (lövés-
   kimenetel, védés, hetes).
4. **+1–2 lidar** — fénytől független, cm-pontos 3D: valódi sebesség,
   ugrás-magasság, lövés-magasság (felső sarok). A kamera adja az
   AZONOSSÁGOT (mezszín, mezszám), a lidar a GEOMETRIÁT — szenzorfúzió.

Kulcskérdések a hardver-tervezéshez:
- **Órajel-szinkron**: a szenzoroknak közös időalapon kell futniuk
  (hálózati szinkron vagy közös trigger) — enélkül a fúzió szétcsúszik.
  Telepítési kérdés, nem szoftveres.
- **Kalibráció egyszer**: fix kameráknál a kalibráció telepítéskor
  készül, és örökre érvényes; a pásztázás-kompenzáció kiesik.
- **Fúziós modul**: az egyetlen új szoftver-komponens — több forrás
  detektálásait egy játékos-listává egyesíti a közös méter-térben. A
  meglévő több-kalibrációs alap (`calibs`, külön térfél) már ezt a mintát
  követi. *(első változat kész: `pipeline/fusion.py` — nézetenkénti
  Match-ek egyesítése pozíció-átlaggal, takarás-kitöltéssel és
  folytonos fúziós track-azonosítókkal; szintetikus két-kamerás
  nézeteken tesztelve. Az órajel-szinkront adottnak veszi — az eltolás-
  becslés külön lépcső.)*

## B. TV-közvetítés (ellenfél-felderítés)

Cél: ha az ellenfél nem enged telepített rendszert, a tévés/streamelt
közvetítés a bemenet. A mai pásztázó-kamerás motor ehhez áll a
legközelebb — de a közvetítés négy saját nehézséget hoz:

1. **Vágás-felismerő** — a közvetítés szakaszokra bontása
   (totál / közeli / ismétlés) a képkockák hisztogram-ugrásaiból.
   *(kész: `pipeline/broadcast.py`, `GET /broadcast/segments`)*
2. **Totálkép-szűrő** — csak a használható (elég hosszú totál) szakaszok
   mennek az elemzőbe; a visszajátszás így nem számol duplán gólt.
   *(kész: `usable_segments`)*
3. **Vonal-alapú auto-kalibráció** — a pályavonalakból, vágásonként újra
   (a kézi 4-sarok helyett, mert a nézőpont és a zoom folyton változik).
   *(első fele kész: `pipeline/broadcast_lines.py` — vonal-jelöltek
   felismerése tiszta numpy Hough-transzformációval, szintetikus képen
   tesztelve; a hátralévő fele a vonalak megfeleltetése a pálya-modellnek
   → homográfia, ehhez már valódi közvetítés-felvétel kell)*
4. **Eredményjelző-OCR** — az állás és a játékóra leolvasva: hitelesített
   eredmény + időszinkron (a felismert gólok validálása, pontos
   félidő-határ).
5. **Élő stream-bemenet** — a videófájl helyére capture/hálózati stream;
   a feldolgozás csúszó ablakban, a padra 10–20 mp késéssel.

Jogi/etikai keret: a tévés anyag elemzése belső, saját csapat-
felkészülési célra a videós scouting bevett formája; a kimenet belső
jelentés, nem a felvétel újraközlése.

## Miért illeszkedik költséghatékonyan

- Az elemző rétegek a `Match` objektumot látják (pozíciók méterben +
  labda) — a bemenet cseréje NEM érinti őket.
- A job-pipeline, a checkpoint-mentés és az élő-mód riasztás-folyama már
  inkrementálisan gondolkodik — az élő stream ebbe illeszkedik.
- A `calibs` (több-kalibráció) már a több-forrásos jövő magja.
