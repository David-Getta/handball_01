"""Labdafelismerő a közvetítésen: tanítás a labdajelölő kattintásaiból.

A kész (COCO "sports ball") felismerők a közvetítésen nem találják a labdát:
az elengedésnél 10–25 px-es és elmosódott. Itt egy kis YOLO11 detektort
tanítunk a labdajelölő pontjain (klipenként kézben / elválik / repül).

Adat:
  - a jelölt kocka a labdajelölő éles, lövő köré vágott videójából (640 px, 1:1
    az eredeti 1080p-hez);
  - a labda doboza: középpont = a kattintás, átmérő = BALL_REL × a lövő
    doboz-magassága (kézilabda Ø 19 cm, játékos ~1,9 m), BALL_PX korlátok közt;
  - tanító képek: TILE-os kivágások, POS_PER_POINT olyan, amin a labda rajta van
    (véletlen helyen), és NEG_PER_POINT olyan, amin nincs (egy pályán egy labda
    van → ez biztos "nincs labda" példa).

Kiértékelés: a lövések (csoportok: élő + ismétlése együtt) HOLDOUT része
kimarad a tanításból; azokon a teljes 640-es kivágáson fut a felismerő, és
mérjük: a legbiztosabb jelölt a valódi labdától legfeljebb HIT_X × átmérőre
van-e.

    python -m hbd.ball build --ball-dir m1ball2 --labels cimkek/meccs1_labda_cimkek.json --zoom m1_zoom --out balldata
    python -m hbd.ball train --data balldata --epochs 40
    python -m hbd.ball evaluate --data balldata --weights runs/.../best.pt
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np

BALL_REL = 0.10
BALL_PX = (8, 40)
TILE = 320
POS_PER_POINT = 3
NEG_PER_POINT = 1
HOLDOUT = 0.2
HIT_X = 1.5
# A kattintások közötti kockák kitöltése (csak tanításhoz), legfeljebb ekkora hézagban.
INTERPOLATE = True
INTERP_MAX_GAP = 8
SEED = 0
# Öntanítás: a jelöletlen kockákon a követett (összefésült) jelölt, ha legalább ennyire biztos.
# A félretett lövéseken mérve 0,1 fölött a jelöltek 89%-a, 0,2 fölött 90%-a valódi labda.
PSEUDO_MIN_CONF = 0.15
PSEUDO_POS_PER_POINT = 1


def read_video_frames(path: Path) -> list[np.ndarray]:
    """Minden kocka (BGR) egy rövid videóból."""
    from .video import iter_frames

    return list(iter_frames(path))


def ball_size(zoom: dict | None, local_k: int, default: float = 20.0) -> float:
    """A labda becsült átmérője px-ben a lövő dobozmagasságából (a ráközelítő követésből)."""
    if zoom is None or bool(zoom["lost"]):
        return default
    t = int(np.clip(local_k - int(zoom["start"]), 0, len(zoom["boxes"]) - 1))
    b = zoom["boxes"][t]
    return float(np.clip(BALL_REL * (b[3] - b[1]), *BALL_PX))


def split_groups(ids: list[str], groups: dict[str, str]) -> set[str]:
    """A kiértékelésre félretett klipek (csoportonként, determinisztikusan)."""
    gs = sorted({groups[i] for i in ids})
    rng = random.Random(SEED)
    rng.shuffle(gs)
    held = set(gs[:int(round(HOLDOUT * len(gs)))])
    return {i for i in ids if groups[i] in held}


def _tile_with(rng, cx, cy, size, W, H):
    x0 = int(np.clip(rng.uniform(cx - TILE + size, cx - size), 0, W - TILE))
    y0 = int(np.clip(rng.uniform(cy - TILE + size, cy - size), 0, H - TILE))
    return x0, y0


def _tile_without(rng, cx, cy, size, W, H, tries=50):
    for _ in range(tries):
        x0, y0 = rng.randint(0, W - TILE), rng.randint(0, H - TILE)
        if not (x0 - size <= cx <= x0 + TILE + size and y0 - size <= cy <= y0 + TILE + size):
            return x0, y0
    return None


def interpolate_points(pontok: list[dict], max_gap: int = INTERP_MAX_GAP) -> list[dict]:
    """A kattintások KÖZÖTTI kockák labdahelye egyenes vonalú közelítéssel.

    Kézben → elválik: 1–3 kocka, a kéz rövid íve jól közelíthető egyenessel;
    elválik → repül: a labda röppályája ilyen rövid szakaszon szinte egyenes.
    Csak a tanító lövésekre (a kiértékelés a valódi kattintásokon fut)."""
    pts = sorted((p for p in pontok if not p.get("nincs")), key=lambda p: p["k"])
    out = []
    for a, b in zip(pts, pts[1:]):
        gap = b["k"] - a["k"]
        if not 2 <= gap <= max_gap:
            continue
        for k in range(a["k"] + 1, b["k"]):
            w = (k - a["k"]) / gap
            out.append({"nev": f"koztes{k}", "k": k, "cx": a["cx"] + w * (b["cx"] - a["cx"]),
                        "cy": a["cy"] + w * (b["cy"] - a["cy"])})
    return out


def build(ball_dir: Path, labels: Path, zoom_dir: Path | None, clips_manifest: Path, out: Path,
          pseudo: dict[str, list[dict]] | None = None) -> dict:
    """YOLO-formátumú adathalmaz (images/labels train+val) + a kiértékelő pontok listája.

    pseudo: a gépi (öntanított) labdapontok klipenként — csak a TANÍTÓ klipekre kerülnek be,
    pontonként PSEUDO_POS_PER_POINT pozitív kivágással és negatív nélkül (ha a gépi pont
    téves, a "nincs labda" kivágáson épp a valódi labda lehetne)."""
    import cv2

    from .match_shots import replay_groups

    man = {c["id"]: c for c in json.loads((ball_dir / "ball_manifest.json").read_text())["klipek"]}
    groups = replay_groups(json.loads(clips_manifest.read_text())["clips"])
    L = {d["klip"]: d for d in json.loads(labels.read_text())["cimkek"]}
    ids = sorted(i for i in L if i in man)
    held = split_groups(ids, groups)
    for sub in ("images/train", "labels/train", "images/val", "labels/val", "full"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    evalpts, n_tr = [], 0
    for cid in ids:
        m = man[cid]
        frames = read_video_frames(ball_dir / m["src"])
        zf = (zoom_dir / f"{cid}.npz") if zoom_dir else None
        z = np.load(zf) if zf is not None and zf.exists() else None
        # a zoom kimenet kockái a lövés-klip k0-jához mérve; a labdavideó saját k0-ja más
        pts = list(L[cid]["pontok"])
        if cid not in held and INTERPOLATE:
            pts += interpolate_points(pts)
        if cid not in held and pseudo:
            have = {p["k"] for p in pts if not p.get("nincs")}
            pts += [q for q in pseudo.get(cid, []) if q["k"] not in have]
        for p in pts:
            if p.get("nincs"):
                continue
            f = p["k"] - m["k0"]
            if not 0 <= f < len(frames):
                continue
            img = frames[f]
            H, W = img.shape[:2]
            cx, cy = p["cx"] * W, p["cy"] * H
            zk = p["k"] - int(z["k0"]) if z is not None else 0
            size = ball_size(z, zk)
            name = f"{cid}_{p['nev']}"
            if cid in held:
                cv2.imwrite(str(out / "full" / f"{name}.jpg"), img)
                evalpts.append({"klip": cid, "nev": p["nev"], "kep": f"full/{name}.jpg", "x": cx, "y": cy, "d": size})
                split = "val"
                reps = 1
            else:
                split = "train"
                reps = PSEUDO_POS_PER_POINT if p.get("gepi") else POS_PER_POINT
            for r in range(reps):
                x0, y0 = _tile_with(rng, cx, cy, size, W, H)
                tile = img[y0:y0 + TILE, x0:x0 + TILE]
                stem = f"{name}_p{r}"
                cv2.imwrite(str(out / f"images/{split}/{stem}.jpg"), tile)
                (out / f"labels/{split}/{stem}.txt").write_text(
                    f"0 {(cx - x0) / TILE:.5f} {(cy - y0) / TILE:.5f} {size / TILE:.5f} {size / TILE:.5f}\n")
                n_tr += split == "train"
            for r in range(NEG_PER_POINT if split == "train" and not p.get("gepi") else 0):
                pos = _tile_without(rng, cx, cy, size, W, H)
                if pos is None:
                    continue
                x0, y0 = pos
                stem = f"{name}_n{r}"
                cv2.imwrite(str(out / f"images/{split}/{stem}.jpg"), img[y0:y0 + TILE, x0:x0 + TILE])
                (out / f"labels/{split}/{stem}.txt").write_text("")
    (out / "data.yaml").write_text(f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n  0: labda\n")
    (out / "eval_points.json").write_text(json.dumps(evalpts))
    (out / "labels_full.json").write_text(json.dumps({cid: [p for p in L[cid]["pontok"] if not p.get("nincs")]
                                                      for cid in sorted(held)}))
    info = {"klipek": len(ids), "kiertekelo_klipek": len(held), "tanito_kepek": n_tr, "kiertekelo_pontok": len(evalpts)}
    (out / "info.json").write_text(json.dumps(info))
    return info


def evaluate(data: Path, weights: str, imgsz: int = 640, conf: float = 0.01) -> dict:
    """A félretett lövések teljes kivágásain: eltalálja-e a labdát (a legbiztosabb jelölt)."""
    from ultralytics import YOLO

    model = YOLO(weights)
    pts = json.loads((data / "eval_points.json").read_text())
    by = {}
    for p in pts:
        r = model.predict(str(data / p["kep"]), imgsz=imgsz, conf=conf, verbose=False)[0]
        b = r.boxes.xyxy.cpu().numpy()
        c = r.boxes.conf.cpu().numpy()
        hit, top = False, None
        if len(b):
            j = int(np.argmax(c))
            bx, by_ = (b[j, 0] + b[j, 2]) / 2, (b[j, 1] + b[j, 3]) / 2
            top = float(c[j])
            hit = float(np.hypot(bx - p["x"], by_ - p["y"])) <= HIT_X * p["d"]
        by.setdefault(p["nev"], []).append((hit, top))
    out = {}
    for nev, v in by.items():
        hits = np.array([h for h, _ in v])
        out[nev] = {"pontok": len(v), "talalat": float(hits.mean())}
    allh = np.array([h for v in by.values() for h, _ in v])
    out["osszes"] = {"pontok": int(len(allh)), "talalat": float(allh.mean())}
    return out


# Követés: kockánként ennyi jelölt, a hiányzó kocka "ára", és a mozgás korlátja
# labdaátmérőben / kocka (25 m/s, 25 fps → ~1 m/kocka ≈ 5 átmérő; a tartalék a becsült méret hibájára).
TRACK_TOPK = 5
# A 0,03 túl olcsó volt: a pálya inkább "eltűnt", mint hogy a kicsit
# gyengébb, de helyes jelöltet vegye (a félretett lövéseken mérve: 0,003 → 67%).
TRACK_MISS = np.log(0.003)
TRACK_FREE_JUMP = 6.0
TRACK_JUMP_W = 0.5
# A követés ablaka a (korábbi, meccs-lövésjelölős) elengedéshez képest, kockában.
TRACK_WINDOW = (-8, 10)


def detect_candidates(model, frames: list[np.ndarray], imgsz: int = 640, conf: float = 0.01) -> list[np.ndarray]:
    """Kockánként a legjobb TRACK_TOPK jelölt: (x, y, átmérő, megbízhatóság)."""
    out = []
    for i in range(0, len(frames), 16):
        for r in model.predict(frames[i:i + 16], imgsz=imgsz, conf=conf, verbose=False):
            b = r.boxes.xyxy.cpu().numpy()
            c = r.boxes.conf.cpu().numpy()
            o = np.argsort(-c)[:TRACK_TOPK]
            out.append(np.stack([(b[o, 0] + b[o, 2]) / 2, (b[o, 1] + b[o, 3]) / 2,
                                 (b[o, 2] - b[o, 0] + b[o, 3] - b[o, 1]) / 2, c[o]], 1) if len(o) else np.zeros((0, 4)))
    return out


def track(cands: list[np.ndarray]) -> list[np.ndarray | None]:
    """A legvalószínűbb, egyenletes labdapálya (Viterbi): kockánként egy jelölt vagy "nem látszik".

    Pontszám: a jelöltek log-megbízhatósága, mínusz a túl nagy ugrás büntetése
    (TRACK_FREE_JUMP átmérő / kocka fölött négyzetesen). A "nem látszik" állapot
    ára TRACK_MISS; utána a következő jelölt a legutóbbi látott helyhez mérődik."""
    T = len(cands)
    if T == 0:
        return []
    # állapot: (jelölt index | -1 = nem látszik); a "nem látszik" a legutóbbi látott helyet viszi tovább
    score = [np.append(np.log(cands[0][:, 3] + 1e-6), TRACK_MISS)]
    last = [np.vstack([cands[0][:, :3], [np.nan, np.nan, np.nan]])]
    back = []
    for t in range(1, T):
        c = cands[t]
        n = len(c)
        prev_s, prev_last = score[-1], last[-1]
        s = np.full(n + 1, -np.inf)
        bk = np.zeros(n + 1, int)
        lp = np.full((n + 1, 3), np.nan)
        for j in range(n):
            for i in range(len(prev_s)):
                px, py, pd = prev_last[i]
                pen = 0.0
                if not np.isnan(px):
                    jump = np.hypot(c[j, 0] - px, c[j, 1] - py) / max(pd, c[j, 2], 4.0)
                    pen = TRACK_JUMP_W * max(0.0, jump - TRACK_FREE_JUMP) ** 2
                v = prev_s[i] + np.log(c[j, 3] + 1e-6) - pen
                if v > s[j]:
                    s[j], bk[j] = v, i
            lp[j] = c[j, :3]
        i = int(np.argmax(prev_s))
        s[n], bk[n], lp[n] = prev_s[i] + TRACK_MISS, i, prev_last[i]
        score.append(s)
        last.append(lp)
        back.append(bk)
    j = int(np.argmax(score[-1]))
    path = [j]
    for bk in reversed(back):
        j = int(bk[j])
        path.append(j)
    path.reverse()
    return [cands[t][j] if j < len(cands[t]) else None for t, j in enumerate(path)]


# Sebesség-alapú (másodrendű) követés: a labda a következő kockán nagyjából ott van,
# ahová a mostani sebessége viszi. A gyors, de EGYENLETES repülés így nem büntetett,
# a hirtelen irányváltás (átugrás egy álló téves jelöltre) igen.
# (A 40 félretett lövésen keresztvalidálva NEM jobb az elsőrendűnél: 64,9% vs 64,4% —
# a repülő labdánál a felismerő a szűk keresztmetszet, nem a pálya. Összevetésre megmarad.)
TRACK2_FREE_ACC = 4.0    # ennyi átmérő eltérés a jósolt helytől ingyenes (kézmozgás, becslési zaj)
TRACK2_ACC_W = 0.1       # az e fölötti eltérés négyzetes büntetése
TRACK2_MAX_GAP = 3       # ennyi "nem látszik" kocka után a sebesség elfelejtődik


def track2(cands: list[np.ndarray], miss: float | None = None, free_acc: float | None = None,
           acc_w: float | None = None, free_jump: float | None = None, jump_w: float | None = None,
           topk: int | None = None) -> list[np.ndarray | None]:
    """Másodrendű Viterbi: állapot = (előző kocka jelöltje, mostani jelölt), így a sebesség
    az állapotból adódik. Az átmenet ára a jósolt helytől (hely + sebesség × hézag) való
    eltérés; ha még nincs sebesség (pálya eleje, hosszú kiesés után), az elsőrendű
    ugrás-büntetés (TRACK_FREE_JUMP, TRACK_JUMP_W) érvényes. "Nem látszik" állapot: TRACK_MISS,
    alatta a pálya a legutóbbi helyről, a sebességgel tovább vetítve folytatódik."""
    miss = TRACK_MISS if miss is None else miss
    free_acc = TRACK2_FREE_ACC if free_acc is None else free_acc
    acc_w = TRACK2_ACC_W if acc_w is None else acc_w
    free_jump = TRACK_FREE_JUMP if free_jump is None else free_jump
    jump_w = TRACK_JUMP_W if jump_w is None else jump_w
    K = TRACK_TOPK if topk is None else topk
    cands = [c[:K] for c in cands]
    T = len(cands)
    if T == 0:
        return []
    # állapot (i, j) → (pontszám, utolsó látott hely (x, y, d) | None, sebesség (vx, vy) | None, hézag, vissza)
    c0 = cands[0]
    states = {(-1, j): (float(np.log(c0[j, 3] + 1e-6)), tuple(c0[j, :3]), None, 1, None) for j in range(len(c0))}
    states[(-1, -1)] = (miss, None, None, 1, None)
    hist = [states]
    for t in range(1, T):
        c = cands[t]
        new: dict = {}
        for (i, j), (s, pos, vel, gap, _) in states.items():
            # a következő jelölt k (vagy -1 = nem látszik)
            for k in range(-1, len(c)):
                if k < 0:
                    v = s + miss
                    nst = (v, pos, vel if gap < TRACK2_MAX_GAP else None, gap + 1, (i, j))
                else:
                    x, y, d, conf = c[k]
                    v = s + float(np.log(conf + 1e-6))
                    nvel = None
                    if pos is not None:
                        dd = max(pos[2], d, 4.0)
                        if vel is not None:
                            px, py = pos[0] + vel[0] * gap, pos[1] + vel[1] * gap
                            acc = np.hypot(x - px, y - py) / dd
                            v -= acc_w * max(0.0, acc - free_acc) ** 2
                        else:
                            jump = np.hypot(x - pos[0], y - pos[1]) / dd / gap
                            v -= jump_w * max(0.0, jump - free_jump) ** 2
                        nvel = ((x - pos[0]) / gap, (y - pos[1]) / gap)
                    nst = (v, (x, y, d), nvel, 1, (i, j))
                key = (j, k)
                if key not in new or nst[0] > new[key][0]:
                    new[key] = nst
        states = new
        hist.append(states)
    key = max(states, key=lambda q: states[q][0])
    path = []
    for t in range(T - 1, -1, -1):
        path.append(key[1])
        key = hist[t][key][4]
    path.reverse()
    return [cands[t][j] if j >= 0 else None for t, j in enumerate(path)]


# Összefésülés: a követett jelölt helyett a kocka legbiztosabbja, ha az ennyiszer biztosabb,
# vagy ha a követés "nem látszik"-ot mond (a gyors, elmosódott repülő labda gyakran kiesik
# a pályából, de a kockán önmagában felismerhető). Keresztvalidálva 64% → 69%; a 3–10 közti
# arányok mind hasonlóak.
TRACK_FUSE_RATIO = 3.0


def fuse(cands: list[np.ndarray], path: list[np.ndarray | None], ratio: float = TRACK_FUSE_RATIO) -> list[np.ndarray | None]:
    """A követés kimenete, ahol a kocka legjobb jelöltje sokkal biztosabb (vagy nincs követett), azzal felülírva."""
    out = []
    for c, q in zip(cands, path):
        top = c[0] if len(c) else None
        out.append(top if top is not None and (q is None or top[3] > ratio * q[3]) else q)
    return out


def evaluate_track(data: Path, ball_dir: Path, weights: str) -> dict:
    """A félretett lövéseken: kockánkénti legjobb jelölt vs. követés — eltalálja-e a jelölt labdát."""
    from ultralytics import YOLO

    model = YOLO(weights)
    man = {c["id"]: c for c in json.loads((ball_dir / "ball_manifest.json").read_text())["klipek"]}
    pts = json.loads((data / "eval_points.json").read_text())
    by_clip = {}
    for p in pts:
        by_clip.setdefault(p["klip"], []).append(p)
    res = {"kockankent": {}, "kovetes": {}, "kovetes_masodrendu": {}, "osszefesult": {}}
    for cid, ps in sorted(by_clip.items()):
        m = man[cid]
        frames = read_video_frames(ball_dir / m["src"])
        e = m["elengedes"] - m["k0"]
        a, b = max(0, e + TRACK_WINDOW[0]), min(len(frames), e + TRACK_WINDOW[1] + 1)
        cands = detect_candidates(model, frames[a:b])
        paths = {"kovetes": track(cands), "kovetes_masodrendu": track2(cands)}
        paths["osszefesult"] = fuse(cands, paths["kovetes"])
        lab = {q["nev"]: q for q in json.loads((data / "labels_full.json").read_text())[cid]}
        for p in ps:
            f = lab[p["nev"]]["k"] - m["k0"] - a
            ok = 0 <= f < len(cands)
            c = cands[f] if ok else np.zeros((0, 4))
            hit_top = bool(len(c)) and np.hypot(c[0, 0] - p["x"], c[0, 1] - p["y"]) <= HIT_X * p["d"]
            res["kockankent"].setdefault(p["nev"], []).append(bool(hit_top))
            for mode, path in paths.items():
                q = path[f] if ok else None
                hit = q is not None and np.hypot(q[0] - p["x"], q[1] - p["y"]) <= HIT_X * p["d"]
                res[mode].setdefault(p["nev"], []).append(bool(hit))
    out = {}
    for mode, d in res.items():
        out[mode] = {nev: round(float(np.mean(v)), 3) for nev, v in d.items()}
        out[mode]["osszes"] = round(float(np.mean([x for v in d.values() for x in v])), 3)
    return out


def pseudo_labels(weights: str, ball_dir: Path, labels: Path, clips_manifest: Path,
                  min_conf: float = PSEUDO_MIN_CONF) -> dict[str, list[dict]]:
    """Gépi labdapontok a TANÍTÓ klipek összes kockáján (a félretett klipeket nem érinti):
    felismerő → követés → összefésülés, és ahol a választott jelölt legalább min_conf biztos."""
    from ultralytics import YOLO

    from .match_shots import replay_groups

    model = YOLO(weights)
    man = {c["id"]: c for c in json.loads((ball_dir / "ball_manifest.json").read_text())["klipek"]}
    groups = replay_groups(json.loads(clips_manifest.read_text())["clips"])
    L = {d["klip"]: d for d in json.loads(labels.read_text())["cimkek"]}
    ids = sorted(i for i in L if i in man)
    held = split_groups(ids, groups)
    out = {}
    for cid in ids:
        if cid in held:
            continue
        m = man[cid]
        frames = read_video_frames(ball_dir / m["src"])
        cands = detect_candidates(model, frames)
        path = fuse(cands, track(cands))
        H, W = frames[0].shape[:2]
        out[cid] = [{"nev": f"gepi{m['k0'] + f}", "k": m["k0"] + f, "cx": float(q[0] / W), "cy": float(q[1] / H),
                     "gepi": True, "biztos": round(float(q[3]), 3)}
                    for f, q in enumerate(path) if q is not None and q[3] >= min_conf]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Labdafelismerő a közvetítésen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--ball-dir", required=True, help="a make_ball_frames kimenete (ball_manifest.json + videók)")
    b.add_argument("--labels", required=True)
    b.add_argument("--clips", required=True, help="a lövés-klipek manifest.json-ja (csoportokhoz)")
    b.add_argument("--zoom", help="a match_shots zoom kimenete (a labda méretéhez)")
    b.add_argument("--out", required=True)
    b.add_argument("--pseudo", help="a pseudo lépés kimenete (gépi labdapontok a tanító klipekre)")
    ps = sub.add_parser("pseudo", help="öntanítás: gépi labdapontok a tanító klipek összes kockáján")
    ps.add_argument("--ball-dir", required=True)
    ps.add_argument("--labels", required=True)
    ps.add_argument("--clips", required=True)
    ps.add_argument("--weights", required=True)
    ps.add_argument("--min-conf", type=float, default=PSEUDO_MIN_CONF)
    ps.add_argument("--out", required=True, help="kimeneti JSON")
    t = sub.add_parser("train")
    t.add_argument("--data", required=True)
    t.add_argument("--weights", default="yolo11n.pt")
    t.add_argument("--epochs", type=int, default=40)
    t.add_argument("--device", default="cpu")
    t.add_argument("--project", default="runs_ball")
    t.add_argument("--name", default="labda")
    e = sub.add_parser("evaluate")
    e.add_argument("--data", required=True)
    e.add_argument("--weights", required=True)
    e.add_argument("--ball-dir", help="megadva a követést is kiértékeli (a labdajelölő videóin)")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        pseudo = json.loads(Path(args.pseudo).read_text()) if args.pseudo else None
        info = build(Path(args.ball_dir), Path(args.labels), Path(args.zoom) if args.zoom else None,
                     Path(args.clips), Path(args.out), pseudo)
        print(info)
    elif args.cmd == "pseudo":
        res = pseudo_labels(args.weights, Path(args.ball_dir), Path(args.labels), Path(args.clips), args.min_conf)
        Path(args.out).write_text(json.dumps(res))
        print(f"{sum(map(len, res.values()))} gépi pont, {len(res)} klip → {args.out}")
    elif args.cmd == "train":
        from ultralytics import YOLO

        YOLO(args.weights).train(data=str(Path(args.data) / "data.yaml"), imgsz=TILE, epochs=args.epochs,
                                 device=args.device, batch=16, project=args.project, name=args.name, exist_ok=True,
                                 mosaic=0.5, fliplr=0.5, degrees=0, scale=0.3, workers=2, patience=15, verbose=False)
    else:
        res = evaluate(Path(args.data), args.weights)
        if args.ball_dir:
            res["kovetessel"] = evaluate_track(Path(args.data), Path(args.ball_dir), args.weights)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
