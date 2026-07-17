"""A meccs-összefűzés (két félidő → egy meccs) tesztjei."""
from handball.pipeline.merge import merge_matches
from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, Team,
)


def _part(match_id, n_frames, track_id):
    meta = MatchMeta(match_id=match_id, home_team="A", away_team="B", fps=8.0,
                     video_path=f"/tmp/{match_id}.mp4")
    frames = [
        Frame(t=i, players=[
            PlayerPosition(track_id=track_id, team=Team.HOME, x=1.0 * i, y=2.0),
        ], ball=Ball(x=20.0, y=10.0))
        for i in range(n_frames)
    ]
    return Match(meta=meta, frames=frames)


def test_merge_offsets_time_and_ids():
    a = _part("h1", 3, track_id=7)
    b = _part("h2", 2, track_id=7)
    m = merge_matches([a, b], "teljes")
    assert len(m.frames) == 5
    assert [f.t for f in m.frames] == [0, 1, 2, 3, 4]  # folytonos idő
    ids = {p.track_id for f in m.frames for p in f.players}
    assert len(ids) == 2  # a két "7-es" NEM mosódik össze


def test_merge_copies_do_not_alias_originals():
    a = _part("h1", 2, track_id=1)
    b = _part("h2", 2, track_id=1)
    m = merge_matches([a, b], "teljes")
    m.swap_teams()
    # az eredeti szakaszok érintetlenek
    assert a.frames[0].players[0].team == Team.HOME
    assert b.frames[0].players[0].team == Team.HOME


def test_merge_meta_and_video():
    a = _part("h1", 1, track_id=1)
    b = _part("h2", 1, track_id=1)
    m = merge_matches([a, b], "teljes", home_team="Deac", away_team="Szike")
    assert m.meta.match_id == "teljes"
    assert m.meta.home_team == "Deac" and m.meta.away_team == "Szike"
    assert m.meta.video_path is None  # nincs egyben lejátszható videó
    assert m.meta.fps == 8.0


def test_merge_same_video_keeps_playback():
    """Ha minden szakasz UGYANABBÓL a videóból jött (megszakadt feldolgozás
    folytatása), a lejátszás-hivatkozás és a kezdőkocka megmarad."""
    a = _part("resz", 3, track_id=1)
    b = _part("resz-folyt", 2, track_id=1)
    b.meta.video_path = a.meta.video_path  # ugyanaz a fájl
    b.meta.start_frame = 3
    m = merge_matches([a, b], "resz-teljes")
    assert m.meta.video_path == a.meta.video_path
    assert m.meta.start_frame == a.meta.start_frame
    assert m.meta.partial is False


def test_merge_inherits_partial_from_last_part():
    """Ha az utolsó szakasz maga is részleges (újra megszakadt), az
    összefűzött meccs is folytatható marad."""
    a = _part("resz", 3, track_id=1)
    b = _part("resz-folyt", 2, track_id=1)
    b.meta.video_path = a.meta.video_path
    b.meta.partial = True
    b.meta.next_start_frame = 5
    m = merge_matches([a, b], "resz-teljes")
    assert m.meta.partial is True
    assert m.meta.next_start_frame == 5
