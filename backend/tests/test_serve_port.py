"""
Tesztek a motor port-választására (serve.pick_free_port).

Futtatás:
    python -m pytest tests/test_serve_port.py
"""

from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.serve import pick_free_port


def test_returns_start_port_when_free():
    # Egy biztosan szabad, magas kezdőport.
    assert pick_free_port("127.0.0.1", 47311) == 47311


def test_skips_occupied_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    busy = s.getsockname()[1]
    try:
        # A foglalt portról a KÖVETKEZŐRE lép (feltéve, hogy az szabad).
        picked = pick_free_port("127.0.0.1", busy)
        assert picked != busy
        assert busy < picked < busy + 11
    finally:
        s.close()


def test_gives_up_after_range_and_returns_start():
    """Ha az egész tartomány foglalt, az eredeti portot adja vissza —
    a bind-hiba így érthető helyen (az eredeti porton) jelentkezik."""
    socks = []
    base = None
    try:
        # 11 egymást követő port lefoglalása egy szabad sávban.
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        base = probe.getsockname()[1]
        probe.close()
        for p in range(base, base + 11):
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", p))
                socks.append(s)
            except OSError:
                # Nem sikerült az egész sávot lefoglalni — a teszt így nem
                # tudja a "minden foglalt" esetet felépíteni; kihagyjuk.
                import pytest
                pytest.skip("nem sikerült 11 egymás utáni portot lefoglalni")
        assert pick_free_port("127.0.0.1", base) == base
    finally:
        for s in socks:
            s.close()


if __name__ == "__main__":
    test_returns_start_port_when_free()
    test_skips_occupied_port()
    test_gives_up_after_range_and_returns_start()
    print("Minden port-választó teszt OK.")


def test_health_full_checklist():
    """A teljes egészség-ellenőrzés: minden elem name/ok/detail hármas,
    és a teszt-környezet alap-ellenőrzései zöldek."""
    import os
    import tempfile

    import pytest

    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(prefix="hb_health_")
    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient
    from handball.api.app import create_app
    client = TestClient(create_app())
    r = client.get("/health/full")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and isinstance(body["checks"], list)
    names = {c["name"] for c in body["checks"]}
    for c in body["checks"]:
        assert set(c) == {"name", "ok", "detail"}
    assert "Adatmappa írható" in names
    assert "Videó-írás (mp4v)" in names
    by_name = {c["name"]: c for c in body["checks"]}
    assert by_name["Adatmappa írható"]["ok"] is True
    assert by_name["OpenCV (videó-kezelés)"]["ok"] is True
    assert by_name["Meccskönyvtár"]["ok"] is True


def test_health_kiadja_a_motor_verziot():
    """ŐR: a /health a motor verzióját is kiadja — a kliens ebből veszi
    észre a fél-frissült telepítést (új app + régi motor)."""
    import pytest

    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient
    from handball import __version__
    from handball.api.app import create_app

    client = TestClient(create_app())
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_az_indulas_merfoldkovei_a_nehez_importok_elott_szolalnak_meg():
    """ŐR: a motor indulási sorai a NEHÉZ IMPORTOK ELŐTT kezdődnek.

    A torch/OpenCV betöltése másodpercekig — becsomagolt kiadásban,
    víruskereső-átvizsgálással percekig — tart. Ha az első naplósor csak
    utánuk jönne, akkor az ott elhaló motor ÜRES naplót hagyna, és nem
    lehetne megmondani, meddig jutott el. A felhasználó ilyenkor csak
    "Connection refused"-öt lát.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "serve.py").read_text(encoding="utf-8")
    fo = src.index("def main(")
    elso_sor = src.index("_stage(", fo)
    elso_import = src.index("import uvicorn", fo)
    assert elso_sor < elso_import, (
        "az első indulási naplósor a nehéz importok UTÁN jön — az ott "
        "elhaló motor üres naplót hagyna")


def test_az_indulasi_kivetel_nem_vesz_el():
    """ŐR: a végzetes indulási kivétel jelentést kap.

    A becsomagolt kiadás legcsúnyább hibái (hiányzó rendszerkönyvtár,
    OpenMP-ütközés, nem írható adatmappa) itt csapódnak le. Kezeletlenül
    a folyamat NÉMÁN meghal, és a felhasználónak nincs mit elküldenie.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "serve.py").read_text(encoding="utf-8")
    assert "except BaseException" in src, (
        "a main() nem fogja meg a végzetes indulási kivételt")
    assert "_crash_report" in src, "nincs összeomlás-jelentés"
    assert "engine-crash.log" in src, (
        "az összeomlás nem kerül tartós fájlba — a cső eltörésével elvész")
