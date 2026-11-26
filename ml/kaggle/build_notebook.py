"""A Kaggle-notebook előállítása az `ml/hbd` forrásából.

A notebook ÖNÁLLÓ: a csomag fájljait `%%writefile` cellákkal írja ki, így
nem kell hozzá a (privát) GitHub-repó. A forrás változásakor újra kell
generálni — a `tests/test_notebook.py` őrzi, hogy a notebook naprakész.

    cd ml && python kaggle/build_notebook.py

Két notebook készül:
  uniri_hbd_pose.ipynb — testpont-kinyerés és mozdulat-modellek (UNIRI-HBD);
  labda_gpu.ipynb      — nagyobb labdafelismerők tanítása és összevetése GPU-n
                         (bemenet: a `tools/labda_kaggle_csomag.py` zipje).
"""

from __future__ import annotations

import json
from pathlib import Path

ML = Path(__file__).resolve().parents[1]
NB = ML / "kaggle" / "uniri_hbd_pose.ipynb"
MODULES = ["__init__", "dataset", "video", "locate", "pose", "features", "goalkeeper", "models",
           "train", "release", "match_pose", "broadcast", "court", "shot_detect", "match_shots", "ball", "hand_image",
           "shooter_ball", "scoreboard", "ticker"]

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


BALL_NB = ML / "kaggle" / "labda_gpu.ipynb"
BALL_MODULES = ["__init__", "video", "ball"]

BALL_INTRO = """# Sport Machine — nagyobb labdafelismerő GPU-n

A kis (YOLO11n, 320 px) labdafelismerő a félretett 40 lövésen kockánként 64%-ot
talál; a repülő, elmosódott labdát a legjobb 5 jelöltje közé is csak 65%-ban
teszi. Az öntanítás nem segített. Ez a notebook azt méri, hogy a **nagyobb
modell** és a **nagyobb felbontás** (a 320 px-es kivágások 2× nagyítva) segít-e.

Változatok (mind ugyanazon a félretett 40 lövésen, 110 labdaponton mérve):

| név | modell | tanítás | kiértékelés |
|---|---|---|---|
| v2_alap | a jelenlegi (YOLO11n) | — | 640 |
| s320 | YOLO11s | 320 | 640 |
| s640 | YOLO11s | 640 (2×) | 1280 |
| m640 | YOLO11m | 640 (2×) | 1280 |

**Beállítás (egyszer):**
- *Add Input* → a feltöltött `labda_kaggle.zip` adathalmaz (**privát**; a Kaggle kibontja).
- *Settings → Accelerator*: **GPU T4 x2** (egyet használunk). *Internet*: **On**.
- *Save Version → Save & Run All* (a háttérben fut, bezárhatod). Kb. 2–3 óra.

Kimenet (*Output* fül): `labda_eredmenyek.md` (a táblázat), `eredmeny_*.json`,
és a modellek: `labda_s320.pt`, `labda_s640.pt`, `labda_m640.pt`.
Ha megszakad, újraindítva a kész változatokat kihagyja.
"""

BALL_RUN = """import glob, json, shutil, subprocess, sys
from pathlib import Path

IN = Path(glob.glob('/kaggle/input/**/balldata/eval_points.json', recursive=True)[0]).parents[1]
W = Path('/kaggle/working')
D = W / 'balldata'      # másolat: a YOLO a címkék mellé gyorsítótárat ír, a bemenet csak olvasható
if not D.exists():
    shutil.copytree(IN / 'balldata', D)
(D / 'data.yaml').write_text(f"path: {D}\\ntrain: images/train\\nval: images/val\\nnames:\\n  0: labda\\n")
V = IN / 'labdavideo'
print('bemenet:', IN, '| tanító képek:', len(list((D / 'images' / 'train').iterdir())))

EPOCHS = 60
# (név, kiinduló súly, tanító bemenet px, kiértékelő bemenet px, köteg)
VARIANTS = [
    ('v2_alap', None, None, 640, None),
    ('s320', 'yolo11s.pt', 320, 640, 32),
    ('s640', 'yolo11s.pt', 640, 1280, 16),
    ('m640', 'yolo11m.pt', 640, 1280, 16),
]


def run(name, base, tr, ev, batch):
    out = W / f'eredmeny_{name}.json'
    if out.exists():
        return json.loads(out.read_text())
    if base:
        wt = W / 'runs_ball' / name / 'weights' / 'best.pt'
        if not wt.exists():
            subprocess.run([sys.executable, '-m', 'hbd.ball', 'train', '--data', str(D), '--weights', base,
                            '--epochs', str(EPOCHS), '--device', '0', '--imgsz', str(tr), '--batch', str(batch),
                            '--patience', '20', '--project', str(W / 'runs_ball'), '--name', name], check=True)
        shutil.copy(wt, W / f'labda_{name}.pt')
    else:
        wt = IN / 'alap' / 'labda2.pt'
    subprocess.run([sys.executable, '-m', 'hbd.ball', 'evaluate', '--data', str(D), '--weights', str(wt),
                    '--ball-dir', str(V), '--imgsz', str(ev), '--out', str(out)], check=True,
                   stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def table(results):
    pct = lambda x: f"{100 * x:.0f}%"
    rows = ['| változat | kockánként | kézben / elválik / repül | követés | összefésülés |', '|---|---|---|---|---|']
    for name, r in results.items():
        k = r['kovetessel']
        rows.append(f"| {name} | {pct(r['osszes']['talalat'])} | "
                    f"{pct(r['kezben']['talalat'])} / {pct(r['elvalik']['talalat'])} / {pct(r['repul']['talalat'])} | "
                    f"{pct(k['kovetes']['osszes'])} | {pct(k['osszefesult']['osszes'])} |")
    return '\\n'.join(rows)


results = {}
for v in VARIANTS:
    results[v[0]] = run(*v)
    md = '# Labdafelismerők a félretett 40 lövésen (110 labdapont)\\n\\n' + table(results) + '\\n'
    (W / 'labda_eredmenyek.md').write_text(md)   # minden változat után: megszakadáskor is megmarad
    print(md)
"""


def build_ball() -> dict:
    cells = [_cell("markdown", BALL_INTRO),
             _cell("code", "!pip install -q ultralytics imageio-ffmpeg\n!nvidia-smi -L || true"),
             _cell("markdown", "## A csomag forrása (a repó `ml/hbd` mappájából generálva)"),
             _cell("code", "import os\nos.makedirs('hbd', exist_ok=True)")]
    for m in BALL_MODULES:
        src = (ML / "hbd" / f"{m}.py").read_text()
        cells.append(_cell("code", f"%%writefile hbd/{m}.py\n{src}"))
    cells += [
        _cell("markdown", "## Tanítás és kiértékelés (változatonként)"),
        _cell("code", BALL_RUN),
        _cell("code", (
            "from IPython.display import Markdown\n"
            "display(Markdown(open('/kaggle/working/labda_eredmenyek.md').read()))")),
    ]
    return {"cells": cells, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=1) + "\n"


def render_ball() -> str:
    return json.dumps(build_ball(), ensure_ascii=False, indent=1) + "\n"


if __name__ == "__main__":
    NB.write_text(render())
    BALL_NB.write_text(render_ball())
    print(f"kész: {NB}, {BALL_NB}")
