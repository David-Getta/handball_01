/// Meccs-elemző — felülnézeti taktikai nézet (a shell összecsukott railjével).
///
/// Bal oldalon eszköztár + pálya kártyán + élő taktikai felirat + lejátszó, jobbra
/// tabos elemző panel. Adatforrás: lokális backend, ha elérhető; különben demó.
library;

import "dart:async";
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
import "heatmap_painter.dart";
import "shell/app_shell.dart";
import "stats_panel.dart";
import "summary_panel.dart";

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
  int _frameIndex = 0;
  bool _playing = false;
  String _sourceLabel = "betöltés…";
  Timer? _timer;

  ViewMode _viewMode = ViewMode.players;
  Team _heatmapTeam = Team.home;
  Heatmap? _heatmap;

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
    if (await _api.isHealthy()) {
      try {
        match = await _api.fetchMatch(widget.matchId);
        label = "backend · ${match.meta.matchId}";
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
        const Spacer(),
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
        IconButton(onPressed: _load, icon: const Icon(Icons.refresh, color: AppColors.textSecondary)),
      ],
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
    return Stack(
      children: [
        Positioned.fill(
          child: CustomPaint(
            painter: CourtPainter(frame: _viewMode == ViewMode.players ? frame : null),
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
      ],
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
        length: 3,
        child: Column(
          children: [
            const TabBar(
              labelColor: AppColors.textPrimary,
              unselectedLabelColor: AppColors.textFaint,
              indicatorColor: AppColors.accent,
              labelStyle: TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
              tabs: [Tab(text: "Statisztika"), Tab(text: "Összegzés"), Tab(text: "Döntések")],
            ),
            Expanded(
              child: TabBarView(
                children: [
                  StatsPanel(stats: _stats, homeName: match.meta.homeTeam, awayName: match.meta.awayTeam),
                  _summary == null
                      ? const SizedBox()
                      : SummaryPanel(summary: _summary!, homeName: match.meta.homeTeam, awayName: match.meta.awayTeam),
                  DecisionsPanel(key: ValueKey(match.meta.matchId), match: match),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
