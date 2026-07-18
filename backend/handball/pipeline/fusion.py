"""Nézet-fúzió — több kamera pozíció-folyamának egyesítése (arénarendszer).

A telepített rendszer (2 oldalvonali + 2 alapvonali kamera, később lidar)
minden nézete UGYANARRA a méteres pálya-koordinátára kalibrálódik (a
meglévő homográfiával). Ez a modul a nézetenkénti Match-eket egyesíti:

- ugyanaz a játékos több nézetben: pozíció-átlag (pontosabb, mint bármelyik
  nézet önmagában);
- takarás az egyik nézetben: a másik nézet kitölti (nincs lyuk);
- labda: a legnagyobb konfidenciájú nézet észlelése.

A fúzió a méteres térben történik, ezért kamera-független — és mivel az
elemzési rétegek mind a Match-en dolgoznak, a kimenet azonnal a teljes
elemző-láncba köthető. Szintetikus nézetekkel, valódi több-kamerás
felvétel nélkül tesztelhető.

Az órajel-eltolás (frame-eltolás a nézetek közt) a labda-pálya
keresztkorrelációjából becsülhető (estimate_clock_offset) — a fúzió
előtt az apply_offset igazítja össze a nézeteket.
"""

from __future__ import annotations

import math

from ..models.tracking import Ball, Frame, Match, PlayerPosition

# Két nézet észlelése ennél közelebb (méter) ugyanaz a játékos.
FUSE_RADIUS_M = 1.5
# A fúziós track-folytonosság sugara (az előző kockabeli pozícióhoz).
TRACK_CONTINUITY_M = 2.0


def _fuse_players(views: list[list[PlayerPosition]]) -> list[dict]:
    """Egy kockányi játékos-észlelés egyesítése nézetek közt.

    Mohó klaszterezés: az első nézet észleléseihez hozzávesszük a többi
    nézet azonos-csapatú, FUSE_RADIUS_M-en belüli észlelését; a klaszter
    pozíciója az átlag. Visszatérés: [{"x","y","team","role","n_views"}].
    """
    clusters: list[dict] = []
    for view in views:
        for p in view:
            best = None
            for c in clusters:
                if c["team"] != p.team:
                    continue
                d = math.hypot(c["x"] - p.x, c["y"] - p.y)
                if d <= FUSE_RADIUS_M and (best is None or d < best[1]):
                    best = (c, d)
            if best is None:
                clusters.append({"x": p.x, "y": p.y, "team": p.team,
                                 "role": p.role, "n_views": 1})
            else:
                c = best[0]
                n = c["n_views"]
                c["x"] = (c["x"] * n + p.x) / (n + 1)
                c["y"] = (c["y"] * n + p.y) / (n + 1)
                c["n_views"] = n + 1
                if c["role"] is None and p.role is not None:
                    c["role"] = p.role
    return clusters


def fuse_matches(views: list[Match]) -> Match:
    """Több, közös órajelű nézet egyesítése egyetlen Match-be.

    A kimeneti track-azonosítók a fúzió sajátjai: kockáról kockára az
    előző kocka legközelebbi (TRACK_CONTINUITY_M-en belüli, azonos
    csapatú) fúziós trackjét folytatjuk, különben új azonosítót nyitunk.
    A meta az első nézeté.
    """
    if not views:
        raise ValueError("legalább egy nézet kell")
    n_frames = max(len(v.frames) for v in views)
    out_frames: list[Frame] = []
    prev: list[tuple[int, float, float, object]] = []  # (tid, x, y, team)
    next_tid = 1

    for i in range(n_frames):
        per_view = [v.frames[i].players if i < len(v.frames) else []
                    for v in views]
        clusters = _fuse_players(per_view)

        players: list[PlayerPosition] = []
        used_prev: set[int] = set()
        new_prev: list[tuple[int, float, float, object]] = []
        for c in clusters:
            best = None
            for (tid, px, py, pteam) in prev:
                if pteam != c["team"] or tid in used_prev:
                    continue
                d = math.hypot(px - c["x"], py - c["y"])
                if d <= TRACK_CONTINUITY_M and (best is None or d < best[1]):
                    best = ((tid, px, py, pteam), d)
            if best is None:
                tid = next_tid
                next_tid += 1
            else:
                tid = best[0][0]
                used_prev.add(tid)
            players.append(PlayerPosition(
                track_id=tid, team=c["team"], x=round(c["x"], 3),
                y=round(c["y"], 3), role=c["role"]))
            new_prev.append((tid, c["x"], c["y"], c["team"]))
        prev = new_prev

        # Labda: a legnagyobb konfidenciájú nézet észlelése.
        ball: Ball | None = None
        for v in views:
            b = v.frames[i].ball if i < len(v.frames) else None
            if b is not None and (ball is None
                                  or b.confidence > ball.confidence):
                ball = b
        out_frames.append(Frame(t=i, players=players, ball=ball))

    return Match(meta=views[0].meta, frames=out_frames)


# Az eltolás-kereséshez legalább ennyi közös labda-mintás kocka kell.
SYNC_MIN_OVERLAP = 25


def estimate_clock_offset(a: Match, b: Match,
                          max_offset: int = 250) -> int | None:
    """A b nézet órajel-eltolása az a nézethez képest (kockában).

    A két nézet UGYANAZT a labdát látja — a labda-pálya a legjobb közös
    jel. Minden jelölt eltolásra a mindkét nézetben látott labda-pozíciók
    átlagos távolságát számoljuk; a legkisebb átlagú eltolás nyer.
    Pozitív érték: a b nézet KÉSIK (b[t] az a[t - offset]-tel esik egybe).

    None, ha nincs elég közös labda-minta egyik eltolásnál sem.
    """
    balls_a = {f.t: f.ball for f in a.frames if f.ball is not None}
    balls_b = {f.t: f.ball for f in b.frames if f.ball is not None}
    if not balls_a or not balls_b:
        return None

    best_offset = None
    best_score = None
    for off in range(-max_offset, max_offset + 1):
        dists = []
        for t_b, ball_b in balls_b.items():
            ball_a = balls_a.get(t_b - off)
            if ball_a is None:
                continue
            dists.append(math.hypot(ball_a.x - ball_b.x,
                                    ball_a.y - ball_b.y))
        if len(dists) < SYNC_MIN_OVERLAP:
            continue
        score = sum(dists) / len(dists)
        if best_score is None or score < best_score:
            best_score = score
            best_offset = off
    return best_offset


def apply_offset(match: Match, offset: int) -> Match:
    """A nézet kockáinak eltolása -offset-tel (az összeigazításhoz).

    Az estimate_clock_offset(a, b) eredményével: apply_offset(b, offset)
    után a b nézet t-tengelye az a nézetével közös. A negatív időre
    csúszó kockák kiesnek.
    """
    frames = []
    for f in match.frames:
        t = f.t - offset
        if t < 0:
            continue
        frames.append(Frame(t=t, players=f.players, ball=f.ball))
    frames.sort(key=lambda f: f.t)
    return Match(meta=match.meta, frames=frames)
