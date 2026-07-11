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


def _resolve_weights(weights):
    """A súlyfájl (yolov8n.pt) tényleges elérési útja — hogy a BECSOMAGOLT
    (telepítés nélküli) kiadásban is megtalálja, ne kelljen letölteni.

    Sorrend: (1) ha a megadott út létezik, azt; (2) HANDBALL_WEIGHTS_DIR/<név>;
    (3) a PyInstaller csomag weights/<név> mappája (sys._MEIPASS); (4) az exe
    melletti weights/ mappa. Ha egyik sincs, marad az eredeti (ultralytics letölti).
    """
    import os
    import sys
    if not weights:
        return weights
    if os.path.exists(weights):
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
            return c
    return weights


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
                  court_poly=None, start=0, skip_dark=True, on_frame=None, pan=False):
    import os
    # Apple GPU (MPS): a ritka, nem-implementált műveletek essenek vissza CPU-ra
    # hiba helyett. A torch importja ELŐTT kell beállítani.
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import numpy as np
    import cv2
    from ultralytics import YOLO
    model = YOLO(_resolve_weights(weights))
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
    raw, all_colors = [], []
    # EGY menet nagy felbontáson (1920) + alacsony küszöb (0.05), hogy a kis labdát
    # is elkapja; a JÁTÉKOSOKAT utólag szűrjük a megadott (magasabb) küszöbre, hogy
    # ne jöjjenek téves emberek. Így egy inferencia/frame (kétszer gyorsabb).
    # A `start` a bevezető (sötét) rész átugrására: csak innen dolgozunk fel.
    results = model.track(source=video_path, stream=True, persist=True,
                          classes=[0, 32], imgsz=1920, conf=0.05, device=device,
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
                if cls == 0:
                    if bc < conf:  # játékos-küszöb (a low-conf téves emberek kiszűrése)
                        continue
                    if poly is not None and cv2.pointPolygonTest(poly, (float(fx), float(y2)), False) < 0:
                        continue
                    if b.id is None or _is_referee(img, x1, y1, x2, y2):
                        continue
                    color = _torso_color(img, x1, y1, x2, y2)
                    all_colors.append(color)
                    persons.append((int(b.id[0]), fx, y2, color))
                elif cls == 32:  # labda — a legmegbízhatóbbat tartjuk
                    if best_ball is None or bc > best_ball[0]:
                        best_ball = (bc, (x1 + x2) / 2.0, (y1 + y2) / 2.0)
        ball_xy = (best_ball[1], best_ball[2]) if best_ball else None
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
            track_smooth=True, calib_region="full", calib_rotate=False):
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
    report("A", 0.02, "kalibráció" if calib_corners else "kalibráció nélkül")

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

    if weights:
        # Pásztázás-követés csak kalibrációval együtt értelmes (ahhoz igazítunk).
        raw, all_colors = _process_yolo(video_path, weights, stride, max_frames, imgsz, conf,
                                        court_poly, start=start, skip_dark=skip_dark,
                                        on_frame=on_frame, pan=bool(calib_corners))
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

    # KALIBRÁCIÓ: ha van 4 sarok (kép-pixel), homográfiával pontos pálya-koordinátára
    # váltunk, és a pályán KÍVÜL esőket (kispad/edző) eldobjuk (CourtRegion).
    to_court = None
    region = None
    if calib_corners:
        from handball.pipeline._homography import homography_from_points, apply_homography
        from handball.pipeline.roi import CourtRegion
        court_pts = _calib_court_points(calib_region, calib_rotate)
        Himg2court = homography_from_points([tuple(p) for p in calib_corners], court_pts)
        region = CourtRegion(margin_m=2.0)
        def to_court(px, py):
            return apply_homography(Himg2court, px, py)

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
    meta = MatchMeta(match_id=match_id, home_team=home_team, away_team=away_team,
                     fps=fps / stride, frame_width=W, frame_height=H,
                     # A videó-visszajátszáshoz: honnan játszható le a jelenet.
                     video_path=str(video_path), start_frame=int(start),
                     stride=int(stride))
    frames = []
    dropped = 0
    for t, (persons, ball_xy, panH) in enumerate(raw):
        players = []
        for (tid, fx, fy, color) in persons:
            cx, cy = map_xy(fx, fy, panH)
            if region is not None and not region.contains(cx, cy):
                dropped += 1
                continue  # pályán kívül (kispad/edző/néző)
            players.append(PlayerPosition(track_id=tid, team=team_of(color),
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

    if estimate and calib_corners:
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
