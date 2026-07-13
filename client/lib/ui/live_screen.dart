/// Élő követés — a meccs valós idejű lejátszása ÉLŐ EDZŐI JAVASLAT-folyammal.
///
/// A vízió "élő meccskövetés valós idejű javaslatokkal" része. A felülnézeti
/// pálya mellett kettéosztott javaslat-panel fut:
///  - MOST: az aktuális pillanat javaslatai (max. néhány, fontosság szerint),
///  - KORÁBBI JELZÉSEK: időbélyeges folyam — az elmúlt percek jelzései nem
///    tűnnek el, visszaolvashatók, és koppintásra a lejátszó odaugrik.
/// A meccs a fejléc választójából jön (a könyvtár bármely meccse vagy demó),
/// a lejátszási sebesség állítható (0,5–4×). A javaslatokat a kliens HELYBEN
/// számolja (coaching.dart), a backend /coaching az igazság forrása.
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
  const LiveScreen({super.key, this.matchId = ""});

  @override
  State<LiveScreen> createState() => _LiveScreenState();
}

/// Egy bejegyzés a javaslat-folyamban (mikor szólt, mit).
class _FeedEntry {
  final int frame;
  final Suggestion suggestion;
  const _FeedEntry(this.frame, this.suggestion);
}

class _LiveScreenState extends State<LiveScreen> {
  final ApiClient _api = ApiClient();
  static const _cfg = TacticsConfig();

  Match? _match;
  List<Map<String, dynamic>> _library = []; // a könyvtár meccsei a választóhoz
  String? _selectedId; // null = demó
  int _frameIndex = 0;
  bool _playing = false;
  double _speed = 1.0;
  String _sourceLabel = "betöltés…";
  Timer? _timer;

  // Javaslat-folyam: az elmúlt jelzések időbélyeggel (legújabb elöl).
  final List<_FeedEntry> _feed = [];
  static const _feedMax = 40;

