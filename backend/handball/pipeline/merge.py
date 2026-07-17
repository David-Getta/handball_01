"""Meccs-szakaszok összefűzése — pl. a KÉT FÉLIDŐ egy meccsé.

A gyakorlatban a két félidőt külön videóból (vagy külön szakaszként) dolgozzuk
fel; az edzőnek viszont a TELJES meccsről kell statisztika, esemény-lista és
felderítés. Az összefűzés:
 - a képkocka-időket eltolja (a 2. szakasz az 1. után folytatódik),
 - a track-azonosítókat is eltolja (a követő mindkét szakaszban 1-től számoz,
   de a "7-es" az első félidőben NEM biztos, hogy ugyanaz, mint a másodikban
   — az összemosás hamis statisztikát adna),
 - a videó-hivatkozást elengedi (két külön fájlból nem lehet egyben
   lejátszani) — KIVÉVE, ha minden szakasz UGYANABBÓL a videóból jött
   (megszakadt feldolgozás folytatása): akkor a lejátszás megmarad,
 - ha az utolsó szakasz maga is részleges, az összefűzött meccs is az
   (partial + next_start_frame öröklődik) — tovább folytatható.
"""

from __future__ import annotations

from dataclasses import replace

from ..models.tracking import Ball, Frame, Match, MatchMeta


def merge_matches(parts: list[Match], match_id: str,
                  home_team: str | None = None,
                  away_team: str | None = None) -> Match:
    """Több feldolgozott szakaszból (sorrendben!) egyetlen Match-et készít.

    A metaadatok az ELSŐ szakaszból jönnek (fps, felbontás); a csapatnevek
    felülbírálhatók. Minden frame-et és játékost MÁSOLUNK, hogy az eredeti
    meccsek érintetlenek maradjanak.
    """
    if not parts:
        raise ValueError("legalább egy szakasz kell az összefűzéshez")
    first = parts[0]
    # Ha minden szakasz ugyanabból a videófájlból jött (azonos stride-dal) —
    # tipikusan egy megszakadt feldolgozás folytatása —, a lejátszás-
    # hivatkozás megtartható; különben két külön fájl, és elengedjük.
    same_video = first.meta.video_path is not None and all(
        p.meta.video_path == first.meta.video_path
        and p.meta.stride == first.meta.stride for p in parts)
    meta = MatchMeta(
        match_id=match_id,
        home_team=home_team or first.meta.home_team,
        away_team=away_team or first.meta.away_team,
        fps=first.meta.fps,
        frame_width=first.meta.frame_width,
        frame_height=first.meta.frame_height,
        date=first.meta.date,
        video_path=first.meta.video_path if same_video else None,
        start_frame=first.meta.start_frame if same_video else 0,
        stride=first.meta.stride,
        # Az utolsó szakasz részlegessége öröklődik: ha a folytatás is
        # megszakadt, az összefűzött meccs is folytatható marad.
        partial=parts[-1].meta.partial,
        next_start_frame=parts[-1].meta.next_start_frame,
    )

    frames: list[Frame] = []
    t_offset = 0
    id_offset = 0
    for part in parts:
        max_id = 0
        for f in part.frames:
            players = [replace(p, track_id=p.track_id + id_offset)
                       for p in f.players]
            for p in f.players:
                if p.track_id > max_id:
                    max_id = p.track_id
            ball = Ball(x=f.ball.x, y=f.ball.y, confidence=f.ball.confidence) \
                if f.ball is not None else None
            frames.append(Frame(t=t_offset + f.t, players=players, ball=ball))
        t_offset = (frames[-1].t + 1) if frames else 0
        id_offset += max_id + 1
    return Match(meta=meta, frames=frames)
