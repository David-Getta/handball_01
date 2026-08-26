"""
[K] Videóklip-export — a felismert események jelenetei külön videófájlként.

Feladata: az eredeti meccsvideóból kivágni az események (gól/lövés/
labdaeladás) körüli jeleneteket, eseményenként egy-egy MP4 fájlba, majd az
egészet egyetlen zip-be csomagolni. Az edző így megosztható "gólvideó-
csomagot" kap a csapatnak — vágóprogram nélkül.

Idő-leképezés (lásd MatchMeta): a feldolgozás a videó minden `stride`-adik
képkockáját dolgozta fel a `start_frame`-től; a tracking `fps`-e az eredeti
videóé osztva a stride-dal. A t. tracking-frame az eredeti videóban a
`start_frame + t*stride` kép-indexnél van.
"""

from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..models.tracking import Match
from ..video_io import open_capture

# A jelenet-ablak: ennyivel a lövés/gól ELŐTT kezdjük (látszódjon a
# felépítés), és ennyivel utána zárjuk (látszódjon a befejezés).
PRE_SECONDS = 5.0
POST_SECONDS = 3.0
MAX_CLIPS = 60  # ésszerű plafon — ennél több klip zip-je már kezelhetetlen

_TYPE_HU = {"goal": "gol", "shot": "loves", "turnover": "labdaelado",
            "seven_meter": "hetmeteres", "timeout": "idokeres",
            "substitution": "csere", "note": "jegyzet",
            "missed_chance": "kihagyott-ziccer", "big_save": "nagy-vedes",
            "top_shooter": "fo-lovo", "empty_net": "het-a-hat",
            "turning_point": "fordulopont", "block": "blokk",
            "key_moment": "kulcs-pillanat", "best_figure": "figura",
            "free_shot": "szabad-lovo", "pivot_goal": "beallo-gol",
            "breakthrough": "betores", "steal": "labdaszerzes"}


@dataclass
class ClipResult:
    """Az export eredménye: a zip útja + hány klip készült.

    A skipped az azonos pillanatra eső ismétlések és a MAX_CLIPS fölé
    eső jelenetek száma — a hívó ebből tudja jelezni, hogy a csomag
    nem teljes.

    A `by_type` típusonként mondja meg, hány klip készült, az `empty`
    pedig azokat a KÉRT típusokat sorolja, amelyekhez egyetlen jelenet
    sem volt. Enélkül a néma semmi félrevezet: az edző hat csomagot
    kér, kap egy zip-et, és nem tudja, hogy kettő üresen maradt-e
    (nem volt ilyen jelenet), vagy elromlott valami.
    """
    zip_path: str
    count: int
    skipped: int = 0
    by_type: dict = field(default_factory=dict)
    empty: list = field(default_factory=list)


