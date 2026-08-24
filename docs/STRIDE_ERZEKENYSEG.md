# Stride-érzékenység — az ítélet és a kocka-ritkítás

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.stride_sensitivity`

A feldolgozó alapból minden harmadik képkockát dolgozza fel
(stride=3, effektív fps = fps/3). A kockaszám-küszöbbel ítélő
rétegek ugyanarról a meccsről ritkítva másképp — jellemzően
óvatosabban — ítélhetnek. Ez a lista a döntés alapja, hol
érdemes a kockaszám-küszöböt másodperc-alapúra váltani.

Mérés: 240 mp-es szimulált meccs (mag: 7), sűrű (25 fps) vs 3-as ritkítás; **500 réteg** összevetve, ebből **25 eltérő ítéletű**.

## Fontos: mit jelent az eltérés

Az eltérés NEM feltétlenül hiba: a ritkított meccsen kevesebb a
minta, és a "kevés mintánál nincs ítélet" elv pont ezt
kívánja. A lista arra való, hogy a küszöb-kalibrálás tudatos
legyen — a termék alap-stride-jánál (3) a kocka-küszöbök
háromszor annyi valós időt követelnek.

## Eltérő ítéletű rétegek

### `attack_motion`

- `home.style`: sűrűn `mozgásos` → ritkítva `None`

### `attack_starter_roles`

- `home.verdict`: sűrűn `None` → ritkítva `a támadásaik 63%-a a(z) irányító posztnál indul (38 szakaszból) — a felhozatalt őt presszingelve lehet borítani: korai nyomás rá már a felezőnél, és a szervezésük el sem kezdődik`

### `backward_passers`

- `away.top`: sűrűn `13` → ritkítva `14`

### `ball_carrier_roles`

- `home.verdict`: sűrűn `a térnyerésük a(z) irányító poszt lábán van (72%-a a labdával megtett 279 előre-méternek) — őt a felezőtől hátrálva kell fogadni: lendületbe engedni tilos` → ritkítva `a térnyerésük a(z) irányító poszt lábán van (74%-a a labdával megtett 91 előre-méternek) — őt a felezőtől hátrálva kell fogadni: lendületbe engedni tilos`

### `beaten_defenders`

- `away.top`: sűrűn `None` → ritkítva `13`

### `blocked_shooter_roles`

- `home.verdict`: sűrűn `a blokkolt lövéseik 100%-a a(z) beálló posztról jön (8 blokkból) — a fal ellene bátran zárhat: az ő előkészítetlen lövése falba megy, és onnan kontra indul` → ritkítva `a blokkolt lövéseik 100%-a a(z) beálló posztról jön (4 blokkból) — a fal ellene bátran zárhat: az ő előkészítetlen lövése falba megy, és onnan kontra indul`

### `counter_plan`

- `home.pairs[0].verdict`: sűrűn `a kulcs-emberük a(z) 10. számú: 9 réteg ítélete mutat rá (a 16 megszólalóból) — ő nem egy a hét mezőnyjátékos közül, az ő kezelése önmagában meccstervnyi feladat` → ritkítva `a kulcs-emberük a(z) 10. számú: 9 réteg ítélete mutat rá (a 15 megszólalóból) — ő nem egy a hét mezőnyjátékos közül, az ő kezelése önmagában meccstervnyi feladat`
- `home.pairs[2].verdict`: sűrűn `a(z) beálló közelről fejez be (átl. 6.0 m) — őt ki kell zárni` → ritkítva `a(z) beálló közelről fejez be (átl. 5.9 m) — őt ki kell zárni`
- `home.pairs[4].verdict`: sűrűn `a(z) 1. figurájuk lövéseinek 61%-a a(z) irányító posztra fut ki — a figura INDULÁSAKOR arra az oldalra kell csúszni, nem a lövésnél` → ritkítva `a(z) 1. figurájuk indításainak 100%-a a(z) beálló posztról jön — amint a labda odaér, zárni kell a kiinduló passzsávot, és a figura el sem indul`
- `home.verdict`: sűrűn `a(z) 5 teendőből 1-hez van kész gyakorlat; a maradék 4 edzői döntést kíván` → ritkítva `a(z) 5 teendőből 2-hez van kész gyakorlat; a maradék 3 edzői döntést kíván`

### `defensive_shift_lag`

- `away.verdict`: sűrűn `None` → ritkítva `gyorsan igazodnak`

### `high_steal_roles`

- `home.verdict`: sűrűn `az elöl-szerzéseik 92%-a a(z) irányító posztjuknál születik (25 letámadás-szerzésből) — az ő oldalán tilos a kihozatalt vezetni: a kapus a másik oldalra indítson` → ritkítva `az elöl-szerzéseik 100%-a a(z) irányító posztjuknál születik (23 letámadás-szerzésből) — az ő oldalán tilos a kihozatalt vezetni: a kapus a másik oldalra indítson`

### `hold_time_roles`

- `home.verdict`: sűrűn `a labda a(z) irányító posztjuknál áll meg: a mért labdatartásuk 72%-a nála telik (230 mp-ből) — a kettőzést rá kell időzíteni, nála lassul a támadásuk` → ritkítva `a labda a(z) irányító posztjuknál áll meg: a mért labdatartásuk 73%-a nála telik (223 mp-ből) — a kettőzést rá kell időzíteni, nála lassul a támadásuk`

### `keeper_involvement`

- `away.verdict`: sűrűn `sokat játszanak vissza` → ritkítva `None`

### `key_player`

- `home.verdict`: sűrűn `a kulcs-emberük a(z) 10. számú: 9 réteg ítélete mutat rá (a 16 megszólalóból) — ő nem egy a hét mezőnyjátékos közül, az ő kezelése önmagában meccstervnyi feladat` → ritkítva `a kulcs-emberük a(z) 10. számú: 9 réteg ítélete mutat rá (a 15 megszólalóból) — ő nem egy a hét mezőnyjátékos közül, az ő kezelése önmagában meccstervnyi feladat`

### `key_post`

- `home.verdict`: sűrűn `a kulcs-posztjuk a(z) irányító: 10 réteg ítélete fut ki rá (a 17 megszólalóból) — az ő kezelése nem részfeladat, hanem a meccsterv első lapja` → ritkítva `a kulcs-posztjuk a(z) irányító: 11 réteg ítélete fut ki rá (a 18 megszólalóból) — az ő kezelése nem részfeladat, hanem a meccsterv első lapja`

### `last_pass_roles`

- `home.verdict`: sűrűn `a lövéseik előkészítése 87%-ban a(z) beálló posztról jön (23 előkészítő passzból) — az ő sávjának zárásával a lövéseik előkészítetlenné válnak, és a lövők maguktól elhalnak` → ritkítva `a lövéseik előkészítése 83%-ban a(z) beálló posztról jön (24 előkészítő passzból) — az ő sávjának zárásával a lövéseik előkészítetlenné válnak, és a lövők maguktól elhalnak`

### `outlet_hunter_roles`

- `home.verdict`: sűrűn `az indítás-vadászatuk a(z) irányító poszton fut (100%, 23 elrabolt indításból) — a kapus-indítás a másik oldalon vagy az ő feje fölött nyisson` → ritkítva `az indítás-vadászatuk a(z) irányító poszton fut (100%, 22 elrabolt indításból) — a kapus-indítás a másik oldalon vagy az ő feje fölött nyisson`

### `pivot_feeder_roles`

- `home.verdict`: sűrűn `a beálló-beadásaik a(z) irányító posztról jönnek (100%, 28 beadásból) — az ő kezén kell a beálló-vonalba lépni, és az ő oldalán induljon a kettőzés` → ritkítva `a beálló-beadásaik a(z) irányító posztról jönnek (100%, 27 beadásból) — az ő kezén kell a beálló-vonalba lépni, és az ő oldalán induljon a kettőzés`

### `pivot_runners`

- `home.top`: sűrűn `6` → ritkítva `None`

### `role_shooting_hand`

- `home.lefty_role`: sűrűn `beálló` → ritkítva `None`

### `role_shot_distance`

- `home.verdict`: sűrűn `a(z) beálló közelről fejez be (átl. 6.0 m) — őt ki kell zárni` → ritkítva `a(z) beálló közelről fejez be (átl. 5.9 m) — őt ki kell zárni`

### `role_steal_sources`

- `home.verdict`: sűrűn `a labdáik felét-többségét a(z) irányító szedi (92%, 25 szerzésből) — az ő sávjába csak biztonsági passz mehet, a támadást a másik oldalon kell átvezetni` → ritkítva `a labdáik felét-többségét a(z) irányító szedi (100%, 23 szerzésből) — az ő sávjába csak biztonsági passz mehet, a támadást a másik oldalon kell átvezetni`

### `setplay_concentration`

- `home.verdict`: sűrűn `a támadásaik 41%-a egyetlen mintából jön (44 mért támadásból, 3 figura fedi le a 80%-ot) — konkrét figurára lehet készülni: videó, bejátszott védekezés, előre megbeszélt kettőzés` → ritkítva `a támadásaik 71%-a egyetlen mintából jön (38 mért támadásból, 2 figura fedi le a 80%-ot) — konkrét figurára lehet készülni: videó, bejátszott védekezés, előre megbeszélt kettőzés`

### `setplay_finishers`

- `home.figures[1].main_role`: sűrűn `irányító` → ritkítva `beálló`
- `home.figures[2].main_role`: sűrűn `beálló` → ritkítva `None`
- `home.figures[3].main_role`: sűrűn `szélső` → ritkítva `None`
- `home.verdict`: sűrűn `a(z) 1. figurájuk lövéseinek 61%-a a(z) irányító posztra fut ki — a figura INDULÁSAKOR arra az oldalra kell csúszni, nem a lövésnél` → ritkítva `None`

### `setplay_openers`

- `home.figures[1].main_role`: sűrűn `irányító` → ritkítva `beálló`
- `home.figures[2].main_role`: sűrűn `beálló` → ritkítva `None`
- `home.figures[3].main_role`: sűrűn `beálló` → ritkítva `None`
- `home.verdict`: sűrűn `a(z) 2. figurájuk indításainak 100%-a a(z) beálló posztról jön — amint a labda odaér, zárni kell a kiinduló passzsávot, és a figura el sem indul` → ritkítva `a(z) 1. figurájuk indításainak 100%-a a(z) beálló posztról jön — amint a labda odaér, zárni kell a kiinduló passzsávot, és a figura el sem indul`

### `shooting_hand`

- `home.lefty`: sűrűn `6` → ritkítva `4`

### `wrongfooted_keeper`

- `away.verdict`: sűrűn `None` → ritkítva `a kapusuk állja a cseleket`

