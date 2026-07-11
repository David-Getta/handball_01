"""A súlyfájl-feloldás épség-ellenőrzésének tesztjei (sérült .pt kihagyása)."""
import os

from scripts.process_video import _resolve_weights, _weights_ok


def test_weights_ok_detects_zip_and_junk(tmp_path):
    good = tmp_path / "good.pt"
    good.write_bytes(b"PK\x03\x04 tovabbi tartalom")
    junk = tmp_path / "junk.pt"
    junk.write_bytes(b"<html>hiba</html>")
    assert _weights_ok(str(good)) is True
    assert _weights_ok(str(junk)) is False
    assert _weights_ok(str(tmp_path / "nincs.pt")) is False


def test_resolve_skips_corrupt_candidate(tmp_path, monkeypatch):
    # A HANDBALL_WEIGHTS_DIR-ben SÉRÜLT fájl van → nem szabad visszaadni.
    bad_dir = tmp_path / "w"
    bad_dir.mkdir()
    (bad_dir / "yolov8n.pt").write_bytes(b"nem zip")
    monkeypatch.setenv("HANDBALL_WEIGHTS_DIR", str(bad_dir))
    # A letöltési ág ne fusson hálózatra a tesztben: az adatmappát is ide tesszük,
    # és a letöltést elrontjuk egy nem létező URL-lel? Egyszerűbb: a data_root-ot
    # a tmp-re irányítjuk, és elfogadjuk, hogy a letöltés hibára fut (offline CI),
    # ekkor a függvény az EREDETI nevet adja vissza — de sosem a sérült utat.
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path / "data"))
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlretrieve",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    out = _resolve_weights("yolov8n.pt")
    assert out == "yolov8n.pt"  # nem a sérült fájl útja!


def test_resolve_prefers_valid_downloaded_copy(tmp_path, monkeypatch):
    # Ha az adatmappában már van ÉP letöltött példány, azt adja vissza.
    monkeypatch.delenv("HANDBALL_WEIGHTS_DIR", raising=False)
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    wdir = tmp_path / "weights"
    wdir.mkdir(parents=True)
    (wdir / "yolov8n.pt").write_bytes(b"PK\x03\x04 ep fajl")
    out = _resolve_weights("yolov8n.pt")
    assert out == str(wdir / "yolov8n.pt")
