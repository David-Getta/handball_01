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
