/// Statisztika-panel — játékosonkénti táv és sebesség, csapatonként (sötét téma).
library;

import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../models/tracking.dart";
import "../theme/app_theme.dart";

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
    this.homeColor = AppColors.home,
    this.awayColor = AppColors.away,
  });

  @override
  Widget build(BuildContext context) {
    final home = stats.values.where((s) => s.team == Team.home).toList()
      ..sort((a, b) => (a.jerseyNumber ?? a.trackId).compareTo(b.jerseyNumber ?? b.trackId));
    final away = stats.values.where((s) => s.team == Team.away).toList()
      ..sort((a, b) => (a.jerseyNumber ?? a.trackId).compareTo(b.jerseyNumber ?? b.trackId));

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Text("táv · átlagsebesség", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.md),
        _teamHeader(homeName, homeColor),
        ...home.map(_row),
        const SizedBox(height: AppSpacing.lg),
        _teamHeader(awayName, awayColor),
        ...away.map(_row),
      ],
    );
  }

  Widget _teamHeader(String name, Color color) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: Row(children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: AppSpacing.sm),
          Text(name, style: AppText.value),
        ]),
      );

  Widget _row(PlayerStat s) {
    final label = s.jerseyNumber != null ? "#${s.jerseyNumber}" : "id ${s.trackId}";
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: AppText.label.copyWith(color: AppColors.textPrimary)),
          Row(children: [
            Text("${s.distanceM.toStringAsFixed(1)} m", style: AppText.value),
            const SizedBox(width: 10),
            Text("${s.avgSpeedMs.toStringAsFixed(1)} m/s",
                style: AppText.label.copyWith(color: AppColors.accent)),
          ]),
        ],
      ),
    );
  }
}
