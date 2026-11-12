"""
Tesztek a motor NATÍV összeomlásának nyomára (handball.crashlog) és a
félbehagyott munka okkal való visszaadására (futó-munka jel).

Terepen látott hiba: feldolgozás közben a motor-folyamat meghalt, az
őrkutya újraindította, és a felhasználó csak annyit látott, hogy "a
motor újraindult, a munka elveszett" — a MIÉRT nyomtalanul elveszett.

Futtatás:
    python -m pytest tests/test_crashlog.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A faulthandler valódi kimenete (Python 3.11, szegmentációs hiba).
MINTA = textwrap.dedent("""\
    Fatal Python error: Segmentation fault

    Thread 0x00007fe27829d6c0 (most recent call first):
      File "/usr/lib/python3.11/threading.py", line 324 in wait
      File "/usr/lib/python3.11/threading.py", line 1002 in _bootstrap

    Current thread 0x00007fe2787aa080 (most recent call first):
      File "/app/_internal/cv2/__init__.py", line 181 in read
      File "/app/_internal/ultralytics/data/loaders.py", line 412 in __next__
      File "/app/_internal/scripts/process_video.py", line 94 in run
      File "/usr/lib/python3.11/threading.py", line 982 in run
    """)


def test_a_fault_blokk_felismerese():
    """Az összeomló szál legfelső hívása és az első saját kódbeli sora."""
    from handball.crashlog import parse_fault
    r = parse_fault("korábbi sorok\n" + MINTA)
    assert r["fatal"] == "Fatal Python error: Segmentation fault"
    assert r["top"] == ("/app/_internal/cv2/__init__.py", 181, "read")
    assert r["own"] == ("/app/_internal/scripts/process_video.py", 94, "run")
    assert parse_fault("csak egy Python-kivétel\nTraceback ...") is None
    # Windows-alak
    w = parse_fault("Windows fatal exception: access violation\n\n"
                    "Current thread 0x1 (most recent call first):\n"
                    '  File "C:\\x\\torch\\nn.py", line 5 in forward\n')
    assert w["fatal"].startswith("Windows fatal exception")
    assert w["top"][2] == "forward"


def test_az_osszefoglalo_az_offset_utani_nyomot_mondja(tmp_path, monkeypatch):
    """Csak a munka indulása (offset) UTÁN írt összeomlás számít; a
    mondat megmondja, hol (videó-olvasás) és melyik sorban."""
    from handball.crashlog import crash_summary
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    log = tmp_path / "engine-crash.log"
    log.write_text(MINTA, encoding="utf-8")
    offset = log.stat().st_size
    assert crash_summary(offset) is None          # azóta nincs új nyom
    m = crash_summary(0)
    assert m.startswith("natív összeomlás (Segmentation fault) a videó "
                        "olvasása (dekódolása) közben — itt: read "
                        "(cv2/__init__.py:181)"), m
    assert "a mi kódunkban: run (scripts/process_video.py:94)" in m
    with open(log, "a", encoding="utf-8") as f:
        f.write(MINTA.replace("cv2/__init__.py\", line 181 in read",
                              "torch/nn/modules/conv.py\", line 7 in forward"))
    m2 = crash_summary(offset)
    assert "a detektáló modell futtatása közben" in m2 and "forward" in m2


def test_a_hely_az_ut_tagjai_alapjan():
    """A hely-besorolás az út TAGJAIBÓL jön: a "VideoElemzes" telepítési
    mappa nem "videó-olvasás", a saját process_video.py sem — csak a cv2
    (és az ultralytics olvasója) az; a torch / ultralytics a modell."""
    from handball.crashlog import _hol
    assert _hol("/app/_internal/scripts/process_video.py") == "a feldolgozás közben"
    assert _hol("D:\\VideoElemzes\\_internal\\torch\\nn\\conv.py") == (
        "a detektáló modell futtatása közben")
    assert _hol("D:\\VideoElemzes\\_internal\\cv2\\__init__.py") == (
        "a videó olvasása (dekódolása) közben")
    assert _hol("/x/ultralytics/data/loaders.py") == (
        "a videó olvasása (dekódolása) közben")
    assert _hol("/x/numpy/core/_methods.py") == "a feldolgozás közben"


def test_valodi_nativ_osszeomlas_nyoma(tmp_path):
    """Egy valódi szegmentációs hiba (ctypes) a bekapcsolt naplóval: a
    folyamat meghal, a napló megmondja, hol."""
    kod = textwrap.dedent("""
        import ctypes
        from handball.crashlog import enable_fault_log
        assert enable_fault_log()
        def melyen():
            ctypes.string_at(0)
        melyen()
    """)
    env = dict(os.environ, HANDBALL_DATA_DIR=str(tmp_path),
               PYTHONPATH=BACKEND)
    r = subprocess.run([sys.executable, "-c", kod], env=env,
                       capture_output=True, timeout=60)
    assert r.returncode != 0
    from handball.crashlog import parse_fault
    szoveg = (tmp_path / "engine-crash.log").read_text(encoding="utf-8")
    p = parse_fault(szoveg)
    assert p is not None and p["top"][2] == "string_at", szoveg


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    return TestClient(create_app())


def _halott_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_a_felbehagyott_munka_okkal_kerul_vissza(tmp_path, monkeypatch):
    """Az előző motor-folyamat futó-munka jele: újraindulás után a munka
    hibaként, OKKAL (hol tartott + a natív összeomlás) a listában és a
    naplóban — nem 404 ("a munka elveszett")."""
    pytest.importorskip("fastapi")
    mappa = tmp_path / "data" / "futo_munkak"
    mappa.mkdir(parents=True)
    log = tmp_path / "engine-crash.log"
    log.write_text("régi, nem ide tartozó nyom\n", encoding="utf-8")
    offset = log.stat().st_size
    (mappa / "abc123def456.json").write_text(json.dumps({
        "job_id": "abc123def456", "match_id": "video-abc", "video": "m.mp4",
        "stage": "B", "progress": 0.05,
        "message": "detektálás 0/300 · a detektáló modell betöltve (MPS)"
                   " — az első kockák olvasása",
        "boot": "regi", "pid": _halott_pid(), "crash_offset": offset,
        "stride": 3, "imgsz": 1280}), encoding="utf-8")
    with open(log, "a", encoding="utf-8") as f:
        f.write(MINTA)
    c = _app(tmp_path, monkeypatch)
    j = c.get("/jobs/abc123def456").json()
    assert j["status"] == "error" and j["crashed"] is True
    assert j["stage"] == "B" and j["match_id"] == "video-abc"
    assert ("a motor váratlanul leállt a feldolgozás közben (Detektálás [B], "
            "5%: „detektálás 0/300 · a detektáló modell betöltve (MPS)") in j["error"]
    assert "natív összeomlás (Segmentation fault) a videó olvasása" in j["error"]
    assert "Diagnosztika másolása" in j["error"]
    assert not list(mappa.glob("*.json"))          # a jel elfogyott
    hist = c.get("/jobs/history").json()["jobs"]
    assert hist[0]["job_id"] == "abc123def456" and hist[0]["status"] == "error"


def test_nyom_nelkuli_leallas_es_elo_masik_motor(tmp_path, monkeypatch):
    """Nyom nélkül: a rendszer állította le (memória / alvás). Egy MÁSIK,
    még élő motor-példány munkájához nem nyúlunk; a sérült jel törlődik."""
    pytest.importorskip("fastapi")
    mappa = tmp_path / "data" / "futo_munkak"
    mappa.mkdir(parents=True)
    (mappa / "nyomnelkul1.json").write_text(json.dumps({
        "job_id": "nyomnelkul1", "stage": "A", "progress": 0.02,
        "message": "kalibráció", "boot": "regi", "pid": _halott_pid(),
        "crash_offset": 0}), encoding="utf-8")
    elo = subprocess.Popen([sys.executable, "-c",
                            "import time; time.sleep(60)"])
    try:
        (mappa / "masikmotor1.json").write_text(json.dumps({
            "job_id": "masikmotor1", "stage": "B", "progress": 0.4,
            "boot": "masik", "pid": elo.pid, "updated": time.time()}),
            encoding="utf-8")
        # Élő pid, de ELAVULT jel (10 percnél régebbi): újraindítás / pid-
        # újrahasznosítás után a pid idegen folyamaté — a munka helyreáll.
        (mappa / "elavultjel1.json").write_text(json.dumps({
            "job_id": "elavultjel1", "stage": "B", "progress": 0.6,
            "boot": "masik", "pid": elo.pid,
            "updated": time.time() - 3600}), encoding="utf-8")
        (mappa / "serult.json").write_text("{nem json", encoding="utf-8")
        c = _app(tmp_path, monkeypatch)
        j = c.get("/jobs/nyomnelkul1").json()
        assert "nem hagyott nyomot a naplóban" in j["error"]
        assert "(Kalibráció [A], 2%: „kalibráció”)" in j["error"]
        assert c.get("/jobs/masikmotor1").status_code == 404
        assert (mappa / "masikmotor1.json").exists()
        assert c.get("/jobs/elavultjel1").json()["crashed"] is True
        assert not (mappa / "elavultjel1.json").exists()
        assert not (mappa / "serult.json").exists()
        # A lista rendezése "created" nélküli (jelből helyreállt) munkával
        # sem bukik el — 500 helyett a helyreállt munkák elöl.
        lista = c.get("/jobs")
        assert lista.status_code == 200
        assert {j["job_id"] for j in lista.json()["jobs"]} >= {
            "nyomnelkul1", "elavultjel1"}
    finally:
        elo.kill()
        elo.wait()


def test_a_futo_munka_jele_el_es_a_vegen_torlodik(tmp_path, monkeypatch):
    """A feldolgozás közben a jel a lemezen van (a lépéssel); a munka
    végén törlődik — kész munkánál nincs mit visszaadni."""
    pytest.importorskip("fastapi")
    import time

    import scripts.process_video as pv
    c = _app(tmp_path, monkeypatch)
    latott = {}

    def hamis_process(path, out, progress_cb=None, match_id="m", **_kw):
        progress_cb("B", 0.3, "detektálás 10/100")
        jelek = list((tmp_path / "data" / "futo_munkak").glob("*.json"))
        latott["jel"] = json.loads(jelek[0].read_text(encoding="utf-8"))
        from handball.models.tracking import Match, MatchMeta
        return Match(meta=MatchMeta(match_id=match_id, home_team="H",
                                    away_team="V", fps=25.0), frames=[])

    monkeypatch.setattr(pv, "process", hamis_process)
    v = tmp_path / "m.mp4"
    v.write_bytes(b"x")
    jid = c.post("/matches/process", json={"path": str(v)}).json()["job_id"]
    hatarido = time.time() + 30
    while c.get(f"/jobs/{jid}").json()["status"] in ("queued", "running"):
        assert time.time() < hatarido
        time.sleep(0.1)
    assert latott["jel"]["job_id"] == jid and latott["jel"]["stage"] == "B"
    assert latott["jel"]["pid"] == os.getpid()
    assert not list((tmp_path / "data" / "futo_munkak").glob("*.json"))


# ---- A napló helye, mérete, az út rövidítése és a folyamat-ellenőrzés -------

def test_crash_log_path_es_size_az_adatmappaban(tmp_path, monkeypatch):
    """A napló az adat-gyökérben él (engine-crash.log); a mérete a munka
    indulásakor feljegyzett offset — hiányzó fájlnál és hiányzó mappánál
    0, nem kivétel."""
    from handball.crashlog import (CRASH_LOG_NAME, crash_log_path,
                                   crash_log_size)

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    assert CRASH_LOG_NAME == "engine-crash.log"
    assert crash_log_path() == tmp_path / "engine-crash.log"
    assert crash_log_size() == 0                      # még nincs napló
    crash_log_path().write_bytes(b"x" * 137)
    assert crash_log_size() == 137
    crash_log_path().write_text("árvíztűrő", encoding="utf-8")
    assert crash_log_size() == len("árvíztűrő".encode("utf-8"))   # bájtban
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path / "nincs" / "ilyen"))
    assert crash_log_size() == 0


def test_rovid_az_ut_utolso_ket_tagja():
    """A hibaüzenetbe az út utolsó két tagja kerül — a felhasználói
    mappa neve nem; Windows- és Unix-elválasztóval is."""
    from handball.crashlog import _rovid

    assert _rovid("/home/dávid/app/handball/pipeline/detect.py") == \
        "pipeline/detect.py"
    assert _rovid("C:\\Users\\Dávid\\SportMachine\\_internal\\cv2\\"
                  "__init__.py") == "cv2/__init__.py"
    assert _rovid("C:\\app/scripts\\process_video.py") == \
        "scripts/process_video.py"
    assert _rovid("detect.py") == "detect.py"
    assert _rovid("") == ""


def test_sajat_a_mi_kodunk_az_ut_tagja_szerint():
    """Saját kód az, aminek az útjában a handball vagy a scripts MAPPA
    szerepel (bármelyik elválasztóval) — a hasonló nevű telepítési mappa
    vagy fájl nem."""
    from handball.crashlog import _sajat

    assert _sajat("/app/_internal/handball/pipeline/detect.py")
    assert _sajat("C:\\app\\_internal\\scripts\\process_video.py")
    assert not _sajat("/app/_internal/cv2/__init__.py")
    assert not _sajat("/usr/lib/python3.11/threading.py")
    assert not _sajat("C:\\handball_videok\\cv2\\__init__.py")
    assert not _sajat("/home/user/scripts.py")
    assert not _sajat("")


def test_pid_alive_az_elo_es_a_megszunt_folyamat():
    """A saját folyamat él; a már kilépett (megvárt) gyerek-folyamat
    nem; értelmezhetetlen vagy nem pozitív azonosítóra hamis (kétes
    esetben a félbehagyott munkát inkább jelezzük)."""
    from handball.crashlog import pid_alive

    assert pid_alive(os.getpid()) is True
    assert pid_alive(str(os.getpid())) is True        # a jel-fájlból szöveg
    gyerek = subprocess.Popen([sys.executable, "-c", "pass"])
    gyerek.wait(timeout=60)
    assert pid_alive(gyerek.pid) is False
    for rossz in (None, "", "abc", 0, -1, "-7", [1], float("nan")):
        assert pid_alive(rossz) is False, rossz


def test_pid_alive_tul_nagy_vagy_vegtelen_azonosito_sem_kivetel():
    """REGRESSZIÓ: a rendszer pid-típusánál nagyobb szám és a végtelen
    OverflowError-t dobott (az int() és az os.kill is) — ez is "kétes
    eset": hamis, nem kivétel."""
    from handball.crashlog import pid_alive

    for rossz in (3.0e40, 2 ** 70, 2 ** 31, float("inf"), float("-inf"),
                  "99999999999999999999999"):
        assert pid_alive(rossz) is False, rossz


