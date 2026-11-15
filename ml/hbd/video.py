"""Képkockák olvasása ffmpeg-gel.

Miért nem OpenCV? A felhős gépen az OpenCV videó-dekódere ezeken a
fájlokon összeomlott (szegmentálási hiba), az ffmpeg viszont stabil és a
Kaggle-képen is megvan. Ha nincs rendszer-ffmpeg, az `imageio-ffmpeg`
csomag statikus binárisát használjuk.

A kockákat EGYENKÉNT adjuk vissza (generátor): egy 2704×1520-as jelenet
egészében több GB lenne a memóriában.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

import numpy as np

_SIZE_RE = re.compile(r"\b(\d{2,5})x(\d{2,5})\b")
_FPS_RE = re.compile(r"(\d+(?:\.\d+)?) fps")


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:  # pragma: no cover - környezetfüggő
        raise RuntimeError("Nincs ffmpeg: telepítsd (apt) vagy `pip install imageio-ffmpeg`") from e


def probe(path: str | Path) -> tuple[int, int, float]:
    """(szélesség, magasság, fps) az ffmpeg fejléc-kiírásából (ffprobe nélkül)."""
    p = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True
    )
    for line in p.stderr.splitlines():
        if "Video:" in line:
            m = _SIZE_RE.search(line.split("Video:", 1)[1])
            f = _FPS_RE.search(line)
            if m:
                return int(m.group(1)), int(m.group(2)), float(f.group(1)) if f else 0.0
    raise RuntimeError(f"Nem olvasható videó: {path}")


def iter_frames(path: str | Path, gray: bool = False) -> Iterator[np.ndarray]:
    """A videó kockái sorban: (H, W) szürke vagy (H, W, 3) BGR uint8."""
    w, h, _ = probe(path)
    ch = 1 if gray else 3
    size = w * h * ch
    proc = subprocess.Popen(
        [ffmpeg_exe(), "-v", "error", "-i", str(path), "-f", "rawvideo",
         "-pix_fmt", "gray" if gray else "bgr24", "-"],
        stdout=subprocess.PIPE,
        # a klip végén szándékosan bezárjuk a csövet → az ffmpeg "Broken pipe"-ot
        # írna; ez nem hiba, ne szemetelje a naplót
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdout is not None
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            arr = np.frombuffer(buf, np.uint8)
            yield arr.reshape(h, w) if gray else arr.reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def read_frames(path: str | Path, gray: bool = False) -> np.ndarray:
    """Az összes kocka egy tömbben — csak KIS videóra (a kivágott klipekre)."""
    frames = list(iter_frames(path, gray=gray))
    if not frames:
        raise RuntimeError(f"Üres videó: {path}")
    return np.stack(frames)
