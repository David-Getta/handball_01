# A 3D pálya — edzői útmutató

A Sport Machine a követésből (ki hol volt, hol a labda) egy bejárható
3D-s csarnokot épít: szabályos 40×20 m-es pálya (6 m-es kapuelőtér,
szaggatott 9 m-es vonal, hetes-, kapus- és cserevonal, 3×2 m-es
kapuk), emberszerű figurák mezszámmal, labda a birtokos kezében.
Kétféle felületen ugyanaz a nézet él:

- **az appban** (a Meccs képernyő "3D" füle, vagy egy esemény
  "Megnézem 3D-ben" gombja),
- **a böngészőben / VR-headsetben** (az app "Böngészős 3D / VR" gombja
  — ugyanott, ugyanazzal a kamerával és rétegekkel nyílik, ahol az
  appban tartasz).

A két felület ugyanazokból a számokból dolgozik (a mérés, a falsablonok
és a hőtérkép rácsa a backend `court3d` és `analytics` moduljainak
tükre — őr-tesztek ellenőrzik, hogy nem térhetnek el).

## Mozgás a térben

| Mit akarsz | App | Böngésző |
|---|---|---|
| Körülnézni | húzás az egérrel/ujjal | húzás |
| Menni | W A S D, R/F (C) fel/le, Shift gyors | ugyanaz |
| Előre ugrani / közelíteni | görgetés / két ujj csípése | görgetés / csípés |
| Keringeni a pálya körül | **Keringés** gomb vagy **O** | ugyanaz |
| Kész állás | Lelátó · Kapu mögül · Pálya-szint · Madártávlat | ugyanaz |
| TV-kamera (a labdát követi az oldalvonal felől) | **TV-kamera (labda)** gomb | **TV-kamera** gomb vagy **T** |
| Játékos-kamera (egy mezszám hátulról) | **Játékos-kamera** választó | ugyanaz |
| A játékos SZEMÉVEL, vele együtt | dupla koppintás a figurára · Esc kilép | dupla katt · Esc |
| Lejátszás / sebesség | Szóköz · 0,5–4× | ugyanaz |
| Előző / következő esemény | ⏮ ⏭ | ⏮ ⏭ vagy [ / ] |