def test_a_serult_pid_u_jel_nem_akasztja_meg_a_helyreallitast(
        tmp_path, monkeypatch):
    """REGRESSZIÓ a valódi úton: a futó-munka jel pid-je sérült fájlban
    bármi lehet (óriási szám, Infinity, szöveg, null). A helyreállítás
    ettől nem állhat meg: MINDEN ilyen munka hibaként visszakerül, a
    jelek elfogynak, a motor elindul."""
    pytest.importorskip("fastapi")
    mappa = tmp_path / "data" / "futo_munkak"
    mappa.mkdir(parents=True)
    pidek = {"oriaspid001": "1e40", "vegtelen001": "Infinity",
             "nagyegesz01": str(2 ** 70), "szovegpid01": '"abc"',
             "nullaspid01": "null"}
    for jid, pid in pidek.items():
        # Kézzel írt JSON: a json.dumps az Infinity-t is így írná ki.
        (mappa / f"{jid}.json").write_text(
            '{"job_id": "%s", "stage": "B", "progress": 0.4, '
            '"boot": "regi", "pid": %s, "updated": %r, "crash_offset": 0}'
            % (jid, pid, time.time()), encoding="utf-8")
    c = _app(tmp_path, monkeypatch)
    for jid in pidek:
        j = c.get(f"/jobs/{jid}").json()
        assert j["status"] == "error" and j["crashed"] is True, jid
        assert "a motor váratlanul leállt" in j["error"], jid
    assert not list(mappa.glob("*.json"))             # minden jel elfogyott


