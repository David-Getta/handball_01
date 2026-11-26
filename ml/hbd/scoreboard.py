"""Az állás KIOLVASÁSA az eredményjelzőből → a meccs teljes gól-idővonala.

A `broadcast` csak azt látja, hogy az állás-kivágás megváltozott-e; ez a modul
ki is olvassa a két számot. A közvetítés grafikájának betűtípusa fix, így a
számjegy-felismerés egyszerű sablon-illesztés:

  1. stabil állapotok: a grafika látszik és legalább STABLE_S-ig nem változik
     (az animáció, beúszás így kiesik); állapotonként a medián kép;
  2. a két szám a középvonalnál kettévágva; jelek = összefüggő világos foltok,
     egységes GLYPH méretre hozva;
  3. sablonok: a jelek k-közép csoportjai, amiket EGYSZER, szemmel címkézünk
     (közvetítőnként; `cluster` parancs → kép → `--labels`);
  4. idővonal: csak a növekvő, lépésenként legfeljebb +2 gólos olvasatok
     (a kettős lépés: két gól egy ismétlés alatt, a grafika nem látszott).

Ellenőrzés emberi jelölés nélkül: a végső olvasatnak egyeznie kell a hivatalos
végeredménnyel. A 2. meccsen (ARD-grafika): 35:33 olvasva, 68/68 gól.

    python -m hbd.scoreboard crops  --video m.mp4 --box 0.462 0.062 0.545 0.110 --stride 10 --out sb.npy
    python -m hbd.scoreboard cluster --crops sb.npy --broadcast m_broadcast.npz --out sablon/   # → klaszterek.png
    python -m hbd.scoreboard read --crops sb.npy --broadcast m_broadcast.npz \\
        --templates sablon/kozeppontok.npy --labels 2,1,9,4,3,7,5,6,8,0,1,2,x,3 --out allas.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

# Egy állapot legalább ennyi ideig látszó, változatlan grafika (s).
STABLE_S = 2.0
# Szomszédos minták átlagos eltérése e fölött: a grafika épp változik (zaj ~0,1–0,3).
STEP_DIFF = 2.0
# A számjegy világos a sötét háttéren: ennél világosabb pixel a jel része.
BRIGHT = 110
# A jel legalább a kivágás magasságának ennyi része, és legalább ennyi px széles
# (a középső elválasztó vonal és a zaj így kiesik).
MIN_H_FRAC = 0.5
MIN_W_PX = 4
# A jelek egységes mérete (szél × mag) és a sablontól megengedett legnagyobb távolság.
GLYPH = (16, 24)
MAX_DIST = 40.0
# A középvonal a kivágásban (arány) és a két oldal elhagyott sávja körülötte (px).
SPLIT = 0.5
SPLIT_GAP = 2


def extract_crops(video: str, box, stride: int) -> np.ndarray:
    """Az állás-rész szürke kivágásai minden stride-adik kockán (N, H, W).

    A szélesség és a magasság PÁROS-ra kerekítve: a yuv420 kivágás páratlan
    méretet csendben páros-ra igazít, és a nyers kimenet sorai elcsúsznának."""
    from .video import ffmpeg_exe, probe

    w, h, _ = probe(video)
    x0, y0 = int(round(box[0] * w)), int(round(box[1] * h))
    cw, ch = int(round((box[2] - box[0]) * w)) // 2 * 2, int(round((box[3] - box[1]) * h)) // 2 * 2
    x0, y0 = x0 // 2 * 2, y0 // 2 * 2
    cmd = [ffmpeg_exe(), "-v", "error", "-threads", "1", "-i", video, "-vf",
           f"select='not(mod(n\\,{stride}))',crop={cw}:{ch}:{x0}:{y0},format=gray", "-vsync", "0",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout
    n = len(raw) // (cw * ch)
    return np.frombuffer(raw[:n * cw * ch], np.uint8).reshape(n, ch, cw)


def stable_states(crops: np.ndarray, t: np.ndarray, present: np.ndarray) -> list[tuple[float, float, np.ndarray]]:
    """(kezdet, vég, medián kép) minden legalább STABLE_S hosszú, látszó, változatlan szakaszra."""
    n = len(crops)
    s = crops.reshape(n, -1).astype(np.float32)
    step = np.full(n, np.inf, np.float32)
    step[1:] = np.abs(s[1:] - s[:-1]).mean(1)
    ok = present[:n] & (step < STEP_DIFF)
    if n:
        ok[0] = present[0]
    out, i = [], 0
    while i < n:
        if not ok[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and ok[j + 1]:
            j += 1
        if t[j] - t[i] >= STABLE_S:
            out.append((float(t[i]), float(t[j]), np.median(crops[i:j + 1], 0).astype(np.uint8)))
        i = j + 1
    return out


def glyphs(img: np.ndarray) -> list[list[np.ndarray]]:
    """A két oldal jelei balról jobbra, egységes méretre hozva: [[hazai jelek], [vendég jelek]]."""
    from PIL import Image
    from scipy import ndimage

    w = img.shape[1]
    mid = int(round(SPLIT * w))
    out = []
    for a, b in ((0, mid - SPLIT_GAP), (mid + SPLIT_GAP, w)):
        x = img[:, a:b] > BRIGHT
        lab, _ = ndimage.label(x)
        g = []
        for q, sl in enumerate(ndimage.find_objects(lab)):
            if sl is None:
                continue
            hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            if hh < MIN_H_FRAC * x.shape[0] or ww < MIN_W_PX:
                continue
            m = ((lab[sl] == q + 1) * 255).astype(np.uint8)
            g.append((sl[1].start, np.asarray(Image.fromarray(m).resize(GLYPH, Image.BILINEAR), np.float32) / 255.0))
        g.sort(key=lambda z: z[0])
        out.append([z[1] for z in g])
    return out


def read_state(img: np.ndarray, centers: np.ndarray, labels: list[int | None]) -> tuple[int, int] | None:
    """A két szám egy állapot képéről; None, ha bármelyik jel bizonytalan."""
    res = []
    for side in glyphs(img):
        if not 1 <= len(side) <= 2:
            return None
        digits = []
        for g in side:
            d = ((centers - g.ravel()) ** 2).sum(1)
            c = int(d.argmin())
            if labels[c] is None or d[c] > MAX_DIST:
                return None
            digits.append(str(labels[c]))
        res.append(int("".join(digits)))
    return res[0], res[1]


def timeline(readings: list[tuple[float, float, tuple[int, int] | None]]) -> dict:
    """Az állás-idővonal: csak a növekvő, lépésenként legfeljebb +2 gólos olvasatok.

    Egy gól ideje a [előző állapot vége, új állapot kezdete] sávba esik (a grafika
    közben nem látszott, vagy épp változott)."""
    seq = [{"t": 0.0, "t_elozo": 0.0, "allas": (0, 0)}]
    last_end, rejected = 0.0, []
    for t0, t1, r in readings:
        if r is None:
            continue
        h, v = seq[-1]["allas"]
        if r == (h, v):
            last_end = t1
            continue
        dh, dv = r[0] - h, r[1] - v
        if dh >= 0 and dv >= 0 and dh + dv <= 2:
            seq.append({"t": t0, "t_elozo": last_end, "allas": r})
            last_end = t1
        else:
            rejected.append({"t": t0, "olvasat": r, "elozo": (h, v)})
    goals = []
    for prev, cur in zip(seq[:-1], seq[1:]):
        for side, k in (("hazai", 0), ("vendeg", 1)):
            for _ in range(cur["allas"][k] - prev["allas"][k]):
                goals.append({"csapat": side, "t_tol": round(cur["t_elozo"], 1), "t_ig": round(cur["t"], 1),
                              "allas_utana": list(cur["allas"])})
    return {"vegeredmeny": list(seq[-1]["allas"]), "golok": goals, "valtozasok": len(seq) - 1,
            "elutasitott": rejected}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Az állás kiolvasása az eredményjelzőből")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crops")
    c.add_argument("--video", required=True)
    c.add_argument("--box", type=float, nargs=4, required=True, help="az állás-rész (x0 y0 x1 y1, 0..1)")
    c.add_argument("--stride", type=int, required=True, help="ugyanaz, mint a hbd.broadcast-nál")
    c.add_argument("--out", required=True)
    k = sub.add_parser("cluster")
    k.add_argument("--crops", required=True)
    k.add_argument("--broadcast", required=True)
    k.add_argument("--k", type=int, default=14)
    k.add_argument("--out", required=True)
    r = sub.add_parser("read")
    r.add_argument("--crops", required=True)
    r.add_argument("--broadcast", required=True)
    r.add_argument("--templates", required=True)
    r.add_argument("--labels", required=True, help="a klaszterek számjegyei vesszővel; x = nem számjegy")
    r.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "crops":
        np.save(args.out, extract_crops(args.video, args.box, args.stride))
        return 0
    from .broadcast import SB_PRESENT_NCC, load

    crops = np.load(args.crops)
    bc = load(args.broadcast)
    n = min(len(crops), len(bc["t"]))
    states = stable_states(crops[:n], bc["t"][:n], bc["sb_ncc"][:n] > SB_PRESENT_NCC)
    if args.cmd == "cluster":
        from PIL import Image
        from sklearn.cluster import KMeans

        G = np.array([g.ravel() for _, _, img in states for side in glyphs(img) for g in side])
        km = KMeans(args.k, n_init=10, random_state=0).fit(G)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        np.save(out / "kozeppontok.npy", km.cluster_centers_)
        gw, gh = GLYPH
        rows = []
        for ci in range(args.k):
            ex = [np.pad(e.reshape(gh, gw), 1, constant_values=0.5) for e in G[km.labels_ == ci][:8]]
            ex += [np.full((gh + 2, gw + 2), 0.5)] * (8 - len(ex))
            rows.append(np.hstack(ex))
        im = (np.vstack(rows) * 255).astype(np.uint8)
        Image.fromarray(im).resize((im.shape[1] * 3, im.shape[0] * 3), Image.NEAREST).save(out / "klaszterek.png")
        print(f"{len(states)} állapot, {len(G)} jel → {out / 'klaszterek.png'} (soronként egy klaszter; címkézd)")
        return 0
    centers = np.load(args.templates)
    labels = [None if x.strip() in ("x", "") else int(x) for x in args.labels.split(",")]
    readings = [(t0, t1, read_state(img, centers, labels)) for t0, t1, img in states]
    res = timeline(readings)
    res["allapotok"] = len(states)
    res["olvashato"] = sum(r[2] is not None for r in readings)
    Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"végeredmény {res['vegeredmeny'][0]}:{res['vegeredmeny'][1]}, {len(res['golok'])} gól, "
          f"{res['olvashato']}/{len(states)} állapot olvasható, {len(res['elutasitott'])} elutasított olvasat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
