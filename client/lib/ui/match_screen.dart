/// Meccs-képernyő — betölti a Tracking-et, lejátssza, és megjeleníti a
/// hőtérképet + a statisztika-panelt.
///
/// Adatforrás: lokális backend, ha elérhető; különben a beágyazott demó.
/// Nézetek: JÁTÉKOSOK (mozgó pontok) vagy HŐTÉRKÉP (csapat látogatottsága).
/// Jobb oldalt (desktop-first) a statisztika-panel (táv/sebesség).
library;

import "dart:async";
import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../analytics/match_summary.dart";
import "../analytics/tactics.dart";
import "../models/tracking.dart";
import "../services/api_client.dart";
import "../sim/demo_data.dart";
import "court_painter.dart";
import "heatmap_painter.dart";
import "stats_panel.dart";
import "summary_panel.dart";

/// Mit mutatunk a pályán: a játékosokat vagy a hőtérképet.
enum ViewMode { players, heatmap }

class MatchScreen extends StatefulWidget {
  final String matchId;
  const MatchScreen({super.key, this.matchId = "sim-0"});

  @override
  State<MatchScreen> createState() => _MatchScreenState();
}

class _MatchScreenState extends State<MatchScreen> {
  static const _homeColor = Color(0xFF1E66F5);
  static const _awayColor = Color(0xFFE5484D);

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
  Heatmap? _heatmap; // a kiválasztott csapat hőtérképe (igény szerint számolva)

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
        label = "backend (localhost): ${match.meta.matchId}";
      } catch (e) {
        match = buildDemoMatch();
        label = "demó (backend hiba: $e)";
      }
    } else {
      match = buildDemoMatch();
      label = "demó (nincs backend)";
    }
    setState(() {
      _match = match;
      _stats = computePlayerStats(match);     // statisztika a panelhez
      _summary = computeMatchSummary(match);  // meccs-összegzés a panelhez
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
    return Scaffold(
      appBar: AppBar(
        title: const Text("Kézilabda — felülnézeti nézet"),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh), tooltip: "Újratöltés"),
        ],
      ),
      body: match == null
          ? const Center(child: CircularProgressIndicator())
          : Row(
              children: [
                // Bal oldal: vezérlők + pálya + lejátszó.
                Expanded(
                  child: Column(
                    children: [
                      _topBar(match),
                      Expanded(child: _courtArea(match)),
                      _tacticalCaption(match),
                      _controls(match),
                    ],
                  ),
                ),
                // Jobb oldal (desktop-first): tabos panel — Statisztika / Összegzés.
                SizedBox(
                  width: 300,
                  child: DefaultTabController(
                    length: 2,
                    child: Column(
                      children: [
                        const TabBar(tabs: [
                          Tab(text: "Statisztika"),
                          Tab(text: "Összegzés"),
                        ]),
                        Expanded(
                          child: TabBarView(
                            children: [
                              StatsPanel(
                                stats: _stats,
                                homeName: match.meta.homeTeam,
                                awayName: match.meta.awayTeam,
                                homeColor: _homeColor,
                                awayColor: _awayColor,
                              ),
                              _summary == null
                                  ? const SizedBox()
                                  : SummaryPanel(
                                      summary: _summary!,
                                      homeName: match.meta.homeTeam,
                                      awayName: match.meta.awayTeam,
                                    ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }

  Widget _topBar(Match match) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          // Nézetváltó: játékosok / hőtérkép.
          SegmentedButton<ViewMode>(
            segments: const [
              ButtonSegment(value: ViewMode.players, label: Text("Játékosok"), icon: Icon(Icons.groups)),
              ButtonSegment(value: ViewMode.heatmap, label: Text("Hőtérkép"), icon: Icon(Icons.local_fire_department)),
            ],
            selected: {_viewMode},
            onSelectionChanged: (s) => setState(() => _viewMode = s.first),
          ),
          const SizedBox(width: 16),
          // Hőtérkép-csapatválasztó (csak hőtérkép nézetben).
          if (_viewMode == ViewMode.heatmap)
            DropdownButton<Team>(
              value: _heatmapTeam,
              items: [
                DropdownMenuItem(value: Team.home, child: Text(match.meta.homeTeam)),
                DropdownMenuItem(value: Team.away, child: Text(match.meta.awayTeam)),
              ],
              onChanged: (t) => t == null ? null : _setHeatmapTeam(t),
            ),
          const Spacer(),
          Text("forrás: $_sourceLabel", style: const TextStyle(fontSize: 12, color: Colors.grey)),
        ],
      ),
    );
  }

  Widget _courtArea(Match match) {
    final frame = match.frames[_frameIndex];
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Stack(
        children: [
          // Alapréteg: a pálya + (játékos nézetben) a játékosok.
          Positioned.fill(
            child: CustomPaint(
              painter: CourtPainter(
                frame: _viewMode == ViewMode.players ? frame : null,
                colors: const DisplayColors(home: _homeColor, away: _awayColor),
              ),
            ),
          ),
          // Hőtérkép-réteg (csak hőtérkép nézetben).
          if (_viewMode == ViewMode.heatmap && _heatmap != null)
            Positioned.fill(
              child: CustomPaint(
                painter: HeatmapPainter(
                  heatmap: _heatmap!,
                  color: _heatmapTeam == Team.home ? _homeColor : _awayColor,
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// Élő taktikai felirat az aktuális frame-ről: fázis + (támadáskor) a védő
  /// csapat formája. A számítás a kliensoldali tactics.dart-tal (a backend tükre).
  Widget _tacticalCaption(Match match) {
    const cfg = TacticsConfig();
    final frame = match.frames[_frameIndex];
    final phase = classifyPhase(frame, cfg);

    String text = "Fázis: ${phaseLabelHu(phase)}";
    if (phase == Phase.homeAttack) {
      text += " · ${match.meta.awayTeam} véd: ${detectFormation(frame, Team.away, cfg)}";
    } else if (phase == Phase.awayAttack) {
      text += " · ${match.meta.homeTeam} véd: ${detectFormation(frame, Team.home, cfg)}";
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: const Color(0xFF1E66F5).withOpacity(0.08),
      child: Text(text, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
    );
  }

  Widget _controls(Match match) {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          IconButton(
            iconSize: 32,
            onPressed: _togglePlay,
            icon: Icon(_playing ? Icons.pause_circle : Icons.play_circle),
          ),
          Expanded(
            child: Slider(
              value: _frameIndex.toDouble(),
              min: 0,
              max: (match.frames.length - 1).toDouble(),
              onChanged: (v) => setState(() => _frameIndex = v.round()),
            ),
          ),
          Text("${_frameIndex + 1}/${match.frames.length}  "
              "(${(_frameIndex / (match.meta.fps > 0 ? match.meta.fps : 25.0)).toStringAsFixed(1)} s)"),
        ],
      ),
    );
  }
}
