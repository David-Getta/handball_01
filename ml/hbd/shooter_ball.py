"""Ki lő? — a lövő a LABDÁBÓL, kézi kattintás nélkül.

A testpontokból tanult lövő-választó (match_shots.evaluate_picker) a klipek
egy részén el sem jut a lövőig: a teljes képen futó pózbecslő a lövőt sokszor
nem találja meg külön emberként (76/184 klip), és ahol igen, ott is csak 55%.
Itt a labdafelismerő (hbd.ball) dönt: az elengedés körül a labda a lövő
kezében van / épp elválik tőle, tehát a lövő az, akinek a CSUKLÓJA a labdához
legközelebb van.

Menet klipenként (a meccs-lövésjelölő elengedés-kockája körül, ±WIN kocka):
  1. a labdafelismerő a teljes 1920×1080 kockán, TILE px-es átfedő csempéken,
     natív léptékben (a labdajelölő videói is natív 640 px-es kivágások),
  2. minden emberre pontszám: max_labda megbízhatóság × exp(−(d/SIGMA)²), ahol
     d a legközelebbi csukló távolsága a labdától, az ember magasságában mérve,
  3. a lövő a legnagyobb pontszámú ember (ha van PICK_MIN fölött); ha senki,
     a lövő HELYE a legbiztosabb labda (ez a ráközelítő követés kiindulópontja
     lehet — a kattintás helyett).

Célzóna (lent / fent) a labda repülési irányából: a lövő köré vágott
kivágáson a labdát kockáról kockára követjük (hbd.ball.track), és az elválás
→ repülés elmozdulásából becslünk — ugyanazokkal a jellemzőkkel, mint a kézi
labdapontokkal mért 76%.

    python -m hbd.shooter_ball --video meccs.mp4 --clips m1web/manifest.json \
        --poses m1_clip_poses --zoom m1_zoom2 --labels cimkek/meccs1_lovesek_cimkek.json \
        --ball-labels cimkek/meccs1_labda_cimkek.json --ball-manifest m1ball2/ball_manifest.json \
        --weights runs_ball/labda2/weights/best.pt --cache sb_cache --out res/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

# Csempe natív képpontban (mint a labdajelölő 640 px-es kivágásai) és az átfedés aránya.
TILE = 640
TILE_OVERLAP = 1 / 3
# Az elengedés körüli kockák (a jelölt elengedéstől, kockában).
WIN = (-2, 2)
# A labdajelöltek alsó megbízhatósága, és az összevonás sugara (px) a csempék közt.
CONF = 0.05
NMS_PX = 12.0
# Csukló–labda távolság léptéke az ember magasságában (0,25 × ~180 px ≈ 45 px).
SIGMA = 0.25
WRIST_CONF = 0.2
# Kockák összevonása emberenként: "max" (a legjobb kocka) vagy "sum" (a lövő keze több kockán át a labdánál).
ACCUM = "sum"
# Ennél kisebb pontszámmal nem választunk embert (akkor a labda helye a lövő helye).
PICK_MIN = 0.02
# Átfedés, amivel a többi kocka embereit az elengedés kockájának embereihez kötjük.
LINK_IOU = 0.3
# A cél-lövő (a követett lövő doboza az elengedésnél) — ugyanaz, mint match_shots.build.
TARGET_IOU = 0.5
# A lövő HELYE akkor talált, ha a követett lövő dobozától legfeljebb LOC_PAD × doboz-magasságra van
# (a ráközelítő követés a pont körüli kivágáson keres embert — ennyi elég az indításhoz).
LOC_PAD = 0.25
# Repülés-követés: kivágás a lövő köré, az elengedéstől ennyi kockán.
FLIGHT_WIN = (-2, 10)
FLIGHT_MIN_DK = 2

# Álló hamis jelöltek (reklám, vonal, néző): ennyi px-en belül ugyanott legalább STATIC_MIN másik
# kockában is → nem a labda (a labda az elengedés körül kockánként több tíz px-t mozdul).
STATIC_PX = 4.0
STATIC_MIN = 2
# A labda mérete az emberhez: átmérő ≈ BALL_REL × magasság (mint a tanításnál); log-eltérés szórása.
SIZE_SIGMA = 0.5

L_WR, R_WR = 9, 10


# ------------------------------------------------------------ labda a teljes kockán
def tile_origins(W: int, H: int, side: int = TILE, overlap: float = TILE_OVERLAP) -> list[tuple[int, int]]:
    """Átfedő csempék bal felső sarkai, amelyek a teljes képet lefedik."""
    def axis(n):
        if n <= side:
            return [0]
        step = side * (1 - overlap)
        k = int(np.ceil((n - side) / step)) + 1
        return [int(round(v)) for v in np.linspace(0, n - side, k)]
    return [(x, y) for y in axis(H) for x in axis(W)]


def merge_points(c: np.ndarray, radius: float = NMS_PX) -> np.ndarray:
    """Közeli jelöltek összevonása (a csempék átfedéséből): a biztosabb marad. c: (N, 4) x, y, d, conf."""
    if len(c) == 0:
        return c.reshape(0, 4)
    c = c[np.argsort(-c[:, 3])]
    keep = []
    for row in c:
        if all(np.hypot(row[0] - k[0], row[1] - k[1]) > radius for k in keep):
            keep.append(row)
    return np.array(keep, np.float32)


def detect_full(model, frames: list[np.ndarray], conf: float = CONF) -> list[np.ndarray]:
    """Kockánként a labdajelöltek a teljes képen: (N, 4) — x, y, átmérő, megbízhatóság."""
    out = []
    for img in frames:
        H, W = img.shape[:2]
        orig = tile_origins(W, H)
        tiles = [img[y:y + TILE, x:x + TILE] for x, y in orig]
        rows = []
        for (x0, y0), r in zip(orig, model.predict(tiles, imgsz=TILE, conf=conf, verbose=False)):
            b = r.boxes.xyxy.cpu().numpy()
            c = r.boxes.conf.cpu().numpy()
            for bb, cc in zip(b, c):
                rows.append([x0 + (bb[0] + bb[2]) / 2, y0 + (bb[1] + bb[3]) / 2,
                             (bb[2] - bb[0] + bb[3] - bb[1]) / 2, cc])
        out.append(merge_points(np.array(rows, np.float32).reshape(-1, 4)))
    return out


def suppress_static(balls: list[np.ndarray], px: float = STATIC_PX, min_other: int = STATIC_MIN) -> list[np.ndarray]:
    """Az ablak több kockájában ugyanott álló jelöltek elhagyása."""
    out = []
    for i, b in enumerate(balls):
        keep = []
        for row in b:
            n = sum(1 for j, o in enumerate(balls) if j != i and len(o)
                    and np.min(np.hypot(o[:, 0] - row[0], o[:, 1] - row[1])) <= px)
            keep.append(n < min_other)
        out.append(b[np.array(keep, bool)] if len(b) else b)
    return out


# ------------------------------------------------------------ ember ↔ labda
def person_scores(boxes: np.ndarray, kps: np.ndarray, balls: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Emberenként: a legjobb labda pontszáma (megbízhatóság × csukló-közelség) és a labda indexe (−1: nincs)."""
    n = len(boxes)
    s, bi = np.zeros(n), np.full(n, -1)
    if n == 0 or len(balls) == 0:
        return s, bi
    for j in range(n):
        h = max(float(boxes[j, 3] - boxes[j, 1]), 1.0)
        wr = [kps[j, w, :2] for w in (L_WR, R_WR) if kps[j, w, 2] > WRIST_CONF]
        if not wr:
            continue
        from .ball import BALL_REL

        d = np.min([np.hypot(balls[:, 0] - p[0], balls[:, 1] - p[1]) for p in wr], 0) / h
        size = np.exp(-np.log(np.maximum(balls[:, 2], 1.0) / (BALL_REL * h)) ** 2 / (2 * SIZE_SIGMA ** 2))
        v = balls[:, 3] * np.exp(-(d / SIGMA) ** 2) * size
        k = int(np.argmax(v))
        s[j], bi[j] = v[k], k
    return s, bi


