"""
Finomhangoló CLI — a YOLO detektor tanítása a saját kézilabda-adathalmazon.

Bemenet a scripts/collect_dataset.py által gyűjtött (és emberileg átnézett)
YOLO-adathalmaz. A tanítás az ultralytics beépített train-jével fut; a kész
modellt a --install kapcsoló a program felhasználói súly-mappájába másolja
`yolov8n.pt` néven — a feldolgozó a helyi súly-mappát részesíti előnyben,
így a TELJES alkalmazás (feltöltés-feldolgozás) beállítás nélkül az új,
kézilabdára hangolt modellt használja. Teljes útmutató: docs/FINETUNE.md.

Használat:
    python -m scripts.finetune --data dataset/dataset.yaml \
        [--model yolov8n.pt] [--epochs 60] [--imgsz 960] [--install]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.process_video import _pick_device, _resolve_weights  # noqa: E402


def install_weights(best: Path) -> Path:
    """A kész modellt a felhasználói súly-mappába másolja `yolov8n.pt`
    néven (a korábbi fájl .bak mentésével) — a feldolgozó ezt a mappát
    részesíti előnyben, így az app azonnal az új modellt használja."""
    from handball.storage import data_root
    wdir = data_root() / "weights"
    wdir.mkdir(parents=True, exist_ok=True)
    target = wdir / "yolov8n.pt"
    if target.exists():
        shutil.copy2(target, target.with_suffix(".pt.bak"))
    shutil.copy2(best, target)
    return target


def main() -> int:
    ap = argparse.ArgumentParser(
        description="YOLO finomhangolás a kézilabda-adathalmazon")
    ap.add_argument("--data", required=True,
                    help="a dataset.yaml útja (collect_dataset kimenete)")
    ap.add_argument("--model", default="yolov8n.pt",
                    help="kiinduló modell (alap: yolov8n.pt)")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=960,
                    help="tanítási felbontás (alap: 960 — jó kompromisszum)")
    ap.add_argument("--batch", type=int, default=-1,
                    help="batch-méret (-1 = automatikus a memóriához)")
    ap.add_argument("--install", action="store_true",
                    help="a kész modellt élesbe állítja (felhasználói "
                         "súly-mappa) — a program ezt fogja használni")
    args = ap.parse_args()

    if not Path(args.data).exists():
        print(f"HIBA: nincs ilyen adathalmaz: {args.data}")
        return 1

    from ultralytics import YOLO
    device = _pick_device()
    print(f"tanítás indul · eszköz: {device} · adat: {args.data}")
    model = YOLO(_resolve_weights(args.model))
    results = model.train(data=args.data, epochs=args.epochs,
                          imgsz=args.imgsz, batch=args.batch, device=device,
                          project="runs", name="handball", exist_ok=True)
    best = Path(getattr(results, "save_dir", "runs/handball")) / "weights" / "best.pt"
    if not best.exists():
        print("HIBA: nem található a kész modell (best.pt) — a tanítás "
              "nem fejeződött be rendben.")
        return 1
    print(f"kész modell: {best}")

    if args.install:
        target = install_weights(best)
        print(f"ÉLESBE ÁLLÍTVA: {target}")
        print("A program mostantól ezt a modellt használja; visszaállítás: "
              "töröld a fájlt (a letöltött alapmodell visszaáll), vagy "
              "másold vissza a .bak mentést.")
    else:
        print("Élesbe állítás: python -m scripts.finetune --data ... --install")
        print("(vagy másold a best.pt-t a felhasználói weights/ mappába "
              "yolov8n.pt néven)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
