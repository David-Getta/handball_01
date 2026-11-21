"""Lövés-profil valódi meccsről: a meccs-lövésjelölő címkéiből tanulva.

Bemenet: a `tools/cut_match_clips.py` klipjei (manifest.json + v/*.mp4) és a
meccs-lövésjelölő oldal jelölései (klipenként: elengedés kockája, a lövőre
kattintás helye, kartartás, lövőkéz, célzóna, kimenet).

Lépések:
  1. Testpont-kinyerés a klipek MINDEN kockáján, minden emberre (`extract`).
  2. A lövő követése a kattintástól előre és hátra (`track_shooter`).
  3. Kiértékelés, jelenet szerint csoportosítva (az ismétlés ugyanannak a
     lövésnek a másik képe → az élő párjával egy csoportba kerül):
       - LÖVŐ-VÁLASZTÁS: az elengedés kockáján a képen lévő emberek közül
         melyik lő? (tanított rangsoroló vs. "legnagyobb" / "legmagasabb kar")
       - ELENGEDÉS, KARTARTÁS (fent / oldalt), LÖVŐKÉZ: a `release` modul
         ugyanazon csöve, amely az UNIRI-klipeken is fut.
       - CÉLZÓNA: vízszintes (bal/közép/jobb) és függőleges (lent/közép/fent)
         harmad a lövő testtartásából — van-e benne jel a "mindig a
         leggyakoribb" tipphez képest?

A kartartás edzői besorolás: a fej mellől induló lövés is "oldalt" (a
jelölő megerősítése szerint), tehát két osztály: fent / oldalt.

    python -m hbd.match_shots extract --clips m1web --video meccs.mp4 --out m1_clip_poses
    python -m hbd.match_shots zoom --clips m1web --labels cimkek_m1/ --video meccs.mp4 --out m1_zoom
    python -m hbd.match_shots evaluate --clips m1web --poses m1_clip_poses --labels cimkek_m1/ --zoom m1_zoom --out res/
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .features import L_SH, L_WR, NOSE, R_SH, R_WR

# A pózbecslő az EREDETI (1920 px-es) felvételen fut, 1280-as bemenettel: a 960 px-es
# klipen széles képen a játékosok fele (köztük sokszor a lövő) nem kerül elő.
CLIP_IMGSZ = 1280
# A feldolgozott ablak a gombnyomáshoz képest (s). Az első meccsen az elengedés a
# nyomás előtt legfeljebb 0,4 s-mal, utána legfeljebb 1,2 s-mal volt.
WINDOW_S = (-1.2, 1.6)
# Követés: kockánként legfeljebb ennyit ugorhat a doboz közepe (doboz-magasságban),
# és ekkora méretváltozás fér bele (arány).
TRACK_JUMP = 0.45
TRACK_SIZE_RATIO = (0.6, 1.6)
# Ennyi ideig tartjuk meg a követést, ha a lövő egy-két kockán nem látszik (s).
TRACK_GAP_S = 0.2
# Az ismétlés legfeljebb ennyivel jön az élő lövés után (s) — csoportosításhoz.
REPLAY_MAX_LAG_S = 120.0
# Lövő-választás: a jelöltek mozgását ekkora ablakban nézzük az elengedés körül (s).
PICK_WINDOW_S = 0.3
FOLDS = 5


# ------------------------------------------------------------ 1. testpontok
def _orig_frames(video: str, t0: float, n: int):
    """n kocka az eredeti felvételből a t0 időponttól (BGR)."""
    import subprocess

    from .video import ffmpeg_exe, probe

    w, h, _ = probe(video)
    cmd = [ffmpeg_exe(), "-v", "error", "-ss", f"{max(0.0, t0):.3f}", "-i", video, "-frames:v", str(n),
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout
    k = len(raw) // (w * h * 3)
    return list(np.frombuffer(raw[:k * w * h * 3], np.uint8).reshape(k, h, w, 3))


def extract(clips_dir: Path, out_dir: Path, weights: str, device: str | None, imgsz: int = CLIP_IMGSZ,
            batch: int = 8, video: str | None = None) -> None:
    """Az összes ember testpontja a klipek kockáin → out_dir/<id>.npz (folytatható).

    video megadásával az eredeti felvétel kockáin, csak a gombnyomás körüli
    WINDOW_S ablakban; a kimenet `k0` mezője az ablak első kockája a klipben."""
    from ultralytics import YOLO

    from .video import iter_frames

    man = json.loads((clips_dir / "manifest.json").read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(weights)
    t0, done = time.time(), 0
    for c in man["clips"]:
        dst = out_dir / f"{c['id']}.npz"
        if dst.exists():
            continue
        fps = float(c["fps"])
        if video:
            k0 = max(0, c["press_k"] + int(round(WINDOW_S[0] * fps)))
            k1 = min(c["frames"], c["press_k"] + int(round(WINDOW_S[1] * fps)) + 1)
            frames = _orig_frames(video, c["t_start"] + k0 / fps, k1 - k0)
        else:
            k0, frames = 0, list(iter_frames(clips_dir / c["src"]))
        n, boxes, kps = [], [], []
        for i in range(0, len(frames), batch):
            for r in model.predict(frames[i:i + batch], imgsz=imgsz, conf=0.1, device=device, verbose=False):
                if r.keypoints is not None and len(r.boxes):
                    b = r.boxes.xyxy.cpu().numpy()
                    xy = r.keypoints.xy.cpu().numpy()
                    kc = r.keypoints.conf
                    kc = kc.cpu().numpy() if kc is not None else np.ones(xy.shape[:2])
                    k = np.concatenate([xy, kc[..., None]], -1)
                else:
                    b, k = np.zeros((0, 4)), np.zeros((0, 17, 3))
                n.append(len(b))
                boxes.append(b.astype(np.float32))
                kps.append(k.astype(np.float32))
        h, w = frames[0].shape[:2] if frames else (0, 0)
        np.savez_compressed(dst, n=np.array(n, np.int32), offsets=np.concatenate([[0], np.cumsum(n)]),
                            boxes=np.concatenate(boxes) if sum(n) else np.zeros((0, 4), np.float32),
                            kps=np.concatenate(kps) if sum(n) else np.zeros((0, 17, 3), np.float32),
                            size=np.array([w, h], np.int32), fps=np.float32(c["fps"]), k0=np.int32(k0))
        done += 1
        el = time.time() - t0
        print(f"  {c['id']}: {len(frames)} kocka · {el / done:.1f} s/klip", flush=True)


def load_clip_pose(path: Path) -> dict:
    z = np.load(path)
    return {k: z[k] for k in z.files}


def frame_people(p: dict, f: int) -> tuple[np.ndarray, np.ndarray]:
    a, b = p["offsets"][f], p["offsets"][f + 1]
    return p["boxes"][a:b], p["kps"][a:b]


# ------------------------------------------------------------ 2. a lövő követése
def _center(b: np.ndarray) -> np.ndarray:
    return np.stack([(b[..., 0] + b[..., 2]) / 2, (b[..., 1] + b[..., 3]) / 2], -1)


def pick_clicked(boxes: np.ndarray, x: float, y: float) -> int | None:
    """A kattintott ember: akinek a dobozában van a pont (több közül a középhez legközelebbi)."""
    if len(boxes) == 0:
        return None
    c = _center(boxes)
    hgt = np.maximum(boxes[:, 3] - boxes[:, 1], 1.0)
    inside = (boxes[:, 0] <= x) & (x <= boxes[:, 2]) & (boxes[:, 1] <= y) & (y <= boxes[:, 3])
    d = np.hypot(c[:, 0] - x, c[:, 1] - y) / hgt
    if inside.any():
        d = np.where(inside, d, np.inf)
    j = int(np.argmin(d))
    return j if d[j] <= 0.75 else None


def _step(prev_box: np.ndarray, boxes: np.ndarray, gap: int) -> int | None:
    if len(boxes) == 0:
        return None
    ph = max(prev_box[3] - prev_box[1], 1.0)
    hgt = boxes[:, 3] - boxes[:, 1]
    d = np.linalg.norm(_center(boxes) - _center(prev_box), axis=1) / ph
    ratio = hgt / ph
    ok = (d <= TRACK_JUMP * (1 + gap)) & (ratio >= TRACK_SIZE_RATIO[0]) & (ratio <= TRACK_SIZE_RATIO[1])
    if not ok.any():
        return None
    return int(np.argmin(np.where(ok, d, np.inf)))


def track_shooter(p: dict, k: int, x: float, y: float) -> dict | None:
    """A lövő testpont-sorozata a kattintás kockájától előre és hátra.

    Visszaad: {"start": első kocka, "kps": (T,17,3), "boxes": (T,4), "k": a kattintás
    kockája a sorozatban}; None, ha a kattintásnál nincs ember."""
    T = len(p["n"])
    k = int(min(max(k, 0), T - 1))
    boxes, kps = frame_people(p, k)
    j = pick_clicked(boxes, x, y)
    if j is None:
        return None
    max_gap = max(1, int(round(TRACK_GAP_S * float(p["fps"]))))
    seq = {k: (boxes[j], kps[j])}
    for direction in (1, -1):
        last_box, gap, f = boxes[j], 0, k + direction
        while 0 <= f < T and gap <= max_gap:
            bb, kk = frame_people(p, f)
            i = _step(last_box, bb, gap)
            if i is None:
                gap += 1
            else:
                seq[f] = (bb[i], kk[i])
                last_box, gap = bb[i], 0
            f += direction
    a, b = min(seq), max(seq) + 1
    out_b = np.zeros((b - a, 4), np.float32)
    out_k = np.zeros((b - a, 17, 3), np.float32)
    last = None
    for f in range(a, b):
        if f in seq:
            last = seq[f]
            out_b[f - a], out_k[f - a] = seq[f]
        else:                      # rövid kiesés: a doboz marad, a testpont "nem látszik"
            out_b[f - a] = last[0]
            out_k[f - a, :, :2] = last[1][:, :2]
    return {"start": a, "kps": out_k, "boxes": out_b, "k": k - a}


def refine_all(clips_dir: Path, poses_dir: Path, labels_dir: Path, video: str, out_dir: Path, weights: str,
               device: str | None = None) -> None:
    """A követett lövő testpontjai újra, a köré vágott, felnagyított képen (folytatható).

    Széles képen a lövő ~100 px magas, a teljes képen futó pózbecslő karja
    zajos. A UNIRI-csőhöz hasonlóan a lövő dobozát négyzetesen kivágjuk
    (CROP_SCALE), és a kivágáson fut újra a becslő (POSE_IMGSZ); a doboza
    alapján választjuk ki (pick_person)."""
    from .pose import PoseModel, pick_person, square_crop_box

    man = {c["id"]: c for c in json.loads((clips_dir / "manifest.json").read_text())["clips"]}
    labels = load_labels(labels_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = PoseModel(weights, device)
    t0, done = time.time(), 0
    for cid, lab in labels.items():
        dst, f = out_dir / f"{cid}.npz", poses_dir / f"{cid}.npz"
        if dst.exists() or not f.exists():
            continue
        p = load_clip_pose(f)
        k0, (w, h), fps = int(p.get("k0", 0)), p["size"], float(p["fps"])
        tr = track_shooter(p, lab["lovo"]["k"] - k0, lab["lovo"]["x"] * w, lab["lovo"]["y"] * h)
        if tr is None:
            continue
        T = len(tr["boxes"])
        frames = _orig_frames(video, man[cid]["t_start"] + (k0 + tr["start"]) / fps, T)
        crops, origins = [], []
        for img, box in zip(frames, tr["boxes"]):
            x0, y0, x1, y1 = square_crop_box(box, w, h)
            crops.append(np.ascontiguousarray(img[y0:y1, x0:x1]))
            origins.append((x0, y0))
        kps = tr["kps"][:len(crops)].copy()
        found = np.zeros(len(crops), bool)
        for t, (db, dk) in enumerate(model(crops)):
            ox, oy = origins[t]
            tb = tr["boxes"][t]
            j = pick_person(db, (tb[0] - ox, tb[1] - oy, tb[2] - ox, tb[3] - oy))
            if j is not None:
                kps[t] = dk[j]
                kps[t, :, 0] += ox
                kps[t, :, 1] += oy
                found[t] = True
        np.savez_compressed(dst, start=np.int32(tr["start"]), kps=kps, found=found)
        done += 1
        print(f"  {cid}: {len(crops)} kocka, {found.mean():.0%} újrabecsülve · "
              f"{(time.time() - t0) / done:.1f} s/klip", flush=True)


# ------------------------------------------------------------ ráközelítő követés
# A kivágás oldala a lövő doboz-magasságának ennyiszerese (korlátok px-ben, 1080p-n).
ZOOM_SIDE_X = 2.5
ZOOM_SIDE_PX = (280, 900)
ZOOM_IMGSZ = 640


def _zoom_detect(model, img, cx, cy, side):
    """Kivágás (cx, cy) körül, észlelés → dobozok, testpontok a teljes kép koordinátáiban."""
    h, w = img.shape[:2]
    half = side / 2
    x0, y0 = int(max(0, cx - half)), int(max(0, cy - half))
    x1, y1 = int(min(w, cx + half)), int(min(h, cy + half))
    (db, dk), = model([np.ascontiguousarray(img[y0:y1, x0:x1])])
    if len(db):
        db = db + [x0, y0, x0, y0]
        dk = dk.copy()
        dk[..., 0] += x0
        dk[..., 1] += y0
    return db, dk


def zoom_track(frames: list, k: int, x: float, y: float, model, fps: float) -> dict | None:
    """A lövő követése RÁKÖZELÍTVE: minden kockán az előző helye körüli kivágáson keresünk.

    Széles képen a lövő gyakran csak 60–100 px, a 6-os előtti tömegben a
    teljes képen futó becslő nem találja meg; a kivágáson (ZOOM_IMGSZ-re
    nagyítva) igen, és a testpontjai is pontosabbak. Indulás: a kattintás
    kockáján a kattintás körül; ha ott nincs találat, a szomszédos kockákon."""
    T = len(frames)
    k = int(min(max(k, 0), T - 1))
    start = None
    for dk_ in (0, -1, 1, -2, 2, -3, 3):
        f = k + dk_
        if not 0 <= f < T:
            continue
        for side in (ZOOM_SIDE_PX[0], 2 * ZOOM_SIDE_PX[0]):
            db, dkp = _zoom_detect(model, frames[f], x, y, side)
            j = pick_clicked(db, x, y)
            if j is not None:
                start = (f, db[j], dkp[j])
                break
        if start:
            break
    if start is None:
        return None
    max_gap = max(1, int(round(TRACK_GAP_S * fps)))
    seq = {start[0]: (start[1], start[2])}
    for direction in (1, -1):
        last, gap, f = start[1], 0, start[0] + direction
        while 0 <= f < T and gap <= max_gap:
            hgt = max(last[3] - last[1], 1.0)
            side = float(np.clip(ZOOM_SIDE_X * hgt, *ZOOM_SIDE_PX))
            c = _center(last)
            db, dkp = _zoom_detect(model, frames[f], c[0], c[1], side)
            i = _step(last, db, gap)
            if i is None:
                gap += 1
            else:
                seq[f] = (db[i], dkp[i])
                last, gap = db[i], 0
            f += direction
    a, b = min(seq), max(seq) + 1
    out_b = np.zeros((b - a, 4), np.float32)
    out_k = np.zeros((b - a, 17, 3), np.float32)
    last = None
    for f in range(a, b):
        if f in seq:
            last = seq[f]
            out_b[f - a], out_k[f - a] = seq[f]
        else:
            out_b[f - a] = last[0]
            out_k[f - a, :, :2] = last[1][:, :2]
    return {"start": a, "kps": out_k, "boxes": out_b, "k": k - a}


def zoom_track_all(clips_dir: Path, labels_dir: Path, video: str, out_dir: Path, weights: str,
                   device: str | None = None) -> None:
    """Minden címkézett klip lövőjének ráközelítő követése → out_dir/<id>.npz (folytatható)."""
    from .pose import PoseModel

    man = {c["id"]: c for c in json.loads((clips_dir / "manifest.json").read_text())["clips"]}
    labels = load_labels(labels_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = PoseModel(weights, device, imgsz=ZOOM_IMGSZ, batch=1)
    t0, done = time.time(), 0
    for cid, lab in labels.items():
        dst = out_dir / f"{cid}.npz"
        if dst.exists() or cid not in man:
            continue
        c = man[cid]
        fps = float(c["fps"])
        k0 = max(0, c["press_k"] + int(round(WINDOW_S[0] * fps)))
        k1 = min(c["frames"], c["press_k"] + int(round(WINDOW_S[1] * fps)) + 1)
        frames = _orig_frames(video, c["t_start"] + k0 / fps, k1 - k0)
        h, w = frames[0].shape[:2]
        tr = zoom_track(frames, lab["lovo"]["k"] - k0, lab["lovo"]["x"] * w, lab["lovo"]["y"] * h, model, fps)
        done += 1
        if tr is None:
            np.savez_compressed(dst, lost=True)
            print(f"  {cid}: NINCS lövő a kattintásnál", flush=True)
            continue
        np.savez_compressed(dst, lost=False, start=np.int32(tr["start"]), kps=tr["kps"], boxes=tr["boxes"],
                            k0=np.int32(k0), fps=np.float32(fps), size=np.array([w, h], np.int32))
        print(f"  {cid}: {len(tr['kps'])}/{len(frames)} kocka · {(time.time() - t0) / done:.1f} s/klip", flush=True)


# ------------------------------------------------------------ címkék, csoportok
def load_labels(labels_dir: Path) -> dict[str, dict]:
    """A meccs-lövésjelölő dokumentumai (klip → címke); a "rossz" klipek kimaradnak."""
    out = {}
    for f in sorted(Path(labels_dir).glob("*.json")):
        d = json.loads(f.read_text())
        d = d.get("data", d)
        if d.get("rossz") or d.get("elengedes") is None or not d.get("lovo"):
            continue
        out[d["klip"]] = d
    return out


def replay_groups(clips: list[dict]) -> dict[str, str]:
    """Klip → csoport: az ismétlés a legutóbbi előtte lévő élő lövés csoportjába kerül."""
    live = sorted((c["t_video"], c["id"]) for c in clips if not c.get("ismetles"))
    out = {}
    for c in clips:
        if not c.get("ismetles"):
            out[c["id"]] = c["id"]
            continue
        prev = [i for t, i in live if 0 <= c["t_video"] - t <= REPLAY_MAX_LAG_S]
        out[c["id"]] = prev[-1] if prev else c["id"]
    return out


def arm_class(label: str | None) -> str | None:
    """Edzői besorolás: a fej melletti lövés is oldalt."""
    if label is None:
        return None
    return "fent" if label == "fent" else "oldalt"


# ------------------------------------------------------------ 3a. lövő-választás
def candidate_features(p: dict, r: int) -> tuple[np.ndarray, np.ndarray]:
    """Az r. kocka minden emberére: mennyire néz ki lövőnek (C, F) + a dobozok (C, 4).

    Rövid követés az r körüli ablakban: a csukló legmagasabb pontja a vállhoz
    és a fejhez képest, a csukló legnagyobb sebessége (doboz-magasság / s), a
    doboz mérete a képen lévő legnagyobbhoz képest, és a hely a képen."""
    fps = float(p["fps"])
    w, h = p["size"]
    boxes, kps = frame_people(p, r)
    if len(boxes) == 0:
        return np.zeros((0, 9)), boxes
    win = max(1, int(round(PICK_WINDOW_S * fps)))
    T = len(p["n"])
    hmax = max((boxes[:, 3] - boxes[:, 1]).max(), 1.0)
    feats = []
    for j in range(len(boxes)):
        hj = max(boxes[j, 3] - boxes[j, 1], 1.0)
        traj = {r: kps[j]}
        for direction in (1, -1):
            last, f = boxes[j], r + direction
            while 0 <= f < T and abs(f - r) <= win:
                bb, kk = frame_people(p, f)
                i = _step(last, bb, 0)
                if i is None:
                    break
                traj[f] = kk[i]
                last = bb[i]
                f += direction
        up, head, spd = -1.0, -1.0, 0.0
        fs = sorted(traj)
        for f in fs:
            k = traj[f]
            for wr, sh in ((L_WR, L_SH), (R_WR, R_SH)):
                if k[wr, 2] > 0.3 and k[sh, 2] > 0.3:
                    up = max(up, (k[sh, 1] - k[wr, 1]) / hj)
                if k[wr, 2] > 0.3 and k[NOSE, 2] > 0.3:
                    head = max(head, (k[NOSE, 1] - k[wr, 1]) / hj)
        for f0, f1 in zip(fs, fs[1:]):
            a, b = traj[f0], traj[f1]
            for wr in (L_WR, R_WR):
                if a[wr, 2] > 0.3 and b[wr, 2] > 0.3:
                    spd = max(spd, np.linalg.norm(b[wr, :2] - a[wr, :2]) / hj * fps / (f1 - f0))
        cx, cy = (boxes[j, 0] + boxes[j, 2]) / 2 / w, (boxes[j, 1] + boxes[j, 3]) / 2 / h
        feats.append([up, head, spd, hj / hmax, hj / h, cx, cy, abs(cx - 0.5), len(fs) / (2 * win + 1)])
    return np.array(feats, np.float32), boxes


def evaluate_picker(items: list[dict], seed: int = 0) -> dict:
    """Lövő-választás csoportosított keresztvalidációval: top-1 találat a klipek között."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold

    data = [it for it in items if len(it["X"]) >= 1 and it["target"] is not None]
    groups = np.array([it["group"] for it in data])
    hit_model = np.zeros(len(data), bool)
    for tr, te in GroupKFold(FOLDS).split(np.zeros(len(data)), groups=groups):
        X = np.concatenate([data[i]["X"] for i in tr])
        y = np.concatenate([np.arange(len(data[i]["X"])) == data[i]["target"] for i in tr]).astype(int)
        clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                             class_weight="balanced", random_state=seed).fit(X, y)
        for i in te:
            hit_model[i] = int(np.argmax(clf.predict_proba(data[i]["X"])[:, 1])) == data[i]["target"]
    hit_big = np.array([int(np.argmax(it["X"][:, 3])) == it["target"] for it in data])
    hit_arm = np.array([int(np.argmax(it["X"][:, 0])) == it["target"] for it in data])
    n_people = np.array([len(it["X"]) for it in data])
    # a teljes képen elő sem került lövő: egyik módszer sem találhatja el
    n_all = len(items)
    return {"klipek": len(data), "osszes_klip": n_all, "lovo_nincs_a_jeloltek_kozt": n_all - len(data),
            "modell_az_osszesbol": float(hit_model.sum() / max(1, n_all)),
            "emberek_atlag": float(n_people.mean()),
            "veletlen": float((1 / n_people).mean()),
            "legnagyobb_ember": float(hit_big.mean()), "legmagasabb_kar": float(hit_arm.mean()),
            "modell": float(hit_model.mean())}


