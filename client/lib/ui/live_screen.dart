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

  // Időzített taktikai jelzések a backend felismerőiből (7a6, ember-
  // hátrány, hétméteres, passzív) — a lejátszó a megfelelő pillanatban
  // tolja be őket a folyamba, arany kiemeléssel.
  List<_FeedEntry> _alerts = [];
  int _alertIdx = 0;

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
    // Időzített taktikai jelzések a backend felismerőiből (csak valódi
    // meccsnél; hibánál üres lista — a mód enélkül is teljes).
    final alerts = selected == null
        ? <_FeedEntry>[]
        : await _buildAlerts(selected, match);
    if (!mounted) return;
    _timer?.cancel();
    setState(() {
      _match = match;
      _selectedId = selected;
      _sourceLabel = label;
      _frameIndex = 0;
      _playing = false;
      _feed.clear();
      _alerts = alerts;
      _alertIdx = 0;
    });
  }

  /// A backend felismerőinek időzített jelzésekké alakítása (frame + szöveg).
  Future<List<_FeedEntry>> _buildAlerts(String matchId, Match match) async {
    final names = {
      "home": match.meta.homeTeam,
      "away": match.meta.awayTeam,
    };
    final out = <_FeedEntry>[];
    try {
      for (final w in await _api.fetchEmptyNet(matchId)) {
        final team = names[w["team"]] ?? "";
        out.add(_FeedEntry(
            (w["start_frame"] as num?)?.toInt() ?? 0,
            Suggestion(5, "taktika",
                "7 a 6! $team lehozta a kapust — labdaszerzésnél azonnali "
                "hosszú indítás az üres kapura!")));
      }
    } catch (_) {}
    try {
      final r = await _api.fetchRules(matchId);
      for (final w in ((r["powerplay"] as List?) ?? const [])
          .cast<Map<String, dynamic>>()) {
        final down = names[w["team_down"]] ?? "";
        out.add(_FeedEntry(
            (w["start_frame"] as num?)?.toInt() ?? 0,
            Suggestion(5, "taktika",
                "Emberhátrány: $down kevesebben van — a létszámfölényt "
                "gyors, széles játékkal érdemes kihasználni.")));
      }
      final sevens = ((r["seven_meters"] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
      for (final e in sevens) {
        final team = names[e["team"]] ?? "";
        final t7 = (e["t"] as num?)?.toInt() ?? 0;
        var text = "Hétméteres következik — $team dob.";
        // A dobó KORÁBBI hetesei ezen a meccsen: ha volt már mért
        // iránya, a kapus élő tippet kap (jövőbe nem nézünk).
        final sid = e["shooter_id"];
        if (sid != null) {
          final dirs = <String, int>{};
          for (final p in sevens) {
            if (p["shooter_id"] == sid &&
                ((p["t"] as num?)?.toInt() ?? 0) < t7 &&
                p["irany"] != null) {
              dirs["${p["irany"]}"] = (dirs["${p["irany"]}"] ?? 0) + 1;
            }
          }
          if (dirs.isNotEmpty) {
            final best =
                dirs.entries.reduce((a, b) => a.value >= b.value ? a : b);
            const hu = {"bal": "balra", "jobb": "jobbra",
                "közép": "középre"};
            text += " A dobó eddigi hetesei ${hu[best.key] ?? best.key} "
                "mentek (${best.value}×).";
          }
        }
        out.add(_FeedEntry(t7, Suggestion(4, "taktika", text)));
      }
      for (final a in ((r["passive_risk"] as List?) ?? const [])
          .cast<Map<String, dynamic>>()) {
        out.add(_FeedEntry(
            (a["start_frame"] as num?)?.toInt() ?? 0,
            Suggestion(4, "taktika",
                "Passzív-kockázat: elhúzódó támadás lövés nélkül — "
                "kényszeríts ritmusváltást vagy lövést.")));
      }
    } catch (_) {}
    // Félidei emberfogás-kép: a szünetben szól, ha valaki lazán őrzött
    // az első félidőben (csak az addigi kockákból — jövőbe nem nézünk).
    try {
      final d = await _api.fetchDefense(matchId);
      final fh = (d["marking_fh"] as Map?)?.cast<String, dynamic>();
      if (fh != null) {
        final atFrame = ((fh["until_frame"] as num?) ?? 0).toInt();
        for (final side in ["home", "away"]) {
          final loose =
              ((fh[side] as Map?)?["loosest"] as Map?)?.cast<String, dynamic>();
          if (loose == null) continue;
          final dist = ((loose["avg_dist_m"] as num?) ?? 0).toDouble();
          if (dist < 2.5) continue;
          final j = (loose["defender_jersey"] as num?)?.toInt();
          final who = j != null ? "$j-es" : "#${loose["defender"]}";
          final team = names[side] ?? "";
          out.add(_FeedEntry(
              atFrame,
              Suggestion(4, "taktika",
                  "Félidei kép ($team): a(z) $who átlag "
                  "${dist.toStringAsFixed(1)} m-ről őrizte az emberét — "
                  "a második félidőre szorosabb tapadást kérj.")));
        }
      }
    } catch (_) {}
    // Félidei beálló-kép: ha az első félidőben alig ment a beállón át
    // a játék (van beálló, de a támadások <=15%-a), a szünetben szól.
    try {
      final a = await _api.fetchAttacks(matchId);
      final fh = (a["pivot_fh"] as Map?)?.cast<String, dynamic>();
      if (fh != null) {
        final atFrame = ((fh["until_frame"] as num?) ?? 0).toInt();
        for (final side in ["home", "away"]) {
          final rec = (fh[side] as Map?)?.cast<String, dynamic>();
          if (rec == null) continue;
          final attacks = ((rec["attacks"] as num?) ?? 0).toInt();
          final pivots = ((rec["pivot_ids"] as List?) ?? const []);
          final share = (rec["pivot_share_pct"] as num?)?.toDouble();
          if (attacks < 5 || pivots.isEmpty || share == null) continue;
          if (share > 15.0) continue;
          final team = names[side] ?? "";
          out.add(_FeedEntry(
              atFrame,
              Suggestion(4, "taktika",
                  "Félidei kép ($team): a támadások csak "
                  "${share.toStringAsFixed(0)}%-a ment a beállón át — "
                  "a másodikban keresd a beadást, onnan jönnek a "
                  "legjobb helyzetek.")));
        }
      }
    } catch (_) {}
    // Félidei rotáció-kép: ha az első félidőt szűk kerettel nyomta
    // végig a csapat, a szünetben szól — a hajrá-fáradás megelőzhető.
    try {
      final ts = await _api.fetchTeamStats(matchId);
      final fh = (ts["rotation_fh"] as Map?)?.cast<String, dynamic>();
      if (fh != null) {
        final atFrame = ((fh["until_frame"] as num?) ?? 0).toInt();
        for (final side in ["home", "away"]) {
          final rec = (fh[side] as Map?)?.cast<String, dynamic>();
          if (rec == null) continue;
          final used = ((rec["used"] as num?) ?? 0).toInt();
          final reg = ((rec["regulars"] as num?) ?? 0).toInt();
          if (used < 6 || used > 8) continue;
          final team = names[side] ?? "";
          out.add(_FeedEntry(
              atFrame,
              Suggestion(4, "taktika",
                  "Félidei kép ($team): eddig $used emberrel ment a "
                  "meccs ($reg alapember) — frissíts a második "
                  "félidőre, a szűk rotáció a hajrában üt vissza.")));
        }
      }
    } catch (_) {}
    // Hajrá-protokoll: ha a hajrá szoros állásról indul, az utolsó
    // szakasz kezdetén szól a padnak — a döntéseket előre kell hozni.
    try {
      final pr = await _api.fetchProgression(matchId);
      final cl = (pr["clutch"] as Map?)?.cast<String, dynamic>();
      if (cl != null &&
          (cl["available"] as bool? ?? false) &&
          (cl["close"] as bool? ?? false)) {
        final winS = ((cl["window_s"] as num?) ?? 300).toDouble();
        final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
        final atFrame = (match.frames.length - winS * fps).round();
        final ss = ((cl["start_score"] as List?) ?? const [0, 0]);
        if (atFrame > 0) {
          out.add(_FeedEntry(
              atFrame,
              Suggestion(5, "taktika",
                  "Hajrá-protokoll: ${ss[0]}–${ss[1]} az állás, "
                  "${(winS / 60).round()} perc van hátra — időkérés-terv "
                  "elő, eldöntött hetes-dobó, 7 a 6 döntés; minden "
                  "támadás lövéssel záruljon.")));
        }
      }
    } catch (_) {}
    // Vezetés-váltások: a meccs gerincéből — élőben ez a "most fordult
    // a meccs" pillanat, a padnak azonnal reagálnia kell.
    try {
      for (final m in await _api.fetchKeyMoments(matchId)) {
        final label = "${(m as Map)["label"]}";
        if (!label.startsWith("Vezetés-váltás")) continue;
        out.add(_FeedEntry(
            (m["t"] as num?)?.toInt() ?? 0,
            Suggestion(5, "momentum",
                "$label — reagálj: időkérés vagy védekezés-váltás "
                "jöhet.")));
      }
    } catch (_) {}
    // Gól-sorozatok: a széria lezárultakor jelzés az okokkal — élőben ez
    // az "időt kell kérni / váltani kell" pillanat.
    try {
      for (final r in await _api.fetchMomentum(matchId)) {
        final team = names[r["team"]] ?? "";
        final ctx = ((r["context"] as List?) ?? const []).cast<String>();
        out.add(_FeedEntry(
            (r["end_frame"] as num?)?.toInt() ?? 0,
            Suggestion(
                5,
                "momentum",
                "${r["length"]}-0-s sorozat: $team elhúzott"
                "${ctx.isNotEmpty ? " (${ctx.first})" : ""} — időkérés vagy "
                "védekezés-váltás jöhet.")));
      }
    } catch (_) {}
    // Cserehullámok: a forgatás utáni első támadás a legérzékenyebb.
    try {
      final si = await _api.fetchSubstitutions(matchId);
      for (final ev in ((si["events"] as List?) ?? const [])
          .cast<Map<String, dynamic>>()) {
        final team = names[ev["team"]] ?? "";
        out.add(_FeedEntry(
            (ev["t"] as num?)?.toInt() ?? 0,
            Suggestion(3, "csere",
                "Cserehullám: $team frissít — az első támadásukra dupla "
                "figyelem, a friss sor tempót válthat.")));
      }
    } catch (_) {}
    // Időkérések: a folytatásban gyakran vált a védekezés.
    try {
      for (final st in await _api.fetchStoppages(matchId)) {
        if (st["kind"] != "időkérés") continue;
        final team = names[st["likely_team"]] ?? "";
        out.add(_FeedEntry(
            (st["start_frame"] as num?)?.toInt() ?? 0,
            Suggestion(
                4,
                "taktika",
                "Időkérés${team.isNotEmpty ? " ($team)" : ""} — a "
                "folytatásban figyeld a felállást: gyakran itt jön a "
                "védekezés-váltás.")));
      }
    } catch (_) {}
    out.sort((a, b) => a.frame.compareTo(b.frame));
    return out;
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
    // Időzített taktikai jelzések: az épp esedékesek a folyam elejére.
    while (_alertIdx < _alerts.length &&
        _alerts[_alertIdx].frame <= _frameIndex) {
      _feed.insert(0, _alerts[_alertIdx]);
      _alertIdx++;
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
            _alertIdx = 0;
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
