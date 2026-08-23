"""
[3. fázis] Figura-felismerés — visszatérő támadás-mintázatok (set play-ek).

A vízió "milyen figurákat csinálnak" része. Az ötlet:
1. A meccset szervezett TÁMADÁSOKRA bontjuk (a tactics.py fázisaiból).
2. Minden támadásból egy MOZGÁS-UJJLENYOMATOT (signature) készítünk: a támadó
   csapat játékosainak térbeli eloszlása a támadás alatt, durva rácson, normálva.
   (A normálás miatt a támadás HOSSZA nem számít, csak a mintázat alakja.)
3. A hasonló ujjlenyomatú támadásokat KLASZTEREZZÜK — minden klaszter egy
   visszatérő figura. Így megtudjuk, egy csapat milyen figurákat, milyen
   gyakorisággal játszik.

Tiszta Python (nincs ML-csomag), így videó nélkül, szintetikus pályákon tesztelhető.
A valódi figurák finomabb modellt (trajektória-szekvenciák) is kaphatnak később,
de a felismerés alap-elve és csővezetéke ez.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..models.tracking import Match, Frame, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig, classify_phase, Phase
from .primitive_cache import memoize_primitive


@dataclass
class AttackSequence:
    """Egy szervezett támadás-szakasz (a klaszterezés egysége).

    - team:     a támadó csapat.
    - start_t:  a szakasz első frame-ének ideje.
    - end_t:    az utolsó frame ideje.
    - frames:   a szakasz frame-jei.
    """
    team: Team
    start_t: int
    end_t: int
    frames: list[Frame] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.frames)


@memoize_primitive("segment_attacks")
def segment_attacks(match: Match, config: TacticsConfig | None = None,
                    min_length: int = 5) -> list[AttackSequence]:
    """A meccset szervezett támadás-szakaszokra bontja.

    Az egymást követő, AZONOS támadó-fázisú (HAZAI/VENDÉG_TÁMADÁS) frame-ek egy
    szakaszt alkotnak. A `min_length`-nél rövidebb szakaszokat eldobjuk (zaj).
    """
    config = config or TacticsConfig()
    sequences: list[AttackSequence] = []
    current: AttackSequence | None = None

    def close():
        nonlocal current
        if current is not None and current.length >= min_length:
            sequences.append(current)
        current = None

    for f in match.frames:
        ph = classify_phase(f, config)
        team = (Team.HOME if ph == Phase.HOME_ATTACK
                else Team.AWAY if ph == Phase.AWAY_ATTACK else None)
        if team is None:
            close()
            continue
        if current is None or current.team != team:
            close()
            current = AttackSequence(team=team, start_t=f.t, end_t=f.t, frames=[f])
        else:
            current.frames.append(f)
            current.end_t = f.t
    close()
    return sequences


def attack_signature(seq: AttackSequence, bins_x: int = 6, bins_y: int = 3) -> list[float]:
    """Egy támadás MOZGÁS-UJJLENYOMATA: a támadó csapat térbeli eloszlása.

    A támadó csapat játékosainak látogatottságát durva rácson (alap 6x3) gyűjtjük,
    majd a vektort 1-re NORMÁLJUK (a támadás hossza ne számítson, csak az alakja).
    Visszaad egy bins_x*bins_y hosszú vektort (sorfolytonos).
    """
    grid = [0.0] * (bins_x * bins_y)
    total = 0.0
    for f in seq.frames:
        for p in f.players:
            if p.team != seq.team:
                continue
            ix = min(bins_x - 1, max(0, int(p.x / COURT_LENGTH_M * bins_x)))
            iy = min(bins_y - 1, max(0, int(p.y / COURT_WIDTH_M * bins_y)))
            grid[iy * bins_x + ix] += 1.0
            total += 1.0
    if total > 0:
        grid = [v / total for v in grid]
    return grid


def _distance(a: list[float], b: list[float]) -> float:
    """Két ujjlenyomat euklideszi távolsága."""
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


# ---- Figura-felismerés a mentett könyvtár (playbook) ellen -------------------

def interpolate_play(attackers: list, steps: int = 20) -> list:
    """Egy mentett figura kulcs-pozícióiból folyamatos mozgáspálya.

    A figura játékosonként kulcs-pozíciók listája ([[x,y], ...]); ezeket
    szakaszonként lineárisan interpoláljuk `steps` lépésre — így ugyanolyan
    "mozgás" lesz belőle, mint egy valódi támadásból.
    """
    paths = []
    for path in attackers:
        pts = []
        if len(path) == 1:
            pts = [(float(path[0][0]), float(path[0][1]))] * steps
        else:
            for s in range(steps):
                t = s / (steps - 1)
                seg = t * (len(path) - 1)
                i = min(int(seg), len(path) - 2)
                local = seg - i
                x = path[i][0] + (path[i + 1][0] - path[i][0]) * local
                y = path[i][1] + (path[i + 1][1] - path[i][1]) * local
                pts.append((float(x), float(y)))
        paths.append(pts)
    return paths


def play_signature(attackers: list, bins_x: int = 6, bins_y: int = 3,
                   steps: int = 20, mirror_x: bool = False) -> list[float]:
    """Egy mentett figura ujjlenyomata — ÖSSZEVETHETŐ az attack_signature-rel.

    Ugyanaz a rács-hisztogram készül az interpolált mozgáspályából, mint a valódi
    támadásokból. `mirror_x`-szel a pálya hossztengelyére tükrözve — a figurát
    a tervezőben a +x kapura rajzoljuk, de az ellenfél a -x kapura is támadhat.
    """
    grid = [0.0] * (bins_x * bins_y)
    total = 0.0
    for path in interpolate_play(attackers, steps):
        for (x, y) in path:
            if mirror_x:
                x = COURT_LENGTH_M - x
            ix = min(bins_x - 1, max(0, int(x / COURT_LENGTH_M * bins_x)))
            iy = min(bins_y - 1, max(0, int(y / COURT_WIDTH_M * bins_y)))
            grid[iy * bins_x + ix] += 1.0
            total += 1.0
    if total > 0:
        grid = [v / total for v in grid]
    return grid


def match_attacks_to_playbook(match: Match, plays: list[dict],
                              config: TacticsConfig | None = None,
                              team: Team | None = None,
                              threshold: float = 0.2,
                              min_length: int = 5) -> dict:
    """A meccs támadásait a MENTETT figurákhoz (playbook) rendeli.

    `plays` elemei: {"name": ..., "attackers": [[[x,y],...], ...]}. Minden
    felismert támadás-szakaszhoz megkeressük a legközelebbi figurát (normál ÉS
    tükrözött aláírással — a támadási irány ne számítson); ha a távolság a
    küszöb alatt van, a figurához soroljuk, különben "ismeretlen".

    Visszaad: {"total_attacks", "matched": {figura-név: darab}, "unmatched"}.
    Ez a "melyik ismert figurát játsszák és hányszor" — a felderítés kiegészítése.
    """
    config = config or TacticsConfig()
    seqs = segment_attacks(match, config, min_length=min_length)
    if team is not None:
        seqs = [s for s in seqs if s.team == team]

    play_sigs = []
    for p in plays:
        attackers = p.get("attackers") or []
        if not attackers:
            continue
        play_sigs.append((str(p.get("name", "névtelen")),
                          play_signature(attackers),
                          play_signature(attackers, mirror_x=True)))

    matched: dict[str, int] = {}
    unmatched = 0
    for s in seqs:
        sig = attack_signature(s)
        best_name = None
        best_d = float("inf")
        for name, ps, psm in play_sigs:
            d = min(_distance(sig, ps), _distance(sig, psm))
            if d < best_d:
                best_d = d
                best_name = name
        if best_name is not None and best_d <= threshold:
            matched[best_name] = matched.get(best_name, 0) + 1
        else:
            unmatched += 1
    return {"total_attacks": len(seqs),
            "matched": dict(sorted(matched.items(), key=lambda kv: -kv[1])),
            "unmatched": unmatched}


def cluster_signatures(signatures: list[list[float]], threshold: float = 0.15) -> list[int]:
    """Mohó (greedy) klaszterezés: a hasonló ujjlenyomatok egy klaszterbe.

    Minden ujjlenyomatot a hozzá LEGKÖZELEBBI meglévő klaszter-középponthoz teszünk,
    ha a távolság a küszöb alatt van; különben új klasztert nyit. A középpontot
    (futó átlag) frissítjük. Visszaad egy klaszter-címkét (0,1,2,…) elemenként.

    A küszöb hangolható: kisebb = szigorúbb (több, finomabb figura), nagyobb =
    megengedőbb (kevesebb, durvább csoport).
    """
    centroids: list[list[float]] = []
    counts: list[int] = []
    labels: list[int] = []

    for sig in signatures:
        best_idx = -1
        best_dist = float("inf")
        for i, c in enumerate(centroids):
            d = _distance(sig, c)
            if d < best_dist:
                best_dist = d
                best_idx = i
        if best_idx >= 0 and best_dist <= threshold:
            # Hozzávesszük a klaszterhez, és frissítjük a középpontot (futó átlag).
            n = counts[best_idx]
            centroids[best_idx] = [(c * n + s) / (n + 1) for c, s in zip(centroids[best_idx], sig)]
            counts[best_idx] = n + 1
            labels.append(best_idx)
        else:
            centroids.append(list(sig))
            counts.append(1)
            labels.append(len(centroids) - 1)
    return labels


@dataclass
class SetPlayReport:
    """A figura-felismerés összegzése.

    - attacks:        a felismert támadás-szakaszok száma.
    - num_figures:    a megkülönböztetett visszatérő figurák (klaszterek) száma.
    - figure_sizes:   klaszterenként hány támadás tartozik bele (gyakoriság).
    - labels:         minden támadás-szakasz klaszter-címkéje (a sorrendjükben).
    """
    attacks: int
    num_figures: int
    figure_sizes: dict[int, int]
    labels: list[int]


def discover_setplays(match: Match, config: TacticsConfig | None = None,
                      threshold: float = 0.15, min_length: int = 5) -> SetPlayReport:
    """Végpontok közötti figura-felismerés: támadások → ujjlenyomat → klaszterek.

    Megmondja, hány visszatérő figurát játszott a csapat és milyen gyakorisággal.
    """
    config = config or TacticsConfig()
    sequences = segment_attacks(match, config, min_length=min_length)
    signatures = [attack_signature(s) for s in sequences]
    labels = cluster_signatures(signatures, threshold=threshold)

    sizes: dict[int, int] = {}
    for lab in labels:
        sizes[lab] = sizes.get(lab, 0) + 1
    return SetPlayReport(
        attacks=len(sequences),
        num_figures=len(sizes),
        figure_sizes=sizes,
        labels=labels,
    )


def setplay_efficiency(match: Match, config: TacticsConfig | None = None,
                       threshold: float = 0.15, min_length: int = 5,
                       min_attacks: int = 2) -> dict:
    """Melyik figura működik: klaszterenként támadás / lövés / gól.

    A figurákat csapatonként külön klaszterezzük (a két csapat mintái
    ne keveredjenek), és minden támadás-szakaszhoz hozzárendeljük a
    benne (vagy közvetlenül utána, 3 mp-en belül) esett lövéseket.
    A felderítésben ebből lesz a "melyik figurájuk veszélyes" kép.

    Visszatérés csapatonként: [{"figure", "attacks", "shots", "goals",
    "goal_pct", "starts"}] — csak a min_attacks-szor látott figurák,
    gyakoriság szerint csökkenő sorrendben; a starts a figura
    támadásainak kezdő-frame-jei (klip-exporthoz).
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(3.0 * fps)
    shots_ev = [e for e in detect_shots(match, config)
                if e.type in (EventType.SHOT, EventType.GOAL)]
    out: dict = {}
    for team in (Team.HOME, Team.AWAY):
        seqs = [s_ for s_ in segment_attacks(match, config,
                                             min_length=min_length)
                if s_.team == team]
        labels = cluster_signatures([attack_signature(s_) for s_ in seqs],
                                    threshold=threshold)
        agg: dict = {}
        for seq, lab in zip(seqs, labels):
            rec = agg.setdefault(lab, {"attacks": 0, "shots": 0,
                                       "goals": 0, "starts": []})
            rec["attacks"] += 1
            rec["starts"].append(int(seq.start_t))
            for e in shots_ev:
                if e.team == team and \
                        seq.start_t <= e.t <= seq.end_t + tail:
                    rec["shots"] += 1
                    if e.type == EventType.GOAL:
                        rec["goals"] += 1
        rows = [{"figure": int(lab), **rec,
                 "goal_pct": round(100.0 * rec["goals"] / rec["attacks"],
                                   1)}
                for lab, rec in agg.items()
                if rec["attacks"] >= min_attacks]
        rows.sort(key=lambda r: (-r["attacks"], -r["goals"]))
        out[team.value] = rows
    return out


