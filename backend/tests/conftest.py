"""Közös teszt-beállítás.

A meccs-tár a motorban HÁTTÉRBEN töltődik a lemezről (lásd
`api.app._MatchStore`): a motor azonnal válaszol, a lista pedig
fokozatosan telik meg. A tesztek zöme viszont "fájlt ír → app-ot csinál
→ azonnal olvas" mintával dolgozik, és a részleges listától véletlenül
bukna. Ezért a tesztekben a SZINKRON (blokkoló) betöltés az alap; a
háttér-viselkedést a `test_store_background.py` külön, kifejezetten
kikapcsolt kapcsolóval teszteli.
"""
import os

import pytest

os.environ.setdefault("HANDBALL_STORE_SYNC", "1")
# A feldolgozás végi háttér-előszámolás a teszteknél ki: a számláló-alapú
# tesztek (hányszor fut egy réteg) különben a háttérszállal versenyeznének.
os.environ.setdefault("HANDBALL_WARM_RESULTS", "0")


@pytest.fixture(autouse=True)
def _munkakonyvtar_or(request):
    """ŐR: egyetlen teszt sem hagyhatja megváltoztatva a munkakönyvtárat.

    Több őr-teszt a forrást a backend mappából olvassa; egy
    xdist-munkásban a megváltozott munkakönyvtár a KÉSŐBBI teszteket
    buktatta (FileNotFoundError), látszólag véletlenszerűen — a
    forrás-olvasók azóta `__file__`-alapúak, ez az őr pedig azt a tesztet
    nevezi meg, amelyik elmozdítja a könyvtárat, és visszaállítja."""
    try:
        elott = os.getcwd()
    except FileNotFoundError:
        elott = None
    yield
    try:
        utana = os.getcwd()
    except FileNotFoundError:
        utana = "(törölt könyvtár)"
    if elott is not None and utana != elott:
        os.chdir(elott)
        pytest.fail(f"{request.node.nodeid} megváltoztatta a "
                    f"munkakönyvtárat: {elott} → {utana}")
