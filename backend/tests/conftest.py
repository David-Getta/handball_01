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

os.environ.setdefault("HANDBALL_STORE_SYNC", "1")
# A feldolgozás végi háttér-előszámolás a teszteknél ki: a számláló-alapú
# tesztek (hányszor fut egy réteg) különben a háttérszállal versenyeznének.
os.environ.setdefault("HANDBALL_WARM_RESULTS", "0")
