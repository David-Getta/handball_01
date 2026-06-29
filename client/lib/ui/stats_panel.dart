/// Statisztika-panel — játékosonkénti táv és sebesség, csapatonként csoportosítva.
///
/// A számítást a court_analytics végzi (a backend stats.py tükre). Desktop-first
/// elrendezésben a pálya mellett, oldalt jelenik meg.
library;

import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../models/tracking.dart";

class StatsPanel extends StatelessWidget {
  final Map<int, PlayerStat> stats;
  final String homeName;
  final String awayName;
  final Color homeColor;
  final Color awayColor;

  const StatsPanel({
    super.key,
    required this.stats,
    required this.homeName,
    required this.awayName,
    this.homeColor = const Color(0xFF1E66F5),
    this.awayColor = const Color(0xFFE5484D),
  });

  @override
  Widget build(BuildContext context) {
    // Csapatonként, mezszám szerint rendezve.
    final home = stats.values.where((s) => s.team == Team.home).toList()
      ..sort((a, b) => (a.jerseyNumber ?? a.trackId).compareTo(b.jerseyNumber ?? b.trackId));
    final away = stats.values.where((s) => s.team == Team.away).toList()
      ..sort((a, b) => (a.jerseyNumber ?? a.trackId).compareTo(b.jerseyNumber ?? b.trackId));

    return Container(
      width: 280,
      color: const Color(0xFFF2F2F7),
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          const Text("Statisztika", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          const Text("táv (m) · átlagsebesség (m/s)", style: TextStyle(fontSize: 11, color: Colors.grey)),
          const SizedBox(height: 12),
          _teamHeader(homeName, homeColor),
          ...home.map(_row),
          const SizedBox(height: 16),
          _teamHeader(awayName, awayColor),
          ...away.map(_row),
        ],
      ),
    );
  }

  Widget _teamHeader(String name, Color color) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(children: [
          Container(width: 12, height: 12, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 8),
          Text(name, style: const TextStyle(fontWeight: FontWeight.bold)),
        ]),
      );

  Widget _row(PlayerStat s) {
    final label = s.jerseyNumber != null ? "#${s.jerseyNumber}" : "id ${s.trackId}";
    // A becsült frame-ek aránya jelzi, mennyire volt "látott" a játékos.
    final estNote = s.estimatedFrames > 0 ? "  (becsült: ${s.estimatedFrames})" : "";
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text("${s.distanceM.toStringAsFixed(1)} m · "
              "${s.avgSpeedMs.toStringAsFixed(2)} m/s$estNote",
              style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }
}
