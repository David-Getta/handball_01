"""
Valódi videó-feldolgozás — meccsvideóból Tracking JSON.

Két detektáló mód:
  - HOG (alap): az OpenCV BEÉPÍTETT ember-detektora — nincs letöltés, azonnal megy,
    de gyengébb (kis, gyors játékosokat nehezen lát). Első, valós próbához.
  - YOLO (--weights yolov8n.pt): pontosabb, de a súlyfájl kell hozzá (az egyes
    súly-letöltő hostok szervezeti policyból blokkoltak, ezért a .pt-t kézzel kell
    megadni; ultralytics + torch szükséges).

Követés: egyszerű legközelebbi-középpont társítás (stabil-ish id-k). Csapatszín:
2-means a törzs-színeken. Kalibráció EGYELŐRE nincs — kép→pálya egyszerű aránnyal
(x=px/W*40, y=py/H*20); a pontos pálya-koordináta a homográfiával jön ([A]).

Használat:
    python -m scripts.process_video BE.mp4 KI.json [--stride N] [--max N] [--weights yolov8n.pt]
"""

from __future__ import annotations

import math
import sys

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.calibration import COURT_LENGTH_M, COURT_WIDTH_M

PROC_WIDTH = 960  # feldolgozási szélesség (gyorsításhoz lekicsinyítünk)


def _torso_color(frame_bgr, x1, y1, x2, y2):
    import numpy as np
    h = y2 - y1
    ty1 = max(0, y1 + int(0.20 * h)); ty2 = max(0, y1 + int(0.55 * h))
    tx1 = x1 + int(0.25 * (x2 - x1)); tx2 = x1 + int(0.75 * (x2 - x1))
    crop = frame_bgr[ty1:ty2, tx1:tx2]
    if crop.size == 0:
        return (128.0, 128.0, 128.0)
    m = crop.reshape(-1, 3).mean(axis=0)
    return (float(m[2]), float(m[1]), float(m[0]))  # RGB


class _SimpleTracker:
    """Legközelebbi-középpont követő: stabil-ish id-k a detektált dobozokra."""
    def __init__(self, max_dist=80.0, max_gap=15):
        self.tracks = {}  # id -> [cx, cy, missed]
        self.next_id = 1
        self.max_dist = max_dist
        self.max_gap = max_gap

    def update(self, centers):
        assigned = {}
        used = set()
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
            self.tracks[best] = [cx, cy, 0]
            used.add(best)
            assigned[(cx, cy)] = best
        # elévülő trackek
        for tid in list(self.tracks):
            if tid not in used:
                self.tracks[tid][2] += 1
                if self.tracks[tid][2] > self.max_gap:
                    del self.tracks[tid]
        return assigned


def _detect_hog(hog, frame):
    rects, weights = hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.05)
    out = []
    for (x, y, w, h), score in zip(rects, weights):
        if score < 0.4:
            continue
        out.append((int(x), int(y), int(x + w), int(y + h)))
    return out


def process(video_path, out_path, stride=3, max_frames=400, weights=None):
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"videó: {W}x{H} @ {fps:.1f} fps, {total} frame")

    scale = PROC_WIDTH / W if W > PROC_WIDTH else 1.0
    pw, ph = int(W * scale), int(H * scale)

    use_yolo = weights is not None
    if use_yolo:
        from ultralytics import YOLO
        model = YOLO(weights)
    else:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    tracker = _SimpleTracker()
    raw = []
    all_colors = []
    fi = out_i = 0
    while out_i < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if fi % stride != 0:
            fi += 1
            continue
        fi += 1
        small = cv2.resize(frame, (pw, ph)) if scale != 1.0 else frame

        boxes = []  # (x1,y1,x2,y2) a KICSINYÍTETT képen
        if use_yolo:
            r = model.predict(small, classes=[0, 32], verbose=False)[0]
            if r.boxes is not None:
                for b in r.boxes:
                    if int(b.cls[0]) == 0:
                        boxes.append(tuple(int(v) for v in b.xyxy[0].tolist()))
        else:
            boxes = _detect_hog(hog, small)

        centers = [((x1 + x2) / 2.0, (y1 + y2) / 2.0) for (x1, y1, x2, y2) in boxes]
        ids = tracker.update(centers)
        persons = []
        for (x1, y1, x2, y2) in boxes:
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            tid = ids[(cx, cy)]
            color = _torso_color(small, x1, y1, x2, y2)
            all_colors.append(color)
            fx = (x1 + x2) / 2.0 / scale   # vissza az eredeti felbontásra
            fy = y2 / scale
            persons.append((tid, fx, fy, color))
        raw.append(persons)
        out_i += 1
    cap.release()
    print(f"feldolgozott frame: {len(raw)}, észlelt személy: {len(all_colors)}")

    # Csapatszín 2-means.
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

    meta = MatchMeta(match_id="video-1", home_team="Csapat A", away_team="Csapat B",
                     fps=fps / stride, frame_width=W, frame_height=H)
    frames = []
    for t, persons in enumerate(raw):
        players = [PlayerPosition(
            track_id=tid, team=team_of(color),
            x=fx / W * COURT_LENGTH_M, y=fy / H * COURT_WIDTH_M,
            source=PositionSource.MEASURED, confidence=1.0,
        ) for (tid, fx, fy, color) in persons]
        frames.append(Frame(t=t, players=players, ball=None))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(Match(meta=meta, frames=frames).to_json(indent=2))
    print(f"Tracking JSON kiírva: {out_path} ({len(frames)} frame)")


def main(argv):
    if len(argv) < 3:
        print("Használat: python -m scripts.process_video BE.mp4 KI.json [--stride N] [--max N] [--weights yolov8n.pt]")
        return 1
    stride = int(argv[argv.index("--stride") + 1]) if "--stride" in argv else 3
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 400
    w = argv[argv.index("--weights") + 1] if "--weights" in argv else None
    process(argv[1], argv[2], stride=stride, max_frames=mx, weights=w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
