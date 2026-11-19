"""Lövés-klipek kivágása egy meccsfelvételből a meccsjelölő időpontjai alapján.

Bemenet: a meccsfelvétel és a meccsjelölő adatbázis-dokumentuma (JSON).
A jelölési szokás: a lövés pillanatában L, majd az eredmény (G/V/M) pár
tized másodperccel később; a PAIR_S-en belüli pár egy lövés (ugyanaz a
szabály, mint az oldalon). A kipattanó (K) mindig új lövés; az ismétlésből
jelölt lövések "ismetles" jelzést kapnak.

Kimenet:
  v/<id>.mp4      — klip a nyomás előtt PRE_S és utána POST_S másodperccel,
                    beégetett kockaszámmal (k = a klip kockája)
  manifest.json   — a lövésjelölő oldal bemenete
  negativ.json    — "nem lövés" időablakok a lövésfelismerő tanításához
                    (egyetlen jelöléshez sincs NEG_GAP_S-nél közelebb)

    python tools/cut_match_clips.py --video meccs.mp4 --events meccs.json --out m1 --prefix m1
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
from multiprocessing import Pool
from pathlib import Path

# Egy lövéshez tartozó eredmény-nyomás legkésőbb ennyi másodperccel jön.
PAIR_S = 4.0
# A klip a nyomás előtt / után (s). A nyomás a reakcióidő miatt a lövés UTÁN jön.
PRE_S = 3.0
POST_S = 2.0
# Negatív ("nem lövés") ablak: ilyen hosszú, és minden jelöléstől ennyire távol.
NEG_LEN_S = 5.0
NEG_GAP_S = 6.0
CRF = "32"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def pair_shots(events: list[dict]) -> list[dict]:
    """A nyomások lövésekké párosítása (az oldal shotsView szabálya)."""
    out, i = [], 0
    while i < len(events):
        e = events[i]
        n = events[i + 1] if i + 1 < len(events) else None
        if (e["tipus"] == "loves" and not e.get("eredmeny") and n and n.get("tipus") == "loves"
                and n.get("eredmeny") and not n.get("kipattano") and n["t"] - e["t"] <= PAIR_S
                and bool(n.get("ismetles")) == bool(e.get("ismetles"))):
            out.append({**e, "eredmeny": n["eredmeny"], "t_eredmeny": n["t"]})
            i += 2
        else:
            out.append(dict(e))
            i += 1
    return out


def probe_fps(video: str) -> float:
    o = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=r_frame_rate", "-of", "default=nw=1:nk=1", video], text=True)
    a, b = o.strip().split("/")
    return float(a) / float(b)


def cut(job) -> dict:
    video, out_dir, item, fps, width = job
    start = max(0.0, item["t"] - PRE_S)
    dur = PRE_S + POST_S
    dst = out_dir / "v" / f"{item['id']}.mp4"
    label = "k=%{eif\\:n\\:d}" + ("   ISMETLES" if item.get("ismetles") else "")
    vf = (f"setpts=PTS-STARTPTS,scale={width}:-2,drawtext=fontfile={FONT}:text='{label}':x=12:y=12:fontsize=26:"
          "fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=6")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", video, "-t", f"{dur:.3f}",
                    "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF, "-g", "12", "-bf", "0",
                    "-pix_fmt", "yuv420p", "-avoid_negative_ts", "make_zero",
                    "-movflags", "+faststart", str(dst)], check=True)
    frames = int(round(dur * fps))
    return {"id": item["id"], "src": f"v/{item['id']}.mp4", "fps": round(fps, 3), "n": frames,
            "frames": frames, "t_video": round(item["t"], 2), "t_start": round(start, 2),
            "press_k": int(round((item["t"] - start) * fps)), "eredmeny": item.get("eredmeny"),
            "ismetles": bool(item.get("ismetles")), "kipattano": bool(item.get("kipattano"))}


def negative_windows(shots, events, duration, n, seed=0):
    presses = sorted(e["t"] for e in events)
    rng = random.Random(seed)
    out, tries = [], 0
    while len(out) < n and tries < n * 200:
        tries += 1
        s = rng.uniform(0, max(0.0, duration - NEG_LEN_S))
        mid = s + NEG_LEN_S / 2
        if all(abs(p - mid) > NEG_GAP_S + NEG_LEN_S / 2 for p in presses):
            out.append(round(s, 2))
    return sorted(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--events", required=True, help="a meccsjelölő adatbázis-dokumentuma (JSON)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix", default="m1")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--negatives", type=int, default=600)
    args = ap.parse_args(argv)

    doc = json.loads(Path(args.events).read_text())
    doc = doc.get("data", doc)
    events = sorted(doc["esemenyek"], key=lambda e: e["t"])
    shots = [s for s in pair_shots(events) if s["tipus"] == "loves"]
    for i, s in enumerate(shots):
        s["id"] = f"{args.prefix}_{i:03d}{'_ism' if s.get('ismetles') else ''}"
    out = Path(args.out)
    (out / "v").mkdir(parents=True, exist_ok=True)
    fps = probe_fps(args.video)
    with Pool(args.workers) as pool:
        items = pool.map(cut, [(args.video, out, s, fps, args.width) for s in shots])
    (out / "manifest.json").write_text(json.dumps({"meccs": doc.get("nev"), "fps": fps, "clips": items},
                                                  ensure_ascii=False))
    neg = negative_windows(shots, events, doc.get("hossz_s") or 0, args.negatives)
    (out / "negativ.json").write_text(json.dumps({"hossz_s": NEG_LEN_S, "kezdetek": neg}))
    size = sum(f.stat().st_size for f in (out / "v").glob("*.mp4"))
    print(f"{len(items)} klip ({sum(not c['ismetles'] for c in items)} élő, "
          f"{sum(c['ismetles'] for c in items)} ismétlés), {size / 1e6:.1f} MB; {len(neg)} negatív ablak → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
