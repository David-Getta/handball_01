"""Hatókörös elsődleges gyorsítótár — egy mérés egyszer fusson le.

A rétegek szándékosan önállóak: mindegyik maga hívja meg az alap-
méréseket (lövés-felismerés, poszt-becslés, létszám-idővonal), hogy egy
réteg hibája ne vigye el a többit. Ennek ára van: egyetlen edzői
összefoglaló futása közben a `detect_shots` négyszáznál is többször
lefut UGYANARRA a meccsre, ugyanazzal az eredménnyel.

Ez a modul egy KIMONDOTT HATÓKÖRT ad ehhez. A `primitive_cache(match)`
blokkon belül az alap-mérések eredménye csak egyszer számolódik ki, a
blokk elhagyásakor pedig a gyorsítótár nyomtalanul eltűnik. A rétegek
kódja változatlan marad — nem kell tudniuk a gyorsítótárról.

Miért biztonságos:

- **Hatókörös, nem globális.** Blokk nélkül minden hívás pontosan úgy
  fut, mint eddig; hosszú életű, elavuló gyorsítótár nem keletkezik.
- **A szerep-jelölés a kulcs része.** A `detect_goalkeepers` BELEÍR a
  meccsbe (`p.role = "kapus"`), és több mérés (pl. a `detect_shots`)
  olvassa a szerepet. Ezért a gyorsítótár-kulcs tartalmazza a
  szerep-jelölés nemzedékszámát: amikor a kapus-jelölés ténylegesen
  megváltozik, a korábbi bejegyzések nem használhatók, a mérés újra
  lefut. Így a hatókör NEM változtat egyetlen eredményt sem — pontosan
  azt adja, amit gyorsítótár nélkül kapnánk, csak kevesebbszer számol.
- **Másolatot adunk vissza.** A hívók néha megjelölik az eredményt
  (pl. a gólpassz beírása a gól detail-jébe), ezért minden kiadott
  érték friss másolat: egy réteg jelölése nem szivároghat át a
  következőbe.
- **A meccs objektumhoz kötött.** Ha a blokkon belül más meccsre
  hívnak alap-mérést, az gyorsítótár nélkül, normálisan fut le.
"""

from __future__ import annotations

import contextvars
import functools
from contextlib import contextmanager
from dataclasses import is_dataclass, replace
from typing import Callable, Optional

from ..models.tracking import Match

# A hatókör állapota: {"match": Match, "store": dict} — vagy None,
# ha épp nincs nyitott blokk (ilyenkor minden a régi úton fut).
_SCOPE: contextvars.ContextVar = contextvars.ContextVar(
    "handball_primitive_cache", default=None)

_MISS = object()


