/// Fejlődés-követés — két időszak (korábbi vs. újabb meccsek) összevetése.
///
/// A vízió "csapat/játékos fejlődése" része: mutatónként régi → új érték,
/// javult/romlott jelöléssel, és magyar nyelvű összegzéssel. Működik a saját
/// csapatra ("fejlődünk-e?") és az ellenfélre ("változott-e a játékuk?").
/// Az adatokat a backend /scouting/trend végpontja adja.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "shell/app_shell.dart";

class TrendScreen extends StatefulWidget {
  final List<Map<String, String>> older; // a korábbi időszak meccsei
  final List<Map<String, String>> newer; // az újabb időszak meccsei

  const TrendScreen({super.key, required this.older, required this.newer});

  @override
  State<TrendScreen> createState() => _TrendScreenState();
}

class _TrendScreenState extends State<TrendScreen> {
  final ApiClient _api = ApiClient();
  Map<String, dynamic>? _trend;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final t = await _api.fetchTrend(widget.older, widget.newer);
      if (!mounted) return;
      setState(() {
        _trend = t;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "$e";
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.dashboard,
      crumbTag: "1g",
      crumbPath: "FEJLŐDÉS · KÉT IDŐSZAK ÖSSZEVETÉSE",
      collapsed: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _header(),
          const SizedBox(height: AppSpacing.lg),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _header() {
    final t = _trend;
    return Row(children: [
      IconButton(
        onPressed: () => Navigator.of(context).maybePop(),
        icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
      ),
      const SizedBox(width: 4),
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t != null ? "${t["team_name"]} — fejlődés" : "Fejlődés", style: AppText.title),
          Text(
            t != null
                ? "Korábbi: ${t["older_matches"]} meccs · Újabb: ${t["newer_matches"]} meccs"
                : "Két időszak összevetése",
            style: AppText.subtitle,
          ),
        ],
      ),
    ]);
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.error_outline, size: 36, color: AppColors.away),
          const SizedBox(height: AppSpacing.md),
          Text("Nem sikerült az összevetés", style: AppText.value.copyWith(fontSize: 16)),
          const SizedBox(height: 6),
          Text(_error!, style: AppText.label, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text("Újra")),
        ]),
      );
    }
    final t = _trend!;
    final metrics = (t["metrics"] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final summary = (t["summary"] as List?) ?? [];
    return ListView(
      children: [
        // Összegzés (a lényeg, kiemelve).
        Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.gold.withOpacity(0.5)),
          ),
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.insights, size: 18, color: AppColors.gold),
                const SizedBox(width: 8),
                Text("ÖSSZEGZÉS", style: AppText.sectionLabel.copyWith(color: AppColors.gold)),
              ]),
              const SizedBox(height: AppSpacing.md),
              for (final s in summary)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Text("$s", style: AppText.value.copyWith(fontSize: 14)),
                ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        // Mutatónkénti sorok.
        Container(
          decoration: AppTheme.card(),
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("MUTATÓK (korábbi → újabb)", style: AppText.sectionLabel),
              const SizedBox(height: AppSpacing.md),
              for (final m in metrics) _metricRow(m),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.xl),
      ],
    );
  }

  Widget _metricRow(Map<String, dynamic> m) {
    final better = m["better"] as bool?;
    final color = better == null
        ? AppColors.textFaint
        : better
            ? AppColors.accent
            : AppColors.away;
    final icon = better == null
        ? Icons.remove
        : better
            ? Icons.trending_up
            : Icons.trending_down;
    final unit = (m["unit"] as String?) ?? "";
    String num(dynamic v) {
      final d = (v as num?)?.toDouble() ?? 0.0;
      return d % 1 == 0 ? d.toInt().toString() : d.toStringAsFixed(1);
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: AppSpacing.md),
        Expanded(child: Text("${m["label"]}", style: AppText.value.copyWith(fontSize: 13.5))),
        Text("${num(m["older"])}$unit", style: AppText.label.copyWith(fontSize: 13)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Icon(Icons.arrow_forward, size: 13, color: AppColors.textFaint),
        ),
        Text("${num(m["newer"])}$unit",
            style: AppText.value.copyWith(fontSize: 13.5, color: color)),
      ]),
    );
  }
}