def iou(a: np.ndarray, b: np.ndarray) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / ua) if ua > 0 else 0.0


def pick_shooter(people: list[tuple[np.ndarray, np.ndarray]], balls: list[np.ndarray], r: int) -> dict:
    """A lövő a kockák (people[i], balls[i]) alapján; r = az elengedés kockája a listában.

    Visszaad: {"index": az elengedés-kocka embere vagy None, "pont": (x, y) a lövő helye vagy None,
    "pontszam": a döntés pontszáma, "labda": a döntő labda (x, y, d, conf) vagy None}."""
    R = people[r][0]
    acc = np.zeros(len(R))
    best_ball = [None] * len(R)
    best_s: dict[int, float] = {}
    for (bx, kp), bl in zip(people, balls):
        s, bi = person_scores(bx, kp, bl)
        for j in range(len(bx)):
            if s[j] <= 0:
                continue
            # a kocka emberét az elengedés-kocka emberéhez kötjük (átfedés)
            ov = [iou(bx[j], R[i]) for i in range(len(R))]
            if not ov or max(ov) < LINK_IOU:
                continue
            i = int(np.argmax(ov))
            if s[j] > best_s.get(i, 0.0):
                best_ball[i], best_s[i] = bl[bi[j]], s[j]
            acc[i] = acc[i] + s[j] if ACCUM == "sum" else max(acc[i], s[j])
    if len(R) and acc.max() >= PICK_MIN:
        i = int(np.argmax(acc))
        b = R[i]
        return {"index": i, "pont": ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), "pontszam": float(acc[i]),
                "labda": best_ball[i], "doboz": b}
    allb = [b for b in balls if len(b)]
    if allb:
        cand = np.concatenate(allb)
        top = cand[int(np.argmax(cand[:, 3]))]
        return {"index": None, "pont": (float(top[0]), float(top[1])), "pontszam": 0.0, "labda": top, "doboz": None}
    return {"index": None, "pont": None, "pontszam": 0.0, "labda": None, "doboz": None}


