/// Szezon — a KÖNYVTÁR egésze egy lapon, saját menüponttal.
///
/// Eddig a szezon-összkép, a toplisták és a nyomtatható szezon-/egymás
/// elleni riportok mind a kezdőlap mélyén laktak: aki nem görgetett
/// odáig, nem is tudott róluk. Két külön nézőpont kéri ugyanezt az
/// adatot, ezért kap saját helyet a menüben:
///
///   EDZŐI szemmel: hány meccs van a könyvtárban, mennyi a mért
///   játékidő, és melyik csapatról készíthető szezon- vagy egymás
///   elleni riport (nyomtatható HTML).
///
///   JÁTÉKOS szemmel: a toplisták — gól, gólpassz, blokk, labdaszerzés,
///   védés — MEZSZÁM szerint összesítve az egész szezonra. Ez az a lap,
///   amin a játékos megkeresi magát; a mezszám nélküli trackek
///   kimaradnak (meccsek közt nincs stabil azonosítójuk), ezt ki is
///   mondjuk, hogy senki ne hiányzó teljesítménynek olvassa.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "shell/app_shell.dart";
import "waiting.dart";

class SeasonScreen extends StatefulWidget {
  const SeasonScreen({super.key});

  @override
  State<SeasonScreen> createState() => _SeasonScreenState();
}

