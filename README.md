# handball_01 — Kézilabda elemző AI

## Letöltés (Windows / Mac) — mint egy Steam-játék

1. Nyisd meg a repo **Releases** oldalát (GitHub → jobb oldalt "Releases").
2. Töltsd le a legfrissebbet: Windowsra a **`SportMachine-Setup.exe`**-t, Macre a **`SportMachine-macOS.zip`**-et.
3. Dupla kattintás → Tovább → Telepítés → indul. Ennyi.

Nem kell hozzá Python, Flutter vagy bármilyen fejlesztői eszköz — a telepítő a
teljes programot (felület + elemző motor + AI-modell) egyben tartalmazza.
Laikus útmutató: [`TELEPITES.md`](TELEPITES.md).

> A telepítőt a GitHub Actions automatikusan gyártja
> ([.github/workflows/release.yml](.github/workflows/release.yml)):
> kézzel az Actions fülről indítható, kiadás pedig egy `v*` címke
> (`git tag v0.1.0 && git push origin v0.1.0`) pusholásával készül.

Videó- (és később LiDAR-) alapú elemző platform kézilabdára: csapatstílus
tanulása, egyéni játékos-döntéselemzés, figura-szimuláció ellenfél ellen, 3D/VR
bejárható meccsek és élő meccskövetés javaslatokkal.

## Dokumentáció
- [`docs/VISION.md`](docs/VISION.md) — mit építünk és miért (a teljes vízió).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — a pipeline rétegei és a stack.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — fázisokra bontott útiterv.
- [`docs/MVP_PLAN.md`](docs/MVP_PLAN.md) — az 1. fázis (MVP) részletes terve.
- [`docs/RULES.md`](docs/RULES.md) — a követéshez releváns szabály-kivonat.
- [`docs/FOOTAGE_NOTES.md`](docs/FOOTAGE_NOTES.md) — a valódi felvétel megfigyelései
  és azok hatása a tervre (pásztázó kamera, sárga 6 m, több-vonal, kosárpalánk,
  sárga bírók, GoPro-torzítás).
- [`docs/BROADCAST_AND_SENSORS.md`](docs/BROADCAST_AND_SENSORS.md) — a jövőbeli
  bemenetek útiterve: telepített több-kamerás + lidar arénarendszer és
  TV-közvetítés-elemzés (ellenfél-felderítéshez).

## Kód
- [`backend/`](backend/) — szerveroldali Python csomag: a központi `Tracking`
  adatmodell (JSON, a kliens-szerződés), a `[A]–[H]` pipeline-váz, a meccs-
  szimulátor és a FastAPI. Lásd [`backend/README.md`](backend/README.md).
- [`client/`](client/) — Flutter kliens (desktop-first): a felülnézeti taktikai
  nézet, ami a backend Tracking JSON-ját rajzolja ki (backend nélkül beágyazott
  demóval is fut). Lásd [`client/README.md`](client/README.md).

## Hol tartunk
A rendszer **működő, telepíthető alkalmazás** (v0.1.28 kiadva Windows- és
macOS-telepítővel, SportMachine néven; a fejlemények a CHANGELOG-ban):

- **Feldolgozás**: YOLO + ByteTrack követés, kézi 4-sarkos kalibráció
  méter-térbe (a hatpontos összenézet a két bekalibrált térfelet egymás
  mellett mutatja), pásztázás-kompenzáció, csapat-szétválasztás, kapus- és
  mezszám-felismerés; megszakítás-biztos (checkpoint, folytatás).
