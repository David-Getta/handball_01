/// Statisztika-panel — játékosonkénti terhelés-rangsor (sötét téma).
///
/// Táv, max sebesség és sprintek játékosonként, csapatokra bontva; a fejléc
/// gombjaival rendezhető (mezszám / táv / max sebesség / sprintek szerint),
/// így azonnal látszik, ki futott-sprintelt a legtöbbet.
library;

import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../models/tracking.dart";
import "../theme/app_theme.dart";

class StatsPanel extends StatefulWidget {
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
  State<StatsPanel> createState() => _StatsPanelState();
}

class _StatsPanelState extends State<StatsPanel> {
  // Rendezés: jersey (mezszám) | dist | top | sprint — csapaton belül.
  String _sort = "dist";

  List<PlayerStat> _team(Team team) {
    final list =
        widget.stats.values.where((s) => s.team == team).toList();
    switch (_sort) {
      case "dist":
        list.sort((a, b) => b.distanceM.compareTo(a.distanceM));
      case "top":
        list.sort((a, b) => b.topSpeedMs.compareTo(a.topSpeedMs));
      case "sprint":
        list.sort((a, b) => b.sprintCount != a.sprintCount
            ? b.sprintCount.compareTo(a.sprintCount)
            : b.sprintDistanceM.compareTo(a.sprintDistanceM));
      default:
        list.sort((a, b) => (a.jerseyNumber ?? a.trackId)
            .compareTo(b.jerseyNumber ?? b.trackId));
    }
    return list;
  }

  @override
  Widget build(BuildContext context) {
    final home = _team(Team.home);
    final away = _team(Team.away);
    // A csúszkák skálázásához: a legnagyobb táv a meccsen.
    final maxDist = widget.stats.values
        .fold(0.0, (m, s) => s.distanceM > m ? s.distanceM : m);

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Text("JÁTÉKOS-TERHELÉS", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        // Rendezés-választó: mire kíváncsi az edző?
        Wrap(spacing: 6, children: [
          _sortChip("dist", "Táv"),
          _sortChip("top", "Max sebesség"),
          _sortChip("sprint", "Sprintek"),
          _sortChip("jersey", "Mezszám"),
        ]),
        const SizedBox(height: AppSpacing.md),
        _header(),
        const SizedBox(height: 2),
        _teamHeader(widget.homeName, widget.homeColor),
        ...home.map((s) => _row(s, maxDist)),
        const SizedBox(height: AppSpacing.lg),
        _teamHeader(widget.awayName, widget.awayColor),
        ...away.map((s) => _row(s, maxDist)),
      ],
    );
  }

  Widget _sortChip(String value, String label) {
    final selected = _sort == value;
    return ChoiceChip(
      label: Text(label, style: AppText.label.copyWith(
          fontSize: 11,
          color: selected ? AppColors.onAccent : AppColors.textSecondary)),
      selected: selected,
      showCheckmark: false,
      selectedColor: AppColors.accent,
      backgroundColor: AppColors.surfaceAlt,
      side: BorderSide(
          color: selected ? AppColors.accent : AppColors.border),
      visualDensity: VisualDensity.compact,
      onSelected: (_) => setState(() => _sort = value),
    );
  }

  /// Oszlopfejléc — a sorok oszlopaival azonos szélességekkel.
  Widget _header() => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(children: [
          const SizedBox(width: 44),
          const Expanded(child: SizedBox()),
          _cell("táv", 64),
          _cell("max km/h", 66),
          _cell("sprint", 48),
        ]),
      );

  Widget _cell(String text, double width) => SizedBox(
      width: width,
      child: Text(text,
          textAlign: TextAlign.right,
          style: AppText.label.copyWith(fontSize: 10, color: AppColors.textFaint)));

  Widget _teamHeader(String name, Color color) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm, top: AppSpacing.sm),
        child: Row(children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: AppSpacing.sm),
          Text(name, style: AppText.value),
        ]),
      );

  Widget _row(PlayerStat s, double maxDist) {
    final label = s.jerseyNumber != null ? "#${s.jerseyNumber}" : "id ${s.trackId}";
    final frac = maxDist > 0 ? (s.distanceM / maxDist).clamp(0.0, 1.0) : 0.0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        children: [
          SizedBox(
              width: 44,
              child: Text(label,
                  style: AppText.label.copyWith(color: AppColors.textPrimary))),
          // Vizuális táv-csík: ránézésre látszik, ki dolgozott a legtöbbet.
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(
                value: frac,
                minHeight: 5,
                backgroundColor: AppColors.surfaceAlt,
                valueColor: const AlwaysStoppedAnimation(AppColors.accent),
              ),
            ),
          ),
          SizedBox(
              width: 64,
              child: Text("${s.distanceM.toStringAsFixed(0)} m",
                  textAlign: TextAlign.right, style: AppText.value.copyWith(fontSize: 13))),
          SizedBox(
              width: 66,
              child: Text((s.topSpeedMs * 3.6).toStringAsFixed(1),
                  textAlign: TextAlign.right,
                  style: AppText.label.copyWith(fontSize: 13, color: AppColors.accent))),
          SizedBox(
              width: 48,
              child: Text("${s.sprintCount}×",
                  textAlign: TextAlign.right,
                  style: AppText.label.copyWith(fontSize: 13, color: AppColors.gold))),
        ],
      ),
    );
  }
}
