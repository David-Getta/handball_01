/// Nagyítható nézet — touchpaddal (két ujjas csippentés) és egérrel
/// (Ctrl + görgő) is nagyítható-kicsinyíthető tartalom.
///
/// Viselkedés:
/// - touchpad-csippentés (vagy érintőkijelzős csípés): nagyítás a
///   csippentés középpontja körül; két ujjas húzás: mozgatás,
/// - Ctrl + egérgörgő: nagyítás a kurzor körül (görgő felfelé =
///   közelítés) — a sima görgő szándékosan érintetlen marad, hogy a
///   görgethető felületek viselkedése ne változzon,
/// - dupla kattintás/koppintás: vissza az alaphelyzetbe (1x).
///
/// A tartalom sosem szakad el a szélektől (a nagyított kép széle nem
/// úszhat beljebb a keretnél), és 1x alá nem kicsinyíthető.
library;

import "dart:math" as math;

import "package:flutter/gestures.dart";
import "package:flutter/material.dart";
import "package:flutter/services.dart";

class ZoomPanView extends StatefulWidget {
  final Widget child;

  /// Legnagyobb nagyítás (az alapméret szorzója).
  final double maxScale;

  const ZoomPanView({super.key, required this.child, this.maxScale = 6.0});

  @override
  State<ZoomPanView> createState() => _ZoomPanViewState();
}

class _ZoomPanViewState extends State<ZoomPanView> {
  double _scale = 1.0;
  Offset _offset = Offset.zero; // a tartalom eltolása képpontban

  // A csippentés kezdetekor rögzített állapot — a d.scale mindig a
  // gesztus KEZDETÉHEZ képest értendő, ezért innen számolunk.
  double _startScale = 1.0;
  Offset _startOffset = Offset.zero;
  Offset _startFocal = Offset.zero;

  /// Az eltolás határok közé szorítása: a nagyított tartalom széle nem
  /// úszhat a kereten belülre.
  Offset _clamp(Offset o, Size size) {
    final minX = size.width * (1.0 - _scale);
    final minY = size.height * (1.0 - _scale);
    return Offset(
      o.dx.clamp(minX, 0.0),
      o.dy.clamp(minY, 0.0),
    );
  }

  /// Nagyítás a megadott pont körül: a pont a művelet után is
  /// ugyanoda mutat a tartalomban.
  void _zoomAt(Offset focal, double factor, Size size) {
    final ns = (_scale * factor).clamp(1.0, widget.maxScale);
    final f = ns / _scale;
    final no = focal - (focal - _offset) * f;
    setState(() {
      _scale = ns;
      _offset = _clamp(no, size);
    });
  }

  void _reset() {
    setState(() {
      _scale = 1.0;
      _offset = Offset.zero;
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      final size = Size(c.maxWidth, c.maxHeight);
      return Listener(
        onPointerSignal: (e) {
          // Csak a Ctrl+görgő nagyít — a sima görgőt nem fogjuk el.
          if (e is! PointerScrollEvent ||
              !HardwareKeyboard.instance.isControlPressed) {
            return;
          }
          // Görgő felfelé (negatív dy) = közelítés; a exp() adja a
          // finom, sebesség-arányos lépésközt.
          final factor = math.exp(-e.scrollDelta.dy / 240.0);
          _zoomAt(e.localPosition, factor, size);
        },
        child: GestureDetector(
          // A scale-gesztus a touchpad csippentését és két ujjas
          // húzását is megkapja (Flutter 3.3+ trackpad-események).
          onScaleStart: (d) {
            _startScale = _scale;
            _startOffset = _offset;
            _startFocal = d.localFocalPoint;
          },
          onScaleUpdate: (d) {
            final ns =
                (_startScale * d.scale).clamp(1.0, widget.maxScale);
            final f = ns / _startScale;
            final no = _startFocal -
                (_startFocal - _startOffset) * f +
                (d.localFocalPoint - _startFocal);
            setState(() {
              _scale = ns;
              _offset = _clamp(no, size);
            });
          },
          onDoubleTap: _reset,
          child: ClipRect(
            child: Transform(
              transform: Matrix4.identity()
                ..translate(_offset.dx, _offset.dy)
                ..scale(_scale),
              child: SizedBox(
                width: size.width,
                height: size.height,
                child: widget.child,
              ),
            ),
          ),
        ),
      );
    });
  }
}