# ------------------------------------------------------------ 3c. célzóna
ZONE_H = {"bal": 0, "kozep": 1, "jobb": 2}
ZONE_V = {"lent": 0, "kozep": 1, "fent": 2}


def split_zone(z: str | None) -> tuple[int | None, int | None]:
    """'lent-jobb' → (függőleges, vízszintes); 'kozep' → (1, 1)."""
    if not z:
        return None, None
    if z == "kozep":
        return 1, 1
    v, hz = z.split("-")
    return ZONE_V[v], ZONE_H[hz]


def evaluate_zone(clips: list[dict], labels: dict, seed: int = 0) -> dict:
    """A célzóna harmadai a lövő testtartásából (a kézi elengedésnél) — van-e jel benne?"""
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import GroupKFold

    from .release import _clf, arm_hand_features

    rows = [(c, split_zone(labels[c["name"]].get("zona"))) for c in clips]
    rows = [(c, z) for c, z in rows if z[0] is not None]
    X = np.stack([np.concatenate([arm_hand_features(c["kps"], c["boxes"], c["fps"], c["release"]),
                                  [labels[c["name"]]["lovokez"] == "bal", labels[c["name"]]["lovo"]["x"],
                                   labels[c["name"]]["lovo"]["y"]]]) for c, _ in rows]).astype(np.float64)
    groups = np.array([c["scene_id"] for c, _ in rows])
    out = {"klipek": len(rows)}
    for name, idx in (("fuggoleges", 0), ("vizszintes", 1)):
        y = np.array([z[idx] for _, z in rows])
        pred = np.zeros_like(y)
        for tr, te in GroupKFold(FOLDS).split(X, y, groups):
            pred[te] = _clf().fit(X[tr], y[tr]).predict(X[te])
        major = np.bincount(y).argmax()
        out[name] = {"eloszlas": np.bincount(y, minlength=3).tolist(),
                     "modell": float((pred == y).mean()),
                     "modell_kiegyensulyozott": float(balanced_accuracy_score(y, pred)),
                     "mindig_leggyakoribb": float((y == major).mean()),
                     "kiegyensulyozott_veletlen": 1 / 3}
    return out