A játékos szemével nézve a kép tetején a HUD mutatja a **sebességét
(km/h)** és az addig **megtett útját** ("Szeged #7 · 14,2 km/h ·
1,18 km eddig"). A megtett út a mezszám mentén, kockánként összegezve
készül; a 3 m-nél nagyobb lépés (követés-ugrás) nem számít.

## Elemző rétegek a pályán

Mindegyik külön kapcsolható, egymásra is tehetők.

- **Lövés-mérés** — koppints/katts a padlóra: távolság a kapu
  közepétől és a kapufáktól, a **kapu-szög** (mennyi kapu "látszik"
  onnan) és a sáv (kapuelőtér / 6–9 m / 9 m-en túl), kék
  lövő-háromszöggel a két kapufáig. Esc törli.
- **Lövéstérkép** — a meccs minden lövése a helyén: kék a hazai, piros
  a vendég; a kör az **xG-vel nő**, a gólt **arany gyűrű** jelzi, a
  védett/kihagyott halványabb. Módok: minden lövés / a lejátszásig
  (a térkép a meccsel együtt épül) / csak hazai / csak vendég.
  **Katt egy körre: odaugrik a lövéshez** (4 mp-cel előtte), és a
  mérés-doboz a lövés sorával kezdődik ("Szeged lövése 12:40 · gól ·
  xG 0,55").
- **Védekezés** — a 6-0, 5-1, 4-2, 3-2-1 tankönyvi fal sárga körökkel a
  kapu előtt; "élő" módban a pillanatnyi fal neve ("Most: Szeged
  védekezik — 5-1") és az **átlagos eltérés** a tankönyvi faltól
  méterben. A kaput a védett / bal / jobb választó adja.
- **Passzok** — "élő": a futó passz vonala az adótól a fogadóig
  (egy másodpercig, halványodva); "háló": a csapat MINDEN passza vékony
  vonalként a padlón, összegzővel — a játékszervezés fő tengelyei.
- **Hőtérkép** — hol tartózkodott a csapat a meccsen (2 m-es cellák,
  csak a mért helyek), a legsűrűbb cellához mért erősséggel.
- **Labda-nyom** — a labda útja az utolsó 3 másodpercben narancs
  vonalként (a passz-sorozat és a lövés íve egyben).
- **Passzsávok** — a pillanatnyi labdástól minden csapattársához egy
  vonal: **zöld** nyitott, **sárga** kockázatos, **piros** zárt sáv,
  összegzővel ("Labdás (Szeged): 4 nyitott, 0 kockázatos, 2 zárt").
  A színezés a döntés-elemzés passz-modellje (a távolság és a sávban
  1,5 m-en belül álló ellenfelek), a labdás az elemzés birtoklás-
  sugarával (3 m) dől el — a 3D nem mond mást, mint az elemzés.
- **Fal-rések** — szervezett védekezésben a védőfal szomszédos védői
  közt sáv a padlón: **zöld**, ha zárt, **piros**, ha a rés eléri a
  3,5 m-t — ott nyílik a fal (oda kell betörni, oda úszik be a beálló).
  Összegző: "Fal (Szeged, 6 védő): 2 nyitott rés — a legnagyobb 4,1 m".
  A fal ugyanaz, mint a fal-rés rétegben: a mért, kapus nélküli védők a
  saját kaputól 12 m-en belül, a rés az oldalirányú távolság.
- **Feltörés és Megállítás** (a Védekezés "élő" módjában) — a fal
  mellé a felderítés két rangsorának teteje: HOL és MIVEL törhető fel a
  védekező csapat fala, és mivel állíthatja meg a most támadó csapatot;
  ha a feltörés egy sávra mutat, az **piros sávként** a padlón is
  megjelenik a védett kapu előtt ("ide kell betörni").

## Jelenetek lapozása

A felderítés és az elemzés arányokat mond ("60%-ban optimális
döntés", "a lövők 84%-át szabadon hagyják"). A lapozók a mögöttük
lévő JELENETEKRE ugranak — a jelenet előtt 1,5 mp-cel, lejátszva, a
pillanat körül rajzolva és felirattal (ha több egyszerre aktív, a
feliratok egymás alatt):

- **Döntések ◀ ▶** — a passz-döntések, ahol a döntés-elemzés modellje
  szerint érdemben (legalább 0,10 értékkel) jobb opció is volt: a
  választott passz **fehér**, a jobb opció **arany** vonal (egy másik
  társhoz, vagy lövésnél a kapura).
- **Szabad lövők ◀ ▶** — a kapott lövések, ahol a lövőtől 2 m-en belül
  nem volt mezőnyvédő: **piros kör** a lövő körül (a fedezés-sugár) és
  szaggatott vonal a legközelebbi védőhöz, a felirat a távolsággal.
- **Emberelőny ◀ ▶** — a kiállítások szakaszai; amíg a lejátszás egy
  ilyenben jár, lent középen élő jelző: ki van előnyben, ki hiányos,
  mennyi van hátra, és az előny alatti állás eddig. A kiállítás-
  felismerés és a lövés-szabály az emberelőny-hatékonyság rétegé.
- **Gól-akciók ◀ ▶** — a gólok előkészítése: a gólt megelőző saját
  passz-lánc a csapat színével (a régebbi passz halványabb), **arany**
  vonal a lövőtől a kapuig; a felirat a mezszámokkal ("#10 → #9 → … →
  #4 → #10 lő · 8 passz, 6,5 mp"). A lánc-szabály a gól-előkészítés
  rétegé: a gól előtti 20 mp saját passzai, a birtoklás-határig.
- **Labdavesztések ◀ ▶** — az elvesztett labdák: **narancs kör** a
  vesztő körül (a 2,5 m-es nyomás-sugár: ha ezen belül állt ellenfél,
  az eladás KIPRÉSELT, különben MAGÁTÓL jött), szaggatott vonal a
  legközelebbi mezőnybeli ellenfélhez, **X** a labdánál; a felirat a
  vesztő mezszámával, a pálya-harmaddal, a nyomással, és ha fél percen
  belül gól lett belőle, azzal is. Ugyanaz a négy válasz, amit a
  labdaeladás-rétegek számokban mondanak — itt egy jeleneten.

A ▶ az utoljára nézett jelenettől lép tovább (nem ragad le, és a meccs
legelső pillanatai is elérhetők).

Két lapozó jelenetei a **Klipek** képernyőn videóként is kivághatók:
a "Drága eladások" (a gólba került labdavesztések) és a "Döntés-hibák"
csomag — mezszámra szűkítve is ("a #7 drága eladásai").

A **Jelenet-lista** a három lapozó összes jelenetét egy időrendi
listában mutatja ("12:40 · Szeged — labdavesztés #7 (támadó harmad) ·
gól lett belőle"); koppintás egy sorra: odaugrik, az épp futó jelenet
sora kiemelve. Meccs-elemzéshez gyorsabb, mint a ◀ ▶ lapozás.

A **Kinek a hibái** választó a három lapozót egy csapatra szűri: mind
a három egy csapat hibáját mutatja (a rossz döntést, a szabadon hagyott
lövőt, az elvesztett labdát) — a saját csapatra szűrve videóelemzés a
játékosoknak, az ellenfélre szűrve felkészülés ellenük.

## Jelenet megosztása

A böngészős nézet **Link másolása** gombja a MOSTANI jelenetet adja
címként: idő, kamera-állás vagy Játékos-/TV-kamera és a bekapcsolt
rétegek. A címet megnyitva mindez visszaáll — így egy JELENETET
küldesz a stábnak, nem egy meccset. A paraméterek:

```
/matches/<meccs>/view3d?t=349&nezet=madar
   &kamera=h7 | &tv=1
   &hoter=mind&loves=hazai&passz=vendeg&fal=6-0&falOldal=jobb
   &nyom=1&passzsav=1&falres=1&jelenet=vendeg&lista=1&seb=2
```

## VR-headset

A böngészős oldal WebXR-képes: a lenti "ENTER VR" gombbal a csarnok
headsetben nyílik, a bal kar hüvelykujj-karja a nézés iránya szerint
visz. A jelenet-feliratok (esemény, döntés, szabad lövő,
labdavesztés, gól-akció, emberelőny) a headsetben egy fejhez rögzített
táblán látszanak — a lapozók VR-ben is használhatók (a gombokat a VR
előtt, az ablakban nyomd meg, vagy a jelenet-linkkel indíts). A WebXR biztonságos környezetet kér — a localhost az; Quest-féle
headsetről USB-kábellel és `adb reverse`-szel érhető el az app gépe.

## Hol él a kód

- Backend: `backend/handball/pipeline/court3d.py` (lövés-geometria,
  falsablonok, védekezés-idővonal, `tactical_keys_by_team` — feltörés
  és megállítás, `pass_lanes` — passzsávok, `decision_moments` —
  döntés-pillanatok, `free_shot_moments` — szabadon hagyott lövők,
  `turnover_moments` — labdavesztések, `wall_gap_segments` — fal-rések,
  `goal_build_ups` — gól-akciók, `powerplay_moments` — emberelőny,
  `scene_rows` — a jelenet-lista sorai),
  `view3d_html.py` (a böngészős oldal és a tömör adat), végpontok:
  `/matches/{id}/view3d`, `/matches/{id}/defence-timeline`,
  `/matches/{id}/decision-moments`, `/matches/{id}/free-shots`,
  `/matches/{id}/turnover-moments`, `/matches/{id}/goal-build-ups`,
  `/matches/{id}/powerplay-moments`.
- App: `client/lib/ui/court3d_screen.dart` (szoftveres vetítés,
  gesztusok, rétegek), `court_geometry.dart` (a backend tükre).
- Tesztek: `backend/tests/test_view3d_eszkozok.py`,
  `test_court3d.py`; `client/test/court3d_screen_test.dart`,
  `court_geometry_test.dart`.
