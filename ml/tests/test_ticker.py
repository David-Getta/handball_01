"""A liveticker-feldolgozás: kinyerés, helyzet-kulcsszavak, párosítás az eredményjelzővel."""

from hbd.ticker import align, helyzet, parse_sportschau

MD = """- 3.

16:10

[Valaki](x)

**Tor für Gast, 1:2 durch Bea Gast**

Gast trifft per Tempogegenstoß.

- 2.

16:08

**7-Meter verworfen von Ana Heim (Heim)**

Der Torwart pariert.

- 2.

16:08

**Tor für Gast, 1:1 durch Cili Gast**

Vom Kreis zum Ausgleich, nach einem Abpraller.

- 1.

16:07

**Tor für Heim, 1:0 durch Ana Heim**

Heim trifft aus dem Rückraum.

- 1.

16:05

**Spielbeginn**
"""

SB = {"golok": [
    {"csapat": "hazai", "t_tol": 100.0, "t_ig": 101.0, "allas_utana": [1, 0]},
    {"csapat": "vendeg", "t_tol": 160.0, "t_ig": 161.0, "allas_utana": [1, 1]},
    {"csapat": "vendeg", "t_tol": 230.0, "t_ig": 231.0, "allas_utana": [1, 2]},
]}

ROSTER = {"hazai": {"jatekosok": [{"mez": 7, "nev": "Ana Heim", "poszt": "atlovo"}]},
          "vendeg": {"jatekosok": [{"mez": 3, "nev": "Bea Gast", "poszt": "szelso"},
                                   {"mez": 5, "nev": "Cili Gast", "poszt": "beallo"}]}}


def test_helyzet_kulcsszavak_es_sorrend():
    assert helyzet("aus dem Rückraum")[0] == "atlovo"
    assert helyzet("vom Kreis")[0] == "beallo"
    assert helyzet("von Rechtsaußen")[0] == "szelso"
    assert helyzet("Hornke von der Siebenmeterlinie")[0] == "hetes"
    # az indítás erősebb, mint a hely
    assert helyzet("Tempogegenstoß von Linksaußen")[0] == "inditas"
    assert helyzet("Und wieder trifft er.") == (None, None)


def test_kinyeres_idorendben():
    ev = parse_sportschau(MD, "Heim")
    assert [e["tipus"] for e in ev] == ["gol", "gol", "hetes_kihagyva", "gol"]
    assert ev[0] == {**ev[0], "csapat": "hazai", "allas": [1, 0], "jatekos": "Ana Heim", "perc": 1,
                     "ora": "16:07", "helyzet": "atlovo", "kipattano": False}
    assert ev[1]["helyzet"] == "beallo" and ev[1]["kipattano"] is True
    assert ev[2]["csapat"] == "hazai" and ev[2]["helyzet"] == "hetes"
    assert ev[3]["helyzet"] == "inditas"


def test_parositas_a_csapat_gol_sorszamaval():
    res = align(parse_sportschau(MD, "Heim"), SB, ROSTER)
    gols = [e for e in res["esemenyek"] if e["tipus"] == "gol"]
    assert res["parositott_golok"] == 3 and res["allas_eltero"] == []
    assert [(e["t_tol"], e["t_ig"]) for e in gols] == [(100.0, 101.0), (160.0, 161.0), (230.0, 231.0)]
    assert [e["poszt_keretbol"] for e in gols] == ["atlovo", "beallo", "szelso"]


def test_elteres_az_allasban_jelezve():
    md = MD.replace("1:1 durch Cili", "1:3 durch Cili")
    res = align(parse_sportschau(md, "Heim"), SB, ROSTER)
    assert res["allas_eltero"] == [{"ticker": [1, 3], "sorszam": 1}]
