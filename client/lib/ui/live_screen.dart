/// Élő követés — a meccs valós idejű lejátszása ÉLŐ EDZŐI JAVASLAT-folyammal.
///
/// A vízió "élő meccskövetés valós idejű javaslatokkal" része. A felülnézeti pálya
/// mellett egy folyamatosan frissülő javaslat-lista fut (a birtokló csapat
/// szemszögéből: forma-kihasználás, ember-előny, szabad ember, gyors indítás).
/// A javaslatokat a kliens HELYBEN számolja (coaching.dart), a backend /coaching
/// az igazság forrása. Adatforrás: lokális backend, ha elérhető; különben demó.
library;

import "dart:async";
import "package:flutter/material.dart";

import "../analytics/coaching.dart";
import "../analytics/tactics.dart";
import "../models/tracking.dart";
import "../services/api_client.dart";
import "../sim/demo_data.dart";
import "../theme/app_theme.dart";
import "court_painter.dart";
import "shell/app_shell.dart";

class LiveScreen extends StatefulWidget {
  final String matchId;
  const LiveScreen({super.key, this.matchId = "sim-0"});

  @override
  State<LiveScreen> createState() => _LiveScreenState();
}

class _LiveScreenState extends State<LiveScreen> {
  final ApiClient _api = ApiClient();
  static const _cfg = TacticsConfig();

