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
