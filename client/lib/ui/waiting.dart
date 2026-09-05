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
import "anim.dart";

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

class _WaitingViewState extends State<WaitingView>
    with SingleTickerProviderStateMixin {
  final Stopwatch _watch = Stopwatch()..start();
  Timer? _tick;
  int _seconds = 0;

  /// Lélegző pulzus a pörgettyű közepén: a mozgás maga a "dolgozom" jel.
  late final AnimationController _pulse = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1400));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Csökkentett mozgásnál a lélegző ragyogás megáll egy középső
    // állapotban: a pörgettyű és az élő másodperc-számláló továbbra is
    // elmondja, hogy a program dolgozik.
    if (reduceMotion(context)) {
      _pulse.stop();
      _pulse.value = 0.5;
    } else if (!_pulse.isAnimating) {
      _pulse.repeat(reverse: true);
    }
  }

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
    _pulse.dispose();
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
          width: 52, height: 52,
          child: Stack(alignment: Alignment.center, children: [
            // Puha akcentus-ragyogás a pörgettyű mögött, lélegző ütemben.
            FadeTransition(
              opacity: Tween<double>(begin: 0.10, end: 0.30).animate(
                  CurvedAnimation(
                      parent: _pulse, curve: Curves.easeInOut)),
              child: Container(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                        color: AppColors.accent.withOpacity(0.8),
                        blurRadius: 26,
                        spreadRadius: 2),
                  ],
                ),
              ),
            ),
            const SizedBox(
              width: 44, height: 44,
              child: CircularProgressIndicator(
                  strokeWidth: 3, color: AppColors.accent),
            ),
            if (widget.icon != null)
              ScaleTransition(
                scale: Tween<double>(begin: 0.92, end: 1.06).animate(
                    CurvedAnimation(
                        parent: _pulse, curve: Curves.easeInOut)),
                child: Icon(widget.icon, size: 18,
                    color: AppColors.textSecondary),
              ),
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
