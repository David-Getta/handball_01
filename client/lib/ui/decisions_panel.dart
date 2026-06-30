/// Döntések-panel — egy kiválasztott játékos passz-döntései (sötét téma).
library;

import "package:flutter/material.dart";

import "../analytics/decisions.dart";
import "../models/tracking.dart";
import "../theme/app_theme.dart";

class DecisionsPanel extends StatefulWidget {
  final Match match;
  const DecisionsPanel({super.key, required this.match});

  @override
  State<DecisionsPanel> createState() => _DecisionsPanelState();
}

class _DecisionsPanelState extends State<DecisionsPanel> {
  int? _playerId;
  late Map<int, int?> _jerseyById;
  late List<int> _passers;

  @override
  void initState() {
    super.initState();
    _jerseyById = _buildJerseyMap(widget.match);
    _passers = passingPlayerIds(widget.match);
    _playerId = _passers.isNotEmpty ? _passers.first : null;
  }

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
      return Center(child: Text("Nincs felismert passz.", style: AppText.label));
    }

    final report = analyzePlayerDecisions(widget.match, _playerId!);
    final dist = report.passDistribution.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Text("JÁTÉKOS", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.border),
          ),
          child: DropdownButton<int>(
            value: _playerId,
            isExpanded: true,
            underline: const SizedBox(),
            dropdownColor: AppColors.surfaceAlt,
            items: [for (final id in _passers) DropdownMenuItem(value: id, child: Text(_label(id)))],
            onChanged: (v) => setState(() => _playerId = v),
          ),
        ),

        const SizedBox(height: AppSpacing.lg),
        Row(
          children: [
            _metric("Passzok", "${report.passes}"),
            _metric("Optimális", "${(report.optimalRate * 100).toStringAsFixed(0)}%",
                accent: true),
          ],
        ),

        const SizedBox(height: AppSpacing.lg),
        Text("KIHEZ PASSZOL", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        if (dist.isEmpty) Text("—", style: AppText.label),
        for (final e in dist) _distRow(_label(e.key), e.value, report.passes),
      ],
    );
  }

  Widget _metric(String label, String value, {bool accent = false}) => Expanded(
        child: Container(
          margin: const EdgeInsets.only(right: AppSpacing.sm),
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value, style: AppText.valueBig.copyWith(color: accent ? AppColors.accent : AppColors.textPrimary)),
              const SizedBox(height: 2),
              Text(label, style: AppText.label.copyWith(fontSize: 11)),
            ],
          ),
        ),
      );

  Widget _distRow(String target, int count, int total) {
    final frac = total > 0 ? count / total : 0.0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text("→ $target", style: AppText.label.copyWith(color: AppColors.textPrimary)),
              Text("$count/$total · ${(frac * 100).toStringAsFixed(0)}%", style: AppText.value),
            ],
          ),
          const SizedBox(height: 5),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: frac.clamp(0.0, 1.0),
              minHeight: 6,
              backgroundColor: AppColors.surfaceAlt,
              valueColor: const AlwaysStoppedAnimation(AppColors.accent),
            ),
          ),
        ],
      ),
    );
  }
}
