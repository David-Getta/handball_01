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


def test_az_osszeomlas_jelentes_stdout_nelkul_is_ir(tmp_path, monkeypatch):
    """ŐR: a hibajelentő akkor is fájlba ír, ha NINCS stdout.

    Pont az az eset a legfontosabb, amikor a stream-átirányítás maga
    bukott el (nem írható adatmappa, ablak nélküli futás): ilyenkor a
    print() kivételt dob, és ha a jelentő azon elhasal, a hiba oka
    nyomtalanul elvész — a felhasználó csak "Connection refused"-öt lát.
    """
    import sys

    from scripts.serve import _crash_report

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    try:
        raise RuntimeError("szimulált indulási hiba")
    except BaseException as exc:  # noqa: BLE001 — ezt teszteljük
        _crash_report(exc)  # nem dobhat

    naplo = tmp_path / "engine-crash.log"
    assert naplo.exists(), "stdout nélkül nem készült összeomlás-napló"
    szoveg = naplo.read_text(encoding="utf-8")
    assert "RuntimeError: szimulált indulási hiba" in szoveg, (
        "a napló nem tartalmazza a hiba lényegét")


def test_a_stream_atiranyitas_a_hibakezelesen_belul_fut():
    """ŐR: az _ensure_streams a try-n BELÜL fut.

    Ha az adatmappa nem írható, a napló megnyitása kivételt dob. A
    try-n kívülről ez azt jelentette, hogy a motor nyom nélkül halt meg
    — a hibajelentő maga sem futott le.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "serve.py").read_text(encoding="utf-8")
    fo = src.index("def main(")
    try_poz = src.index("try:", fo)
    ensure_poz = src.index("_ensure_streams()", fo)
    assert try_poz < ensure_poz, (
        "az _ensure_streams a hibakezelésen KÍVÜL fut — nem írható "
        "adatmappánál a motor nyom nélkül hal meg")


# ---- Az indító lépései: stream-átirányítás, mérföldkő, main --------------------
# (eddig egyszer sem futottak a csomagban — csak a forrásukat néztük)

def test_ensure_streams_ablak_nelkul_naploba_iranyit(tmp_path, monkeypatch):
    """Ablak nélküli (csomagolt) futásnál nincs stdout/stderr: a kimenet
    a felhasználói adatmappa engine.log fájljába megy — a print nem dől
    el, és hiba esetén van mit megnézni."""
    import sys

    from scripts.serve import _ensure_streams

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path / "adat"))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    _ensure_streams()
    naplo_fajl = sys.stdout
    try:
        assert naplo_fajl is not None and sys.stderr is naplo_fajl
        print("a motor elindult — árvíztűrő")
        print("hiba-sor", file=sys.stderr)
    finally:
        naplo_fajl.close()
    naplo = tmp_path / "adat" / "engine.log"
    assert naplo.read_text(encoding="utf-8") == (
        "a motor elindult — árvíztűrő\nhiba-sor\n")


def test_ensure_streams_csak_a_hianyzo_streamet_potolja(tmp_path, monkeypatch):
    """Ha csak a stderr hiányzik, a stdout marad, ami volt; a napló
    HOZZÁFŰZ (a korábbi indulás sorai megmaradnak)."""
    import io
    import sys

    from scripts.serve import _ensure_streams

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    (tmp_path / "engine.log").write_text("korábbi indulás\n",
                                         encoding="utf-8")
    sajat = io.StringIO()
    monkeypatch.setattr(sys, "stdout", sajat)
    monkeypatch.setattr(sys, "stderr", None)
    _ensure_streams()
    naplo_fajl = sys.stderr
    try:
        assert sys.stdout is sajat and naplo_fajl is not None
        print("új hiba", file=sys.stderr)
    finally:
        naplo_fajl.close()
    assert (tmp_path / "engine.log").read_text(encoding="utf-8") == (
        "korábbi indulás\núj hiba\n")


def test_ensure_streams_meglevo_streamekhez_nem_nyul(tmp_path, monkeypatch):
    """Terminálból futtatva (van stdout és stderr) nem irányít át semmit,
    és nem hoz létre naplófájlt."""
    import sys

    from scripts.serve import _ensure_streams

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path / "adat"))
    ki, hiba = sys.stdout, sys.stderr
    _ensure_streams()
    assert sys.stdout is ki and sys.stderr is hiba
    assert not (tmp_path / "adat").exists()


def test_stage_merfoldko_a_naploba_es_a_hibaja_nem_all_meg(monkeypatch,
                                                            capsys):
    """Az indulási mérföldkő "[indulás] …" sorként megy ki; ha a kimenet
    hiányzik vagy a cső eltört, a naplózás hibája nem állítja meg az
    indulást."""
    import sys

    from scripts.serve import _stage

    _stage("webszerver betöltése…")
    assert capsys.readouterr().out == "[indulás] webszerver betöltése…\n"

    class _TorottCso:
        def write(self, _s):
            raise BrokenPipeError("a kliens leállt")

        def flush(self):
            raise BrokenPipeError("a kliens leállt")

    monkeypatch.setattr(sys, "stdout", _TorottCso())
    _stage("ez nem dobhat")                      # nem dobhat
    monkeypatch.setattr(sys, "stdout", None)
    _stage("stdout nélkül sem dobhat")


def _indito_kornyezet(monkeypatch, tmp_path):
    """A main kamu webszerverrel és motorral: nem nyit portot, nem tölt
    modellt — csak azt nézzük, mit indítana és hová."""
    import pytest

    uvicorn = pytest.importorskip("uvicorn")
    import handball.api.app as api_mod
    import handball.crashlog as crashlog

    hivasok: dict = {"fault_log": 0}
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(crashlog, "enable_fault_log",
                        lambda: hivasok.__setitem__(
                            "fault_log", hivasok["fault_log"] + 1))
    monkeypatch.setattr(api_mod, "create_app", lambda: "KAMU-APP")

    def kamu_run(app, host, port, log_level):
        hivasok["run"] = {"app": app, "host": host, "port": port,
                          "log_level": log_level}

    monkeypatch.setattr(uvicorn, "run", kamu_run)
    return hivasok, uvicorn


def test_main_a_beallitott_cimen_inditja_a_motort(tmp_path, monkeypatch,
                                                   capsys):
    """A main a környezetben megadott címen és (szabad) porton indítja a
    kész alkalmazást, előtte bekapcsolja a natív összeomlás-naplót, és a
    mérföldkövek a kimenetre mennek; a kilépőkód 0."""
    import socket

    from scripts.serve import main

    hivasok, _ = _indito_kornyezet(monkeypatch, tmp_path)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    szabad = s.getsockname()[1]
    s.close()
    monkeypatch.setenv("HANDBALL_HOST", "127.0.0.1")
    monkeypatch.setenv("HANDBALL_PORT", str(szabad))

    assert main() == 0
    assert hivasok["run"] == {"app": "KAMU-APP", "host": "127.0.0.1",
                              "port": szabad, "log_level": "info"}
    assert hivasok["fault_log"] == 1
    ki = capsys.readouterr().out
    assert "[indulás] az indító elindult (python " in ki
    assert "[indulás] a motor betöltve" in ki
    assert f"Sport Machine backend indul: http://127.0.0.1:{szabad}" in ki
    assert "FIGYELEM" not in ki and "VÉGZETES" not in ki
    assert not (tmp_path / "engine-crash.log").exists()


def test_main_foglalt_portnal_tartalek_portra_kot(tmp_path, monkeypatch,
                                                  capsys):
    """Ha a kért portot már használja valami, a motor nem hal el: a
    következő szabad portra köt, és ezt ki is mondja."""
    import socket

    from scripts.serve import main

    hivasok, _ = _indito_kornyezet(monkeypatch, tmp_path)
    foglalo = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    foglalo.bind(("127.0.0.1", 0))
    foglalo.listen(1)
    foglalt = foglalo.getsockname()[1]
    monkeypatch.setenv("HANDBALL_HOST", "127.0.0.1")
    monkeypatch.setenv("HANDBALL_PORT", str(foglalt))
    try:
        assert main() == 0
    finally:
        foglalo.close()
    port = hivasok["run"]["port"]
    assert foglalt < port <= foglalt + 10
    ki = capsys.readouterr().out
    assert f"FIGYELEM: a {foglalt}-es port foglalt — tartalék port: {port}" \
        in ki
    assert f"http://127.0.0.1:{port}" in ki


def test_main_vegzetes_hibanal_1_es_kod_es_osszeomlas_naplo(tmp_path,
                                                            monkeypatch,
                                                            capsys):
    """Ha az indulás közben bármi elszáll (itt: a webszerver), a main nem
    hal meg némán: 1-es kilépőkód, a mérföldkő kimondja a végzetes hibát,
    és a hiba lényege az engine-crash.log-ba kerül."""
    from scripts.serve import main

    hivasok, uvicorn = _indito_kornyezet(monkeypatch, tmp_path)

    def elszall(*a, **k):
        raise OSError("hiányzó rendszerkönyvtár: libomp")

    monkeypatch.setattr(uvicorn, "run", elszall)
    monkeypatch.setenv("HANDBALL_PORT", "8000")
    assert main() == 1
    ki = capsys.readouterr().out
    assert "[indulás] VÉGZETES HIBA az indulás közben" in ki
    assert "OSError: hiányzó rendszerkönyvtár: libomp" in ki
    naplo = (tmp_path / "engine-crash.log").read_text(encoding="utf-8")
    assert "OSError: hiányzó rendszerkönyvtár: libomp" in naplo
    assert "Traceback" in naplo

    # A rossz port-beállítás (nem szám) is ide esik — nem néma halál.
    monkeypatch.setenv("HANDBALL_PORT", "nyolcezer")
    assert main() == 1
    assert "ValueError" in capsys.readouterr().out