def _arg_key(value):
    """Egy hívás-argumentum kulcsa — konfigurációs objektumokra is működik.

    A `__dict__`-es ág szándékos: a `TacticsConfig` (és bármely későbbi
    beállítás-osztály) mezőiből képez kulcsot, tehát két különböző
    beállítás sosem olvassa egymás eredményét.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (tuple, list)):
        return tuple(_arg_key(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _arg_key(v)) for k, v in value.items()))
    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        # Az ALAPÉRTELMEZETT beállítás kulcsa ugyanaz, mint a None-é.
        # A rétegek `config=None` esetén maguk állítanak elő egy
        # alapértelmezett TacticsConfig-ot, tehát a két hívás
        # SZÓ SZERINT ugyanazt számolja — külön kulccsal viszont
        # kétszer futna le. Mérve: az edzői összefoglalóban a
        # teendő-rangsor emiatt számolódott újra.
        try:
            if data == getattr(type(value)(), "__dict__", None):
                return None
        except Exception:
            pass                       # kötelező mezős osztály: marad a régi
        return (type(value).__name__,
                tuple(sorted((k, repr(v)) for k, v in data.items())))
    return repr(value)


# A védő-másolatok. Mindegyik a felszínt másolja: annyit, amennyit a
# hívók ténylegesen jelölhetnek (lásd a modul-docstringet).

def copy_events(events: list) -> list:
    """Esemény-lista másolata (a hívók jelölik, pl. gólpasszal)."""
    return [replace(e) for e in events]


def copy_rows(rows: list) -> list:
    """Dict-sorok listájának másolata (idővonalak, szakasz-listák)."""
    return [dict(r) if isinstance(r, dict) else r for r in rows]


def copy_by_id(data: dict) -> dict:
    """{azonosító: adatosztály} másolata (pl. játékos-statisztika)."""
    return {k: (replace(v) if is_dataclass(v) and not isinstance(v, type)
                else v)
            for k, v in (data or {}).items()}


def copy_sides(data: dict) -> dict:
    """{oldal: {kulcs: szám/szöveg}} másolata — a rétegek leggyakoribb
    alakja (csapatonkénti mérés-szótár).

    A `copy_nested` ennél egy szinttel mélyebbre megy; itt a belső
    értékek skalárok, nem szótárak.
    """
    return {side: dict(rec or {}) for side, rec in (data or {}).items()}


def copy_nested(data: dict) -> dict:
    """{oldal: {azonosító: dict}} kétszintű másolata (poszt-becslés)."""
    return {side: {tid: dict(rec) for tid, rec in (per or {}).items()}
            for side, per in (data or {}).items()}


def mark_roles_changed() -> None:
    """Jelzés: a meccs szerep-jelölése (kapus) ténylegesen megváltozott.

    A nyitott hatókör nemzedékszáma lép egyet, így a korábbi mérések
    bejegyzései nem használhatók újra — a szerepet olvasó mérések
    (pl. `detect_shots`) újraszámolnak. Hatókör nélkül nem csinál semmit.
    """
    scope = _SCOPE.get()
    if scope is not None:
        scope["roles"] += 1


def active_match() -> Optional[Match]:
    """A jelenleg nyitott hatókör meccse (vagy None, ha nincs blokk)."""
    scope = _SCOPE.get()
    return scope["match"] if scope else None


def _mark_goalkeepers(match: Match) -> None:
    """Kapus-jelölés a hatókör NYITÁSAKOR — hogy az eredmény ne függjön
    a kiértékelés SORRENDJÉTŐL.

    A `detect_goalkeepers` beleír a meccsbe (`role = "kapus"`), és több
    mint ötven réteg a szerepből dolgozik (a kapust nem számolja
    védőnek, birtokosnak, lövőnek). Ha a jelölés csak akkor történik
    meg, amikor épp egy kapus-réteg lefut, ugyanaz a réteg MÁS számot
    ad attól függően, hányadikként értékeltük ki — ezt mérte a
    docs/SORREND_FUGGES.md (50 érintett réteg).

    A jelölés idempotens, és csak tényleges változásnál jelez a
    gyorsítótárnak, tehát az ismételt hívás nem dob el semmit. Hibára
    NEM esünk szét: ha a felismerés elszáll, a hatókör attól még nyílik
    (egy réteg hibája nem viheti el a többit).
    """
    try:
        from .goalkeeper import detect_goalkeepers
        detect_goalkeepers(match)
    except Exception:
        pass


@contextmanager
def primitive_cache(match: Match):
    """Hatókör, amelyen belül az alap-mérések egyszer futnak le.

    Újra-belépő: ha ugyanarra a meccsre már nyitva van egy blokk, a
    belső blokk nem nyit újat (a külső gyorsítótárat használja), így a
    beágyazott aggregátorok (edzői összefoglaló → edzés-fókusz) is
    osztoznak a méréseken.
    """
    scope = _SCOPE.get()
    if scope is not None and scope["match"] is match:
        yield  # újra-belépés: a külső blokk gyorsítótárát használjuk
        return

    token = _SCOPE.set({"match": match, "store": {}, "frames": {}, "roles": 0})
    try:
        _mark_goalkeepers(match)
        yield
    finally:
        _SCOPE.reset(token)


def cached(name: str, match: Match, config, compute: Callable,
           copy: Optional[Callable] = None):
    """A `compute()` eredménye a hatókörön belül csak egyszer számolódik.

    Nyitott blokk nélkül (vagy más meccsre) egyszerűen lefuttatja a
    `compute`-ot — a viselkedés ilyenkor bitre azonos a korábbival.
    A `copy` az eredmény védő-másolata (lásd a modul-docstringet).
    """
    scope = _SCOPE.get()
    if scope is None or scope["match"] is not match:
        return compute()
    key = (name, _arg_key(config), scope["roles"])
    store = scope["store"]
    val = store.get(key, _MISS)
    if val is _MISS:
        val = compute()
        store[key] = val
    return copy(val) if copy is not None else val


def memoize_primitive(name: str, copy: Optional[Callable] = None):
    """Dekorátor: a mérés a hatókörön belül meccsenként egyszer fut le.

    A becsomagolt függvény ELSŐ paramétere a meccs; a többi argumentum
    a gyorsítótár-kulcs része, tehát más beállítással hívva külön
    eredmény születik. Hatókör nélkül a dekorátor nem csinál semmit —
    a függvény pontosan úgy fut, mint korábban.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(match, *args, **kwargs):
            return cached(
                name, match, (args, tuple(sorted(kwargs.items()))),
                lambda: fn(match, *args, **kwargs), copy=copy)
        wrapper.uncached = fn  # méréshez/teszthez: a nyers függvény
        return wrapper
    return deco


def open_scope(match: Match):
    """Hatókör kézi nyitása — ott, ahol a `with` nem fér a szerkezetbe.

    A visszaadott jelzőt a `close_scope`-nak kell átadni (a hívó
    `finally` ágában). Ha ugyanarra a meccsre már nyitva van hatókör,
    None-t ad vissza — ilyenkor a `close_scope` nem csinál semmit.
    """
    scope = _SCOPE.get()
    if scope is not None and scope["match"] is match:
        return None
    token = _SCOPE.set({"match": match, "store": {}, "frames": {},
                        "roles": 0})
    _mark_goalkeepers(match)
    return token


def close_scope(token) -> None:
    """A `open_scope`-pal nyitott hatókör bezárása (None-ra nem művelet)."""
    if token is not None:
        _SCOPE.reset(token)


def cached_frame(name: str, frame, config, compute: Callable):
    """Kocka-szintű memoizálás — a legforróbb, kockánkénti mérésekhez.

    A birtoklás-számítás (`ball_holder`, `possession_team`,
    `classify_phase`) kockánként fut, és egy nagy összeállítás alatt
    ugyanarra a kockára több százszor. Ez a segéd a nyitott hatókörön
    belül kockánként egyszer számol.

    A bejegyzés MAGÁT A KOCKÁT is eltárolja: így a kocka nem
    szemetelődhet ki a bejegyzés alatt, tehát az azonosítója sem
    használódhat újra egy másik kockára (a hatókörön belül keletkező
    ideiglenes kockák miatt fontos). A visszaadott érték nem másolat —
    ugyanaz az objektum, amit gyorsítótár nélkül is kapnánk (játékos a
    kockából, illetve érték-típusú csapat/fázis).
    """
    scope = _SCOPE.get()
    if scope is None:
        return compute()
    key = (name, id(frame),
           getattr(config, "possession_radius_m", None),
           getattr(config, "home_attacks_positive", None))
    entry = scope["frames"].get(key)
    if entry is not None and entry[0] is frame:
        return entry[1]
    val = compute()
    scope["frames"][key] = (frame, val)
    return val