def _clock(seconds: float) -> str:
    m, s = int(seconds // 60), int(seconds % 60)
    return f"{m:02d}-{s:02d}"


def _fair_cap(picked: list, field) -> list:
    """A MAX_CLIPS plafon TÍPUSONKÉNT igazságosan, nem az elejéről.

    A korábbi `picked[:MAX_CLIPS]` időrendben vágott: aki tizenhárom
    csomagot kért egyszerre, a meccs ELSŐ harmadát kapta meg, a
    hajrából semmit — és a ritkább csomagok (fordulópont, 7 a 6) simán
    kimaradtak, mert a gólok elvitték a keretet. Ez néma hiba: a zip
    tele van klippel, csak épp nem arról, amit az edző keresett.

    Ezért a keretet a TÍPUSOK között osztjuk el: minden kért típus
    kap egy alap-kvótát (a plafon osztva a típusok számával), a
    maradékot pedig a bővebb típusok kapják — a típuson belül időben
    egyenletesen mintázunk, hogy a meccs egésze látsszon, ne csak az
    eleje. A visszaadott lista időrendben marad.
    """
    if len(picked) <= MAX_CLIPS:
        return picked
    szerint: dict = {}
    for e in picked:
        szerint.setdefault(str(field(e, "type")), []).append(e)
    kivalasztott: list = []
    maradek = MAX_CLIPS
    # Előbb a SZŰKÖS típusok: az ő teljes anyaguk befér, a fel nem
    # használt kvóta pedig azonnal felszabadul a bővebbeknek (a kvótát
    # ezért számoljuk újra minden lépésben).
    tipusok = sorted(szerint.items(), key=lambda kv: len(kv[1]))
    hatra = len(tipusok)
    for _typ, sor in tipusok:
        kvota = max(1, maradek // max(1, hatra))
        hanyat = min(len(sor), kvota)
        if hanyat >= len(sor):
            kivalasztott.extend(sor)
        else:
            # Egyenletes mintavétel a típus TELJES idősávjából.
            lepes = len(sor) / float(hanyat)
            kivalasztott.extend(sor[int(i * lepes)] for i in range(hanyat))
        maradek -= hanyat
        hatra -= 1
        if maradek <= 0:
            break
    kivalasztott.sort(key=lambda e: field(e, "t") or 0)
    return kivalasztott


def export_event_clips(match: Match, events: list, types: set[str],
                       out_dir: str | Path,
                       progress_cb: Optional[Callable] = None) -> ClipResult:
    """A kiválasztott típusú események jeleneteit MP4 klipekbe vágja.

    - match:   a kész Match (meta.video_path mutat az eredeti videóra).
    - events:  a felismert események ({"t", "type", "team"} szótárak vagy
               MatchEvent-ek — mindkettőt kezeljük).
    - types:   mely esemény-típusokból készüljön klip (pl. {"goal"}).
    - out_dir: ide kerülnek a klipek + a zip.
    - progress_cb(done, total, message): haladás-jelzés a hívónak.

    Kivételt dob érthető magyar üzenettel, ha az eredeti videó nem érhető el
    (pl. másik gépen dolgozták fel, vagy elmozdították a fájlt).
    """
    import cv2

    video_path = match.meta.video_path
    if not video_path or not os.path.exists(video_path):
        raise RuntimeError(
            "Az eredeti videófájl nem érhető el ezen a gépen "
            f"({video_path or 'nincs útvonal mentve'}) — a klipvágáshoz a "
            "feldolgozáskor használt videó kell.")

    cap = open_capture(video_path)
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if W <= 0 or H <= 0:
        cap.release()
        raise RuntimeError(f"A videó nem olvasható: {video_path}")

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    stride = max(1, getattr(match.meta, "stride", 1) or 1)
    start_frame = getattr(match.meta, "start_frame", 0) or 0

    # A kért típusú események, idő szerint; plafon fölött a lista eleje.
    def _field(e, name):
        v = e.get(name) if isinstance(e, dict) else getattr(e, name, None)
        return getattr(v, "value", v)  # Enum → érték

    picked = [e for e in events if _field(e, "type") in types]
    picked.sort(key=lambda e: _field(e, "t") or 0)
    n_requested = len(picked)
    # Azonos pillanatra eső ismétlések ki (több csomagban is szereplő
    # jelenet — pl. gól, ami egyben vezetés-váltás — csak egyszer kell).
    dedup = []
    last_t = None
    for e in picked:
        t_e = int(_field(e, "t") or 0)
        if last_t is not None and abs(t_e - last_t) < 2:
            continue
        dedup.append(e)
        last_t = t_e
    picked = _fair_cap(dedup, _field)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    # (fájl, típus magyar mappaneve) — a zip ebből rendez mappákba.
    made: list[tuple[Path, str]] = []

    for i, e in enumerate(picked):
        t = int(_field(e, "t") or 0)
        typ = str(_field(e, "type"))
        team = str(_field(e, "team") or "")
        team_name = (match.meta.home_team if team == "home"
                     else match.meta.away_team)
        # Az esemény helye az eredeti videóban (kép-index és másodperc).
        center_idx = start_frame + t * stride
        clip_from = max(0, center_idx - int(PRE_SECONDS * native_fps))
        clip_to = center_idx + int(POST_SECONDS * native_fps)
        if n_frames > 0:
            clip_to = min(clip_to, n_frames - 1)
        if clip_to <= clip_from:
            continue

        game_s = t / fps  # játékidő a feldolgozott szakaszon belül
        # A fájlnév vége: az esemény opcionális címkéje (pl. a jegyzet
        # szövege), különben a csapatnév.
        label = _field(e, "label") or team_name
        safe_label = re.sub(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+", "_",
                            str(label))[:32].strip("_") or "klip"
        name = (f"{i + 1:02d}_{_TYPE_HU.get(typ, typ)}_{_clock(game_s)}"
                f"_{safe_label}.mp4")
        dest = out_dir / name

        if progress_cb:
            progress_cb(i, len(picked), f"klipvágás: {name}")

        writer = cv2.VideoWriter(str(dest), fourcc, native_fps, (W, H))
        cap.set(cv2.CAP_PROP_POS_FRAMES, clip_from)
        ok_frames = 0
        for _ in range(clip_from, clip_to + 1):
            ok, img = cap.read()
            if not ok:
                break
            writer.write(img)
            ok_frames += 1
        writer.release()
        if ok_frames > 0:
            made.append((dest, _TYPE_HU.get(typ, typ)))
        else:
            dest.unlink(missing_ok=True)  # üres klip nem kell

    cap.release()

    if not made:
        raise RuntimeError("Nem készült klip — nincs a szűrőnek megfelelő "
                           "esemény, vagy a videó nem olvasható.")

    # Zip-be csomagolás (tömörítés nélkül — a videó már tömörített).
    #
    # TÖBB típusnál a klipek TÍPUS-MAPPÁKBA kerülnek: egy tizenhárom
    # csomagos dosszié hatvan fájlja egy lapos mappában kezelhetetlen,
    # az edzésen pedig témánként kell levetíteni. Egyetlen típusnál
    # marad a lapos alak (a mappa ott csak egy fölösleges kattintás).
    zip_path = out_dir / "klipek.zip"
    tobb_tipus = len({t for _f, t in made}) > 1
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for f, typ_of in made:
            arcname = f"{typ_of}/{f.name}" if tobb_tipus else f.name
            z.write(f, arcname)
    if progress_cb:
        progress_cb(len(picked), len(picked), f"kész: {len(made)} klip")
    # Típusonkénti darabszám és a NÉMÁN üres csomagok: a hívó ebből
    # tudja megmondani, mihez nem volt jelenet.
    by_type: dict = {}
    for _f, typ_hu in made:
        by_type[typ_hu] = by_type.get(typ_hu, 0) + 1
    empty = sorted(_TYPE_HU.get(t, t) for t in types
                   if _TYPE_HU.get(t, t) not in by_type)
    return ClipResult(zip_path=str(zip_path), count=len(made),
                      skipped=max(0, n_requested - len(made)),
                      by_type=by_type, empty=empty)