# Figura-kopás: sávonként ennyi mért figura-támadás kell az
# ítélethez, és ekkora (százalékpontos) esés számít érdeminek.
SPD_MIN_ATTACKS = 4
SPD_GAP_PP = 15.0


def setplay_decay(match: Match, config: TacticsConfig | None = None,
                  threshold: float = 0.15, min_length: int = 5) -> dict:
    """Figura-kopás: MŰKÖDIK-E MÉG a figura a második ismétlésre.

    A figura-hatékonyság (setplay_efficiency) azt mondja meg, MELYIK
    figurájuk veszélyes — ez azt, MEDDIG: minden figura első
    előfordulását szétválasztja az ISMÉTLÉSEKTŐL, és a két sávban
    külön számol gólarányt.

    Edzőileg ez a felismerés értéke, számokban. Ha az ismétlésre
    érdemben esik a hozamuk, a fal maga megoldja a felismerést —
    elég lefuttatni velük a figurát, és a második-harmadik
    ismétlésre már készen áll a válasz. Ha az ismétlés is ugyanúgy
    gólt hoz, a baj nem a felismerés, hanem a párharc: ott
    emberfogás vagy kettőzés kell a befejezőre, nem "figyeljetek
    jobban".

    Visszatérés csapatonként: {"first_attacks", "first_goals",
    "repeat_attacks", "repeat_goals", "first_pct", "repeat_pct",
    "gap_pp", "verdict"} — a pct/gap/verdict None, ha valamelyik
    sávban kevés (SPD_MIN_ATTACKS alatti) a mért figura-támadás.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(3.0 * fps)
    shots_ev = [e for e in detect_shots(match, config)
                if e.type in (EventType.SHOT, EventType.GOAL)]

    out: dict = {}
    for team in (Team.HOME, Team.AWAY):
        seqs = [s_ for s_ in segment_attacks(match, config,
                                             min_length=min_length)
                if s_.team == team]
        labels = cluster_signatures([attack_signature(s_) for s_ in seqs],
                                    threshold=threshold)
        seen: set = set()
        rec = {"first_attacks": 0, "first_goals": 0,
               "repeat_attacks": 0, "repeat_goals": 0,
               "first_pct": None, "repeat_pct": None,
               "gap_pp": None, "verdict": None}
        for seq, lab in zip(seqs, labels):
            kulcs = "first" if lab not in seen else "repeat"
            seen.add(lab)
            rec[f"{kulcs}_attacks"] += 1
            if any(e.team == team and e.type == EventType.GOAL
                   and seq.start_t <= e.t <= seq.end_t + tail
                   for e in shots_ev):
                rec[f"{kulcs}_goals"] += 1
        if (rec["first_attacks"] >= SPD_MIN_ATTACKS
                and rec["repeat_attacks"] >= SPD_MIN_ATTACKS):
            fp = 100.0 * rec["first_goals"] / rec["first_attacks"]
            rp = 100.0 * rec["repeat_goals"] / rec["repeat_attacks"]
            rec["first_pct"] = round(fp, 1)
            rec["repeat_pct"] = round(rp, 1)
            rec["gap_pp"] = round(rp - fp, 1)
            if fp - rp >= SPD_GAP_PP:
                rec["verdict"] = (
                    f"a figuráik kopnak az ismétlésre ({fp:.0f}% → "
                    f"{rp:.0f}% gólarány) — a fal maga megoldja a "
                    "felismerést: elég lefuttatni velük a figurát, a "
                    "második ismétlésre kész a válasz")
            elif rp - fp >= SPD_GAP_PP:
                rec["verdict"] = (
                    f"az ismétlés NEKIK dolgozik ({fp:.0f}% → "
                    f"{rp:.0f}% gólarány) — a baj nem a felismerés, "
                    "hanem a párharc: a befejezőre emberfogás vagy "
                    "kettőzés kell")
        out[team.value] = rec
    return out


# Figura-befejező: egy figurához ennyi mért lövés kell az ítélethez, és
# ekkora részarány számít kiszámíthatónak. A 60% azt jelenti, hogy öt
# lövésből három ugyanarra a posztra fut ki — a falnak ennyiből már
# érdemes a figura FELISMERÉSÉRE készülnie, nem a lövés pillanatára.
SPF_MIN_SHOTS = 4
SPF_SHARE_PCT = 60.0


def setplay_finishers(match: Match, config: TacticsConfig | None = None,
                      threshold: float = 0.15, min_length: int = 5,
                      min_attacks: int = 2) -> dict:
    """Figura-befejező: MELYIK FIGURÁJUKAT KI FEJEZI BE.

    A figura-hatékonyság (`setplay_efficiency`) azt mondja meg, melyik
    figurájuk veszélyes — ez azt, hogy a veszélyes figura KIRE FUT KI.
    Minden figura-klaszterhez összegyűjtjük a benne (vagy 3 mp-en belül
    utána) esett lövéseket, és az ELENGEDŐ játékos posztjához írjuk
    őket.

    Edzőileg ez a FELISMERÉS haszna. Egy figurát a fal a második-
    harmadik ismétlésre megismer — de a felismerésből csak akkor lesz
    védés, ha tudja, mire fut ki. Ha a figura lövéseinek nagy része
    ugyanarra a posztra megy, a fal már a figura INDULÁSAKOR
    elhelyezkedhet: a befejező oldalára csúszik, és a passzsávot zárja,
    ahelyett hogy a lövés pillanatában reagálna. Ha a figura befejezése
    szórt, a felismerés önmagában keveset ér — ott a labdát kell
    üldözni, nem az embert.

    Visszatérés csapatonként: {"figures": [{"figure", "attacks",
    "shots", "roles": {poszt: lövés}, "main_role", "share_pct"}],
    "telegraphed": {"figure", "shots", "poszt", "share_pct"} | None,
    "verdict": str | None} — a main_role/share_pct None, ha a figura
    nem érte el az SPF_MIN_SHOTS lövést; a telegraphed/verdict None, ha
    egyik figura sem éri el az SPF_SHARE_PCT részarányt.
    """
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(3.0 * fps)
    shots_ev = [e for e in detect_shots(match, config)
                if e.type in (EventType.SHOT, EventType.GOAL)]
    roles = estimate_positions(match, config)

    out: dict = {}
    for team in (Team.HOME, Team.AWAY):
        seqs = [s_ for s_ in segment_attacks(match, config,
                                             min_length=min_length)
                if s_.team == team]
        labels = cluster_signatures([attack_signature(s_) for s_ in seqs],
                                    threshold=threshold)
        agg: dict = {}
        for seq, lab in zip(seqs, labels):
            rec = agg.setdefault(lab, {"attacks": 0, "shots": 0,
                                       "roles": {}})
            rec["attacks"] += 1
            for e in shots_ev:
                if e.team != team or not (seq.start_t <= e.t
                                          <= seq.end_t + tail):
                    continue
                rec["shots"] += 1
                if e.player_id is None:
                    continue
                rec_role = roles[team.value].get(e.player_id)
                if rec_role is None:
                    continue
                poszt = rec_role["poszt"]
                rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1

        rows = []
        for lab, rec in agg.items():
            if rec["attacks"] < min_attacks:
                continue
            named = sum(rec["roles"].values())
            main = share = None
            if named >= SPF_MIN_SHOTS:
                poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
                main = poszt
                share = round(100.0 * rec["roles"][poszt] / named, 1)
            rows.append({"figure": int(lab), "attacks": rec["attacks"],
                         "shots": rec["shots"],
                         "roles": dict(sorted(rec["roles"].items(),
                                              key=lambda kv: -kv[1])),
                         "main_role": main, "share_pct": share})
        rows.sort(key=lambda r: (-r["attacks"], -r["shots"]))

        telegraphed = verdict = None
        best = [r for r in rows
                if r["share_pct"] is not None
                and r["share_pct"] >= SPF_SHARE_PCT]
        if best:
            r = max(best, key=lambda r_: (r_["share_pct"], r_["shots"]))
            telegraphed = {"figure": r["figure"],
                           "shots": sum(r["roles"].values()),
                           "poszt": r["main_role"],
                           "share_pct": r["share_pct"]}
            verdict = (f"a(z) {r['figure']}. figurájuk lövéseinek "
                       f"{r['share_pct']:.0f}%-a a(z) {r['main_role']} "
                       "posztra fut ki — a figura INDULÁSAKOR arra az "
                       "oldalra kell csúszni, nem a lövésnél")
        out[team.value] = {"figures": rows, "telegraphed": telegraphed,
                           "verdict": verdict}
    return out


# Figura-indító küszöbei: ennyi poszthoz kötött INDÍTÁS kell a figura
# ítéletéhez, és ekkora részarány fölött mondjuk ki, hogy a figura
# indítása egy posztról olvasható.
SPO_MIN_STARTS = 4
SPO_SHARE_PCT = 60.0


def setplay_openers(match: Match, config: TacticsConfig | None = None,
                    threshold: float = 0.15, min_length: int = 5,
                    min_attacks: int = 2) -> dict:
    """Figura-indító: MELYIK POSZTRÓL INDUL a figurájuk.

    A figura-befejező (`setplay_finishers`) azt mondja meg, KIRE FUT KI
    a figura — ez azt, HONNAN INDUL. A kettő nem ugyanaz a védekező
    szempontjából: a befejezőt a fal a lövés előtt egy-két másodperccel
    ismeri fel, az indítót viszont AZONNAL, az első passznál.

    Minden figura-klaszter minden támadásában megnézzük, kinél volt a
    labda a szakasz ELSŐ mért pillanatában (a birtoklás-eldöntött első
    kockán), és azt a játékos posztjához írjuk.

    Edzőileg ez az ELŐJEL. Ha egy figura a támadásaik nagy részében
    ugyanarról a posztról indul, akkor abban a pillanatban, ahogy a
    labda odaér, a fal már tudja, mi jön — nem a felismerésre kell
    várni, hanem a kiinduló passzsávot lehet zárni, és a figura el sem
    indul. Saját oldalon fordítva: ha a mi figuránk mindig ugyanonnan
    indul, az ellenfél ugyanezt látja — az indítót variálni kell,
    különben a figura a harmadik ismétléstől nem ér semmit.

    Visszatérés csapatonként: {"figures": [{"figure", "attacks",
    "starts", "roles": {poszt: indítás}, "main_role", "share_pct"}],
    "telegraphed": {"figure", "starts", "poszt", "share_pct"} | None,
    "verdict": str | None} — a main_role/share_pct None, ha a figura
    nem érte el az SPO_MIN_STARTS poszthoz kötött indítást; a
    telegraphed/verdict None, ha egyik figura sem éri el az
    SPO_SHARE_PCT részarányt (sose hallgatólagos előjel).
    """
    from .decisions import ball_holder
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {}
    for team in (Team.HOME, Team.AWAY):
        seqs = [s_ for s_ in segment_attacks(match, config,
                                             min_length=min_length)
                if s_.team == team]
        labels = cluster_signatures([attack_signature(s_) for s_ in seqs],
                                    threshold=threshold)
        agg: dict = {}
        for seq, lab in zip(seqs, labels):
            rec = agg.setdefault(lab, {"attacks": 0, "starts": 0,
                                       "roles": {}})
            rec["attacks"] += 1
            # A szakasz ELSŐ kockája, ahol a labda a támadó csapat
            # egyik emberénél van — ő indítja a figurát.
            for f in seq.frames:
                holder = ball_holder(f, config)
                if holder is None or holder.team != team:
                    continue
                rec["starts"] += 1
                rec_role = roles[team.value].get(holder.track_id)
                if rec_role is not None:
                    poszt = rec_role["poszt"]
                    rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
                break

        rows = []
        for lab, rec in agg.items():
            if rec["attacks"] < min_attacks:
                continue
            named = sum(rec["roles"].values())
            main = share = None
            if named >= SPO_MIN_STARTS:
                poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
                main = poszt
                share = round(100.0 * rec["roles"][poszt] / named, 1)
            rows.append({"figure": int(lab), "attacks": rec["attacks"],
                         "starts": rec["starts"],
                         "roles": dict(sorted(rec["roles"].items(),
                                              key=lambda kv: -kv[1])),
                         "main_role": main, "share_pct": share})
        rows.sort(key=lambda r: (-r["attacks"], -r["starts"]))

        telegraphed = verdict = None
        best = [r for r in rows
                if r["share_pct"] is not None
                and r["share_pct"] >= SPO_SHARE_PCT]
        if best:
            r = max(best, key=lambda r_: (r_["share_pct"], r_["starts"]))
            telegraphed = {"figure": r["figure"],
                           "starts": sum(r["roles"].values()),
                           "poszt": r["main_role"],
                           "share_pct": r["share_pct"]}
            verdict = (f"a(z) {r['figure']}. figurájuk indításainak "
                       f"{r['share_pct']:.0f}%-a a(z) {r['main_role']} "
                       "posztról jön — amint a labda odaér, zárni kell a "
                       "kiinduló passzsávot, és a figura el sem indul")
        out[team.value] = {"figures": rows, "telegraphed": telegraphed,
                           "verdict": verdict}
    return out


# Figura-koncentráció küszöbei: ennyi mért támadás kell az ítélethez,
# ekkora részarány számít "egy figurára épülő" játéknak, ennyi
# részarány alatt viszont változatosnak, és ennyi figurát nézünk a
# lefedettségnél.
SPK_MIN_ATTACKS = 6
SPK_TOP_PCT = 40.0
SPK_VARIED_PCT = 25.0
SPK_COVER_PCT = 80.0


def setplay_concentration(match: Match,
                          config: TacticsConfig | None = None,
                          threshold: float = 0.15,
                          min_length: int = 5) -> dict:
    """Figura-koncentráció: EGY FIGURÁRA épül-e a támadójátékuk.

    A figura-hatékonyság (setplay_efficiency) azt mondja meg, MELYIK
    figurájuk veszélyes, a figura-befejező azt, KIRE fut ki — ez a
    repertoár SZÉLESSÉGÉT: a támadás-szakaszaikat csapatonként
    klaszterezi, és megnézi, mekkora hányad esik a legnagyobb
    klaszterbe, illetve hány figura fedi le a támadások
    SPK_COVER_PCT százalékát.

    Edzőileg ez a felkészülés terjedelme. Ha a támadásaik nagy része
    egyetlen mintából jön, konkrét figurára lehet készülni (videó,
    bejátszott védekezés, előre megbeszélt kettőzés) — ez a
    legolcsóbb felkészülés. Ha viszont sokfelé oszlik, figurákra
    készülni pazarlás: elvekre kell (kilépés-szabály, beálló-átadás,
    kettőzés-jel), mert a konkrét minta úgysem ismétlődik.

    Visszatérés csapatonként: {"attacks" (mért támadás), "figures"
    (klaszter), "top_pct" (a legnagyobb klaszter részaránya),
    "cover_figures" (ennyi figura fedi le a támadások
    SPK_COVER_PCT%-át), "verdict"} — az ítélet None, ha nincs meg a
    SPK_MIN_ATTACKS, vagy a kép a két küszöb közé esik.
    """
    config = config or TacticsConfig()

    out: dict = {}
    for team in (Team.HOME, Team.AWAY):
        seqs = [s_ for s_ in segment_attacks(match, config,
                                             min_length=min_length)
                if s_.team == team]
        rec = {"attacks": len(seqs), "figures": 0, "top_pct": None,
               "cover_figures": None, "verdict": None}
        if seqs:
            labels = cluster_signatures(
                [attack_signature(s_) for s_ in seqs],
                threshold=threshold)
            sizes: dict = {}
            for lab in labels:
                sizes[lab] = sizes.get(lab, 0) + 1
            counts = sorted(sizes.values(), reverse=True)
            rec["figures"] = len(counts)
            top = 100.0 * counts[0] / len(seqs)
            rec["top_pct"] = round(top, 1)
            # Hány figura kell a támadások SPK_COVER_PCT%-ához.
            acc = 0
            cover = 0
            for n in counts:
                acc += n
                cover += 1
                if 100.0 * acc / len(seqs) >= SPK_COVER_PCT:
                    break
            rec["cover_figures"] = cover
            if len(seqs) >= SPK_MIN_ATTACKS:
                if top >= SPK_TOP_PCT:
                    rec["verdict"] = (
                        f"a támadásaik {top:.0f}%-a egyetlen "
                        f"mintából jön ({len(seqs)} mért támadásból, "
                        f"{cover} figura fedi le a "
                        f"{SPK_COVER_PCT:.0f}%-ot) — konkrét figurára "
                        "lehet készülni: videó, bejátszott "
                        "védekezés, előre megbeszélt kettőzés")
                elif top <= SPK_VARIED_PCT:
                    rec["verdict"] = (
                        f"a támadásaik sokfelé oszlanak (a legnagyobb "
                        f"minta is csak {top:.0f}%, {rec['figures']} "
                        f"figura, {cover} kell a "
                        f"{SPK_COVER_PCT:.0f}%-hoz) — figurákra "
                        "készülni pazarlás: elvekre kell "
                        "(kilépés-szabály, beálló-átadás, "
                        "kettőzés-jel)")
        out[team.value] = rec
    return out