def test_pid_alive_jogosultsag_hianya_is_elo_folyamat(monkeypatch):
    """Ha a rendszer a jelzést jogosultság híján utasítja el, a folyamat
    LÉTEZIK (csak nem a miénk) — él; minden más rendszerhiba: nem él."""
    import handball.crashlog as cl

    if sys.platform == "win32":
        pytest.skip("a jelzés-alapú ág nem Windowsra való")
    kapott = []

    def tiltott(pid, jel):
        kapott.append((pid, jel))
        raise PermissionError("nem a miénk")

    monkeypatch.setattr(cl.os, "kill", tiltott)
    assert cl.pid_alive(4321) is True
    assert kapott == [(4321, 0)]                      # 0-s jel: csak kérdez

    def nincs(pid, jel):
        raise ProcessLookupError("nincs ilyen folyamat")

    monkeypatch.setattr(cl.os, "kill", nincs)
    assert cl.pid_alive(4321) is False


class _HamisKernel32:
    """A Windows folyamat-lekérdezés hamisítványa: `kilepes_kod` None =
    a folyamat nem nyitható meg; 259 = STILL_ACTIVE."""

    def __init__(self, kilepes_kod, sikeres=1):
        self.kilepes_kod, self.sikeres = kilepes_kod, sikeres
        self.megnyitva, self.lezarva = [], []

    def OpenProcess(self, jog, orokol, pid):
        self.megnyitva.append((jog, pid))
        return 0 if self.kilepes_kod is None else 77

    def GetExitCodeProcess(self, h, ref):
        ref._obj.value = self.kilepes_kod
        return self.sikeres

    def CloseHandle(self, h):
        self.lezarva.append(h)


