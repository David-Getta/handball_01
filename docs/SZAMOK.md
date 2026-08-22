# Projekt-számok (generált tény-lap)

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.project_facts`

Ezek a számok a kódbázisból, statikusan számoltak — a pályázati és
bemutató anyagok ide hivatkoznak, hogy az állításaik ellenőrizhetők
legyenek. A teszt-csomag őre nem engedi elavulni.

| Mérték | Érték | Miből számolva |
|---|---:|---|
| Elemző réteg (meccs-csomag) | **491** | `_layer("...")` regisztrációk az `api/app.py`-ban |
| Automata teszt | **1779** | `def test_*` függvények a `backend/tests/`-ben |
| Meccsterv-szabály | **444** | a legnagyobb sorszámozott szabály a `pipeline/scouting.py`-ban |
| Edzés-szabály | **464** | a legnagyobb sorszámozott szabály a `pipeline/training.py`-ban |
| Kliens-csempe (felderítés) | **464** | csempe-sorok a `client/lib/ui/scouting_screen.dart`-ban |
| Pipeline-modul | **57** | `.py` fájlok a `backend/handball/pipeline/`-ban |

A rétegek tételes listája (mit mér melyik):
[`docs/RETEG_KATALOGUS.md`](RETEG_KATALOGUS.md).
