"""
[C2] Track-összefűzés — a megszakadt követés automatikus helyreállítása.

A követés (ByteTrack) takarásnál/tömörülésnél elveszti a játékost, aki új
track_id-val tér vissza — az elemzésben így EGY emberből KETTŐ lesz. Ez a
modul a kész Match-en utólag összefűzi azokat a track-párokat, ahol a
folytonosság tér-időben egyértelmű:

- az egyik track MÉRT szakasza véget ér, a másiké röviddel később indul;
- ugyanaz a csapat;
- a két pont távolsága belefér a fizikailag lehetségesbe (max sebesség ×
  eltelt idő + ráhagyás);
- a MEGJELENÉSÜK (átlagos mezszín) nem mond ellent (ha ismert);
- és a párosítás KÖLCSÖNÖSEN a legjobb (mindkét fél első jelöltje a másik).

A küszöbök szándékosan óvatosak: a hamis összefűzés (két KÜLÖNBÖZŐ játékos
összeragasztása) rosszabb, mint a kihagyott — ami kimarad, azt a
mezszám-hozzárendelés még mindig összekötheti kézzel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..models.tracking import Match, PositionSource


@dataclass
class StitchConfig:
    """Az összefűzés küszöbei.

    - max_gap_s:      legfeljebb ekkora időbeli lyukat hidalunk át.
    - max_speed_ms:   ennyivel mozoghatott a játékos a lyuk alatt.
    - slack_m:        fix ráhagyás a detektálási zajra (méter).
    - max_color_dist: megjelenés-kapu — ha mindkét track átlag-mezszíne
                      ismert és a távolságuk (RGB euklideszi, 0..441)
                      ennél nagyobb, NEM fűzzük össze őket (azonos csapaton
                      belül is: kapus vs mezőnyjátékos, eltérő tónusok).
    - color_weight:   a színtávolság súlya a jelölt-pontszámban
                      (méter-egyenérték színegységenként) — két hasonló
                      tér-időbeli jelölt közül a hasonlóbb színű nyer.
    """
    max_gap_s: float = 2.0
    max_speed_ms: float = 7.0
    slack_m: float = 1.0
    max_color_dist: float = 90.0
    color_weight: float = 0.02


def _mean_colors(colors_by_track: dict | None) -> dict:
    """track_id → átlagszín (r, g, b). Üres/None bemenetre üres szótár."""
    out: dict = {}
    for tid, colors in (colors_by_track or {}).items():
        if not colors:
            continue
        n = len(colors)
        out[tid] = tuple(sum(c[i] for c in colors) / n for i in range(3))
    return out


def stitch_tracks(match: Match, config: StitchConfig | None = None,
                  colors_by_track: dict | None = None) -> int:
    """Megszakadt trackek összefűzése (helyben) — visszaadja, hány
    összefűzés történt. Csak MÉRT szakaszokra épít; az összefűzött track
    a KORÁBBI azonosítót viszi tovább (az elemzések egy játékost látnak).

    `colors_by_track` (opcionális): track_id → [mezszín-minták (r, g, b)]
    a feldolgozásból. Ha adott, a megjelenés is beleszól a döntésbe:
    nagyon eltérő színű trackek nem fűződnek össze, a hasonlóbb színű
    jelölt előnyt kap.
    """
    config = config or StitchConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    max_gap = max(1, round(config.max_gap_s * fps))
    mean_color = _mean_colors(colors_by_track)

    # Trackenként az első/utolsó MÉRT pont (t, x, y) + csapat.
    first: dict = {}
    last: dict = {}
    team_of: dict = {}
    for frame in match.frames:
        for p in frame.players:
            if p.source != PositionSource.MEASURED:
                continue
            team_of.setdefault(p.track_id, p.team)
            if p.track_id not in first:
                first[p.track_id] = (frame.t, p.x, p.y)
            last[p.track_id] = (frame.t, p.x, p.y)

    # Jelölt-párok: a VÉGZŐDŐ track (a) és a KÉSŐBB INDULÓ track (b).
    candidates = []
    for a, (ta, xa, ya) in last.items():
        for b, (tb, xb, yb) in first.items():
            if a == b or team_of.get(a) != team_of.get(b):
                continue
            gap = tb - ta
            if gap <= 0 or gap > max_gap:
                continue
            dist = math.hypot(xb - xa, yb - ya)
            allowed = config.max_speed_ms * (gap / fps) + config.slack_m
            if dist > allowed:
                continue
            # Megjelenés-kapu és -súly: csak ha MINDKÉT track színe ismert
            # (ismeretlen színnél a tér-időbeli logika dönt, mint eddig).
            color_pen = 0.0
            ca, cb = mean_color.get(a), mean_color.get(b)
            if ca is not None and cb is not None:
                cdist = math.dist(ca, cb)
                if cdist > config.max_color_dist:
                    continue  # más mez — nem ugyanaz a játékos
                color_pen = config.color_weight * cdist
            candidates.append((dist + gap / fps + color_pen, a, b))  # kisebb = jobb

    # Kölcsönösen legjobb párok, mohón (a legjobb pontszámtól felfelé):
    # egy track csak EGYSZER lehet előd és egyszer utód.
    candidates.sort()
    used_pred: set = set()
    used_succ: set = set()
    rename: dict = {}  # b -> a (az utód a korábbi azonosítót kapja)
    for (_, a, b) in candidates:
        if a in used_pred or b in used_succ:
            continue
        used_pred.add(a)
        used_succ.add(b)
        rename[b] = a

    if not rename:
        return 0

    # Láncok feloldása (a->b->c): mindenki a lánc gyökerére képződik.
    def root(tid: int) -> int:
        seen = set()
        while tid in rename and tid not in seen:
            seen.add(tid)
            tid = rename[tid]
        return tid

    # Átcímkézés + ütközés-feloldás: ha egy kockán az előd BECSÜLT és az
    # utód MÉRT pozíciója is jelen van (a becslő kitöltötte a lyukat),
    # a mért marad, a becsült duplikátum kiesik.
    for frame in match.frames:
        for p in frame.players:
            if p.track_id in rename:
                p.track_id = root(p.track_id)
        by_id: dict = {}
        keep = []
        for p in frame.players:
            other = by_id.get(p.track_id)
            if other is None:
                by_id[p.track_id] = p
                keep.append(p)
            else:
                # Duplikátum: a mért győz a becsült felett.
                if (other.source != PositionSource.MEASURED
                        and p.source == PositionSource.MEASURED):
                    keep[keep.index(other)] = p
                    by_id[p.track_id] = p
        frame.players = keep
    return len(rename)
