/// Ellenfél-felderítő jelentés — a szoftver "headline" haszna edzőknek.
///
/// Egy csapatról (a felderített ellenfélről) ad egy edzői nyelven megírt
/// jelentést: hogyan játssz ellenük (kulcsok), erősségek/gyengeségek, védekezés,
/// tempó, befejezés, kulcsjátékosok. A backend /scouting végpontból tölt.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "shell/app_shell.dart";

class ScoutingScreen extends StatefulWidget {
  final String matchId;
  final String homeName;
  final String awayName;
  final String team; // kezdetben melyik csapatot derítjük fel

  const ScoutingScreen({
    super.key,
    required this.matchId,
    this.homeName = "Hazai",
    this.awayName = "Vendég",
    this.team = "away",
  });

  @override
  State<ScoutingScreen> createState() => _ScoutingScreenState();
}

class _ScoutingScreenState extends State<ScoutingScreen> {
  final ApiClient _api = ApiClient();
  late String _team = widget.team;
  Map<String, dynamic>? _report;
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
      final r = await _api.fetchScouting(widget.matchId, _team);
      if (!mounted) return;
      setState(() {
        _report = r;
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
      active: NavId.matches,
      crumbTag: "1c",
      crumbPath: "FELDERÍTÉS · ELLENFÉL-JELENTÉS",
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
    final r = _report;
    return Row(
      children: [
        IconButton(
          onPressed: () => Navigator.of(context).maybePop(),
          icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
        ),
        const SizedBox(width: 4),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(r != null ? "${r["team_name"]} — felderítés" : "Felderítés", style: AppText.title),
            Text("Ellenfél-jelentés · edzői kulcsok", style: AppText.subtitle),
          ],
        ),
        const Spacer(),
        // Melyik csapatot derítsük fel.
        SegmentedButton<String>(
          showSelectedIcon: false,
          segments: [
            ButtonSegment(value: "home", label: Text(widget.homeName)),
            ButtonSegment(value: "away", label: Text(widget.awayName)),
          ],
          selected: {_team},
          onSelectionChanged: (s) {
            setState(() => _team = s.first);
            _load();
          },
        ),
      ],
    );
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.error_outline, size: 36, color: AppColors.away),
          const SizedBox(height: AppSpacing.md),
          Text("Nem sikerült a felderítés", style: AppText.value.copyWith(fontSize: 16)),
          const SizedBox(height: 6),
          Text(_error!, style: AppText.label, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text("Újra")),
        ]),
      );
    }
    final r = _report!;
    return ListView(
      children: [
        _keysCard(r),
        const SizedBox(height: AppSpacing.lg),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: _listCard("ERŐSSÉGEK", r["strengths"], AppColors.accent, Icons.trending_up)),
          const SizedBox(width: AppSpacing.lg),
          Expanded(child: _listCard("GYENGESÉGEK", r["weaknesses"], AppColors.away, Icons.trending_down)),
        ]),
        const SizedBox(height: AppSpacing.lg),
        _metricsCard(r),
        const SizedBox(height: AppSpacing.lg),
        _defenseCard(r),
        const SizedBox(height: AppSpacing.lg),
        _keyPlayersCard(r),
        const SizedBox(height: AppSpacing.xl),
      ],
    );
  }

  /// A LEGFONTOSABB kártya: hogyan játssz ellenük.
  Widget _keysCard(Map<String, dynamic> r) {
    final keys = (r["keys_to_game"] as List?) ?? const [];
    return Container(
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
            const Icon(Icons.vpn_key, size: 18, color: AppColors.gold),
            const SizedBox(width: 8),
            Text("HOGYAN JÁTSSZ ELLENÜK", style: AppText.sectionLabel.copyWith(color: AppColors.gold)),
          ]),
          const SizedBox(height: AppSpacing.md),
          for (final k in keys)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Padding(
                  padding: EdgeInsets.only(top: 3, right: 10),
                  child: Icon(Icons.chevron_right, size: 18, color: AppColors.gold),
                ),
                Expanded(child: Text("$k", style: AppText.value.copyWith(fontSize: 14))),
              ]),
            ),
        ],
      ),
    );
  }

  Widget _listCard(String title, dynamic items, Color color, IconData icon) {
    final list = (items as List?) ?? const [];
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 8),
            Text(title, style: AppText.sectionLabel.copyWith(color: color)),
          ]),
          const SizedBox(height: AppSpacing.sm),
          if (list.isEmpty)
            Text("—", style: AppText.label)
          else
            for (final s in list)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Text("• $s", style: AppText.label.copyWith(color: AppColors.textPrimary, fontSize: 12)),
              ),
        ],
      ),
    );
  }

  Widget _metricsCard(Map<String, dynamic> r) {
    String num(dynamic v, [String unit = ""]) =>
        v == null ? "—" : "${(v is num) ? (v % 1 == 0 ? v.toInt() : v) : v}$unit";
    final tiles = <List<String>>[
      ["Szervezett támadás", num(r["attack_share_pct"], "%")],
      ["Gyors indítás", num(r["fast_break_pct"], "%")],
      ["Labda átlagsebesség", num(r["avg_ball_speed_ms"], " m/s")],
      ["Átl. támadáshossz", num(r["avg_attack_duration_s"], " s")],
      ["Lövés / gól", "${num(r["shots"])} / ${num(r["goals"])}"],
      ["Gólarány", num(r["shot_efficiency_pct"], "%")],
      ["Labdaeladás", num(r["turnovers"])],
      ["Figurák", num(r["num_figures"])],
    ];
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("MUTATÓK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          Wrap(
            spacing: AppSpacing.lg,
            runSpacing: AppSpacing.md,
            children: [for (final t in tiles) _metricTile(t[0], t[1])],
          ),
        ],
      ),
    );
  }

  Widget _metricTile(String label, String value) {
    return SizedBox(
      width: 150,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: AppText.value.copyWith(fontSize: 20, color: AppColors.accent)),
          const SizedBox(height: 2),
          Text(label, style: AppText.label.copyWith(fontSize: 11)),
        ],
      ),
    );
  }

  Widget _defenseCard(Map<String, dynamic> r) {
    final dist = (r["defense_distribution"] as Map?)?.cast<String, dynamic>() ?? {};
    final entries = dist.entries.toList()
      ..sort((a, b) => ((b.value as num).toDouble()).compareTo((a.value as num).toDouble()));
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("VÉDEKEZÉS (amikor ők védenek)", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          if (entries.isEmpty)
            Text("Nincs elég védekező minta.", style: AppText.label)
          else
            for (final e in entries) _defenseBar(e.key, (e.value as num).toDouble()),
        ],
      ),
    );
  }

  Widget _defenseBar(String label, double pct) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [
        SizedBox(width: 56, child: Text(label, style: AppText.value.copyWith(fontSize: 13))),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (pct / 100).clamp(0.0, 1.0),
              minHeight: 8,
              backgroundColor: AppColors.surfaceAlt,
              valueColor: const AlwaysStoppedAnimation(AppColors.accent),
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        SizedBox(width: 44, child: Text("${pct.toStringAsFixed(0)}%",
            textAlign: TextAlign.right, style: AppText.label.copyWith(fontSize: 12))),
      ]),
    );
  }

  Widget _keyPlayersCard(Map<String, dynamic> r) {
    final players = (r["key_players"] as List?) ?? const [];
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("KULCSJÁTÉKOSOK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          if (players.isEmpty)
            Text("Több meccs felderítése pontosítja a játékos-profilt.", style: AppText.label)
          else
            for (final p in players) _playerRow(p as Map<String, dynamic>),
        ],
      ),
    );
  }

  Widget _playerRow(Map<String, dynamic> p) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [
        CircleAvatar(
          radius: 14,
          backgroundColor: AppColors.surfaceAlt,
          child: Text("${p["track_id"]}", style: AppText.label.copyWith(color: AppColors.textPrimary, fontSize: 12)),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(child: Text("${p["role"] ?? "játékos"}", style: AppText.value.copyWith(fontSize: 13))),
        Text("birtoklás ${p["possession_frames"] ?? 0} · ${p["distance_m"] ?? 0} m",
            style: AppText.label.copyWith(fontSize: 11)),
      ]),
    );
  }
}
