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
from typing import Optional

from ..models.tracking import (Ball, Frame, Match, MatchMeta,
                               PositionSource, Team)


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
        # A forrásvideó hossza csak akkor öröklődik, ha tényleg ugyanaz
        # a fájl — ebből számol a minőség-jelentés lefedettséget, és két
        # külön videó összefűzésénél az szám félrevezető lenne.
        video_seconds=(first.meta.video_seconds if same_video else None),
        # Kalibráltság: csak akkor állítjuk, ha MINDEN szakasz egyetért
        # (különben nem tudjuk, mire vonatkozna az állítás).
        calibrated=(first.meta.calibrated
                    if all(p.meta.calibrated == first.meta.calibrated
                           for p in parts) else None),
    )

    frames: list[Frame] = []
    t_offset = 0
    id_offset = 0
    # FORRÁS-TÉRKÉP: melyik játékidő melyik fájl melyik kép-indexén
    # van. Enélkül az összefűzött meccsből nem lehetne klipet vágni —
    # a `video_path` üres, és a klipvágás azt mondaná, hogy "a videó
    # nem érhető el", ami félrevezető: a fájl megvan, csak több van
    # belőle.
    szakaszok: list = []
    # KÉZI JAVÍTÁSOK a szakaszokból. Aki hat klipben kijavította a
    # felismerés nyolc tévedését, az EMBERI munkát végzett — az
    # összefűzés némán eldobta volna, és az összerakott meccs megint
    # rossz eredményt mutatna. A javítás ideje a szakasz eltolásával
    # együtt mozog, különben egy MÁSIK esemény típusát írná át.
    javitasok: list = []
    for part in parts:
        max_id = 0
        szakasz_kezd = t_offset
        for f in part.frames:
            players = [replace(p, track_id=p.track_id + id_offset)
                       for p in f.players]
            for p in f.players:
                if p.track_id > max_id:
                    max_id = p.track_id
            ball = Ball(x=f.ball.x, y=f.ball.y, confidence=f.ball.confidence) \
                if f.ball is not None else None
            frames.append(Frame(t=t_offset + f.t, players=players, ball=ball))
        uj_offset = (frames[-1].t + 1) if frames else 0
        if part.meta.video_path and uj_offset > szakasz_kezd:
            szakaszok.append({
                "t_from": szakasz_kezd,
                "t_to": uj_offset,          # kizárólagos
                "video_path": part.meta.video_path,
                # A szakaszon BELÜLI t-hez tartozó kép-index:
                # start_frame + (t - t_from) * stride.
                "start_frame": part.meta.start_frame or 0,
                "stride": part.meta.stride or 1,
            })
        for ov in (getattr(part.meta, "event_overrides", None) or []):
            if not isinstance(ov, dict):
                continue
            try:
                eltolt = dict(ov)
                eltolt["t"] = int(ov["t"]) + szakasz_kezd
            except (KeyError, TypeError, ValueError):
                continue  # rossz alakú javítás: kihagyjuk, nem hiba
            # A lövő track-azonosítója is eltolódik — enélkül a kézzel
            # felvett gól egy MÁSIK emberhez kerülne.
            if ov.get("player_id") is not None:
                try:
                    eltolt["player_id"] = int(ov["player_id"]) + id_offset
                except (TypeError, ValueError):
                    eltolt.pop("player_id", None)
            javitasok.append(eltolt)
        t_offset = uj_offset
        id_offset += max_id + 1
    meta.source_segments = szakaszok
    meta.event_overrides = javitasok
    meta.merged_from = [p.meta.match_id for p in parts]
    ki = Match(meta=meta, frames=frames)
    # TÉRFÉLCSERE a szakasz-határokon. Egy videón BELÜL a feldolgozás
    # felismeri a szünetet és tükrözi a második félidőt — de a
    # darabokban felvett meccsnél a csere a DARABOK KÖZÖTT van, és a
    # 2. félidő darabja önmagában normalizálatlan. Enélkül a lövés-
    # felismerés a 2. félidő MINDEN gólját a rossz csapathoz írná: az
    # irány-szabály (attacks_toward_x) az egész meccsre egy.
    _normalize_segment_sides(ki)
    return ki


# A szakasz-határos térfélcsere ellenőrző ablaka: ennyi (valós)
# másodpercet nézünk a határ két oldalán. IDŐTARTAM, tehát
# másodpercben — a kockaszámot a meccs fps-éből számoljuk.
SEG_SWAP_WINDOW_S = 120.0
# Ennyi mért pozíció alatt nem döntünk: a tükrözés rossz irányba is
# üthet, és egy bizonytalan tükrözés rosszabb, mint a kimondott
# bizonytalanság.
SEG_SWAP_MIN_SAMPLES = 50


