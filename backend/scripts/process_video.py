"""
Valódi videó-feldolgozás — meccsvideóból Tracking JSON (YOLO + ByteTrack).

Detektáló módok:
  - YOLO (--weights yolov8n.pt): pontos; ByteTrack-kel stabil id-k. Nagy felbontású
    inferencia (imgsz) + alacsonyabb küszöb a kis/széli játékosok elkapásához.
    Bíró-szűrő (sárga mez) kiveszi a játékvezetőket.
  - HOG (alap): OpenCV beépített, letöltés nélkül; gyenge kis/gyors játékosokra.

FIGYELEM: kalibráció (homográfia) EGYELŐRE nincs — kép→pálya egyszerű aránnyal.
Emiatt a pályán KÍVÜLI személyek (kispad, edző, néző) is bekerülhetnek; ezt a
kalibráció + pálya-régió szűrő oldja meg ([A], CourtRegion). A perspektíva is
torzít kalibráció nélkül.

Használat:
    python -m scripts.process_video BE.mp4 KI.json [--weights yolov8n.pt]
        [--stride N] [--max N] [--imgsz 1280] [--conf 0.20]
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


def _process_yolo(video_path, weights, stride, max_frames, imgsz, conf,
                  court_poly=None, start=0, skip_dark=True):
    import numpy as np
    import cv2
    from ultralytics import YOLO
    model = YOLO(weights)
    poly = np.array(court_poly, np.int32) if court_poly else None
    raw, all_colors = [], []
    # EGY menet nagy felbontáson (1920) + alacsony küszöb (0.05), hogy a kis labdát
    # is elkapja; a JÁTÉKOSOKAT utólag szűrjük a megadott (magasabb) küszöbre, hogy
    # ne jöjjenek téves emberek. Így egy inferencia/frame (kétszer gyorsabb).
    # A `start` a bevezető (sötét) rész átugrására: csak innen dolgozunk fel.
    results = model.track(source=video_path, stream=True, persist=True,
                          classes=[0, 32], imgsz=1920, conf=0.05,
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
        raw.append((persons, ball_xy))
    if skipped_dark:
        print(f"sötét bevezető képkocka kihagyva: {skipped_dark}")
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
    hog = cv2.HOGDescriptor(); hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
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
        rects, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        boxes = [(int(x), int(y), int(x + w), int(y + h)) for (x, y, w, h), s in zip(rects, weights) if s >= 0.4]
        centers = [((x1 + x2) / 2.0, (y1 + y2) / 2.0) for (x1, y1, x2, y2) in boxes]
        ids = tracker.update(centers)
        persons = []
        for (x1, y1, x2, y2) in boxes:
            cx = (x1 + x2) / 2.0
            color = _torso_color(small, x1, y1, x2, y2)
            all_colors.append(color)
            persons.append((ids[(cx, (y1 + y2) / 2.0)], cx / scale, y2 / scale, color))
        raw.append((persons, None))
        out_i += 1
    cap.release()
    return raw, all_colors


def process(video_path, out_path, weights=None, stride=3, max_frames=400, imgsz=1280,
            conf=0.20, court_poly=None, calib_corners=None, start=0, skip_dark=True):
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    cap.release()
    print(f"videó: {W}x{H} @ {fps:.1f} fps | mód: {'YOLO' if weights else 'HOG'}")

    if weights:
        raw, all_colors = _process_yolo(video_path, weights, stride, max_frames, imgsz, conf,
                                        court_poly, start=start, skip_dark=skip_dark)
    else:
        raw, all_colors = _process_hog(video_path, stride, max_frames)
    print(f"feldolgozott frame: {len(raw)}, észlelt személy: {len(all_colors)}")

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
        court_pts = [(0.0, 0.0), (COURT_LENGTH_M, 0.0), (COURT_LENGTH_M, COURT_WIDTH_M), (0.0, COURT_WIDTH_M)]
        Himg2court = homography_from_points([tuple(p) for p in calib_corners], court_pts)
        region = CourtRegion(margin_m=2.0)
        def to_court(px, py):
            return apply_homography(Himg2court, px, py)

    def map_xy(px, py):
        if to_court is not None:
            return to_court(px, py)
        return (px / W * COURT_LENGTH_M, py / H * COURT_WIDTH_M)  # kalibráció nélkül: arányos

    meta = MatchMeta(match_id="video-1", home_team="Csapat A", away_team="Csapat B",
                     fps=fps / stride, frame_width=W, frame_height=H)
    frames = []
    dropped = 0
    for t, (persons, ball_xy) in enumerate(raw):
        players = []
        for (tid, fx, fy, color) in persons:
            cx, cy = map_xy(fx, fy)
            if region is not None and not region.contains(cx, cy):
                dropped += 1
                continue  # pályán kívül (kispad/edző/néző)
            players.append(PlayerPosition(track_id=tid, team=team_of(color),
                                          x=cx, y=cy, source=PositionSource.MEASURED, confidence=1.0))
        ball = None
        if ball_xy:
            bx, by = map_xy(ball_xy[0], ball_xy[1])
            ball = Ball(x=bx, y=by, confidence=1.0)
        frames.append(Frame(t=t, players=players, ball=ball))
    if region is not None:
        print(f"kalibrációval: pályán kívüli detektálás eldobva: {dropped}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(Match(meta=meta, frames=frames).to_json(indent=2))
    print(f"Tracking JSON kiírva: {out_path} ({len(frames)} frame)")


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
            start=opt("--start", 0, int), skip_dark="--no-skip-dark" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
