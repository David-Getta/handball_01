"""
[T] Tanítóadat-gyűjtés — YOLO-formátumú adathalmaz a feldolgozott videókból.

Cél: a detektor (YOLO) KÉZILABDÁRA finomhangolásához tanítóadatot gyűjteni a
saját felvételekből. A jelenlegi (általános) modell adja az ELŐCÍMKÉKET
(bootstrap): a mintavételezett képkockákra lefut a detektálás, az eredmény
YOLO-label formátumban mentődik — ezt kell embernek átnéznie/javítania egy
címkéző eszközben (pl. CVAT, LabelImg), majd jöhet a tanítás
(scripts/finetune.py). Részletes útmutató: docs/FINETUNE.md.

A modul magja szándékosan FÜGGETLEN az ultralytics-től: a detektálást a hívó
adja át függvényként (detect_fn), így a logika valódi modell nélkül is
tesztelhető, a CLI (scripts/collect_dataset.py) pedig a YOLO-t köti be.

Osztályok a kimeneti adathalmazban: 0 = person (játékos), 1 = ball (labda).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# A finomhangolt modell osztályai. A sorrend számít: a label-fájlok ezekre
# az indexekre hivatkoznak, és a dataset.yaml ezt rögzíti.
CLASS_NAMES = {0: "person", 1: "ball"}


@dataclass
class DatasetStats:
    """A gyűjtés összegzése — a hívó (CLI) ezt írja ki a felhasználónak."""
    images: int = 0
    train_images: int = 0
    val_images: int = 0
    person_boxes: int = 0
    ball_boxes: int = 0
    images_with_ball: int = 0
    skipped_dark: int = 0
    yaml_path: str = ""
    notes: list = field(default_factory=list)


def sample_frame_indices(n_total: int, count: int, start: int = 0) -> list[int]:
    """Egyenletesen elosztott képkocka-indexek a videó `start` utáni részéből.

    Egyenletes mintát veszünk (nem egymás utáni kockákat), hogy a tanítóadat
    változatos legyen — az egymás melletti kockák majdnem azonosak, keveset
    tanítanak."""
    if n_total <= start or count <= 0:
        return []
    span = n_total - start
    count = min(count, span)
    stepped = [start + round(i * (span - 1) / max(1, count - 1))
               for i in range(count)]
    # Kerekítésből adódó duplikátumok kiszűrése, sorrendben.
    seen: set[int] = set()
    out = []
    for i in stepped:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def yolo_label_lines(boxes: list, width: int, height: int) -> list[str]:
    """YOLO label-sorok: "osztály cx cy w h" — 0..1-re normálva.

    `boxes`: (class_id, x1, y1, x2, y2) pixelben. A képen kívülre lógó
    dobozokat a kép szélére vágjuk; az elfajult (0 területű) doboz kimarad."""
    lines = []
    for (cls, x1, y1, x2, y2) in boxes:
        x1, x2 = max(0.0, min(x1, x2)), min(float(width), max(x1, x2))
        y1, y2 = max(0.0, min(y1, y2)), min(float(height), max(y1, y2))
        w, h = x2 - x1, y2 - y1
        if w <= 1 or h <= 1:
            continue
        cx, cy = x1 + w / 2, y1 + h / 2
        lines.append(f"{int(cls)} {cx / width:.6f} {cy / height:.6f} "
                     f"{w / width:.6f} {h / height:.6f}")
    return lines


def write_dataset_yaml(out_dir: Path) -> Path:
    """A YOLO-tanításhoz szükséges dataset.yaml megírása."""
    names = "\n".join(f"  {k}: {v}" for k, v in CLASS_NAMES.items())
    yaml_path = out_dir / "dataset.yaml"
    yaml_path.write_text(
        f"path: {out_dir.resolve()}\n"
        "train: images/train\n"
        "val: images/val\n"
        f"names:\n{names}\n",
        encoding="utf-8")
    return yaml_path


def collect_dataset(video_path: str | Path,
                    detect_fn: Callable,
                    out_dir: str | Path,
                    samples: int = 200,
                    start: int = 0,
                    val_ratio: float = 0.1,
                    skip_dark: bool = True,
                    dark_thresh: float = 40.0) -> DatasetStats:
    """Képkockák mintavételezése egy videóból + előcímkék a detektorral.

    - detect_fn(img) -> [(name, conf, x1, y1, x2, y2), ...] — a név "person"
      vagy "ball" (mást eldobunk); a koordináták pixelben.
    - Minden ~10. minta a validációs halmazba kerül (val_ratio szerint).
    - A sötét (bevezető/átúszós) kockákat kihagyjuk.

    A képek a videó nevével prefixelve mentődnek, így TÖBB videóból is
    gyűjthető ugyanabba a mappába — a kész adathalmaz együtt nő.
    """
    import cv2

    video_path = Path(video_path)
    out_dir = Path(out_dir)
    stats = DatasetStats()

    cap = cv2.VideoCapture(str(video_path))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n_total <= 0:
        cap.release()
        raise RuntimeError(f"A videó nem olvasható: {video_path}")

    for split in ("train", "val"):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    stem = video_path.stem.replace(" ", "_")
    val_every = max(2, round(1 / val_ratio)) if val_ratio > 0 else 0
    kept = 0
    for idx in sample_frame_indices(n_total, samples, start=start):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, img = cap.read()
        if not ok:
            continue
        if skip_dark and float(img.mean()) < dark_thresh:
            stats.skipped_dark += 1
            continue
        H, W = img.shape[:2]
        boxes = []
        has_ball = False
        for (name, conf, x1, y1, x2, y2) in detect_fn(img):
            if name == "person":
                boxes.append((0, x1, y1, x2, y2))
            elif name == "ball":
                boxes.append((1, x1, y1, x2, y2))
                has_ball = True
        lines = yolo_label_lines(boxes, W, H)
        # Detektálás nélküli kockát nem mentünk: előcímke nélkül a kocka a
        # címkézőben csak plusz kézi munka, a bootstrap lényege az előcímke.
        if not lines:
            continue
        kept += 1
        split = "val" if (val_every and kept % val_every == 0) else "train"
        name = f"{stem}_{idx:06d}"
        cv2.imwrite(str(out_dir / "images" / split / f"{name}.jpg"), img,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        (out_dir / "labels" / split / f"{name}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        stats.images += 1
        if split == "train":
            stats.train_images += 1
        else:
            stats.val_images += 1
        stats.person_boxes += sum(1 for line in lines if line.startswith("0 "))
        stats.ball_boxes += sum(1 for line in lines if line.startswith("1 "))
        if has_ball:
            stats.images_with_ball += 1
    cap.release()

    stats.yaml_path = str(write_dataset_yaml(out_dir))
    if stats.images and stats.images_with_ball / stats.images < 0.3:
        stats.notes.append(
            "Kevés képen látszik a labda — a labda-osztály tanításához "
            "érdemes kézzel pótolni a hiányzó labda-dobozokat a címkézőben.")
    return stats
