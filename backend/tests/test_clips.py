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


def test_empty_net_clip_gets_hungarian_name(tmp_path):
    """A 7 a 6 klip-típus magyar fájlnevet kap (het-a-hat)."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 40, "type": "empty_net", "team": "home"},
              {"t": 80, "type": "goal", "team": "home"}]
    res = export_event_clips(m, events, {"empty_net"}, tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        names = " ".join(z.namelist())
    assert "het-a-hat" in names
    assert "gol" not in names


def test_turning_point_clip_gets_hungarian_name(tmp_path):
    """A fordulópont klip-típus magyar fájlnevet kap (fordulopont)."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 60, "type": "turning_point", "team": "home"}]
    res = export_event_clips(m, events, {"turning_point"}, tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        names = " ".join(z.namelist())
    assert "fordulopont" in names


def test_block_clip_gets_hungarian_name(tmp_path):
    """A blokk klip-típus magyar fájlnevet kap (blokk)."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 50, "type": "block", "team": "away"}]
    res = export_event_clips(m, events, {"block"}, tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        names = " ".join(z.namelist())
    assert "blokk" in names


def test_duplicate_moments_deduplicated_and_reported(tmp_path):
    """Az azonos pillanatra eső (több csomagban is szereplő) jelenet
    csak egyszer kerül a zip-be, és a skipped számolja a kimaradókat."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [
        {"t": 60, "type": "goal", "team": "home"},
        {"t": 60, "type": "key_moment", "team": "home",
         "label": "Vezetés-váltás"},
        {"t": 120, "type": "goal", "team": "away"},
    ]
    res = export_event_clips(m, events, {"goal", "key_moment"},
                             tmp_path / "ki")
    assert res.count == 2
    assert res.skipped == 1


def test_pivot_goal_clip_gets_hungarian_name(tmp_path):
    """A beállós gól klip-típus magyar fájlnevet kap (beallo-gol)."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 60, "type": "pivot_goal", "team": "home",
               "label": "beállós gól"}]
    res = export_event_clips(m, events, {"pivot_goal"}, tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        names = " ".join(z.namelist())
    assert "beallo-gol" in names


def test_breakthrough_clip_gets_hungarian_name(tmp_path):
    """A betörés klip-típus magyar fájlnevet kap (betores), a sáv a
    címkéből kerül a fájlnévbe."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 60, "type": "breakthrough", "team": "home",
               "label": "közép"}]
    res = export_event_clips(m, events, {"breakthrough"},
                             tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        names = " ".join(z.namelist())
    assert "betores" in names


def test_steal_clip_gets_hungarian_name(tmp_path):
    """A labdaszerzés klip-típus magyar fájlnevet kap (labdaszerzes)."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 60, "type": "steal", "team": "home",
               "label": "labdaszerzés"}]
    res = export_event_clips(m, events, {"steal"}, tmp_path / "ki")
    assert res.count == 1
    with zipfile.ZipFile(res.zip_path) as z:
        names = " ".join(z.namelist())
    assert "labdaszerzes" in names


def test_tobb_tipusnal_a_zip_mappakba_rendez(tmp_path):
    """Több csomagnál TÍPUS-MAPPÁK, egynél lapos a zip.

    A klip-képernyőn az edző egyszerre tizenhárom csomagot is kérhet;
    hatvan fájl egy lapos mappában kezelhetetlen, az edzésen pedig
    témánként kell levetíteni. Egyetlen típusnál viszont a mappa csak
    egy fölösleges kattintás lenne.
    """
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [
        {"t": 60, "type": "goal", "team": "home"},
        {"t": 120, "type": "block", "team": "away"},
    ]
    res = export_event_clips(m, events, {"goal", "block"}, tmp_path / "ki")
    with zipfile.ZipFile(res.zip_path) as z:
        names = z.namelist()
    assert sorted(n.split("/")[0] for n in names) == ["blokk", "gol"], names
    assert all("/" in n for n in names)

    # Egyetlen típus: marad a lapos alak.
    res1 = export_event_clips(m, events, {"goal"}, tmp_path / "ki1")
    with zipfile.ZipFile(res1.zip_path) as z:
        names1 = z.namelist()
    assert names1 and all("/" not in n for n in names1), names1


def test_a_plafon_tipusonkent_igazsagos_es_a_meccs_egeszet_lefedi():
    """A MAX_CLIPS plafon nem az elejéről vág.

    A korábbi `picked[:MAX_CLIPS]` időrendben csonkolt: aki sok
    csomagot kért egyszerre, a meccs ELSŐ harmadát kapta meg, és a
    ritka csomagok (fordulópont) simán kimaradtak, mert a gólok
    elvitték a keretet. Ez néma hiba: a zip tele van klippel, csak épp
    nem arról, amit az edző keresett.
    """
    from handball.pipeline.clips import MAX_CLIPS, _fair_cap

    def field(e, name):
        return e[name]

    events = ([{"t": i, "type": "goal"} for i in range(100)]
              + [{"t": i * 40, "type": "turning_point"} for i in range(3)]
              + [{"t": i * 5, "type": "block"} for i in range(20)])
    events.sort(key=lambda e: e["t"])
    out = _fair_cap(events, field)

    assert len(out) == MAX_CLIPS
    tipusok = {e["type"] for e in out}
    # A ritka típus TELJES egészében benne van — ez a lényeg.
    assert tipusok == {"goal", "turning_point", "block"}
    assert sum(1 for e in out if e["type"] == "turning_point") == 3
    assert sum(1 for e in out if e["type"] == "block") == 20
    # A gólok a meccs EGÉSZÉBŐL jönnek, nem az első hatvanból.
    golok = [e["t"] for e in out if e["type"] == "goal"]
    assert max(golok) > 90, golok
    # Időrendben marad (a fájlnevek sorszáma így követi a meccset).
    assert [e["t"] for e in out] == sorted(e["t"] for e in out)


def test_a_plafon_alatt_semmi_nem_valtozik():
    """Plafon alatt a lista érintetlen — a mintavétel csak akkor lép be,
    ha tényleg nem fér bele minden."""
    from handball.pipeline.clips import _fair_cap

    def field(e, name):
        return e[name]

    events = [{"t": i, "type": "goal"} for i in range(10)]
    assert _fair_cap(events, field) == events


def test_a_neman_ures_csomagokat_megnevezzuk(tmp_path):
    """Aki hat csomagot kér és egy zip-et kap, tudja meg, mihez nem
    volt jelenet.

    A néma semmi félrevezet: az edző nem tudja eldönteni, hogy az adott
    csomaghoz tényleg nem volt jelenet, vagy elromlott valami.
    """
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 60, "type": "goal", "team": "home"}]
    res = export_event_clips(m, events, {"goal", "block", "big_save"},
                             tmp_path / "ki")
    assert res.count == 1
    assert res.by_type == {"gol": 1}
    # A két kért, de üres csomag MAGYAR néven jelenik meg.
    assert res.empty == ["blokk", "nagy-vedes"], res.empty


def test_minden_csomag_adott_jelenetet(tmp_path):
    """Ha mindegyik kért típushoz volt jelenet, az `empty` üres —
    a jelzés csak akkor ér valamit, ha ritka."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match(video)
    events = [{"t": 60, "type": "goal", "team": "home"},
              {"t": 120, "type": "block", "team": "away"}]
    res = export_event_clips(m, events, {"goal", "block"}, tmp_path / "ki")
    assert res.empty == []
    assert res.by_type == {"gol": 1, "blokk": 1}
# ---- Mezszám-szűrés: a játékos SAJÁT válogatása -----------------------


def _match_mezekkel(video_path):
    """Meccs két emberrel: a 7-es (track 1) és a 9-es (track 2).

    A klip-motor a track_id-ből (esemény player_id) számol mezszámot,
    tehát a keretek KELLENEK — mezszám nélküli meccsen a szűrés némán
    mindent kidobna.
    """
    from handball.models.tracking import Frame, PlayerPosition, Team

    m = _match(video_path)
    m.frames = [
        Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=10.0,
                   jersey_number=7),
            PlayerPosition(track_id=2, team=Team.HOME, x=20.0, y=10.0,
                   jersey_number=9),
        ], ball=None)
        for i in range(3)
    ]
    return m


