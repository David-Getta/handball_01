"""
Fiókok és felhasználási feltételek — ki használja a programot, és mit fogadott el.

A Sport Machine LOKÁLIS program: a fiókok is a gépen, a program írható
adatmappájában élnek (lásd storage.data_root), nem felhőben. A modul
szándékosan függőség-mentes (csak Python-alapkönyvtár), hogy az API nélkül
is tesztelhető legyen — a FastAPI-végpontok (api/app.py) csak ráhívnak.

Két dolgot intéz:

1. **Felhasználási feltételek (ÁSZF/EULA)**: a program a TULAJDONOS szellemi
   és fizikai tulajdona; a felhasználó csak használati engedélyt kap. A
   feltételeket a fiók létrehozásakor el kell fogadni, és a szöveg
   VERZIÓZOTT — ha a feltételek változnak (TERMS_VERSION nő), a belépés után
   újra el kell fogadni. Az elfogadás ténye (verzió + UTC időbélyeg) a
   fiókban tárolódik, tehát később is bizonyítható.

2. **Fiókok**: e-mail + jelszó, a jelszó SOSE tárolódik nyíltan — csak
   PBKDF2-HMAC-SHA256 lenyomat, fiókonkénti véletlen sóval. A belépés
   munkamenet-kulcsot (token) ad; a kulcs a fiók-fájlban él, hogy az app
   újraindítás után is emlékezzen a bejelentkezésre (a program a felhasználó
   saját gépén, az ő jogosultságával fut).

A fiók-fájl (accounts.json) alakja:
    {"version": 1, "accounts": [ {...}, ... ]}
egy fiók:
    {"id", "email", "name", "team", "salt", "hash", "iterations",
     "created_at", "terms_version", "terms_accepted_at",
     "tokens": [{"token", "created_at", "expires_at"}]}
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .storage import data_root

# A program tulajdonosa. A feltételek szövege és a fiók-elfogadás erre a
# névre szól; másik tulajdonos-névhez elég a SPORTMACHINE_OWNER környezeti
# változót beállítani (a telepítő/csomagoló is átállíthatja).
OWNER_NAME = os.environ.get("SPORTMACHINE_OWNER", "Getta Dávid")
OWNER_CONTACT = os.environ.get("SPORTMACHINE_OWNER_CONTACT",
                               "davidesgyula@gmail.com")
PRODUCT_NAME = "Sport Machine"

# A feltételek verziója. HA A SZÖVEG VÁLTOZIK, EZT IS NÖVELNI KELL — a
# meglévő fiókoknak ilyenkor újra el kell fogadniuk (a belépés jelzi).
TERMS_VERSION = 1
TERMS_UPDATED = "2026-08-18"

# Jelszó-lenyomat: PBKDF2-HMAC-SHA256, ennyi kör és ekkora só. (Alapkönyvtár
# — nem kell külön csomag; a kör-szám lassítja a próbálgatást.)
PBKDF2_ITERATIONS = 200_000
SALT_BYTES = 16
MIN_PASSWORD_LEN = 8

# A munkamenet-kulcs ennyi napig érvényes (utána újra be kell lépni).
TOKEN_DAYS = 90

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


class AccountError(Exception):
    """Fiók-hiba beszélő, MAGYAR üzenettel (a kliens ezt mutatja meg)."""


def terms_text() -> str:
    """A felhasználási feltételek teljes szövege (magyarul).

    A felhasználó ezt fogadja el a fiók létrehozásakor. A lényeg az 1. és a
    2. pont: a program a tulajdonosé (szellemi és fizikai tulajdon), a
    felhasználó csak korlátozott, visszavonható használati engedélyt kap.
    """
    return f"""\
{PRODUCT_NAME} — Felhasználási feltételek és végfelhasználói licencszerződés
(verzió: {TERMS_VERSION}, hatályos: {TERMS_UPDATED})

Kérjük, a fiók létrehozása előtt olvassa el. A fiók létrehozásával és a
program használatával Ön elfogadja az alábbiakat.