  @override
  void initState() {
    super.initState();
    _load(widget.matchId.isEmpty ? null : widget.matchId);
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  /// Betöltés: a könyvtár listája + a kért (vagy első) meccs; enélkül demó.
  Future<void> _load(String? matchId) async {
    Match match;
    String label;
    String? selected = matchId;
    if (await _api.isHealthy()) {
      try {
        _library = await _api.listMatches();
      } catch (_) {
        _library = [];
      }
      selected ??= _library.isNotEmpty
          ? _library.first["match_id"] as String
          : null;
      if (selected != null) {
        try {
          match = await _api.fetchMatch(selected);
          label = "backend · $selected";
        } catch (_) {
          match = buildDemoMatch();
          label = "demó";
          selected = null;
        }
      } else {
        match = buildDemoMatch();
        label = "demó";
      }
    } else {
      match = buildDemoMatch();
      label = "demó";
      selected = null;
    }
    if (!mounted) return;
    _timer?.cancel();
    setState(() {
      _match = match;
      _selectedId = selected;
      _sourceLabel = label;
      _frameIndex = 0;
      _playing = false;
      _feed.clear();
    });
  }

  void _togglePlay() {
    final match = _match;
    if (match == null || match.frames.isEmpty) return;
    setState(() => _playing = !_playing);
    _restartTimer(match);
  }

  void _restartTimer(Match match) {
    _timer?.cancel();
    if (!_playing) return;
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    final interval = (1000 / (fps * _speed)).round().clamp(8, 4000);
    _timer = Timer.periodic(Duration(milliseconds: interval), (_) {
      setState(() {
        if (_frameIndex < match.frames.length - 1) {
          _frameIndex++;
          _updateFeed(match);
        } else {
          _playing = false;
          _timer?.cancel();
        }
      });
    });
  }

  /// A folyam frissítése az aktuális kockából: az új (mostanában nem
  /// szerepelt) javaslatok időbélyeggel a folyam elejére kerülnek — így a
  /// jelzések nem villannak el, visszaolvashatók.
  void _updateFeed(Match match) {
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    final frame = match.frames[_frameIndex];
    final prev = _frameIndex > 0 ? match.frames[_frameIndex - 1] : null;
    for (final s in suggestForFrame(frame, config: _cfg, prevFrame: prev,
        fps: fps)) {
      // Ismétlés-szűrés: ugyanaz a szöveg 12 mp-en belül nem kerül be újra.
      final repeat = _feed.any((e) =>
          e.suggestion.text == s.text &&
          (_frameIndex - e.frame) / fps < 12.0);
      if (!repeat) {
        _feed.insert(0, _FeedEntry(_frameIndex, s));
      }
    }
    while (_feed.length > _feedMax) {
      _feed.removeLast();
    }
  }

  @override
  Widget build(BuildContext context) {
    final match = _match;
    return AppShell(
      active: NavId.live,
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
        // Meccs-választó: a könyvtár bármely meccse vagy a demó.
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.border),
          ),
          child: DropdownButton<String?>(
            value: _selectedId,
            underline: const SizedBox(),
            dropdownColor: AppColors.surfaceAlt,
            items: [
              for (final m in _library)
                DropdownMenuItem(
                  value: m["match_id"] as String,
                  child: Text(
                      "${m["home_team"] ?? "Hazai"} vs ${m["away_team"] ?? "Vendég"}",
                      overflow: TextOverflow.ellipsis),
                ),
              const DropdownMenuItem(value: null, child: Text("Demó")),
            ],
            onChanged: (id) => _load(id),
          ),
        ),
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
        // Újraindítás az elejéről (a folyam is tisztul).
        IconButton(
          iconSize: 22,
          color: AppColors.textSecondary,
          tooltip: "Újraindítás az elejéről",
          onPressed: () => setState(() {
            _frameIndex = 0;
            _feed.clear();
          }),
          icon: const Icon(Icons.restart_alt),
        ),
        Expanded(
          child: Slider(
            value: _frameIndex.toDouble(),
            min: 0,
            max: (match.frames.length - 1).toDouble(),
            onChanged: (v) => setState(() => _frameIndex = v.round()),
          ),
        ),
        // Lejátszási sebesség (0,5–4×) — mint a meccs-elemzőben.
        PopupMenuButton<double>(
          tooltip: "Sebesség",
          color: AppColors.surface,
          onSelected: (v) {
            setState(() => _speed = v);
            _restartTimer(match);
          },
          itemBuilder: (_) => [
            for (final v in const [0.5, 1.0, 2.0, 4.0])
              PopupMenuItem(
                value: v,
                child: Text(v == v.roundToDouble() ? "${v.toInt()}×" : "$v×",
                    style: AppText.value.copyWith(
                        color: v == _speed
                            ? AppColors.accent
                            : AppColors.textPrimary)),
              ),
          ],
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: AppColors.surfaceAlt,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: Text(
                _speed == _speed.roundToDouble()
                    ? "${_speed.toInt()}×"
                    : "$_speed×",
                style: AppText.value.copyWith(
                    fontSize: 12, color: AppColors.accent)),
          ),
        ),
      ],
    );
  }

  Widget _coachingPanel(Match match) {
    final frame = match.frames[_frameIndex];
    final prev = _frameIndex > 0 ? match.frames[_frameIndex - 1] : null;
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    final now = suggestForFrame(frame, config: _cfg, prevFrame: prev, fps: fps);

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
            Text("MOST", style: AppText.sectionLabel),
          ]),
          const SizedBox(height: AppSpacing.md),
          _stateChip(Icons.sports_handball, phaseLabelHu(phase)),
          const SizedBox(height: 6),
          _stateChip(Icons.my_location,
              poss == null ? "Szabad labda"
                  : "Birtoklás: ${poss == Team.home ? match.meta.homeTeam : match.meta.awayTeam}"),
          const SizedBox(height: 6),
          _stateChip(Icons.shield_outlined, "Véd: $defLabel"),
          const SizedBox(height: AppSpacing.md),
          // Az aktuális pillanat legfontosabb javaslatai (max 3).
          for (final s in now.take(3)) ...[
            _suggestionRow(s),
            const SizedBox(height: AppSpacing.sm),
          ],
          if (now.isEmpty)
            Text("nincs aktív jelzés", style: AppText.label),
          const Divider(height: AppSpacing.xl, color: AppColors.border),
          Text("KORÁBBI JELZÉSEK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          Expanded(
            child: _feed.isEmpty
                ? Text("Indítsd el a lejátszást — a jelzések itt gyűlnek, "
                    "és koppintásra visszaugrasz a pillanatukra.",
                    style: AppText.label)
                : ListView.separated(
                    itemCount: _feed.length,
                    separatorBuilder: (_, __) =>
                        const SizedBox(height: AppSpacing.sm),
                    itemBuilder: (_, i) =>
                        _feedRow(_feed[i], fps),
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

  /// Egy folyam-bejegyzés: időbélyeg + javaslat; koppintásra odaugrunk.
  Widget _feedRow(_FeedEntry e, double fps) {
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: () => setState(() {
        _timer?.cancel();
        _playing = false;
        _frameIndex = e.frame;
      }),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 44,
          child: Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Text("${(e.frame / fps).toStringAsFixed(0)} s",
                style: AppText.label.copyWith(
                    fontSize: 11, color: AppColors.accent)),
          ),
        ),
        Expanded(child: _suggestionRow(e.suggestion)),
      ]),
    );
  }

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