def test_pid_alive_windows_aga_a_kilepesi_kodbol(monkeypatch):
    """Windowson a folyamat akkor él, ha megnyitható ÉS a kilépési kódja
    STILL_ACTIVE (259); a megnyitott leíró minden ágon bezárul; a
    rendszerhívás hibája: nem él."""
    import ctypes
    import types

    import handball.crashlog as cl

    monkeypatch.setattr(cl, "sys", types.SimpleNamespace(platform="win32"))

    def futtat(k32):
        monkeypatch.setattr(ctypes, "windll",
                            types.SimpleNamespace(kernel32=k32),
                            raising=False)
        return cl.pid_alive(4321)

    el = _HamisKernel32(259)
    assert futtat(el) is True
    assert el.megnyitva == [(0x1000, 4321)] and el.lezarva == [77]
    kilepett = _HamisKernel32(0)
    assert futtat(kilepett) is False and kilepett.lezarva == [77]
    sikertelen = _HamisKernel32(259, sikeres=0)       # a lekérdezés bukik
    assert futtat(sikertelen) is False and sikertelen.lezarva == [77]
    nincs = _HamisKernel32(None)
    assert futtat(nincs) is False and nincs.lezarva == []
    # A rendszerhívás kivétele (vagy hiányzó windll) sem jut ki.
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(),
                        raising=False)
    assert cl.pid_alive(4321) is False
