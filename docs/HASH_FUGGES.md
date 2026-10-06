# Hash-függés (generált jelentés)

A `python3 -m scripts.hash_sensitivity` írja — kézzel ne szerkeszd.

Minden regisztrált réteg egy friss, szimulált meccsen (600 mp, mag: 3), 3 külön folyamatban, különböző hash-keveréssel (PYTHONHASHSEED = 1, 4, 7). Ha egy réteg kimenete eltér, ugyanaz a meccs két indításkor más eredményt ad.

- összevetve: 513 réteg
- hash-függő: 0
- nem mérhető (hibára futott): 0

A hash-függő lista üres — és annak is kell maradnia.
