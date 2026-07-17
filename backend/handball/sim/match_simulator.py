"""
Meccs-szimulátor — valósághű szintetikus kézilabda-mozgás, VIDEÓ NÉLKÜL.

Miért kell: tesztvideót nem mindig lehet feltölteni/feldolgozni (méret, GPU,
jogvédelem). Ez a modul a nyers pixelek nélkül állít elő élethű `Tracking`-et,
hogy:
- a Flutter-kliens valós adatra fejleszthető/tesztelhető legyen,
- a teljes downstream lánc (becslés, statisztika, megjelenítés) életre keljen,
- a pásztázó kamera + becslés viselkedését DEMONSTRÁLNI tudjuk (a VALÓDI [F]
  becslőnkkel), ahogy egy igazi meccsen működne.

Két lépés:
1. `simulate_ground_truth(...)` — "földi igazság": mind a 14 játékos (7+7) és a
   labda valósághű mozgása. Itt MINDEN játékos mért (ezt a kamera nem korlátozza).
2. `simulate_with_panning_camera(...)` — egy mozgó látómező (a labdát követő
   pásztázás) modellezése: a látómezőn KÍVÜL eső játékosokat "nem látottnak"
   vesszük, és a valódi OffScreenEstimator-ral BECSÜLJÜK őket. Ez adja azt a
   Tracking-et, amit a rendszer egy igazi pásztázó kamerán előállítana.

A mozgás determinisztikus (sin-oszcilláció + ütemezett passzok) + kevés zaj egy
magból (seed), hogy a tesztek reprodukálhatók legyenek.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from ..models.events import RosterTimeline
from ..pipeline.estimation import OffScreenEstimator
from ..pipeline.calibration import COURT_LENGTH_M, COURT_WIDTH_M


@dataclass
class _PlayerSpec:
    """Egy szintetikus játékos alap-jellemzői (a mozgás ebből származik)."""
    track_id: int
    team: Team
    role: str
    base_x: float      # nyugalmi pálya-pozíció (méter)
    base_y: float
    jersey: int
    is_gk: bool = False


def _roster_specs() -> list[_PlayerSpec]:
    """A 14 játékos (7 hazai + 7 vendég) szerepei és alappozíciói.

    A HAZAI támad a jobb oldali (x=40) kapu felé; a VENDÉG 6-0-ban védekezik a
    saját kapuja (x=40) előtt. A koordináták a 40x20 m-es pályán, méterben.
    """
    cy = COURT_WIDTH_M / 2.0  # 10 m
    return [
        # HAZAI támadás ( id 1..7)
        _PlayerSpec(1, Team.HOME, "bal_szelso", 30.0, 2.5, 7),
        _PlayerSpec(2, Team.HOME, "bal_atlovo", 28.0, 6.0, 9),
        _PlayerSpec(3, Team.HOME, "iranyito", 27.0, cy, 10),
        _PlayerSpec(4, Team.HOME, "jobb_atlovo", 28.0, 14.0, 4),
        _PlayerSpec(5, Team.HOME, "jobb_szelso", 30.0, 17.5, 11),
        _PlayerSpec(6, Team.HOME, "beallo", 34.0, cy, 13),
        _PlayerSpec(7, Team.HOME, "kapus", 1.0, cy, 1, is_gk=True),
        # VENDÉG 6-0 védekezés (id 11..17), a 6 m-es ív körül x~35-36
        _PlayerSpec(11, Team.AWAY, "vedo1", 35.5, 3.0, 7),
        _PlayerSpec(12, Team.AWAY, "vedo2", 35.0, 6.5, 8),
        _PlayerSpec(13, Team.AWAY, "vedo3", 34.8, cy - 1.0, 5),
        _PlayerSpec(14, Team.AWAY, "vedo4", 34.8, cy + 1.0, 6),
        _PlayerSpec(15, Team.AWAY, "vedo5", 35.0, 13.5, 3),
        _PlayerSpec(16, Team.AWAY, "vedo6", 35.5, 17.0, 12),
        _PlayerSpec(17, Team.AWAY, "kapus", 39.0, cy, 1, is_gk=True),
    ]


# A labda körbejár a hazai támadók között (ütemezett passz-útvonal): id-k.
_BALL_ROUTE = [3, 2, 1, 2, 3, 4, 5, 4, 3, 6]
_PASS_PERIOD_S = 1.0  # ennyi időnként vált a labdabirtokos


def _player_xy(spec: _PlayerSpec, t: int, fps: float, rng: random.Random) -> tuple[float, float]:
    """Egy játékos pozíciója a `t` frame-en: alappozíció + lassú oszcilláció + kis zaj.

    A kapus alig mozog; a mezőnyjátékosok szerepfüggő fázissal ingadoznak, hogy a
    kép "éljen", de a pályán belül maradjanak.
    """
    sec = t / fps
    if spec.is_gk:
        amp_x, amp_y = 0.3, 0.6
    else:
        amp_x, amp_y = 0.8, 1.2
    phase = (spec.track_id % 7) * 0.9         # szerepfüggő fáziseltolás
    x = spec.base_x + amp_x * math.sin(0.7 * sec + phase)
    y = spec.base_y + amp_y * math.sin(0.5 * sec + phase * 1.3)
    # Kevés véletlen zaj (reprodukálható a seed miatt).
    x += rng.uniform(-0.15, 0.15)
    y += rng.uniform(-0.15, 0.15)
    # A pályán belül tartjuk.
    x = max(0.0, min(COURT_LENGTH_M, x))
    y = max(0.0, min(COURT_WIDTH_M, y))
    return x, y


def _ball_xy(positions: dict[int, tuple[float, float]], t: int, fps: float) -> tuple[float, float]:
    """A labda pozíciója: a pillanatnyi és a következő labdabirtokos között
    interpolálva (passz-mozgás), kis előretartással a birtokos felé."""
    period_frames = max(1, int(_PASS_PERIOD_S * fps))
    idx = (t // period_frames) % len(_BALL_ROUTE)
    nxt = (idx + 1) % len(_BALL_ROUTE)
    holder = _BALL_ROUTE[idx]
    receiver = _BALL_ROUTE[nxt]
    # Hol tartunk a passz-cikluson belül (0..1).
    frac = (t % period_frames) / period_frames
    hx, hy = positions[holder]
    rx, ry = positions[receiver]
    # A ciklus elején a birtokosnál van, a vége felé a fogadó felé halad.
    ease = max(0.0, (frac - 0.6) / 0.4)  # 0-ig 60%-ig, majd lineárisan a fogadóig
    bx = hx + (rx - hx) * ease
    by = hy + (ry - hy) * ease
    return bx, by


def simulate_ground_truth(duration_s: float = 8.0, fps: float = 25.0,
                          seed: int = 0) -> Match:
    """A "földi igazság": mind a 14 játékos + labda valósághű mozgása.

    Minden játékos MÉRT (a kamera-korlát nélkül). Ez a referencia, amiből a
    pásztázó-kamerás változatot származtatjuk.
    """
    rng = random.Random(seed)
    specs = _roster_specs()
    meta = MatchMeta(
        match_id=f"sim-{seed}", home_team="Szimu Hazai", away_team="Szimu Vendég",
        fps=fps, frame_width=1920, frame_height=1080, date="2026-06-29",
    )
    match = Match(meta=meta, frames=[])
    n_frames = int(duration_s * fps)
    for t in range(n_frames):
        positions = {s.track_id: _player_xy(s, t, fps, rng) for s in specs}
        players = [
            PlayerPosition(
                track_id=s.track_id, team=s.team,
                x=positions[s.track_id][0], y=positions[s.track_id][1],
                source=PositionSource.MEASURED, confidence=1.0,
                jersey_number=s.jersey, role=s.role,
            )
            for s in specs
        ]
        bx, by = _ball_xy(positions, t, fps)
        match.frames.append(Frame(t=t, players=players, ball=Ball(x=bx, y=by)))
    return match


def simulate_with_panning_camera(ground_truth: Match, fov_width_m: float = 18.0,
                                 roster: RosterTimeline | None = None) -> Match:
    """Pásztázó kamera modellezése a földi igazságra + a VALÓDI becslő alkalmazása.

    Minden frame-en a kamera látómezeje egy `fov_width_m` széles ablak az x tengely
    mentén, a LABDÁT követve. A látómezőn kívüli játékosok "nem látottak" → őket az
    OffScreenEstimator becsüli (source=ESTIMATED), pont úgy, ahogy egy igazi
    pásztázó-kamerás felvételen történne.

    Visszaadja azt a Tracking-et, amit a rendszer ilyen kamerán előállítana.
    """
    roster = roster or RosterTimeline()
    estimator = OffScreenEstimator(roster)
    out = Match(meta=ground_truth.meta, frames=[])

    for frame in ground_truth.frames:
        # A kamera középpontja a labdát követi (ha nincs labda, a pálya közepe).
        cam_x = frame.ball.x if frame.ball is not None else COURT_LENGTH_M / 2.0
        half = fov_width_m / 2.0

        # A látómezőn belüli játékosok = MÉRT; a többit majd becsüljük.
        visible = [p for p in frame.players if abs(p.x - cam_x) <= half]

        # A valódi [F] becslő: előbb a látottakból tanul, majd a hiányzókat becsli.
        estimator.update_seen(frame.t, visible)
        estimated = estimator.estimate_missing(frame.t, visible)

        # A labdát csak akkor "látjuk", ha a látómezőben van.
        ball = frame.ball if (frame.ball is not None and abs(frame.ball.x - cam_x) <= half) else None

        out.frames.append(Frame(t=frame.t, players=visible + estimated, ball=ball))
    return out


def append_demo_episodes(match: Match) -> None:
    """FORGATÓKÖNYV-epizódok a demó meccs végére — hogy az elemző rétegek
    (gól-sorozat, hétméteres, cserehullám, időkérés) a demóban is éledjenek.

    Az epizódok az utolsó képkocka játékosaiból építkeznek (kis, élethű
    mozgással), és sorban fűződnek a meccs végére:
      1. hazai 3 gólos sorozat (momentum + xG),
      2. hétméteres, majd értékesítés (szabály-réteg + kimenetel),
      3. hazai cserehullám a cserezónán át,
      4. vendég időkérés (rövid birtoklás után 18 mp állás).
    A meccset HELYBEN bővíti."""
    if not match.frames:
        return
    base = match.frames[-1]
    t = base.t + 1
    gone: set[int] = set()

    def clones(phase: float, frozen: bool = False, extra=None):
        players = []
        for p in base.players:
            if p.track_id in gone:
                continue
            dx = 0.0 if frozen else 0.4 * math.sin(phase + p.track_id)
            dy = 0.0 if frozen else 0.3 * math.cos(0.8 * phase + p.track_id)
            players.append(PlayerPosition(
                track_id=p.track_id, team=p.team,
                x=min(39.5, max(0.5, p.x + dx)),
                y=min(19.5, max(0.5, p.y + dy)),
                source=PositionSource.MEASURED, confidence=1.0,
                jersey_number=p.jersey_number, role=p.role))
        if extra:
            players.extend(extra)
        return players

    def emit(ball, frozen=False, extra=None):
        nonlocal t
        match.frames.append(Frame(t=t, players=clones(t / 6.0, frozen=frozen,
                                                      extra=extra),
                                  ball=ball))
        t += 1

    def goal_to_plus_x():
        for i in range(7):
            emit(Ball(x=min(40.0, 34.0 + i), y=10.0, confidence=1.0))
        for _ in range(50):  # visszaállás (debounce a következő gólig)
            emit(Ball(x=20.0, y=10.0, confidence=1.0))

    # 1) Hazai 3 gólos sorozat.
    for _ in range(3):
        goal_to_plus_x()

    # 2) Hétméteres: álló labda a 7 m-es ponton, majd értékesítés.
    for _ in range(30):
        emit(Ball(x=33.0, y=10.0, confidence=1.0))
    goal_to_plus_x()

    # 3) Cserehullám: egy hazai mezőnyjátékos a cserezónába megy és lemegy,
    #    a 90-es ott jön be, és beáll a helyére.
    out_p = next(p for p in base.players
                 if p.team == Team.HOME and p.role != "kapus")
    gone.add(out_p.track_id)
    for k in range(100):  # 4 mp: kifelé sétál
        frac = k / 99.0
        walker = PlayerPosition(
            track_id=out_p.track_id, team=Team.HOME,
            x=out_p.x + (20.0 - out_p.x) * frac,
            y=out_p.y + (1.0 - out_p.y) * frac,
            source=PositionSource.MEASURED, confidence=1.0,
            jersey_number=out_p.jersey_number)
        emit(Ball(x=20.0, y=10.0, confidence=1.0), extra=[walker])
    for k in range(100):  # a csere befut
        frac = k / 99.0
        sub_in = PlayerPosition(
            track_id=90, team=Team.HOME,
            x=20.0 + 10.0 * frac, y=1.0 + 11.0 * frac,
            source=PositionSource.MEASURED, confidence=1.0)
        emit(Ball(x=20.0, y=10.0, confidence=1.0), extra=[sub_in])

    # 4) Időkérés: a vendég birtokol pár mp-ig, majd mindenki megáll.
    holder = next(p for p in base.players
                  if p.team == Team.AWAY and p.role != "kapus")
    for _ in range(75):
        hp = next(pp for pp in match.frames[-1].players
                  if pp.track_id == holder.track_id)
        emit(Ball(x=hp.x, y=hp.y, confidence=1.0))
    for _ in range(int(18 * 25)):
        emit(None, frozen=True)
    for _ in range(75):  # újraindulás
        emit(Ball(x=20.0, y=10.0, confidence=1.0))
