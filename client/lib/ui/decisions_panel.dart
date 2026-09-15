/// Döntések-panel — egy kiválasztott játékos passz-döntései (sötét téma).
library;

import "package:flutter/material.dart";

import "anim.dart";
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
            _metric("Passzok", report.passes.toDouble(), (v) => "${v.round()}"),
            _metric("Optimális", report.optimalRate * 100,
                (v) => "${v.toStringAsFixed(0)}%",
                accent: true),
          ],
        ),
        const SizedBox(height: 6),
        // A "62%" magában semmit nem mond: a szám ÉRTELMÉT ide kell
        // odaírni, különben az edző nem tudja, mihez viszonyítson.
        Text(
            "Az \"optimális\" azt méri, hányszor a LEGJOBB elérhető opciót "
            "választotta — a mezőny akkori állásából számolva. A 100% nem "
            "reális cél: a kényszerpasszok is beleszámítanak.",
            style: AppText.label.copyWith(fontSize: 11)),

        const SizedBox(height: AppSpacing.lg),
        Text("KIHEZ PASSZOL", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        if (dist.isEmpty) Text("—", style: AppText.label),
        for (final (i, e) in dist.indexed)
          FadeSlideIn(
              index: i,
              child: _distRow(_label(e.key), e.value, report.passes)),
      ],
    );
  }

  /// Egy mérő-doboz. A szám FELPÖRÖG (CountUp): játékos-váltáskor a
  /// mozgás jelzi, hogy az érték kicserélődött — eddig némán átugrott,
  /// és könnyű volt a régi számot olvasni az újnak.
  Widget _metric(String label, double value, String Function(double) format,
          {bool accent = false}) =>
      Expanded(
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
              CountUp(
                  value: value,
                  format: format,
                  style: AppText.valueBig.copyWith(
                      color: accent
                          ? AppColors.accent
                          : AppColors.textPrimary)),
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
          AnimatedBar(value: frac, minHeight: 6),
        ],
      ),
    );
  }
}