# ------------------------------------------------------------ összefűzés
def build(clips_dir: Path, poses_dir: Path, labels_dir: Path, zoom_dir: Path | None = None):
    """A címkézett klipekből: lövő-sorozatok (a `release` modul formátumában) és lövő-választási tételek."""
    man = json.loads((clips_dir / "manifest.json").read_text())
    labels = load_labels(labels_dir)
    groups = replay_groups(man["clips"])
    seqs, pick, rel_labels, lost = [], [], {}, []
    for c in man["clips"]:
        lab = labels.get(c["id"])
        f = poses_dir / f"{c['id']}.npz"
        if lab is None or not f.exists():
            continue
        p = load_clip_pose(f)
        k0 = int(p.get("k0", 0))
        w, h = p["size"]
        lv = lab["lovo"]
        tr = None
        if zoom_dir is not None and (zoom_dir / f"{c['id']}.npz").exists():
            z = np.load(zoom_dir / f"{c['id']}.npz")
            if not bool(z["lost"]) and int(z["k0"]) == k0:
                tr = {"start": int(z["start"]), "kps": z["kps"], "boxes": z["boxes"]}
        if tr is None:
            # a kattintás általában az elengedés kockáján van; ha az ablakon kívül esne, onnan indulunk
            tr = track_shooter(p, lv["k"] - k0, lv["x"] * w, lv["y"] * h)
        if tr is None:
            lost.append(c["id"])
            continue
        r = lab["elengedes"] - k0 - tr["start"]
        if not (0 <= r < len(tr["kps"])):
            lost.append(c["id"])
            continue
        seqs.append({"name": c["id"], "kps": tr["kps"], "boxes": tr["boxes"], "fps": float(p["fps"]),
                     "scene_id": groups[c["id"]], "release": r, "ismetles": bool(c.get("ismetles"))})
        rel_labels[c["id"]] = {"elengedes": r, "kartartas": arm_class(lab["kartartas"]),
                               "lovokez": lab["lovokez"]}
        # lövő-választás az elengedés kockáján: a célpont a követett lövő doboza
        X, boxes = candidate_features(p, lab["elengedes"] - k0)
        target = None
        if len(boxes):
            sb = tr["boxes"][r]
            ious = [_iou(sb, b) for b in boxes]
            target = int(np.argmax(ious)) if max(ious) > 0.5 else None
        pick.append({"name": c["id"], "X": X, "target": target, "group": groups[c["id"]]})
    return seqs, pick, rel_labels, labels, lost


