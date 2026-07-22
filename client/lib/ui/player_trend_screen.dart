/// Játékos-fejlődés képernyő — egy játékos terhelése meccsről meccsre.
///
/// A mezszám-hozzárendelésre épül: csapat + mezszám megadása után minden
/// tárolt meccsből kigyűjti a játékos táv/max sebesség/sprint mutatóit,
/// időrendben. Az edző így látja a szezon-terhelést és a formagörbét —
/// pl. hogy a sérülés utáni visszatérésnél hol tart a játékos.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "shell/app_shell.dart";

class PlayerTrendScreen extends StatefulWidget {
  /// A csapatnevek a meccs-könyvtárból (a választóhoz). Üresen hagyva a
  /// képernyő maga tölti be — így a menüből közvetlenül is nyitható.
  final List<String> teams;

  const PlayerTrendScreen({super.key, this.teams = const []});

  @override
  State<PlayerTrendScreen> createState() => _PlayerTrendScreenState();
}

class _PlayerTrendScreenState extends State<PlayerTrendScreen> {
  final ApiClient _api = ApiClient();
  final TextEditingController _jerseyCtrl = TextEditingController();

  List<String> _teams = [];
  String? _team;
  bool _loading = false;
  String? _error;
  List<Map<String, dynamic>> _points = [];

  @override
  void initState() {
    super.initState();
    _teams = List.of(widget.teams);
    if (_teams.isNotEmpty) {
      _team = _teams.first;
    } else {
      _loadTeams(); // menüből nyitva: csapatnevek a könyvtárból
    }
  }

  Future<void> _loadTeams() async {
    try {
      final ms = await _api.listMatches();
      if (!mounted) return;
      final teams = <String>{
        for (final m in ms) ...[
          if (m["home_team"] != null) m["home_team"] as String,
          if (m["away_team"] != null) m["away_team"] as String,
        ]
      }.toList()
        ..sort();
      setState(() {
        _teams = teams;
        if (_team == null && teams.isNotEmpty) _team = teams.first;
      });
    } catch (_) {
      // a képernyő enélkül is használható marad (üres választó)
    }
  }

