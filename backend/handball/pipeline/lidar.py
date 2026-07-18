"""Lidar-bemenet előkészítése — pont-klaszterek és pozíció-finomítás.

Az arénarendszer utolsó lépcsője az 1-2 lidar: fénytől független,
cm-pontos geometria. A munkamegosztás (lásd docs/BROADCAST_AND_SENSORS):
a KAMERA adja az azonosságot (mez-szín, mezszám), a LIDAR a pontos
helyet. Ez a modul a lidar-oldal két, valódi szenzor nélkül is
építhető darabja:

1. cluster_points: a talajra vetített pontfelhő játékos-jelölt
   klaszterei (egyszerű, rács-gyorsított DBSCAN-szerű klaszterezés) —
   a lidar nyers kimenetéből (x, y pontok a pálya méter-terében)
   játékos-pozíciókat csinál, azonosság nélkül;
2. refine_with_lidar: a kamerás Match pozícióinak finomítása — minden
   kamerás játékost a hozzá legközelebbi (sugáron belüli) lidar-
   jelöltre igazítunk. Az azonosság a kameráé marad, a geometria a
   lidaré lesz.

A valódi szenzor-illesztéshez (pontfelhő-formátum, talaj-sík szűrés)
majd eszköz kell; a lánc többi része innen már kész.
"""

from __future__ import annotations

import math

from ..models.tracking import Frame, Match, PlayerPosition

# Klaszterezés: két pont ennél közelebb ugyanahhoz a jelölthöz tartozik,
# és legalább ennyi pont kell egy játékos-jelölthöz (zaj-szűrés).
CLUSTER_EPS_M = 0.5
CLUSTER_MIN_PTS = 5
# Finomítás: a kamerás pozíciót legfeljebb ekkora sugáron belüli
# lidar-jelölthöz igazítjuk.
REFINE_RADIUS_M = 1.0


def cluster_points(points: list[tuple], eps: float = CLUSTER_EPS_M,
                   min_pts: int = CLUSTER_MIN_PTS) -> list[dict]:
    """Játékos-jelölt klaszterek a talajra vetített (x, y) pontokból.

    Rács-gyorsított összevonás: a pontokat eps-méretű cellákba soroljuk,
    és a szomszédos cellák pontjait egy klaszterbe fűzzük (union-find).
    A min_pts alatti klaszter zaj. Visszatérés: [{"x","y","n"}] —
    a klaszter súlypontja és pontszáma, n szerint csökkenőben.
    """
    if not points:
        return []
    cell: dict[tuple, list[int]] = {}
    for i, (x, y) in enumerate(points):
        cell.setdefault((int(x // eps), int(y // eps)), []).append(i)

    parent = list(range(len(points)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for (cx, cy), idxs in cell.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                other = cell.get((cx + dx, cy + dy))
                if not other:
                    continue
                for i in idxs:
                    xi, yi = points[i]
                    for j in other:
                        if j <= i:
                            continue
                        xj, yj = points[j]
                        if math.hypot(xi - xj, yi - yj) <= eps:
                            union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(len(points)):
        groups.setdefault(find(i), []).append(i)

    out = []
    for idxs in groups.values():
        if len(idxs) < min_pts:
            continue
        xs = [points[i][0] for i in idxs]
        ys = [points[i][1] for i in idxs]
        out.append({"x": round(sum(xs) / len(xs), 3),
                    "y": round(sum(ys) / len(ys), 3), "n": len(idxs)})
    out.sort(key=lambda c: -c["n"])
    return out


def refine_with_lidar(match: Match,
                      candidates_by_t: dict[int, list[dict]],
                      radius: float = REFINE_RADIUS_M) -> Match:
    """A kamerás pozíciók finomítása a lidar-jelöltekkel.

    Minden kamerás játékost a hozzá legközelebbi, `radius`-on belüli
    lidar-jelölt pozíciójára igazítunk (egy jelölt egy játékoshoz).
    Ami kívül esik (nincs lidar-lefedettség), változatlan marad — a
    finomítás sosem ront. Az azonosság (track_id, csapat, szerep) a
    kameráé marad.
    """
    frames = []
    for f in match.frames:
        cands = list(candidates_by_t.get(f.t, []))
        used: set[int] = set()
        players = []
        for p in f.players:
            best = None
            for ci, c in enumerate(cands):
                if ci in used:
                    continue
                d = math.hypot(c["x"] - p.x, c["y"] - p.y)
                if d <= radius and (best is None or d < best[1]):
                    best = (ci, d)
            if best is None:
                players.append(p)
            else:
                used.add(best[0])
                c = cands[best[0]]
                players.append(PlayerPosition(
                    track_id=p.track_id, team=p.team, x=c["x"], y=c["y"],
                    source=p.source, confidence=p.confidence,
                    jersey_number=p.jersey_number, role=p.role))
        frames.append(Frame(t=f.t, players=players, ball=f.ball))
    return Match(meta=match.meta, frames=frames)