def _centroid_x_window(frames: list, team: Team, t_from: int,
                       t_to: int) -> tuple[Optional[float], int]:
    """A csapat mért pozícióinak átlagos x-e és darabszáma [t_from, t_to)."""
    total = 0.0
    n = 0
    for f in frames:
        if not (t_from <= f.t < t_to):
            continue
        for p in f.players:
            if p.team == team and p.source == PositionSource.MEASURED:
                total += p.x
                n += 1
    return (total / n if n else None), n


def _normalize_segment_sides(match: Match) -> None:
    """A szakasz-határokon átforduló térfelek tükrözése helyben.

    Minden belső határnál a HAZAI és a VENDÉG súlypontját hasonlítjuk a
    határ előtti és utáni ablakban (a halftime.detect_side_swap
    szabályával: mindkét csapat a felező MÁSIK oldalára került,
    legalább SWAP_MIN_SHIFT_M-rel). Ha fordulás van, a szakaszt — és
    minden utána következőt az ESETLEGES következő fordulásig —
    tükrözzük (x→L−x, y→W−y). A döntés szakaszonként a
    `source_segments` bejegyzésbe kerül ("mirrored": True/False/None
    — None = kevés minta, nem döntöttünk).

    A klip-vágást nem érinti: a forrás-térkép kép-indexei a VIDEÓRA
    mutatnak, a tükrözés csak a pálya-koordinátákat fordítja.
    """
    from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
    from .halftime import SWAP_MIN_SHIFT_M

    szakaszok = getattr(match.meta, "source_segments", None) or []
    if len(szakaszok) < 2 or not match.frames:
        return
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    ablak = round(SEG_SWAP_WINDOW_S * fps)
    mid = COURT_LENGTH_M / 2.0

    # Görgetett állapot: az aktuális szakasz tükrözve van-e az ELSŐHÖZ
    # képest. Egy fordulás után minden későbbi szakasz fordítva jön,
    # amíg egy újabb fordulás vissza nem állítja.
    forditva = False
    szakaszok[0]["mirrored"] = False
    szakaszok[0]["mirror_decided"] = True
    for i in range(1, len(szakaszok)):
        elozo, ez = szakaszok[i - 1], szakaszok[i]
        hatar = ez["t_from"]
        fordult = None  # None = nem eldönthető
        atfordult = 0
        vizsgalt = 0
        for team in (Team.HOME, Team.AWAY):
            elott, n1 = _centroid_x_window(
                match.frames, team, max(elozo["t_from"], hatar - ablak),
                hatar)
            utan, n2 = _centroid_x_window(
                match.frames, team, hatar,
                min(ez["t_to"] or (match.frames[-1].t + 1),
                    hatar + ablak))
            if (elott is None or utan is None
                    or n1 < SEG_SWAP_MIN_SAMPLES
                    or n2 < SEG_SWAP_MIN_SAMPLES):
                continue
            # Az ELŐZŐ oldal már a normalizált képet mutatja (ha a
            # korábbi szakaszokat tükröztük, a frames-ben az van).
            vizsgalt += 1
            if ((elott - mid) * (utan - mid) < 0
                    and abs(elott - mid) >= SWAP_MIN_SHIFT_M
                    and abs(utan - mid) >= SWAP_MIN_SHIFT_M):
                atfordult += 1
        if vizsgalt > 0:
            fordult = atfordult == vizsgalt and atfordult > 0
        if fordult:
            forditva = not forditva
        # Eldönthetetlen határnál (kevés minta) az ÁLLAPOT öröklődik:
        # fordulásra nincs jel, tehát maradunk az eddigi irányban — és
        # ha az fordított volt, ezt a szakaszt is tükrözni kell,
        # különben épp itt csúszna szét a pálya.
        ez["mirrored"] = forditva
        ez["mirror_decided"] = fordult is not None
        if forditva:
            veg = ez["t_to"]
            for f in match.frames:
                if f.t < hatar or (veg is not None and f.t >= veg):
                    continue
                for p_ in f.players:
                    p_.x = COURT_LENGTH_M - p_.x
                    p_.y = COURT_WIDTH_M - p_.y
                if f.ball is not None:
                    f.ball.x = COURT_LENGTH_M - f.ball.x
                    f.ball.y = COURT_WIDTH_M - f.ball.y
