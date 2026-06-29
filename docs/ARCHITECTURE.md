# Architektúra

A rendszer egy **pipeline**: nyers videó → követés → taktikai értelmezés →
elemzés/szimuláció → megjelenítés. Minden réteg jól definiált adatot ad át a
következőnek, hogy a komponensek külön fejleszthetők és cserélhetők legyenek.

```
┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐   ┌────────────┐
│  Felvétel   │ → │  Észlelés &  │ → │   Taktikai    │ → │  Elemzés &   │ → │ Megjelenítés│
│ videó/LiDAR │   │  követés     │   │ értelmezés    │   │  szimuláció  │   │  2D/3D/VR  │
└─────────────┘   └──────────────┘   └───────────────┘   └──────────────┘   └────────────┘
```

## 1. Felvétel (Ingest)
- Broadcast vagy kézi kamera videó (MVP).
- Később: több kamera, majd LiDAR pontfelhő.
- Egységes belső formátum: idősoros frame-ek + metaadat (FPS, felbontás, csapatok).

## 2. Észlelés & követés (Perception)
- **Játékos- és labdadetektálás**: YOLO (Ultralytics) vagy RT-DETR.
- **Követés / ID-tartás**: ByteTrack / BoT-SORT — minden játékos stabil ID-t kap.
- **Csapatba sorolás**: mezszín-klaszterezés (k-means a játékos-bbox színhisztogramján).
  - **A színek MECCSENKÉNT változnak** (csapatok, kapusok, bírók, pálya) — sehol
    nincs bedrótozott szín. Minden meccshez egy `AppearanceProfile` (lásd
    `pipeline/appearance.py`), amit a meccs elejéből tanulunk vagy a felhasználó
    állít be. A besorolás a profil referenciaszíneihez a legközelebbit rendeli
    (szín-agnosztikus, tesztelt). A bírók is így, profil alapján szűrhetők ki.
- **Pálya-kalibráció (homográfia)**: a képi koordinátákat a valós pálya
  felülnézeti (top-down) koordinátáira képezzük. Kézi keypoint-kalibráció
  először, később automatikus vonalfelismerés.
  - **Pásztázó kamera esete** (a projekt aktuális felvétele): a kamera helyben
    marad és csak forog, ezért a képkockák tiszta homográfiával köthetők egy
    referencia-nézethez. Egyszer kalibrálunk kézzel, majd a frame→referencia
    homográfiát automatikusan propagáljuk. Részleges láthatóság: lásd lent és
    `MVP_PLAN.md`.
- **Képen kívüli játékosok becslése**: pásztázó kameránál a túloldali játékosok
  időnként kicsúsznak a képből. A látható játékosokat *mérjük*, a hiányzókat
  *becsüljük* (dinamikus létszám-állapot — NEM fix 7 fő, mert kiállítás és a
  kapus helyett felhozott 7. mezőnyjátékos változtatja — + szerep-/formációmodell
  + mozgáspredikció), explicit bizonytalanság-jelöléssel.
- **Kimenet**: minden játékos (id, csapat, x, y a pályán) minden frame-en +
  labdapozíció. Ez a rendszer "gerince" — a `Tracking` adatmodell.

## 3. Taktikai értelmezés (Tactics)
A követési adatból taktikai fogalmakat építünk:
- **Fázis-szegmentálás**: támadás / védekezés / átmenet (lerohanás).
- **Védekezési forma felismerése**: a védők pozícióiból (6-0, 5-1, 3-2-1…).
- **Tempó-metrikák**: támadások hossza, lerohanások aránya, sebességek, futott táv.
- **Figura- (set play) felismerés**: játékos-trajektóriák szekvencia-modellezése
  és klaszterezése (hasonló mozgásminták = ugyanaz a figura).
- **Eseményfelismerés**: gól, lövés, passz, eladott labda — temporális
  akciófelismerés.

## 4. Elemzés & szimuláció (Analytics)
- **Játékos-döntésmodell**: adott játékállásban a döntések eloszlása
  (passz/lövés/csel + cél) és azok **várható értéke** (kézilabda-EPV/xG).
  Ebből jön a "mi lett volna a legjobb opció".
