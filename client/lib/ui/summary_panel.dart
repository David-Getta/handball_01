/// Meccs-összegző panel — a csapatstílus egy nézetben (jobb oldali "Összegzés" tab).
///
/// A computeMatchSummary kimenetét mutatja: fázis-megoszlás, csapatonkénti
/// védekezési forma, tempó-metrikák, visszatérő figurák száma.
library;

import "package:flutter/material.dart";

import "../analytics/match_summary.dart";
import "../analytics/tactics.dart";

class SummaryPanel extends StatelessWidget {
  final MatchSummary summary;
  final String homeName;
  final String awayName;

  const SummaryPanel({
    super.key,
    required this.summary,
    required this.homeName,
    required this.awayName,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const Text("Meccs-összegzés", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),

        _section("Fázis-megoszlás"),
        _bar("Hazai támadás", summary.phasePercentages[Phase.homeAttack] ?? 0),
        _bar("Vendég támadás", summary.phasePercentages[Phase.awayAttack] ?? 0),
        _bar("Átmenet", summary.phasePercentages[Phase.transition] ?? 0),

        const SizedBox(height: 16),
        _section("Védekezési forma"),
        _kv(homeName, summary.homeFormation),
        _kv(awayName, summary.awayFormation),

        const SizedBox(height: 16),
        _section("Tempó"),
        _kv("Birtoklások", "${summary.possessions}"),
        _kv("Átlagos támadás", "${summary.avgAttackDurationS.toStringAsFixed(1)} s"),
        _kv("Átmenet aránya", "${summary.transitionPct.toStringAsFixed(0)} %"),
        _kv("Labda átlagseb.", "${summary.avgBallSpeedMs.toStringAsFixed(1)} m/s"),

        const SizedBox(height: 16),
        _section("Figurák (set play-ek)"),
        _kv("Felismert támadás", "${summary.attacks}"),
        _kv("Visszatérő figura", "${summary.numFigures}"),
      ],
    );
  }

  Widget _section(String title) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(title, style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF1E66F5))),
      );

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [Text(k), Text(v, style: const TextStyle(fontWeight: FontWeight.w600))],
        ),
      );

  Widget _bar(String label, double pct) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [Text(label), Text("${pct.toStringAsFixed(0)} %")],
          ),
          const SizedBox(height: 2),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (pct / 100).clamp(0.0, 1.0),
              minHeight: 8,
              backgroundColor: const Color(0xFFE0E0E0),
            ),
          ),
        ],
      ),
    );
  }
}
