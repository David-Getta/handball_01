"""Helyzetminőség (xG) — mennyit "ér" egy lövéshelyzet.

Két lövés nem egyforma: a hatosról, szemből leadott lövés sokkal nagyobb
eséllyel gól, mint a szélső szögből vagy kilencméterről lőtt. Minden
felismert lövéshez (detect_shots) kiszámolunk egy 0..1 közti értéket a
helyzet minőségére, KIZÁRÓLAG a lövés helyéből:

- távolság a kapu közepétől: közelebbről könnyebb;
- a kapu látott szöge: szemből a teljes 3 m-es kapu "látszik", éles
  szélső szögből csak egy szelete.

Szándékosan átlátható heurisztika (nem betanított modell): minden szám
mögött geometria áll, így az érték magyarázható az edzőnek — valódi
adathalmazon később kalibrálható. A csapat-összeg a "várható gól":
a tényleges gólszámmal összevetve látszik, melyik csapat fejezte be
hatékonyan a helyzeteit, és melyik puskázta el őket.
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.tracking import Match, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig

# A kapu a pálya rövid oldalának közepén, 3 m széles (y: 8,5..11,5).
_GOAL_HALF_W = 1.5
_GOAL_CY = COURT_WIDTH_M / 2.0

# Távolság-görbe: 6 m-ről ~0,60, 9 m-ről ~0,37, 12 m-ről ~0,15 az alap.
_DIST_BASE = 1.05
_DIST_SLOPE = 0.075
# A látott kapuszög normálása: ~0,9 rad a közeli-középső helyzet szöge.
_ANGLE_FULL_RAD = 0.9
# Az xG végső korlátai (0 és 1 helyett óvatos sáv — heurisztika vagyunk).
_XG_MIN, _XG_MAX = 0.05, 0.90


def xg_of_position(x: float, y: float, goal_x: float) -> float:
    """Egy lövéshelyzet értéke (0..1) a helyből: távolság + látott kapuszög."""
    dx = max(0.5, abs(x - goal_x))  # a kapu síkján állva se osszunk nullával
    dist = math.hypot(x - goal_x, y - _GOAL_CY)
    # A két kapufa iránya közti szög — szemből nagy, éles szögből kicsi.
    a1 = math.atan2(y - (_GOAL_CY - _GOAL_HALF_W), dx)
    a2 = math.atan2(y - (_GOAL_CY + _GOAL_HALF_W), dx)
    angle = abs(a1 - a2)
    p_dist = min(max(_DIST_BASE - _DIST_SLOPE * dist, 0.08), 0.85)
    ang_norm = min(max(angle / _ANGLE_FULL_RAD, 0.0), 1.0)
    xg = p_dist * (0.55 + 0.45 * ang_norm)
    return round(min(max(xg, _XG_MIN), _XG_MAX), 3)


def match_xg(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """A meccs minden lövésének helyzetminősége + csapat-összegzés.

    A lövés helye: a lövő pozíciója az esemény képkockáján; ha a lövő nem
    azonosítható, a labda helye. Visszatérés:
    {"shots": [{"t", "team", "player_id", "x", "y", "xg", "outcome"}],
     "teams": {"home"/"away": {"xg", "goals", "shots", "diff"}},
     "shooters": [{"player_id", "team", "shots", "goals", "xg", "diff"}]}
    — diff = gól − várható gól (pozitív: a helyzetei FELETT teljesít,
    negatív: kihagyott nagy helyzetek). A shooters xG szerint csökkenő."""
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    shots: list[dict] = []
    teams = {"home": {"xg": 0.0, "goals": 0, "shots": 0},
             "away": {"xg": 0.0, "goals": 0, "shots": 0}}

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        f = by_t.get(e.t)
        if f is None:
            continue
        x = y = None
        if e.player_id is not None:
            for p in f.players:
                if p.track_id == e.player_id:
                    x, y = p.x, p.y
                    break
        if x is None and f.ball is not None:
            x, y = f.ball.x, f.ball.y
        if x is None:
            continue
        goal_x = config.attacks_toward_x(e.team)
        xg = xg_of_position(x, y, goal_x)
        outcome = (e.detail or {}).get("outcome") or \
            ("goal" if e.type == EventType.GOAL else "miss")
        side = e.team.value
        shots.append({"t": e.t, "team": side, "player_id": e.player_id,
                      "x": round(x, 2), "y": round(y, 2),
                      "xg": xg, "outcome": outcome})
        teams[side]["xg"] += xg
        teams[side]["shots"] += 1
        if e.type == EventType.GOAL:
            teams[side]["goals"] += 1

    for side in ("home", "away"):
        # A lövés-választás minősége: átlagos xG lövésenként (magas = jó
        # helyzetek, alacsony = sok kis esélyű lövés).
        n_sh = teams[side]["shots"]
        teams[side]["avg_xg_per_shot"] = (round(teams[side]["xg"] / n_sh, 3)
                                          if n_sh else 0.0)
        teams[side]["xg"] = round(teams[side]["xg"], 2)
        teams[side]["diff"] = round(teams[side]["goals"] - teams[side]["xg"], 2)

    # Lövőnkénti bontás: ki teljesít a helyzetei felett/alatt. (A lövő
    # nélküli — azonosíthatatlan — lövések csak a csapat-összegben vannak.)
    by_shooter: dict[int, dict] = {}
    for sh in shots:
        pid = sh["player_id"]
        if pid is None:
            continue
        rec = by_shooter.setdefault(pid, {"player_id": pid, "team": sh["team"],
                                          "shots": 0, "goals": 0, "xg": 0.0})
        rec["shots"] += 1
        rec["xg"] += sh["xg"]
        if sh["outcome"] == "goal":
            rec["goals"] += 1
    shooters = []
    for rec in by_shooter.values():
        rec["xg"] = round(rec["xg"], 2)
        rec["diff"] = round(rec["goals"] - rec["xg"], 2)
        shooters.append(rec)
    shooters.sort(key=lambda r: -r["xg"])
    return {"shots": shots, "teams": teams, "shooters": shooters}


# Kihagyott ziccer: legalább ekkora helyzet-érték, gól nélkül.
BIG_CHANCE_XG = 0.5


def missed_big_chances(match: Match,
                       config: Optional[TacticsConfig] = None) -> list[dict]:
    """A kihagyott nagy helyzetek: xG >= BIG_CHANCE_XG, de nem gól.

    A leginkább visszanézendő jelenetek — a klip-export "kihagyott
    ziccer" típusa erre épül. Visszatérés: [{"t","team","player_id",
    "xg"}], idő szerint."""
    out = []
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("xg", 0.0) >= BIG_CHANCE_XG and sh.get("outcome") != "goal":
            out.append({"t": sh["t"], "team": sh["team"],
                        "player_id": sh.get("player_id"), "xg": sh["xg"]})
    out.sort(key=lambda r: r["t"])
    return out


# Kihagyott ziccer ára: az ennyi másodpercen belül kapott gól számít a
# kihagyás azonnali büntetésének; és ennyi kihagyástól ítélünk arányt.
MISS_PUNISH_QUICK_S = 40.0
MISS_PUNISH_MIN = 3


def miss_punishment(match: Match,
                    config: Optional[TacticsConfig] = None,
                    quick_s: float = MISS_PUNISH_QUICK_S) -> dict:
    """Kihagyott ziccer ára: a kihagyott nagy helyzet utáni gyors kapott gól.

    A klasszikus: "a kihagyott helyzet a túloldalon gól". Minden
    kihagyott ziccer (missed_big_chances) után megnézzük, kapott-e a
    csapat `quick_s` másodpercen belül gólt. A magas arány a kihagyás
    utáni fejlógatás jele — kihagyott helyzet után a visszarendeződésre
    külön figyelni kell; az ellenfél olvasata: az ő kihagyásuk után
    azonnal indítani kell.

    Visszatérés csapatonként: {"misses", "punished", "rate_pct"} —
    rate_pct None, ha kevés (MISS_PUNISH_MIN alatti) a kihagyás.
    """
    from .event_detection import EventType, detect_shots

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(quick_s * fps)
    goals = sorted((e.t, e.team.value) for e in
                   detect_shots(match, config or TacticsConfig())
                   if e.type == EventType.GOAL)

    out = {}
    counts = {"home": {"misses": 0, "punished": 0},
              "away": {"misses": 0, "punished": 0}}
    for miss in missed_big_chances(match, config):
        side = miss["team"]
        other = "away" if side == "home" else "home"
        counts[side]["misses"] += 1
        if any(gs == other and 0 <= gt - miss["t"] <= win
               for (gt, gs) in goals):
            counts[side]["punished"] += 1
    for side in ("home", "away"):
        rec = counts[side]
        out[side] = {
            "misses": rec["misses"],
            "punished": rec["punished"],
            "rate_pct": (round(100.0 * rec["punished"] / rec["misses"], 1)
                         if rec["misses"] >= MISS_PUNISH_MIN else None),
        }
    return out


# Célzás-pontosság: ennyi lövés-kísérlettől ítélünk arányt; ez alatt
# gyenge, e felett kiemelkedő a kapura tartó arány.
ACCURACY_MIN_SHOTS = 8
ACCURACY_LOW_PCT = 55.0
ACCURACY_HIGH_PCT = 80.0


def shot_accuracy(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Célzás-pontosság: a lövés-kísérletekből mennyi tart kapura.

    A mellé lőtt labda a legolcsóbb támadás-halál: nincs lepattanó,
    nincs szöglet — kapus-kidobás van, azonnali ellen-indítással. Aki
    sokat lő mellé, annak a lövése fele ajándék: a mellé lövés utáni
    kidobás a védekező csapat indítás-jele. Aki szinte mindent kapura
    tesz, az ellen a blokk-munka kötelező — ott a kapus egyedül nem
    marad meg.

    Visszatérés csapatonként: {"attempts", "on_target", "pct"} — pct
    None, ha kevés (ACCURACY_MIN_SHOTS alatti) a kísérlet.
    """
    from .event_detection import EventType, detect_shots

    counts = {"home": {"attempts": 0, "on_target": 0},
              "away": {"attempts": 0, "on_target": 0}}
    for e in detect_shots(match, config or TacticsConfig()):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        rec = counts[e.team.value]
        rec["attempts"] += 1
        if e.type == EventType.GOAL \
                or (e.detail or {}).get("outcome") == "save":
            rec["on_target"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        out[side] = {
            "attempts": rec["attempts"],
            "on_target": rec["on_target"],
            "pct": (round(100.0 * rec["on_target"] / rec["attempts"], 1)
                    if rec["attempts"] >= ACCURACY_MIN_SHOTS else None),
        }
    return out


# Lövő-koncentráció: ennyi azonosított lövőjű lövéstől ítélünk, és e
# részarány felett számít egy emberre épülőnek a lövés-terhelés.
CONC_MIN_SHOTS = 12
CONC_TOP_SHARE = 0.35


# Befejező-váltás: egymást követő befejezések ugyanattól az embertől.
# Viszonyítás: hat mezőnyjátékosnál a véletlen ismétlődés ~17%, ezért
# a 35% már tudatos (kiszámítható) minta, a 10% alatti jó rotáció.
FRT_MIN_SHOTS = 8
FRT_HIGH_PCT = 35.0
FRT_LOW_PCT = 10.0


def finisher_rotation(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Befejező-váltás: UGYANAZ fejez-e be a következő támadásban is.

    A forró kéz (hot_hands) a GÓLOKAT nézi sorozatban, a
    lövő-koncentráció (shot_concentration) a teljes meccs eloszlását
    — ez a BEFEJEZÉS-SORRENDET: a csapat lövéseit időrendben
    végigolvasva megszámoljuk, hányszor lő ugyanaz az ember kétszer
    egymás után (a kimenetel mindegy: a védekezés a lövő SZEMÉLYÉRE
    áll rá, nem az eredményre).

    Hat mezőnyjátékosnál a véletlen ismétlődés ~17% — a fölötti érték
    tudatos vagy megszokásból jövő minta: a védekezés a második
    támadásban már rákészülhet, és a lövő rossz szögből is elereszti.

    Edzőileg: a sorozat-befejezős csapat ellen a lövőjükre a KÖVETKEZŐ
    támadásban is számítani kell (korai kilépés, kettőzés); a saját
    oldalon a befejezés-rotáció (a figura a második támadásban másra
    fusson ki) az edzés-téma.

    Visszatérés csapatonként: {"shots", "repeats", "repeat_pct",
    "top", "verdict"} — repeat_pct/verdict None FRT_MIN_SHOTS alatt;
    a verdict "ugyanaz fejez be sorozatban" / "jól rotálják a
    befejezést" / None; a top a legtöbb ismétlést hozó lövő.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    seqs: dict = {"home": [], "away": []}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL) \
                or e.player_id is None:
            continue
        seqs[getattr(e.team, "value", e.team)].append(e.player_id)

    out = {}
    for side, seq in seqs.items():
        repeats = 0
        by_player: dict = {}
        for a, b in zip(seq, seq[1:]):
            if a == b:
                repeats += 1
                by_player[a] = by_player.get(a, 0) + 1
        rec = {"shots": len(seq), "repeats": repeats,
               "repeat_pct": None, "top": None, "verdict": None}
        if by_player:
            rec["top"] = max(by_player.items(), key=lambda kv: kv[1])[0]
        if len(seq) >= FRT_MIN_SHOTS:
            pct = 100.0 * repeats / (len(seq) - 1)
            rec["repeat_pct"] = round(pct, 1)
            if pct >= FRT_HIGH_PCT:
                rec["verdict"] = "ugyanaz fejez be sorozatban"
            elif pct <= FRT_LOW_PCT:
                rec["verdict"] = "jól rotálják a befejezést"
        out[side] = rec
    return out


# Gól-minta: az ismétlődő gól-ujjlenyomat (sáv x táv) küszöbei.
GPT_MIN_GOALS = 3     # ennyi azonos mintájú gól kell
GPT_SHARE_PCT = 40.0  # ...és ekkora részarány az azonosított gólokból
GPT_FAR_M = 9.0       # e fölött "távoli", alatta "közeli" a lövéshely


def goal_patterns(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Gól-minta: UGYANAZT a gólt lövik-e újra és újra.

    A lövő-koncentráció a SZEMÉLYT nézi, a gól-koncentráció a
    befejezőt — ez a HELYET: minden azonosított lövőjű gólnál a lövő
    helyéből képzett ujjlenyomatot (oldal-sáv x lövéstáv, pl.
    "bal-távoli") számoljuk. Ha a gólok nagy része ugyanabból a
    mintából jön, a támadásuk kiszámítható: egyetlen fal-igazítás
    (kilépő védő abba a sávba, blokk arra a kézre) a gólforrásuk
    nagyját elzárja.

    Edzőileg: a minta ellen nem általában kell jobban védekezni,
    hanem AZT az egy képet kell megfogni — és mérni, hogy a meccs
    közben áttérnek-e másikra; a saját oldalon a befejezés-szórás
    (több sáv, több táv) az edzés-téma.

    Visszatérés csapatonként: {"goals", "patterns": {minta: darab},
    "top", "verdict"} — a verdict "a góljaik mintázata: X (N/M)"
    (GPT_MIN_GOALS darabtól és GPT_SHARE_PCT részaránytól), különben
    None.
    """
    from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    out = {side: {"goals": 0, "patterns": {}, "top": None,
                  "verdict": None} for side in ("home", "away")}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        f = by_t.get(e.t)
        if f is None:
            continue
        shooter = next((p for p in f.players
                        if p.track_id == e.player_id), None)
        if shooter is None:
            continue
        side = getattr(e.team, "value", e.team)
        goal_x = config.attacks_toward_x(e.team)
        third = (0 if shooter.y < COURT_WIDTH_M / 3 else
                 1 if shooter.y < 2 * COURT_WIDTH_M / 3 else 2)
        if goal_x <= COURT_LENGTH_M / 2:
            third = 2 - third
        lane = ("bal", "közép", "jobb")[third]
        band = ("távoli" if abs(shooter.x - goal_x) >= GPT_FAR_M
                else "közeli")
        label = f"{lane}-{band}"
        rec = out[side]
        rec["goals"] += 1
        rec["patterns"][label] = rec["patterns"].get(label, 0) + 1
    for rec in out.values():
        if not rec["patterns"]:
            continue
        top, n = max(rec["patterns"].items(), key=lambda kv: kv[1])
        rec["top"] = top
        if n >= GPT_MIN_GOALS \
                and 100.0 * n / rec["goals"] >= GPT_SHARE_PCT:
            rec["verdict"] = (f"a góljaik mintázata: {top} "
                              f"({n}/{rec['goals']})")
    return out


def shot_concentration(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Lövő-koncentráció: mennyire egy emberre épül a lövés-terhelés.

    A kiszámíthatóság személyi olvasata: ha a csapat lövéseinek nagy
    hányadát ugyanaz a játékos adja le, a védekezés személyre szabható
    — emberfogás vagy korai kettőzés a fő lövőn, és onnantól olyanoknak
    kell befejezniük, akik ezt nem szokták. Elosztott terhelés ellen
    ilyen rövidítés nincs: ott sáv- és fal-munka kell, nem személy.

    Visszatérés csapatonként: {"shots", "top_shots", "top_player_id",
    "share", "concentrated"} — share/concentrated None, ha kevés
    (CONC_MIN_SHOTS alatti) az azonosított lövőjű lövés.
    """
    from .event_detection import EventType, detect_shots

    counts = {"home": {}, "away": {}}
    for e in detect_shots(match, config or TacticsConfig()):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
            continue
        by = counts[e.team.value]
        by[e.player_id] = by.get(e.player_id, 0) + 1
    out = {}
    for side in ("home", "away"):
        by = counts[side]
        total = sum(by.values())
        top_pid = max(by, key=lambda p: by[p]) if by else None
        top = by[top_pid] if top_pid is not None else 0
        rec = {"shots": total, "top_shots": top,
               "top_player_id": top_pid, "share": None,
               "concentrated": None}
        if total >= CONC_MIN_SHOTS:
            rec["share"] = round(top / total, 2)
            rec["concentrated"] = rec["share"] >= CONC_TOP_SHARE
        out[side] = rec
    return out


# Befejezés-esés: félidőnként ennyi lövés-kísérlet kell az ítélethez,
# és ekkora gólarány-esés (százalékpont) számít érdeminek.
FINISH_FADE_MIN_SHOTS = 6
FINISH_FADE_DROP_PP = 15.0


def finish_fade(match: Match,
                config: Optional[TacticsConfig] = None) -> dict:
    """Befejezés-esés: a gólra váltás az 1. vs 2. félidőben.

    A fáradás-kép befejezés-tagja: a kapus-forma (gk_save_fade)
    támadó-oldali párja, de az ÖSSZES lövés-kísérletből (a mellé menőt
    is beleértve) számolt gólarányon. Akinek a 2. félidőre érdemben
    esik a gólra váltása, annál fáradtan már nem ül a befejezés — a
    hajrában a kidolgozott ziccerig kell játszania; akinek nő, az a
    meccs végére lő formába.

    Visszatérés csapatonként: {"fh_shots", "fh_goals", "sh_shots",
    "sh_goals", "drop_pp"} — drop_pp a gólarány esése százalékpontban
    (pozitív = romlik), None, ha nincs félidő-jel vagy kevés
    (félidőnként FINISH_FADE_MIN_SHOTS alatti) a kísérlet.
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime

    empty = {"fh_shots": 0, "fh_goals": 0, "sh_shots": 0, "sh_goals": 0,
             "drop_pp": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    evs = [e for e in detect_shots(match, config or TacticsConfig())
           if e.type in (EventType.SHOT, EventType.GOAL)]
    for side in ("home", "away"):
        rec = out[side]
        own = [e for e in evs if e.team.value == side]
        rec["fh_shots"] = sum(1 for e in own if e.t <= ht)
        rec["sh_shots"] = len(own) - rec["fh_shots"]
        rec["fh_goals"] = sum(1 for e in own
                              if e.t <= ht and e.type == EventType.GOAL)
        rec["sh_goals"] = sum(1 for e in own
                              if e.t > ht and e.type == EventType.GOAL)
        if rec["fh_shots"] >= FINISH_FADE_MIN_SHOTS \
                and rec["sh_shots"] >= FINISH_FADE_MIN_SHOTS:
            fh_pct = 100.0 * rec["fh_goals"] / rec["fh_shots"]
            sh_pct = 100.0 * rec["sh_goals"] / rec["sh_shots"]
            rec["drop_pp"] = round(fh_pct - sh_pct, 1)
    return out


# Bravúr utáni lendület: az ennyi másodpercen belül szerzett gól számít
# a nagy védés azonnali kamatoztatásának; és ennyi bravúrtól ítélünk.
BIG_SAVE_SPARK_S = 40.0
BIG_SAVE_SPARK_MIN = 3


def big_save_momentum(match: Match,
                      config: Optional[TacticsConfig] = None,
                      quick_s: float = BIG_SAVE_SPARK_S) -> dict:
    """Bravúr utáni lendület: a nagy védés után jön-e gyors gól elöl.

    A kihagyott ziccer ára (miss_punishment) védés-oldali tükre: minden
    bravúr-védés (big_saves) után megnézzük, szerzett-e a VÉDŐ csapat
    `quick_s` másodpercen belül gólt. A magas arány azt jelenti, hogy a
    kapus náluk indítás: a rossz lövés ellenük kontra — a lövést meg
    kell válogatni, bravúr után azonnali visszarendeződés kell. Az
    alacsony arány: a bravúr náluk elhal — a kapus megfog, de nem
    büntet, a merész lövésnek nincs kontra-ára.

    Visszatérés csapatonként (a VÉDÉST jegyző oldalon): {"saves",
    "sparked", "rate_pct"} — rate_pct None, ha kevés
    (BIG_SAVE_SPARK_MIN alatti) a bravúr.
    """
    from .event_detection import EventType, detect_shots

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(quick_s * fps)
    goals = sorted((e.t, e.team.value) for e in
                   detect_shots(match, config or TacticsConfig())
                   if e.type == EventType.GOAL)

    counts = {"home": {"saves": 0, "sparked": 0},
              "away": {"saves": 0, "sparked": 0}}
    for sv in big_saves(match, config):
        saver = "away" if sv["team"] == "home" else "home"
        counts[saver]["saves"] += 1
        if any(gs == saver and 0 <= gt - sv["t"] <= win
               for (gt, gs) in goals):
            counts[saver]["sparked"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        out[side] = {
            "saves": rec["saves"],
            "sparked": rec["sparked"],
            "rate_pct": (round(100.0 * rec["sparked"] / rec["saves"], 1)
                         if rec["saves"] >= BIG_SAVE_SPARK_MIN else None),
        }
    return out


def big_saves(match: Match,
              config: Optional[TacticsConfig] = None) -> list[dict]:
    """Bravúr-védések: nagy értékű (xG >= BIG_CHANCE_XG) helyzet, amit a
    kapus fogott. A kihagyott ziccer tükörképe — a kapus-kiemelések és a
    "nagy védés" klipek alapja. Visszatérés: [{"t","team","player_id",
    "xg"}] — a team a LÖVŐ csapata (a védő kapus az ellenfélé)."""
    out = []
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("xg", 0.0) >= BIG_CHANCE_XG and sh.get("outcome") == "save":
            out.append({"t": sh["t"], "team": sh["team"],
                        "player_id": sh.get("player_id"), "xg": sh["xg"]})
    out.sort(key=lambda r: r["t"])
    return out


def xg_saved(match: Match, config: Optional[XGConfig] = None) -> dict:
    """Hárított xG: a fogott lövések helyzet-értékének összege a VÉDŐ
    csapat oldalán. A sima védés% minden védést egyformán számol — ez a
    mutató a NEHÉZ védéseket díjazza: a 0,6 xG-s ziccer megfogása többet
    ér, mint egy 0,05-ös távoli pötty.

    Visszatérés: {"home": xg, "away": xg} — a védést jegyző oldal.
    """
    out = {"home": 0.0, "away": 0.0}
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("outcome") == "save":
            out["away" if sh["team"] == "home" else "home"] += sh["xg"]
    return {k: round(v, 2) for k, v in out.items()}


def xg_prevented(match: Match, config: Optional[XGConfig] = None) -> dict:
    """Megmentett gólok (GSAx): a kapura tartó lövések összesített
    helyzet-értéke MÍNUSZ a ténylegesen kapott gólok, a védő oldalon.

    Pozitív: a kapus a helyzetekhez képest kevesebbet kapott (jó forma);
    negatív: többet kapott a vártnál. A mellé menő lövés nem számít —
    az nem a kapus érdeme.

    Visszatérés: {"home"/"away": {"faced_xg", "conceded", "prevented"}}.
    """
    out = {side: {"faced_xg": 0.0, "conceded": 0, "prevented": 0.0}
           for side in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("outcome") not in ("save", "goal"):
            continue
        rec = out["away" if sh["team"] == "home" else "home"]
        rec["faced_xg"] += sh["xg"]
        rec["conceded"] += int(sh["outcome"] == "goal")
    for rec in out.values():
        rec["faced_xg"] = round(rec["faced_xg"], 2)
        rec["prevented"] = round(rec["faced_xg"] - rec["conceded"], 2)
    return out


# Elsütés-idő: a labda ekkora sugáron belül számít a lövőnél lévőnek;
# ennyi másodpercen belüli elsütés "kapásból" lövés; ennyi lövéstől
# ítélünk, és e részarányok döntik el a csapat-címkét.
RELEASE_HOLD_R_M = 2.0
RELEASE_QUICK_S = 0.6
RELEASE_LOOKBACK_S = 4.0
RELEASE_MIN_SHOTS = 8
RELEASE_QUICK_SHARE = 60.0
RELEASE_SLOW_SHARE = 25.0


def shot_release(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Elsütés-idő: kapásból lőnek, vagy sokáig fogják a labdát.

    Lövésenként visszafelé lépkedve megmérjük, mennyi ideig volt a
    labda folyamatosan a lövőnél az elengedés előtt. A kapásból lövő
    csapat ellen a blokk és a kapus időzítése borul: a kapus a
    PASSZRA mozduljon, ne a lövésre, a sáncnak kész kéztartás kell.
    A labdafogó lövő (kevés gyors elsütés) viszont időt ad: a kilépés
    és a blokk ellene szinte ingyen van — és a saját edzésnek is
    témája, mert a sokat fogott labda a védelemnek is idő.

    Visszatérés csapatonként: {"shots", "quick", "avg_hold_s",
    "quick_pct", "style"} — quick_pct/style None, ha kevés
    (RELEASE_MIN_SHOTS alatti) a mérhető lövés; a style "kapásból" /
    "labdafogó" / None (vegyes).
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    lookback = round(RELEASE_LOOKBACK_S * fps)
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    def _hold_s(t_shot: int, pid: int) -> Optional[float]:
        i0 = idx_of.get(t_shot)
        if i0 is None:
            return None
        # Először a repülés-kockákat lépjük át (a labda már elhagyta a
        # kezet), majd a folyamatos birtoklás hosszát számoljuk.
        i = i0
        held = 0
        seen_hold = False
        while i >= 0 and i0 - i <= lookback:
            f = match.frames[i]
            p = next((p for p in f.players if p.track_id == pid), None)
            near = (p is not None and f.ball is not None
                    and math.hypot(p.x - f.ball.x, p.y - f.ball.y)
                    <= RELEASE_HOLD_R_M)
            if near:
                seen_hold = True
                held += 1
            elif seen_hold:
                break
            i -= 1
        return held / fps if seen_hold else None

    counts = {"home": {"shots": 0, "quick": 0, "sum_s": 0.0},
              "away": {"shots": 0, "quick": 0, "sum_s": 0.0}}
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("player_id") is None:
            continue
        hold = _hold_s(sh["t"], sh["player_id"])
        if hold is None:
            continue
        rec = counts[sh["team"]]
        rec["shots"] += 1
        rec["sum_s"] += hold
        if hold <= RELEASE_QUICK_S:
            rec["quick"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {"shots": rec["shots"], "quick": rec["quick"],
             "avg_hold_s": (round(rec["sum_s"] / rec["shots"], 2)
                            if rec["shots"] else None),
             "quick_pct": None, "style": None}
        if rec["shots"] >= RELEASE_MIN_SHOTS:
            pct = 100.0 * rec["quick"] / rec["shots"]
            r["quick_pct"] = round(pct, 1)
            if pct >= RELEASE_QUICK_SHARE:
                r["style"] = "kapásból"
            elif pct <= RELEASE_SLOW_SHARE:
                r["style"] = "labdafogó"
        out[side] = r
    return out


# Pontatlan lövők: ennyi mért lövéstől ítélünk emberenként, és e
# feletti mellé-arány jelenti, hogy rá lehet engedni a lövést.
WASTEFUL_MIN_SHOTS = 5
WASTEFUL_MISS_PCT = 40.0


def wasteful_shooters(match: Match,
                      config: Optional[XGConfig] = None) -> dict:
    """Pontatlan lövők: KINEK a lövései mennek mellé.

    A célzás-pontosság (shot_accuracy) csapat-szinten mondja meg, a
    lövéseikből mennyi tart kapura — ez játékosonként bontja: lövőnként
    számoljuk a kísérleteket és a kaput elkerülő (mellé/blokk)
    lövéseket.

    Edzőileg: akinek a lövései rendre elkerülik a kaput, arra rá lehet
    engedni a lövést — nála a kilépés fölösleges kockázat, és a mellé
    lövés utáni kidobás azonnali indítás nektek.

    Visszatérés csapatonként: {"players": [{"player_id", "jersey",
    "shots", "off_target"}], "top"} — a lista mellé-lövés szerint
    csökkenő; a "top" az a játékos, akinek legalább
    WASTEFUL_MIN_SHOTS lövése van, és a mellé-aránya eléri a
    WASTEFUL_MISS_PCT-t.
    """
    jersey: dict = {}
    for fr in match.frames:
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for sh in match_xg(match, config).get("shots", []):
        pid = sh.get("player_id")
        if pid is None:
            continue
        rec = tally[sh["team"]].setdefault(pid, {"shots": 0,
                                                 "off_target": 0})
        rec["shots"] += 1
        if sh["outcome"] not in ("goal", "save"):
            rec["off_target"] += 1  # mellé vagy blokkolt: nem kapura

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "shots": r["shots"], "off_target": r["off_target"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["off_target"])]
        top = None
        for row in rows:
            if row["shots"] >= WASTEFUL_MIN_SHOTS and (
                    100.0 * row["off_target"] / row["shots"]
                    >= WASTEFUL_MISS_PCT):
                top = row
                break
        out[side] = {"players": rows, "top": top}
    return out


# Kapott helyzetek minősége: ennyi kapott lövés kell az ítélethez, és e
# feletti / alatti átlagos helyzet-érték a nagy, illetve a nehéz
# helyzeteket engedő fal jele.
CCQ_MIN_SHOTS = 8
CCQ_BIG_XG = 0.35
CCQ_TIGHT_XG = 0.22


def conceded_chance_quality(match: Match,
                            config: Optional[TacticsConfig] = None) -> dict:
    """Kapott helyzetek minősége: MILYEN LÖVÉSEKET ENGED a fal.

    A saját lövés-választást a match_xg avg_xg_per_shot mutatja — ez a
    másik oldal: a csapat ELLEN leadott lövések átlagos
    helyzet-értéke. Nem azt méri, mennyit kapnak (xGA-összeg), hanem
    hogy egy-egy lövés mennyire volt ziccer: a fal beengedi-e az
    ellenfelet, vagy kifelé szorítja.

    Edzőileg: aki nagy helyzeteket enged, annál befelé kell játszani —
    beállós, áttörés, elzárás után kapott labda; aki csak nehéz
    helyzeteket enged, annál a 9 méteres lövés ajándék nekik: ott
    keresztmozgással, elzárással kell embert kihúzni, és a kapus mögé
    kerülni.

    Visszatérés csapatonként (a VÉDEKEZŐ oldalé): {"shots",
    "avg_xga", "verdict"} — az avg_xga/verdict None CCQ_MIN_SHOTS
    alatt; a verdict "nagy helyzeteket engednek" / "csak nehéz
    helyzeteket engednek" / None.
    """
    xg = match_xg(match, config)
    acc = {"home": [0, 0.0], "away": [0, 0.0]}
    for sh in xg["shots"]:
        # A lövést a MÁSIK csapat védekezése engedte.
        deff = "away" if sh["team"] == "home" else "home"
        acc[deff][0] += 1
        acc[deff][1] += sh["xg"]

    out: dict = {}
    for side in ("home", "away"):
        n, total = acc[side]
        rec = {"shots": n, "avg_xga": None, "verdict": None}
        if n >= CCQ_MIN_SHOTS:
            avg = total / n
            rec["avg_xga"] = round(avg, 3)
            if avg >= CCQ_BIG_XG:
                rec["verdict"] = "nagy helyzeteket engednek"
            elif avg <= CCQ_TIGHT_XG:
                rec["verdict"] = "csak nehéz helyzeteket engednek"
        out[side] = rec
    return out


# Fal-fáradás: félidőnként ennyi kapott lövés kell az ítélethez, és
# ekkora átlagos helyzetérték-emelkedés jelenti a kinyíló (vagy
# csökkenés az összeálló) falat.
WF_MIN_SHOTS = 5
WF_RISE_XG = 0.08


def wall_fade(match: Match,
              config: Optional[TacticsConfig] = None) -> dict:
    """Fal-fáradás: MELYIK FÉLIDŐBEN nyílik ki a fal.

    A kapott helyzetek minősége (conceded_chance_quality) a teljes
    meccset nézi — ez félidőnként: a csapat ELLEN leadott lövések
    átlagos helyzet-értékét külön mérjük a két félidőben. Ha a második
    félidőben nő meg, a fal fáradással nyílik ki; ha csökken, a
    védekezés a szünet után áll össze.

    Edzőileg: a második félidőre kinyíló fal ellen a belső játékot
    (beállós, betörés) a második félidőre kell tartogatni — az elején
    kintről is jó a lövés, a végén már befelé kell menni; az összeálló
    fal ellen fordítva: az első félidőben kell megszerezni a
    gól-előnyt, mert a szünet után bezár a bolt.

    Visszatérés csapatonként (a VÉDEKEZŐ oldalé): {"fh_shots",
    "fh_avg_xga", "sh_shots", "sh_avg_xga", "verdict"} — az átlagok
    None a félidőnkénti WF_MIN_SHOTS alatt (vagy ha nincs felismert
    szünet); a verdict "a második félidőre kinyílik a faluk" / "a
    második félidőre áll össze a faluk" / None.
    """
    from .halftime import detect_halftime

    empty = {"fh_shots": 0, "fh_avg_xga": None,
             "sh_shots": 0, "sh_avg_xga": None, "verdict": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out

    acc = {side: {"fh": [0, 0.0], "sh": [0, 0.0]}
           for side in ("home", "away")}
    for sh in match_xg(match, config)["shots"]:
        deff = "away" if sh["team"] == "home" else "home"
        half = "fh" if sh["t"] <= ht else "sh"
        acc[deff][half][0] += 1
        acc[deff][half][1] += sh["xg"]

    for side in ("home", "away"):
        rec = out[side]
        fh_n, fh_sum = acc[side]["fh"]
        sh_n, sh_sum = acc[side]["sh"]
        rec["fh_shots"], rec["sh_shots"] = fh_n, sh_n
        if fh_n >= WF_MIN_SHOTS and sh_n >= WF_MIN_SHOTS:
            fh_avg, sh_avg = fh_sum / fh_n, sh_sum / sh_n
            rec["fh_avg_xga"] = round(fh_avg, 3)
            rec["sh_avg_xga"] = round(sh_avg, 3)
            if sh_avg - fh_avg >= WF_RISE_XG:
                rec["verdict"] = "a második félidőre kinyílik a faluk"
            elif fh_avg - sh_avg >= WF_RISE_XG:
                rec["verdict"] = "a második félidőre áll össze a faluk"
    return out


# Lövés-választás állás szerint: állapotonként ennyi lövés kell az
# ítélethez, és ekkora átlagos helyzetérték-esés (vagy -többlet) a
# kapkodó, illetve a türelmes hátrány-játék jele.
SQS_MIN_SHOTS = 5
SQS_GAP_XG = 0.08


def shot_quality_by_score(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Lövés-választás állás szerint: HÁTRÁNYBAN ELKAPKODJÁK-E.

    Az előny-kezelés (pace_by_score) a támadás-hosszot méri állás
    szerint — ez a lövés-minőséget: a leadott lövések átlagos
    helyzet-értékét (xG) külön számoljuk, amikor a csapat hátrányban
    van, és amikor nem. A hátrány stressz-teszt: van, aki ilyenkor
    rossz, kis esélyű lövésekbe menekül, és van, aki a nyomás alatt
    is végigjátssza a támadást.

    Edzőileg: a hátrányban kapkodó csapat ellen a vezetés önmagát
    védi — nyugodt fal, semmi kockázat, a rossz lövéseik nektek
    dolgoznak; a hátrányban is türelmes csapat ellen a vezetés sosem
    biztonságos, a hajrában is teljes fegyelem kell.

    Visszatérés csapatonként: {"trail_shots", "trail_avg_xg",
    "other_shots", "other_avg_xg", "verdict"} — az átlagok None
    SQS_MIN_SHOTS alatt; a verdict "hátrányban elkapkodják a
    lövéseket" / "hátrányban is türelmesek" / None.
    """
    xg = match_xg(match, config)
    goals = sorted((sh["t"], sh["team"]) for sh in xg["shots"]
                   if sh["outcome"] == "goal")

    acc = {side: {"trail": [0, 0.0], "other": [0, 0.0]}
           for side in ("home", "away")}
    for sh in xg["shots"]:
        side = sh["team"]
        other = "away" if side == "home" else "home"
        sc = {"home": 0, "away": 0}
        for (gt, tm) in goals:
            if gt < sh["t"]:
                sc[tm] += 1
        bucket = "trail" if sc[side] < sc[other] else "other"
        acc[side][bucket][0] += 1
        acc[side][bucket][1] += sh["xg"]

    out: dict = {}
    for side in ("home", "away"):
        t_n, t_sum = acc[side]["trail"]
        o_n, o_sum = acc[side]["other"]
        rec = {"trail_shots": t_n, "trail_avg_xg": None,
               "other_shots": o_n, "other_avg_xg": None,
               "verdict": None}
        if t_n >= SQS_MIN_SHOTS and o_n >= SQS_MIN_SHOTS:
            t_avg, o_avg = t_sum / t_n, o_sum / o_n
            rec["trail_avg_xg"] = round(t_avg, 3)
            rec["other_avg_xg"] = round(o_avg, 3)
            if o_avg - t_avg >= SQS_GAP_XG:
                rec["verdict"] = "hátrányban elkapkodják a lövéseket"
            elif t_avg - o_avg >= SQS_GAP_XG:
                rec["verdict"] = "hátrányban is türelmesek"
        out[side] = rec
    return out


# Ziccer-befejezők: ennyi nagy helyzet kell egy játékoshoz, és e
# feletti / alatti értékesítés a biztos, illetve a bizonytalan
# befejező jele.
BCF_MIN_CHANCES = 3
BCF_SAFE_PCT = 80.0
BCF_SHAKY_PCT = 40.0


def big_chance_finishers(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Ziccer-befejezők: KI ÉRTÉKESÍTI a nagy helyzeteket.

    A pazarló lövők (wasteful_shooters) minden lövést néznek — ez
    csak a ziccereket: játékosonként számoljuk a BIG_CHANCE_XG
    feletti helyzet-értékű lövéseket és a belőlük szerzett gólokat.

    Edzőileg: a ziccer-biztos befejező ellen a helyzetet már a
    kialakulása ELŐTT kell megelőzni — korábbi besegítés, mert amit ő
    megkap a hatoson, az gól; a ziccer-bizonytalan lövőnél viszont a
    fal vállalhatja, hogy inkább őt engedi helyzetbe a veszélyesebb
    társak helyett.

    Visszatérés csapatonként: {"players": [{"player_id", "chances",
    "goals"}], "safe", "shaky"} — a safe/shaky a legalább
    BCF_MIN_CHANCES ziccerrel rendelkező, BCF_SAFE_PCT feletti,
    illetve BCF_SHAKY_PCT alatti értékesítésű játékos (vagy None).
    """
    xg = match_xg(match, config)
    tally: dict = {"home": {}, "away": {}}
    for sh in xg["shots"]:
        pid = sh.get("player_id")
        if pid is None or sh["xg"] < BIG_CHANCE_XG:
            continue
        rec = tally[sh["team"]].setdefault(
            pid, {"player_id": pid, "chances": 0, "goals": 0})
        rec["chances"] += 1
        if sh["outcome"] == "goal":
            rec["goals"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = sorted(tally[side].values(),
                      key=lambda r: -r["chances"])
        safe = None
        shaky = None
        for r in rows:
            if r["chances"] < BCF_MIN_CHANCES:
                continue
            pct = 100.0 * r["goals"] / r["chances"]
            if pct >= BCF_SAFE_PCT and safe is None:
                safe = r
            elif pct <= BCF_SHAKY_PCT and shaky is None:
                shaky = r
        out[side] = {"players": rows, "safe": safe, "shaky": shaky}
    return out


# Előny-védekezés: állás-vödrönként legalább ennyi kapott lövés kell,
# és ekkora kapott átlag-xG többlet a leülés, ekkora hiány a feszesen
# maradó fal jele vezetés közben.
DBS_MIN_SHOTS = 5
DBS_SOFT_XG = 0.05
DBS_TIGHT_XG = -0.02


def defense_by_score(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Előny-védekezés: LEÜL-E A FALUK, amikor vezetnek.

    A kapott helyzetek minősége (conceded_chance_quality) a teljes
    meccset nézi — ez állás szerint bontja: a csapat ellen leadott
    lövések átlagos helyzet-értékét (xG) akkor, amikor VEZETNEK,
    szemben az összes többi állapottal. Aki vezetve nagyobb
    helyzeteket enged, annak a fala előnyben elkényelmesedik.

    Edzőileg: az előnyben leülő csapat ellen hátrányban sincs ok
    pánikra — a vezetésük puhább falat hoz, türelmes, bevitt
    támadásokkal visszajön a meccs; az előnyben is feszes fal ellen
    a korai hátrány valódi baj — az elejét kell megnyerni.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"leading":
    {"shots", "xg_sum", "avg_xg"}, "rest": {"shots", "xg_sum",
    "avg_xg"}, "verdict"} — az avg_xg None DBS_MIN_SHOTS alatt; a
    verdict "előnyben leül a faluk" / "előnyben is feszes a faluk" /
    None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out: dict = {side: {"leading": {"shots": 0, "xg_sum": 0.0,
                                    "avg_xg": None},
                        "rest": {"shots": 0, "xg_sum": 0.0,
                                 "avg_xg": None},
                        "verdict": None}
                 for side in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        deff = "away" if sh["team"] == "home" else "home"
        own = sum(1 for (t, tm) in goals
                  if t < sh["t"] and tm == deff)
        opp = sum(1 for (t, tm) in goals
                  if t < sh["t"] and tm != deff)
        rec = out[deff]["leading" if own > opp else "rest"]
        rec["shots"] += 1
        rec["xg_sum"] += float(sh.get("xg", 0.0))

    for side in ("home", "away"):
        buckets = out[side]
        for rec in (buckets["leading"], buckets["rest"]):
            rec["xg_sum"] = round(rec["xg_sum"], 2)
            if rec["shots"] >= DBS_MIN_SHOTS:
                rec["avg_xg"] = round(rec["xg_sum"] / rec["shots"], 3)
        lead, rest = buckets["leading"], buckets["rest"]
        if lead["avg_xg"] is not None and rest["avg_xg"] is not None:
            diff = lead["avg_xg"] - rest["avg_xg"]
            if diff >= DBS_SOFT_XG:
                buckets["verdict"] = "előnyben leül a faluk"
            elif diff <= DBS_TIGHT_XG:
                buckets["verdict"] = "előnyben is feszes a faluk"
    return out


# Pazarló-poszt: ennyi poszthoz kötött, kaput elkerülő lövés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a pontatlan
# lövéseik egy posztra sűrűsödnek.
WSR_MIN_OFF = 3
WSR_SHARE_PCT = 60.0


def wasteful_shooter_roles(match: Match,
                           config: Optional[XGConfig] = None) -> dict:
    """Pazarló-poszt: MELYIK POSZTJUK lövi mellé a lövéseit.

    A pontatlan lövők rétege (wasteful_shooters) az embert nevezi
    meg — ez a posztot: a kaput elkerülő (mellé/blokkolt) lövéseket
    a lövő posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez a védekezés-takarékosság terve: amelyik posztjuk
    rendre mellé lő, arra rá lehet engedni a lövést — ott a kilépés
    és a belemenés fölösleges kockázat, a mellé lövés utáni kidobás
    pedig azonnali indítás nektek. Saját csapatra: célzás-gyakorlat
    a posztnak, vagy a befejezés átosztása.

    Visszatérés csapatonként: {"off_target" (poszthoz kötött, kaput
    elkerülő lövés), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    WSR_MIN_OFF, vagy egyik poszt sem éri el a WSR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    roles = estimate_positions(match, TacticsConfig())
    ws = wasteful_shooters(match, config)

    out: dict = {side: {"off_target": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in ws[side]["players"]:
            if not row["off_target"]:
                continue
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["off_target"])
            rec["off_target"] += row["off_target"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["off_target"] >= WSR_MIN_OFF:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["off_target"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= WSR_SHARE_PCT:
                rec["verdict"] = (
                    f"a kaput elkerülő lövéseik {share:.0f}%-a a(z) "
                    f"{poszt} posztról jön ({rec['off_target']} mellé/"
                    "blokkolt lövésből) — az ő lövését rá lehet "
                    "engedni: kilépés helyett zárt sáv, a mellé lövés "
                    "utáni kidobás azonnali indítás")
    return out


# Ziccer-poszt: ennyi poszthoz kötött nagy helyzet kell az ítélethez,
# és ekkora részarány fölött mondjuk ki, hogy a ziccereik egy posztnál
# alakulnak ki.
BCR_MIN_CHANCES = 3
BCR_SHARE_PCT = 60.0


def big_chance_roles(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Ziccer-poszt: MELYIK POSZTJUKNÁL alakul ki a nagy helyzet.

    A ziccer-befejezők rétege (big_chance_finishers) az embert nevezi
    meg — ez a posztot: a BIG_CHANCE_XG feletti helyzet-értékű
    lövéseket a lövő posztjához írja. Így a minta akkor is látszik,
    ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a megelőzés terve: ha a ziccereik rendre ugyanannál a
    posztnál alakulnak ki, a helyzetet a kialakulása ELŐTT kell
    megfogni — korábbi besegítés és szűkítés az ő sávjában, mert ami
    ott már kialakult, az jó eséllyel gól. Saját csapatra: ha csak
    egy posztunk jut ziccerbe, a helyzet-teremtésünk egysíkú.

    Visszatérés csapatonként: {"chances" (poszthoz kötött nagy
    helyzet), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg a BCR_MIN_CHANCES,
    vagy egyik poszt sem éri el a BCR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    roles = estimate_positions(match, config or TacticsConfig())
    bcf = big_chance_finishers(match, config)

    out: dict = {side: {"chances": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in bcf[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["chances"])
            rec["chances"] += row["chances"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["chances"] >= BCR_MIN_CHANCES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["chances"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= BCR_SHARE_PCT:
                rec["verdict"] = (
                    f"a ziccereik {share:.0f}%-a a(z) {poszt} "
                    f"posztnál alakul ki ({rec['chances']} nagy "
                    "helyzetből) — a helyzetet a kialakulása előtt "
                    "kell megfogni: korábbi besegítés és szűkítés "
                    "az ő sávjában")
    return out


# Ziccerhagyó-poszt: ennyi poszthoz kötött kihagyott nagy helyzet
# kell az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# ziccer-kihagyásaik egy posztra sűrűsödnek.
MCR_MIN_MISSES = 3
MCR_SHARE_PCT = 60.0


def missed_chance_roles(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Ziccerhagyó-poszt: MELYIK POSZTJUK hagyja ki a ziccereket.

    A ziccer-befejezők rétege (big_chance_finishers) az embert nevezi
    meg — ez a posztot: a BIG_CHANCE_XG feletti helyzet-értékű, gól
    NÉLKÜL záruló lövéseket a lövő posztjához írja. Így a minta akkor
    is látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a fal kockázat-kezelése: amelyik posztjuk a ziccert
    rendre kihagyja, annál a helyzetbe engedés a kisebbik rossz — a
    besegítés inkább a biztos kezű társakra menjen, az ő ziccere
    vállalható. Saját csapatra: a posztnak befejezés-gyakorlás kell
    (ziccer-sorozatok kapussal, fáradtan is).

    Visszatérés csapatonként: {"misses" (poszthoz kötött kihagyott
    ziccer), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg az MCR_MIN_MISSES,
    vagy egyik poszt sem éri el az MCR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig as _TC

    roles = estimate_positions(match, _TC())
    xg = match_xg(match, config)

    out: dict = {side: {"misses": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for sh in xg["shots"]:
        pid = sh.get("player_id")
        if pid is None or sh["xg"] < BIG_CHANCE_XG:
            continue
        if sh["outcome"] == "goal":
            continue
        side = sh["team"]
        rec_role = roles[side].get(pid)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["misses"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["misses"] >= MCR_MIN_MISSES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["misses"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= MCR_SHARE_PCT:
                rec["verdict"] = (
                    f"a kihagyott ziccereik {share:.0f}%-a a(z) "
                    f"{poszt} posztnál esik ({rec['misses']} "
                    "kihagyásból) — az ő helyzetbe engedése a "
                    "kisebbik rossz: a besegítés a biztos kezű "
                    "társakra menjen")
    return out


# Fáradt-lövő poszt: legalább ennyi 2. félidei kaput elkerülő lövés
# kell, és ennyiszerese az első félideinek, hogy a posztot fáradt
# lövőjűnek mondjuk ki.
FSA_MIN_SH = 3
FSA_FACTOR = 2.0


def tired_shooter_roles(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Fáradt-lövő poszt: MELYIK POSZTJUK lövései mennek szét fáradtan.

    A pazarló-poszt a teljes meccset nézi — ez a fáradást: a kaput
    elkerülő (mellé/blokkolt) lövéseket félidőnként a lövő
    posztjához írja, és megkeresi, melyik posztjuk pontatlansága
    ugrik meg a második félidőre. Így látszik, kinek megy szét
    fáradtan a lövése.

    Edzőileg ez a második félidei fal-terv: akinek fáradtan szétmegy
    a lövése, arra a szünet után rá lehet engedni — a kilépés nála
    már fölösleges kockázat. Saját csapatra: fáradt célzás-blokk és
    a befejezés átosztása a második félidőben.

    Visszatérés csapatonként: {"fh_roles": {poszt: darab},
    "sh_roles": {poszt: darab}, "main_role", "fh", "sh", "verdict"}
    — az ítélet None, ha nincs felismert szünet, vagy egyik poszt
    sem éri el az FSA_MIN_SH-t az FSA_FACTOR-os ugrással.
    """
    from .halftime import detect_halftime
    from .roles import estimate_positions
    from .tactics import TacticsConfig as _TC

    out: dict = {side: {"fh_roles": {}, "sh_roles": {},
                        "main_role": None, "fh": None, "sh": None,
                        "verdict": None}
                 for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    roles = estimate_positions(match, _TC())
    xg = match_xg(match, config)

    for sh in xg["shots"]:
        pid = sh.get("player_id")
        if pid is None or sh["outcome"] in ("goal", "save"):
            continue
        side = sh["team"]
        key = "fh_roles" if sh["t"] <= ht else "sh_roles"
        rec_role = roles[side].get(pid)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        out[side][key][poszt] = out[side][key].get(poszt, 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        fader = None
        for poszt, n_sh in sorted(rec["sh_roles"].items(),
                                  key=lambda kv: -kv[1]):
            n_fh = rec["fh_roles"].get(poszt, 0)
            if n_sh >= FSA_MIN_SH and n_sh >= FSA_FACTOR * max(1, n_fh):
                fader = (poszt, n_fh, n_sh)
                break
        if fader is not None:
            poszt, n_fh, n_sh = fader
            rec["main_role"] = poszt
            rec["fh"], rec["sh"] = n_fh, n_sh
            rec["verdict"] = (
                f"a(z) {poszt} posztjuk kaput elkerülő lövései a "
                f"második félidőre megugranak ({n_fh} → {n_sh}) — "
                "fáradtan szétmegy a lövése: a szünet után rá lehet"
                " engedni, a kilépés nála fölösleges kockázat")
    return out


# Ziccer-előkészítő poszt: ennyi poszthoz kötött ziccer-előkészítés
# kell az ítélethez, ekkora részarány fölött mondjuk ki a mintát, és
# ennyi időn belüli utolsó passzt tekintünk előkészítésnek.
BCF_FEED_MIN = 3
BCF_FEED_SHARE_PCT = 60.0
BCF_FEED_WINDOW_S = 4.0


def big_chance_feeder_roles(match: Match,
                            config: Optional[TacticsConfig] = None
                            ) -> dict:
    """Ziccer-előkészítő poszt: KI ADJA a passzt a nagy helyzethez.

    A ziccer-poszt azt mondja meg, MELYIK POSZTNÁL alakul ki a nagy
    helyzet — ez azt, KI TEREMTI: a BIG_CHANCE_XG feletti lövésekhez
    megkeresi a lövő felé menő utolsó passzt, és a helyzetet a
    PASSZOLÓ posztjához írja. Az előkészítő-poszt minden lövést néz,
    ez csak a veszélyeseket.

    Edzőileg ez a legdrágább passzsáv: ha a ziccereik nagy része
    ugyanannak a posztnak a kezéből indul, az ő bejátszó-sávját kell
    elvágni (testtel zárás, előrelépő védő) — a helyzet így ki sem
    alakul, nem a befejezést kell hárítani. Saját csapatra: ha a
    ziccer-teremtés egy emberen áll, a kiesésével a helyzeteink is
    eltűnnek.

    Visszatérés csapatonként: {"chances" (poszthoz kötött
    ziccer-előkészítés), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    BCF_FEED_MIN, vagy egyik poszt sem éri el a
    BCF_FEED_SHARE_PCT-t.
    """
    from .decisions import detect_passes
    from .roles import estimate_positions
    from .tactics import TacticsConfig as _TC

    config = config or _TC()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = BCF_FEED_WINDOW_S * fps
    roles = estimate_positions(match, config)
    passes = detect_passes(match, config)
    xg = match_xg(match, config)

    out: dict = {side: {"chances": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for sh in xg["shots"]:
        pid = sh.get("player_id")
        if pid is None or sh["xg"] < BIG_CHANCE_XG:
            continue
        side = sh["team"]
        best = None
        for p in passes:
            if not (0 <= sh["t"] - p.t <= win):
                continue
            if p.team.value != side:
                continue
            if p.receiver_id != pid or p.passer_id == pid:
                continue
            if best is None or p.t > best.t:
                best = p
        if best is None:
            continue
        rec_role = roles[side].get(best.passer_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["chances"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["chances"] >= BCF_FEED_MIN:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["chances"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= BCF_FEED_SHARE_PCT:
                rec["verdict"] = (
                    f"a ziccereik {share:.0f}%-át a(z) {poszt} "
                    f"posztjuk teremti ({rec['chances']} "
                    "ziccer-előkészítésből) — az ő bejátszó-sávját "
                    "vágjátok el: a helyzet így ki sem alakul, nem "
                    "a befejezést kell hárítani")
    return out


# Ziccerpáros-poszt küszöbei: ennyi poszthoz kötött ziccer-páros kell
# az ítélethez, és ekkora részarány a fő párosnak (a páros ritkább
# esemény, mint az egy-posztos minta, ezért enyhébb a részarány).
BCP_PAIR_MIN = 3
BCP_PAIR_SHARE_PCT = 55.0


def big_chance_pair_roles(match: Match,
                          config: Optional[TacticsConfig] = None
                          ) -> dict:
    """Ziccerpáros-poszt: KI ADJA és KI FEJEZI BE a nagy helyzeteiket.

    A ziccer-előkészítő poszt azt mondja meg, kinek a kezéből indul a
    nagy helyzet, a ziccer-poszt azt, kinél alakul ki — ez a kettőt
    köti össze helyzetenként: az (előkészítő poszt → befejező poszt)
    párost számolja. A gólpasszpáros a GÓLLAL zárult összjátékot
    nézi, ez a helyzet-értéket: itt a bejáratott ziccer-gyár akkor is
    látszik, ha a befejezés sokszor kimarad.

    Edzőileg egy mozdulattal két posztot fog ki a védekezés: a párost
    nem külön-külön kell fogni, hanem a köztük lévő passzsávot
    elvágni (testtel zárás a bejátszó és az érkező között,
    előrelépéssel a passz idejére) — ha a sáv zárva van, a ziccer ki
    sem alakul. Saját csapatra: ha a ziccereink egyetlen kettősön
    állnak, a párost szét kell szedni az edzésen (más befejező, más
    bejátszó), különben az ellenfél egy emberrel megfogja mindkettőt.

    Visszatérés csapatonként: {"chances" (poszthoz kötött
    ziccer-páros), "roles": {"A→B": darab}, "main_role" (a fő páros),
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    BCP_PAIR_MIN, vagy egyik páros sem éri el a
    BCP_PAIR_SHARE_PCT-t.
    """
    from .decisions import detect_passes
    from .roles import estimate_positions
    from .tactics import TacticsConfig as _TC

    config = config or _TC()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = BCF_FEED_WINDOW_S * fps
    roles = estimate_positions(match, config)
    passes = detect_passes(match, config)
    xg = match_xg(match, config)

    out: dict = {side: {"chances": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for sh in xg["shots"]:
        pid = sh.get("player_id")
        if pid is None or sh["xg"] < BIG_CHANCE_XG:
            continue
        side = sh["team"]
        # A helyzethez vezető utolsó passz — mint a ziccer-előkészítő
        # rétegben; itt a passzoló ÉS a befejező posztja is kell.
        best = None
        for p in passes:
            if not (0 <= sh["t"] - p.t <= win):
                continue
            if p.team.value != side:
                continue
            if p.receiver_id != pid or p.passer_id == pid:
                continue
            if best is None or p.t > best.t:
                best = p
        if best is None:
            continue
        r_feed = roles[side].get(best.passer_id)
        r_fin = roles[side].get(pid)
        if r_feed is None or r_fin is None:
            continue
        kulcs = f"{r_feed['poszt']}→{r_fin['poszt']}"
        rec = out[side]
        rec["roles"][kulcs] = rec["roles"].get(kulcs, 0) + 1
        rec["chances"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["chances"] >= BCP_PAIR_MIN:
            par = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][par] / rec["chances"]
            rec["main_role"] = par
            rec["share_pct"] = round(share, 1)
            if share >= BCP_PAIR_SHARE_PCT:
                rec["verdict"] = (
                    f"a ziccereik {share:.0f}%-a ugyanabból a "
                    f"párosból jön ({par}, {rec['chances']} "
                    "helyzetből) — nem külön-külön kell fogni őket, "
                    "hanem a köztük lévő passzsávot elvágni: zárt "
                    "sávnál a helyzet ki sem alakul")
    return out


# Ziccer-előkészítők: ennyi ziccer-előkészítéstől emeljük ki a
# játékost.
BCFP_MIN_FEEDS = 2


def big_chance_feeders(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Ziccer-előkészítők: KI ADJA a passzt a nagy helyzethez.

    A ziccer-előkészítő poszt (big_chance_feeder_roles) a POSZTOT
    nevezi meg — ez az EMBERT: a BIG_CHANCE_XG feletti lövésekhez
    megkeresi a lövő felé menő utolsó passzt, és a helyzetet a
    PASSZOLÓ játékoshoz írja.

    Edzőileg ez a legdrágább passzsáv névre szólóan: az ő
    bejátszó-sávját kell elvágni (testtel zárás, előrelépő védő) — a
    helyzet így ki sem alakul, nem a befejezést kell hárítani. Saját
    csapatra: ha a ziccer-teremtés egy emberen áll, a kiesésével a
    helyzeteink is eltűnnek.

    Visszatérés csapatonként: {"chances" (emberhez kötött
    ziccer-előkészítés), "players": [{"player_id", "jersey",
    "chances"}], "top"} — a "top" az első játékos, ha legalább
    BCFP_MIN_FEEDS előkészítése van, különben None.
    """
    from .decisions import detect_passes
    from .tactics import TacticsConfig as _TC

    config = config or _TC()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = BCF_FEED_WINDOW_S * fps
    passes = detect_passes(match, config)
    xg = match_xg(match, config)

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for sh in xg["shots"]:
        pid = sh.get("player_id")
        if pid is None or sh["xg"] < BIG_CHANCE_XG:
            continue
        side = sh["team"]
        best = None
        for p in passes:
            if not (0 <= sh["t"] - p.t <= win):
                continue
            if p.team.value != side:
                continue
            if p.receiver_id != pid or p.passer_id == pid:
                continue
            if best is None or p.t > best.t:
                best = p
        if best is None:
            continue
        tally[side][best.passer_id] = (
            tally[side].get(best.passer_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "chances": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0]
               if rows and rows[0]["chances"] >= BCFP_MIN_FEEDS
               else None)
        out[side] = {"chances": sum(r["chances"] for r in rows),
                     "players": rows, "top": top}
    return out