def inside(pt, box, pad: float = LOC_PAD) -> bool:
    """A pont legfeljebb pad × magasságra van a dobozától (benne: 0)."""
    if pt is None or box is None:
        return False
    dx = max(box[0] - pt[0], 0.0, pt[0] - box[2])
    dy = max(box[1] - pt[1], 0.0, pt[1] - box[3])
    return float(np.hypot(dx, dy)) <= pad * float(box[3] - box[1])


# ------------------------------------------------------------ célzóna a repülésből
def flight_features(p_sep: tuple[float, float], k_sep: int, p_fly: tuple[float, float], k_fly: int,
                    box: np.ndarray, W: int = 1920, H: int = 1080) -> list[float]:
    """Ugyanazok a jellemzők, mint a kézi labdapontokkal mért zóna-becslésnél (pixelben megadott pontok)."""
    hh = max(float(box[3] - box[1]), 1.0)
    dk = max(1, k_fly - k_sep)
    dx = (p_fly[0] - p_sep[0]) / hh / dk
    dy = (p_fly[1] - p_sep[1]) / hh / dk
    return [dx, dy, float(np.arctan2(dy, dx)), p_sep[0] / W, p_sep[1] / H, (p_sep[1] - box[1]) / hh]


def flight_from_path(path: list, r: int) -> tuple | None:
    """A követett labdapályából (hbd.ball.track) az elválás (az elengedéshez legközelebbi látott pont,
    r-től) és a repülés (a legtávolabbi látott pont legalább FLIGHT_MIN_DK kockával később)."""
    seen = [(t, q) for t, q in enumerate(path) if q is not None and t >= r - 1]
    if len(seen) < 2:
        return None
    t0, q0 = seen[0]
    later = [(t, q) for t, q in seen if t - t0 >= FLIGHT_MIN_DK]
    if not later:
        return None
    t1, q1 = later[-1]
    return (float(q0[0]), float(q0[1])), t0, (float(q1[0]), float(q1[1])), t1


