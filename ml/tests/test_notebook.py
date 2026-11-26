"""A Kaggle-notebook a csomag forrásából generált, és naprakész."""

import importlib.util
import json
from pathlib import Path

ML = Path(__file__).resolve().parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location("build_notebook", ML / "kaggle" / "build_notebook.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_notebook_naprakesz():
    b = _builder()
    assert b.NB.read_text() == b.render(), (
        "A notebook elavult: futtasd `cd ml && python kaggle/build_notebook.py`")


def test_notebook_minden_modult_kiir():
    nb = json.loads((ML / "kaggle" / "uniri_hbd_pose.ipynb").read_text())
    written = {c["source"][0].strip() for c in nb["cells"]
               if c["cell_type"] == "code" and c["source"][0].startswith("%%writefile")}
    for f in (ML / "hbd").glob("*.py"):
        assert f"%%writefile hbd/{f.name}" in written, f"{f.name} hiányzik a notebookból"


def test_labda_notebook_naprakesz():
    b = _builder()
    assert b.BALL_NB.read_text() == b.render_ball(), (
        "A labda-notebook elavult: futtasd `cd ml && python kaggle/build_notebook.py`")


def test_labda_notebook_futtato_cellaja_ervenyes_python():
    nb = json.loads(_builder().render_ball())
    run = [c for c in nb["cells"] if c["cell_type"] == "code" and "VARIANTS" in "".join(c["source"])]
    assert len(run) == 1
    compile("".join(run[0]["source"]), "labda_gpu", "exec")
