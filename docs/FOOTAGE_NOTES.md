# A valódi felvétel megfigyelései (és hatásuk a tervre)

> Forrás: a projekt tényleges meccsfelvétele (`20241120_180934.mp4`, ~14 perc,
> MP4, ~2,78 GB). Három képkocka elemzése alapján (kb. 0:27, 1:04, 1:27).
> A teljes videót feltölteni/itt feldolgozni nem praktikus (méret); fejlesztéshez
> rövid klip / állóképek + a `handball.sim` szimulátor szolgál (lásd MVP_PLAN.md).

## Csarnok és kamera
- **Pásztázó kamera megerősítve**: fix, emelt, sarok-közeli pozíció; a képkockák a
  pálya különböző részeit mutatják (jobb kapu → bal kapu → középpálya lerohanás).
  Egyezik a tervezési feltevéssel (pásztázás, homográfia a referenciához).
- **Széles látószögű (GoPro-jellegű) objektív**: a kép szélén látható hordó-
  torzítás (ívelő falak/vonalak). → **Hatás [A]**: egyetlen homográfia a kép
  szélén pontatlan lehet; érdemes **lencsetorzítás-korrekciót (undistort)** a
  homográfia ELŐTT (a kamera belső paramétereinek becslésével vagy egyszeri
  kalibrációval).

## Pálya és vonalak
- **Sárga kapuelőtér (6 m-es zóna)**: a kapuelőtér tömör sárgára festve mindkét
  oldalon. → **Hatás [A]/[orientáció]**: a sárga folt detektálása erős támpont a
  kapuelőtér és a térfél-orientáció azonosításához (melyik kapu melyik).
- **Több sportág vonalai egy padlón**: kézilabda + kosár + egyéb vonalak
  keverednek (piros/fekete/fehér). → **Hatás [A]**: az AUTOMATIKUS vonalfelismerés
  félrevezethető; a **kézi referencia-kalibráció** (a helyes kézilabda-pontokra
  kattintva) itt szükséglet, nem opció. A `standard_court_landmarks()` pontjait
  kell a képen kijelölni.

## Belógó / pályán kívüli objektumok
- **Kosárpalánkok**: üveg palánkok a falon és egy **nagy gördíthető kosárállvány
  az előtérben**, amely a pálya elé/fölé lóg, és időnként takarja a játékot. →
  **Hatás [B]/ROI**: ezek a `ExclusionZones` (kép-téri kizárás) tipikus esetei.
  Az előtéri állvány takarása miatt a mögötte elhaladó játékos rövid időre eltűnik
  → a `[F]` becslő hidalja át (ahogy a képből kicsúszásnál).
- **Kispad / cserejátékosok az oldalvonalnál**, valamint nézők. → **Hatás ROI**:
  a `CourtRegion` tűréssávját úgy kell hangolni, hogy a padon ülőket kizárja, de a
  vonalnál álló valódi játékost ne. (A jelenlegi 2 m jó kiindulás, finomítandó.)

## Szereplők és színek
> **FONTOS**: az alábbi színek CSAK ERRE A MECCSRE igazak — a csapatok, kapusok,
> bírók és a pálya színe meccsenként más. A rendszer ezért NEM drótoz be színeket;
> meccsenként `AppearanceProfile`-t tanul/állít be (lásd appearance.py). Az
> alábbiak példák, amik ennek a felvételnek a profilját adnák.
- **Csapatszínek**: A csapat **fehér**, B csapat **fekete** (fehér számokkal). →
  tiszta eset a mezszín-klaszterezéshez [D].
- **Kapusok zöldben** — jól elkülönülnek (egyezik a szabálykönyvi mezszín-
  szabállyal, RULES.md 4.).
- **Bírók SÁRGÁBAN, a pályán (2-3 fő)**: NEM játékosok! → **Hatás [D]**: a
  csapatosztályozónak fel kell ismernie és **ki kell szűrnie** a bírókat (sárga
  szín alapján). Ez új követelmény a felvétel alapján.
- **Mezszámok jól olvashatók** (pl. DEAC 50, 48, 53, 63, 37, 31). → **Hatás [C]**:
  a mezszám-OCR reális és erős ReID-jel.

## Teendők listája (a felvétel alapján, prioritással)
1. **[D] bíró-kiszűrés** (sárga, nem-játékos) — interfész kész (lásd teams.py),
   szín-logika a valódi modellnél.
2. **[A] kézi kalibráció** a `standard_court_landmarks()` pontjaival (a több-vonal
   miatt kötelező), + **lencsetorzítás-korrekció** a kép széle miatt.
3. **ROI** finomhangolás: az előtéri kosárállvány kizárási zónája + a kispad
   tűréssáv hangolása.
4. **Sárga 6 m-es zóna** mint orientációs/kalibrációs támpont (későbbi automatika).

## Bevezető (fade-in) képkockák — futási megfigyelés
- A felvétel **eleje sötét** (Filmora-átúszás, csak a vízjel látszik). A 0–14.
  képkockán a YOLO **0 személyt** észlel — ez NEM hiba, a bevezető sötét része.
- **Hatás**: `process_video.py` mostantól **automatikusan kihagyja** a sötét
  képkockákat (`_is_dark`, átlagfényesség < 40), és van `--start N` kapcsoló a
  bevezető átugrására. Így a `--max` nem fogy el üres képkockákra, és a
  birtoklás-elemzéshez összefüggő, tartalmas képkockákat kapunk.
- **Teszt-recept** (tartalmas rész, összefüggő képkockák a birtokláshoz):
  `python -m scripts.process_video BE.mp4 KI.json --weights yolov8n.pt
   --stride 1 --max 20 --start 180 --calib calib.json`

## Pásztázás-követés (pan tracking) — használat
- Kalibrációval (`--calib`) a feldolgozó mostantól **kompenzálja a kamera
  pásztázását**: képkockánként megbecsüli a kamera mozgását (Shi–Tomasi +
  Lucas–Kanade + RANSAC), és a detektált pontokat előbb visszaforgatja az
  alap-képkockába, csak utána vetíti a pályára.
- **FONTOS**: a 4 sarkot ahhoz a képkockához kell felvenni, AMELYIKTŐL a
  feldolgozás indul (`--start N`) — a kalibráló képernyő alapból a 180-as
  képkockát tölti be, a teszt-recept is `--start 180`-nal fut. Így a kettő
  ugyanarra a képre vonatkozik.
- A futás végén a napló kiírja az össz-elmozdulást px-ben (diagnosztika).
