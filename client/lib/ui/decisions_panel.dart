/// Döntések-panel — egy kiválasztott játékos passz-döntései.
///
/// Mutatja: kihez passzol (eloszlás, "10/7-szer ide"), és mennyire optimálisan
/// (az értékmodell szerinti legjobb opcióhoz képest). A számítást a kliensoldali
/// decisions.dart végzi (a backend tükre), így backend nélkül is működik.
library;

import "package:flutter/material.dart";

import "../analytics/decisions.dart";
import "../models/tracking.dart";

class DecisionsPanel extends StatefulWidget {
  final Match match;
  const DecisionsPanel({super.key, required this.match});

  @override
  State<DecisionsPanel> createState() => _DecisionsPanelState();
}

class _DecisionsPanelState extends State<DecisionsPanel> {
  int? _playerId;
  late Map<int, int?> _jerseyById; // track_id -> mezszám (megjelenítéshez)
  late List<int> _passers;

  @override
  void initState() {
    super.initState();
    _jerseyById = _buildJerseyMap(widget.match);
    _passers = passingPlayerIds(widget.match);
    _playerId = _passers.isNotEmpty ? _passers.first : null;
  }

  /// track_id -> mezszám térkép a meccs frame-jeiből (a megjelenítéshez).
  Map<int, int?> _buildJerseyMap(Match match) {
    final map = <int, int?>{};
    for (final f in match.frames) {
      for (final p in f.players) {
        map.putIfAbsent(p.trackId, () => p.jerseyNumber);
      }
    }
    return map;
  }

  String _label(int id) {
    final j = _jerseyById[id];
    return j != null ? "#$j" : "id $id";
  }

  @override
  Widget build(BuildContext context) {
    if (_passers.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Text("Nincs felismert passz ezen az adaton."),
      );
    }

    final report = analyzePlayerDecisions(widget.match, _playerId!);
    // A passzeloszlás csökkenő sorrendben (a leggyakoribb cél elöl).
    final dist = report.passDistribution.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const Text("Játékos-döntések", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        Row(
          children: [
            const Text("Játékos: "),
            DropdownButton<int>(
              value: _playerId,
              items: [for (final id in _passers) DropdownMenuItem(value: id, child: Text(_label(id)))],
              onChanged: (v) => setState(() => _playerId = v),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _kv("Passzok száma", "${report.passes}"),
        _kv("Optimális döntés", "${(report.optimalRate * 100).toStringAsFixed(0)} %"),
        _kv("Átlagos veszteség", report.avgValueGap.toStringAsFixed(3)),
        const SizedBox(height: 16),
        const Text("Kihez passzol", style: TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF1E66F5))),
        const SizedBox(height: 6),
        if (dist.isEmpty) const Text("—"),
        for (final e in dist) _distRow(_label(e.key), e.value, report.passes),
      ],
    );
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [Text(k), Text(v, style: const TextStyle(fontWeight: FontWeight.w600))],
        ),
      );

  /// Egy passz-cél sora: "ide → N (X%)" + arányos sáv.
  Widget _distRow(String target, int count, int total) {
    final frac = total > 0 ? count / total : 0.0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text("→ $target"),
              Text("$count/$total (${(frac * 100).toStringAsFixed(0)}%)"),
            ],
          ),
          const SizedBox(height: 2),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: frac.clamp(0.0, 1.0),
              minHeight: 7,
              backgroundColor: const Color(0xFFE0E0E0),
            ),
          ),
        ],
      ),
    );
  }
}
