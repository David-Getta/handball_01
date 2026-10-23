"""Feldolgozási füstteszt a BECSOMAGOLT motorra (a kiadás-build lépése).

Miért kell: a régi füstteszt csak azt nézte, hogy a motor elindul és a
fiók-út megy — VALÓDI feldolgozást sosem futtatott. A becsomagolt
motorba minden kiadásnál a legfrissebb torch / ultralytics / OpenCV
kerül, és ha ezek közül valamelyik a csomagban a detektálásnál
összeomlik, az csak a felhasználónál derült ki: a feldolgozás 2%-nál
megállt, "a motor újraindult". Ez a teszt a kliens kérésével (yolov8n,
kiegyensúlyozott profil, két térfél-kalibráció — az egyik sarok a képen
kívül —, kezdőkocka, mezszám-felismerés) egy rövid videót dolgoztat fel,
és hibánál kiírja a motor naplóját és a natív összeomlás nyomát.

Használat:
    python packaging/smoke_process.py <motor-program> <adatmappa>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# Külön port: az előző füstteszt motorja még elengedheti a 8000-est.
PORT = 8123
# Ennyi ideig várunk a kész feldolgozásra (a CI-gép lassú CPU-n fut).
TIMEOUT_S = 900


def _video(path: Path) -> None:
    """Rövid teszt-videó emberekkel: az ultralytics saját képe (bus.jpg),
    képkockánként eltolva — van mit detektálni és követni."""
    import cv2
    import numpy as np
    kep = None
    try:
        import ultralytics
        kep = cv2.imread(str(Path(ultralytics.__file__).parent / "assets"
                             / "bus.jpg"))
    except Exception:
        pass
    if kep is None:
        kep = np.full((1080, 810, 3), 128, np.uint8)
    kep = cv2.resize(kep, (1280, 720))
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                         (1280, 720))
    for k in range(150):
        m = np.float32([[1, 0, 2 * (k % 40)], [0, 1, 0]])
        vw.write(cv2.warpAffine(kep, m, (1280, 720),
                                borderMode=cv2.BORDER_REFLECT))
    vw.release()


def _get(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url: str, body: dict):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _naplok(adat: Path, kimenet: Path) -> None:
    print("--- a motor kimenete (vége) ---")
    try:
        print("\n".join(kimenet.read_text(encoding="utf-8",
                                          errors="replace").splitlines()[-80:]))
    except OSError:
        print("(nincs)")
    for nev in ("engine-crash.log", "engine.log"):
        p = adat / nev
        if p.exists():
            print(f"--- {nev} (vége) ---")
            print("\n".join(p.read_text(encoding="utf-8",
                                        errors="replace").splitlines()[-80:]))


def main(argv: list[str]) -> int:
    exe, adat = argv[1], Path(argv[2])
    adat.mkdir(parents=True, exist_ok=True)
    video = Path(tempfile.mkdtemp(prefix="smoke_")) / "smoke.mp4"
    _video(video)
    kimenet = adat / "smoke-engine-out.log"
    env = dict(os.environ, HANDBALL_DATA_DIR=str(adat),
               HANDBALL_PORT=str(PORT))
    with open(kimenet, "w", encoding="utf-8") as ki:
        p = subprocess.Popen([exe], stdout=ki, stderr=subprocess.STDOUT,
                             env=env, cwd=str(Path(exe).parent))
    alap = f"http://127.0.0.1:{PORT}"
    try:
        for _ in range(90):
            time.sleep(2)
            if p.poll() is not None:
                print(f"A motor elindulás közben leállt (kód: {p.returncode})")
                _naplok(adat, kimenet)
                return 1
            try:
                if _get(alap + "/health", 2).get("status") == "ok":
                    break
            except Exception:
                continue
        else:
            print("A motor nem válaszolt a /health-en")
            _naplok(adat, kimenet)
            return 1
        # A kliens kérése (upload_screen): yolov8n, stride 3, imgsz 1280,
        # két térfél-kalibráció (a jobb fél egyik sarka a képen kívül),
        # kezdőkocka, mezszám-felismerés.
        test = {
            "path": str(video), "weights": "yolov8n.pt", "stride": 3,
            "imgsz": 1280, "max": 12, "start": 30, "jersey_ocr": True,
            "home_team": "Füst A", "away_team": "Füst B",
            "calibs": [
                {"corners": [[20, 300], [640, 260], [640, 700], [10, 710]],
                 "region": "left", "rotate": False, "frame": 30},
                {"corners": [[-4, 595], [893, 475], [1270, 611], [101, 2646]],
                 "region": "right", "rotate": False, "frame": 60},
            ],
        }
        jid = _post(alap + "/matches/process", test)["job_id"]
        print("feldolgozás elindítva:", jid)
        hatarido = time.time() + TIMEOUT_S
        utolso = None
        while time.time() < hatarido:
            time.sleep(3)
            if p.poll() is not None:
                print(f"A MOTOR FELDOLGOZÁS KÖZBEN LEÁLLT (kód: {p.returncode});"
                      f" utolsó állapot: {utolso}")
                _naplok(adat, kimenet)
                return 1
            try:
                j = _get(f"{alap}/jobs/{jid}")
            except Exception as e:
                print("lekérdezési hiba:", e)
                continue
            allapot = (j.get("status"), j.get("stage"), j.get("progress"),
                       j.get("message"))
            if allapot != utolso:
                print("  ", allapot)
                utolso = allapot
            if j.get("status") == "done":
                m = _get(f"{alap}/matches")
                print("KÉSZ — meccsek:", [x.get("match_id")
                                          for x in m.get("matches", [])])
                return 0
            if j.get("status") in ("error", "cancelled"):
                print("A FELDOLGOZÁS HIBÁVAL ZÁRULT:", j.get("error"))
                _naplok(adat, kimenet)
                return 1
        print("A feldolgozás nem ért véget időben")
        _naplok(adat, kimenet)
        return 1
    finally:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(10)
            except Exception:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
