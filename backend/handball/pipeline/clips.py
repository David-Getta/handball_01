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
    # Mely mezszámokra szűkítettünk (üres lista = az egész csapatra).
    jerseys: list = field(default_factory=list)


def _clock(seconds: float) -> str:
    m, s = int(seconds // 60), int(seconds % 60)
    return f"{m:02d}-{s:02d}"


def _source_segments(match: Match) -> list:
    """A meccs forrás-szakaszai egységes alakban.

    Egyetlen videóból feldolgozott meccsnél EGY elem (a teljes
    játékidő); összefűzött meccsnél annyi, ahány részből összeraktuk
    (`meta.source_segments`). A hívó így nem ágazik el: ugyanaz a kód
    vágja a klipet mindkét esetben.

    Elemenként: {"t_from", "t_to" (kizárólagos, None = a végéig),
    "video_path", "start_frame", "stride"}.
    """
    nyers = getattr(match.meta, "source_segments", None) or []
    ki = []
    for sz in nyers:
        if not isinstance(sz, dict) or not sz.get("video_path"):
            continue
        try:
            ki.append({
                "t_from": int(sz.get("t_from") or 0),
                "t_to": (int(sz["t_to"]) if sz.get("t_to") is not None
                         else None),
                "video_path": str(sz["video_path"]),
                "start_frame": int(sz.get("start_frame") or 0),
                "stride": max(1, int(sz.get("stride") or 1)),
            })
        except (TypeError, ValueError):
            continue  # rossz alakú bejegyzés: kihagyjuk, nem hiba
    if ki:
        ki.sort(key=lambda z: z["t_from"])
        return ki
    # Nincs térkép: a klasszikus, EGY videós eset.
    if match.meta.video_path:
        return [{"t_from": 0, "t_to": None,
                 "video_path": match.meta.video_path,
                 "start_frame": getattr(match.meta, "start_frame", 0) or 0,
                 "stride": max(1, getattr(match.meta, "stride", 1) or 1)}]
    return []


def _segment_of(szakaszok: list, t: int) -> Optional[dict]:
    """Melyik forrás-szakaszba esik a t. játékidő-kocka."""
    for sz in szakaszok:
        if t >= sz["t_from"] and (sz["t_to"] is None or t < sz["t_to"]):
            return sz
    return None


def _jersey_of_track(match: Match) -> dict:
    """track_id → mezszám (trackenként az ELSŐ ismert érték).

    Ugyanaz a szabály, mint az edzői összefoglalóban: a mezszám a
    felismerés során ingadozhat, de egy trackhez egy embert rendelünk,
    tehát az első biztos leolvasás dönt.
    """
    out: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None and p.track_id not in out:
                out[p.track_id] = p.jersey_number
    return out


def _fair_cap(picked: list, field, csoport=None) -> list:
    """A MAX_CLIPS plafon CSOPORTONKÉNT igazságosan, nem az elejéről.

    A korábbi `picked[:MAX_CLIPS]` időrendben vágott: aki tizenhárom
    csomagot kért egyszerre, a meccs ELSŐ harmadát kapta meg, a
    hajrából semmit — és a ritkább csomagok (fordulópont, 7 a 6) simán
    kimaradtak, mert a gólok elvitték a keretet. Ez néma hiba: a zip
    tele van klippel, csak épp nem arról, amit az edző keresett.

    Ezért a keretet a CSOPORTOK között osztjuk el: minden csoport kap
    egy alap-kvótát (a plafon osztva a csoportok számával), a maradékot
    pedig a bővebb csoportok kapják — a csoporton belül időben
    egyenletesen mintázunk, hogy a meccs egésze látsszon, ne csak az
    eleje. A visszaadott lista időrendben marad.

    A csoport alapban a TÍPUS. Több kijelölt JÁTÉKOSNÁL viszont a
    (mezszám, típus) páros a csoport: különben ugyanez a néma
    igazságtalanság térne vissza egy szinttel feljebb — a sokat
    szereplő ember elvinné a keretet, és a másik két játékos mappája
    két klippel maradna.
    """
    if len(picked) <= MAX_CLIPS:
        return picked
    if csoport is None:
        def csoport(e):
            return str(field(e, "type"))
    szerint: dict = {}
    for e in picked:
        szerint.setdefault(csoport(e), []).append(e)
    kivalasztott: list = []
    maradek = MAX_CLIPS
    # Előbb a SZŰKÖS típusok: az ő teljes anyaguk befér, a fel nem
    # használt kvóta pedig azonnal felszabadul a bővebbeknek (a kvótát
    # ezért számoljuk újra minden lépésben).
    tipusok = sorted(szerint.items(), key=lambda kv: (len(kv[1]), str(kv[0])))
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
                       progress_cb: Optional[Callable] = None,
                       jerseys: Optional[set] = None,
                       extra_files: Optional[dict] = None) -> ClipResult:
    """A kiválasztott típusú események jeleneteit MP4 klipekbe vágja.

    - match:   a kész Match (meta.video_path mutat az eredeti videóra).
    - events:  a felismert események ({"t", "type", "team"} szótárak vagy
               MatchEvent-ek — mindkettőt kezeljük).
    - types:   mely esemény-típusokból készüljön klip (pl. {"goal"}).
    - out_dir: ide kerülnek a klipek + a zip.
    - progress_cb(done, total, message): haladás-jelzés a hívónak.
    - jerseys: ha meg van adva, CSAK az ezekhez a mezszámokhoz kötött
      események kerülnek klipre (a játékos saját válogatása). Üres vagy
      None esetén az egész csapat jelenetei jönnek.
    - extra_files: {útvonal a zipben: szöveg} — a klipek MELLÉ tett
      lapok (pl. a játékos meccs-lapja a saját mappájába). A hívó
      dönti el, mit tesz be: a klip-motor nem ismeri a jelentéseket.
      A hiányzó vagy hibás bejegyzés csendben kimarad — egy lap
      hiánya nem viheti el a videót.

    Kivételt dob érthető magyar üzenettel, ha az eredeti videó nem érhető el
    (pl. másik gépen dolgozták fel, vagy elmozdították a fájlt).
    """
    import cv2

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    # A FORRÁS-SZAKASZOK: egyetlen videónál egy elem, összefűzött
    # meccsnél annyi, ahány klipből összeraktuk. Így a kettő ugyanazon
    # az úton megy — egy külön "összefűzött" ág idővel szétcsúszna a
    # normálistól, és a hiba pont a ritkább eseten jönne elő.
    szakaszok = _source_segments(match)
    hianyzo = [sz["video_path"] for sz in szakaszok
               if not sz["video_path"] or not os.path.exists(sz["video_path"])]
    if not szakaszok:
        raise RuntimeError(
            "Az eredeti videófájl nem érhető el ezen a gépen (nincs "
            "útvonal mentve) — a klipvágáshoz a feldolgozáskor használt "
            "videó kell.")
    if hianyzo:
        # ÖSSZEFŰZÖTT meccsnél megnevezzük, MELYIK szakasz hiányzik: a
        # "a videó nem érhető el" itt félrevezető lenne, mert a többi
        # fájl megvan.
        ha_tobb = len(szakaszok) > 1
        nevek = ", ".join(os.path.basename(h) or "nincs útvonal"
                          for h in hianyzo)
        raise RuntimeError(
            (f"Az összefűzött meccs {len(hianyzo)}/{len(szakaszok)} "
             f"forrás-videója nem érhető el ezen a gépen ({nevek}) — a "
             "klipvágáshoz a feldolgozáskor használt fájlok kellenek."
             ) if ha_tobb else
            (f"Az eredeti videófájl nem érhető el ezen a gépen "
             f"({nevek}) — a klipvágáshoz a feldolgozáskor használt "
             "videó kell."))

    # A kért típusú események, idő szerint; plafon fölött a lista eleje.
    def _field(e, name):
        v = e.get(name) if isinstance(e, dict) else getattr(e, name, None)
        return getattr(v, "value", v)  # Enum → érték

    picked = [e for e in events if _field(e, "type") in types]
    # MEZSZÁM-szűrés: az események a track_id-t őrzik (player_id), az
    # edző és a játékos viszont mezszámban gondolkodik — a leképezést
    # itt csináljuk meg, hogy a hívónak ne kelljen track_id-t ismernie.
    kert_mezek = {int(j) for j in (jerseys or []) if j is not None}
    # A leképezés a MAPPÁZÁSHOZ is kell, nem csak a szűréshez: több
    # kijelölt játékosnál mindenki külön mappát kap.
    mez_of_ev = _jersey_of_track(match) if kert_mezek else {}
    if kert_mezek:
        picked = [e for e in picked
                  if mez_of_ev.get(_field(e, "player_id")) in kert_mezek]
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
    # Több kijelölt játékosnál a keret JÁTÉKOSONKÉNT ÉS típusonként
    # oszlik, hogy senki mappája ne maradjon két klippel.
    if len(kert_mezek) > 1:
        picked = _fair_cap(
            dedup, _field,
            csoport=lambda e: (mez_of_ev.get(_field(e, "player_id")),
                               str(_field(e, "type"))))
    else:
        picked = _fair_cap(dedup, _field)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    # (fájl, típus magyar mappaneve, mezszám vagy None) — a zip ebből
    # rendez mappákba.
    made: list[tuple[Path, str, Optional[int]]] = []

    # A megnyitott videók gyorsítótára: egy összefűzött meccsnél az
    # események oda-vissza ugrálhatnak a szakaszok közt, és minden
    # eseménynél újranyitni a fájlt lassú lenne.
    nyitott: dict = {}

    def _cap_of(sz):
        """(capture, natív fps, W, H, kockaszám) a szakasz videójához."""
        ut = sz["video_path"]
        if ut not in nyitott:
            c = open_capture(ut)
            w = int(c.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w <= 0 or h <= 0:
                c.release()
                raise RuntimeError(f"A videó nem olvasható: {ut}")
            nyitott[ut] = (c, c.get(cv2.CAP_PROP_FPS) or 25.0, w, h,
                           int(c.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
        return nyitott[ut]

    for i, e in enumerate(picked):
        t = int(_field(e, "t") or 0)
        typ = str(_field(e, "type"))
        team = str(_field(e, "team") or "")
        team_name = (match.meta.home_team if team == "home"
                     else match.meta.away_team)
        # MELYIK forrás-videóban van ez a pillanat. Összefűzött meccsnél
        # ez szakaszonként más fájl; egyetlen videónál mindig ugyanaz.
        sz = _segment_of(szakaszok, t)
        if sz is None:
            continue  # a térképen kívüli esemény: nincs mit vágni
        cap, native_fps, W, H, n_frames = _cap_of(sz)
        # Az esemény helye a SZAKASZ videójában (kép-index): a
        # játékidőből előbb a szakaszon belüli t-t kell képezni.
        center_idx = (sz["start_frame"]
                      + (t - sz["t_from"]) * sz["stride"])
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
            made.append((dest, _TYPE_HU.get(typ, typ),
                         mez_of_ev.get(_field(e, "player_id"))))
        else:
            dest.unlink(missing_ok=True)  # üres klip nem kell

    for c, *_ in nyitott.values():
        c.release()

    if not made:
        # A mezszám-szűrés a leggyakoribb ok: a #7-es kér magának
        # gólvideót, de a felismerés egyetlen gólt sem kötött hozzá.
        # A néma "nincs klip" itt hibának látszana, pedig nem az.
        if kert_mezek:
            mezek = ", ".join(f"#{j}" for j in sorted(kert_mezek))
            raise RuntimeError(
                f"Nem készült klip: a(z) {mezek} mezszámhoz egyetlen "
                "kért jelenet sem tartozik ezen a meccsen. Vagy nincs "
                "ilyen eseménye, vagy a mezszám nincs kiosztva — ez "
                "utóbbi a meccs-elemzőben pótolható.")
        raise RuntimeError("Nem készült klip — nincs a szűrőnek megfelelő "
                           "esemény, vagy a videó nem olvasható.")

    # Zip-be csomagolás (tömörítés nélkül — a videó már tömörített).
    #
    # TÖBB típusnál a klipek TÍPUS-MAPPÁKBA kerülnek: egy tizenhárom
    # csomagos dosszié hatvan fájlja egy lapos mappában kezelhetetlen,
    # az edzésen pedig témánként kell levetíteni. Egyetlen típusnál
    # marad a lapos alak (a mappa ott csak egy fölösleges kattintás).
    #
    # TÖBB KIJELÖLT JÁTÉKOSNÁL mindenki a SAJÁT mappáját kapja: az edző
    # három emberrel külön-külön ül le, és egy összekevert zip-ből
    # minden beszélgetés előtt újra kellene válogatnia. Egy játékosnál
    # nincs mappa (ott csak fölösleges kattintás lenne).
    zip_path = out_dir / "klipek.zip"
    tobb_tipus = len({t for _f, t, _j in made}) > 1
    tobb_jatekos = len(kert_mezek) > 1
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for f, typ_of, mez in made:
            arcname = f"{typ_of}/{f.name}" if tobb_tipus else f.name
            if tobb_jatekos:
                arcname = f"#{mez}/{arcname}" if mez is not None else arcname
            z.write(f, arcname)
        # A klipek MELLÉ tett lapok (pl. a játékos meccs-lapja): az
        # edző így EGY fájlt visz a beszélgetésre, nem kettőt.
        for utvonal, tartalom in (extra_files or {}).items():
            try:
                z.writestr(str(utvonal), tartalom)
            except Exception:
                continue
    if progress_cb:
        progress_cb(len(picked), len(picked), f"kész: {len(made)} klip")
    # Típusonkénti darabszám és a NÉMÁN üres csomagok: a hívó ebből
    # tudja megmondani, mihez nem volt jelenet.
    by_type: dict = {}
    for _f, typ_hu, _mez in made:
        by_type[typ_hu] = by_type.get(typ_hu, 0) + 1
    empty = sorted(_TYPE_HU.get(t, t) for t in types
                   if _TYPE_HU.get(t, t) not in by_type)
    return ClipResult(zip_path=str(zip_path), count=len(made),
                      skipped=max(0, n_requested - len(made)),
                      by_type=by_type, empty=empty,
                      jerseys=sorted(kert_mezek))