  @override
  void dispose() {
    _jerseyCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final team = _team;
    final jersey = int.tryParse(_jerseyCtrl.text.trim());
    if (team == null || jersey == null) {
      setState(() => _error = "Válassz csapatot és adj meg mezszámot.");
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final r = await _api.fetchPlayerTrend(team, jersey);
      if (!mounted) return;
      setState(() {
        _points = (r["points"] as List).cast<Map<String, dynamic>>();
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

  /// A szezon-lap letöltése és mentése a választott helyre.
  Future<void> _saveSeasonReport() async {
    final team = _team;
    final jersey = int.tryParse(_jerseyCtrl.text.trim());
    if (team == null || jersey == null) return;
    try {
      final bytes = await _api.fetchPlayerSeasonReport(team, jersey);
      if (!mounted) return;
      final safe = team.replaceAll(
          RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Szezon-lap mentése (HTML)",
        fileName: "szezon_lap_${safe}_$jersey.html",
        type: FileType.custom,
        allowedExtensions: const ["html"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Szezon-lap mentve: $path — böngészőből "
              "nyomtatható, kiosztható")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text("Szezon-lap hiba: $e")));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.playerTrend,
      crumbPath: "DASHBOARD · JÁTÉKOS-FEJLŐDÉS",
      child: ListView(
        children: [
          Text("Játékos-fejlődés", style: AppText.title),
          const SizedBox(height: 4),
          Text("egy játékos terhelése meccsről meccsre — mezszám alapján "
              "(a meccs-nézetben rendelj számot a játékoshoz)",
              style: AppText.subtitle),
          const SizedBox(height: AppSpacing.xl),
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.border),
              ),
              child: DropdownButton<String>(
                value: _team,
                hint: Text("Csapat", style: AppText.label),
                underline: const SizedBox(),
                dropdownColor: AppColors.surfaceAlt,
                items: [
                  for (final t in _teams)
                    DropdownMenuItem(value: t, child: Text(t)),
                ],
                onChanged: (t) => setState(() => _team = t),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            SizedBox(
              width: 120,
              child: TextField(
                controller: _jerseyCtrl,
                keyboardType: TextInputType.number,
                style: AppText.value,
                decoration: InputDecoration(
                  isDense: true,
                  labelText: "Mezszám",
                  labelStyle: AppText.label,
                ),
                onSubmitted: (_) => _load(),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            FilledButton.icon(
              onPressed: _loading ? null : _load,
              icon: _loading
                  ? const SizedBox(width: 16, height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.timeline, size: 18),
              label: const Text("Lekérdezés"),
            ),
            // Szezon-lap mentése (HTML) — csak ha van megjelenített adat.
            if (_points.isNotEmpty) ...[
              const SizedBox(width: AppSpacing.md),
              IconButton(
                tooltip: "Szezon-lap mentése (HTML)",
                onPressed: _saveSeasonReport,
                icon: const Icon(Icons.badge_outlined,
                    color: AppColors.accent),
              ),
            ],
          ]),
          const SizedBox(height: AppSpacing.lg),
          if (_error != null)
            Text(_error!, style: AppText.label.copyWith(color: AppColors.away)),
          if (!_loading && _error == null && _points.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xl),
              child: Text(
                "Nincs találat. Ellenőrizd, hogy a meccs-nézetben "
                "hozzárendelted-e ezt a mezszámot a játékoshoz.",
                style: AppText.label,
              ),
            ),
          if (_points.isNotEmpty) ..._results(),
        ],
      ),
    );
  }

  List<Widget> _results() {
    final maxDist = _points.fold(
        0.0, (m, p) => (p["distance_m"] as num) > m
            ? (p["distance_m"] as num).toDouble() : m);
    final totalSprints = _points.fold(
        0, (s, p) => s + ((p["sprint_count"] as num?)?.toInt() ?? 0));
    final bestTop = _points.fold(
        0.0, (m, p) => (p["top_speed_ms"] as num) > m
            ? (p["top_speed_ms"] as num).toDouble() : m);
    final totalShots = _points.fold(
        0, (s, p) => s + ((p["shots"] as num?)?.toInt() ?? 0));
    final totalGoals = _points.fold(
        0, (s, p) => s + ((p["goals"] as num?)?.toInt() ?? 0));
    // Szezon-szintű helyzetminőség: összes xG + befejezés-eltérés.
    final totalXg = _points.fold(
        0.0, (s, p) => s + ((p["xg"] as num?)?.toDouble() ?? 0.0));
    final totalXgDiff = _points.fold(
        0.0, (s, p) => s + ((p["xg_diff"] as num?)?.toDouble() ?? 0.0));
    // Kapus-mód: ha bármely meccsen van védés-mérleg, a kapus-oszlopok
    // is megjelennek (azonos adatok a szezon-lappal).
    final isGk = _points.any(
        (p) => ((p["gk_on_target"] as num?)?.toInt() ?? 0) > 0);
    // Emberfogás-mód: ha bármely meccsen van mért őrzés, az Őrzés
    // oszlop is megjelenik (azonos adatok a szezon-lappal).
    final hasMark = _points.any(
        (p) => ((p["mark_s"] as num?)?.toDouble() ?? 0) > 0);
    final markS = _points.fold(
        0.0, (s, p) => s + ((p["mark_s"] as num?)?.toDouble() ?? 0.0));
    final markWeighted = _points.fold(
        0.0,
        (s, p) =>
            s +
            ((p["mark_dist"] as num?)?.toDouble() ?? 0.0) *
                ((p["mark_s"] as num?)?.toDouble() ?? 0.0));
    final gkOn = _points.fold(
        0, (s, p) => s + ((p["gk_on_target"] as num?)?.toInt() ?? 0));
    final gkSaves = _points.fold(
        0, (s, p) => s + ((p["gk_saves"] as num?)?.toInt() ?? 0));
    final gkPrev = _points.fold(
        0.0, (s, p) => s + ((p["gk_prevented"] as num?)?.toDouble() ?? 0.0));
    return [
      // Szezon-összkép.
      Wrap(spacing: AppSpacing.lg, runSpacing: AppSpacing.sm, children: [
        _chip("${_points.length} meccs"),
        _chip("legjobb max sebesség: ${(bestTop * 3.6).toStringAsFixed(1)} km/h"),
        _chip("összes sprint: $totalSprints"),
        if (totalShots > 0)
          _chip("gól/lövés: $totalGoals/$totalShots "
              "(${(100.0 * totalGoals / totalShots).toStringAsFixed(0)}%)"),
        if (totalXg > 0)
          _chip("várható gól: ${totalXg.toStringAsFixed(1)} · befejezés: "
              "${totalXgDiff >= 0 ? "+" : ""}${totalXgDiff.toStringAsFixed(1)}"),
        if (isGk && gkOn > 0)
          _chip("védés: $gkSaves/$gkOn "
              "(${(100.0 * gkSaves / gkOn).toStringAsFixed(0)}%) · GSAx: "
              "${gkPrev >= 0 ? "+" : ""}${gkPrev.toStringAsFixed(1)}"),
        if (hasMark && markS > 0)
          _chip("őrzés: ${markS.toStringAsFixed(0)} mp · átl. "
              "${(markWeighted / markS).toStringAsFixed(1)} m"),
      ]),
      const SizedBox(height: AppSpacing.lg),
      // Fejléc + meccsenkénti sorok (táv-csíkkal — a forma ránézésre látszik).
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(children: [
          const SizedBox(width: 170, child: SizedBox()),
          const Expanded(child: SizedBox()),
          _cell("táv", 64),
          _cell("max km/h", 66),
          _cell("sprint", 48),
          _cell("gól/löv", 56),
          _cell("xG ±", 52),
          if (isGk) _cell("védés", 52),
          if (isGk) _cell("GSAx", 50),
          if (hasMark) _cell("őrzés", 66),
          _cell("perc", 44),
        ]),
      ),
      ..._points.map((p) => _row(p, maxDist, isGk, hasMark)),
    ];
  }

