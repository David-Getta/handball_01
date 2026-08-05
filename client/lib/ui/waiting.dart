/// Várakozó nézet — mondjuk meg, MIRE várunk, és MEDDIG.
///
/// Egy csupasz pörgettyű nem mond semmit. A felderítő jelentés több
/// meccsen percekig fut; a felhasználó ilyenkor nem tudja eldönteni,
/// hogy a program dolgozik-e, vagy megakadt — és jellemzően megnyomja
/// mégegyszer, vagy kilép.
///
/// Ez a nézet három dolgot ad a pörgettyű mellé:
///   1. MIT csinálunk most (egy mondat, edzői nyelven),
///   2. mennyi ideig szokott tartani (`hint`) — ha percekről van szó,
///      azt ki KELL mondani, mert különben hibának látszik,
///   3. mennyi ideje fut (élő másodperc-számláló) — ez a bizonyíték,
///      hogy a program nem fagyott le.
library;

import "dart:async";

import "package:flutter/material.dart";

import "../theme/app_theme.dart";

/// Ennyi másodperc után jelenik meg az eltelt idő.
///
/// Rövid műveleteknél a számláló csak zaj; a "megakadt?" kérdés
/// nagyjából ennyi várakozás után merül fel.
const int kElapsedAfterS = 3;

/// Ennyi idő fölött külön megnyugtató sort is kiírunk.
const int kLongWaitS = 30;

/// Várakozó nézet felirattal.
///
/// - [what]: mi történik most ("Felderítő jelentés készül…").
/// - [hint]: mennyi ideig szokott tartani, vagy miért lassú. Percekben
///   mérhető műveletnél NE hagyd üresen.
/// - [icon]: a művelethez illő ikon (a pörgettyű mellett).
class WaitingView extends StatefulWidget {
  const WaitingView(this.what, {this.hint, this.icon, super.key});

  final String what;
  final String? hint;
  final IconData? icon;

  @override
  State<WaitingView> createState() => _WaitingViewState();
}

class _WaitingViewState extends State<WaitingView> {
  final Stopwatch _watch = Stopwatch()..start();
  Timer? _tick;
  int _seconds = 0;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() => _seconds = _watch.elapsed.inSeconds);
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  /// Az eltelt idő embernek: "12 mp", "2:05".
  static String elapsedLabel(int seconds) {
    if (seconds < 60) return "$seconds mp";
    final m = seconds ~/ 60, s = seconds % 60;
    return "$m:${s.toString().padLeft(2, "0")}";
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        SizedBox(
          width: 44, height: 44,
          child: Stack(alignment: Alignment.center, children: [
            const CircularProgressIndicator(
                strokeWidth: 3, color: AppColors.accent),
            if (widget.icon != null)
              Icon(widget.icon, size: 18, color: AppColors.textFaint),
          ]),
        ),
        const SizedBox(height: AppSpacing.lg),
        Text(widget.what, style: AppText.value.copyWith(fontSize: 16),
            textAlign: TextAlign.center),
        if (widget.hint != null) ...[
          const SizedBox(height: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Text(widget.hint!, style: AppText.label,
                textAlign: TextAlign.center),
          ),
        ],
        if (_seconds >= kElapsedAfterS) ...[
          const SizedBox(height: AppSpacing.md),
          Text("fut: ${elapsedLabel(_seconds)}",
              style: AppText.label.copyWith(color: AppColors.textFaint)),
        ],
        if (_seconds >= kLongWaitS) ...[
          const SizedBox(height: 6),
          Text("Hosszabb felvételnél ez normális — hagyd futni.",
              style: AppText.label.copyWith(color: AppColors.textFaint)),
        ],
      ]),
    );
  }
}
