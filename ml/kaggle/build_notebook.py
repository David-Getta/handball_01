"""A Kaggle-notebook előállítása az `ml/hbd` forrásából.

A notebook ÖNÁLLÓ: a csomag fájljait `%%writefile` cellákkal írja ki, így
nem kell hozzá a (privát) GitHub-repó. A forrás változásakor újra kell
generálni — a `tests/test_notebook.py` őrzi, hogy a notebook naprakész.

    cd ml && python kaggle/build_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

ML = Path(__file__).resolve().parents[1]
NB = ML / "kaggle" / "uniri_hbd_pose.ipynb"
MODULES = ["__init__", "dataset", "video", "locate", "pose", "features", "goalkeeper", "models",
           "train", "release", "match_pose", "broadcast", "shot_detect", "match_shots"]

INTRO = """# Sport Machine — kézilabda-mozdulatfelismerés (UNIRI-HBD)

Mit csinál ez a notebook:
1. Minden kivágott klipnél megkeresi a végrehajtót a teljes jelenetben, és előtanított
   **YOLO11-pose** modellel kinyeri a 17 testpontot kockánként (→ `poses.npz`).
2. Kiértékel három feladatot, **jelenet szerint csoportosított 5-szörös keresztvalidációval**:
   lövés / nem lövés · felugrásos / helyből / egyéb · mind a 7 kategória.
3. Minden lövésre kapus-szempontú profilt ír (lövőkéz, kartartás, felugrás) → `kapus_profilok.csv`.
4. Végső modelleket ment (`model_*.joblib`, `model_*.pt`) a Macen futtatáshoz.

**Beállítás (egyszer):**
- *Add Input* → a feltöltött `uniri-hbd` adathalmaz (a zip; a Kaggle kibontja).
- *Settings → Accelerator*: **GPU T4 x2** (egyet használunk). *Internet*: **On** (pip + súlyok).
- *Run All*. Kb. 30–50 perc; a kimenet a jobb oldali *Output* fülön (`/kaggle/working`).

Ha megszakad: újraindítva a már kész klipeket a gyorsítótárból (`poses_cache/`) veszi.

Adat: UNIRI-HBD, Ivašić-Kos, M., Pobar, M., University of Rijeka, DOI 10.21227/0g0a-fe06, CC BY 4.0.
"""


def _cell(kind: str, src: str) -> dict:
    lines = src.splitlines(keepends=True)
    c = {"cell_type": kind, "metadata": {}, "source": lines}
    if kind == "code":
        c.update(execution_count=None, outputs=[])
    return c


def build() -> dict:
    cells = [_cell("markdown", INTRO),
             _cell("code", "!pip install -q ultralytics imageio-ffmpeg\n!nvidia-smi -L || true"),
             _cell("markdown", "## A csomag forrása (a repó `ml/hbd` mappájából generálva)"),
             # a %%writefile nem hoz létre mappát → előtte külön cellában
             _cell("code", "import os\nos.makedirs('hbd', exist_ok=True)")]
    for m in MODULES:
        src = (ML / "hbd" / f"{m}.py").read_text()
        cells.append(_cell("code", f"%%writefile hbd/{m}.py\n{src}"))
    cells += [
        _cell("markdown", "## 1. Testpont-kinyerés (GPU)"),
        _cell("code", (
            "from hbd.dataset import find_root, index_dataset\n"
            "DATA = str(find_root('/kaggle/input'))\n"
            "print('adat:', DATA, '| klipek:', len(index_dataset(DATA)))")),
        _cell("code", (
            "!python -m hbd.pose --data \"$DATA\" --out /kaggle/working/poses.npz "
            "--device 0 --preview 6")),
        _cell("code", (
            "from IPython.display import Image, display\n"
            "display(Image('/kaggle/working/poses_preview.jpg'))")),
        _cell("markdown", "## 2. Kiértékelés és végső modellek"),
        _cell("code", "!python -m hbd.train --poses /kaggle/working/poses.npz --out /kaggle/working/results"),
        _cell("code", (
            "from IPython.display import Markdown\n"
            "display(Markdown(open('/kaggle/working/results/results.md').read()))")),
    ]
    return {"cells": cells, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=1) + "\n"


if __name__ == "__main__":
    NB.write_text(render())
    print(f"kész: {NB}")
