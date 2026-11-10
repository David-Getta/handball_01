"""
Tesztek a félidő-érzékelésre és térfélcsere-normalizálásra (halftime.py).

Futtatás:
    python -m pytest tests/test_halftime.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.halftime import (
    auto_normalize, detect_halftime, detect_side_swap, normalize_sides,
)

FPS = 25.0


def _meta():
    return MatchMeta(match_id="ht", home_team="H", away_team="A", fps=FPS)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _play_frames(t0, seconds, home_x, away_x):
    """Aktív játék: 6-6 mért játékos a megadott térfél-középpontok körül."""
    frames = []
    for i in range(int(seconds * FPS)):
        players = [_pl(100 + k, Team.HOME, home_x + k * 0.5, 4.0 + k * 2)
                   for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, away_x + k * 0.5, 4.0 + k * 2)
                    for k in range(6)]
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=(home_x + away_x) / 2, y=10.0,
                                      confidence=1.0)))
    return frames


def _break_frames(t0, seconds):
    """Szünet: üres pálya (nincs mért játékos, nincs labda)."""
    return [Frame(t=t0 + i, players=[], ball=None)
            for i in range(int(seconds * FPS))]


def _full_match(swap=True, break_s=90):
    """1. félidő (hazai balra) + szünet + 2. félidő (cserélt vagy azonos)."""
    frames = _play_frames(0, 120, home_x=12.0, away_x=26.0)
    t = len(frames)
    frames += _break_frames(t, break_s)
    t = len(frames)
    if swap:
        frames += _play_frames(t, 120, home_x=26.0, away_x=12.0)
    else:
        frames += _play_frames(t, 120, home_x=12.0, away_x=26.0)
    return Match(_meta(), frames)


def test_halftime_detected_in_middle():
    m = _full_match()
    ht = detect_halftime(m)
    assert ht is not None
    # A szünet a 120–210 mp tartományban van.
    assert 120 * FPS <= ht <= 210 * FPS


def test_no_halftime_without_break():
    m = Match(_meta(), _play_frames(0, 240, home_x=12.0, away_x=26.0))
    assert detect_halftime(m) is None


def test_side_swap_detected_and_normalized():
    m = _full_match(swap=True)
    ht = detect_halftime(m)
    assert detect_side_swap(m, ht) is True
    mirrored = normalize_sides(m, ht)
    assert mirrored > 0
    # Normalizálás után a hazai súlypont a 2. félidőben is a bal térfélen.
    from handball.pipeline.halftime import _centroid_x
    b = _centroid_x(m, Team.HOME, ht, m.frames[-1].t + 1)
    assert b is not None and b < 20.0


def test_no_swap_when_sides_kept():
    m = _full_match(swap=False)
    ht = detect_halftime(m)
    assert ht is not None
    assert detect_side_swap(m, ht) is False


def test_auto_normalize_end_to_end():
    m = _full_match(swap=True)
    info = auto_normalize(m)
    assert info is not None and info["swapped"] is True
    assert info["mirrored_frames"] > 0
    # Szünet nélküli meccsen nem csinál semmit.
    m2 = Match(_meta(), _play_frames(0, 240, home_x=12.0, away_x=26.0))
    assert auto_normalize(m2) is None


def test_second_half_start_counts_goals():
    """A szünet utáni első 5 perc góljai csapatonként; félidő-jel
    nélkül None."""
    from handball.pipeline.halftime import second_half_start

    frames = _play_frames(0, 120, home_x=12.0, away_x=26.0)
    t = len(frames)
    frames += _break_frames(t, 90)
    t = len(frames)
    frames += _play_frames(t, 30, home_x=12.0, away_x=26.0)
    t = len(frames)
    for i in range(8):  # hazai gól a szünet után (a +x kapuba)
        frames.append(Frame(t=t + i,
                            players=[_pl(100, Team.HOME, 33.5, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
    t += 8
    frames += _play_frames(t, 30, home_x=12.0, away_x=26.0)
    m = Match(_meta(), frames)
    rec = second_half_start(m)
    assert rec is not None
    assert rec["home"] >= 1 and rec["away"] == 0

    no_ht = Match(_meta(), _play_frames(0, 240, home_x=12.0,
                                        away_x=26.0))
    assert second_half_start(no_ht) is None


def test_first_half_close_counts_goals_before_break():
    """A szünet előtti 5 perc góljai csapatonként; félidő-jel nélkül
    None."""
    from handball.pipeline.halftime import first_half_close

    frames = _play_frames(0, 90, home_x=12.0, away_x=26.0)
    t = len(frames)
    for i in range(8):  # hazai gól a szünet előtt (a +x kapuba)
        frames.append(Frame(t=t + i,
                            players=[_pl(100, Team.HOME, 33.5, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
    t += 8
    frames += _play_frames(t, 30, home_x=12.0, away_x=26.0)
    t = frames[-1].t + 1
    frames += _break_frames(t, 90)
    t = frames[-1].t + 1
    frames += _play_frames(t, 120, home_x=12.0, away_x=26.0)
    m = Match(_meta(), frames)
    rec = first_half_close(m)
    assert rec is not None
    assert rec["home"] >= 1 and rec["away"] == 0

    no_ht = Match(_meta(), _play_frames(0, 240, home_x=12.0,
                                        away_x=26.0))
    assert first_half_close(no_ht) is None


# ---- A szünet SÁVJA (detect_break_span / credible_break_span) ----------------

def _ritka_frames(t0, seconds, n=2, source=PositionSource.MEASURED):
    """Ritkás követés: csak `n` játékos látszik (a megadott forrással)."""
    frames = []
    for i in range(int(seconds * FPS)):
        players = [PlayerPosition(track_id=300 + k, team=Team.HOME,
                                  x=10.0 + k, y=5.0 + k, source=source,
                                  confidence=1.0) for k in range(n)]
        frames.append(Frame(t=t0 + i, players=players, ball=None))
    return frames


def _szakaszok(*reszek):
    """Szakaszok egymás után: ("jatek" | "szunet" | "ritka", mp) párok."""
    frames = []
    for fajta, mp in reszek:
        t = len(frames)
        if fajta == "jatek":
            frames += _play_frames(t, mp, home_x=12.0, away_x=26.0)
        elif fajta == "szunet":
            frames += _break_frames(t, mp)
        else:
            frames += _ritka_frames(t, mp)
    return Match(_meta(), frames)


def test_break_span_a_szunet_teljes_kiterjedeset_adja():
    """120 mp játék + 90 mp szünet + 120 mp játék: a sáv pont a szünet
    kockái (zárt index-pár), és a félidő-pont ennek a közepe."""
    from handball.pipeline.halftime import detect_break_span

    m = _full_match(break_s=90)
    span = detect_break_span(m)
    assert span == (3000, 5249)
    assert all(not m.frames[i].players for i in span)
    assert m.frames[span[0] - 1].players and m.frames[span[1] + 1].players
    assert detect_halftime(m) == m.frames[(span[0] + span[1]) // 2].t


def test_break_span_rovid_vagy_hianyzo_szunetnel_none():
    """60 mp alatti megállás (időkérés, sérülés-ápolás) nem félidei
    szünet; szünet nélküli, egykockás és üres felvételen sincs sáv."""
    from handball.pipeline.halftime import BREAK_MIN_S, detect_break_span

    assert BREAK_MIN_S == 60.0
    assert detect_break_span(_full_match(break_s=50)) is None
    assert detect_break_span(_full_match(break_s=60)) == (3000, 4499)
    assert detect_break_span(
        Match(_meta(), _play_frames(0, 240, 12.0, 26.0))) is None
    assert detect_break_span(Match(_meta(), _break_frames(0, 0.04))) is None
    assert detect_break_span(Match(_meta(), [])) is None


def test_break_span_csak_a_felvetel_kozepso_reszen_keres():
    """A felvétel elejére (bemelegítés) vagy végére (levonulás) eső
    hosszú üresjárat nem félidei szünet: a sávot a 20–80% között
    keressük."""
    from handball.pipeline.halftime import detect_break_span

    eleje = _szakaszok(("szunet", 90), ("jatek", 600))
    assert detect_break_span(eleje) is None
    vege = _szakaszok(("jatek", 600), ("szunet", 90))
    assert detect_break_span(vege) is None


def test_break_span_a_leghosszabb_megallast_valasztja():
    """Két hosszú megállás közül a hosszabb a félidei szünet — akkor is,
    ha a rövidebb van előbb."""
    from handball.pipeline.halftime import detect_break_span

    m = _szakaszok(("jatek", 120), ("szunet", 70), ("jatek", 60),
                   ("szunet", 100), ("jatek", 120))
    # A második megállás a 250. mp-nél kezdődik és 100 mp-ig tart.
    assert detect_break_span(m) == (250 * 25, 350 * 25 - 1)


def test_break_span_csak_a_mert_jatekos_szamit_aktivitasnak():
    """Az aktivitás a MÉRT játékosok ablak-átlaga: a becsült pozíciók
    (akárhány) nem teszik játékká a szünetet; 3 mért játékos még
    "áll a játék", 4 már nem."""
    from handball.pipeline.halftime import LOW_PLAYERS, detect_break_span

    def meccs(n, source):
        frames = _play_frames(0, 120, 12.0, 26.0)
        frames += _ritka_frames(len(frames), 90, n=n, source=source)
        frames += _play_frames(len(frames), 120, 12.0, 26.0)
        return Match(_meta(), frames)

    assert LOW_PLAYERS == 4.0
    assert detect_break_span(
        meccs(12, PositionSource.ESTIMATED)) == (3000, 5249)
    assert detect_break_span(meccs(3, PositionSource.MEASURED)) == (3000, 5249)
    assert detect_break_span(meccs(4, PositionSource.MEASURED)) is None


def test_break_span_ritkitott_felvetelen_is_ugyanaz_a_szunet():
    """Az ablak és a minimum MÁSODPERCBEN él: harmad-fps-en (a termék
    ritkítása) ugyanaz a 90 mp-es szünet ugyanott van — egy ablaknyi
    (10 mp) pontossággal."""
    from handball.pipeline.halftime import detect_break_span

    fps = FPS / 3.0
    teljes = _full_match(break_s=90)
    ritka = Match(MatchMeta(match_id="ht3", home_team="H", away_team="A",
                            fps=fps), teljes.frames[::3])
    span = detect_break_span(ritka)
    assert span is not None
    assert abs(span[0] / fps - 120.0) <= 10.0
    assert abs((span[1] + 1) / fps - 210.0) <= 10.0
    # A 60 mp alatti megállás ritkítva sem lesz szünet.
    rovid = _full_match(break_s=50)
    assert detect_break_span(Match(ritka.meta, rovid.frames[::3])) is None


def test_credible_break_span_aktiv_meccsen_a_szunet_savja():
    """Ha a sávon kívül a felvétel jellemzően aktív, a hihető sáv maga a
    felismert szünet-sáv."""
    from handball.pipeline.halftime import (credible_break_span,
                                            detect_break_span)

    m = _full_match(break_s=90)
    assert credible_break_span(m) == detect_break_span(m) == (3000, 5249)


def test_credible_break_span_vegig_ritkas_kovetesnel_none():
    """Végig ritkás követésű felvételen a "szünet" csak a gyenge követés
    közepe: a nyers mérés talál sávot, a hihető változat nem — különben
    valódi gólok esnének ki az esemény-szűrésen."""
    from handball.pipeline.halftime import (credible_break_span,
                                            detect_break_span)

    m = _szakaszok(("ritka", 330))
    assert detect_break_span(m) is not None
    assert credible_break_span(m) is None
    # Szünet nélkül (None nyers sáv) a hihető sáv is None.
    aktiv = Match(_meta(), _play_frames(0, 240, 12.0, 26.0))
    assert credible_break_span(aktiv) is None
    assert credible_break_span(Match(_meta(), [])) is None


def test_credible_break_span_a_kontraszt_kuszobe_a_fele():
    """A sávon kívüli ablakok legalább fele legyen aktív: pont a felénél
    (12/24) még hihető, egy ablakkal kevesebbnél (11/24) már nem."""
    from handball.pipeline.halftime import (BREAK_CONTRAST_SHARE,
                                            credible_break_span,
                                            detect_break_span)

    assert BREAK_CONTRAST_SHARE == 0.5
    fele = _szakaszok(("ritka", 60), ("jatek", 60), ("szunet", 90),
                      ("jatek", 60), ("ritka", 60))
    assert detect_break_span(fele) == (3000, 5249)
    assert credible_break_span(fele) == (3000, 5249)
    alatta = _szakaszok(("ritka", 70), ("jatek", 50), ("szunet", 90),
                        ("jatek", 60), ("ritka", 60))
    assert detect_break_span(alatta) == (3000, 5249)
    assert credible_break_span(alatta) is None
