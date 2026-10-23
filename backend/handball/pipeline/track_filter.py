"""
[Játékos-pálya simítás] — a detektálási remegés (jitter) csökkentése.

A valódi felvételen a játékos doboza kockáról kockára kissé ugrál (a detektor
zaja), ezért a pálya-pozíció is remeg. Ennek két káros hatása van:
- a MEGTETT TÁV / SEBESSÉG statisztika felfelé torzul (a remegés is "futás"),
- a felülnézeti lejátszás vibrál.

A megoldás egy ÓVATOS, középre igazított mozgóátlag (alap: 3 kocka), ami csak a
MÉRT pozíciókat simítja, és NEM átlagol össze nem összetartozó szakaszokat:
- track-enként dolgozik (stabil ByteTrack id-k),
- a hosszú kihagyás (max_gap-nél nagyobb) szakaszhatár — két külön látási
  periódust nem kötünk össze,
- a becsült (ESTIMATED) pozíciókhoz nem nyúlunk (azok már modellből jönnek).

A kis ablak szándékos: az éles irányváltás (csel) valódi jel — azt nem szabad
elmosni. Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

from ..models.tracking import Match, PositionSource

DEFAULT_WINDOW = 3      # középre igazított ablak (kocka) — óvatos simítás
DEFAULT_MAX_GAP = 10    # ennél nagyobb kihagyás szakaszhatár (nem kötjük össze)


def smooth_player_tracks(match: Match, window: int = DEFAULT_WINDOW,
                         max_gap: int = DEFAULT_MAX_GAP) -> int:
    """A mért játékos-pozíciók remegésének simítása. Visszaadja a módosított
    pozíciók számát.

    Track-enként összegyűjtjük a mért pozíciókat, folytonos szakaszokra bontjuk
    (max_gap-nél nagyobb kihagyásnál vágunk), és szakaszonként középre igazított
    mozgóátlagot számolunk. CSAK a teljes ablakú belső pontokat simítjuk — a
    szakasz szélső pontjai érintetlenek (az aszimmetrikus átlag a széleken
    befelé húzna, ami egyenes mozgásnál is torzítana).
    """
    if window < 3 or window % 2 == 0:
        raise ValueError("window: legalább 3, páratlan")
    half = window // 2

    # track_id -> [(frame_index, PlayerPosition)] a mért pozíciókról.
    by_track: dict[int, list] = {}
    for fi, frame in enumerate(match.frames):
        for p in frame.players:
            if p.source == PositionSource.MEASURED:
                by_track.setdefault(p.track_id, []).append((fi, p))

    changed = 0
    for entries in by_track.values():
        # Folytonos szakaszok (a nagy kihagyás szakaszhatár).
        segments: list[list] = [[]]
        for item in entries:
            if segments[-1] and item[0] - segments[-1][-1][0] > max_gap:
                segments.append([])
            segments[-1].append(item)

        for seg in segments:
            if len(seg) < 3:
                continue  # 1-2 pontot nincs mivel simítani
            xs = [p.x for _, p in seg]
            ys = [p.y for _, p in seg]
            # csak a TELJES ablakú belső pontok — a szélsők érintetlenek
            for i in range(half, len(seg) - half):
                _, p = seg[i]
                nx = sum(xs[i - half:i + half + 1]) / window
                ny = sum(ys[i - half:i + half + 1]) / window
                if nx != p.x or ny != p.y:
                    p.x = nx
                    p.y = ny
                    changed += 1
    return changed


# --- Kispad- és néző-szűrés ---------------------------------------------
# A pálya-régió (roi.CourtRegion) tűréssávot hagy a vonalon kívül, mert a
# játékos néha kilép (partdobás, cserezóna). A csarnokban viszont pont
# ebben a sávban ül a KISPAD, és mögötte a nézők első sora — a felhasználó
# felvételén a cserepad székei közvetlenül az oldalvonal mellett vannak.
# Ezek a "játékosok" végig egy helyben ülnek: ez a jel különbözteti meg
# őket a valóban kilépő játékostól.
BENCH_OUT_MARGIN_M = 0.3    # ennyivel a vonalon kívül már "kint"
BENCH_OUT_SHARE = 0.8       # a track kockáinak ennyi része legyen kint
BENCH_SPREAD_M = 3.0        # ...és ekkora dobozban férjen el a mozgása
BENCH_MIN_FRAMES = 50       # ennyi mért kocka kell az ítélethez


def drop_bench_tracks(match: Match,
                      out_margin_m: float = BENCH_OUT_MARGIN_M,
                      out_share: float = BENCH_OUT_SHARE,
                      spread_m: float = BENCH_SPREAD_M,
                      min_frames: int = BENCH_MIN_FRAMES) -> dict:
    """A pályán KÍVÜL ÜLŐ (kispad, néző) track-ek eldobása.

    Egy track akkor kispad/néző, ha
      - a mért kockáinak legalább `out_share` része a pálya vonalain
        KÍVÜL van (`out_margin_m`-nél nagyobb kilógással), ÉS
      - a mozgása belefér egy `spread_m` oldalú dobozba (ül vagy áll),
    és van róla legalább `min_frames` mért kocka. A rövid ideig kint
    lévő, de MOZGÓ játékos (partdobás, csere) így megmarad.

    A talált track-ek pozíciói minden kockából kikerülnek — a
    létszám-, formáció- és fal-mérések különben a padot is falnak
    néznék.

    Visszatérés: {"tracks": [track_id, ...], "removed": pozíció-szám}.
    """
    from .calibration import COURT_LENGTH_M, COURT_WIDTH_M

    by_track: dict[int, list] = {}
    for frame in match.frames:
        for p in frame.players:
            by_track.setdefault(p.track_id, []).append(p)

    bench: set = set()
    for tid, pts in by_track.items():
        measured = [p for p in pts if p.source == PositionSource.MEASURED]
        if len(measured) < min_frames:
            continue
        outside = sum(
            1 for p in measured
            if (p.x < -out_margin_m or p.x > COURT_LENGTH_M + out_margin_m
                or p.y < -out_margin_m or p.y > COURT_WIDTH_M + out_margin_m))
        if outside < out_share * len(measured):
            continue
        xs = [p.x for p in measured]
        ys = [p.y for p in measured]
        if (max(xs) - min(xs) <= spread_m
                and max(ys) - min(ys) <= spread_m):
            bench.add(tid)

    removed = 0
    if bench:
        for frame in match.frames:
            keep = [p for p in frame.players if p.track_id not in bench]
            removed += len(frame.players) - len(keep)
            frame.players = keep
    return {"tracks": sorted(bench), "removed": removed}
