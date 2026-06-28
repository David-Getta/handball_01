"""HTTP API a kliens felé. A FastAPI app a `create_app()`-ből jön létre (a FastAPI
importja lusta, hogy a csomag függőség nélkül is importálható maradjon)."""

from .app import create_app

__all__ = ["create_app"]