# ------------------------------------------------------------ összefűzés
def read_frames(video: str, t0: float, n: int, size: tuple[int, int] = (1920, 1080)) -> list[np.ndarray]:
    """n kocka t0-tól, kockára pontosan.

    A match_shots._orig_frames az ffmpeg alap kocka-időzítésével olvas, ami a pontos
    ugrásnál az első kockát néha megduplázza ([F, F, F+1, …]): ott a lista i. eleme
    (i ≥ 1) valójában az F+i−1. kocka. A `-fps_mode passthrough` ezt megszünteti."""
    import subprocess

    from .video import ffmpeg_exe

    w, h = size
    raw = subprocess.run([ffmpeg_exe(), "-v", "error", "-ss", f"{max(0.0, t0):.3f}", "-i", video,
                          "-fps_mode", "passthrough", "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout
    k = len(raw) // (w * h * 3)
    return list(np.frombuffer(raw[:k * w * h * 3], np.uint8).reshape(k, h, w, 3))


def _clip_frames(video: str, clip: dict, k_from: int, n: int) -> list[np.ndarray]:
    return read_frames(video, clip["t_start"] + k_from / float(clip["fps"]), n)


def pose_lag(p: dict) -> int:
    """1, ha a klip-póz a duplázott első kockával készült (az i. póz-kocka a k0+i−1. klip-kocka), különben 0."""
    if len(p["n"]) < 2 or p["n"][0] == 0 or p["n"][0] != p["n"][1]:
        return 0
    a, b = p["offsets"][0], p["offsets"][1]
    return int(np.allclose(p["boxes"][a:b], p["boxes"][b:b + (b - a)]))


def heldout_ids(ball_labels: Path, ball_manifest: Path, groups: dict[str, str]) -> set[str]:
    """A labdafelismerő tanításából kimaradt klipek (ugyanaz a felosztás, mint a hbd.ball build-ben)."""
    from .ball import split_groups

    man = {c["id"] for c in json.loads(ball_manifest.read_text())["klipek"]}
    L = {d["klip"] for d in json.loads(ball_labels.read_text())["cimkek"]}
    return split_groups(sorted(i for i in L if i in man), groups)


def run(args) -> dict:
    import torch
    from ultralytics import YOLO

    from .ball import detect_candidates, track
    from .match_shots import candidate_features, frame_people, load_clip_pose, replay_groups, split_zone

    torch.set_num_threads(args.threads)
    model = YOLO(args.weights)
    clips = json.loads(Path(args.clips).read_text())["clips"]
    groups = replay_groups(clips)
    held = heldout_ids(Path(args.ball_labels), Path(args.ball_manifest), groups)
    labs = {d["klip"]: d for d in json.loads(Path(args.labels).read_text())["cimkek"]
            if not d.get("rossz") and d.get("lovo") and d.get("elengedes") is not None}
    bl = {d["klip"]: {p["nev"]: p for p in d["pontok"]} for d in json.loads(Path(args.ball_labels).read_text())["cimkek"]}
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in clips:
        cid = c["id"]
        lab = labs.get(cid)
        pf, zf = Path(args.poses) / f"{cid}.npz", Path(args.zoom) / f"{cid}.npz"
        if lab is None or not pf.exists() or not zf.exists() or (args.only and cid not in args.only):
            continue
        p = load_clip_pose(pf)
        z = np.load(zf)
        # a póz-index egy klip-kockához: f − k0 + lag (lásd read_frames)
        k0 = int(p["k0"]) - pose_lag(p)
        rel = int(lab["elengedes"])
        fr = [f for f in range(rel + WIN[0], rel + WIN[1] + 1) if 0 <= f - k0 < len(p["n"])]
        if rel not in fr:
            continue
        cf = cache / f"{cid}_teljes.npz"
        if cf.exists():
            zc = np.load(cf)
            balls = [zc["c"][zc["f"] == i] for i in range(len(fr))]
        else:
            balls = detect_full(model, _clip_frames(args.video, c, fr[0], len(fr)))
            np.savez_compressed(cf, c=np.concatenate(balls) if balls else np.zeros((0, 4)),
                                f=np.concatenate([np.full(len(b), i) for i, b in enumerate(balls)]))
        people = [frame_people(p, f - k0) for f in fr]
        r = fr.index(rel)
        balls = suppress_static(balls)
        res = pick_shooter(people, balls, r)
        # a cél: a követett lövő doboza az elengedésnél (mint a match_shots.build-ben)
        target, sbox = None, None
        if not bool(z["lost"]):
            t = int(np.clip(rel - (int(z["k0"]) - (int(p["k0"]) - k0)) - int(z["start"]), 0, len(z["boxes"]) - 1))
            sbox = z["boxes"][t]
            R = people[r][0]
            if len(R):
                ov = [iou(sbox, b) for b in R]
                target = int(np.argmax(ov)) if max(ov) > TARGET_IOU else None
        X, _ = candidate_features(p, rel - k0)
        row = {"klip": cid, "csoport": groups[cid], "felretett": cid in held, "cel": target,
               "valasztott": res["index"], "talalt": res["index"] is not None and res["index"] == target,
               "hely_talalt": inside(res["pont"], sbox), "pontszam": res["pontszam"],
               "emberek": int(len(people[r][0])), "X": X, "R": people[r][0], "sbox": sbox}
        # emberenkénti labda-jellemző a kombinált választóhoz (elengedés-kocka emberei)
        R = people[r][0]
        ballf = np.zeros((len(R), 4))
        for (bx, kp), b in zip(people, balls):
            s, bi = person_scores(bx, kp, b)
            for j in range(len(bx)):
                ov = [iou(bx[j], R[i]) for i in range(len(R))]
                if ov and max(ov) >= LINK_IOU:
                    i = int(np.argmax(ov))
                    ballf[i, 0] = max(ballf[i, 0], s[j])
                    ballf[i, 2] += s[j]
        if len(R):
            ballf[:, 1] = ballf[:, 0] / max(ballf[:, 0].max(), 1e-6)
            ballf[:, 3] = ballf[:, 2] / max(ballf[:, 2].max(), 1e-6)
        row["Xb"] = np.concatenate([X, ballf], 1) if len(X) else X
        # repülés: a lövő köré vágott kivágáson követett labda
        vz, hz = split_zone(lab.get("zona"))
        row["zona_v"] = vz
        if res["pont"] is not None and not args.no_flight:
            box = res["doboz"] if res["doboz"] is not None else (
                np.array([res["pont"][0] - 50, res["pont"][1] - 100, res["pont"][0] + 50, res["pont"][1] + 100]))
            cx, cy = res["labda"][:2] if res["labda"] is not None else res["pont"]
            x0 = int(np.clip(cx - TILE / 2, 0, 1920 - TILE))
            y0 = int(np.clip(cy - TILE / 2, 0, 1080 - TILE))
            ff = cache / f"{cid}_repules_{x0}_{y0}.npz"
            a = rel + FLIGHT_WIN[0]
            n = FLIGHT_WIN[1] - FLIGHT_WIN[0] + 1
            if ff.exists():
                zc = np.load(ff)
                cands = [zc["c"][zc["f"] == i] for i in range(int(zc["n"]))]
            else:
                frames = [im[y0:y0 + TILE, x0:x0 + TILE] for im in _clip_frames(args.video, c, a, n)]
                cands = detect_candidates(model, frames)
                np.savez_compressed(ff, c=np.concatenate(cands) if cands else np.zeros((0, 4)),
                                    f=np.concatenate([np.full(len(q), i) for i, q in enumerate(cands)]),
                                    n=np.int32(len(cands)))
            fl = flight_from_path(track(cands), rel - a)
            if fl is not None:
                (sx, sy), ts, (fx, fy), tf = fl
                row["repules"] = flight_features((x0 + sx, y0 + sy), ts, (x0 + fx, y0 + fy), tf, box)
        # kézi labdapontokból ugyanez (a zóna-modell tanításához)
        b = bl.get(cid, {})
        if sbox is not None and "elvalik" in b and "repul" in b and not b["elvalik"].get("nincs") \
                and not b["repul"].get("nincs"):
            row["repules_kezi"] = flight_features((b["elvalik"]["x"] * 1920, b["elvalik"]["y"] * 1080),
                                                  b["elvalik"]["k"], (b["repul"]["x"] * 1920, b["repul"]["y"] * 1080),
                                                  b["repul"]["k"], sbox)
        rows.append(row)
        print(f"  {cid}: {'+' if row['talalt'] else '-'}{'+' if row['hely_talalt'] else '-'} "
              f"({row['emberek']} ember)", flush=True)
    return {"rows": rows}


def summarize(rows: list[dict]) -> dict:
    """Lövő-választás és lövő-hely: a félretett klipeken és az összesen (ez utóbbi optimista)."""
    combined = combined_picker(rows)
    out = {}
    for name, sel in (("felretett", [r for r in rows if r["felretett"]]), ("osszes", rows)):
        n = len(sel)
        with_t = [r for r in sel if r["cel"] is not None]
        out[name] = {
            "klipek": n, "lovo_a_jeloltek_kozt": len(with_t),
            "labda_valaszto_ha_jelolt": float(np.mean([r["talalt"] for r in with_t])) if with_t else None,
            "labda_valaszto_az_osszesbol": float(np.mean([r["talalt"] for r in sel])) if sel else None,
            "lovo_helye_az_osszesbol": float(np.mean([r["hely_talalt"] for r in sel])) if sel else None,
            "kombinalt_ha_jelolt": float(np.mean([_hit(r, combined) for r in with_t])) if with_t else None,
            "testpont_valaszto_ha_jelolt": float(np.mean([_hit(r, _BASE_HITS) for r in with_t])) if with_t else None,
            "testpont_hely": float(np.mean([_loc(r, _BASE_HITS) for r in sel])) if sel else None,
            "kombinalt_hely": float(np.mean([_loc(r, combined) for r in sel])) if sel else None,
        }
    return out


_BASE_HITS: dict = {}


def _cv_hits(rows: list[dict], key: str, seed: int = 0) -> dict[str, int]:
    """Csoportosított CV: klipenként a választott ember indexe (az elengedés-kocka emberei közt)."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold

    # tanítás a lövőt tartalmazó klipeken; jóslás MINDEN klipre, ahol van ember (a hely-méréshez)
    data = [r for r in rows if len(r[key])]
    groups = np.array([r["csoport"] for r in data])
    hits = {}
    if len(set(groups)) < 2:
        return hits
    for tr, te in GroupKFold(min(5, len(set(groups)))).split(np.zeros(len(data)), groups=groups):
        trc = [i for i in tr if data[i]["cel"] is not None]
        X = np.concatenate([data[i][key] for i in trc])
        y = np.concatenate([np.arange(len(data[i][key])) == data[i]["cel"] for i in trc]).astype(int)
        clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                             class_weight="balanced", random_state=seed).fit(X, y)
        for i in te:
            j = int(np.argmax(clf.predict_proba(data[i][key])[:, 1]))
            hits[data[i]["klip"]] = j
    return hits


def combined_picker(rows: list[dict]) -> dict[str, int]:
    """A testpont-jellemzős választó + labda-jellemzők (csoportosított CV): klip → választott index."""
    _BASE_HITS.clear()
    _BASE_HITS.update(_cv_hits(rows, "X"))
    return _cv_hits(rows, "Xb")


def _hit(r: dict, picks: dict) -> bool:
    return r["cel"] is not None and picks.get(r["klip"]) == r["cel"]


def _loc(r: dict, picks: dict) -> bool:
    j = picks.get(r["klip"])
    if j is None:
        return False
    b = r["R"][j]
    return inside(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), r["sbox"])


def zone_eval(rows: list[dict]) -> dict:
    """Lent vs fent (a közép kimarad) a repülési irányból.

    A: tanítás a kézi labdapontokon (a nem félretett klipeken), teszt a félretett klipek
       AUTOMATIKUS repülésén — a valódi, kattintás nélküli helyzet.
    B: csoportosított CV az automatikus repülésen, minden klipen (optimista: a labdafelismerő
       a klipek 80%-án tanult)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def clf():
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=3000, class_weight="balanced"))

    lf = [r for r in rows if r.get("zona_v") in (0, 2)]
    out = {}
    tr = [r for r in lf if not r["felretett"] and "repules_kezi" in r]
    te = [r for r in lf if r["felretett"]]
    te_ok = [r for r in te if "repules" in r]
    if tr and te_ok:
        m = clf().fit(np.array([r["repules_kezi"] for r in tr]), np.array([r["zona_v"] == 2 for r in tr], int))
        y = np.array([r["zona_v"] == 2 for r in te_ok], int)
        pred = m.predict(np.array([r["repules"] for r in te_ok]))
        out["felretett_automatikus"] = {"lent_fent_klipek": len(te), "repules_megvan": len(te_ok),
                                        "kiegyensulyozott": float(balanced_accuracy_score(y, pred)),
                                        "pontossag": float((pred == y).mean())}
        te_k = [r for r in te if "repules_kezi" in r]
        if te_k:
            yk = np.array([r["zona_v"] == 2 for r in te_k], int)
            pk = m.predict(np.array([r["repules_kezi"] for r in te_k]))
            out["felretett_kezi_labdaval"] = {"klipek": len(te_k),
                                              "kiegyensulyozott": float(balanced_accuracy_score(yk, pk))}
    au = [r for r in lf if "repules" in r]
    if len(au) >= 20:
        X = np.array([r["repules"] for r in au])
        y = np.array([r["zona_v"] == 2 for r in au], int)
        g = np.array([r["csoport"] for r in au])
        pred = np.zeros_like(y)
        for a, b in GroupKFold(5).split(X, y, g):
            pred[b] = clf().fit(X[a], y[a]).predict(X[b])
        out["osszes_automatikus_cv"] = {"lent_fent_klipek": len(lf), "repules_megvan": len(au),
                                        "kiegyensulyozott": float(balanced_accuracy_score(y, pred))}
    return out