1. TULAJDONJOG
A {PRODUCT_NAME} szoftver — beleértve a forráskódot, az elemző eljárásokat
és modelleket, a betanított súlyokat, az adatszerkezeteket, a felhasználói
felületet, a grafikai és szöveges tartalmakat, a dokumentációt, a nevet és
minden egyéb megjelenést — {OWNER_NAME} (a továbbiakban: Tulajdonos)
kizárólagos szellemi tulajdona. A program adathordozón, eszközön vagy
szerveren megjelenő példányai, valamint a Tulajdonos által rendelkezésre
bocsátott fizikai eszközök a Tulajdonos fizikai tulajdonát képezik.
Ön tudomásul veszi, hogy a programra vonatkozó minden vagyoni és személyhez
fűződő jog a Tulajdonost illeti, és a használat semmilyen tulajdoni vagy
társtulajdonosi részesedést nem keletkeztet az Ön javára.

2. FELHASZNÁLÁSI ENGEDÉLY
A Tulajdonos nem kizárólagos, át nem ruházható, tovább nem engedélyezhető,
bármikor visszavonható engedélyt ad Önnek arra, hogy a programot saját
(egyesületi, edzői, elemzői) céljára használja. Az engedély a program
használatára szól — nem jelenti a program vagy bármely részének átadását.

3. AMIT NEM TEHET
Ön nem jogosult a programot vagy annak bármely részét: másolni,
terjeszteni, kölcsönadni, bérbe adni, továbbértékesíteni, nyilvánosan
hozzáférhetővé tenni; visszafejteni, visszafordítani, a forráskódját
kinyerni; származékos művet készíteni belőle; a védjegyeit, neveit,
szerzői jogi jelzéseit eltávolítani vagy megváltoztatni; harmadik félnek
hozzáférést adni hozzá a Tulajdonos előzetes írásbeli engedélye nélkül.

4. AZ ÖN ADATAI
A feltöltött felvételek, a belőlük készült elemzések és a jegyzetek az Ön
adatai, és a saját gépén, a program adatmappájában maradnak. A Tulajdonos
ezekhez nem fér hozzá, kivéve, ha Ön kifejezetten megosztja vele (például
hibajelentéshez). Ön felel azért, hogy a felvételek készítéséhez és
elemzéséhez a szükséges hozzájárulásokkal rendelkezik.

5. FELELŐSSÉG
A program elemzései döntéstámogató becslések, nem hivatalos meccsadatok. A
program "adott állapotban" áll rendelkezésre; a Tulajdonos a jogszabály
által megengedett mértékig kizárja a felelősségét a használatból eredő
károkért, elmaradt haszonért vagy adatvesztésért. Adatairól Ön készít
biztonsági mentést.

6. AZ ENGEDÉLY MEGSZŰNÉSE
A feltételek megsértése esetén az engedély azonnal megszűnik, és a
programot törölnie kell. Ön a fiókja törlésével bármikor felhagyhat a
használattal.

7. A FELTÉTELEK VÁLTOZÁSA
A Tulajdonos a feltételeket módosíthatja; a módosított szöveg új verziót
kap, és a program a belépéskor újra elfogadásra felkínálja. Az elfogadás
tényét (verzió és időpont) a program a fiókjában rögzíti.

8. IRÁNYADÓ JOG
A szerződésre a magyar jog irányadó. Kapcsolat: {OWNER_CONTACT}.

A fiók létrehozásával Ön kijelenti, hogy a fenti feltételeket elolvasta,
megértette, elfogadja, és tudomásul veszi, hogy a {PRODUCT_NAME} szoftver
{OWNER_NAME} szellemi és fizikai tulajdona.
"""


def terms_document() -> dict:
    """A feltételek "csomagja" a kliensnek: verzió, cím, szöveg, tulajdonos."""
    return {
        "version": TERMS_VERSION,
        "updated": TERMS_UPDATED,
        "title": f"{PRODUCT_NAME} — Felhasználási feltételek",
        "owner": OWNER_NAME,
        "contact": OWNER_CONTACT,
        "text": terms_text(),
    }


def accounts_path() -> Path:
    """A fiók-fájl helye a program írható adatmappájában."""
    return data_root() / "data" / "accounts.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def load_accounts() -> list:
    """A tárolt fiókok listája (hiányzó vagy sérült fájlnál üres lista)."""
    p = accounts_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    accounts = data.get("accounts") if isinstance(data, dict) else None
    return accounts if isinstance(accounts, list) else []


def save_accounts(accounts: list) -> None:
    """A fiókok kiírása (a mappa létrehozásával együtt)."""
    p = accounts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"version": 1, "accounts": accounts},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")


def normalize_email(email: str) -> str:
    """Az e-mail egységes alakja (kisbetű, levágott szóközök) — ez a kulcs."""
    return unicodedata.normalize("NFKC", str(email or "")).strip().lower()


def _hash_password(password: str, salt: bytes,
                   iterations: int = PBKDF2_ITERATIONS) -> str:
    """A jelszó PBKDF2-HMAC-SHA256 lenyomata hexben (só + kör-szám mellett)."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations).hex()


