# ml/ — gépi tanulás valódi videóból

Miért van ez külön? A `backend/` közel 500 kézzel írt szabályrétege
koordinátákon számol; ha a videóból nem jön megbízható felismerés, ezek a
levegőben lógnak. Ez a mappa a **látás**: a gép felvételekből tanulja meg a
kézilabdás mozdulatokat. A backend rétegei később erre épülnek rá
("gondolkodó" réteg). A kód független a backendtől, a tesztjei is külön
futnak — a backend tesztcsomagját nem érinti.

## Első cél: a lövés, a kapus szemszögéből

1. **Lövés vagy nem lövés**, és ha lövés: **felugrásos vagy helyből**.
2. Minden lövésre **kapus-profil** a testtartásból: lövőkéz, kartartás az
   elengedéskor (fent / oldalt / lent), felugrás, vállhelyzet, a lövő helye
   a képen.
3. Később (külön jelölés kell hozzá): hova megy a lövés, és a védőfalhoz
   képest hogyan.

## Adat: UNIRI-HBD

Ivašić-Kos, M., Pobar, M., University of Rijeka, DOI 10.21227/0g0a-fe06,
**CC BY 4.0** (üzleti célra is, forrásmegjelöléssel). 754 jelenet, 809
kivágott klip, 7 kategória (`crossing, defence, dribbling, jump-shot,
passing, running, shot`). Edzések, magasról, álló kamerával; a játékos
jellemzően ~110 px magas a képen.

A zip a repón KÍVÜL tartandó (2,8 GB). A `.gitignore` a videókat és a
`*.pt` súlyokat kizárja.

## Hogyan működik

```
kivágott klip ──sablon-egyezés──▶ hol áll a végrehajtó a teljes jeleneten
                                       │
teljes felbontású jelenet ──margós kivágás──▶ YOLO11-pose ──▶ 17 testpont / kocka
                                                                 │
                     ┌───────────────────────────────────────────┤
                     ▼                                           ▼
     normalizált sorozat + klip-jellemzők              kapus-profil (címke nélkül)
                     │
   osztályozók (logreg, döntési fák, kis konvolúciós háló)
   jelenet szerint csoportosított 5-szörös keresztvalidációval
```

A klipek a jelenet képpontjainak szó szerinti kivágásai, ezért a
végrehajtó a jelenetben pontosan visszakereshető (egyezés 1,000) — a
`player_detections` ezt nem mondja meg (nincs benne, ki a végrehajtó).

## Futtatás Kaggle-en (ajánlott, ingyenes GPU)

1. Töltsd fel a `uniri-hbd.zip`-et privát Kaggle-adathalmazként
   (*Datasets → New Dataset*; a Kaggle kibontja). Ez egyszeri.
2. *Code → New Notebook → File → Import Notebook* →
   `ml/kaggle/uniri_hbd_pose.ipynb`.
3. *Add Input* → az adathalmaz; *Accelerator*: GPU T4 x2; *Internet*: On.
4. *Run All*. A kimenet (`poses.npz`, `results/results.md`,
   `results/kapus_profilok.csv`, `results/model_*`) az *Output* fülön.

A notebook önálló (a csomag forrását `%%writefile` cellák írják ki), nem
kell hozzá a GitHub-repó. Forrásváltozás után újragenerálandó:

```bash
cd ml && python kaggle/build_notebook.py
```

### Nagyobb labdafelismerő GPU-n (`labda_gpu.ipynb`)

A kis labdafelismerő (YOLO11n, 320 px) helyett YOLO11s / YOLO11m, illetve
2× nagyított bemenet — mind ugyanazon a félretett 40 lövésen mérve, a v2
mellett. Bemenet: a labdajelölő címkéiből épített csomag (közvetítés-képek →
**privát** Kaggle-adathalmaz):

```bash
python tools/labda_kaggle_csomag.py --data balldata2 --ball-dir m1ball2 \
    --weights runs_ball/labda2/weights/best.pt --out labda_kaggle.zip   # ~165 MB
```

Kaggle: *Datasets → New Dataset* (privát) → a zip; *Import Notebook* →
`ml/kaggle/labda_gpu.ipynb`; *Add Input*, GPU T4 x2, Internet On;
*Save Version → Save & Run All* (kb. 2–3 óra, a háttérben fut). Kimenet:
`labda_eredmenyek.md` és a modellek (`labda_*.pt`).

