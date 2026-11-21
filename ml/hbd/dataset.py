"""Az UNIRI-HBD adathalmaz bejárása.

Szerkezet (a zip kibontva):

    handball_s/
        actions/<kategória>/<jelenet>_act<N>.avi   — a végrehajtóra kivágott klip
        scenes/<kategória>/<jelenet>.mp4|.avi       — a teljes jelenet
        player_detections/<kategória>/<jelenet>.csv — játékos-dobozok kockánként

Egy tanító minta = egy kivágott klip (`actions/`). A klip a jelenet
képpontjaiból van kivágva (a sablon-egyezés 1,000), így a jelenetben
pontosan visszakereshető (lásd `locate`). A kiértékelés a JELENET szerint
csoportosít: ugyanannak a jelenetnek két klipje sosem kerülhet egyszerre a
tanító és a teszt részbe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# A zip kategória-mappái (a "lövés" mappa neve "shot", nem "shooting").
CATEGORIES = ("crossing", "defence", "dribbling", "jump-shot", "passing", "running", "shot")
SHOT_CATEGORIES = ("jump-shot", "shot")

# Feladatok: név → (osztálynevek, kategória → osztály-index)
TASKS = {
    # lövés vagy nem lövés — a kapus első kérdése
    "binary": (("nem_loves", "loves"), {c: int(c in SHOT_CATEGORIES) for c in CATEGORIES}),
    # felugrásos lövés / helyből lövés / egyéb
    "shot3": (
        ("egyeb", "felugrasos", "helybol"),
        {c: {"jump-shot": 1, "shot": 2}.get(c, 0) for c in CATEGORIES},
    ),
    # mind a hét kategória (a szakirodalommal összevethető)
    "all7": (CATEGORIES, {c: i for i, c in enumerate(CATEGORIES)}),
}

VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv")
_ACT_RE = re.compile(r"_act\d+$")


@dataclass(frozen=True)
class Clip:
    """Egy kivágott mozdulat-klip és a hozzá tartozó jelenet."""

    name: str  # a klip fájlneve kiterjesztés nélkül, pl. "shot_KS_100_act1"
    category: str  # pl. "shot"
    action_path: Path
    scene_path: Path
    detections_path: Path | None

    @property
    def scene_id(self) -> str:
        """Csoport-azonosító a kiértékeléshez: kategória/jelenet."""
        return f"{self.category}/{self.scene_path.stem}"


def find_root(path: str | Path) -> Path:
    """Megkeresi az adathalmaz gyökerét (ahol `actions/` és `scenes/` van).

    Elfogadja magát a gyökeret, a `handball_s` szülőjét, vagy egy Kaggle
    bemeneti mappát, ahol a kibontott zip mélyebben ül.
    """
    p = Path(path)
    if (p / "actions").is_dir() and (p / "scenes").is_dir():
        return p
    for cand in sorted(p.rglob("actions")):
        root = cand.parent
        if cand.is_dir() and (root / "scenes").is_dir():
            return root
    raise FileNotFoundError(f"Nem találom az UNIRI-HBD gyökerét (actions/ + scenes/) itt: {p}")


def _find_video(folder: Path, stem: str) -> Path | None:
    for ext in VIDEO_EXTS:
        f = folder / f"{stem}{ext}"
        if f.exists():
            return f
    return None


def index_dataset(root: str | Path, categories: tuple[str, ...] | None = None) -> list[Clip]:
    """Az összes kivágott klip listája, determinisztikus (név szerinti) sorrendben.

    A jelenet nélküli ("árva") klipeket kihagyja — ezekből nem kereshető
    vissza a végrehajtó helye.
    """
    root = find_root(root)
    cats = categories or CATEGORIES
    clips: list[Clip] = []
    for cat in cats:
        act_dir = root / "actions" / cat
        if not act_dir.is_dir():
            continue
        for act in sorted(act_dir.iterdir()):
            if act.suffix.lower() not in VIDEO_EXTS:
                continue
            scene_stem = _ACT_RE.sub("", act.stem)
            scene = _find_video(root / "scenes" / cat, scene_stem)
            if scene is None:
                continue
            det = root / "player_detections" / cat / f"{scene_stem}.csv"
            clips.append(Clip(act.stem, cat, act, scene, det if det.exists() else None))
    return clips


def read_detections(path: str | Path) -> list[list[tuple[float, float, float, float, float]]]:
    """A `player_detections` CSV beolvasása: kockánként a dobozok listája.

    Formátum: "Frame N" sor, alatta soronként "x1, y1, x2, y2, megbízhatóság".
    Követés (ki kicsoda) és a végrehajtó jelölése NINCS benne.
    """
    frames: list[list[tuple[float, float, float, float, float]]] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Frame"):
            frames.append([])
            continue
        parts = [float(v) for v in line.split(",")]
        if len(parts) == 4:
            parts.append(1.0)
        if frames and len(parts) == 5:
            frames[-1].append(tuple(parts))  # type: ignore[arg-type]
    return frames