def _iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def write_report(res: dict, out: Path, title: str) -> Path:
    pct = lambda v: f"{100 * v:.0f}%"  # noqa: E731
    pk, rl, z = res["lovo_valasztas"], res["release"], res["celzona"]
    e = rl["elengedes"]
    md = [f"# Lövés-profil valódi meccsről — {title}", "",
          f"{res['cimkezett']} címkézett lövés-klip, ebből {res['kovetett']} lövőjét sikerült végigkövetni "
          f"(élő + ismétlés; az ismétlés az élő párjával egy csoportban, {FOLDS}-szörös csoportosított "
          "keresztvalidáció).", "",
          "## Ki lő? (lövő-választás az elengedés pillanatában)", "",
          f"Átlagosan {pk['emberek_atlag']:.1f} ember a képen. {pk['lovo_nincs_a_jeloltek_kozt']} klipen a lövőt a "
          "teljes képen futó becslő meg sem találta (ott egyik módszer sem választhatja); a táblázat a többi "
          f"{pk['klipek']} klipre vonatkozik, a tanított rangsoroló az összesből: {pct(pk['modell_az_osszesbol'])}.", "",
          "| módszer | eltalálja a lövőt |", "|---|---|",
          f"| véletlen | {pct(pk['veletlen'])} |",
          f"| a legnagyobb ember | {pct(pk['legnagyobb_ember'])} |",
          f"| a legmagasabbra emelt kar | {pct(pk['legmagasabb_kar'])} |",
          f"| **tanított rangsoroló** | **{pct(pk['modell'])}** |", "",
          "## Elengedés pillanata (a lövő sorozatán)", "",
          "| | medián hiba | ±2 kockán belül | 100 ms-on belül |", "|---|---|---|---|",
          f"| tanított háló | {e['modell']['median_hiba_ms']:.0f} ms | {pct(e['modell']['pontos_2_kockan_belul'])} | "
          f"{pct(e['modell']['pontos_100ms_belul'])} |",
          f"| régi kézi szabály | {e['regi_szabaly']['median_hiba_ms']:.0f} ms | "
          f"{pct(e['regi_szabaly']['pontos_2_kockan_belul'])} | {pct(e['regi_szabaly']['pontos_100ms_belul'])} |", "",
          "## Kartartás (fent / oldalt — a fej melletti is oldalt) és lövőkéz", "",
          f"Osztályok: kartartás {rl['osztalyok']['kartartas']}, lövőkéz {rl['osztalyok']['lovokez']}.", "",
          "| | pontosság | kiegyensúlyozott |", "|---|---|---|"]
    for k, lab in (("modell", "kartartás — modell (a talált elengedésnél)"),
                   ("modell_kezi_elengedesnel", "kartartás — modell (a kézi elengedésnél)"),
                   ("mindig_fent", "kartartás — mindig „fent”")):
        v = rl["kartartas"][k]
        md.append(f"| {lab} | {pct(v['pontossag'])} | {pct(v['kiegyensulyozott'])} |")
    for k, lab in (("modell", "lövőkéz — modell"), ("mindig_jobb", "lövőkéz — mindig „jobb”")):
        v = rl["lovokez"][k]
        md.append(f"| {lab} | {pct(v['pontossag'])} | {pct(v['kiegyensulyozott'])} |")
    md += ["", "## Célzóna a testtartásból (harmadok)", "",
           "| | eloszlás (0/1/2) | modell | kiegyensúlyozott | mindig a leggyakoribb |", "|---|---|---|---|---|"]
    for k, lab in (("fuggoleges", "függőleges (lent/közép/fent)"), ("vizszintes", "vízszintes (bal/közép/jobb)")):
        v = z[k]
        md.append(f"| {lab} | {v['eloszlas']} | {pct(v['modell'])} | {pct(v['modell_kiegyensulyozott'])} | "
                  f"{pct(v['mindig_leggyakoribb'])} |")
    p = out / "match_shots.md"
    p.write_text("\n".join(md) + "\n")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lövés-profil valódi meccsről")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--clips", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--weights", default="yolo11n-pose.pt")
    e.add_argument("--device", default=None)
    e.add_argument("--imgsz", type=int, default=CLIP_IMGSZ)
    e.add_argument("--video", help="az eredeti meccsfelvétel (ajánlott: nagyobb felbontás)")
    v = sub.add_parser("evaluate")
    v.add_argument("--clips", required=True)
    v.add_argument("--poses", required=True)
    v.add_argument("--labels", required=True)
    v.add_argument("--out", required=True)
    v.add_argument("--title", default="1. meccs")
    v.add_argument("--epochs", type=int, default=120)
    v.add_argument("--zoom", help="a zoom lépés kimenete (a lövő ráközelítő követése)")
    zm = sub.add_parser("zoom")
    zm.add_argument("--clips", required=True)
    zm.add_argument("--labels", required=True)
    zm.add_argument("--video", required=True)
    zm.add_argument("--out", required=True)
    zm.add_argument("--weights", default="yolo11n-pose.pt")
    zm.add_argument("--device", default=None)
    rf = sub.add_parser("refine")
    rf.add_argument("--clips", required=True)
    rf.add_argument("--poses", required=True)
    rf.add_argument("--labels", required=True)
    rf.add_argument("--video", required=True)
    rf.add_argument("--out", required=True)
    rf.add_argument("--weights", default="yolo11n-pose.pt")
    rf.add_argument("--device", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        extract(Path(args.clips), Path(args.out), args.weights, args.device, args.imgsz, video=args.video)
        return 0
    if args.cmd == "zoom":
        zoom_track_all(Path(args.clips), Path(args.labels), args.video, Path(args.out), args.weights, args.device)
        return 0
    if args.cmd == "refine":
        refine_all(Path(args.clips), Path(args.poses), Path(args.labels), args.video, Path(args.out),
                   args.weights, args.device)
        return 0
    from .release import evaluate as eval_release

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    seqs, pick, rel_labels, labels, lost = build(Path(args.clips), Path(args.poses), Path(args.labels),
                                                 Path(args.zoom) if args.zoom else None)
    res = {"cimkezett": len(labels), "kovetett": len(seqs), "elveszett": lost,
           "lovo_valasztas": evaluate_picker(pick),
           "release": eval_release(seqs, rel_labels, epochs=args.epochs),
           "celzona": evaluate_zone(seqs, labels)}
    (out / "match_shots.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(write_report(res, out, args.title).read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
