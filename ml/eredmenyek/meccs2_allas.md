# Az állás kiolvasása az eredményjelzőből — 2. meccs (Magdeburg–Füchse Berlin)

ARD-közvetítés, 50 fps, 92 perc. Emberi jelölés NÉLKÜL, csak a képből.

| | eredmény |
|---|---|
| stabil eredményjelző-állapot (≥ 2 s látszik, nem változik) | 387 |
| ebből kiolvasható | 386 |
| kiolvasott végeredmény | **35:33** — egyezik a hivatalossal |
| gólok | **68 / 68** (35 hazai, 33 vendég) |
| hibás (nem növekvő) olvasat | 0 |
| a gól idejének bizonytalansága | medián 0,4 s; két esetben ismétlés alatt 2 gól egyszerre |

Módszer (`hbd/scoreboard.py`): az állás-rész kivágása minden 10. kockán →
stabil állapotok mediánképe → a két szám kettévágva → jelek (összefüggő
világos foltok) → sablon-illesztés. A sablonok a jelek 14 k-közép csoportja,
amit egyszer, szemmel címkéztünk (`modellek/eredmenyjelzo_ard_sablon.npy`).
Új közvetítőnél (más grafika) a sablont újra kell címkézni (kb. 1 perc).

Tanulság: a csak a kép változását figyelő gólszámlálás (`broadcast.goal_changes`)
ugyanezen a meccsen 52–96 "gólt" talált a beállítástól függően — az animációk és
az ismétlés alatt eltűnő grafika miatt. A számok kiolvasása ezt megszünteti, és
a végeredmény független ellenőrzést ad.

Mire jó: a 2. meccs minden lövés-jelöltjéhez automatikusan megadható, hogy gól
lett-e (az állás a gól után átlagosan néhány másodperccel változik), és ki
szerezte (hazai / vendég) — az eredmény-címke így emberi jelölés nélkül is
megvan. A gépi idővonal: `meccs2_allas_gepi.json`.
