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

## Jelenet megosztása

A böngészős nézet **Link másolása** gombja a MOSTANI jelenetet adja
címként: idő, kamera-állás vagy Játékos-/TV-kamera és a bekapcsolt
rétegek. A címet megnyitva mindez visszaáll — így egy JELENETET
küldesz a stábnak, nem egy meccset. A paraméterek:

```
/matches/<meccs>/view3d?t=349&nezet=madar
   &kamera=h7 | &tv=1
   &hoter=mind&loves=hazai&passz=vendeg&fal=6-0&falOldal=jobb
   &nyom=1&seb=2
```

## VR-headset

A böngészős oldal WebXR-képes: a lenti "ENTER VR" gombbal a csarnok
headsetben nyílik, a bal kar hüvelykujj-karja a nézés iránya szerint
visz. A WebXR biztonságos környezetet kér — a localhost az; Quest-féle
headsetről USB-kábellel és `adb reverse`-szel érhető el az app gépe.

## Hol él a kód

- Backend: `backend/handball/pipeline/court3d.py` (lövés-geometria,
  falsablonok, védekezés-idővonal), `view3d_html.py` (a böngészős
  oldal és a tömör adat), végpontok: `/matches/{id}/view3d`,
  `/matches/{id}/defence-timeline`.
- App: `client/lib/ui/court3d_screen.dart` (szoftveres vetítés,
  gesztusok, rétegek), `court_geometry.dart` (a backend tükre).
- Tesztek: `backend/tests/test_view3d_eszkozok.py`,
  `test_court3d.py`; `client/test/court3d_screen_test.dart`,
  `court_geometry_test.dart`.
