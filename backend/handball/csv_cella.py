"""A CSV-exportok (Excel-barát: pontosvessző, UTF-8 BOM) szöveges
cellái — nevek, csapatok, megjegyzések.

Két veszély ellen: (1) a pontosvesszőt, idézőjelet vagy sortörést
tartalmazó név szétcsúsztatja az oszlopokat; (2) a "="-vel, "+"-szal,
"-"-szal, "@"-cal (vagy tabulátorral, kocsivissza-jellel) kezdődő szöveget
az Excel KÉPLETKÉNT futtatja (CSV-befecskendezés: egy importált könyvtár
neve is lehet ilyen). A képlet elé aposztróf kerül — az Excel szövegként
mutatja, az aposztróf nem látszik.

Számot (tizedesvesszős mérőszámot) NE ezen át írj: a "-0,3" így szöveg
lenne.
"""
from __future__ import annotations

# A képletként induló cella első jelei (OWASP: CSV Injection).
KEPLET_JELEK = ("=", "+", "-", "@", "\t", "\r")


def keplet_vedett(v) -> str:
    """A szöveg, a képletként induló elé aposztróffal (a csv.writer
    idéz — ott ennyi kell)."""
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(KEPLET_JELEK) else s


def csv_cella(v) -> str:
    """Kézzel fűzött (pontosvesszős) CSV szöveges cellája: képlet-védve,
    és ha pontosvesszőt, idézőjelet vagy sortörést tartalmaz, idézőjelek
    közt (a belső idézőjel kettőzve)."""
    s = keplet_vedett(v)
    if any(c in s for c in (";", '"', "\n", "\r")):
        s = '"' + s.replace('"', '""') + '"'
    return s
