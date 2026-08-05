# Projekt-számok (generált tény-lap)

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.project_facts`

Ezek a számok a kódbázisból, statikusan számoltak — a pályázati és
bemutató anyagok ide hivatkoznak, hogy az állításaik ellenőrizhetők
legyenek. A teszt-csomag őre nem engedi elavulni.

| Mérték | Érték | Miből számolva |
|---|---:|---|
| Elemző réteg (meccs-csomag) | **310** | `_layer("...")` regisztrációk az `api/app.py`-ban |
| Automata teszt | **1280** | `def test_*` függvények a `backend/tests/`-ben |
| Meccsterv-szabály | **262** | a legnagyobb sorszámozott szabály a `pipeline/scouting.py`-ban |
| Edzés-szabály | **283** | a legnagyobb sorszámozott szabály a `pipeline/training.py`-ban |
| Kliens-csempe (felderítés) | **283** | csempe-sorok a `client/lib/ui/scouting_screen.dart`-ban |
| Pipeline-modul | **56** | `.py` fájlok a `backend/handball/pipeline/`-ban |

A rétegek tételes listája (mit mér melyik):
[`docs/RETEG_KATALOGUS.md`](RETEG_KATALOGUS.md).