- **AI-elemzés**: ~130 magyarázható réteg — események (gól/lövés/passz/
  labdaeladás), xG és ziccerek, **befejezés-profil** (lövés-távolság,
  kapu-sarok, szélső-hatékonyság, kapus gyenge sávja), **építkezés**
  (passz-irány, gólpassz-forrás, passz-láncok, beálló-terhelés),
  védekezés-kép (blokkok, őrzési párok, labdaszerzők, labdaeladók,
  betörés-folyosók, védekezési vonal magassága, nyomás), momentum
  (sorozatok, fordulópont, vezetés-váltások, hajrá-emberek, gólcsend),
  kondíció, fáradás és rotáció-mélység, passz- és gólpassz-hálózat,
  poszt-becslés, hetesek iránnyal, kapusonkénti GSAx és kapus-kimozdulás,
  átmenet-támadás/-védekezés, fegyelem (kiülők/kiharcolók), szünet utáni
  kezdés, előny-kezelés, cserék, időkérések, valamint az újabb rétegek:
  második roham (lepattanó-harc), kezdés-profil (nyitógól), lövőerő-esés,
  gól-koncentráció, támogatás-távolság (izoláció), területi fölény,
  fal-szélesség, engedett lövésminőség, passz-tempó, falba lövés,
  lövés-időzítés, védekezés-fellazulás, időkérés-mérleg,
  labdabiztonság-esés, kapus-forma félidőnként, előny-őrzés,
  kihagyott ziccer ára, tempó-esés, félidei fordítás, holtpont-mérleg,
  sorozat-törés, bravúr utáni lendület, befejezés-esés, fegyelem-esés,
  gól utáni elalvás, szoros meccs-mérleg, félidő-zárás, hetes-védés,
  kapuscsere-hatás, célzás-pontosság, oldal-részrehajlás,
  ritmus-egyhangúság, lövő-koncentráció, kapus-gyengeoldal,
  eladás-időzítés, pressz-tűrés, lepattanó-fal, asszist-függés,
  területi-fölény-esés, kapus-indítás hossza, eladás-büntetés,
  engedett-oldal, gólcsend-anatómia, fal-rés, támadó-mozgás,
  indítás-biztonság, beálló-védekezés, elsütés-idő, középkezdés-tempó,
  előkészítő-függés, gól-előkészítés hossza, lerohanás-védés,
  oldalváltás, elzárás-használat, elzárás-védekezés, passz-kockázat,
  hajrá-lövésválasztás, ellen-press, fölény-befejezés,
  hátrány-támadás, hajrá-eladás, kapus-indítás iránya, kettőzés,
  kapus szabad lövés ellen, emberelőny-védekezés, drága eladók,
  szélső-védekezés, lövő-kapuoldal, lövő-erő, játékos-mérleg,
  célba vett védő.
  Minden réteg magyar edzői nyelven indokol.
- **Felderítés és tervezés**: több-meccses ellenfél-profil pontos
  (count-alapú) összegzéssel, edzői kulcsok, meccsterv-illesztés (94 páros
  szabály), fejlődés-követés trenddel, edzés-fókusz (115 szabály,
  szezon-szintű visszatérő gyengeségekkel), élő jelzések a padnak (félidei
  emberfogás/beálló/rotáció-kép, hajrá-protokoll).
- **Kimenetek**: edzői összefoglaló a meccs történetével, nyolc
  nyomtatható riport (meccs, felderítő, játékos-lap, szezon
  játékos-lap, fejlődés, szezon — hazai/idegen és ellenfél-mérleggel,
  egymás ellen — visszavágó-meccstervvel, toplisták), tematikus
  klip-csomagok (kulcs-pillanatoktól a beállós gólokig), Excel-kész
  CSV, teljes meccs-csomag zip, szezon-toplisták a kezdőlapon.
- **Új bemenetek (előkészítve)**: TV-közvetítés előfeldolgozás
  (vágás/totálkép-szűrő, pályavonal-felismerés), több-nézetes fúzió
  (`POST /matches/fuse`) és lidar-finomítás — részletek a
  [`docs/BROADCAST_AND_SENSORS.md`](docs/BROADCAST_AND_SENSORS.md)-ben.
- **Minőség**: 1724 automata teszt; pontosság-validáció kézi eseménylista
  ellen (API + parancssori eszköz); réteg-megbízhatósági önjelentés
  (mihez van elég minta az adott meccsen).

## Elv
Alulról építkezünk. A megbízható 2D követés a rendszer gerince; minden további
elemzés (taktika, döntések, szimuláció, VR, élő javaslat) erre épül.

## Pályázat

A projekt EU-forrásból való továbbfejlesztésének tervei:
- **EIC Pre-accelerator** (widening-országok belépő programja, 300–500 k€,
  TRL 4→6): `docs/PALYAZAT_EIC_PRE_ACCELERATOR.md`
- **EIC Accelerator** (a következő lépcső): `docs/PALYAZAT_EIC.md`
- Angol projekt-összefoglaló a Part B-hez: `docs/EXECUTIVE_SUMMARY_EN.md`
- Part B vázlat (EN): `docs/PART_B_VAZLAT_EN.md` · Költségterv-vázlat:
  `docs/KOLTSEGTERV_VAZLAT.md` · Pitch deck-vázlat:
  `docs/PITCH_DECK_VAZLAT.md`
- Versenytárs-tábla: `docs/VERSENYTARS_TABLA.md`
- Generált tény-lap (rétegek, tesztek, szabályok — őr-teszttel
  frissen tartva): `docs/SZAMOK.md`
- Réteg-katalógus (mind a 296 réteg egy helyen, mit mér):
  `docs/RETEG_KATALOGUS.md`
- Pilot LOI-sablon: `docs/LOI_SABLON.md` · Annotációs útmutató:
  `docs/ANNOTACIOS_UTMUTATO.md` · Mérési jegyzőkönyv:
  `docs/MERESI_JEGYZOKONYV.md`
- Cél: beadás 2027. május 5-től (részletek a Pre-accelerator tervben)
