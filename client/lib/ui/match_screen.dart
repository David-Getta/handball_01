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
import "package:flutter/services.dart";

import "../analytics/court_analytics.dart";
import "../analytics/match_summary.dart";
import "../analytics/tactics.dart";
import "../models/tracking.dart";
import "../services/api_client.dart";
import "../sim/demo_data.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";
import "court_painter.dart";
import "decisions_panel.dart";
import "designer_screen.dart";
import "scouting_screen.dart";
import "heatmap_painter.dart";
import "pass_network_painter.dart";
import "shell/app_shell.dart";
import "shot_map_painter.dart";
import "stats_panel.dart";
import "story_timeline.dart";
import "summary_panel.dart";
import "video_panel.dart";

enum ViewMode { players, heatmap, shots, passes }

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
  // Tempó-alakulás idő-ablakonként (fáradás-grafikon az Összegzés fülön).
  List<IntensityWindow> _intensity = [];
  // Védekezés-idővonal (mikor milyen formát játszottak) — Összegzés fül.
  List<FormationWindow> _formations = [];
  // Felismert események a backendből (passz/lövés/gól/labdaeladás) — kattintásra
  // a lejátszó az esemény képkockájára ugrik. Demó módban üres.
  List<Map<String, dynamic>> _events = [];
  // A feldolgozás minőség-önellenőrzése (score + figyelmeztetések) — a
  // felhasználó lássa, mennyire megbízható az elemzés. Demó módban null.
  Map<String, dynamic>? _quality;
  // Automatikus edzői összefoglaló (GET /matches/{id}/coach-summary).
  Map<String, dynamic>? _coach;
  // Címkézett támadás-szakaszok (GET /matches/{id}/attacks).
  List<Map<String, dynamic>> _attacks = [];
  // Gól-sorozatok (GET /matches/{id}/momentum) — az eredmény-grafikonon.
  List<Map<String, dynamic>> _momentum = [];
  // Lövőnkénti helyzetminőség (player_id → {shots, goals, xg, diff}).
  Map<int, Map<String, dynamic>> _xgShooters = {};
  // Szabály-réteg (GET /matches/{id}/rules): 7m, emberhátrány, passzív.
  Map<String, dynamic> _rules = {};
  List<Map<String, dynamic>> _emptyNet = [];
  List<Map<String, dynamic>> _subs = [];
  List<Map<String, dynamic>> _stoppages = [];
  // Esemény-szűrő az Események fülön (all/goal/shot/turnover/pass) — az
  // előző/következő esemény léptetés is a szűrt listán belül ugrál.
  String _eventFilter = "all";
  // Fut-e épp videóklip-export (a gomb letiltásához + pörgettyűhöz).
  bool _exportingClips = false;
  // Fut-e épp meccs-csomag export.
  bool _exportingPackage = false;
  // Edzői jegyzetek (időbélyeggel) — a backend menti, kattintásra odaugrik
  // a lejátszó. Demó módban nem elérhető (nincs hova menteni).
  List<Map<String, dynamic>> _notes = [];
  final TextEditingController _noteCtrl = TextEditingController();
  bool _savingNote = false;
  int _frameIndex = 0;
  bool _playing = false;
  String _sourceLabel = "betöltés…";
  Timer? _timer;

  ViewMode _viewMode = ViewMode.players;
  Team _heatmapTeam = Team.home;
  Heatmap? _heatmap;
  // Lejátszási sebesség (0.5–4×) — elemzésnél a gyors áttekintés kulcsa.
  double _speed = 1.0;
  // Lövéstérkép: a lövés/gól események helye a pályán (a lövő pozíciójából,
  // annak híján a labdáéból). Koppintásra a lejátszó a jelenetre ugrik.
  List<ShotMarker> _shots = [];
  String _shotTeam = "all"; // all | home | away — szűrő a lövéstérképen
  // Passzháló: melyik csapatét mutatjuk (a két háló egymáson olvashatatlan).
  Team _passTeam = Team.home;
  PassNetwork? _passNetwork; // a kiválasztott csapat hálója (cache)

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
    _noteCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    Match match;
    String label;
    List<Map<String, dynamic>> events = [];
    Map<String, dynamic>? quality;
    List<Map<String, dynamic>> notes = [];
    Map<String, dynamic>? coach;
    List<Map<String, dynamic>> attacks = [];
    List<Map<String, dynamic>> momentum = [];
    Map<String, dynamic> rules = {};
    List<Map<String, dynamic>> emptyNet = [];
    List<Map<String, dynamic>> subs = [];
    List<Map<String, dynamic>> stoppages = [];
    Map<int, double> xgByT = {};
    Map<int, Map<String, dynamic>> xgShooters = {};
    Map<int, bool> freeByT = {};
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
          coach = await _api.fetchCoachSummary(widget.matchId);
        } catch (_) {
          coach = null; // az összefoglaló nélkül is teljes a nézet
        }
        try {
          final r = await _api.fetchAttacks(widget.matchId);
          attacks = (r["attacks"] as List).cast<Map<String, dynamic>>();
        } catch (_) {
          attacks = []; // támadás-címkék nélkül is teljes a nézet
        }
        try {
          rules = await _api.fetchRules(widget.matchId);
        } catch (_) {
          rules = {}; // szabály-réteg nélkül is teljes a nézet
        }
        try {
          emptyNet = await _api.fetchEmptyNet(widget.matchId);
        } catch (_) {
          emptyNet = []; // 7 a 6 réteg nélkül is teljes a nézet
        }
        try {
          final si = await _api.fetchSubstitutions(widget.matchId);
          subs = ((si["events"] as List?) ?? const [])
              .cast<Map<String, dynamic>>();
        } catch (_) {
          subs = []; // csere-réteg nélkül is teljes a nézet
        }
        try {
          stoppages = await _api.fetchStoppages(widget.matchId);
        } catch (_) {
          stoppages = []; // megszakítás-réteg nélkül is teljes a nézet
        }
        try {
          momentum = await _api.fetchMomentum(widget.matchId);
        } catch (_) {
          momentum = []; // sorozatok nélkül is teljes a nézet
        }
        try {
          final xg = await _api.fetchXg(widget.matchId);
          for (final sh in (xg["shots"] as List).cast<Map<String, dynamic>>()) {
            final t = (sh["t"] as num?)?.toInt();
            final v = (sh["xg"] as num?)?.toDouble();
            if (t != null && v != null) xgByT[t] = v;
          }
          for (final r
              in ((xg["shooters"] as List?) ?? const []).cast<Map<String, dynamic>>()) {
            final pid = (r["player_id"] as num?)?.toInt();
            if (pid != null) xgShooters[pid] = r;
          }
        } catch (_) {
          xgByT = {}; // helyzetminőség nélkül is teljes a nézet
          xgShooters = {};
        }
        try {
          final d = await _api.fetchDefense(widget.matchId);
          for (final side in ["home", "away"]) {
            for (final sh in (((d[side] as Map?)?["shots"] as List?) ?? const [])
                .cast<Map<String, dynamic>>()) {
              final t = (sh["t"] as num?)?.toInt();
              final fr = sh["free"] as bool?;
              if (t != null && fr != null) freeByT[t] = fr;
            }
          }
        } catch (_) {
          freeByT = {}; // védekezés-réteg nélkül is teljes a nézet
        }
        try {
          quality = await _api.fetchQuality(widget.matchId);
        } catch (_) {
          quality = null; // minőség-jelentés nélkül is teljes a nézet
        }
        try {
          notes = await _api.fetchNotes(widget.matchId);
        } catch (_) {
          notes = []; // jegyzetek nélkül is teljes a nézet
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
      _intensity = computeIntensityTimeline(match);
      _formations = computeFormationTimeline(match);
      _events = events;
      _shots = _computeShotMarkers(match, events, xgByT, freeByT);
      _xgShooters = xgShooters;
      _passNetwork = computePassNetwork(match, events, _passTeam);
      _quality = quality;
      _notes = notes;
      _coach = coach;
      _attacks = attacks;
      _momentum = momentum;
      _rules = rules;
      _emptyNet = emptyNet;
      _subs = subs;
      _stoppages = stoppages;
      _sourceLabel = label;
      _frameIndex = 0;
      _heatmap = computeTeamHeatmap(match, _heatmapTeam);
    });
  }

  /// A lövés/gól események helye a pályán. A lövő játékos pozícióját
  /// használjuk az esemény képkockájából; ha a lövő nem azonosítható, a
  /// labda helyét; ha az sincs, az eseményt kihagyjuk a térképről.
  List<ShotMarker> _computeShotMarkers(
      Match match, List<Map<String, dynamic>> events, Map<int, double> xgByT,
      Map<int, bool> freeByT) {
    // frame.t → frame index (a t nem feltétlenül a lista-index).
    final byT = <int, Frame>{for (final f in match.frames) f.t: f};
    final out = <ShotMarker>[];
    for (final e in events) {
      final type = e["type"] as String?;
      if (type != "shot" && type != "goal") continue;
      final t = (e["t"] as num?)?.toInt() ?? 0;
      final frame = byT[t];
      if (frame == null) continue;
      final team = e["team"] == "home" ? Team.home : Team.away;
      final pid = (e["player_id"] as num?)?.toInt();
      double? x, y;
      if (pid != null) {
        for (final p in frame.players) {
          if (p.trackId == pid) {
            x = p.x;
            y = p.y;
            break;
          }
        }
      }
      if (x == null && frame.ball != null) {
        x = frame.ball!.x;
        y = frame.ball!.y;
      }
      if (x == null || y == null) continue;
      out.add(ShotMarker(t, team, type == "goal", x, y,
          xg: xgByT[t], free: freeByT[t]));
    }
    return out;
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
    _restartTimer(match);
  }

  /// A lejátszó-óra (újra)indítása az aktuális sebességgel — sebesség-
  /// váltásnál futás közben is újraindul.
  void _restartTimer(Match match) {
    _timer?.cancel();
    if (!_playing) return;
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    final interval = (1000 / (fps * _speed)).round().clamp(8, 4000);
    _timer = Timer.periodic(Duration(milliseconds: interval), (_) {
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

  /// Léptetés adott számú képkockával (billentyűzet: ←/→, Shift+←/→).
  void _step(Match match, int frames) {
    setState(() {
      _timer?.cancel();
      _playing = false;
      _frameIndex = (_frameIndex + frames).clamp(0, match.frames.length - 1);
    });
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
              : _withShortcuts(match, Column(
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
            )),
    );
  }

  /// Billentyűzet-vezérlés a lejátszóhoz: szóköz = lejátszás/szünet,
  /// ←/→ = 1 kocka, Shift+←/→ = 5 mp, Q/E = előző/következő esemény.
  /// Szövegmezőben gépelve a karakterek a mezőé maradnak (a fókuszált
  /// TextField elnyeli őket), így a jegyzetírást nem zavarja.
  Widget _withShortcuts(Match match, Widget child) {
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.space): _togglePlay,
        const SingleActivator(LogicalKeyboardKey.arrowLeft): () =>
            _step(match, -1),
        const SingleActivator(LogicalKeyboardKey.arrowRight): () =>
            _step(match, 1),
        const SingleActivator(LogicalKeyboardKey.arrowLeft, shift: true): () =>
            _step(match, -(5 * fps).round()),
        const SingleActivator(LogicalKeyboardKey.arrowRight, shift: true): () =>
            _step(match, (5 * fps).round()),
        const SingleActivator(LogicalKeyboardKey.keyQ): () =>
            _jumpToEvent(match, -1),
        const SingleActivator(LogicalKeyboardKey.keyE): () =>
            _jumpToEvent(match, 1),
        // Fel/le nyíl: ugyanaz, mint a Q/E — előző/következő ugrópont
        // az AKTÍV szűrő szerint (esemény / támadás-típus / szabály).
        const SingleActivator(LogicalKeyboardKey.arrowUp): () =>
            _jumpToEvent(match, -1),
        const SingleActivator(LogicalKeyboardKey.arrowDown): () =>
            _jumpToEvent(match, 1),
      },
      child: Focus(autofocus: true, child: child),
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
    final attackMode = _eventFilter.startsWith("atk:");
    final ruleMode = _eventFilter.startsWith("rule:");
    final shownAttacks = attackMode
        ? [
            for (final a in _attacks)
              if (a["type"] == _eventFilter.substring(4)) a
          ]
        : const <Map<String, dynamic>>[];
    final shownRules = ruleMode ? _ruleRows() : const <Map<String, dynamic>>[];
    final shown = (attackMode || ruleMode)
        ? const <Map<String, dynamic>>[]
        : _filteredEvents();
    return Column(children: [
      // Típus-szűrő: az edző pl. csak a gólokat nézi végig, gólról gólra.
      // A támadás-címkék (atk:) a szakasz-listára váltanak.
      Padding(
        padding: const EdgeInsets.fromLTRB(
            AppSpacing.md, AppSpacing.md, AppSpacing.md, 0),
        child: Row(children: [
          Expanded(
            child: Wrap(spacing: 6, runSpacing: 4, children: [
              _filterChip("all", "Mind"),
              _filterChip("goal", "Gól"),
              _filterChip("shot", "Lövés"),
              _filterChip("turnover", "Labdaeladás"),
              _filterChip("pass", "Passz"),
              if (_attacks.isNotEmpty) ...[
                _filterChip("atk:lerohanás", "Lerohanás"),
                _filterChip("atk:gyors indítás", "Gyors indítás"),
                _filterChip("atk:felállt támadás", "Felállt"),
                _filterChip("atk:7 a 6", "7 a 6"),
              ],
              if ((_rules["seven_meters"] as List?)?.isNotEmpty ?? false)
                _filterChip("rule:7m", "Hétméteres"),
              if ((_rules["powerplay"] as List?)?.isNotEmpty ?? false)
                _filterChip("rule:pp", "Emberhátrány"),
              if ((_rules["passive_risk"] as List?)?.isNotEmpty ?? false)
                _filterChip("rule:passive", "Passzív-kockázat"),
            ]),
          ),
          // Klip-export: a SZŰRT eseménytípusok jelenetei MP4-ekben, zip-ben.
          IconButton(
            tooltip: _exportingClips
                ? "Klipvágás folyamatban…"
                : "Videóklipek exportálása (a szűrt típusból)",
            onPressed:
                _exportingClips ? null : () => _exportClips(match),
            icon: _exportingClips
                ? const SizedBox(width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.movie_outlined, color: AppColors.accent),
          ),
        ]),
      ),
      Expanded(
        child: ruleMode
            ? (shownRules.isEmpty
                ? Center(child: Text("Nincs ilyen szakasz.",
                    style: AppText.label))
                : ListView.separated(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    itemCount: shownRules.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 6),
                    itemBuilder: (_, i) =>
                        _ruleRow(shownRules[i], fps, match),
                  ))
            : attackMode
            ? (shownAttacks.isEmpty
                ? Center(child: Text("Nincs ilyen típusú támadás.",
                    style: AppText.label))
                : ListView.separated(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    itemCount: shownAttacks.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 6),
                    itemBuilder: (_, i) =>
                        _attackRow(shownAttacks[i], fps, match),
                  ))
            : shown.isEmpty
                ? Center(
                    child: Text("Nincs ilyen típusú esemény.", style: AppText.label))
                : ListView.separated(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    itemCount: shown.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 6),
                    itemBuilder: (_, i) => _eventRow(shown[i], fps, match),
                  ),
      ),
    ]);
  }

  /// A kiválasztott szabály-szűrő (rule:...) sorai egységes alakban:
  /// {"label", "team", "frame", "duration_s"?}.
  List<Map<String, dynamic>> _ruleRows() {
    switch (_eventFilter) {
      case "rule:7m":
        return [
          for (final e in ((_rules["seven_meters"] as List?) ?? const [])
              .cast<Map<String, dynamic>>())
            {
              // A kimenetel a backendről jön (gól/védés/kihagyva) — ha van,
              // a címkében is látszik.
              "label": (e["outcome"] as String?) != null &&
                      e["outcome"] != "ismeretlen"
                  ? "Hétméteres — ${e["outcome"]}"
                  : "Hétméteres",
              "team": e["team"],
              "frame": e["t"],
            },
        ];
      case "rule:pp":
        return [
          for (final w in ((_rules["powerplay"] as List?) ?? const [])
              .cast<Map<String, dynamic>>())
            {"label": "Emberhátrány", "team": w["team_down"],
             "frame": w["start_frame"], "duration_s": w["duration_s"]},
        ];
      case "rule:passive":
        return [
          for (final a in ((_rules["passive_risk"] as List?) ?? const [])
              .cast<Map<String, dynamic>>())
            {"label": "Passzív-kockázat", "team": a["team"],
             "frame": a["start_frame"], "duration_s": a["duration_s"]},
        ];
    }
    return const [];
  }

  /// Egy szabály-szakasz sora — koppintásra a lejátszó odaugrik.
  Widget _ruleRow(Map<String, dynamic> r, double fps, Match match) {
    final frame = (r["frame"] as num?)?.toInt() ?? 0;
    final durS = (r["duration_s"] as num?)?.toDouble();
    final team = (r["team"] as String?) == "home"
        ? match.meta.homeTeam
        : match.meta.awayTeam;
    final label = (r["label"] as String?) ?? "";
    final (icon, color) = switch (label) {
      "Hétméteres" => (Icons.sports_score, AppColors.gold),
      "Emberhátrány" => (Icons.person_remove, AppColors.away),
      _ => (Icons.hourglass_bottom, AppColors.textSecondary),
    };
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: () => _seekToFrame(match, frame),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: _frameIndex == frame
              ? AppColors.accentSoft
              : AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Text(label, style: AppText.value.copyWith(fontSize: 12.5, color: color)),
          const SizedBox(width: 8),
          Expanded(child: Text(team,
              style: AppText.label.copyWith(fontSize: 11.5),
              overflow: TextOverflow.ellipsis)),
          Text(
              durS == null
                  ? "${(frame / fps).toStringAsFixed(1)} s"
                  : "${(frame / fps).toStringAsFixed(1)} s · ${durS.toStringAsFixed(1)} s",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
    );
  }

  /// Egy címkézett támadás-szakasz sora: típus + csapat + kezdet/hossz —
  /// koppintásra a lejátszó a szakasz elejére ugrik.
  Widget _attackRow(Map<String, dynamic> a, double fps, Match match) {
    final start = (a["start_frame"] as num?)?.toInt() ?? 0;
    final durS = (a["duration_s"] as num?)?.toDouble() ?? 0.0;
    final team = (a["team"] as String?) == "home"
        ? match.meta.homeTeam
        : match.meta.awayTeam;
    final type = (a["type"] as String?) ?? "";
    final (icon, color) = switch (type) {
      "lerohanás" => (Icons.bolt, AppColors.gold),
      "gyors indítás" => (Icons.fast_forward, AppColors.accent),
      "7 a 6" => (Icons.group_add, AppColors.away),
      _ => (Icons.grid_view, AppColors.textSecondary),
    };
    final selected = _frameIndex >= start &&
        _frameIndex <= ((a["end_frame"] as num?)?.toInt() ?? start);
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: () => _seekToFrame(match, start),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? AppColors.accentSoft : AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Text(type, style: AppText.value.copyWith(fontSize: 12.5, color: color)),
          const SizedBox(width: 8),
          Expanded(child: Text(team,
              style: AppText.label.copyWith(fontSize: 11.5),
              overflow: TextOverflow.ellipsis)),
          Text("${(start / fps).toStringAsFixed(1)} s · ${durS.toStringAsFixed(1)} s",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
    );
  }

  /// Videóklip-export: a szűrt eseménytípusok jelenetei külön MP4-ekbe,
  /// egy zip-be csomagolva. A vágás a backenden fut (job), a haladást
  /// pollozzuk, a kész zip-et a felhasználó által választott helyre mentjük.
  Future<void> _exportClips(Match match) async {
    // "Mind" (és támadás-) szűrőnél passz-klipeket nem vágunk (túl sok,
    // kevés érték) — a klip-export az eseménytípusokból dolgozik.
    final types = _eventFilter == "all" || _eventFilter.startsWith("atk:")
        ? ["goal", "shot", "turnover"]
        : [_eventFilter];
    if (types.contains("pass") && types.length == 1) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text("Passzokból nem készül klip — válassz gólt, lövést "
              "vagy labdaeladást.")));
      return;
    }
    setState(() => _exportingClips = true);
    try {
      final jobId = await _api.startClipExport(widget.matchId, types);
      // A vágás haladásának követése (másodpercenként).
      while (true) {
        await Future.delayed(const Duration(seconds: 1));
        final job = await _api.fetchJob(jobId);
        final status = job["status"] as String?;
        if (status == "done") break;
        if (status == "error") {
          throw Exception(job["error"] ?? "ismeretlen hiba");
        }
        if (!mounted) return; // közben elnavigáltak — a job magától befejeződik
      }
      final bytes = await _api.fetchClipsZip(widget.matchId);
      if (!mounted) return;
      final name = "${match.meta.homeTeam}_${match.meta.awayTeam}"
          .replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Videóklipek mentése (zip)",
        fileName: "klipek_$name.zip",
        type: FileType.custom,
        allowedExtensions: const ["zip"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Klipek mentve: $path — kicsomagolás után "
              "lejátszhatók/megoszthatók")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Klip-export hiba: $e")));
    } finally {
      if (mounted) setState(() => _exportingClips = false);
    }
  }

  /// Meccs-csomag: jelentés + CSV + gólklipek egy zip-ben (a backend állítja
  /// össze job-ként), mentés a felhasználó által választott helyre.
  Future<void> _exportPackage() async {
    final match = _match;
    if (match == null) return;
    setState(() => _exportingPackage = true);
    try {
      final jobId =
          await _api.startPackageExport(widget.matchId, const ["goal"]);
      while (true) {
        await Future.delayed(const Duration(seconds: 1));
        final job = await _api.fetchJob(jobId);
        final status = job["status"] as String?;
        if (status == "done") break;
        if (status == "error") {
          throw Exception(job["error"] ?? "ismeretlen hiba");
        }
        if (!mounted) return;
      }
      final bytes = await _api.fetchPackageZip(widget.matchId);
      if (!mounted) return;
      final name = "${match.meta.homeTeam}_${match.meta.awayTeam}"
          .replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Meccs-csomag mentése (zip)",
        fileName: "meccs_csomag_$name.zip",
        type: FileType.custom,
        allowedExtensions: const ["zip"],
      );
      if (path == null) return;
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Meccs-csomag mentve: $path — jelentés + statisztika "
              "+ gólklipek egy fájlban, mehet a csapatnak.")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Csomag-export hiba: $e")));
    } finally {
      if (mounted) setState(() => _exportingPackage = false);
    }
  }

  /// A szűrőnek megfelelő események — az „előző/következő" léptetés is ezt
  /// használja, így a léptetés a kiválasztott típuson belül ugrál.
  List<Map<String, dynamic>> _filteredEvents() {
    if (_eventFilter == "all") return _events;
    return _events.where((e) => e["type"] == _eventFilter).toList();
  }

  Widget _filterChip(String value, String label) {
    final selected = _eventFilter == value;
    return ChoiceChip(
      label: Text(label, style: AppText.label.copyWith(
          fontSize: 11,
          color: selected ? AppColors.onAccent : AppColors.textSecondary)),
      selected: selected,
      showCheckmark: false,
      selectedColor: AppColors.accent,
      backgroundColor: AppColors.surfaceAlt,
      side: BorderSide(color: selected ? AppColors.accent : AppColors.border),
      visualDensity: VisualDensity.compact,
      onSelected: (_) => setState(() => _eventFilter = value),
    );
  }

  Widget _eventRow(Map<String, dynamic> e, double fps, Match match) {
    final type = (e["type"] as String?) ?? "";
    final t = (e["t"] as num?)?.toInt() ?? 0;
    final team = (e["team"] as String?) == "home" ? match.meta.homeTeam : match.meta.awayTeam;
    // Lövés-kimenetel a backendtől: védés (a kapus hárította) vagy mellé.
    final outcome = ((e["detail"] as Map?)?["outcome"] as String?) ?? "";
    // Gólpassz (assist): a backend a gól detail-jébe teszi a passzoló id-ját.
    final assistId = ((e["detail"] as Map?)?["assist_id"] as num?)?.toInt();
    final (label, icon, color) = switch (type) {
      "goal" => ("GÓL", Icons.sports_score, AppColors.gold),
      "shot" when outcome == "save" =>
        ("Lövés — védés", Icons.front_hand, AppColors.accent),
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
          Expanded(child: Text(
              assistId == null
                  ? team
                  : "$team · gólpassz: ${_playerShort(match, assistId)}",
              style: AppText.label.copyWith(fontSize: 11.5),
              overflow: TextOverflow.ellipsis)),
          Text("${(t / fps).toStringAsFixed(1)} s", style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
    );
  }

  /// Rövid játékos-címke az eseménysorhoz: mezszám, ha ismert ("#7"),
  /// különben a track sorszáma ("12. játékos").
  String _playerShort(Match match, int trackId) {
    for (final f in match.frames) {
      for (final p in f.players) {
        if (p.trackId == trackId && p.jerseyNumber != null) {
          return "#${p.jerseyNumber}";
        }
      }
    }
    return "$trackId. játékos";
  }

  /// Edzői jegyzetek: a lejátszó aktuális idejéhez fűzhető megjegyzés.
  /// A jegyzet a backendre mentődik, kattintásra a lejátszó odaugrik,
  /// és a HTML-jelentésbe is bekerül.
  Widget _notesPanel(Match match) {
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    final demo = _sourceLabel == "demó";
    return Column(children: [
      // Új jegyzet a lejátszó aktuális pillanatához.
      Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: _noteCtrl,
              enabled: !demo && !_savingNote,
              style: AppText.value.copyWith(fontSize: 13),
              decoration: InputDecoration(
                isDense: true,
                hintText: demo
                    ? "Demó módban nem menthető jegyzet"
                    : "Jegyzet ${(_frameIndex / fps).toStringAsFixed(1)} s-hez…",
                hintStyle: AppText.label.copyWith(fontSize: 12),
              ),
              onSubmitted: (_) => _addNote(match),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          IconButton(
            onPressed: demo || _savingNote ? null : () => _addNote(match),
            icon: const Icon(Icons.add_comment, color: AppColors.accent),
            tooltip: "Jegyzet hozzáadása",
          ),
        ]),
      ),
      Expanded(
        child: _notes.isEmpty
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: Text(
                    demo
                        ? "A jegyzetek a backenden tárolódnak — demó módban nem elérhetők."
                        : "Állítsd a lejátszót a kívánt pillanatra, és írd be a megjegyzést — "
                            "a jegyzet a jelentésbe is bekerül.",
                    style: AppText.label,
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            : ListView.separated(
                padding: const EdgeInsets.fromLTRB(
                    AppSpacing.md, 0, AppSpacing.md, AppSpacing.md),
                itemCount: _notes.length,
                separatorBuilder: (_, __) => const SizedBox(height: 6),
                itemBuilder: (_, i) => _noteRow(_notes[i], fps, match),
              ),
      ),
    ]);
  }

  Widget _noteRow(Map<String, dynamic> n, double fps, Match match) {
    final frame = (n["frame"] as num?)?.toInt() ?? 0;
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      // Ugrás a jegyzet pillanatára — mint az eseményeknél.
      onTap: () {
        setState(() {
          _timer?.cancel();
          _playing = false;
          _frameIndex = frame.clamp(0, match.frames.length - 1);
          if (match.meta.videoPath != null && VideoPanel.supported) {
            _showVideo = true;
          }
        });
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _videoKey.currentState?.seekTo(match.meta.videoSecondsOfFrame(frame));
        });
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: _frameIndex == frame ? AppColors.accentSoft : AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(children: [
          const Icon(Icons.sticky_note_2_outlined, size: 16, color: AppColors.gold),
          const SizedBox(width: 8),
          Text("${(frame / fps).toStringAsFixed(1)} s",
              style: AppText.value.copyWith(fontSize: 12, color: AppColors.accent)),
          const SizedBox(width: 8),
          Expanded(
            child: Text((n["text"] as String?) ?? "",
                style: AppText.label.copyWith(
                    fontSize: 12.5, color: AppColors.textPrimary)),
          ),
          InkWell(
            onTap: () => _deleteNote(n),
            child: const Icon(Icons.close, size: 14, color: AppColors.textFaint),
          ),
        ]),
      ),
    );
  }

  Future<void> _addNote(Match match) async {
    final text = _noteCtrl.text.trim();
    if (text.isEmpty || _savingNote) return;
    setState(() => _savingNote = true);
    try {
      await _api.addNote(widget.matchId, _frameIndex, text);
      final notes = await _api.fetchNotes(widget.matchId);
      if (!mounted) return;
      setState(() {
        _notes = notes;
        _noteCtrl.clear();
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Nem sikerült menteni a jegyzetet: $e")));
    } finally {
      if (mounted) setState(() => _savingNote = false);
    }
  }

  Future<void> _deleteNote(Map<String, dynamic> n) async {
    final id = (n["id"] as String?) ?? "";
    if (id.isEmpty) return;
    try {
      await _api.deleteNote(widget.matchId, id);
      if (!mounted) return;
      setState(() => _notes.removeWhere((x) => x["id"] == id));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Nem sikerült törölni a jegyzetet: $e")));
    }
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
        // MECCS-CSOMAG: jelentés + CSV + gólklipek EGY zip-ben — megosztásra.
        IconButton(
          onPressed: _sourceLabel == "demó" || _exportingPackage
              ? null
              : _exportPackage,
          icon: _exportingPackage
              ? const SizedBox(width: 18, height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.card_giftcard, color: AppColors.accent),
          tooltip: "Meccs-csomag (jelentés + CSV + gólklipek egy zip-ben)",
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
            ButtonSegment(value: ViewMode.shots, label: Text("Lövések"), icon: Icon(Icons.sports_handball, size: 18)),
            ButtonSegment(value: ViewMode.passes, label: Text("Passzháló"), icon: Icon(Icons.hub_outlined, size: 18)),
          ],
          selected: {_viewMode},
          onSelectionChanged: (s) => setState(() => _viewMode = s.first),
        ),
        const SizedBox(width: AppSpacing.md),
        if (_viewMode == ViewMode.passes)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: DropdownButton<Team>(
              value: _passTeam,
              underline: const SizedBox(),
              dropdownColor: AppColors.surfaceAlt,
              items: [
                DropdownMenuItem(value: Team.home, child: Text(match.meta.homeTeam)),
                DropdownMenuItem(value: Team.away, child: Text(match.meta.awayTeam)),
              ],
              onChanged: (t) {
                if (t == null) return;
                setState(() {
                  _passTeam = t;
                  _passNetwork = computePassNetwork(_match!, _events, t);
                });
              },
            ),
          ),
        if (_viewMode == ViewMode.shots)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: DropdownButton<String>(
              value: _shotTeam,
              underline: const SizedBox(),
              dropdownColor: AppColors.surfaceAlt,
              items: [
                const DropdownMenuItem(value: "all", child: Text("Mindkét csapat")),
                DropdownMenuItem(value: "home", child: Text(match.meta.homeTeam)),
                DropdownMenuItem(value: "away", child: Text(match.meta.awayTeam)),
              ],
              onChanged: (v) =>
                  v == null ? null : setState(() => _shotTeam = v),
            ),
          ),
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
            if (_viewMode == ViewMode.shots)
              Positioned.fill(
                child: CustomPaint(
                  painter: ShotMapPainter(
                      shots: _filteredShots(), currentFrame: _frameIndex),
                ),
              ),
            if (_viewMode == ViewMode.shots)
              Positioned(left: 10, top: 10, child: _shotMapChip()),
            if (_viewMode == ViewMode.passes && _passNetwork != null)
              Positioned.fill(
                child: CustomPaint(
                  painter: PassNetworkPainter(
                      network: _passNetwork!, team: _passTeam),
                ),
              ),
            if (_viewMode == ViewMode.passes)
              Positioned(left: 10, top: 10, child: _passNetworkChip(match)),
            // A kijelölt játékos adat-kártyája (bal-felső sarok).
            if (_selectedTrack != null && _viewMode == ViewMode.players)
              Positioned(left: 10, top: 10, child: _playerChip(match)),
          ],
        ),
      );
    });
  }

  /// A csapat-szűrőnek megfelelő lövés-jelölők.
  List<ShotMarker> _filteredShots() {
    if (_shotTeam == "all") return _shots;
    final team = _shotTeam == "home" ? Team.home : Team.away;
    return _shots.where((s) => s.team == team).toList();
  }

  /// A lövéstérkép összegző kártyája (bal-felső sarok): lövések, gólok,
  /// hatékonyság + zóna-bontás (irány és távolság szerint). A csapat-
  /// szűrővel nézőpontot váltasz: a saját csapat = honnan lövünk; az
  /// ellenfél = honnan kapjuk (védekezés-elemzés).
  Widget _shotMapChip() {
    final shots = _filteredShots();
    final goals = shots.where((s) => s.goal).length;
    final pct = shots.isEmpty ? 0 : (goals * 100 / shots.length).round();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.surface.withOpacity(0.92),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisSize: MainAxisSize.min, children: [
          Container(width: 9, height: 9, decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: AppColors.gold, width: 2))),
          const SizedBox(width: 4),
          Text("gól", style: AppText.label.copyWith(fontSize: 11)),
          const SizedBox(width: 10),
          Container(width: 9, height: 9, decoration: const BoxDecoration(
              color: AppColors.textFaint, shape: BoxShape.circle)),
          const SizedBox(width: 4),
          Text("lövés", style: AppText.label.copyWith(fontSize: 11)),
          const SizedBox(width: 12),
          Text(shots.isEmpty
                  ? "nincs felismert lövés"
                  : "$goals gól / ${shots.length} lövés · $pct%",
              style: AppText.value.copyWith(fontSize: 12)),
        ]),
        if (shots.isNotEmpty) ...[
          const SizedBox(height: 6),
          _zoneLine("irány", _zoneBreakdown(shots, _lateralZone,
              const ["bal szél", "közép", "jobb szél"])),
          _zoneLine("táv", _zoneBreakdown(shots, _distanceZone,
              const ["6 m-es", "9 m-es", "távoli"])),
          // Várható gól (xG): a helyzetek összesített értéke — a tényleges
          // gólszámmal összevetve látszik a befejezés hatékonysága.
          // Szabad lövések a szűrt lövések közt (fedezés-hiba a védőnél).
          if (shots.any((s) => s.free == true))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                  "szabad lövés (pontozott gyűrű): "
                  "${shots.where((s) => s.free == true).length} — a lövőnél "
                  "nem volt védő 2 m-en belül",
                  style: AppText.label.copyWith(fontSize: 11)),
            ),
          if (shots.any((s) => s.xg != null))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                  "várható gól (xG): "
                  "${shots.fold(0.0, (a, s) => a + (s.xg ?? 0)).toStringAsFixed(1)}"
                  " · a jelölő mérete = a helyzet értéke",
                  style: AppText.label.copyWith(fontSize: 11)),
            ),
        ],
      ]),
    );
  }

  /// Melyik oldali sávból jött a lövés — a MEGTÁMADOTT kapu felől nézve
  /// (a bal szél mindkét kapunál ugyanazt a támadó-oldalt jelenti).
  static int _lateralZone(ShotMarker s) {
    final attackingLeftGoal = s.x < courtLength / 2;
    final third = s.y < courtWidth / 3
        ? 0
        : s.y < 2 * courtWidth / 3
            ? 1
            : 2;
    return attackingLeftGoal ? 2 - third : third;
  }

  /// Milyen távolságról jött a lövés (a közelebbi kapu középpontjától).
  static int _distanceZone(ShotMarker s) {
    final gx = s.x < courtLength / 2 ? 0.0 : courtLength;
    final d = math.sqrt(math.pow(s.x - gx, 2) +
        math.pow(s.y - courtWidth / 2, 2));
    return d < 7.5 ? 0 : d < 11.0 ? 1 : 2;
  }

  /// "gól/lövés" bontás zónánként: [(címke, gól, lövés), ...]
  static List<(String, int, int)> _zoneBreakdown(List<ShotMarker> shots,
      int Function(ShotMarker) zoneOf, List<String> labels) {
    final g = List<int>.filled(labels.length, 0);
    final n = List<int>.filled(labels.length, 0);
    for (final s in shots) {
      final z = zoneOf(s).clamp(0, labels.length - 1);
      n[z]++;
      if (s.goal) g[z]++;
    }
    return [for (var i = 0; i < labels.length; i++) (labels[i], g[i], n[i])];
  }

  Widget _zoneLine(String title, List<(String, int, int)> zones) => Padding(
        padding: const EdgeInsets.only(top: 2),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          SizedBox(width: 38, child: Text(title,
              style: AppText.label.copyWith(
                  fontSize: 10, color: AppColors.textFaint))),
          for (final (label, g, n) in zones)
            Padding(
              padding: const EdgeInsets.only(right: 10),
              child: Text(n == 0 ? "$label –" : "$label $g/$n",
                  style: AppText.label.copyWith(
                      fontSize: 11,
                      color: n == 0
                          ? AppColors.textFaint
                          : AppColors.textPrimary)),
            ),
        ]),
      );

  /// A passzháló összegző kártyája: összes passz + a legerősebb kapcsolat.
  Widget _passNetworkChip(Match match) {
    final net = _passNetwork;
    String text;
    if (net == null || net.totalPasses == 0) {
      text = "nincs felismert passz ehhez a csapathoz";
    } else {
      text = "${net.totalPasses} passz";
      if (net.edges.isNotEmpty) {
        final top = net.edges.first;
        String name(int id) {
          for (final n in net.nodes) {
            if (n.trackId == id) {
              return n.jerseyNumber != null ? "#${n.jerseyNumber}" : "id $id";
            }
          }
          return "id $id";
        }
        text += " · legerősebb: ${name(top.a)} ↔ ${name(top.b)} (${top.count}×)";
      }
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.surface.withOpacity(0.92),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: Text(text, style: AppText.value.copyWith(fontSize: 12)),
    );
  }

  /// Kattintás-visszafejtés: a képpontból méter, majd a legközelebbi játékos
  /// (1,5 m-en belül). Ugyanarra kattintva a kijelölés megszűnik.
  void _handleCourtTap(Offset pos, Size size, Frame frame) {
    if (_viewMode == ViewMode.shots) {
      // Lövés-jelölőre koppintás → a lejátszó a jelenetre ugrik.
      final (scale, origin) = CourtPainter.transformFor(size);
      if (scale <= 0) return;
      ShotMarker? best;
      var bestD = 20.0; // px találati sugár
      for (final s in _filteredShots()) {
        final p = Offset(origin.dx + s.x * scale, origin.dy + s.y * scale);
        final d = (p - pos).distance;
        if (d < bestD) {
          bestD = d;
          best = s;
        }
      }
      if (best != null) _seekToFrame(_match!, best.t);
      return;
    }
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
    var label = st == null
        ? "Játékos #$id"
        : "Játékos #$id · $teamName · ${st.distanceM.toStringAsFixed(0)} m · "
            "max ${(st.topSpeedMs * 3.6).toStringAsFixed(1)} km/h · "
            "${st.sprintCount} sprint";
    // Lövő-adatok (ha lőtt): gól/lövés + várható gól — a diff előjele
    // mutatja, hogy a helyzetei felett (+) vagy alatt (−) teljesít.
    final sh = _xgShooters[id];
    if (sh != null) {
      final diff = (sh["diff"] as num?)?.toDouble() ?? 0.0;
      label += " · ${sh["goals"]}/${sh["shots"]} lövés · "
          "xG ${((sh["xg"] as num?) ?? 0).toStringAsFixed(1)}"
          "${diff.abs() >= 0.5 ? " (${diff > 0 ? "+" : ""}${diff.toStringAsFixed(1)})" : ""}";
    }
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
        // Mezszám megadása/javítása — a szám mindenhol (statisztika,
        // passzháló, jelentés, CSV) megjelenik, és mentésre kerül.
        InkWell(
          onTap: _sourceLabel == "demó" ? null : () => _editJersey(match, id),
          child: Icon(Icons.badge_outlined, size: 15,
              color: _sourceLabel == "demó"
                  ? AppColors.textFaint
                  : AppColors.accent),
        ),
        const SizedBox(width: 6),
        InkWell(
          onTap: () => setState(() => _selectedTrack = null),
          child: const Icon(Icons.close, size: 14, color: AppColors.textFaint),
        ),
      ]),
    );
  }

  /// Mezszám-szerkesztő párbeszéd a kijelölt játékoshoz. Mentés után a
  /// helyi meccs-adatot is frissítjük, így minden nézet azonnal a számot
  /// mutatja (újratöltés nélkül).
  Future<void> _editJersey(Match match, int trackId) async {
    int? current;
    for (final f in match.frames) {
      for (final p in f.players) {
        if (p.trackId == trackId && p.jerseyNumber != null) {
          current = p.jerseyNumber;
          break;
        }
      }
      if (current != null) break;
    }
    final ctrl = TextEditingController(text: current?.toString() ?? "");
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text("Mezszám — játékos #$trackId",
            style: AppText.value.copyWith(fontSize: 16)),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          keyboardType: TextInputType.number,
          style: AppText.value,
          decoration: InputDecoration(
            hintText: "pl. 23 (üresen hagyva törli)",
            hintStyle: AppText.label,
          ),
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text("Mégse"),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, ctrl.text),
            child: const Text("Mentés"),
          ),
        ],
      ),
    );
    if (result == null) return; // Mégse
    final trimmed = result.trim();
    final jersey = trimmed.isEmpty ? null : int.tryParse(trimmed);
    if (trimmed.isNotEmpty && (jersey == null || jersey < 0 || jersey > 99)) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("A mezszám 0 és 99 közötti szám lehet.")));
      return;
    }
    try {
      await _api.setJersey(widget.matchId, trackId, jersey);
      // Helyi frissítés: a szám ráírása minden kockára + a származtatott
      // nézetek (statisztika, passzháló) újraszámítása.
      for (final f in match.frames) {
        for (final p in f.players) {
          if (p.trackId == trackId) p.jerseyNumber = jersey;
        }
      }
      if (!mounted) return;
      setState(() {
        _stats = computePlayerStats(match);
        _passNetwork = computePassNetwork(match, _events, _passTeam);
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Mezszám-mentés hiba: $e")));
    }
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

  /// A sztori-sávon koppintott helyre ugrás (a videó-lejátszóval együtt).
  void _seekTimelineTo(Match match, int frame) {
    setState(() {
      _timer?.cancel();
      _playing = false;
      _frameIndex = frame.clamp(0, match.frames.length - 1);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoKey.currentState?.seekTo(match.meta.videoSecondsOfFrame(_frameIndex));
    });
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
        // Előző/következő esemény — a szűrt listán belül ugrál (pl. csak gólok).
        IconButton(
          iconSize: 24,
          color: AppColors.textSecondary,
          tooltip: "Előző esemény",
          onPressed: _navPoints().isEmpty ? null : () => _jumpToEvent(match, -1),
          icon: const Icon(Icons.skip_previous),
        ),
        IconButton(
          iconSize: 24,
          color: AppColors.textSecondary,
          tooltip: "Következő esemény",
          onPressed: _navPoints().isEmpty ? null : () => _jumpToEvent(match, 1),
          icon: const Icon(Icons.skip_next),
        ),
        Expanded(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            // Meccs-sztori sáv: gólok, sorozatok, emberelőnyök, 7 a 6 és
            // hétméteresek egy idővonalon — koppintásra odaugrik a lejátszó.
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: StoryTimeline(
                totalFrames: match.frames.length,
                fps: fps,
                events: _events,
                runs: _momentum,
                powerplays: ((_rules["powerplay"] as List?) ?? const [])
                    .cast<Map<String, dynamic>>(),
                sevens: ((_rules["seven_meters"] as List?) ?? const [])
                    .cast<Map<String, dynamic>>(),
                emptyNets: _emptyNet,
                subs: _subs,
                stoppages: _stoppages,
                currentFrame: _frameIndex,
                onSeek: (f) => _seekTimelineTo(match, f),
              ),
            ),
            Slider(
              value: _frameIndex.toDouble(),
              min: 0,
              max: (match.frames.length - 1).toDouble(),
              onChanged: (v) => setState(() => _frameIndex = v.round()),
            ),
            // Esemény-jelölők az idővonal alatt: arany = gól, türkiz = lövés,
            // piros = labdaeladás — ránézésre látszik, hol történt valami.
            if (_events.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: SizedBox(
                  height: 6,
                  child: CustomPaint(
                    size: const Size(double.infinity, 6),
                    painter: _EventTickPainter(
                        events: _events, frames: match.frames.length),
                  ),
                ),
              ),
          ]),
        ),
        const SizedBox(width: AppSpacing.sm),
        Text("${(_frameIndex / fps).toStringAsFixed(1)} s", style: AppText.value),
        Text("  /  ${(match.frames.length / fps).toStringAsFixed(0)} s", style: AppText.label),
        const SizedBox(width: AppSpacing.sm),
        // Lejátszási sebesség — billentyűzetről is: szóköz/nyilak/E/Q
        // (a gomb tooltipje sorolja a gyorsbillentyűket).
        PopupMenuButton<double>(
          tooltip: "Sebesség: ${_speedLabel(_speed)}\n"
              "Gyorsbillentyűk: szóköz = lejátszás/szünet · ←/→ = 1 kocka · "
              "Shift+←/→ = 5 mp · Q/E = előző/következő esemény",
          color: AppColors.surface,
          onSelected: (v) {
            setState(() => _speed = v);
            final m = _match;
            if (m != null) _restartTimer(m);
          },
          itemBuilder: (_) => [
            for (final v in const [0.5, 1.0, 2.0, 4.0])
              PopupMenuItem(
                value: v,
                child: Text(_speedLabel(v),
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
            child: Text(_speedLabel(_speed),
                style: AppText.value.copyWith(
                    fontSize: 12, color: AppColors.accent)),
          ),
        ),
      ],
    );
  }

  static String _speedLabel(double v) =>
      v == v.roundToDouble() ? "${v.toInt()}×" : "$v×";

  /// A lejátszó ugrása a legközelebbi (szűrt) eseményre a megadott irányban.
  /// Az aktív szűrő ugrópontjai (képkocka-idők) — a Q/E és a fel/le
  /// billentyűk ezeken lépkednek. Esemény-szűrőnél az események, támadás-
  /// szűrőnél a szakasz-kezdetek, szabály-szűrőnél a szabály-sorok.
  List<int> _navPoints() {
    List<int> pts;
    if (_eventFilter.startsWith("rule:")) {
      pts = [for (final r in _ruleRows()) (r["frame"] as num?)?.toInt() ?? 0];
    } else if (_eventFilter.startsWith("atk:")) {
      pts = [
        for (final a in _attacks)
          if (a["type"] == _eventFilter.substring(4))
            (a["start_frame"] as num?)?.toInt() ?? 0
      ];
    } else {
      pts = [for (final e in _filteredEvents()) (e["t"] as num?)?.toInt() ?? 0];
    }
    pts.sort();
    return pts;
  }

  void _jumpToEvent(Match match, int dir) {
    final points = _navPoints();
    if (points.isEmpty) return;
    int target;
    if (dir > 0) {
      target = points.firstWhere((t) => t > _frameIndex,
          orElse: () => points.first); // a végén körbeér az elejére
    } else {
      target = points.lastWhere((t) => t < _frameIndex,
          orElse: () => points.last); // az elején körbeér a végére
    }
    _seekToFrame(match, target);
  }

  /// Ugrás egy adott képkockára: megállítjuk a lejátszást, és ha van eredeti
  /// videó, azt is a jelenetre állítjuk (közös logika esemény/jegyzet/grafikon
  /// kattintáshoz).
  void _seekToFrame(Match match, int frame) {
    final t = frame.clamp(0, match.frames.length - 1);
    setState(() {
      _timer?.cancel();
      _playing = false;
      _frameIndex = t;
      if (match.meta.videoPath != null && VideoPanel.supported) {
        _showVideo = true;
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoKey.currentState?.seekTo(match.meta.videoSecondsOfFrame(t));
    });
  }

  Widget _rightPanel(Match match) {
    return Container(
      decoration: AppTheme.card(),
      clipBehavior: Clip.antiAlias,
      child: DefaultTabController(
        length: 5,
        child: Column(
          children: [
            const TabBar(
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              labelColor: AppColors.textPrimary,
              unselectedLabelColor: AppColors.textFaint,
              indicatorColor: AppColors.accent,
              labelStyle: TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
              tabs: [
                Tab(text: "Statisztika"),
                Tab(text: "Összegzés"),
                Tab(text: "Döntések"),
                Tab(text: "Események"),
                Tab(text: "Jegyzetek"),
              ],
            ),
            Expanded(
              child: TabBarView(
                children: [
                  StatsPanel(stats: _stats, homeName: match.meta.homeTeam, awayName: match.meta.awayTeam),
                  _summary == null
                      ? const SizedBox()
                      : SummaryPanel(
                          summary: _summary!,
                          homeName: match.meta.homeTeam,
                          awayName: match.meta.awayTeam,
                          goals: _events
                              .where((e) => e["type"] == "goal")
                              .toList(),
                          totalFrames: match.frames.length,
                          fps: match.meta.fps > 0 ? match.meta.fps : 25.0,
                          onSeekFrame: (t) => _seekToFrame(match, t),
                          intensity: _intensity,
                          formations: _formations,
                          coach: _coach,
                          runs: _momentum,
                        ),
                  DecisionsPanel(key: ValueKey(match.meta.matchId), match: match),
                  _eventsPanel(match),
                  _notesPanel(match),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Esemény-jelölők az idővonal alatt: minden eseményhez egy kis függőleges
/// vonás a meccsen belüli helyén (arany = gól, türkiz = lövés, piros =
/// labdaeladás; a passzokat nem rajzoljuk — túl sűrű lenne).
class _EventTickPainter extends CustomPainter {
  final List<Map<String, dynamic>> events;
  final int frames;
  _EventTickPainter({required this.events, required this.frames});

  @override
  void paint(Canvas canvas, Size size) {
    if (frames <= 1) return;
    for (final e in events) {
      final type = (e["type"] as String?) ?? "";
      final color = switch (type) {
        "goal" => AppColors.gold,
        "shot" => AppColors.accent,
        "turnover" => AppColors.away,
        _ => null,
      };
      if (color == null) continue; // passzokat nem jelöljük
      final t = (e["t"] as num?)?.toInt() ?? 0;
      final x = size.width * t / (frames - 1);
      final h = type == "goal" ? size.height : size.height * 0.66;
      canvas.drawLine(
          Offset(x, size.height - h), Offset(x, size.height),
          Paint()..color = color..strokeWidth = type == "goal" ? 2.5 : 1.5);
    }
  }

  @override
  bool shouldRepaint(covariant _EventTickPainter old) =>
      old.events != events || old.frames != frames;
}
