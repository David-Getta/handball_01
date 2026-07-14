"""
Valódi videó-feldolgozás — meccsvideóból Tracking JSON (YOLO + ByteTrack).

Detektáló módok:
  - YOLO (--weights yolov8n.pt): pontos; ByteTrack-kel stabil id-k. Nagy felbontású
    inferencia (imgsz) + alacsonyabb küszöb a kis/széli játékosok elkapásához.
    Bíró-szűrő (sárga mez) kiveszi a játékvezetőket.
  - HOG (alap): OpenCV beépített, letöltés nélkül; gyenge kis/gyors játékosokra.

Kalibrációval (--calib, 4 pálya-sarok):
- homográfia: kép → valós méter-koordináták, a pályán kívüliek (kispad, edző)
  szűrése (CourtRegion),
- pásztázás-követés: a kamera mozgásának kompenzálása (a kalibráció a pásztázás
  közben is érvényes marad) — a sarkokat a --start képkockához kell felvenni,
- képen kívüli becslés: a képből kilógó játékosok pótlása mozgásmodellel
  (source=ESTIMATED, halványítva a kliensben); kikapcsolás: --no-estimate.
Kalibráció nélkül egyszerű arányos kép→pálya leképezés (pontatlan, csak teszthez).

Használat:
    python -m scripts.process_video BE.mp4 KI.json [--weights yolov8n.pt]
        [--stride N] [--max N] [--imgsz 1280] [--conf 0.20] [--start N]
        [--calib calib.json] [--no-skip-dark] [--no-estimate] [--no-ball-smooth] [--no-track-smooth]
"""

from __future__ import annotations

import math
import sys

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.calibration import COURT_LENGTH_M, COURT_WIDTH_M

PROC_WIDTH = 960  # HOG feldolgozási szélesség


def _torso_bounds(x1, y1, x2, y2):
    h = y2 - y1
    return (max(0, y1 + int(0.20 * h)), max(0, y1 + int(0.55 * h)),
            x1 + int(0.25 * (x2 - x1)), x1 + int(0.75 * (x2 - x1)))


def _torso_color(frame_bgr, x1, y1, x2, y2):
    import numpy as np
    ty1, ty2, tx1, tx2 = _torso_bounds(x1, y1, x2, y2)
    crop = frame_bgr[ty1:ty2, tx1:tx2]
    if crop.size == 0:
        return (128.0, 128.0, 128.0)
    m = crop.reshape(-1, 3).mean(axis=0)
    return (float(m[2]), float(m[1]), float(m[0]))  # RGB


def _is_referee(frame_bgr, x1, y1, x2, y2):
    """Sárga mez → játékvezető (kiszűrendő)."""
    import cv2
    import numpy as np
    ty1, ty2, tx1, tx2 = _torso_bounds(x1, y1, x2, y2)
    crop = frame_bgr[ty1:ty2, tx1:tx2]
    if crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    yellow = ((hsv[:, 0] >= 20) & (hsv[:, 0] <= 40) & (hsv[:, 1] > 90) & (hsv[:, 2] > 90)).mean()
    return yellow > 0.35


def _is_dark(img, thresh=40.0):
    """Sötét bevezető/átúszó képkocka? (átlagfényesség a küszöb alatt.)
    A meccsvideók elején gyakran van fade-in — ezeken nincs mit detektálni,
    ezért kihagyjuk, hogy a --max ne fogyjon el üres képkockákra."""
    return float(img.mean()) < thresh


def _weights_ok(path):
    """Épség-ellenőrzés: a .pt fájl valójában zip — a 'PK' kezdet MELLETT a
    zip központi jegyzékét is ellenőrizzük (zipfile). Egy FÉLBESZAKADT
    letöltés ugyanis 'PK'-val kezdődik, de a vége (a jegyzék) hiányzik —
    az ilyen fájl betöltéskor érthetetlen zlib-hibát ad ("Error -3 ...
    incorrect header check"). Inkább itt szűrjük ki, és újratöltjük.
    """
    import zipfile
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"PK":
                return False
        with zipfile.ZipFile(path) as z:
            z.namelist()  # csonka fájlnál (hiányzó jegyzék) itt dob
        return True
    except Exception:
        return False


