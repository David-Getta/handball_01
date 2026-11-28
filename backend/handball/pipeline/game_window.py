"""Meccs-ablak: a felvétel NEM-meccs széleinek levágása.

A feltöltött felvételben gyakran benne van a bemelegítés, a meccs
előtti ceremónia és a lefújás utáni rész is. Ezek NEM a meccs részei:
a bemelegítő kapura lövések gólnak/lövésnek látszanának, az üres vagy
álldogálós percek pedig felhígítanák az idő-alapú mutatókat. Ez a
modul a felvételt aktivitás-ablakokra bontja, és megkeresi a
TÉNYLEGES játék első és utolsó jelét.

JÁTÉK-jel egy ablak, ha:
- elég mért játékos van a pályán (üres pálya / szállingózás kizárva),
- a két csapat súlypontja KÖZEL van egymáshoz — játékban a védelem és
  a támadás ugyanazon kapu körül áll; bemelegítésnél ki-ki a SAJÁT
  kapujánál gyakorol, a két súlypont a két térfélen van,
- a játékosok ténylegesen mozognak — a sorfal/ceremónia álldogálás.

A meccs-ablak az első és az utolsó elég hosszú játék-futam közti
tartomány, kis ráhagyással; az ezen kívüli éleket a `trim_to_game`
levágja. A félidei szünet az ablakon BELÜL marad (a félidő-felismerés
és a térfélcsere-normalizálás épít rá) — a szünet-sávba eső kapura
lövéseket az eseménydetektor szűri (`event_detection.detect_shots`).
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.tracking import Frame, Match, PositionSource, Team

# Játék-jel küszöbei:
GW_WINDOW_S = 10.0        # ekkora ablakokban mérjük az aktivitást
GW_MIN_PLAYERS = 6.0      # ablak-átlagban ennyi mért játékos kell a játékhoz
GW_MAX_SPLIT_M = 12.0     # csapat-súlypontok x-távolsága E FELETT = bemelegítés
GW_MIN_SPEED_MS = 0.3     # ez alatti átlagmozgás = ceremónia / álldogálás
GW_MIN_TEAM_SAMPLES = 10  # ennyi mért pozíció kell csapatonként az ablakban
# Vágás:
GW_MIN_RUN_S = 60.0       # ennyi FOLYAMATOS játék-jel kell a horgonyhoz
GW_PAD_S = 15.0           # biztonsági ráhagyás a vágás előtt/után
GW_MIN_TRIM_S = 45.0      # ennél rövidebb élt nem vágunk (nem éri meg)


def _is_game_window(frames: list[Frame], fps: float) -> bool:
    """Igaz, ha az ablak TÉNYLEGES játéknak látszik (lásd a modul-fejlécet)."""
    measured = 0
    hx: list[float] = []
    ax: list[float] = []
    speeds: list[float] = []
    prev: dict[int, tuple[float, float]] = {}
    for f in frames:
        cur: dict[int, tuple[float, float]] = {}
        for p in f.players:
            if p.source != PositionSource.MEASURED:
                continue
            measured += 1
            if p.team == Team.HOME:
                hx.append(p.x)
            elif p.team == Team.AWAY:
                ax.append(p.x)
            cur[p.track_id] = (p.x, p.y)
            q = prev.get(p.track_id)
            if q is not None:
                speeds.append(math.hypot(p.x - q[0], p.y - q[1]) * fps)
        prev = cur
    if measured / max(1, len(frames)) < GW_MIN_PLAYERS:
        return False
    if len(hx) < GW_MIN_TEAM_SAMPLES or len(ax) < GW_MIN_TEAM_SAMPLES:
        return False
    if abs(sum(hx) / len(hx) - sum(ax) / len(ax)) > GW_MAX_SPLIT_M:
        return False
    if not speeds or sum(speeds) / len(speeds) < GW_MIN_SPEED_MS:
        return False
    return True


def detect_game_window(match: Match) -> Optional[dict]:
    """A tényleges játék tartománya a felvételen (frame-INDEXEK).

    Visszatérés: {"start_idx", "end_idx", "head_s", "tail_s"} — az első
    és az utolsó, legalább GW_MIN_RUN_S hosszú játék-futam által
    kijelölt tartomány, GW_PAD_S ráhagyással; head_s/tail_s az ezen
    kívül eső él hossza másodpercben. None, ha nincs elég hosszú
    játék-futam (a felvétel nem ítélhető meg).
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total = len(match.frames)
    if total < 2:
        return None
    win = max(1, round(GW_WINDOW_S * fps))
    min_run = max(1, math.ceil(GW_MIN_RUN_S / GW_WINDOW_S))

    flags: list[bool] = []
    starts: list[int] = []
    for w0 in range(0, total, win):
        flags.append(_is_game_window(match.frames[w0:w0 + win], fps))
        starts.append(w0)

    # Legalább min_run hosszú összefüggő játék-futamok.
    runs: list[tuple[int, int]] = []  # (első ablak, utolsó ablak)
    run_start = None
    for i in range(len(flags) + 1):
        game = flags[i] if i < len(flags) else False
        if game and run_start is None:
            run_start = i
        elif not game and run_start is not None:
            if i - run_start >= min_run:
                runs.append((run_start, i - 1))
            run_start = None
    if not runs:
        return None

    pad = round(GW_PAD_S * fps)
    start_idx = max(0, starts[runs[0][0]] - pad)
    end_idx = min(total - 1, starts[runs[-1][1]] + win - 1 + pad)
    return {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "head_s": round(start_idx / fps, 1),
        "tail_s": round((total - 1 - end_idx) / fps, 1),
    }