  Match? _match;
  int _frameIndex = 0;
  bool _playing = false;
  String _sourceLabel = "betöltés…";
  Timer? _timer;

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
      } catch (_) {
        match = buildDemoMatch();
        label = "demó";
      }
    } else {
      match = buildDemoMatch();
      label = "demó";
    }
    if (!mounted) return;
    setState(() {
      _match = match;
      _sourceLabel = label;
      _frameIndex = 0;
    });
  }

  void _togglePlay() {
    final match = _match;
    if (match == null || match.frames.isEmpty) return;
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
      active: NavId.live,
      crumbTag: "1d",
      crumbPath: "ÉLŐ KÖVETÉS · VALÓS IDEJŰ ELEMZÉS",
      collapsed: true,
      child: match == null
          ? const Center(child: CircularProgressIndicator())
          : match.frames.isEmpty
              ? _emptyState()
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _header(match),
                    const SizedBox(height: AppSpacing.lg),
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(child: _courtColumn(match)),
                          const SizedBox(width: AppSpacing.lg),
                          SizedBox(width: 340, child: _coachingPanel(match)),
                        ],
                      ),
                    ),
                  ],
                ),
    );
  }

  Widget _emptyState() => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.sensors_off, size: 40, color: AppColors.textFaint),
          const SizedBox(height: AppSpacing.md),
          Text("Nincs lejátszható meccs", style: AppText.title.copyWith(fontSize: 20)),
          const SizedBox(height: 6),
          Text("Tölts fel és dolgozz fel egy videót, vagy indítsd a demót.", style: AppText.label),
        ]),
      );

  Widget _header(Match match) {
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    return Row(
      children: [
        // Pulzáló "ÉLŐ" jelző.
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(
            color: _playing ? AppColors.away.withOpacity(0.15) : AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: _playing ? AppColors.away : AppColors.border),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 8, height: 8, decoration: BoxDecoration(
              color: _playing ? AppColors.away : AppColors.textFaint, shape: BoxShape.circle)),
            const SizedBox(width: 6),
            Text(_playing ? "ÉLŐ" : "SZÜNET",
                style: AppText.label.copyWith(fontSize: 11, fontWeight: FontWeight.w700,
                    color: _playing ? AppColors.away : AppColors.textFaint)),
          ]),
        ),
        const SizedBox(width: AppSpacing.md),
        Text(match.meta.homeTeam, style: AppText.value.copyWith(color: AppColors.home)),
        const SizedBox(width: 8),
        Text("vs", style: AppText.label),
        const SizedBox(width: 8),
        Text(match.meta.awayTeam, style: AppText.value.copyWith(color: AppColors.away)),
        const SizedBox(width: AppSpacing.md),
        _chip(_sourceLabel),
        const Spacer(),
        Text("${(_frameIndex / fps).toStringAsFixed(1)} s", style: AppText.value),
        Text("  /  ${(match.frames.length / fps).toStringAsFixed(0)} s", style: AppText.label),
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

  Widget _courtColumn(Match match) {
    final frame = match.frames[_frameIndex];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: Container(
            decoration: AppTheme.card(),
            padding: const EdgeInsets.all(AppSpacing.md),
            child: CustomPaint(painter: CourtPainter(frame: frame)),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        _controls(match),
      ],
    );
  }

  Widget _controls(Match match) {
    return Row(
      children: [
        IconButton(
          iconSize: 40,
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
      ],
    );
  }

  Widget _coachingPanel(Match match) {
    final frame = match.frames[_frameIndex];
    final prev = _frameIndex > 0 ? match.frames[_frameIndex - 1] : null;
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    final suggestions = suggestForFrame(frame, config: _cfg, prevFrame: prev, fps: fps);

    // Élő taktikai fejléc: fázis + birtoklás + védőforma.
    final phase = classifyPhase(frame, _cfg);
    final poss = possessionTeam(frame, _cfg);
    String defLabel = "—";
    if (phase == Phase.homeAttack) {
      defLabel = "${match.meta.awayTeam}: ${detectFormation(frame, Team.away, _cfg)}";
    } else if (phase == Phase.awayAttack) {
      defLabel = "${match.meta.homeTeam}: ${detectFormation(frame, Team.home, _cfg)}";
    }

    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            const Icon(Icons.tips_and_updates_outlined, size: 18, color: AppColors.accent),
            const SizedBox(width: 8),
            Text("ÉLŐ JAVASLATOK", style: AppText.sectionLabel),
          ]),
          const SizedBox(height: AppSpacing.md),
          // Állapotsor.
          _stateChip(Icons.sports_handball, phaseLabelHu(phase)),
          const SizedBox(height: 6),
          _stateChip(Icons.my_location,
              poss == null ? "Szabad labda"
                  : "Birtoklás: ${poss == Team.home ? match.meta.homeTeam : match.meta.awayTeam}"),
          const SizedBox(height: 6),
          _stateChip(Icons.shield_outlined, "Véd: $defLabel"),
          const Divider(height: AppSpacing.xl, color: AppColors.border),
          Expanded(
            child: ListView.separated(
              itemCount: suggestions.length,
              separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
              itemBuilder: (_, i) => _suggestionRow(suggestions[i]),
            ),
          ),
        ],
      ),
    );
  }

  Widget _stateChip(IconData icon, String text) => Row(children: [
        Icon(icon, size: 15, color: AppColors.textSecondary),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: AppText.label.copyWith(color: AppColors.textPrimary))),
      ]);

  Widget _suggestionRow(Suggestion s) {
    final color = _prioColor(s.priority);
    // FONTOS: BoxDecoration-ben a borderRadius NEM kombinálható egy-oldalú
    // Borderrel (futásidejű hiba) — a bal színcsíkot külön elemként rajzoljuk.
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: AppColors.surfaceAlt,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(width: 3, color: color), // prioritás-színcsík
          const SizedBox(width: 9),
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(color: color.withOpacity(0.16), borderRadius: BorderRadius.circular(6)),
              child: Text(s.category.toUpperCase(),
                  style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: color, letterSpacing: 0.5)),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Text(s.text, style: AppText.value.copyWith(fontSize: 13)),
            ),
          ),
          const SizedBox(width: 12),
        ],
      ),
    );
  }

  /// A prioritás színe: 5 → arany (sürgős kiemelés), 4 → teal, ≤3 → halvány.
  Color _prioColor(int priority) {
    if (priority >= 5) return AppColors.gold;
    if (priority == 4) return AppColors.accent;
    return AppColors.textSecondary;
  }
}
