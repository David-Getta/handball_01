"""
Tesztek az inferencia-eszköz kiválasztására (CUDA → MPS → CPU).

A torch-ot NEM igényli: hamis torch-modult teszünk a sys.modules-ba, így a CI
teszt-környezetben (torch nélkül) is fut.

Futtatás:
    python tests/test_device.py
"""

from __future__ import annotations

import os
import sys
import types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.process_video import _pick_device


def _fake_torch(cuda: bool, mps: bool):
    """Hamis torch-modul a kívánt eszköz-elérhetőséggel."""
    t = types.ModuleType("torch")
    t.cuda = types.SimpleNamespace(is_available=lambda: cuda)
    t.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: mps))
    return t


def _with_torch(fake, fn):
    orig = sys.modules.get("torch")
    sys.modules["torch"] = fake
    try:
        return fn()
    finally:
        if orig is not None:
            sys.modules["torch"] = orig
        else:
            del sys.modules["torch"]


def test_cuda_first():
    """Ha CUDA elérhető, azt választja (akkor is, ha MPS is van)."""
    assert _with_torch(_fake_torch(cuda=True, mps=True), _pick_device) == "cuda"


def test_mps_on_apple_silicon():
    """CUDA nélkül, Apple GPU-val: MPS (M1..M5 Mac-ek)."""
    assert _with_torch(_fake_torch(cuda=False, mps=True), _pick_device) == "mps"


def test_cpu_fallback():
    """Se CUDA, se MPS: CPU."""
    assert _with_torch(_fake_torch(cuda=False, mps=False), _pick_device) == "cpu"


def test_no_torch_at_all():
    """Ha a torch importja hibázik, CPU-t ad (nem dől el)."""
    broken = types.ModuleType("torch")
    # nincs cuda attribútum → AttributeError az is_available hívásnál → except-ág
    assert _with_torch(broken, _pick_device) == "cpu"


def test_real_environment_returns_valid():
    """A valódi környezetben is a három érvényes érték egyike jön."""
    assert _pick_device() in ("cuda", "mps", "cpu")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)
