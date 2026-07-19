"""
Tesztek a videóklip-exportra (clips.py) — szintetikus mini-videóval.

Futtatás:
    python -m pytest tests/test_clips.py
"""

from __future__ import annotations

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest

from handball.models.tracking import Match, MatchMeta
from handball.pipeline.clips import export_event_clips


def _make_video(path, n_frames=200, fps=25.0, size=(320, 240)):
    """Kis teszt-videó: futó kockaszámmal, hogy legyen valódi tartalom."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    w = cv2.VideoWriter(str(path), fourcc, fps, size)
    for i in range(n_frames):
        img = np.full((size[1], size[0], 3), 30, np.uint8)
        cv2.putText(img, str(i), (40, 120), cv2.FONT_HERSHEY_SIMPLEX,
                    2.0, (255, 255, 255), 3)
        w.write(img)
    w.release()


def _match(video_path, fps=25.0, stride=1, start=0):
    return Match(
        meta=MatchMeta(match_id="t", home_team="Hazai", away_team="Vendég",
                       fps=fps / stride, video_path=str(video_path),
                       start_frame=start, stride=stride),
        frames=[])


def test_exports_selected_types_only(tmp_path):
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [
        {"t": 60, "type": "goal", "team": "home"},
        {"t": 120, "type": "shot", "team": "away"},
        {"t": 150, "type": "pass", "team": "home"},
    ]
    res = export_event_clips(m, events, {"goal"}, tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        names = z.namelist()
    assert len(names) == 1 and "gol" in names[0] and "Hazai" in names[0]

    res2 = export_event_clips(m, events, {"goal", "shot"}, tmp_path / "ki2")
    assert res2.count == 2


def test_clip_is_playable_and_window_correct(tmp_path):
    video = tmp_path / "meccs.mp4"
    _make_video(video, n_frames=400)
    # stride=2, start=100: a t=50 tracking-frame az eredeti 100+50*2=200. kockánál.
    m = _match(video, stride=2, start=100)
    res = export_event_clips(m, [{"t": 50, "type": "goal", "team": "away"}],
                             {"goal"}, tmp_path / "ki")
    clip = [p for p in (tmp_path / "ki").iterdir() if p.suffix == ".mp4"][0]
    cap = cv2.VideoCapture(str(clip))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    # Az ablak 5 mp előtte + 3 mp utána = 8 mp x 25 fps = ~200 kocka
    # (a videó végénél/elejénél vágva lehet rövidebb).
    assert 150 <= n <= 210, f"klip-hossz: {n} kocka"


def test_clips_near_video_edges_are_trimmed(tmp_path):
    video = tmp_path / "rovid.mp4"
    _make_video(video, n_frames=100)  # 4 mp-es videó
    m = _match(video)
    # Az esemény az elején: a klip a 0. kockától indul, nem dob hibát.
    res = export_event_clips(m, [{"t": 10, "type": "goal", "team": "home"}],
                             {"goal"}, tmp_path / "ki")
    assert res.count == 1


def test_missing_video_gives_clear_error(tmp_path):
    m = _match(tmp_path / "nincs.mp4")
    with pytest.raises(RuntimeError, match="nem érhető el"):
        export_event_clips(m, [{"t": 1, "type": "goal", "team": "home"}],
                           {"goal"}, tmp_path / "ki")


def test_no_matching_events_gives_clear_error(tmp_path):
    video = tmp_path / "meccs.mp4"
    _make_video(video, n_frames=50)
    m = _match(video)
    with pytest.raises(RuntimeError, match="Nem készült klip"):
        export_event_clips(m, [{"t": 5, "type": "pass", "team": "home"}],
                           {"goal"}, tmp_path / "ki")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        test_exports_selected_types_only(Path(d) / "a")
    print("Minden klip-teszt OK.")


def test_new_layer_types_get_hungarian_names(tmp_path):
    """Az új rétegek klip-típusai (hétméteres/időkérés/csere) magyar
    fájlnevet kapnak, és a szűrés rájuk is működik."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [
        {"t": 40, "type": "seven_meter", "team": "home"},
        {"t": 80, "type": "timeout", "team": "away"},
        {"t": 120, "type": "substitution", "team": "home"},
        {"t": 150, "type": "goal", "team": "home"},
    ]
    res = export_event_clips(m, events, {"seven_meter", "timeout",
                                         "substitution"}, tmp_path / "ki")
    assert res.count == 3
    with zipfile.ZipFile(res.zip_path) as z:
        names = " ".join(z.namelist())
    assert "hetmeteres" in names
    assert "idokeres" in names
    assert "csere" in names
    assert "gol" not in names  # a gól nem volt kérve


def test_note_clip_uses_label_in_filename(tmp_path):
    """A jegyzet-klip fájlnevében a jegyzet szövege szerepel (tisztítva)."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 60, "type": "note", "team": "home",
               "label": "szép indítás a szélre!"}]
    res = export_event_clips(m, events, {"note"}, tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        name = z.namelist()[0]
    assert "jegyzet" in name
    assert "szép_indítás" in name
    assert "!" not in name  # az írásjelek kimaradnak a fájlnévből


def test_top_shooter_clip_gets_hungarian_name(tmp_path):
    """A fő lövő klip-típus magyar fájlnevet kap (fo-lovo)."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 40, "type": "top_shooter", "team": "home"},
              {"t": 80, "type": "goal", "team": "home"}]
    res = export_event_clips(m, events, {"top_shooter"}, tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        names = " ".join(z.namelist())
    assert "fo-lovo" in names
    assert "gol" not in names
