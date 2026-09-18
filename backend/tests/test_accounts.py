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