class _SeasonScreenState extends State<SeasonScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  String? _error;
  Map<String, dynamic> _summary = {};
  Map<String, dynamic> _leaders = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final s = await _api.fetchLibrarySummary();
      final l = await _api.fetchLibraryLeaders();
      if (!mounted) return;
      setState(() {
        _summary = s;
        _leaders = l;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "A szezon-összkép nem érhető el: ${humanError(e)}";
        _loading = false;
      });
    }
  }

  List<String> get _teams =>
      [for (final t in (_summary["teams"] as List? ?? [])) t as String];

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.season,
      crumbPath: "CSAPAT · SZEZON",
      child: _loading
          ? const WaitingView("Szezon-összkép számítása…",
              hint: "A teljes meccs-könyvtárat összesítjük.",
              icon: Icons.calendar_month_outlined)
          : ListView(children: [
              Text("Szezon", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "a teljes könyvtár egy lapon: összkép, toplisták és "
                  "nyomtatható riportok",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text(_error!,
                      style: AppText.label.copyWith(color: AppColors.away)),
                ),
              _totals(),
              const SizedBox(height: AppSpacing.lg),
              Text("TOPLISTÁK", style: AppText.sectionLabel),
              const SizedBox(height: AppSpacing.sm),
              _leaderBoards(),
              const SizedBox(height: AppSpacing.lg),
              Text("RIPORTOK", style: AppText.sectionLabel),
              const SizedBox(height: AppSpacing.sm),
              _reports(),
            ]),
    );
  }

  // ---- Összkép -------------------------------------------------------

  Widget _totals() {
    final perc = ((_summary["total_duration_s"] as num?) ?? 0) / 60.0;
    final cells = <(String, String)>[
      ("Meccs", "${_summary["matches"] ?? 0}"),
      ("Mért játékidő", "${perc.round()} perc"),
      ("Gól", "${_summary["goals"] ?? 0}"),
      ("Lövés", "${_summary["shots"] ?? 0}"),
      ("Védés", "${_summary["saves"] ?? 0}"),
      ("Sprint", "${_summary["sprints"] ?? 0}"),
      ("Megtett táv", "${_summary["distance_km"] ?? 0} km"),
    ];
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final (label, value) in cells)
          Container(
            width: 150,
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: AppTheme.card(),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(value, style: AppText.statBig),
                  const SizedBox(height: 2),
                  Text(label, style: AppText.label.copyWith(fontSize: 11)),
                ]),
          ),
      ],
    );
  }

  // ---- Toplisták -----------------------------------------------------

  Widget _leaderBoards() {
    const boards = <(String, String, IconData)>[
      ("goals", "Gól", Icons.sports_score),
      ("assists", "Gólpassz", Icons.share_outlined),
      ("blocks", "Blokk", Icons.pan_tool_outlined),
      ("steals", "Labdaszerzés", Icons.back_hand_outlined),
      ("saves", "Védés", Icons.sports_handball),
    ];
    final vanBarmi = boards.any(
        (b) => ((_leaders[b.$1] as List?) ?? const []).isNotEmpty);
    if (!vanBarmi) {
      return Text(
          "Még nincs toplista. A szezon-listák MEZSZÁM alapján "
          "összesítenek — a mezszám nélküli játékosok kimaradnak, mert "
          "meccsek közt nincs stabil azonosítójuk. A mezszámokat a "
          "meccs-elemzőben lehet hozzárendelni, és onnantól minden "
          "korábbi meccs is beszámít.",
          style: AppText.label);
    }
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final (key, label, icon) in boards)
          _board(label, icon, (_leaders[key] as List?) ?? const []),
      ],
    );
  }

  Widget _board(String label, IconData icon, List<dynamic> rows) {
    return Container(
      width: 260,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: AppTheme.card(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, size: 16, color: AppColors.accent),
          const SizedBox(width: 6),
          Text(label, style: AppText.value),
        ]),
        const SizedBox(height: AppSpacing.sm),
        if (rows.isEmpty)
          Text("nincs adat", style: AppText.label.copyWith(fontSize: 11.5))
        else
          for (var i = 0; i < rows.length; i++)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(children: [
                SizedBox(
                    width: 18,
                    child: Text("${i + 1}.",
                        style: AppText.label.copyWith(fontSize: 11.5))),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceAlt,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text("#${(rows[i] as Map)["jersey"]}",
                      style: AppText.value.copyWith(fontSize: 11.5)),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text("${(rows[i] as Map)["team"]}",
                      overflow: TextOverflow.ellipsis,
                      style: AppText.label.copyWith(fontSize: 11.5)),
                ),
                Text("${(rows[i] as Map)["value"]}",
                    style: AppText.value.copyWith(fontSize: 12.5)),
              ]),
            ),
      ]),
    );
  }

  // ---- Riportok ------------------------------------------------------

  Widget _reports() {
    if (_teams.isEmpty) {
      return Text("Riporthoz legalább egy feldolgozott meccs kell.",
          style: AppText.label);
    }
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final t in _teams)
          OutlinedButton.icon(
            onPressed: () => _saveSeasonReport(t),
            icon: const Icon(Icons.description_outlined, size: 16),
            label: Text("$t szezon-riport"),
          ),
        if (_teams.length >= 2)
          OutlinedButton.icon(
            onPressed: _headToHead,
            icon: const Icon(Icons.compare_arrows, size: 16),
            label: const Text("Egymás ellen riport"),
          ),
      ],
    );
  }

  /// A letöltött HTML mentése — a böngészőből Ctrl+P → PDF.
  Future<void> _saveBytes(
      List<int> bytes, String dialogTitle, String fileName) async {
    final path = await FilePicker.platform.saveFile(
      dialogTitle: dialogTitle,
      fileName: fileName,
      type: FileType.custom,
      allowedExtensions: const ["html"],
    );
    if (path == null) return; // a felhasználó megszakította
    await File(path).writeAsBytes(bytes);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text("Mentve: $path — böngészőből nyomtatható")));
  }

  String _safe(String s) =>
      s.replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");

  Future<void> _saveSeasonReport(String team) async {
    try {
      final bytes = await _api.fetchSeasonReport(team);
      if (!mounted) return;
      await _saveBytes(bytes, "Szezon-riport mentése (HTML)",
          "szezon_riport_${_safe(team)}.html");
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Szezon-riport hiba: ${humanError(e)} — legalább "
              "2 meccs kell a csapattól")));
    }
  }

  Future<void> _headToHead() async {
    String? a = _teams.first;
    String? b = _teams.length > 1 ? _teams[1] : null;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setLocal) {
        Widget picker(String label, String? value, void Function(String?) on) {
          return Row(children: [
            SizedBox(width: 70, child: Text(label, style: AppText.label)),
            Expanded(
              child: DropdownButton<String>(
                value: value,
                isExpanded: true,
                dropdownColor: AppColors.surface,
                style: AppText.value.copyWith(fontSize: 13),
                items: [
                  for (final t in _teams)
                    DropdownMenuItem(value: t, child: Text(t)),
                ],
                onChanged: (v) => setLocal(() => on(v)),
              ),
            ),
          ]);
        }

        return AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text("Egymás ellen riport"),
          content: SizedBox(
            width: 380,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              picker("Csapat A", a, (v) => a = v),
              picker("Csapat B", b, (v) => b = v),
              const SizedBox(height: AppSpacing.sm),
              Text(
                  "A riport a két csapat KÖZÖS meccseiből készül — ha még "
                  "nem játszottak egymással a könyvtárban, üres marad.",
                  style: AppText.label.copyWith(fontSize: 11.5)),
            ]),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text("Mégse")),
            FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: AppColors.accent,
                  foregroundColor: AppColors.onAccent),
              onPressed: (a == null || b == null || a == b)
                  ? null
                  : () => Navigator.pop(ctx, true),
              child: const Text("Riport"),
            ),
          ],
        );
      }),
    );
    if (ok != true || a == null || b == null || !mounted) return;
    try {
      final bytes = await _api.fetchHeadToHead(a!, b!);
      if (!mounted) return;
      await _saveBytes(bytes, "Egymás ellen riport mentése (HTML)",
          "egymas_ellen_${_safe(a!)}_vs_${_safe(b!)}.html");
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Egymás ellen hiba: ${humanError(e)} — csak közös "
              "meccsel rendelkező pároshoz készül riport")));
    }
  }
}
