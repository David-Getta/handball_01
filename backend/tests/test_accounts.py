"""
Tesztek a fiókokra és a felhasználási feltételekre (accounts.py + API).

A modul saját, ideiglenes adatmappában dolgozik, hogy a fejlesztői
data/accounts.json-hoz ne nyúljon.

Futtatás:
    python -m pytest tests/test_accounts.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp(prefix="handball_accounts_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from handball import accounts  # noqa: E402


def _fresh():
    """Tiszta lap: a teszt-adatmappa és az üres fiók-fájl."""
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    p = Path(_tmp) / "data" / "accounts.json"
    if p.exists():
        p.unlink()
    return p


def test_terms_name_the_owner_and_the_property():
    """A feltételek kimondják, hogy a program a Tulajdonos szellemi ÉS
    fizikai tulajdona — ez a szöveg lényege."""
    doc = accounts.terms_document()
    assert doc["version"] == accounts.TERMS_VERSION
    assert doc["owner"] == accounts.OWNER_NAME
    text = doc["text"]
    assert accounts.OWNER_NAME in text
    assert "szellemi" in text and "fizikai tulajdon" in text
    assert "TULAJDONJOG" in text


def test_register_requires_accepting_the_terms():
    """Elfogadás nélkül nincs fiók — és a fájl sem jön létre."""
    p = _fresh()
    with pytest.raises(accounts.AccountError):
        accounts.register("edzo@pelda.hu", "jelszo12345",
                          accept_terms=False)
    assert not p.exists()


def test_register_and_login_roundtrip():
    """A fiók létrejön, a jelszó SOSE tárolódik nyíltan, a belépés
    ugyanazt a fiókot adja vissza, a rossz jelszó pedig hibát."""
    p = _fresh()
    out = accounts.register("Edzo@Pelda.hu", "jelszo12345",
                            name="Teszt Edző", team="Szimu KC",
                            accept_terms=True)
    assert out["account"]["email"] == "edzo@pelda.hu"  # kisbetűsítve
    assert out["account"]["terms_version"] == accounts.TERMS_VERSION
    assert out["account"]["terms_ok"] is True
    assert out["token"]
    # A lemezen nincs nyílt jelszó, csak lenyomat.
    raw = p.read_text(encoding="utf-8")
    assert "jelszo12345" not in raw
    stored = json.loads(raw)["accounts"][0]
    assert stored["hash"] and stored["salt"] and "password" not in stored

    # Ugyanazzal az e-maillel nem lehet másodszor fiókot csinálni.
    with pytest.raises(accounts.AccountError):
        accounts.register("edzo@pelda.hu", "masikjelszo", accept_terms=True)

    # Belépés (az e-mail nagybetűs alakjával is), majd rossz jelszóval.
    li = accounts.login("EDZO@pelda.hu", "jelszo12345")
    assert li["account"]["id"] == out["account"]["id"]
    assert accounts.me(li["token"])["email"] == "edzo@pelda.hu"
    with pytest.raises(accounts.AccountError):
        accounts.login("edzo@pelda.hu", "rosszjelszo")


def test_new_terms_version_asks_for_acceptance_again():
    """Ha a feltételek verziója nő, a belépés jelzi (terms_ok=False), és
    az elfogadás után újra rendben van."""
    _fresh()
    accounts.register("edzo2@pelda.hu", "jelszo12345", accept_terms=True)
    old = accounts.TERMS_VERSION
    try:
        accounts.TERMS_VERSION = old + 1
        li = accounts.login("edzo2@pelda.hu", "jelszo12345")
        assert li["account"]["terms_ok"] is False
        acc = accounts.accept_terms(li["token"])
        assert acc["terms_ok"] is True
        assert acc["terms_version"] == old + 1
    finally:
        accounts.TERMS_VERSION = old


def test_logout_and_password_change_invalidate_the_session():
    """A kilépés érvényteleníti a kulcsot; a jelszócsere minden korábbit."""
    _fresh()
    out = accounts.register("edzo3@pelda.hu", "jelszo12345",
                            accept_terms=True)
    token = out["token"]
    assert accounts.me(token) is not None
    assert accounts.logout(token) is True
    assert accounts.me(token) is None

    li = accounts.login("edzo3@pelda.hu", "jelszo12345")
    with pytest.raises(accounts.AccountError):
        accounts.change_password(li["token"], "rossz", "ujjelszo12345")
    ch = accounts.change_password(li["token"], "jelszo12345", "ujjelszo12345")
    assert accounts.me(li["token"]) is None       # a régi kulcs elszállt
    assert accounts.me(ch["token"]) is not None   # az új él
    assert accounts.login("edzo3@pelda.hu", "ujjelszo12345")["token"]


def test_short_password_and_bad_email_are_rejected():
    """Rövid jelszó és formailag hibás e-mail nem megy át."""
    _fresh()
    with pytest.raises(accounts.AccountError):
        accounts.register("edzo4@pelda.hu", "rovid", accept_terms=True)
    with pytest.raises(accounts.AccountError):
        accounts.register("nem-email", "jelszo12345", accept_terms=True)


# --- API-szint (FastAPI nélkül a modul kihagyja magát) --------------------

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402


def _client():
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    _fresh()
    return TestClient(create_app())


def test_api_terms_register_login_flow():
    """A kliens útja: feltételek lekérése → fiók → belépés → /accounts/me."""
    client = _client()
    terms = client.get("/legal/terms").json()
    assert terms["version"] == accounts.TERMS_VERSION
    assert accounts.OWNER_NAME in terms["text"]

    assert client.get("/accounts/status").json()["has_accounts"] is False

    # Elfogadás nélkül elutasít.
    bad = client.post("/accounts/register",
                      json={"email": "api@pelda.hu",
                            "password": "jelszo12345",
                            "accept_terms": False})
    assert bad.status_code == 400

    ok = client.post("/accounts/register",
                     json={"email": "api@pelda.hu",
                           "password": "jelszo12345",
                           "name": "API Edző",
                           "accept_terms": True})
    assert ok.status_code == 200, ok.text
    token = ok.json()["token"]
    assert client.get("/accounts/status").json()["has_accounts"] is True

    me = client.get("/accounts/me",
                    headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "api@pelda.hu"
    assert me.json()["terms_ok"] is True

    # Rossz jelszóval 401, jóval új kulcs.
    assert client.post("/accounts/login",
                       json={"email": "api@pelda.hu",
                             "password": "rossz"}).status_code == 401
    li = client.post("/accounts/login",
                     json={"email": "api@pelda.hu",
                           "password": "jelszo12345"})
    assert li.status_code == 200
    token2 = li.json()["token"]

    # Kilépés után a kulcs nem érvényes.
    assert client.post("/accounts/logout",
                       json={"token": token2}).json()["logged_out"] is True
    assert client.get("/accounts/me",
                      params={"token": token2}).status_code == 401


def test_api_me_without_token_is_unauthorized():
    """Kulcs nélkül a /accounts/me 401-et ad."""
    client = _client()
    assert client.get("/accounts/me").status_code == 401


# ---- A fiók-tár építőkövei közvetlenül ---------------------------------------
# (Ezek a tesztek saját, tesztenkénti adatmappát kapnak — nem a modul közös
# mappáját —, így a sorrendtől és egymástól függetlenek.)

@pytest.fixture
def sajat_mappa(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    return tmp_path


def test_terms_text_a_verzioval_a_datummal_es_a_tulajdonossal():
    """A feltételek szövege viszi a verziót és a hatály dátumát (ezt
    fogadja el a felhasználó — később is bizonyítható, melyiket), a
    termék és a tulajdonos nevét; a kliensnek adott csomag ugyanezt a
    szöveget tartalmazza."""
    szoveg = accounts.terms_text()
    assert szoveg.startswith(f"{accounts.PRODUCT_NAME} — Felhasználási "
                             "feltételek")
    assert (f"(verzió: {accounts.TERMS_VERSION}, hatályos: "
            f"{accounts.TERMS_UPDATED})") in szoveg
    assert accounts.OWNER_NAME in szoveg
    assert accounts.terms_document()["text"] == szoveg
    assert accounts.terms_text() == szoveg            # determinisztikus


def test_accounts_path_load_es_save_korbe(sajat_mappa):
    """A fiók-fájl az adatmappa data/accounts.json-ja; hiányzó fájlnál
    üres lista, a mentés a mappát is létrehozza, az ékezet olvashatóan
    (nem \\u-kódolva) kerül a fájlba, és a visszaolvasás ugyanazt adja."""
    ut = accounts.accounts_path()
    assert ut == sajat_mappa / "data" / "accounts.json"
    assert accounts.load_accounts() == [] and not ut.exists()
    fiokok = [{"id": "a1", "email": "edzo@pelda.hu", "name": "Kovács Dávid"}]
    accounts.save_accounts(fiokok)
    assert ut.exists()
    nyers = ut.read_text(encoding="utf-8")
    assert "Kovács Dávid" in nyers
    assert json.loads(nyers) == {"version": 1, "accounts": fiokok}
    assert accounts.load_accounts() == fiokok
    accounts.save_accounts([])
    assert accounts.load_accounts() == []


def test_load_accounts_serult_fajlnal_ures_lista(sajat_mappa):
    """Sérült vagy rossz alakú fiók-fájl: üres lista — a program
    elindul (regisztrálni lehet), nem kivétellel áll meg."""
    ut = accounts.accounts_path()
    ut.parent.mkdir(parents=True)
    for tartalom in ("{nem json", "", "[1, 2, 3]", '"szöveg"',
                     '{"version": 1}', '{"accounts": "nem lista"}',
                     '{"accounts": null}'):
        ut.write_text(tartalom, encoding="utf-8")
        assert accounts.load_accounts() == [], tartalom
    ut.write_bytes(b"\xff\xfe\x00rossz kodolas")
    assert accounts.load_accounts() == []


def test_normalize_email_egyseges_kulcs():
    """Az e-mail a fiók kulcsa: kisbetű, levágott szóközök, egységes
    Unicode-alak (a teljes szélességű betű is ugyanaz a cím); üres vagy
    hiányzó értékre üres szöveg."""
    assert accounts.normalize_email("  Edzo@Pelda.HU ") == "edzo@pelda.hu"
    assert accounts.normalize_email("ｅｄｚｏ@pelda.hu") == "edzo@pelda.hu"
    assert accounts.normalize_email("ÁRVÍZ@pelda.hu") == "árvíz@pelda.hu"
    assert accounts.normalize_email(None) == ""
    assert accounts.normalize_email("") == ""
    assert accounts.normalize_email(123) == "123"


def test_now_es_iso_utc_masodpercre_vagva():
    """Az időbélyegek UTC-ben, másodpercre vágva, ISO-alakban tárolódnak
    (az elfogadás időpontja így bármely gépen ugyanazt jelenti)."""
    from datetime import datetime, timedelta, timezone

    most = accounts._now()
    assert most.tzinfo is not None and most.utcoffset() == timedelta(0)
    assert abs((datetime.now(timezone.utc) - most).total_seconds()) < 5
    pontos = datetime(2026, 8, 18, 9, 30, 15, 987654, tzinfo=timezone.utc)
    assert accounts._iso(pontos) == "2026-08-18T09:30:15+00:00"
    assert datetime.fromisoformat(accounts._iso(pontos)) == pontos.replace(
        microsecond=0)


def test_hash_password_so_es_korszam_fuggo_lenyomat():
    """A jelszó lenyomata PBKDF2-HMAC-SHA256 hexben: ugyanarra a
    (jelszó, só, kör-szám) hármasra ugyanaz, bármelyik változására más;
    az ékezetes jelszó UTF-8-ban megy; a nyílt jelszó nincs benne."""
    import hashlib

    so = bytes(range(16))
    a = accounts._hash_password("jelszo12345", so, 1000)
    assert a == accounts._hash_password("jelszo12345", so, 1000)
    assert len(a) == 64 and int(a, 16) >= 0           # 32 bájt hexben
    assert a == hashlib.pbkdf2_hmac("sha256", b"jelszo12345", so, 1000).hex()
    assert a != accounts._hash_password("jelszo12346", so, 1000)
    assert a != accounts._hash_password("jelszo12345", bytes(16), 1000)
    assert a != accounts._hash_password("jelszo12345", so, 1001)
    ekezetes = accounts._hash_password("árvíztűrő", so, 1000)
    assert ekezetes == hashlib.pbkdf2_hmac(
        "sha256", "árvíztűrő".encode("utf-8"), so, 1000).hex()
    assert "jelszo12345" not in a
    assert accounts.PBKDF2_ITERATIONS >= 100_000      # az alap lassú


def test_public_nem_ad_ki_titkot():
    """A fiók kifelé adható képe: se só, se lenyomat, se munkamenet-
    kulcs; a terms_ok csak akkor igaz, ha a fiók a MOSTANI feltétel-
    verziót fogadta el. Hiányos rekordra sem hibázik."""
    fiok = {"id": "a1", "email": "edzo@pelda.hu", "name": "Edző",
            "team": "Veszprém", "salt": "00", "hash": "ff",
            "iterations": 1000, "created_at": "2026-01-01T00:00:00+00:00",
            "terms_version": accounts.TERMS_VERSION,
            "terms_accepted_at": "2026-01-01T00:00:00+00:00",
            "tokens": [{"token": "titok"}]}
    kep = accounts._public(fiok)
    assert set(kep) == {"id", "email", "name", "team", "created_at",
                        "terms_version", "terms_accepted_at", "terms_ok"}
    assert kep["terms_ok"] is True and kep["team"] == "Veszprém"
    assert "titok" not in json.dumps(kep) and "ff" not in kep.values()
    regi = dict(fiok, terms_version=accounts.TERMS_VERSION - 1)
    assert accounts._public(regi)["terms_ok"] is False
    ures = accounts._public({})
    assert ures["terms_ok"] is False and ures["email"] is None


def test_find_az_egyseges_e_mail_kulccsal_keres():
    """A fiók-keresés a normalizált e-maillel megy (kis-nagybetű és
    szóköz nem számít); nincs találat → None; e-mail nélküli (sérült)
    rekord nem akasztja meg."""
    fiokok = [{"id": "x"}, {"id": "a1", "email": "Edzo@Pelda.hu"},
              {"id": "a2", "email": "masik@pelda.hu"}]
    assert accounts._find(fiokok, " EDZO@pelda.HU ")["id"] == "a1"
    assert accounts._find(fiokok, "masik@pelda.hu")["id"] == "a2"
    assert accounts._find(fiokok, "nincs@pelda.hu") is None
    assert accounts._find([], "edzo@pelda.hu") is None
    # Ugyanaz az objektum jön vissza (a hívó ebbe ír).
    assert accounts._find(fiokok, "edzo@pelda.hu") is fiokok[1]


def test_new_token_lejaratot_ad_takarit_es_plafonoz():
    """Az új munkamenet-kulcs TOKEN_DAYS napig él; a lejárt és a sérült
    kulcsok közben kitakarítódnak; fiókonként legfeljebb 10 élő
    munkamenet marad (a legrégebbi esik ki)."""
    from datetime import datetime, timedelta

    most = accounts._now()
    fiok = {"tokens": [
        {"token": "lejart", "created_at": "x",
         "expires_at": accounts._iso(most - timedelta(days=1))},
        {"token": "serult"},                                    # nincs lejárat
        {"token": "rossz", "expires_at": "nem dátum"},
        {"token": "elo", "created_at": "x",
         "expires_at": accounts._iso(most + timedelta(days=5))}]}
    kulcs = accounts._new_token(fiok)
    assert isinstance(kulcs, str) and len(kulcs) >= 32
    assert [t["token"] for t in fiok["tokens"]] == ["elo", kulcs]
    uj = fiok["tokens"][-1]
    lejar = datetime.fromisoformat(uj["expires_at"])
    kelt = datetime.fromisoformat(uj["created_at"])
    assert lejar - kelt == timedelta(days=accounts.TOKEN_DAYS)
    assert abs((kelt - most).total_seconds()) < 5
    # Tokens kulcs nélküli (új) fiókra is megy.
    friss = {}
    assert accounts._new_token(friss) == friss["tokens"][0]["token"]
    # Plafon: 14 belépés után is csak a 10 legutóbbi él.
    kulcsok = [accounts._new_token(friss) for _ in range(13)]
    assert len(set(kulcsok)) == 13                     # mind különböző
    assert [t["token"] for t in friss["tokens"]] == kulcsok[-10:]


def test_account_for_token_a_nyers_rekord_vagy_none(sajat_mappa):
    """Az érvényes kulcshoz a fiók NYERS rekordja jön (belső használat —
    benne a lenyomat); üres, ismeretlen, lejárt vagy sérült lejáratú
    kulcsra None."""
    from datetime import timedelta

    eredmeny = accounts.register("edzo@pelda.hu", "jelszo12345",
                                 name="Edző", accept_terms=True)
    kulcs = eredmeny["token"]
    nyers = accounts.account_for_token(kulcs)
    assert nyers["email"] == "edzo@pelda.hu" and nyers["hash"]
    assert accounts.me(kulcs) == accounts._public(nyers)
    for rossz in ("", None, "ismeretlen-kulcs", kulcs + "x", kulcs[:-1]):
        assert accounts.account_for_token(rossz) is None, rossz
    # Lejárt kulcs: a rekordban ott van, de nem érvényes.
    fiokok = accounts.load_accounts()
    fiokok[0]["tokens"][0]["expires_at"] = accounts._iso(
        accounts._now() - timedelta(seconds=1))
    accounts.save_accounts(fiokok)
    assert accounts.account_for_token(kulcs) is None
    assert accounts.me(kulcs) is None
    # Sérült lejárat: szintén nem érvényes (nem kivétel).
    for serult in ("nem dátum", None):
        fiokok[0]["tokens"][0]["expires_at"] = serult
        accounts.save_accounts(fiokok)
        assert accounts.account_for_token(kulcs) is None
    del fiokok[0]["tokens"][0]["expires_at"]
    accounts.save_accounts(fiokok)
    assert accounts.account_for_token(kulcs) is None


def test_accounts_status_ures_gepen_es_fiok_utan(sajat_mappa):
    """A kliens ebből tudja, regisztrálni vagy belépni kell-e: első
    indításnál nincs fiók; regisztráció után van — a feltétel-verzióval
    és a tulajdonos nevével."""
    assert accounts.accounts_status() == {
        "count": 0, "has_accounts": False,
        "terms_version": accounts.TERMS_VERSION,
        "owner": accounts.OWNER_NAME}
    accounts.register("edzo@pelda.hu", "jelszo12345", accept_terms=True)
    accounts.register("masik@pelda.hu", "jelszo12345", accept_terms=True)
    allapot = accounts.accounts_status()
    assert allapot["count"] == 2 and allapot["has_accounts"] is True
    # Sérült fájlnál "nincs fiók" (újra lehet regisztrálni).
    accounts.accounts_path().write_text("{nem json", encoding="utf-8")
    assert accounts.accounts_status()["count"] == 0