def suggest_game_window(match: Match) -> Optional[dict]:
    """Javasolt vágás-ablak a TÁROLT meccsre, játékidő-másodpercben.

    A detect_game_window frame-INDEXEKKEL dolgozik; a kézi vágás
    (trim_to_window) viszont a kockák `t` címkéi szerint vág — egy
    korábban már vágott vagy hézagos meccsen a kettő nem ugyanaz. Ez a
    függvény a felismerés eredményét a kocka `t`-jére fordítja, hogy a
    kliens vágás-párbeszéde elő tudja tölteni ("Javasolt kezdés:
    9:09"). Régi motorral feldolgozott meccsen is működik — a
    felismerés a tárolt követésen fut, nem a videón.

    Visszatérés: {"start_s", "end_s", "head_s", "tail_s"} — start_s és
    end_s a trim_to_window-nak közvetlenül átadható játékidő; head_s
    és tail_s az ablakon kívüli él hossza. None, ha nincs elég hosszú
    játék-futam (a felvétel nem ítélhető meg).
    """
    gw = detect_game_window(match)
    if gw is None:
        return None
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    return {
        "start_s": round(match.frames[gw["start_idx"]].t / fps, 1),
        "end_s": round(match.frames[gw["end_idx"]].t / fps, 1),
        "head_s": gw["head_s"],
        "tail_s": gw["tail_s"],
    }