def _resolve_weights(weights):
    """A súlyfájl (yolov8n.pt) tényleges elérési útja — hogy a BECSOMAGOLT
    (telepítés nélküli) kiadásban is megtalálja, ne kelljen letölteni.

    Sorrend: (1) ha a megadott út létezik ÉS ép, azt; (2) HANDBALL_WEIGHTS_DIR/
    <név>; (3) a PyInstaller csomag weights/<név> mappája (sys._MEIPASS);
    (4) az exe melletti weights/ mappa. Sérült jelöltet kihagyunk; ha egyik
    sincs, marad az eredeti név (az ultralytics letölti).
    """
    import os
    import sys
    if not weights:
        return weights
    if os.path.exists(weights) and _weights_ok(weights):
        return weights
    name = os.path.basename(weights)
    candidates = []
    env_dir = os.environ.get("HANDBALL_WEIGHTS_DIR")
    if env_dir:
        candidates.append(os.path.join(env_dir, name))
    meipass = getattr(sys, "_MEIPASS", None)  # PyInstaller kicsomagolt mappa
    if meipass:
        candidates.append(os.path.join(meipass, "weights", name))
    candidates.append(os.path.join(os.path.dirname(sys.executable), "weights", name))
    for c in candidates:
        if os.path.exists(c):
            if _weights_ok(c):
                return c
            print(f"FIGYELEM: sérült súlyfájl kihagyva: {c}")
    # Nincs ép helyi fájl → a puszta név marad, az ultralytics letölti egy
    # ÍRHATÓ helyre (a felhasználói adatmappába), nem az app csomagjába.
    try:
        from handball.storage import data_root
        dl_dir = data_root() / "weights"
        dl_dir.mkdir(parents=True, exist_ok=True)
        target = dl_dir / name
        if target.exists() and _weights_ok(str(target)):
            return str(target)
        import urllib.request
        url = ("https://github.com/ultralytics/assets/releases/latest/"
               f"download/{name}")
        print(f"súlyfájl letöltése: {url} → {target}")
        urllib.request.urlretrieve(url, str(target))
        if _weights_ok(str(target)):
            return str(target)
    except Exception as e:
        print(f"FIGYELEM: a súlyfájl letöltése nem sikerült: {e}")
    return weights


def _class_ids(names) -> tuple[list[int], list[int]]:
    """(játékos-osztályok, labda-osztályok) a modell osztálynevei alapján.

    Az előtanított COCO-modellben a person=0 és a sports ball=32; a saját,
    kézilabdára finomhangolt modellben (scripts/finetune.py) person=0 és
    ball=1. A neveket nézzük, így MINDKÉT modell külön beállítás nélkül
    működik — ismeretlen névlistánál a COCO-kiosztás a tartalék."""
    person, ball = [], []
    for k, v in (names or {}).items():
        n = str(v).strip().lower()
        if n == "person":
            person.append(int(k))
        elif "ball" in n:
            ball.append(int(k))
    return (person or [0]), (ball or [32])