def _public(account: dict) -> dict:
    """A fiók KIFELÉ adható képe — jelszó-lenyomat és kulcsok nélkül."""
    return {
        "id": account.get("id"),
        "email": account.get("email"),
        "name": account.get("name"),
        "team": account.get("team"),
        "created_at": account.get("created_at"),
        "terms_version": account.get("terms_version"),
        "terms_accepted_at": account.get("terms_accepted_at"),
        "terms_ok": account.get("terms_version") == TERMS_VERSION,
    }


def _find(accounts: list, email: str) -> dict | None:
    key = normalize_email(email)
    for a in accounts:
        if normalize_email(a.get("email", "")) == key:
            return a
    return None


def _new_token(account: dict) -> str:
    """Új munkamenet-kulcs a fiókhoz (a lejártakat közben kitakarítja)."""
    now = _now()
    token = secrets.token_urlsafe(32)
    kept = []
    for t in account.get("tokens", []):
        try:
            if datetime.fromisoformat(t["expires_at"]) > now:
                kept.append(t)
        except Exception:
            continue
    kept.append({"token": token, "created_at": _iso(now),
                 "expires_at": _iso(now + timedelta(days=TOKEN_DAYS))})
    account["tokens"] = kept[-10:]  # legfeljebb 10 élő munkamenet fiókonként
    return token


def register(email: str, password: str, name: str = "",
             team: str = "", accept_terms: bool = False) -> dict:
    """Új fiók létrehozása — CSAK a feltételek elfogadásával.

    A feltételek elfogadása nem alapértelmezés: `accept_terms=False` esetén
    a fiók nem jön létre (a felületen a jelölőnégyzetet ki kell pipálni).
    Az elfogadott verzió és az időpont a fiókba kerül.

    Visszatérés: {"account": {...}, "token": "..."} — a token a belépett
    munkamenet kulcsa. Hiba esetén AccountError, magyar üzenettel.
    """
    email_n = normalize_email(email)
    if not _EMAIL_RE.match(email_n):
        raise AccountError("Érvényes e-mail címet adj meg.")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise AccountError(
            f"A jelszó legalább {MIN_PASSWORD_LEN} karakter legyen.")
    if not accept_terms:
        raise AccountError(
            "A fiók létrehozásához el kell fogadni a felhasználási "
            "feltételeket.")
    accounts = load_accounts()
    if _find(accounts, email_n) is not None:
        raise AccountError("Ezzel az e-mail címmel már van fiók.")
    salt = secrets.token_bytes(SALT_BYTES)
    now = _now()
    account = {
        "id": secrets.token_hex(8),
        "email": email_n,
        "name": str(name or "").strip()[:80],
        "team": str(team or "").strip()[:80],
        "salt": salt.hex(),
        "hash": _hash_password(password, salt),
        "iterations": PBKDF2_ITERATIONS,
        "created_at": _iso(now),
        "terms_version": TERMS_VERSION,
        "terms_accepted_at": _iso(now),
        "tokens": [],
    }
    token = _new_token(account)
    accounts.append(account)
    save_accounts(accounts)
    return {"account": _public(account), "token": token}


def login(email: str, password: str) -> dict:
    """Belépés e-mail + jelszóval.

    Visszatérés: {"account": {...}, "token": "..."} — az account
    "terms_ok" mezője mondja meg, kell-e még elfogadni a (megújult)
    feltételeket. Rossz adatnál AccountError (szándékosan nem árulja el,
    az e-mail vagy a jelszó volt-e hibás).
    """
    accounts = load_accounts()
    account = _find(accounts, email)
    ok = False
    if account is not None:
        try:
            salt = bytes.fromhex(account.get("salt", ""))
            iterations = int(account.get("iterations", PBKDF2_ITERATIONS))
            ok = hmac.compare_digest(
                _hash_password(password or "", salt, iterations),
                account.get("hash", ""))
        except Exception:
            ok = False
    if not ok:
        raise AccountError("Hibás e-mail cím vagy jelszó.")
    token = _new_token(account)
    save_accounts(accounts)
    return {"account": _public(account), "token": token}