- **Csapatprofil**: a 3. réteg metrikáiból összeálló stílus-ujjlenyomat.
- **Szimuláció**: az edző által tervezett figura lejátszása egy tanult
  ellenfélmodell ellen (ágens-alapú / RL — késői fázis).

## 5. Megjelenítés (Presentation)
- **2D taktikai nézet**: felülnézeti pálya, mozgó pontok, hőtérképek (MVP).
- **3D**: rekonstrukció LiDAR-ból / több kamerából.
- **VR**: Unity/Unreal kliens, a csapat "bejár" a pályára.
- **Élő dashboard**: valós idejű követés + javaslatok.

### Kliens–szerver szétválasztás (cross-platform cél)
A cél egy app, ami könnyen fut **Windows / Mac / iPad / Android tableten**. Ehhez
a kulcs, hogy a **nehéz feldolgozás nem a kliensen fut**:

```
┌──────────────────────────┐        ┌──────────────────────────────┐
│  Kliens app (vékony)      │ HTTP/  │  Backend (nehéz feldolgozás) │
│  Win / Mac / iPad /       │ ◄────► │  Python + YOLO + követés     │
│  Android tablet           │  WS    │  GPU-s gép / szerver         │
│  - taktikai nézet, lejátszó│       │  - videó-feldolgozás         │
│  - statisztikák           │        │  - Tracking előállítása      │
└──────────────────────────┘        └──────────────────────────────┘
```

- A **YOLO/követés/becslés** GPU-igényes → szerveren (vagy GPU-s desktopon) fut,
  nem tableten. A kliens csak a kész `Tracking`-et és a statisztikákat jeleníti
  meg → vékony lehet, és így könnyen hordozható minden platformra.
- A backend (Python/FastAPI) eleve platformfüggetlen.
- A **VR (Unity)** a 6–7. fázisban külön kliens-modul; az app-stack-választástól
  független.

### Desktop-first és LOKÁLIS mód (első tesztelés)
A rendszert **először asztali gépen / laptopon** teszteljük, ezért:
- A Flutter-kliens **desktop-first**: Windows/Mac/Linux appként is elsőrangú
  (nem csak tablet). A tablet (iPad/Android) ugyanabból a kódbázisból jön.
- **Lokális mód**: a backend és a kliens FUTHAT UGYANAZON a laptopon — nem kell
  külön szerver az első teszthez. A kliens a `localhost`-on éri el a backendet
  (REST/WebSocket). Erősebb GPU-s gép vagy felhő csak később, élesben kell.

## Javasolt technológiai stack
- **Backend / ML**: Python + PyTorch + Ultralytics (YOLO) + OpenCV.
- **API**: FastAPI (REST + WebSocket az élő adathoz).
- **Tárolás**: Postgres (struktúrált események/metrikák) + objektumtár a videókhoz.
- **Cross-platform kliens app** (Win/Mac/iPad/Android tablet): **Flutter**
  *(eldöntve)* — egy Dart kódbázis, natívra fordul mind a 4 platformra; legjobb
  érintő/tablet UX és erős egyedi 2D rajzolás (`CustomPainter`/canvas) a taktikai
  nézethez. A backenddel REST + WebSocket kapcsolaton át kommunikál.
- **3D/VR**: Three.js (web 3D) / Unity (VR) — külön kliens-modul, későbbi fázis.

> A kliens csak a backend kimenetét (`Tracking` + statisztikák) fogyasztja, ezért
> az MVP backendje és `Tracking` modellje a Flutter-klienstől függetlenül
> építhető és tesztelhető.

## Adatmodell (a réteget összekötő szerződés)
A `Tracking` a központi objektum, amire minden épül:
```
Match
 ├── meta: id, csapatok, dátum, fps, felbontás
 └── frames: [ Frame ]
       Frame
        ├── t (időbélyeg / frame index)
        ├── players: [ {track_id, team, x, y, source, confidence} ]
        │     # x,y = pálya-koordináta (m)
        │     # source = measured | estimated  (látható vagy becsült)
        │     # confidence ∈ [0,1]  (becsült játékosnál idővel csökken)
        └── ball: {x, y} | null
```
Az MVP célja, hogy ezt a `Tracking` objektumot megbízhatóan előállítsa egy
videóból — innen minden további elemzés már adatfeldolgozás.
