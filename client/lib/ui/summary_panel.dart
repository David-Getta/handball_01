/// Meccs-összegző panel — csapatstílus egy nézetben (sötét téma).
library;

import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../analytics/match_summary.dart";
import "../analytics/tactics.dart";
import "../theme/app_theme.dart";
import "intensity_chart.dart";
import "score_chart.dart";

class SummaryPanel extends StatelessWidget {
  final MatchSummary summary;
  final String homeName;
  final String awayName;

  /// Gól-események az eredmény-alakulás grafikonhoz (üresnél nincs grafikon).
  final List<Map<String, dynamic>> goals;
  final int totalFrames;
  final double fps;
  final void Function(int frame)? onSeekFrame;

  /// Intenzitás-ablakok a tempó-grafikonhoz (2-nél kevesebbnél nincs grafikon).
  final List<IntensityWindow> intensity;

  const SummaryPanel({
    super.key,
    required this.summary,
    required this.homeName,
    required this.awayName,
    this.goals = const [],
    this.totalFrames = 0,
    this.fps = 25.0,
    this.onSeekFrame,
    this.intensity = const [],
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        if (goals.isNotEmpty) ...[
          Text("EREDMÉNY-ALAKULÁS", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          ScoreChart(
            goals: goals,
            totalFrames: totalFrames,
            fps: fps,
            homeName: homeName,
            awayName: awayName,
            onSeekFrame: onSeekFrame,
          ),
          const SizedBox(height: AppSpacing.xl),
        ],
        if (intensity.length >= 2) ...[
          Text("TEMPÓ-ALAKULÁS (FÁRADÁS)", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          IntensityChart(
            windows: intensity,
            totalFrames: totalFrames,
            fps: fps,
            homeName: homeName,
            awayName: awayName,
            onSeekFrame: onSeekFrame,
          ),
          const SizedBox(height: AppSpacing.xl),
        ],
        Text("FÁZIS-MEGOSZLÁS", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        _bar("Hazai támadás", summary.phasePercentages[Phase.homeAttack] ?? 0, AppColors.home),
        _bar("Vendég támadás", summary.phasePercentages[Phase.awayAttack] ?? 0, AppColors.away),
        _bar("Átmenet", summary.phasePercentages[Phase.transition] ?? 0, AppColors.textSecondary),

        const SizedBox(height: AppSpacing.xl),
        Text("VÉDEKEZÉSI FORMA", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        _kv(homeName, summary.homeFormation),
        _kv(awayName, summary.awayFormation),

        const SizedBox(height: AppSpacing.xl),
        Text("TEMPÓ", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        _kv("Birtoklások", "${summary.possessions}"),
        _kv("Átlagos támadás", "${summary.avgAttackDurationS.toStringAsFixed(1)} s"),
        _kv("Átmenet aránya", "${summary.transitionPct.toStringAsFixed(0)} %"),
        _kv("Labda átlagseb.", "${summary.avgBallSpeedMs.toStringAsFixed(1)} m/s"),

        const SizedBox(height: AppSpacing.xl),
        Text("FIGURÁK", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        _kv("Felismert támadás", "${summary.attacks}"),
        _kv("Visszatérő figura", "${summary.numFigures}"),
      ],
    );
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(k, style: AppText.label.copyWith(color: AppColors.textPrimary)),
            Text(v, style: AppText.value),
          ],
        ),
      );

  Widget _bar(String label, double pct, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: AppText.label.copyWith(color: AppColors.textPrimary)),
              Text("${pct.toStringAsFixed(0)} %", style: AppText.value),
            ],
          ),
          const SizedBox(height: 5),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (pct / 100).clamp(0.0, 1.0),
              minHeight: 6,
              backgroundColor: AppColors.surfaceAlt,
              valueColor: AlwaysStoppedAnimation(color),
            ),
          ),
        ],
      ),
    );
  }
}
