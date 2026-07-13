/// Védekezés-idővonal — csapatonként egy színsáv: mikor milyen védekezési
/// formát játszottak. A színek a FORMÁKHOZ kötődnek (rögzített kiosztás,
/// nem sorrendi), a jelmagyarázat csak a ténylegesen előforduló formákat
/// mutatja; egy sávra koppintva a lejátszó az ablak kezdetére ugrik.
library;

import "package:flutter/material.dart";

import "../analytics/tactics.dart";
import "../theme/app_theme.dart";

/// Rögzített forma→szín kiosztás (a szín az entitást követi, nem a
/// sorrendet): a gyakori formák kapják a megkülönböztethető színeket,
/// minden más semleges szürkét.
const Map<String, Color> _formationColors = {
  "6-0": AppColors.accent,
  "5-1": AppColors.gold,
  "4-2": Color(0xFF9C7BFF), // lila — nem ütközik a csapatszínekkel
  "3-2-1": Color(0xFFFF9BC7), // rózsaszín
  "3-3": Color(0xFF7BD88A), // zöld
};
const Color _otherColor = Color(0xFF5B6775);

class DefenseTimeline extends StatelessWidget {
  final List<FormationWindow> windows;
  final int totalFrames;
  final double fps;
  final String homeName;
  final String awayName;
  final void Function(int frame)? onSeekFrame;

  const DefenseTimeline({
    super.key,
    required this.windows,
    required this.totalFrames,
    required this.fps,
    required this.homeName,
    required this.awayName,
    this.onSeekFrame,
  });

  bool get _hasData =>
      windows.any((w) => w.homeDefense != null || w.awayDefense != null);

  @override
  Widget build(BuildContext context) {
    if (windows.length < 2 || !_hasData) return const SizedBox.shrink();
    // Jelmagyarázat: csak a ténylegesen előforduló formák.
    final present = <String>{};
    for (final w in windows) {
      if (w.homeDefense != null) present.add(w.homeDefense!);
      if (w.awayDefense != null) present.add(w.awayDefense!);
    }
    final legendLabels = [
      ..._formationColors.keys.where(present.contains),
      if (present.any((f) => !_formationColors.containsKey(f))) "egyéb",
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: AppSpacing.md, runSpacing: 4, children: [
        for (final label in legendLabels)
          Row(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 10, height: 10, decoration: BoxDecoration(
                color: _formationColors[label] ?? _otherColor,
                borderRadius: BorderRadius.circular(3))),
            const SizedBox(width: 5),
            Text(label, style: AppText.label.copyWith(
                color: AppColors.textPrimary, fontSize: 11)),
          ]),
      ]),
      const SizedBox(height: AppSpacing.sm),
      _teamStrip("$homeName védekezése", (w) => w.homeDefense),
      const SizedBox(height: 6),
      _teamStrip("$awayName védekezése", (w) => w.awayDefense),
      const SizedBox(height: 2),
      Text("koppints egy szakaszra — a lejátszó odaugrik",
          style: AppText.label.copyWith(fontSize: 10, color: AppColors.textFaint)),
    ]);
  }

  Widget _teamStrip(String title, String? Function(FormationWindow) sel) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: AppText.label.copyWith(fontSize: 10.5)),
      const SizedBox(height: 3),
      SizedBox(
        height: 16,
        child: LayoutBuilder(builder: (context, c) {
          return Row(children: [
            for (final w in windows)
              Expanded(
                child: GestureDetector(
                  onTap: onSeekFrame == null
                      ? null
                      : () => onSeekFrame!(w.startFrame),
                  child: Tooltip(
                    message: sel(w) == null
                        ? "nem védekezett"
                        : "${sel(w)} · ${(w.startFrame / fps / 60).toStringAsFixed(1)}. perc",
                    child: Container(
                      margin: const EdgeInsets.only(right: 1),
                      decoration: BoxDecoration(
                        color: sel(w) == null
                            ? AppColors.surfaceAlt
                            : (_formationColors[sel(w)] ?? _otherColor),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                ),
              ),
          ]);
        }),
      ),
    ]);
  }
}
