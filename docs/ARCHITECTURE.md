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
- **Pálya-kalibráció (homográfia)**: a képi koordinátákat a valós pálya
  felülnézeti (top-down) koordinátáira képezzük. Kézi keypoint-kalibráció
  először, később automatikus vonalfelismerés.
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

## Javasolt technológiai stack
- **Nyelv**: Python (ML pipeline), később TypeScript (web frontend).
- **ML**: PyTorch + Ultralytics (YOLO) + OpenCV.
- **Backend/API**: FastAPI.
- **Tárolás**: Postgres (struktúrált események/metrikák) + objektumtár a videókhoz.
- **Frontend 2D**: React + canvas/WebGL (vagy egyszerű matplotlib/streamlit a
  prototípushoz).
- **3D/VR**: Three.js (web) / Unity (VR).

## Adatmodell (a réteget összekötő szerződés)
A `Tracking` a központi objektum, amire minden épül:
```
Match
 ├── meta: id, csapatok, dátum, fps, felbontás
 └── frames: [ Frame ]
       Frame
        ├── t (időbélyeg / frame index)
        ├── players: [ {track_id, team, x, y}  ]   # x,y = pálya-koordináta (m)
        └── ball: {x, y} | null
```
Az MVP célja, hogy ezt a `Tracking` objektumot megbízhatóan előállítsa egy
videóból — innen minden további elemzés már adatfeldolgozás.
