/// Meccs-elemző — felülnézeti taktikai nézet (a shell összecsukott railjével).
///
/// Bal oldalon eszköztár + pálya kártyán + élő taktikai felirat + lejátszó, jobbra
/// tabos elemző panel. Adatforrás: lokális backend, ha elérhető; különben demó.
library;

import "dart:async";
import "dart:io";
import "dart:math" as math;

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../analytics/match_summary.dart";
import "../analytics/tactics.dart";
import "../models/tracking.dart";
import "../services/api_client.dart";
import "../sim/demo_data.dart";
import "../theme/app_theme.dart";
import "court_painter.dart";
import "decisions_panel.dart";
import "designer_screen.dart";
import "scouting_screen.dart";
import "heatmap_painter.dart";
import "shell/app_shell.dart";
import "stats_panel.dart";
import "summary_panel.dart";
import "video_panel.dart";

enum ViewMode { players, heatmap }

class MatchScreen extends StatefulWidget {
  final String matchId;
  const MatchScreen({super.key, this.matchId = "sim-0"});

  @override
  State<MatchScreen> createState() => _MatchScreenState();
}

class _MatchScreenState extends State<MatchScreen> {
  final ApiClient _api = ApiClient();

  Match? _match;
  Map<int, PlayerStat> _stats = {};
  MatchSummary? _summary;
  // Felismert események a backendből (passz/lövés/gól/labdaeladás) — kattintásra
  // a lejátszó az esemény képkockájára ugrik. Demó módban üres.
  List<Map<String, dynamic>> _events = [];
  // A feldolgozás minőség-önellenőrzése (score + figyelmeztetések) — a
  // felhasználó lássa, mennyire megbízható az elemzés. Demó módban null.
  Map<String, dynamic>? _quality;
  int _frameIndex = 0;
  bool _playing = false;
  String _sourceLabel = "betöltés…";
  Timer? _timer;

  ViewMode _viewMode = ViewMode.players;
  Team _heatmapTeam = Team.home;
  Heatmap? _heatmap;

  // Jelenet-lejátszó: az eredeti videó megjelenítése az elemzés felett.
  // Eseményre kattintva a videó a jelenet idejére ugrik.
  final GlobalKey<VideoPanelState> _videoKey = GlobalKey<VideoPanelState>();
  bool _showVideo = false;

