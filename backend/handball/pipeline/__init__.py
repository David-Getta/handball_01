"""Feldolgozó pipeline: a [A]–[H] lépések (kalibráció, detektálás, követés,
csapatba sorolás, pálya-koordináta, becslés, statisztika) és az összefogó
`HandballPipeline`. A lépések most kommentált csontvázak; a valódi modellek
(YOLO, ByteTrack, OpenCV) lépésről lépésre helyettesíthetők be."""

from .pipeline import HandballPipeline, summarize

__all__ = ["HandballPipeline", "summarize"]