def trim_to_game(match: Match, tail: bool = True,
                 window_out: Optional[dict] = None) -> Optional[dict]:
    """A nem-meccs élek levágása HELYBEN (a frame-lista szűkítése).

    A kockák `t` idejét NEM írja át — a videó-időzítés (jelenet-lejátszás,
    klipek) változatlanul helyes marad. Csak GW_MIN_TRIM_S-nél hosszabb
    élt vág; `tail=False`-szal a vége érintetlen (részleges, folytatható
    feldolgozásnál a folytatás a végéhez fűzne vissza). Visszatérés:
    {"head_cut_s", "tail_cut_s", "kept_frames"}, vagy None, ha nem
    vágott semmit.

    A `window_out` dict (ha meg van adva) a FELISMERÉS eredményét kapja
    meg — akkor is, ha nem vágtunk: {"found": bool, "head_s", "tail_s"}.
    Erre azért van szükség, mert a None visszatérés KÉT, gyökeresen
    eltérő esetet takar: (1) a felismerés nem talált összefüggő játékot
    (ilyenkor a bemelegítés bennmaradhatott, és ezt a felhasználónak
    tudnia kell), (2) talált, de nem volt mit vágni (a felvétel eleve
    csak a meccs). A hívó e nélkül a kettőt nem tudná megkülönböztetni.
    """
    gw = detect_game_window(match)
    if window_out is not None:
        window_out["found"] = gw is not None
        if gw is not None:
            window_out["head_s"] = gw["head_s"]
            window_out["tail_s"] = gw["tail_s"]
    if gw is None:
        return None
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total = len(match.frames)
    start_idx = gw["start_idx"] if gw["head_s"] >= GW_MIN_TRIM_S else 0
    end_idx = (gw["end_idx"] if tail and gw["tail_s"] >= GW_MIN_TRIM_S
               else total - 1)
    if start_idx == 0 and end_idx == total - 1:
        return None
    match.frames[:] = match.frames[start_idx:end_idx + 1]
    info = {
        "head_cut_s": round(start_idx / fps, 1),
        "tail_cut_s": round((total - 1 - end_idx) / fps, 1),
        "kept_frames": len(match.frames),
    }
    if window_out is not None:
        window_out["head_cut_s"] = info["head_cut_s"]
        window_out["tail_cut_s"] = info["tail_cut_s"]
    return info


def trim_to_window(match: Match, from_s: float,
                   to_s: Optional[float] = None) -> dict:
    """KÉZI vágás: a megadott játékidő-ablakon kívüli kockák eldobása.

    Az automatikus felismerés (trim_to_game) nem mindig találja meg a
    meccs kezdetét — a felhasználó viszont pontosan TUDJA ("az 549.
    másodpercben kezdődött"), és eddig csak újrafeldolgozással tudta
    érvényesíteni. Ez a függvény utólag vágja le a bemutatást /
    bemelegítést az elemzésből.

    A kockák `t` idejét NEM írjuk át (a trim_to_game mintája): a
    videó-időzítés (jelenet-lejátszás, klipvágás), a jegyzetek, a
    kiállítások és az esemény-javítások idő-hivatkozásai változatlanul
    helyesek maradnak — a kidobott időkhöz egyszerűen nem tartozik
    többé kocka, tehát esemény sem.

    Részleges (folytatható) meccsen nem vágunk: a folytatás a levágott
    végéhez fűzne vissza, és némán hézag keletkezne.
    Visszatérés: {"head_cut_s", "tail_cut_s", "kept_frames"}.
    """
    if getattr(match.meta, "partial", False):
        raise ValueError("részleges feldolgozás nem vágható — előbb "
                         "fejezd be (Folytatás), vagy dolgozd fel újra")
    if not match.frames:
        raise ValueError("nincs mit vágni: a meccsnek nincs kockája")
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if from_s < 0 or (to_s is not None and to_s <= from_s):
        raise ValueError("az ablak eleje 0-nál, a vége az elejénél "
                         "nagyobb kell legyen")
    t0 = int(round(from_s * fps))
    t1 = None if to_s is None else int(round(to_s * fps))
    total = len(match.frames)
    keep = [f for f in match.frames
            if f.t >= t0 and (t1 is None or f.t <= t1)]
    if not keep:
        raise ValueError("a megadott ablakban nincs egyetlen kocka sem "
                         "— nézd meg a másodperceket")
    eldobott_elol = sum(1 for f in match.frames if f.t < t0)
    match.frames[:] = keep
    return {
        "head_cut_s": round(eldobott_elol / fps, 1),
        "tail_cut_s": round((total - eldobott_elol - len(keep)) / fps, 1),
        "kept_frames": len(keep),
    }