  // Kijelölt játékos a pályán (kattintással) — nyomvonal + egyéni adatok.
  int? _selectedTrack;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    Match match;
    String label;
    List<Map<String, dynamic>> events = [];
    Map<String, dynamic>? quality;
    if (await _api.isHealthy()) {
      try {
        match = await _api.fetchMatch(widget.matchId);
        label = "backend · ${match.meta.matchId}";
        try {
          events = await _api.fetchEvents(widget.matchId);
        } catch (_) {
          events = []; // esemény nélkül is működik a nézet
        }
        try {
          quality = await _api.fetchQuality(widget.matchId);
        } catch (_) {
          quality = null; // minőség-jelentés nélkül is teljes a nézet
        }
      } catch (e) {
        match = buildDemoMatch();
        label = "demó";
      }
    } else {
      match = buildDemoMatch();
      label = "demó";
    }
    setState(() {
      _match = match;
      _stats = computePlayerStats(match);
      _summary = computeMatchSummary(match);
      _events = events;
      _quality = quality;
      _sourceLabel = label;
      _frameIndex = 0;
      _heatmap = computeTeamHeatmap(match, _heatmapTeam);
    });
  }

  void _setHeatmapTeam(Team team) {
    final match = _match;
    if (match == null) return;
    setState(() {
      _heatmapTeam = team;
      _heatmap = computeTeamHeatmap(match, team);
    });
  }

  void _togglePlay() {
    final match = _match;
    if (match == null) return;
    setState(() => _playing = !_playing);
    _timer?.cancel();
    if (_playing) {
      final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
      _timer = Timer.periodic(Duration(milliseconds: (1000 / fps).round()), (_) {
        setState(() {
          if (_frameIndex < match.frames.length - 1) {
            _frameIndex++;
          } else {
            _playing = false;
            _timer?.cancel();
          }
        });
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final match = _match;
    return AppShell(
      active: NavId.matches,
      crumbTag: "1c",
      crumbPath: "MECCS-ELEMZŐ · FELÜLNÉZETI TAKTIKAI NÉZET",
      collapsed: true,
      child: match == null
          ? const Center(child: CircularProgressIndicator())
          : match.frames.isEmpty
              ? _emptyState()
              : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _matchTitle(match),
                const SizedBox(height: AppSpacing.lg),
                // Jelenet-lejátszó (ha az eredeti videó elérhető és kérték).
                if (_showVideo && match.meta.videoPath != null) ...[
                  SizedBox(
                    height: 230,
                    child: VideoPanel(
                      key: _videoKey,
                      videoPath: match.meta.videoPath!,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                ],
                Expanded(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(child: _leftColumn(match)),
                      const SizedBox(width: AppSpacing.lg),
                      SizedBox(width: 320, child: _rightPanel(match)),
                    ],
                  ),
                ),
              ],
            ),
    );
  }

  /// Események-panel: a felismert passzok/lövések/gólok/labdaeladások listája.
  /// Egy elemre kattintva a lejátszó az esemény képkockájára ugrik.
  Widget _eventsPanel(Match match) {
    if (_events.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Text(
            _sourceLabel == "demó"
                ? "Az események a backend feldolgozásból jönnek — demó módban nem elérhetők."
                : "Nincs felismert esemény (ehhez labda-detektálás kell a felvételen).",
            style: AppText.label,
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    return ListView.separated(
      padding: const EdgeInsets.all(AppSpacing.md),
      itemCount: _events.length,
      separatorBuilder: (_, __) => const SizedBox(height: 6),
      itemBuilder: (_, i) => _eventRow(_events[i], fps, match),
    );
  }

  Widget _eventRow(Map<String, dynamic> e, double fps, Match match) {
    final type = (e["type"] as String?) ?? "";
    final t = (e["t"] as num?)?.toInt() ?? 0;
    final team = (e["team"] as String?) == "home" ? match.meta.homeTeam : match.meta.awayTeam;
    final (label, icon, color) = switch (type) {
      "goal" => ("GÓL", Icons.sports_score, AppColors.gold),
      "shot" => ("Lövés", Icons.sports_handball, AppColors.accent),
      "turnover" => ("Labdaeladás", Icons.swap_horiz, AppColors.away),
      _ => ("Passz", Icons.arrow_forward, AppColors.textSecondary),
    };
    final selected = _frameIndex == t;
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      // Ugrás az esemény képkockájára (a lejátszót is megállítjuk), és ha az
      // eredeti videó elérhető, a jelenet-lejátszó is a jelenetre ugrik.
      onTap: () {
        setState(() {
          _timer?.cancel();
          _playing = false;
          _frameIndex = t.clamp(0, match.frames.length - 1);
          if (match.meta.videoPath != null && VideoPanel.supported) {
            _showVideo = true;
          }
        });
        // A panel épp most jelenhetett meg — a kirajzolás után ugrunk.
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _videoKey.currentState?.seekTo(match.meta.videoSecondsOfFrame(t));
        });
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? AppColors.accentSoft : AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Text(label, style: AppText.value.copyWith(fontSize: 12.5, color: color)),
          const SizedBox(width: 8),
          Expanded(child: Text(team, style: AppText.label.copyWith(fontSize: 11.5),
              overflow: TextOverflow.ellipsis)),
          Text("${(t / fps).toStringAsFixed(1)} s", style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
    );
  }

  /// Üres eredmény (0 képkocka) — pl. ha a feldolgozás nem talált tartalmat.
  /// Elkerüli a frames[0] hibát, és értelmes visszajelzést ad.
  Widget _emptyState() {
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.videocam_off_outlined, size: 40, color: AppColors.textFaint),
        const SizedBox(height: AppSpacing.md),
        Text("Nincs képkocka ebben a meccsben", style: AppText.title.copyWith(fontSize: 20)),
        const SizedBox(height: 6),
        Text("A feldolgozás nem adott vissza képkockát (pl. csak sötét bevezető, "
            "vagy nem sikerült a detektálás). Nézd meg a videó-utat és a --start értéket.",
            style: AppText.label, textAlign: TextAlign.center),
        const SizedBox(height: AppSpacing.lg),
        _chip(_sourceLabel),
      ]),
    );
  }

  Widget _matchTitle(Match match) {
    return Row(
      children: [
        Text(match.meta.homeTeam, style: AppText.title.copyWith(fontSize: 24, color: AppColors.home)),
        const SizedBox(width: 12),
        Text("vs", style: AppText.label),
        const SizedBox(width: 12),
        Text(match.meta.awayTeam, style: AppText.title.copyWith(fontSize: 24, color: AppColors.away)),
        const SizedBox(width: AppSpacing.lg),
        _chip(_sourceLabel),
        if (_quality != null) ...[
          const SizedBox(width: AppSpacing.sm),
          _qualityChip(_quality!),
        ],
        const Spacer(),
        FilledButton.icon(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ScoutingScreen(
                matchId: match.meta.matchId,
                homeName: match.meta.homeTeam,
                awayName: match.meta.awayTeam,
                team: "away",
              ),
            ),
          ),
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.gold, foregroundColor: AppColors.onAccent),
          icon: const Icon(Icons.assignment_outlined, size: 18),
          label: const Text("Felderítés"),
        ),
        const SizedBox(width: AppSpacing.sm),
        OutlinedButton.icon(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => DesignerScreen(match: match)),
          ),
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.accent,
            side: const BorderSide(color: AppColors.accent),
          ),
          icon: const Icon(Icons.architecture, size: 18),
          label: const Text("Figura-tervező"),
        ),
        const SizedBox(width: AppSpacing.sm),
        // Jelenet-lejátszó ki/be (csak ha az eredeti videó elérhető).
        if (match.meta.videoPath != null)
          IconButton(
            onPressed: () => setState(() => _showVideo = !_showVideo),
            icon: Icon(Icons.ondemand_video,
                color: _showVideo ? AppColors.accent : AppColors.textSecondary),
            tooltip: _showVideo ? "Videó elrejtése" : "Videó megjelenítése",
          ),
        IconButton(
          onPressed: _sourceLabel == "demó" ? null : _editSuspensions,
          icon: const Icon(Icons.timer_outlined, color: AppColors.textSecondary),
          tooltip: "Kiállítások (2/4 perc)",
        ),
        // Gyors javítás: ha a színfelismerés fordítva találta el a csapatokat.
        IconButton(
          onPressed: _sourceLabel == "demó" ? null : _swapTeams,
          icon: const Icon(Icons.swap_horiz, color: AppColors.textSecondary),
          tooltip: "Csapatok felcserélése (ha a színek fordítva vannak)",
        ),
        // Egyoldalas edzői meccsjelentés mentése (HTML → böngészőből PDF).
        IconButton(
          onPressed: _sourceLabel == "demó" ? null : _exportReport,
          icon: const Icon(Icons.description_outlined, color: AppColors.textSecondary),
          tooltip: "Meccsjelentés mentése (nyomtatható)",
        ),
        // Játékos-statisztika mentése CSV-ben (Excelben nyitható).
        IconButton(
          onPressed: _sourceLabel == "demó" ? null : _exportStatsCsv,
          icon: const Icon(Icons.table_chart_outlined, color: AppColors.textSecondary),
          tooltip: "Statisztika mentése (Excel/CSV)",
        ),
        IconButton(onPressed: _load, icon: const Icon(Icons.refresh, color: AppColors.textSecondary)),
      ],
    );
  }

  /// Játékos-statisztika mentése CSV-ben (Excelben közvetlenül nyitható).
  Future<void> _exportStatsCsv() async {
    final match = _match;
    if (match == null) return;
    try {
      final bytes = await _api.fetchStatsCsv(widget.matchId);
      final name = "${match.meta.homeTeam}_${match.meta.awayTeam}"
          .replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Statisztika mentése (CSV)",
        fileName: "statisztika_$name.csv",
        type: FileType.custom,
        allowedExtensions: const ["csv"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Statisztika mentve: $path — Excelben nyitható")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Export-hiba: $e")));
    }
  }

  /// Meccsjelentés mentése: nyomtatható HTML (böngészőből Ctrl+P/⌘P → PDF).
  Future<void> _exportReport() async {
    final match = _match;
    if (match == null) return;
    try {
      final bytes = await _api.fetchMatchReportExport(widget.matchId);
      final name = "${match.meta.homeTeam}_${match.meta.awayTeam}"
          .replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Meccsjelentés mentése",
        fileName: "meccsjelentes_$name.html",
        type: FileType.custom,
        allowedExtensions: const ["html"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Jelentés mentve: $path — böngészőből ⌘P → PDF")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Jelentés-hiba: $e")));
    }
  }

  /// Csapatok felcserélése — ha a színfelismerés fordítva osztotta ki, melyik
  /// szín a hazai. Megerősítés után a backend átbillenti minden játékos
  /// csapat-mezőjét, és a nézet újratölt (statisztika is frissül).
  Future<void> _swapTeams() async {
    final match = _match;
    if (match == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Csapatok felcserélése"),
        content: Text(
          "Ha a pályán a(z) ${match.meta.homeTeam} játékosai a(z) "
          "${match.meta.awayTeam} színével jelennek meg (és fordítva), ez a "
          "művelet kijavítja. A csapatnevek maradnak, csak a hozzárendelés fordul.",
          style: AppText.label,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("Mégse")),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Csere"),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await _api.swapTeams(widget.matchId);
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Csapatok felcserélve.")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Csere-hiba: $e")));
    }
  }

  /// Kiállítások felvitele: az edző megadja, melyik csapatnál, mikortól és
  /// mennyi ideig volt emberhátrány — a backend ebből újraszámolja a képen
  /// kívüli becslést (emberhátrányban nem pótol fantom-játékost).
  Future<void> _editSuspensions() async {
    final match = _match;
    if (match == null) return;
    // Betöltjük a meglévő rostert (szerkeszthető munkapéldány).
    List<Map<String, dynamic>> entries = [];
    try {
      final r = await _api.fetchRoster(widget.matchId);
      entries = ((r["suspensions"] as List?) ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    } catch (_) {}
    if (!mounted) return;

    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlg) => AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text("Kiállítások"),
          content: SizedBox(
            width: 520,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "Add meg, melyik csapatnál mikortól (másodperc a feldolgozott "
                  "szakasz elejétől) és mennyi ideig volt emberhátrány.",
                  style: AppText.label.copyWith(fontSize: 12),
                ),
                const SizedBox(height: AppSpacing.md),
                Flexible(
                  child: SingleChildScrollView(
                    child: Column(children: [
                      for (int i = 0; i < entries.length; i++)
                        _suspensionRow(match, entries, i, setDlg),
                    ]),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                OutlinedButton.icon(
                  onPressed: () => setDlg(() => entries.add({
                        "team": "away", "start_s": 0.0, "duration_s": 120.0,
                      })),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text("Kiállítás hozzáadása"),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("Mégse")),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text("Mentés"),
            ),
          ],
        ),
      ),
    );
    if (saved != true || !mounted) return;
    try {
      final r = await _api.saveRoster(widget.matchId, entries);
      await _load(); // a frissített (újrabecsült) Tracking betöltése
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Mentve: ${r["suspensions"]} kiállítás · "
              "${r["estimated_added"]} becsült pozíció újraszámolva")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Mentési hiba: $e")));
    }
  }

  /// Egy kiállítás sora: csapat + kezdet (mp) + hossz (2/4 perc) + törlés.
  Widget _suspensionRow(Match match, List<Map<String, dynamic>> entries, int i,
      void Function(void Function()) setDlg) {
    final e = entries[i];
    final startCtrl = TextEditingController(
        text: ((e["start_s"] as num?)?.toDouble() ?? 0).toStringAsFixed(0));
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        DropdownButton<String>(
          value: (e["team"] as String?) == "home" ? "home" : "away",
          dropdownColor: AppColors.surfaceAlt,
          underline: const SizedBox(),
          items: [
            DropdownMenuItem(value: "home", child: Text(match.meta.homeTeam)),
            DropdownMenuItem(value: "away", child: Text(match.meta.awayTeam)),
          ],
          onChanged: (v) => setDlg(() => e["team"] = v ?? "away"),
        ),
        const SizedBox(width: AppSpacing.md),
        SizedBox(
          width: 90,
          child: TextField(
            controller: startCtrl,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(isDense: true, labelText: "kezdet (mp)"),
            onChanged: (v) => e["start_s"] = double.tryParse(v) ?? 0.0,
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        SegmentedButton<double>(
          showSelectedIcon: false,
          style: const ButtonStyle(visualDensity: VisualDensity.compact),
          segments: const [
            ButtonSegment(value: 120.0, label: Text("2 perc")),
            ButtonSegment(value: 240.0, label: Text("4 perc")),
          ],
          selected: {((e["duration_s"] as num?)?.toDouble() ?? 120.0) >= 240.0 ? 240.0 : 120.0},
          onSelectionChanged: (s) => setDlg(() => e["duration_s"] = s.first),
        ),
        IconButton(
          onPressed: () => setDlg(() => entries.removeAt(i)),
          icon: const Icon(Icons.delete_outline, size: 18, color: AppColors.textFaint),
        ),
      ]),
    );
  }

  /// Minőség-jelvény: pontszám színnel (jó/közepes/gyenge), kattintásra részletek.
  Widget _qualityChip(Map<String, dynamic> q) {
    final score = (q["score"] as num?)?.toInt() ?? 0;
    final color = score >= 70
        ? AppColors.accent
        : score >= 40
            ? AppColors.gold
            : AppColors.away;
    return InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: () => _showQualityDetails(q),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.verified_outlined, size: 13, color: color),
          const SizedBox(width: 5),
          Text("minőség $score/100",
              style: AppText.label.copyWith(fontSize: 11, color: color)),
        ]),
      ),
    );
  }

  void _showQualityDetails(Map<String, dynamic> q) {
    final warnings = (q["warnings"] as List?) ?? const [];
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text("Feldolgozás minősége: ${q["score"]}/100"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("Mért játékos/kocka: ${q["avg_measured_players"]}", style: AppText.label),
            Text("Labda-lefedettség: ${q["ball_coverage_pct"]}%", style: AppText.label),
            Text("Becsült pozíciók: ${q["estimated_ratio_pct"]}%", style: AppText.label),
            Text("Leghosszabb labda-kiesés: ${q["longest_ball_gap_s"]} mp", style: AppText.label),
            if (warnings.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.md),
              for (final w in warnings)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Icon(Icons.warning_amber, size: 15, color: AppColors.gold),
                    const SizedBox(width: 6),
                    Expanded(child: Text("$w",
                        style: AppText.label.copyWith(color: AppColors.textPrimary, fontSize: 12))),
                  ]),
                ),
            ],
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Rendben")),
        ],
      ),
    );
  }

  Widget _chip(String text) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(text, style: AppText.label.copyWith(fontSize: 11)),
      );

  Widget _leftColumn(Match match) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _toolbar(match),
        const SizedBox(height: AppSpacing.md),
        Expanded(
          child: Container(
            decoration: AppTheme.card(),
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(left: 4, bottom: 6),
                  child: Text("40 × 20 M · FELÜLNÉZET", style: AppText.sectionLabel.copyWith(fontSize: 10)),
                ),
                Expanded(child: _courtArea(match)),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        _tacticalCaption(match),
        const SizedBox(height: AppSpacing.sm),
        _controls(match),
      ],
    );
  }

  Widget _toolbar(Match match) {
    return Row(
      children: [
        SegmentedButton<ViewMode>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: ViewMode.players, label: Text("Játékosok"), icon: Icon(Icons.groups, size: 18)),
            ButtonSegment(value: ViewMode.heatmap, label: Text("Hőtérkép"), icon: Icon(Icons.whatshot, size: 18)),
          ],
          selected: {_viewMode},
          onSelectionChanged: (s) => setState(() => _viewMode = s.first),
        ),
        const SizedBox(width: AppSpacing.md),
        if (_viewMode == ViewMode.heatmap)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: DropdownButton<Team>(
              value: _heatmapTeam,
              underline: const SizedBox(),
              dropdownColor: AppColors.surfaceAlt,
              items: [
                DropdownMenuItem(value: Team.home, child: Text(match.meta.homeTeam)),
                DropdownMenuItem(value: Team.away, child: Text(match.meta.awayTeam)),
              ],
              onChanged: (t) => t == null ? null : _setHeatmapTeam(t),
            ),
          ),
        const Spacer(),
        _legend(),
      ],
    );
  }

  Widget _legend() {
    Widget dot(Color c) => Container(width: 9, height: 9, decoration: BoxDecoration(color: c, shape: BoxShape.circle));
    return Row(children: [
      dot(AppColors.home), const SizedBox(width: 4), Text(_match!.meta.homeTeam, style: AppText.label.copyWith(fontSize: 11)),
      const SizedBox(width: 12),
      dot(AppColors.away), const SizedBox(width: 4), Text(_match!.meta.awayTeam, style: AppText.label.copyWith(fontSize: 11)),
    ]);
  }

  Widget _courtArea(Match match) {
    final frame = match.frames[_frameIndex];
    return LayoutBuilder(builder: (context, c) {
      final size = Size(c.maxWidth, c.maxHeight);
      return GestureDetector(
        // Kattintás egy játékosra → kijelölés + nyomvonal + egyéni adatok.
        onTapUp: (d) => _handleCourtTap(d.localPosition, size, frame),
        child: Stack(
          children: [
            Positioned.fill(
              child: CustomPaint(
                painter: CourtPainter(
                  frame: _viewMode == ViewMode.players ? frame : null,
                  selectedId: _selectedTrack,
                  trail: _trailFor(match),
                ),
              ),
            ),
            if (_viewMode == ViewMode.heatmap && _heatmap != null)
              Positioned.fill(
                child: CustomPaint(
                  painter: HeatmapPainter(
                    heatmap: _heatmap!,
                    color: _heatmapTeam == Team.home ? AppColors.home : AppColors.away,
                  ),
                ),
              ),
            // A kijelölt játékos adat-kártyája (bal-felső sarok).
            if (_selectedTrack != null && _viewMode == ViewMode.players)
              Positioned(left: 10, top: 10, child: _playerChip(match)),
          ],
        ),
      );
    });
  }

  /// Kattintás-visszafejtés: a képpontból méter, majd a legközelebbi játékos
  /// (1,5 m-en belül). Ugyanarra kattintva a kijelölés megszűnik.
  void _handleCourtTap(Offset pos, Size size, Frame frame) {
    if (_viewMode != ViewMode.players) return;
    final (scale, origin) = CourtPainter.transformFor(size);
    if (scale <= 0) return;
    final mx = (pos.dx - origin.dx) / scale;
    final my = (pos.dy - origin.dy) / scale;
    int? best;
    double bestD = 1.5; // méter — ennél közelebbi találat kell
    for (final pl in frame.players) {
      final d = math.sqrt((pl.x - mx) * (pl.x - mx) + (pl.y - my) * (pl.y - my));
      if (d < bestD) {
        bestD = d;
        best = pl.trackId;
      }
    }
    setState(() => _selectedTrack = best == _selectedTrack ? null : best);
  }

  /// A kijelölt játékos nyomvonala (± 4 mp) az aktuális képkocka körül.
  List<Offset>? _trailFor(Match match) {
    final id = _selectedTrack;
    if (id == null) return null;
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    final w = (fps * 4).round();
    final from = (_frameIndex - w).clamp(0, match.frames.length - 1);
    final to = (_frameIndex + w).clamp(0, match.frames.length - 1);
    final pts = <Offset>[];
    for (int i = from; i <= to; i++) {
      for (final pl in match.frames[i].players) {
        if (pl.trackId == id) {
          pts.add(Offset(pl.x, pl.y));
          break;
        }
      }
    }
    return pts.length >= 2 ? pts : null;
  }

  /// A kijelölt játékos adat-kártyája: csapat, táv, átlagsebesség.
  Widget _playerChip(Match match) {
    final id = _selectedTrack!;
    final st = _stats[id];
    final teamName = st == null
        ? ""
        : (st.team == Team.home ? match.meta.homeTeam : match.meta.awayTeam);
    final label = st == null
        ? "Játékos #$id"
        : "Játékos #$id · $teamName · ${st.distanceM.toStringAsFixed(0)} m · "
            "max ${(st.topSpeedMs * 3.6).toStringAsFixed(1)} km/h · "
            "${st.sprintCount} sprint";
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.surface.withOpacity(0.92),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.gold),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.person_pin_circle, size: 16, color: AppColors.gold),
        const SizedBox(width: 6),
        Text(label, style: AppText.value.copyWith(fontSize: 12)),
        const SizedBox(width: 6),
        InkWell(
          onTap: () => setState(() => _selectedTrack = null),
          child: const Icon(Icons.close, size: 14, color: AppColors.textFaint),
        ),
      ]),
    );
  }

  Widget _tacticalCaption(Match match) {
    const cfg = TacticsConfig();
    final frame = match.frames[_frameIndex];
    final phase = classifyPhase(frame, cfg);

    String text = phaseLabelHu(phase);
    String? formation;
    if (phase == Phase.homeAttack) {
      formation = "${match.meta.awayTeam} · ${detectFormation(frame, Team.away, cfg)}";
    } else if (phase == Phase.awayAttack) {
      formation = "${match.meta.homeTeam} · ${detectFormation(frame, Team.home, cfg)}";
    }

    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(color: AppColors.accentSoft, borderRadius: BorderRadius.circular(20)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.sports_handball, size: 16, color: AppColors.accent),
            const SizedBox(width: 6),
            Text(text, style: AppText.value.copyWith(color: AppColors.accent)),
          ]),
        ),
        if (formation != null) ...[
          const SizedBox(width: AppSpacing.sm),
          Text("véd: $formation", style: AppText.label),
        ],
      ],
    );
  }

  Widget _controls(Match match) {
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    return Row(
      children: [
        IconButton(
          iconSize: 38,
          color: AppColors.accent,
          onPressed: _togglePlay,
          icon: Icon(_playing ? Icons.pause_circle_filled : Icons.play_circle_fill),
        ),
        Expanded(
          child: Slider(
            value: _frameIndex.toDouble(),
            min: 0,
            max: (match.frames.length - 1).toDouble(),
            onChanged: (v) => setState(() => _frameIndex = v.round()),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Text("${(_frameIndex / fps).toStringAsFixed(1)} s", style: AppText.value),
        Text("  /  ${(match.frames.length / fps).toStringAsFixed(0)} s", style: AppText.label),
      ],
    );
  }

  Widget _rightPanel(Match match) {
    return Container(
      decoration: AppTheme.card(),
      clipBehavior: Clip.antiAlias,
      child: DefaultTabController(
        length: 4,
        child: Column(
          children: [
            const TabBar(
              labelColor: AppColors.textPrimary,
              unselectedLabelColor: AppColors.textFaint,
              indicatorColor: AppColors.accent,
              labelStyle: TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
              tabs: [
                Tab(text: "Statisztika"),
                Tab(text: "Összegzés"),
                Tab(text: "Döntések"),
                Tab(text: "Események"),
              ],
            ),
            Expanded(
              child: TabBarView(
                children: [
                  StatsPanel(stats: _stats, homeName: match.meta.homeTeam, awayName: match.meta.awayTeam),
                  _summary == null
                      ? const SizedBox()
                      : SummaryPanel(summary: _summary!, homeName: match.meta.homeTeam, awayName: match.meta.awayTeam),
                  DecisionsPanel(key: ValueKey(match.meta.matchId), match: match),
                  _eventsPanel(match),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