  Widget _chip(String text) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(text, style: AppText.value.copyWith(fontSize: 12)),
      );

  Widget _cell(String text, double width) => SizedBox(
      width: width,
      child: Text(text,
          textAlign: TextAlign.right,
          style: AppText.label.copyWith(fontSize: 10, color: AppColors.textFaint)));

  Widget _row(Map<String, dynamic> p, double maxDist, bool isGk,
      bool hasMark) {
    final dist = (p["distance_m"] as num?)?.toDouble() ?? 0.0;
    final frac = maxDist > 0 ? (dist / maxDist).clamp(0.0, 1.0) : 0.0;
    final date = (p["date"] as String?) ?? "";
    final label = date.isEmpty
        ? "vs ${p["opponent"]}"
        : "$date · vs ${p["opponent"]}";
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [
        SizedBox(
            width: 170,
            child: Text(label,
                overflow: TextOverflow.ellipsis,
                style: AppText.label.copyWith(color: AppColors.textPrimary))),
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
            child: Text("${dist.toStringAsFixed(0)} m",
                textAlign: TextAlign.right,
                style: AppText.value.copyWith(fontSize: 13))),
        SizedBox(
            width: 66,
            child: Text(
                (((p["top_speed_ms"] as num?)?.toDouble() ?? 0) * 3.6)
                    .toStringAsFixed(1),
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(
                    fontSize: 13, color: AppColors.accent))),
        SizedBox(
            width: 48,
            child: Text("${p["sprint_count"] ?? 0}×",
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(
                    fontSize: 13, color: AppColors.gold))),
        SizedBox(
            width: 56,
            child: Text(
                ((p["shots"] as num?)?.toInt() ?? 0) > 0
                    ? "${p["goals"] ?? 0}/${p["shots"]}"
                    : "—",
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(
                    fontSize: 13, color: AppColors.textPrimary))),
        // Befejezés-eltérés a meccsen (gól − xG): zöldes = a helyzetei
        // felett, piros = kihagyott helyzetek, — = nem lőtt.
        SizedBox(
            width: 52,
            child: Builder(builder: (_) {
              final d = (p["xg_diff"] as num?)?.toDouble();
              final color = d == null || d.abs() < 0.3
                  ? AppColors.textFaint
                  : (d > 0 ? AppColors.accent : AppColors.away);
              return Text(
                  d == null
                      ? "—"
                      : "${d >= 0 ? "+" : ""}${d.toStringAsFixed(1)}",
                  textAlign: TextAlign.right,
                  style: AppText.label.copyWith(fontSize: 13, color: color));
            })),
        // Kapus-cellák: védés-mérleg + GSAx (csak kapus-mezszámnál).
        if (isGk) ...[
          SizedBox(
              width: 52,
              child: Text(
                  ((p["gk_on_target"] as num?)?.toInt() ?? 0) > 0
                      ? "${p["gk_saves"] ?? 0}/${p["gk_on_target"]}"
                      : "—",
                  textAlign: TextAlign.right,
                  style: AppText.label.copyWith(
                      fontSize: 13, color: AppColors.textPrimary))),
          SizedBox(
              width: 50,
              child: Builder(builder: (_) {
                final g = (p["gk_prevented"] as num?)?.toDouble();
                final color = g == null || g.abs() < 0.3
                    ? AppColors.textFaint
                    : (g > 0 ? AppColors.accent : AppColors.away);
                return Text(
                    g == null
                        ? "—"
                        : "${g >= 0 ? "+" : ""}${g.toStringAsFixed(1)}",
                    textAlign: TextAlign.right,
                    style: AppText.label.copyWith(
                        fontSize: 13, color: color));
              })),
        ],
        // Emberfogás-cella: őrzés-idő + átlagtáv (ha van mért őrzés).
        if (hasMark)
          SizedBox(
              width: 66,
              child: Builder(builder: (_) {
                final ms = (p["mark_s"] as num?)?.toDouble();
                final md = (p["mark_dist"] as num?)?.toDouble();
                if (ms == null || ms <= 0) {
                  return Text("—",
                      textAlign: TextAlign.right,
                      style: AppText.label.copyWith(
                          fontSize: 13, color: AppColors.textFaint));
                }
                final loose = md != null && md >= 2.5;
                return Text(
                    "${ms.toStringAsFixed(0)}s·"
                    "${md == null ? "?" : md.toStringAsFixed(1)}m",
                    textAlign: TextAlign.right,
                    style: AppText.label.copyWith(
                        fontSize: 13,
                        color: loose
                            ? AppColors.gold
                            : AppColors.textPrimary));
              })),
        SizedBox(
            width: 44,
            child: Text("${p["minutes"] ?? "-"}",
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(fontSize: 13))),
      ]),
    );
  }
}