## Helyben (CPU-n is megy, csak lassabb)

```bash
cd ml
pip install -r requirements.txt
# testpontok (CPU-n a kis modellel ~3 s/klip, a teljes adat ~40 perc)
python -m hbd.pose --data /út/a/handball_s --out out/poses.npz --device cpu --preview 4
# kiértékelés + végső modellek
python -m hbd.train --poses out/poses.npz --out out/results
# tesztek
python -m pytest -q
```

## Modulok

| modul | feladat |
|---|---|
| `hbd/dataset.py` | bejárás: klip → jelenet → kategória; feladat-címkék |
| `hbd/video.py` | kockák olvasása ffmpeg-gel (az OpenCV-dekóder itt összeomlott) |
| `hbd/locate.py` | a kivágott klip visszakeresése a jelenetben |
| `hbd/pose.py` | testpont-kinyerés YOLO11-pose-zal, gyorsítótárral (CLI) |
| `hbd/features.py` | normalizálás, sorozat, klip-jellemzők (idő másodpercben) |
| `hbd/goalkeeper.py` | kapus-profil: lövőkéz, kartartás, felugrás |
| `hbd/models.py` | kis időbeli konvolúciós háló (torch) |
| `hbd/train.py` | keresztvalidált kiértékelés, jelentés, végső modellek (CLI) |
| `hbd/release.py` | elengedés-pillanat + lövőkéz tanított modellje a kézi címkékből (CLI) |
| `hbd/match_pose.py` | teljes meccs: minden ritkított kockán az összes ember testpontja (CLI) |
| `hbd/broadcast.py` | közvetítési jelek: eredményjelző (látszik? változik az állás?) + kamera-mozgás (CLI) |
| `hbd/shot_detect.py` | lövésfelismerés a teljes meccsen: póz + rövid követés (kar-lendítés) + közvetítés (CLI) |
| `hbd/court.py` | ki áll a pályán: a nézők kiszűrése a láb alatti színből (CLI) |
| `hbd/match_shots.py` | lövés-profil a meccs-lövésjelölő címkéiből: ráközelítő lövő-követés, elengedés, kartartás, lövőkéz, célzóna, ki lő (CLI) |

## Teljes meccs: hol vannak a lövések?

```bash
python -m hbd.match_pose --video meccs.mp4 --out out/m1_pose.npz --stride 5 --imgsz 1280   # CPU-n ~50 perc/meccs
python -m hbd.broadcast  --video meccs.mp4 --out out/m1_broadcast.npz --stride 5           # ~6 perc
python -m hbd.shot_detect --pose out/m1_pose.npz --broadcast out/m1_broadcast.npz \
    --events cimkek/meccs1_esemenyek.json --out out/sd
```

Eredmény az első meccsen: `eredmenyek/loves_felismeres_meccs1.md`; lövés-profil: `eredmenyek/meccs1_lovesprofil.md`.

### Új meccs: vak jóslat, aztán összevetés

A kész (az 1. meccsen tanított) modell az új meccsen NEM tanul — így derül ki,
mit ér egy ismeretlen meccsen.

```bash
# 1) előkészítés egy paranccsal (póz, közvetítés, pálya-szűrő, jelölt lövések, klipek)
python tools/uj_meccs.py --video meccs2.mp4 --name m2 --model sd_final/shot_detect.joblib --out m2/
#    → m2/jeloltek/jelolt_lovesek.json: a VAK JÓSLAT — commitold, mielőtt az emberi jelölés megjön
# 2) az ember a meccsjelölővel végignézi a meccset (ez a mérce)
# 3) összevetés újratanítás nélkül
python -m hbd.shot_detect --pose m2/m2_pose.npz --broadcast m2/m2_broadcast.npz --court m2/m2_court.npz \
    --model sd_final/shot_detect.joblib --events cimkek/meccs2_esemenyek.json --live-only --out m2/osszevetes
```

A modell-csomag a beállítást is viszi (közvetítés-jelek, pálya-szűrő, jelölt-küszöb:
az 1. meccs keresztvalidációjában a 80%-os felidézéshez tartozó küszöb).
