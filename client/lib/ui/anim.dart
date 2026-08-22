/// Közös animációs eszköztár — az app "élő" érzete egy helyről.
///
/// Három kicsi, mindenhol újrahasznált építőelem:
///  - [FadeSlideIn]: belépő animáció (áttűnés + finom felfelé úszás),
///    listákban lépcsőzve (`index`) — az első kirajzolásnál játszik le
///    egyszer, utána nem zavar.
///  - [CountUp]: szám-felpörgetés a statisztika-számokhoz — a szem a
///    mozgásra néz oda, a szám "megérkezik".
///  - [HoverLift]: asztali hover-emelés kártyákhoz (finom skálázás +
///    akcentus-keret) — jelzi, hogy az elem kattintható.
///
/// Mindhárom beépített Flutter-primitívekre épül (TweenAnimationBuilder,
/// AnimatedContainer) — nincs külső csomag, nincs vezérlő-életciklus.
library;

import "package:flutter/material.dart";

import "../theme/app_theme.dart";

/// Belépő animáció: áttűnés + 12 px felfelé úszás. Listákban az `index`
/// lépcsőzteti (30 ms/elem, legfeljebb 12 lépcső — a hosszú lista vége ne
/// várjon fél percet). Egyszer játszik le, az elem kulcsa szerint.
class FadeSlideIn extends StatelessWidget {
  final Widget child;
  final int index;
  final Duration duration;

  const FadeSlideIn({
    super.key,
    required this.child,
    this.index = 0,
    this.duration = const Duration(milliseconds: 380),
  });

  @override
  Widget build(BuildContext context) {
    final delayMs = 30 * (index > 12 ? 12 : index);
    final total = duration + Duration(milliseconds: delayMs);
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: total,
      curve: Interval(
        delayMs / total.inMilliseconds,
        1,
        curve: Curves.easeOutCubic,
      ),
      child: child,
      builder: (context, t, child) => Opacity(
        opacity: t,
        child: Transform.translate(
          offset: Offset(0, 12 * (1 - t)),
          child: child,
        ),
      ),
    );
  }
}

/// Szám-felpörgetés: a `value`-ig számol fel (vagy át, ha változik). A
/// formázást a hívó adja (`format`), alapból egészre kerekít.
class CountUp extends StatelessWidget {
  final double value;
  final TextStyle? style;
  final String Function(double)? format;
  final Duration duration;

  const CountUp({
    super.key,
    required this.value,
    this.style,
    this.format,
    this.duration = const Duration(milliseconds: 650),
  });

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: value),
      duration: duration,
      curve: Curves.easeOutCubic,
      builder: (context, v, _) => Text(
        format != null ? format!(v) : v.round().toString(),
        style: style,
      ),
    );
  }
}

/// Asztali hover-emelés: rámutatásra az elem finoman megemelkedik
/// (1,0 → 1,012 skála), a kerete akcentus-színt kap, és puha árnyékot vet.
/// A tartalom változatlan — csak a "megfogható" érzet jön hozzá.
class HoverLift extends StatefulWidget {
  final Widget child;
  final BorderRadius borderRadius;

  const HoverLift({
    super.key,
    required this.child,
    this.borderRadius = const BorderRadius.all(Radius.circular(16)),
  });

  @override
  State<HoverLift> createState() => _HoverLiftState();
}

class _HoverLiftState extends State<HoverLift> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedScale(
        scale: _hover ? 1.012 : 1.0,
        duration: const Duration(milliseconds: 160),
        curve: Curves.easeOutCubic,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          curve: Curves.easeOutCubic,
          decoration: BoxDecoration(
            borderRadius: widget.borderRadius,
            border: Border.all(
              color: _hover
                  ? AppColors.accent.withOpacity(0.55)
                  : Colors.transparent,
            ),
            boxShadow: _hover
                ? [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.35),
                      blurRadius: 18,
                      offset: const Offset(0, 8),
                    ),
                    BoxShadow(
                      color: AppColors.accent.withOpacity(0.10),
                      blurRadius: 24,
                    ),
                  ]
                : const [],
          ),
          child: widget.child,
        ),
      ),
    );
  }
}