def account_for_token(token: str) -> dict | None:
    """A munkamenet-kulcshoz tartozó fiók NYERS rekordja (vagy None).

    A lejárt kulcs nem érvényes. (Belső használatra — kifelé a _public
    kép megy, lásd me().)
    """
    if not token:
        return None
    now = _now()
    for a in load_accounts():
        for t in a.get("tokens", []):
            if not hmac.compare_digest(str(t.get("token", "")), str(token)):
                continue
            try:
                if datetime.fromisoformat(t["expires_at"]) <= now:
                    return None
            except Exception:
                return None
            return a
    return None


def me(token: str) -> dict | None:
    """A belépett fiók kifelé adható képe (vagy None érvénytelen kulcsnál)."""
    a = account_for_token(token)
    return _public(a) if a is not None else None


def accept_terms(token: str) -> dict:
    """A jelenlegi feltétel-verzió elfogadása a belépett fiókkal.

    Akkor kell, ha a feltételek szövege a fiók létrehozása óta új verziót
    kapott — a belépés ilyenkor "terms_ok": false-t ad vissza.
    """
    accounts = load_accounts()
    now = _now()
    for a in accounts:
        for t in a.get("tokens", []):
            if hmac.compare_digest(str(t.get("token", "")), str(token)):
                a["terms_version"] = TERMS_VERSION
                a["terms_accepted_at"] = _iso(now)
                save_accounts(accounts)
                return _public(a)
    raise AccountError("Nincs érvényes bejelentkezés.")


def logout(token: str) -> bool:
    """Kilépés: a munkamenet-kulcs érvénytelenítése (igaz, ha volt ilyen)."""
    accounts = load_accounts()
    found = False
    for a in accounts:
        kept = [t for t in a.get("tokens", [])
                if not hmac.compare_digest(str(t.get("token", "")),
                                           str(token))]
        if len(kept) != len(a.get("tokens", [])):
            found = True
            a["tokens"] = kept
    if found:
        save_accounts(accounts)
    return found


def change_password(token: str, old_password: str, new_password: str) -> dict:
    """Jelszócsere a belépett fiókon (a régi jelszó megadásával).

    A csere minden korábbi munkamenetet érvénytelenít, és új kulcsot ad —
    így az esetleg máshol nyitva maradt belépés megszűnik.
    """
    if len(new_password or "") < MIN_PASSWORD_LEN:
        raise AccountError(
            f"Az új jelszó legalább {MIN_PASSWORD_LEN} karakter legyen.")
    accounts = load_accounts()
    account = None
    for a in accounts:
        for t in a.get("tokens", []):
            if hmac.compare_digest(str(t.get("token", "")), str(token)):
                account = a
                break
        if account is not None:
            break
    if account is None:
        raise AccountError("Nincs érvényes bejelentkezés.")
    salt = bytes.fromhex(account.get("salt", ""))
    iterations = int(account.get("iterations", PBKDF2_ITERATIONS))
    if not hmac.compare_digest(
            _hash_password(old_password or "", salt, iterations),
            account.get("hash", "")):
        raise AccountError("A jelenlegi jelszó nem stimmel.")
    new_salt = secrets.token_bytes(SALT_BYTES)
    account["salt"] = new_salt.hex()
    account["hash"] = _hash_password(new_password, new_salt)
    account["iterations"] = PBKDF2_ITERATIONS
    account["tokens"] = []
    new_token = _new_token(account)
    save_accounts(accounts)
    return {"account": _public(account), "token": new_token}


def accounts_status() -> dict:
    """Van-e már fiók a gépen — a kliens ebből tudja, regisztrálni vagy
    belépni kell-e (első indításnál üres a lista)."""
    accounts = load_accounts()
    return {
        "count": len(accounts),
        "has_accounts": bool(accounts),
        "terms_version": TERMS_VERSION,
        "owner": OWNER_NAME,
    }