def test_a_klip_egy_jatekosra_szukitheto(tmp_path):
    """A #7 a SAJÁT gólvideóját kéri.

    Klip-válogatás mezszám nélkül azt jelenti, hogy a játékos a
    tizennyolc emberes csapatvideóból keresi ki magát — az edzés előtti
    öt percben ez nem történik meg.
    """
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match_mezekkel(video)
    events = [
        {"t": 60, "type": "goal", "team": "home", "player_id": 1},
        {"t": 120, "type": "goal", "team": "home", "player_id": 2},
    ]
    mind = export_event_clips(m, events, {"goal"}, tmp_path / "mind")
    assert mind.count == 2
    assert mind.jerseys == []

    hetes = export_event_clips(m, events, {"goal"}, tmp_path / "hetes",
                               jerseys={7})
    assert hetes.count == 1
    assert hetes.jerseys == [7]


def test_tobb_mezszam_egyszerre_kerheto(tmp_path):
    """A szélső páros két embere egy csomagban — az edző így ül le
    velük négyszemközt."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match_mezekkel(video)
    events = [{"t": 60, "type": "goal", "team": "home", "player_id": 1},
              {"t": 120, "type": "goal", "team": "home", "player_id": 2}]
    res = export_event_clips(m, events, {"goal"}, tmp_path / "ki",
                             jerseys={7, 9})
    assert res.count == 2 and res.jerseys == [7, 9]


def test_az_ures_mezszam_lista_az_egesz_csapatot_jelenti(tmp_path):
    """ŐR: a szűrés HIÁNYA nem szűkíthet.

    Ha az üres lista véletlenül "senki"-t jelentene, a képernyő minden
    vágása üres zip lenne — és ez pont az a hibafajta, ami némán megy
    át a teszteken, mert a hívók külön adják meg a mezszámot.
    """
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match_mezekkel(video)
    events = [{"t": 60, "type": "goal", "team": "home", "player_id": 1}]
    for ures in (None, set(), []):
        res = export_event_clips(m, events, {"goal"},
                                 tmp_path / f"ki{ures}", jerseys=ures)
        assert res.count == 1, ures


def test_az_ismeretlen_mezszam_megmondja_miert_nincs_klip(tmp_path):
    """A #23-hoz nincs jelenet — ez NEM hiba, de ki kell mondani.

    A néma "nem készült klip" itt elromlott programnak látszana, pedig
    csak a mezszám nincs kiosztva vagy nincs ilyen eseménye.
    """
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match_mezekkel(video)
    events = [{"t": 60, "type": "goal", "team": "home", "player_id": 1}]
    with pytest.raises(RuntimeError) as hiba:
        export_event_clips(m, events, {"goal"}, tmp_path / "ki",
                           jerseys={23})
    uzenet = str(hiba.value)
    assert "#23" in uzenet
    assert "mezszám" in uzenet
def test_tobb_jatekosnal_mindenki_sajat_mappat_kap(tmp_path):
    """Az edző három emberrel KÜLÖN-KÜLÖN ül le.

    Egy összekevert zip-ből minden beszélgetés előtt újra kellene
    válogatnia — a mappa itt nem díszítés, hanem a munkamenet.
    """
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match_mezekkel(video)
    events = [{"t": 60, "type": "goal", "team": "home", "player_id": 1},
              {"t": 120, "type": "goal", "team": "home", "player_id": 2}]
    res = export_event_clips(m, events, {"goal"}, tmp_path / "ki",
                             jerseys={7, 9})
    with zipfile.ZipFile(res.zip_path) as z:
        nevek = z.namelist()
    assert len(nevek) == 2
    assert sorted(n.split("/")[0] for n in nevek) == ["#7", "#9"]


def test_egy_jatekosnal_nincs_folosleges_mappa(tmp_path):
    """EGY kijelölt embernél a mappa csak egy kattintás lenne — a zip
    marad lapos, ahogy szűrés nélkül is."""
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match_mezekkel(video)
    events = [{"t": 60, "type": "goal", "team": "home", "player_id": 1}]
    res = export_event_clips(m, events, {"goal"}, tmp_path / "ki",
                             jerseys={7})
    with zipfile.ZipFile(res.zip_path) as z:
        nevek = z.namelist()
    assert nevek and "/" not in nevek[0], nevek


def test_a_jatekos_es_a_tipus_mappa_egymasba_ep(tmp_path):
    """Két játékos × két csomag: a játékos a KÜLSŐ mappa.

    Az edző emberenként készül, nem témánként — a "#7/gol" úton a
    beszélgetés anyaga egyben van, a "gol/#7" úton szét.
    """
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    m = _match_mezekkel(video)
    events = [{"t": 40, "type": "goal", "team": "home", "player_id": 1},
              {"t": 90, "type": "block", "team": "home", "player_id": 2}]
    res = export_event_clips(m, events, {"goal", "block"}, tmp_path / "ki",
                             jerseys={7, 9})
    with zipfile.ZipFile(res.zip_path) as z:
        nevek = sorted(z.namelist())
    assert nevek[0].startswith("#7/gol/"), nevek
    assert nevek[1].startswith("#9/blokk/"), nevek
def test_a_plafon_a_jatekosok_kozt_is_igazsagosan_oszlik(tmp_path):
    """A sokat szereplő ember NE vigye el a másik keretét.

    Ez ugyanaz a néma igazságtalanság, mint a típusoknál, egy szinttel
    feljebb: a zip tele van klippel, csak épp a #9 mappájában kettő
    van, mert a #7-nek nyolcvan jelenete volt. Az edző így pont azzal
    a játékossal nem tud leülni, akiről a legkevesebb anyaga van.
    """
    from handball.pipeline.clips import MAX_CLIPS

    video = tmp_path / "meccs.mp4"
    _make_video(video, n_frames=4000)
    m = _match_mezekkel(video)
    # A #7-nek sokkal több jelenete van, mint a #9-nek — de a plafon
    # fölött mindkettőnek jutnia kell.
    events = [{"t": 20 + i, "type": "goal", "team": "home", "player_id": 1}
              for i in range(0, MAX_CLIPS * 4, 2)]
    events += [{"t": 2000 + i, "type": "goal", "team": "home",
                "player_id": 2} for i in range(0, MAX_CLIPS * 2, 2)]

    res = export_event_clips(m, events, {"goal"}, tmp_path / "ki",
                             jerseys={7, 9})
    with zipfile.ZipFile(res.zip_path) as z:
        nevek = z.namelist()
    hetes = [n for n in nevek if n.startswith("#7/")]
    kilences = [n for n in nevek if n.startswith("#9/")]
    assert hetes and kilences, nevek[:5]
    # Nagyjából fele-fele: a bővebb ember legfeljebb kétszer annyit
    # vihet, mint a szűkebb (nem húszszor).
    assert len(hetes) <= 2 * len(kilences), (len(hetes), len(kilences))