def write_report(summ: dict, zone: dict, out: Path) -> Path:
    pct = lambda v: "–" if v is None else f"{100 * v:.0f}%"  # noqa: E731
    h, a = summ["felretett"], summ["osszes"]
    md = ["# Ki lő? — a lövő a labdából (1. meccs)", "",
          "A labdafelismerő (v2) a teljes 1920×1080 kockán, az elengedés körül ±2 kockán; a lövő az, akinek",
          "a csuklója a legbiztosabb labdához legközelebb van. Kézi labda-kattintás NINCS; az elengedés",
          "kockája még a kézi jelölésé.", "",
          "**Félretett** = a labdafelismerő tanításából kimaradt lövések (ugyanaz a 20%, mint a labda-",
          "kiértékelésnél) — ez a becsületes szám. Az **összes** klipen a labdafelismerő a klipek 80%-án",
          "tanult, ezért az optimista.", "",
          "| | félretett | összes (optimista) |", "|---|---|---|",
          f"| klipek | {h['klipek']} | {a['klipek']} |",
          f"| a lövő a pózbecslő emberei közt van | {h['lovo_a_jeloltek_kozt']} | {a['lovo_a_jeloltek_kozt']} |",
          f"| testpont-választó (eddigi), ha a lövő jelölt | {pct(h['testpont_valaszto_ha_jelolt'])} | "
          f"{pct(a['testpont_valaszto_ha_jelolt'])} |",
          f"| **labda-választó**, ha a lövő jelölt | **{pct(h['labda_valaszto_ha_jelolt'])}** | "
          f"{pct(a['labda_valaszto_ha_jelolt'])} |",
          f"| testpont + labda (tanult), ha a lövő jelölt | {pct(h['kombinalt_ha_jelolt'])} | "
          f"{pct(a['kombinalt_ha_jelolt'])} |",
          f"| labda-választó, az összes klipből | {pct(h['labda_valaszto_az_osszesbol'])} | "
          f"{pct(a['labda_valaszto_az_osszesbol'])} |",
          f"| a lövő HELYE — testpont-választó, az összesből | {pct(h['testpont_hely'])} | {pct(a['testpont_hely'])} |",
          f"| a lövő HELYE — testpont + labda, az összesből | {pct(h['kombinalt_hely'])} | {pct(a['kombinalt_hely'])} |",
          f"| **a lövő HELYE — labda-választó** (ember vagy labda), az összesből | "
          f"**{pct(h['lovo_helye_az_osszesbol'])}** | {pct(a['lovo_helye_az_osszesbol'])} |", "",
          "A „lövő helye” azt méri, hogy a választott pont (a választott ember közepe, vagy ha embert nem",
          "talál, a labda) a követett lövő dobozába esik-e. Ez kell a ráközelítő követés indításához — ott",
          "eddig a kézi kattintás állt.", "",
          "## Célzóna lent / fent — teljesen automatikusan", "",
          "A lövő köré vágott képen a labda követve (hbd.ball.track), az elválás → repülés iránya.", ""]
    if "felretett_automatikus" in zone:
        z = zone["felretett_automatikus"]
        md += [f"- Félretett lövések (lent/fent: {z['lent_fent_klipek']}, ebből követhető repülés: "
               f"{z['repules_megvan']}), kézi pontokon tanított modell, automatikus repüléssel: "
               f"**{pct(z['kiegyensulyozott'])} kiegyensúlyozott** (véletlen: 50%)."]
    if "felretett_kezi_labdaval" in zone:
        z = zone["felretett_kezi_labdaval"]
        md += [f"- Ugyanez a kézi labdapontokkal (felső korlát, {z['klipek']} klip): {pct(z['kiegyensulyozott'])}."]
    if "osszes_automatikus_cv" in zone:
        z = zone["osszes_automatikus_cv"]
        md += [f"- Minden klipen, automatikus repüléssel, csoportosított CV ({z['repules_megvan']} klip; optimista): "
               f"{pct(z['kiegyensulyozott'])}."]
    md += ["", "Megjegyzés: a félretett halmaz kicsi (≈40 lövés, ebből a lent/fent zónás még kevesebb) —",
           "a különbségek pár lövésen múlnak. A végleges számot a második meccs adja."]
    p = out / "lovo_labdabol.md"
    p.write_text("\n".join(md) + "\n")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A lövő a labdából (kattintás nélkül)")
    ap.add_argument("--video", required=True)
    ap.add_argument("--clips", required=True)
    ap.add_argument("--poses", required=True)
    ap.add_argument("--zoom", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--ball-labels", required=True)
    ap.add_argument("--ball-manifest", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--only", nargs="*", help="csak ezek a klipek (próbához)")
    ap.add_argument("--no-flight", action="store_true", help="a repülés-követés nélkül (gyors hangoláshoz)")
    args = ap.parse_args(argv)
    rows = run(args)["rows"]
    summ = summarize(rows)
    zone = zone_eval(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "lovo_labdabol.json").write_text(json.dumps({"lovo": summ, "zona": zone}, ensure_ascii=False, indent=1))
    print(write_report(summ, zone, out).read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
