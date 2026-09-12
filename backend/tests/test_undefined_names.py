"""
Definiálatlan nevek őre — a "némán semmit nem csináló kód" ellen.

Miért kell: a motor rétegeit és szabályait `try/except Exception: pass`
védi, hogy egy elromló réteg ne vigye el a többit. Ennek az ára, hogy
egy ELGÉPELT VÁLTOZÓNÉV is elveszik: a NameError-t elnyeli a védelem, a
kód némán semmit nem csinál, és a tesztek zöldek maradnak — különösen,
ha az adott ág a mintameccsen amúgy sem futna le.

Pontosan ez történt öt hajrá-edzésszabállyal: `focus[side]`-ra írtak az
`out[side]` helyett, és soha nem futottak le. Futtatással nem volt
elkapható; statikus elemzéssel harminc másodperc.

Az ellenőrzés KONZERVATÍV: a Python hatókör-szabályait követi
(függvény-, lambda-, osztály-hatókör külön), és csak azt jelzi, ami
sehol nincs kötve — sem lokálisan, sem a körülölelő hatókörökben, sem
modul-szinten, sem beépítettként. Nincs külső függősége.

Futtatás:
    python -m pytest tests/test_undefined_names.py
"""

from __future__ import annotations

import ast
import builtins
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BUILTINS = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__builtins__",
}
_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = _FUNC + (ast.ClassDef, ast.Lambda)


def _args(node) -> set:
    a = node.args
    out = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    if a.vararg:
        out.add(a.vararg.arg)
    if a.kwarg:
        out.add(a.kwarg.arg)
    return out


def _bound(body) -> set:
    """A törzsben KÖTÖTT nevek.

    Beágyazott függvény/osztály/lambda TÖRZSÉBE nem lépünk be (saját
    hatókör), csak a nevüket vesszük fel.
    """
    names: set = set()
    stack = list(body)
    while stack:
        n = stack.pop()
        if isinstance(n, _FUNC + (ast.ClassDef,)):
            names.add(n.name)
            continue
        if isinstance(n, ast.Lambda):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
        stack.extend(ast.iter_child_nodes(n))
    return names


def _loads(body) -> list:
    """(sor, név) párok a törzsben LOAD-olt nevekre, beágyazott
    hatókörök nélkül."""
    out: list = []
    stack = list(body)
    while stack:
        n = stack.pop()
        if isinstance(n, _SCOPES):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.append((n.lineno, n.id))
        stack.extend(ast.iter_child_nodes(n))
    return out


def _walk_scope(node, outer: set, hibak: list, fajl: str) -> None:
    if isinstance(node, ast.Module):
        scope = outer | _bound(node.body)
        body = node.body
    elif isinstance(node, ast.Lambda):
        # A törzsében lévő értelmezés/generátor célváltozói a
        # kifejezésen BELÜL látszanak.
        scope = outer | _args(node) | _bound([node.body])
        body = [node.body]
    elif isinstance(node, ast.ClassDef):
        scope = outer | _bound(node.body)
        body = node.body
    else:
        scope = outer | _args(node) | _bound(node.body)
        body = node.body

    for ln, name in _loads(body):
        if name not in scope and name not in _BUILTINS:
            hibak.append(f"{fajl}:{ln}: {name}")

    # Az OSZTÁLYTEST nem látszik a metódusokból (Python-szabály).
    kulso = outer if isinstance(node, ast.ClassDef) else scope
    stack = list(body)
    while stack:
        n = stack.pop()
        if isinstance(n, _SCOPES):
            _walk_scope(n, kulso, hibak, fajl)
            continue
        stack.extend(ast.iter_child_nodes(n))


def _scan(gyoker: Path) -> list:
    hibak: list = []
    for py in sorted(gyoker.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:                       # nem a mi dolgunk
            continue
        _walk_scope(tree, set(), hibak, str(py.relative_to(gyoker.parent)))
    return sorted(set(hibak))


def test_nincs_definialatlan_nev_a_motorban():
    """Egy elgépelt változónév a védett ágakban NÉMÁN nem csinál semmit.

    A rétegeket és a szabályokat `try/except Exception: pass` védi
    (helyesen — egy elromló réteg ne vigye el a többit), ezért a
    NameError elvész, és a kód csendben kimarad a jelentésből. Öt
    hajrá-edzésszabállyal pontosan ez történt.
    """
    backend = Path(__file__).resolve().parent.parent
    hibak = _scan(backend / "handball") + _scan(backend / "scripts")
    assert not hibak, (
        "definiálatlan névre hivatkozó kód (a try/except elnyelné a "
        "NameError-t, és a kód némán kimaradna): " + "; ".join(hibak))


def test_az_or_tenyleg_elkapja_a_hibat():
    """Az őr, ami nem tud elbukni, semmit nem ér."""
    forras = (
        "def f(side):\n"
        "    out = {}\n"
        "    try:\n"
        "        focus[side].append('x')\n"   # `focus` sehol nincs kötve
        "    except Exception:\n"
        "        pass\n"
        "    return out\n"
    )
    hibak: list = []
    _walk_scope(ast.parse(forras), set(), hibak, "proba.py")
    assert any("focus" in h for h in hibak), hibak


def test_az_or_nem_riaszt_a_szabalyos_kodra():
    """Beágyazott függvény, lambda, értelmezés, except-név, global —
    ezek MIND szabályosak, és nem szabad riasztaniuk."""
    forras = (
        "import math\n"
        "OSSZ = 3\n"
        "def kulso(a, *args, **kw):\n"
        "    b = a + OSSZ\n"
        "    def belso(c):\n"
        "        return b + c + math.pi\n"
        "    rendezve = sorted([1, 2], key=lambda kv: -kv)\n"
        "    parok = {x: y for x, y in [(1, 2)]}\n"
        "    with open('/dev/null') as fh:\n"
        "        fh.read()\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError as e:\n"
        "        print(e)\n"
        "    return belso(1), rendezve, parok, args, kw\n"
    )
    hibak: list = []
    _walk_scope(ast.parse(forras), set(), hibak, "proba.py")
    assert not hibak, hibak