def _pick_device():
    """A leggyorsabb elérhető inferencia-eszköz: CUDA (NVIDIA) → MPS (Apple
    Silicon GPU-ja, M1..M5) → CPU. Az MPS a Macen többszörös gyorsulást ad."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _calib_court_points(region="full", rotate=False):
    """A kalibráció 4 cél-pontja a pályán (méter), a kijelölt terület szerint.

    A képen bejelölt sarkok sorrendje: bal-fent, jobb-fent, jobb-lent, bal-lent.
    Pásztázó kameránál az induló képen sokszor csak az EGYIK TÉRFÉL látszik —
    ilyenkor a 4 pontot a térfél sarkaira (2 valódi sarok + a felezővonal két
    vége) kell húzni, és itt a térfélnek megfelelő cél-téglalapot használjuk.

    region: "full" (teljes pálya) | "left" (bal térfél) | "right" (jobb térfél)
    rotate: 180°-os forgatás — ha a kamera a túloldali lelátóról néz, és a
            pálya "fejjel lefelé" látszik a képen.
    """
    half = COURT_LENGTH_M / 2.0
    spans = {"full": (0.0, COURT_LENGTH_M), "left": (0.0, half), "right": (half, COURT_LENGTH_M)}
    x0, x1 = spans.get(region or "full", spans["full"])
    pts = [(x0, 0.0), (x1, 0.0), (x1, COURT_WIDTH_M), (x0, COURT_WIDTH_M)]
    if rotate:
        pts = pts[2:] + pts[:2]  # a sarok-hozzárendelés 180°-os forgatása
    return pts


def _normalize_max_frames(max_frames):
    """0/None/negatív képkocka-plafon → 'nincs plafon' (a teljes videó).

    Belül egy gyakorlatban elérhetetlen felső korláttal dolgozunk, így a
    feldolgozó ciklusoknak nem kell külön 'végtelen' ágat kezelniük.
    """
    if not max_frames or max_frames <= 0:
        return 10 ** 9
    return int(max_frames)


def _process_yolo(video_path, weights, stride, max_frames, imgsz, conf,
                  court_poly=None, start=0, skip_dark=True, on_frame=None,
                  pan=False, jersey_voter=None, ocr_every=5,
                  ball_recover=True):
    import os
    # Apple GPU (MPS): a ritka, nem-implementált műveletek essenek vissza CPU-ra
    # hiba helyett. A torch importja ELŐTT kell beállítani.
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import numpy as np
    import cv2
    from ultralytics import YOLO
    resolved = _resolve_weights(weights)
    try:
        model = YOLO(resolved)
    except Exception as first_err:
        # ÖNGYÓGYÍTÁS: ha a fájl a kezelt (letöltött) súly-mappánkban van és
        # nem tölthető be, sérültnek tekintjük — töröljük, újratöltjük, és
        # MÉG EGYSZER próbáljuk, mielőtt hibával leállnánk.
        retried = None
        try:
            from handball.storage import data_root
            managed = str(data_root() / "weights")
            if os.path.exists(resolved) and \
                    os.path.abspath(resolved).startswith(os.path.abspath(managed)):
                print(f"sérült súlyfájl törlése és újratöltése: {resolved}")
                os.remove(resolved)
                retried = _resolve_weights(weights)  # újratölti a friss fájlt
        except Exception:
            retried = None
        try:
            if retried is None:
                raise first_err
            model = YOLO(retried)
        except Exception as e:
            # Érthető hibaüzenet a felhasználónak (a nyers zlib/torch hiba
            # helyett), cselekvési javaslattal.
            raise RuntimeError(
                f"A detektáló modell nem tölthető be ({resolved}): {e} — "
                "a súlyfájl sérült lehet; internetkapcsolattal a rendszer "
                "magától letölti a jót, próbáld újra.") from e
    device = _pick_device()
    labels = {"cuda": "CUDA (NVIDIA GPU)", "mps": "MPS (Apple Silicon GPU)",
              "cpu": "CPU (lassabb — GPU-s gépen sokkal gyorsabb)"}
    print(f"inferencia-eszköz: {labels[device]}")
    poly = np.array(court_poly, np.int32) if court_poly else None
    # Pásztázás-követés: a kamera mozgását becsüljük, hogy a kalibráció a
    # pásztázás közben is érvényes maradjon (aktuális → alap képkocka mátrix).
    pan_tracker = None
    if pan:
        from handball.pipeline.pan_tracking import PanTracker
        pan_tracker = PanTracker()
    # Labda-visszaszerzés: elveszett labdánál a várható helye körüli KIS
    # kivágásban keresünk újra — ott a labda relatíve nagy, jobb az esély.
    reacquirer = None
    if ball_recover:
        from handball.pipeline.ball_reacquire import BallReacquirer
        reacquirer = BallReacquirer()
    raw, all_colors = [], []
    # EGY menet nagy felbontáson (1920) + alacsony küszöb (0.05), hogy a kis labdát
    # is elkapja; a JÁTÉKOSOKAT utólag szűrjük a megadott (magasabb) küszöbre, hogy
    # ne jöjjenek téves emberek. Így egy inferencia/frame (kétszer gyorsabb).
    # A `start` a bevezető (sötét) rész átugrására: csak innen dolgozunk fel.
    # Osztály-kiosztás a modell NEVEI alapján (COCO: person=0, sports ball=32;
    # saját finomhangolt modell: person=0, ball=1) — mindkettő működik.
    person_ids, ball_ids = _class_ids(getattr(model, "names", None))
    results = model.track(source=video_path, stream=True, persist=True,
                          classes=person_ids + ball_ids, imgsz=1920, conf=0.05,
                          device=device,
                          vid_stride=stride, tracker="bytetrack.yaml", verbose=False)
    kept = 0
    skipped_dark = 0
    for fi, r in enumerate(results):
        if fi * stride < start:  # a bevezető rész átugrása (kép-index alapján)
            continue
        if kept >= max_frames:
            break
        img = r.orig_img
        if skip_dark and _is_dark(img):  # sötét fade-in képkocka — kihagyjuk
            skipped_dark += 1
            continue
        kept += 1
        if on_frame is not None:  # élő haladás-jelzés a hívónak (job-státusz)
            on_frame(kept, max_frames)
        # Kameramozgás frissítése (az ALAP = az első feldolgozott képkocka; a
        # kalibrációt ehhez a képkockához kell felvenni — lásd --start).
        panH = None
        if pan_tracker is not None:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            panH = pan_tracker.update(gray)
        persons, best_ball = [], None
        if r.boxes is not None:
            for b in r.boxes:
                cls = int(b.cls[0])
                bc = float(b.conf[0])
                x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
                fx = (x1 + x2) / 2.0
                if cls in person_ids:
                    if bc < conf:  # játékos-küszöb (a low-conf téves emberek kiszűrése)
                        continue
                    if poly is not None and cv2.pointPolygonTest(poly, (float(fx), float(y2)), False) < 0:
                        continue
                    if b.id is None or _is_referee(img, x1, y1, x2, y2):
                        continue
                    color = _torso_color(img, x1, y1, x2, y2)
                    all_colors.append(color)
                    tid = int(b.id[0])
                    persons.append((tid, fx, y2, color))
                    # KÍSÉRLETI mezszám-OCR: ritkított mintavétellel (minden
                    # ocr_every-edik megtartott kockán) leolvasás + szavazat.
                    if jersey_voter is not None and kept % ocr_every == 0:
                        from handball.pipeline.jersey_ocr import (
                            read_jersey_number, torso_crop)
                        crop = torso_crop(img, (x1, y1, x2, y2))
                        if crop is not None:
                            r = read_jersey_number(crop)
                            if r is not None:
                                jersey_voter.add(tid, r[0], r[1])
                elif cls in ball_ids:  # labda — a legmegbízhatóbbat tartjuk
                    if best_ball is None or bc > best_ball[0]:
                        best_ball = (bc, (x1 + x2) / 2.0, (y1 + y2) / 2.0)
        ball_xy = (best_ball[1], best_ball[2]) if best_ball else None
        # Ha a teljes képen nem lett meg a labda, célzott újrakeresés a
        # várható helye körüli kivágásban (a kivágásban nagyobbnak látszik).
        if ball_xy is None and reacquirer is not None:
            roi = reacquirer.roi_for(fi * stride, img.shape[1], img.shape[0])
            if roi is not None:
                crop = img[roi[1]:roi[3], roi[0]:roi[2]]
                try:
                    rr = model.predict(crop, imgsz=640, conf=0.03,
                                       classes=ball_ids, device=device,
                                       verbose=False)
                    best = None
                    for r2 in rr:
                        if r2.boxes is None:
                            continue
                        for b2 in r2.boxes:
                            bc2 = float(b2.conf[0])
                            if best is None or bc2 > best[0]:
                                bx1, by1, bx2, by2 = \
                                    [float(v) for v in b2.xyxy[0].tolist()]
                                best = (bc2, (bx1 + bx2) / 2, (by1 + by2) / 2)
                    if best is not None:
                        ball_xy = reacquirer.map_back(roi, best[1], best[2])
                except Exception:
                    pass  # az újrakeresés hibája sosem állítja meg a feldolgozást
        if reacquirer is not None:
            reacquirer.note(fi * stride, ball_xy)
        raw.append((persons, ball_xy, panH))
    if skipped_dark:
        print(f"sötét bevezető képkocka kihagyva: {skipped_dark}")
    if pan_tracker is not None:
        tx, ty = pan_tracker.translation
        print(f"pásztázás-követés: össz-elmozdulás a végére: ({tx:.0f}, {ty:.0f}) px")
    return raw, all_colors


class _SimpleTracker:
    def __init__(self, max_dist=80.0, max_gap=15):
        self.tracks = {}; self.next_id = 1; self.max_dist = max_dist; self.max_gap = max_gap

    def update(self, centers):
        assigned, used = {}, set()
        for (cx, cy) in centers:
            best, bd = None, self.max_dist
            for tid, st in self.tracks.items():
                if tid in used:
                    continue
                d = math.hypot(cx - st[0], cy - st[1])
                if d < bd:
                    bd, best = d, tid
            if best is None:
                best = self.next_id; self.next_id += 1
            self.tracks[best] = [cx, cy, 0]; used.add(best); assigned[(cx, cy)] = best
        for tid in list(self.tracks):
            if tid not in used:
                self.tracks[tid][2] += 1
                if self.tracks[tid][2] > self.max_gap:
                    del self.tracks[tid]
        return assigned


def _process_hog(video_path, stride, max_frames):
    import cv2
    cap = cv2.VideoCapture(video_path)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    scale = PROC_WIDTH / W if W > PROC_WIDTH else 1.0
    # Az OpenCV 5-ből kikerült a HOG személydetektor — nélküle a tartalék mód
    # detektálás nélkül fut (üres kockák), de nem száll el. (Az éles út a YOLO.)
    try:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    except AttributeError:
        hog = None
    tracker = _SimpleTracker()
    raw, all_colors = [], []
    fi = out_i = 0
    while out_i < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if fi % stride != 0:
            fi += 1; continue
        fi += 1
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1.0 else frame
        if hog is not None:
            rects, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        else:
            rects, weights = [], []
        boxes = [(int(x), int(y), int(x + w), int(y + h)) for (x, y, w, h), s in zip(rects, weights) if s >= 0.4]
        centers = [((x1 + x2) / 2.0, (y1 + y2) / 2.0) for (x1, y1, x2, y2) in boxes]
        ids = tracker.update(centers)
        persons = []
        for (x1, y1, x2, y2) in boxes:
            cx = (x1 + x2) / 2.0
            color = _torso_color(small, x1, y1, x2, y2)
            all_colors.append(color)
            persons.append((ids[(cx, (y1 + y2) / 2.0)], cx / scale, y2 / scale, color))
        raw.append((persons, None, None))  # HOG-nál nincs labda és pásztázás-mátrix
        out_i += 1
    cap.release()
    return raw, all_colors


def process(video_path, out_path, weights=None, stride=3, max_frames=400, imgsz=1280,
            conf=0.20, court_poly=None, calib_corners=None, start=0, skip_dark=True,
            progress_cb=None, match_id="video-1", estimate=True,
            home_team="Csapat A", away_team="Csapat B", ball_smooth=True,
            track_smooth=True, calib_region="full", calib_rotate=False,
            calibs=None, jersey_ocr=False):
    """A videót Tracking-gé dolgozza fel; visszaadja a Match objektumot.

    Ha `out_path` meg van adva, a JSON-t fájlba is írja (CLI-hez). A `progress_cb`
    a feldolgozás állapotát jelzi a hívónak (a szerver ezt továbbítja a kliensnek):
    progress_cb(stage, progress, message) — stage a [A..H] lépéskód, progress 0..1.
    """
    import cv2
    import numpy as np

    def report(stage, prog, msg):
        if progress_cb is not None:
            progress_cb(stage, prog, msg)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    print(f"videó: {W}x{H} @ {fps:.1f} fps | mód: {'YOLO' if weights else 'HOG'}")

    # max_frames = 0/None → a TELJES videó (éles meccsnél ez az alapeset).
    # A haladás-kijelzéshez a videó hosszából becsüljük a feldolgozandó
    # kockák számát (a sötét kockák kihagyása miatt ez felső becslés).
    max_frames = _normalize_max_frames(max_frames)
    est_total = max(1, max(0, n_total - start) // max(1, stride)) if n_total > 0 else 0
    disp_total = min(max_frames, est_total) if est_total else max_frames

    # [A] kalibráció (ha van 4 sarok). A haladás nagy részét a detektálás adja.
    # A kalibrációk EGYSÉGES listája: vagy a `calibs` (1-2 bejegyzés, pl.
    # külön bal és jobb térfél, akár KÜLÖN képkockán bejelölve), vagy a régi
    # egy-kalibrációs paraméterek egyetlen bejegyzésként.
    calib_list = []
    if calibs:
        calib_list = [dict(c) for c in calibs if c.get("corners")]
    elif calib_corners:
        calib_list = [{"corners": calib_corners, "region": calib_region,
                       "rotate": calib_rotate, "frame": start}]
    report("A", 0.02, "kalibráció" if calib_list else "kalibráció nélkül")

    # [B]/[C] detektálás + követés — a képkockánkénti haladást ide képezzük le,
    # sebességgel és hátralévő idővel (teljes félidőnél ez órákban mérhető,
    # a felhasználónak látnia kell, mire számítson).
    import time as _time
    _t0 = _time.time()

    def on_frame(kept, total):
        # A kijelzéshez a becsült teljes darabszámot használjuk (a `total` a
        # belső plafon, ami teljes videónál csak egy óriási felső korlát).
        show = min(total, disp_total) if disp_total else total
        elapsed = _time.time() - _t0
        rate = kept / elapsed if elapsed > 0 else 0.0
        if rate > 0 and kept >= 3 and show > kept:  # az első pár kocka még torzít
            remain = (show - kept) / rate
            eta = f" · {rate:.1f} kocka/mp · ~{int(remain // 60)}:{int(remain % 60):02d} hátra"
        else:
            eta = ""
        frac = min(1.0, kept / max(1, show))
        report("B", 0.05 + 0.70 * frac, f"detektálás {kept}/{show}{eta}")

    # KÍSÉRLETI mezszám-OCR: feldolgozás közben leolvasás + szavazás; a
    # döntések a kész Match-re íródnak (a kézi hozzárendelés erősebb).
    jersey_voter = None
    if jersey_ocr:
        from handball.pipeline.jersey_ocr import JerseyVoter
        jersey_voter = JerseyVoter()

    if weights:
        # Pásztázás-követés csak kalibrációval együtt értelmes (ahhoz igazítunk).
        raw, all_colors = _process_yolo(video_path, weights, stride, max_frames, imgsz, conf,
                                        court_poly, start=start, skip_dark=skip_dark,
                                        on_frame=on_frame, pan=bool(calib_list),
                                        jersey_voter=jersey_voter)
    else:
        raw, all_colors = _process_hog(video_path, stride, max_frames)
    print(f"feldolgozott frame: {len(raw)}, észlelt személy: {len(all_colors)}")
    report("C", 0.78, "követés kész")

    # [D] csapatszín-klaszterezés (kapus/bíró külön kezelése a szín-profilban).
    report("D", 0.82, "csapatszín / kapus / bíró")
    centers2 = None
    if len(all_colors) >= 2:
        data = np.array(all_colors, dtype=np.float32)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, _, centers2 = cv2.kmeans(data, 2, None, crit, 5, cv2.KMEANS_PP_CENTERS)

    def team_of(color):
        if centers2 is None:
            return Team.HOME
        d0 = float(np.linalg.norm(np.array(color) - centers2[0]))
        d1 = float(np.linalg.norm(np.array(color) - centers2[1]))
        return Team.HOME if d0 <= d1 else Team.AWAY

    # Track-szintű TÖBBSÉGI csapat-döntés: a kockánkénti szín-döntés zajos
    # (árnyék/megvilágítás miatt egy játékos villoghatna a két csapat
    # között) — a track összes színmintája szavaz, a többség dönt.
    from handball.pipeline.teams import majority_team_by_track
    _colors_by_track: dict = {}
    for (persons_, _b_, _p_) in raw:
        for (tid_, _fx_, _fy_, color_) in persons_:
            _colors_by_track.setdefault(tid_, []).append(color_)
    team_of_track = majority_team_by_track(_colors_by_track, centers2)

    # KALIBRÁCIÓ: ha van 4 sarok (kép-pixel), homográfiával pontos pálya-koordinátára
    # váltunk, és a pályán KÍVÜL esőket (kispad/edző) eldobjuk (CourtRegion).
    to_court = None
    region = None
    if calib_list:
        from handball.pipeline._homography import (
            homography_from_points, apply_homography, invert_3x3, compose)
        from handball.pipeline.roi import CourtRegion
        region = CourtRegion(margin_m=2.0)

        # Minden kalibrációt az ALAP képkocka koordinátáira vezetünk vissza:
        # a kalibráció a saját képkockáján készült; a pásztázás-mátrix (G:
        # aktuális→alap) inverzével a H ∘ G⁻¹ már alap-pixelből ad pályametert.
        mappers = []  # (térfél x-tartománya, alapra vonatkoztatott H)
        for c in calib_list:
            pts = _calib_court_points(c.get("region", "full"), bool(c.get("rotate")))
            H = homography_from_points([tuple(p) for p in c["corners"]], pts)
            fidx = int(c.get("frame", start))
            if raw:
                idx = max(0, min(len(raw) - 1, round((fidx - start) / max(1, stride))))
                panH_at = raw[idx][2]
                if panH_at is not None and idx > 0:
                    H = compose(H, invert_3x3(panH_at))
            xs = [p[0] for p in pts]
            mappers.append((min(xs), max(xs), H))

        def to_court(px, py):
            # Az elsődleges kalibrációval számolunk; ha az eredmény egy MÁSIK
            # kalibráció térfelére esik, azzal pontosítunk (ott az élesebb).
            x, y = apply_homography(mappers[0][2], px, py)
            for (x0, x1, H) in mappers[1:]:
                if x0 - 1.0 <= x <= x1 + 1.0:
                    try:
                        return apply_homography(H, px, py)
                    except ValueError:
                        return (x, y)
            return (x, y)

    def map_xy(px, py, panH=None):
        if to_court is not None:
            if panH is not None:
                # Előbb vissza az ALAP képkocka koordinátáiba (a kamera mozgásának
                # kompenzálása), és csak utána a pálya-homográfia.
                from handball.pipeline.pan_tracking import apply_h
                px, py = apply_h(panH, px, py)
            return to_court(px, py)
        return (px / W * COURT_LENGTH_M, py / H * COURT_WIDTH_M)  # kalibráció nélkül: arányos

    # [E] pálya-koordináta (homográfia/arányos) + [F] pályán kívüliek szűrése.
    report("E", 0.90, "pálya-koordináta")
    # A meccs dátuma a videó metaadatából (mvhd creation_time, tartalék:
    # fájl-mtime) — a játékos-trend és a könyvtár időrendje erre épül.
    from handball.pipeline.video_meta import video_recording_date
    rec_date = video_recording_date(str(video_path))
    meta = MatchMeta(match_id=match_id, home_team=home_team, away_team=away_team,
                     fps=fps / stride, frame_width=W, frame_height=H,
                     # A videó-visszajátszáshoz: honnan játszható le a jelenet.
                     video_path=str(video_path), start_frame=int(start),
                     stride=int(stride), date=rec_date)
    if rec_date:
        print(f"meccs-dátum a videóból: {rec_date}")
    frames = []
    dropped = 0
    for t, (persons, ball_xy, panH) in enumerate(raw):
        players = []
        for (tid, fx, fy, color) in persons:
            cx, cy = map_xy(fx, fy, panH)
            if region is not None and not region.contains(cx, cy):
                dropped += 1
                continue  # pályán kívül (kispad/edző/néző)
            players.append(PlayerPosition(
                track_id=tid,
                # A track többségi csapata; tartalék a kockánkénti döntés.
                team=team_of_track.get(tid, team_of(color)),
                x=cx, y=cy, source=PositionSource.MEASURED, confidence=1.0))
        ball = None
        if ball_xy:
            bx, by = map_xy(ball_xy[0], ball_xy[1], panH)
            ball = Ball(x=bx, y=by, confidence=1.0)
        frames.append(Frame(t=t, players=players, ball=ball))
    if region is not None:
        print(f"kalibrációval: pályán kívüli detektálás eldobva: {dropped}")

    # [F] képen kívüli becslés — a pásztázó kamera képéből kilógó játékosokat
    # mozgásmodellel pótoljuk (source=ESTIMATED, csökkenő confidence), hogy a
    # felülnézeten a TELJES csapat látszódjon. Csak kalibrációval értelmes
    # (ott valós méter-koordináták vannak).
    report("F", 0.95, "képen kívüli becslés")
    match = Match(meta=meta, frames=frames)

    # Track-összefűzés: a takarásnál megszakadt követés automatikus
    # helyreállítása (óvatos küszöbökkel) — az elemzés egy játékost lásson.
    # A track-színminták is beleszólnak: eltérő mez → nincs összefűzés.
    from handball.pipeline.track_stitch import stitch_tracks
    _stitch_rename: dict = {}
    stitched = stitch_tracks(
        match, colors_by_track=_colors_by_track,
        jerseys_by_track=(jersey_voter.decisions()
                          if jersey_voter is not None else None),
        rename_out=_stitch_rename)
    if stitched:
        print(f"track-összefűzés: {stitched} megszakadt track helyreállítva")

    # Félidő-érzékelés + térfélcsere-normalizálás: teljes meccset egyben
    # tartalmazó felvételnél a 2. félidő koordinátáit tükrözi, hogy a
    # támadás-irányok egységesek legyenek. A kapus-azonosítás ELŐTT fut.
    from handball.pipeline.halftime import auto_normalize
    ht_info = auto_normalize(match)
    if ht_info is not None:
        if ht_info["swapped"]:
            print(f"félidő felismerve (frame {ht_info['halftime_t']}): "
                  f"térfélcsere normalizálva "
                  f"({ht_info['mirrored_frames']} kocka tükrözve)")
        else:
            print(f"félidő felismerve (frame {ht_info['halftime_t']}): "
                  "nincs térfélcsere-jel, a koordináták változatlanok")

    # Kapus-azonosítás pozíció-prior alapján: aki a mért idejének nagy
    # részét a kapuelőtérben tölti, role="kapus" jelölést kap. Az
    # összefűzés UTÁN fut (egyben látja a track teljes idejét).
    from handball.pipeline.goalkeeper import detect_goalkeepers
    gks = detect_goalkeepers(match)
    if gks:
        print("kapus-azonosítás: " + ", ".join(
            f"track {tid} ({share * 100:.0f}% kapuelőtér)"
            for tid, share in gks.items()))

    # KÍSÉRLETI mezszám-OCR: a szavazó döntéseinek ráírása a kockákra.
    if jersey_voter is not None:
        from handball.pipeline.jersey_ocr import apply_jersey_decisions
        # Az összefűzésnél beolvadt trackek OCR-döntéseit a megmaradó
        # azonosítóra visszük át — eddig ezek elvesztek.
        decisions = {}
        for tid, num in jersey_voter.decisions().items():
            decisions[_stitch_rename.get(tid, tid)] = num
        n_ocr = apply_jersey_decisions(match, decisions)
        if n_ocr:
            print(f"mezszám-OCR: {n_ocr} track kapott számot "
                  f"({jersey_voter.decisions()})")

    # Játékos-pálya simítás: a detektálási remegés (jitter) csökkentése — a
    # táv/sebesség statisztika ne a dobozok ugrálását mérje. Csak a mért
    # pozíciókat érinti, az éles irányváltást a kis ablak megőrzi.
    if track_smooth:
        from handball.pipeline.track_filter import smooth_player_tracks
        ts = smooth_player_tracks(match)
        if ts:
            print(f"játékos-simítás: {ts} pozíció simítva")

    # Labda-utómunka: a téves (kiugró) észlelések eldobása + a rövid hézagok
    # pótlása — a birtoklás/passz/lövés-felismerés folytonos labda-pályát igényel.
    if ball_smooth:
        from handball.pipeline.ball_filter import smooth_ball
        bs = smooth_ball(match)
        if bs["removed"] or bs["filled"]:
            print(f"labda-utómunka: {bs['removed']} kiugró eldobva, "
                  f"{bs['filled']} hézag-kocka pótolva")

    if estimate and calib_list:
        from handball.pipeline.estimation import augment_match_with_estimates
        added = augment_match_with_estimates(match)
        print(f"képen kívüli becslés: {added} becsült pozíció pótolva")

    # Minőség-önellenőrzés: a napló végén látszik, mennyire megbízható az eredmény.
    from handball.pipeline.quality import compute_quality_report
    q = compute_quality_report(match)
    print(f"minőség: {q['score']}/100 | játékos/kocka: {q['avg_measured_players']} | "
          f"labda-lefedettség: {q['ball_coverage_pct']}%")
    for w in q["warnings"]:
        print(f"  FIGYELEM: {w}")

    if out_path:  # CLI: fájlba is írjuk; a szerver közvetlenül a Match-et használja
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(match.to_json(indent=2))
        print(f"Tracking JSON kiírva: {out_path} ({len(frames)} frame)")

    # [H] statisztika/hőtérkép igény szerint (külön végpontok) — az adat kész.
    report("H", 1.0, f"kész ({len(frames)} frame)")
    return match


def main(argv):
    if len(argv) < 3:
        print("Használat: python -m scripts.process_video BE.mp4 KI.json [--weights W] "
              "[--stride N] [--max N] [--imgsz N] [--conf F] [--start N] [--no-skip-dark]")
        return 1
    def opt(name, default, cast):
        return cast(argv[argv.index(name) + 1]) if name in argv else default
    import json
    court_poly = json.load(open(argv[argv.index("--court") + 1])) if "--court" in argv else None
    # --calib: 4 kép-sarok [[x,y],...] a pálya (0,0),(40,0),(40,20),(0,20) sarkaihoz.
    calib = json.load(open(argv[argv.index("--calib") + 1])) if "--calib" in argv else None
    process(argv[1], argv[2],
            weights=opt("--weights", None, str),
            stride=opt("--stride", 3, int), max_frames=opt("--max", 400, int),
            imgsz=opt("--imgsz", 1280, int), conf=opt("--conf", 0.20, float),
            court_poly=court_poly, calib_corners=calib,
            start=opt("--start", 0, int), skip_dark="--no-skip-dark" not in argv,
            estimate="--no-estimate" not in argv,
            ball_smooth="--no-ball-smooth" not in argv,
            track_smooth="--no-track-smooth" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
