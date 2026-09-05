/// Meccs-elemző — felülnézeti taktikai nézet (a shell összecsukott railjével).
///
/// Bal oldalon eszköztár + pálya kártyán + élő taktikai felirat + lejátszó, jobbra
/// tabos elemző panel. Adatforrás: lokális backend, ha elérhető; különben demó.
library;

import "dart:async";
import "dart:convert";
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
import "anim.dart";
import "court3d_screen.dart";
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
import "zoomable.dart";
import "video_panel.dart";
import "error_text.dart";
import "waiting.dart";
import "empty_state.dart";

enum ViewMode { players, heatmap, shots, passes }

class MatchScreen extends StatefulWidget {
  final String matchId;

  /// Melyik képkockánál nyíljon meg a lejátszó. A jegyzet-listából
  /// érkezve a MEGJELÖLT pillanatra kell ugrani — különben az edző a
  /// saját jegyzetét keresgélheti végig a meccsen.
  final int? initialFrame;

  const MatchScreen({super.key, this.matchId = "sim-0", this.initialFrame});

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
  // KÉZI esemény-javítások: amit az edző a felismerésen kijavít. A
  // felismerés téved (gólt lövésnek lát, lövést nem vesz észre), az edző
  // pedig egy rossz eredményű jelentésnek EGYETLEN számát sem hiszi el.
  List<Map<String, dynamic>> _overrides = [];
  bool _correcting = false;
  // A feldolgozás minőség-önellenőrzése (score + figyelmeztetések) — a
  // felhasználó lássa, mennyire megbízható az elemzés. Demó módban null.
  Map<String, dynamic>? _quality;
  Map<String, dynamic>? _keyPlayers;
  List<dynamic> _keyMoments = const [];
  Map<String, dynamic>? _setplayEff;
  Map<String, dynamic>? _marking;
  Map<String, dynamic>? _blocks;
  Map<String, dynamic>? _ballWinners;
  // Automatikus edzői összefoglaló (GET /matches/{id}/coach-summary).
  Map<String, dynamic>? _coach;
  // Címkézett támadás-szakaszok (GET /matches/{id}/attacks).
  List<Map<String, dynamic>> _attacks = [];
  // Támadás-hatékonyság csapatonként/típusonként (a /attacks "efficiency").
  Map<String, dynamic> _attackEff = {};
  // Gól-sorozatok (GET /matches/{id}/momentum) — az eredmény-grafikonon.
  List<Map<String, dynamic>> _momentum = [];
  // Lövőnkénti helyzetminőség (player_id → {shots, goals, xg, diff}).
  Map<int, Map<String, dynamic>> _xgShooters = {};
  // Szabály-réteg (GET /matches/{id}/rules): 7m, emberhátrány, passzív.
  Map<String, dynamic> _rules = {};
  List<Map<String, dynamic>> _emptyNet = [];
  List<Map<String, dynamic>> _subs = [];
  List<Map<String, dynamic>> _stoppages = [];
  Map<String, dynamic>? _training;
  Map<String, dynamic> _progression = {};
  List<Map<String, dynamic>> _goalTimeline = [];
  Map<String, dynamic> _shotSpeeds = {};
  Map<int, double> _playerFatigue = {};
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
  // Egyszer használatos: a hívó által kért kezdő-képkocka, amint a
  // meccs betöltött (előtte nincs mihez képest határt szabni).
  bool _initialFrameApplied = false;
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
  // Idő-ablak a lövés- és hőtérképhez: all | h1 | h2 (a felezőpont a
  // feldolgozott szakasz időbeli közepe — külön félidő-jel híján).
  String _period = "all";
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
    Map<String, dynamic>? keyPlayers;
    List<dynamic> keyMoments = const [];
    Map<String, dynamic>? setplayEff;
    List<Map<String, dynamic>> notes = [];
    List<Map<String, dynamic>> overrides = [];
    Map<String, dynamic>? coach;
    List<Map<String, dynamic>> attacks = [];
    Map<String, dynamic> attackEff = {};
    List<Map<String, dynamic>> momentum = [];
    Map<String, dynamic> rules = {};
    List<Map<String, dynamic>> emptyNet = [];
    List<Map<String, dynamic>> subs = [];
    List<Map<String, dynamic>> stoppages = [];
    Map<String, dynamic>? training;
    Map<String, dynamic> progression = {};
    Map<String, dynamic> shotSpeeds = {};
    Map<int, double> playerFatigue = {};
    List<Map<String, dynamic>> goalTimeline = [];
    Map<int, double> xgByT = {};
    Map<int, Map<String, dynamic>> xgShooters = {};
    Map<int, bool> freeByT = {};
    Map<String, dynamic>? marking;
    Map<String, dynamic>? blocks;
    Map<String, dynamic>? ballWinners;
    if (await _api.isHealthy()) {
      try {
        match = await _api.fetchMatch(widget.matchId);
        label = "motor · ${match.meta.matchId}";
        try {
          events = await _api.fetchEvents(widget.matchId);
        } catch (_) {
          events = []; // esemény nélkül is működik a nézet
        }
        try {
          overrides = await _api.fetchEventOverrides(widget.matchId);
        } catch (_) {
          overrides = []; // javítás nélkül is működik a nézet
        }
        try {
          shotSpeeds = await _api.fetchShotSpeeds(widget.matchId);
        } catch (_) {
          shotSpeeds = {}; // sebesség nélkül is teljes a nézet
        }
        try {
          playerFatigue = await _api.fetchPlayerFatigue(widget.matchId);
        } catch (_) {
          playerFatigue = {}; // fáradás-adat nélkül is teljes a nézet
        }
        try {
          coach = await _api.fetchCoachSummary(widget.matchId);
        } catch (_) {
          coach = null; // az összefoglaló nélkül is teljes a nézet
        }
        try {
          final r = await _api.fetchAttacks(widget.matchId);
          attacks = (r["attacks"] as List).cast<Map<String, dynamic>>();
          attackEff = (r["efficiency"] as Map?)?.cast<String, dynamic>() ?? {};
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
          training = await _api.fetchTraining(widget.matchId);
        } catch (_) {
          training = null; // edzés-fókusz nélkül is teljes a nézet
        }
        try {
          progression = await _api.fetchProgression(widget.matchId);
        } catch (_) {
          progression = {}; // állás-menet nélkül is teljes a nézet
        }
        try {
          goalTimeline = await _api.fetchScoringTimeline(widget.matchId);
        } catch (_) {
          goalTimeline = []; // gól-idővonal nélkül is teljes a nézet
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
          marking = (d["marking"] as Map?)?.cast<String, dynamic>();
          blocks = (d["blocks"] as Map?)?.cast<String, dynamic>();
          ballWinners =
              (d["ball_winners"] as Map?)?.cast<String, dynamic>();
        } catch (_) {
          freeByT = {}; // védekezés-réteg nélkül is teljes a nézet
          marking = null;
          blocks = null;
          ballWinners = null;
        }
        try {
          quality = await _api.fetchQuality(widget.matchId);
        } catch (_) {
          quality = null; // minőség-jelentés nélkül is teljes a nézet
        }
        try {
          keyPlayers = (await _api.fetchKeyPlayers(widget.matchId))["key_players"]
              as Map<String, dynamic>?;
        } catch (_) {
          keyPlayers = null; // kulcsemberek nélkül is teljes a nézet
        }
        try {
          keyMoments = await _api.fetchKeyMoments(widget.matchId);
        } catch (_) {
          keyMoments = const []; // kulcs-pillanatok nélkül is teljes
        }
        try {
          setplayEff = (await _api.fetchSetplays(widget.matchId))["efficiency"]
              as Map<String, dynamic>?;
        } catch (_) {
          setplayEff = null; // figura-kép nélkül is teljes a nézet
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
      // A hívó által kért kezdő-képkocka (jegyzet-lista, kulcs-pillanat)
      // — csak most, a hossz ismeretében tudjuk határok közé szorítani.
      if (!_initialFrameApplied && widget.initialFrame != null) {
        _initialFrameApplied = true;
        _frameIndex = _indexOfT(match, widget.initialFrame!);
      }
      _stats = computePlayerStats(match);
      _summary = computeMatchSummary(match);
      _intensity = computeIntensityTimeline(match);
      _formations = computeFormationTimeline(match);
      _events = events;
      _overrides = overrides;
      _shots = _computeShotMarkers(match, events, xgByT, freeByT);
      _xgShooters = xgShooters;
      _passNetwork = computePassNetwork(match, events, _passTeam);
      _quality = quality;
      _keyPlayers = keyPlayers;
      _keyMoments = keyMoments;
      _setplayEff = setplayEff;
      _marking = marking;
      _blocks = blocks;
      _ballWinners = ballWinners;
      _notes = notes;
      _coach = coach;
      _attacks = attacks;
      _attackEff = attackEff;
      _momentum = momentum;
      _rules = rules;
      _emptyNet = emptyNet;
      _subs = subs;
      _stoppages = stoppages;
      _training = training;
      _progression = progression;
      _shotSpeeds = shotSpeeds;
      _playerFatigue = playerFatigue;
      _goalTimeline = goalTimeline;
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
      final (fromT, toT) = _periodRange();
      _heatmap = computeTeamHeatmap(match, team, fromT: fromT, toT: toT);
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
          ? const WaitingView("Meccs betöltése…",
              hint: "A képkockák és az események beolvasása. Hosszú "
                  "felvételnél ez eltarthat egy ideig.",
              icon: Icons.sports_handball)
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
        // ? (Shift+/) és F1: gyorsbillentyű-súgó.
        const SingleActivator(LogicalKeyboardKey.slash, shift: true):
            _showShortcutHelp,
        const SingleActivator(LogicalKeyboardKey.f1): _showShortcutHelp,
      },
      child: Focus(autofocus: true, child: child),
    );
  }

  /// Gyorsbillentyű-súgó. A listát a shell tartja (kShortcutGroups) —
  /// két külön lista előbb-utóbb széttartana, és a meccs-elemzős
  /// változat az app-szintű navigációs billentyűket nem is említette.
  void _showShortcutHelp() => showShortcutHelp(context);

  /// Események-panel: a felismert passzok/lövések/gólok/labdaeladások listája.
  /// Egy elemre kattintva a lejátszó az esemény képkockájára ugrik.
  Widget _eventsPanel(Match match) {
    if (_events.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Text(
            _sourceLabel == "demó"
                ? "Az események a motor feldolgozásából jönnek — demó módban nem elérhetők."
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
      _scoreBar(match),
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
              if (_stoppages.any((s) => s["kind"] == "időkérés"))
                _filterChip("rule:timeout", "Időkérés"),
            ]),
          ),
          // Kézi javítás: a felismerés téved, és egy rossz eredményű
          // jelentésnek az edző EGYETLEN számát sem hiszi el. Itt lehet
          // hiányzó gólt felvenni és az összes javítást visszavonni; a
          // meglévő események javítása a soruk menüjében van.
          PopupMenuButton<String>(
            enabled: !_correcting && _sourceLabel != "demó",
            tooltip: _overrides.isEmpty
                ? "Javítások"
                : "Javítások (${_overrides.length})",
            icon: Icon(Icons.fact_check_outlined,
                color: _overrides.isEmpty
                    ? AppColors.textFaint
                    : AppColors.gold),
            color: AppColors.surface,
            onSelected: (v) {
              if (v == "clear") {
                _clearCorrections();
              } else {
                // A jelenlegi képkockára veszünk fel gólt — az edző
                // épp azt a pillanatot nézi —, és ha ki van jelölve
                // játékos, ő lesz a lövő.
                _correct("add", _tOf(match), "goal",
                    team: v, playerId: _selectedTrack);
              }
            },
            itemBuilder: (_) => [
              PopupMenuItem(
                  value: "home",
                  child: ListTile(
                      leading: const Icon(Icons.add, size: 17),
                      title: Text("Hiányzó gól: ${match.meta.homeTeam}"),
                      subtitle: Text(_selectedTrack == null
                          ? "a jelenlegi pillanatra"
                          : "a jelenlegi pillanatra · lövő: "
                              "${_playerShort(match, _selectedTrack!)}"),
                      dense: true)),
              PopupMenuItem(
                  value: "away",
                  child: ListTile(
                      leading: const Icon(Icons.add, size: 17),
                      title: Text("Hiányzó gól: ${match.meta.awayTeam}"),
                      subtitle: Text(_selectedTrack == null
                          ? "a jelenlegi pillanatra"
                          : "a jelenlegi pillanatra · lövő: "
                              "${_playerShort(match, _selectedTrack!)}"),
                      dense: true)),
              if (_overrides.isNotEmpty)
                PopupMenuItem(
                    value: "clear",
                    child: ListTile(
                        leading: const Icon(Icons.undo, size: 17),
                        title: Text("Minden javítás visszavonása "
                            "(${_overrides.length})"),
                        subtitle: const Text("a felismerés eredeti képe"),
                        dense: true)),
            ],
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
          // Tematikus klip-csomagok egy menüben — a gomb-sor nem nő
          // tovább, és minden csomagnak olvasható neve van.
          PopupMenuButton<String>(
            enabled: !_exportingClips,
            tooltip: "Tematikus klip-csomagok",
            icon: const Icon(Icons.video_library_outlined,
                color: AppColors.gold),
            color: AppColors.surface,
            onSelected: (t) => _exportClips(match,
                typesOverride: t == "_all"
                    ? const [
                        "goal", "key_moment", "turning_point",
                        "missed_chance", "big_save", "top_shooter",
                        "free_shot", "best_figure", "pivot_goal",
                        "breakthrough", "steal", "block", "empty_net",
                      ]
                    : [t]),
            itemBuilder: (_) => const [
              PopupMenuItem(
                  value: "_all",
                  child: ListTile(
                      leading: Icon(Icons.video_library, size: 18),
                      title: Text("Teljes videó-dosszié (minden csomag)"),
                      dense: true)),
              PopupMenuItem(
                  value: "key_moment",
                  child: ListTile(
                      leading: Icon(Icons.auto_awesome, size: 18),
                      title: Text("Kulcs-pillanatok (a meccs gerince)"),
                      dense: true)),
              PopupMenuItem(
                  value: "turning_point",
                  child: ListTile(
                      leading: Icon(Icons.trending_up, size: 18),
                      title: Text("Fordulópont"),
                      dense: true)),
              PopupMenuItem(
                  value: "missed_chance",
                  child: ListTile(
                      leading: Icon(Icons.priority_high, size: 18),
                      title: Text("Kihagyott ziccerek"),
                      dense: true)),
              PopupMenuItem(
                  value: "big_save",
                  child: ListTile(
                      leading: Icon(Icons.back_hand, size: 18),
                      title: Text("Nagy védések"),
                      dense: true)),
              PopupMenuItem(
                  value: "top_shooter",
                  child: ListTile(
                      leading: Icon(Icons.person_search, size: 18),
                      title: Text("Fő lövő lövései"),
                      dense: true)),
              PopupMenuItem(
                  value: "free_shot",
                  child: ListTile(
                      leading: Icon(Icons.person_off_outlined, size: 18),
                      title: Text("Szabad lövők (fedezés-hibák)"),
                      dense: true)),
              PopupMenuItem(
                  value: "best_figure",
                  child: ListTile(
                      leading: Icon(Icons.pattern, size: 18),
                      title: Text("Legjobb figura"),
                      dense: true)),
              PopupMenuItem(
                  value: "pivot_goal",
                  child: ListTile(
                      leading: Icon(Icons.adjust, size: 18),
                      title: Text("Beállós gólok (beadás-játék)"),
                      dense: true)),
              PopupMenuItem(
                  value: "breakthrough",
                  child: ListTile(
                      leading: Icon(Icons.login, size: 18),
                      title: Text("Betörések (sávval a fájlnévben)"),
                      dense: true)),
              PopupMenuItem(
                  value: "steal",
                  child: ListTile(
                      leading: Icon(Icons.back_hand, size: 18),
                      title: Text("Labdaszerzések"),
                      dense: true)),
              PopupMenuItem(
                  value: "block",
                  child: ListTile(
                      leading: Icon(Icons.front_hand, size: 18),
                      title: Text("Blokkok (a fal munkája)"),
                      dense: true)),
              PopupMenuItem(
                  value: "empty_net",
                  child: ListTile(
                      leading: Icon(Icons.groups, size: 18),
                      title: Text("7 a 6 szakaszok"),
                      dense: true)),
            ],
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
                : Column(children: [
                    _attackEffBanner(_eventFilter.substring(4), match),
                    Expanded(
                      child: ListView.separated(
                        padding: const EdgeInsets.all(AppSpacing.md),
                        itemCount: shownAttacks.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 6),
                        itemBuilder: (_, i) =>
                            _attackRow(shownAttacks[i], fps, match),
                      ),
                    ),
                  ]))
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

  /// EREDMÉNY-SÁV: a felismert állás, kimondva, hogy javítható.
  ///
  /// Az edző az eredményből dönti el, hogy hisz-e a jelentésnek. Ha a
  /// felismerés 21–19-et mond a valós 24–22 helyett, a többi szám sem
  /// ér semmit a szemében — akkor sem, ha egyébként pontos. Ezért az
  /// állás LÁTSZIK, és mellette ott a mondat, hogy javítható: a
  /// javítás-eszközök máshogy rejtve maradnának.
  Widget _scoreBar(Match match) {
    var hazai = 0;
    var vendeg = 0;
    for (final e in _events) {
      if (e["type"] != "goal") continue;
      if (e["team"] == "home") {
        hazai++;
      } else {
        vendeg++;
      }
    }
    final demo = _sourceLabel == "demó";
    return Container(
      margin: const EdgeInsets.fromLTRB(
          AppSpacing.md, AppSpacing.md, AppSpacing.md, 0),
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md, vertical: AppSpacing.sm),
      decoration: AppTheme.card(
          borderColor: _overrides.isEmpty ? null : AppColors.gold),
      child: Row(children: [
        Expanded(
          child: Text(match.meta.homeTeam,
              textAlign: TextAlign.right,
              overflow: TextOverflow.ellipsis,
              style: AppText.value.copyWith(fontSize: 13)),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text("$hazai – $vendeg", style: AppText.statBig),
            // A VALÓDI (jegyzőkönyvi) eredmény a felismert alatt — ha
            // az edző megadta a könyvtár ceruza-párbeszédében. Nagy
            // eltérésnél arany: a minőség-jelentés mondja a teendőt.
            if (match.meta.realGoalsHome != null &&
                match.meta.realGoalsAway != null)
              Text(
                  "valódi: ${match.meta.realGoalsHome}–"
                  "${match.meta.realGoalsAway}",
                  style: AppText.label.copyWith(
                      fontSize: 10.5,
                      // = REAL_SCORE_DIFF_WARN (backend-küszöb): 4 gól
                      color: ((hazai - match.meta.realGoalsHome!).abs() +
                                  (vendeg - match.meta.realGoalsAway!)
                                      .abs()) >= 4
                          ? AppColors.gold
                          : AppColors.textFaint)),
          ]),
        ),
        Expanded(
          child: Text(match.meta.awayTeam,
              overflow: TextOverflow.ellipsis,
              style: AppText.value.copyWith(fontSize: 13)),
        ),
        const SizedBox(width: AppSpacing.md),
        Flexible(
          flex: 2,
          child: Text(
              demo
                  ? "demó adat"
                  : _overrides.isEmpty
                      ? "a felismerés szerint — ha nem stimmel, a "
                          "sorok ⋮ menüjében javítható"
                      : "${_overrides.length} kézi javítással",
              style: AppText.label.copyWith(
                  fontSize: 11.5,
                  color: _overrides.isEmpty
                      ? AppColors.textFaint
                      : AppColors.gold)),
        ),
      ]),
    );
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
      case "rule:timeout":
        return [
          for (final st in _stoppages)
            if (st["kind"] == "időkérés")
              {
                // Ha a backend ítéletet is adott (megtörte-e a sorozatot),
                // a címkében is látszik.
                "label": (st["verdict"] as String?) != null
                    ? "Időkérés — ${st["verdict"]}"
                    : "Időkérés",
                "team": st["likely_team"],
                "frame": st["start_frame"],
                "duration_s": st["duration_s"],
              },
        ];
    }
    return const [];
  }

  /// Egy szabály-szakasz sora — koppintásra a lejátszó odaugrik.
  Widget _ruleRow(Map<String, dynamic> r, double fps, Match match) {
    final frame = (r["frame"] as num?)?.toInt() ?? 0;
    final durS = (r["duration_s"] as num?)?.toDouble();
    // Az időkérésnél a "csapat" csak valószínűsítés — lehet ismeretlen is.
    final team = switch (r["team"] as String?) {
      "home" => match.meta.homeTeam,
      "away" => match.meta.awayTeam,
      _ => "",
    };
    final label = (r["label"] as String?) ?? "";
    final (icon, color) = switch (label) {
      // A hétméteres címke kimenetellel is jöhet ("Hétméteres — védés").
      _ when label.startsWith("Hétméteres") =>
        (Icons.sports_score, AppColors.gold),
      "Emberhátrány" => (Icons.person_remove, AppColors.away),
      _ when label.startsWith("Időkérés") =>
        (Icons.pause_circle_outline, AppColors.textSecondary),
      _ => (Icons.hourglass_bottom, AppColors.textSecondary),
    };
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: () => _seekToFrame(match, frame),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: _tOf(match) == frame
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
  /// A kiválasztott támadás-típus hatékonysága csapatonként — a lista
  /// fölött ("H: 4/5 lövés, 3 gól · 60%"). Üres, ha nincs hatékonyság-adat.
  Widget _attackEffBanner(String type, Match match) {
    final rows = <Widget>[];
    for (final side in ["home", "away"]) {
      final rec = (_attackEff[side] as Map?)?[type] as Map?;
      if (rec == null || ((rec["attacks"] as num?) ?? 0) < 1) continue;
      final name = side == "home" ? match.meta.homeTeam : match.meta.awayTeam;
      final color = side == "home" ? AppColors.home : AppColors.away;
      rows.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Text(
            "$name: ${rec["shots"]}/${rec["attacks"]} lövésig, "
            "${rec["goals"]} gól · ${(rec["goal_pct"] as num).toStringAsFixed(0)}% gól",
            style: AppText.label.copyWith(fontSize: 12, color: color)),
      ));
    }
    if (rows.isEmpty) return const SizedBox.shrink();
    return Container(
      margin: const EdgeInsets.fromLTRB(
          AppSpacing.md, AppSpacing.md, AppSpacing.md, 0),
      padding: const EdgeInsets.symmetric(
          horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.surfaceAlt,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
          crossAxisAlignment: CrossAxisAlignment.start, children: rows),
    );
  }

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
    final selected = _tOf(match) >= start &&
        _tOf(match) <= ((a["end_frame"] as num?)?.toInt() ?? start);
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
  Future<void> _exportClips(Match match, {List<String>? typesOverride}) async {
    // "Mind" (és támadás-) szűrőnél passz-klipeket nem vágunk (túl sok,
    // kevés érték) — a klip-export az eseménytípusokból dolgozik. A
    // szabály-szűrők a megfelelő klip-típusra képződnek le.
    const ruleClipTypes = {
      "rule:7m": "seven_meter",
      "rule:timeout": "timeout",
    };
    final types = typesOverride ??
        (_eventFilter == "all" || _eventFilter.startsWith("atk:")
            ? ["goal", "shot", "turnover"]
            : [ruleClipTypes[_eventFilter] ?? _eventFilter]);
    if (types.contains("pass") && types.length == 1) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text("Passzokból nem készül klip — válassz gólt, lövést "
              "vagy labdaeladást.")));
      return;
    }
    if (types.first.startsWith("rule:")) {
      // A hosszú szakaszokból (emberhátrány, passzív) nem vágunk klipet.
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text("Ebből a szűrőből nem készül klip — a hétméteres és "
              "az időkérés szűrőnél elérhető a vágás.")));
      return;
    }
    setState(() => _exportingClips = true);
    try {
      final jobId = await _api.startClipExport(widget.matchId, types);
      // A vágás haladásának követése (másodpercenként). A záró üzenet
      // a mentés-visszajelzőbe kerül (pl. "12 jelenet kimaradt").
      String doneMsg = "";
      while (true) {
        await Future.delayed(const Duration(seconds: 1));
        final job = await _api.fetchJob(jobId);
        final status = job["status"] as String?;
        if (status == "done") {
          doneMsg = (job["message"] as String?) ?? "";
          break;
        }
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
              "lejátszhatók/megoszthatók"
              "${doneMsg.contains("kimaradt") ? " · $doneMsg" : ""}")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Klip-export hiba: ${humanError(e)}")));
    } finally {
      if (mounted) setState(() => _exportingClips = false);
    }
  }

  /// Játékos-lap: egy játékos meccs-riportja HTML-ben, mentés a
  /// felhasználó által választott helyre.
  Future<void> _savePlayerReport(
      Match match, int trackId, String label) async {
    try {
      final bytes = await _api.fetchPlayerReport(widget.matchId, trackId);
      if (!mounted) return;
      final safe = label.replaceAll(
          RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Játékos-lap mentése (HTML)",
        fileName: "jatekos_lap_$safe.html",
        type: FileType.custom,
        allowedExtensions: const ["html"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Játékos-lap mentve: $path — böngészőből "
              "nyomtatható, kiosztható")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Játékos-lap hiba: ${humanError(e)}")));
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
          SnackBar(content: Text("Csomag-export hiba: ${humanError(e)}")));
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
    final selected = _tOf(match) == t;
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      // Ugrás az esemény képkockájára (a lejátszót is megállítjuk), és ha az
      // eredeti videó elérhető, a jelenet-lejátszó is a jelenetre ugrik.
      onTap: () => _seekToFrame(match, t),
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
          // Kézi eredet jelölése: az edző lássa, mit írt felül ő maga.
          if (((e["detail"] as Map?)?["manual"]) == true)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: Tooltip(
                message: "kézzel javított",
                child: Icon(Icons.edit_outlined,
                    size: 13, color: AppColors.gold),
              ),
            ),
          Text("${(t / fps).toStringAsFixed(1)} s", style: AppText.label.copyWith(fontSize: 11.5)),
          // Javítás + 3D: a felismerés téved, és az edző egy rossz
          // eredményű jelentésnek egyetlen számát sem hiszi el — a
          // javítás gól/lövés sorokon él. A "Megnézem 3D-ben" minden
          // soron: a jelenet térben, TV-kamerával játszódik le.
          PopupMenuButton<String>(
            tooltip: "Javítás / 3D",
            enabled: !_correcting && _sourceLabel != "demó",
            iconSize: 15,
            padding: EdgeInsets.zero,
            icon: const Icon(Icons.more_vert,
                color: AppColors.textFaint),
            color: AppColors.surface,
            onSelected: (v) {
              if (v == "goal" || v == "shot") {
                _correct("set_type", t, v);
              } else if (v == "remove") {
                _correct("remove", t, type);
              } else if (v == "3d") {
                Navigator.of(context).pushReplacement(MaterialPageRoute(
                    builder: (_) => Court3DScreen(
                        matchId: widget.matchId, startS: t / fps)));
              }
            },
            itemBuilder: (_) => [
              const PopupMenuItem(
                  value: "3d",
                  child: ListTile(
                      leading: Icon(Icons.view_in_ar, size: 17),
                      title: Text("Megnézem 3D-ben"),
                      dense: true)),
              if (type == "shot")
                const PopupMenuItem(
                    value: "goal",
                    child: ListTile(
                        leading: Icon(Icons.sports_score, size: 17),
                        title: Text("Ez GÓL volt"),
                        dense: true)),
              if (type == "goal")
                const PopupMenuItem(
                    value: "shot",
                    child: ListTile(
                        leading: Icon(Icons.sports_handball, size: 17),
                        title: Text("Ez csak lövés volt"),
                        dense: true)),
              if (type == "goal" || type == "shot")
                const PopupMenuItem(
                    value: "remove",
                    child: ListTile(
                        leading: Icon(Icons.delete_outline, size: 17),
                        title: Text("Nem volt ilyen esemény"),
                        dense: true)),
            ],
          ),
        ]),
      ),
    );
  }

  /// KÉZI javítás felvétele és mentése, majd a nézet újratöltése.
  ///
  /// Miért a teljes újratöltés: a javítás a lövés-felismerésbe épül be,
  /// tehát MINDEN rétegen átüt (eredmény, xG, lövő-listák, edzés-fókusz)
  /// — a fél nézet frissítése ellentmondó képet adna, ami rosszabb,
  /// mint a másodperces várakozás.
  Future<void> _correct(String op, int t, String type,
      {String? team, int? playerId}) async {
    if (_correcting) return;
    setState(() => _correcting = true);
    try {
      final uj = <Map<String, dynamic>>[
        ..._overrides,
        {
          "op": op,
          "t": t,
          "type": type,
          if (team != null) "team": team,
          // A LÖVŐ: ha ki van jelölve játékos a pályán, a kézzel
          // felvett gól hozzá tartozik — enélkül a gól ott lenne az
          // eredményben, de a góllövő-listákból kimaradna.
          if (playerId != null) "player_id": playerId,
        },
      ];
      await _api.saveEventOverrides(widget.matchId, uj);
      if (!mounted) return;
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text("Javítás mentve — az elemzés újraszámolt "
              "(eredmény, xG, listák).")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("A javítás nem sikerült: ${humanError(e)}")));
    } finally {
      if (mounted) setState(() => _correcting = false);
    }
  }

  /// Az ÖSSZES kézi javítás visszavonása (a felismerés eredeti képe).
  Future<void> _clearCorrections() async {
    if (_correcting) return;
    setState(() => _correcting = true);
    try {
      await _api.saveEventOverrides(widget.matchId, const []);
      if (!mounted) return;
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("A visszavonás nem sikerült: ${humanError(e)}")));
    } finally {
      if (mounted) setState(() => _correcting = false);
    }
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
                    : "Jegyzet ${(_tOf(match) / fps).toStringAsFixed(1)} s-hez…",
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
          // A megjelölt pillanatok jelenetei MP4-klipekben — a fájlnévben
          // a jegyzet szövegével.
          IconButton(
            onPressed: demo || _notes.isEmpty || _exportingClips
                ? null
                : () => _exportClips(match, typesOverride: ["note"]),
            icon: _exportingClips
                ? const SizedBox(width: 16, height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.movie_outlined, color: AppColors.gold),
            tooltip: "Jegyzet-klipek exportja (zip)",
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
                        ? "A jegyzeteket a motor tárolja — demó módban nem elérhetők."
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
      onTap: () => _seekToFrame(match, frame),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: _tOf(match) == frame ? AppColors.accentSoft : AppColors.surfaceAlt,
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

  /// Kulcs-pillanat átemelése az edzői jegyzetek közé (a pillanat
  /// címkéjével) — a jegyzet a lejátszóból és a csomagból is látszik.
  Future<void> _noteKeyMoment(Match match, int t, String label) async {
    try {
      await _api.addNote(widget.matchId, t, label);
      final notes = await _api.fetchNotes(widget.matchId);
      if (!mounted) return;
      setState(() => _notes = notes);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Jegyzetbe került: $label")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Nem sikerült a jegyzet: ${humanError(e)}")));
    }
  }

  Future<void> _addNote(Match match) async {
    final text = _noteCtrl.text.trim();
    if (text.isEmpty || _savingNote) return;
    setState(() => _savingNote = true);
    try {
      await _api.addNote(widget.matchId, _tOf(match), text);
      final notes = await _api.fetchNotes(widget.matchId);
      if (!mounted) return;
      setState(() {
        _notes = notes;
        _noteCtrl.clear();
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Nem sikerült menteni a jegyzetet: ${humanError(e)}")));
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
          SnackBar(content: Text("Nem sikerült törölni a jegyzetet: ${humanError(e)}")));
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
        // Mezszámok EGY menetben: enélkül minden szezon-szintű lap
        // (keret, toplisták, játékos-fejlődés) néma marad, a
        // pályára-kattintós szerkesztő pedig játékosonként külön
        // párbeszéd — tizennégy emberre az már nem munka, hanem
        // elrettentés.
        IconButton(
          onPressed: _sourceLabel == "demó"
              ? null
              : () => _bulkJerseys(match),
          icon: const Icon(Icons.badge_outlined,
              color: AppColors.textSecondary),
          tooltip: "Mezszámok kiosztása (egy listában)",
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
        // UTÓLAGOS vágás: a bennmaradt bemutatás/bemelegítés ál-eseményeket
        // gyárt — itt, a meccs-nézetben veszi észre a felhasználó.
        IconButton(
          onPressed: _sourceLabel == "demó" ? null : _trimDialog,
          icon: const Icon(Icons.content_cut, color: AppColors.textSecondary),
          tooltip: "Meccs eleje/vége levágása (bennmaradt bemutatás, "
              "bemelegítés)",
        ),
        // Egyoldalas edzői meccsjelentés mentése (HTML → böngészőből PDF).
        IconButton(
          onPressed: _sourceLabel == "demó" ? null : _exportReport,
          icon: const Icon(Icons.description_outlined, color: AppColors.textSecondary),
          tooltip: "Meccsjelentés mentése (nyomtatható)",
        ),
        // KALIBRÁCIÓ-ELLENŐRZÉS: a pályavonalak visszarajzolva a videó
        // három kockájára (eleje/közepe/vége) — a szem dönti el, tartja-e
        // a kalibráció a svenkelés alatt.
        IconButton(
          onPressed: _sourceLabel == "demó" ? null : _calibCheckDialog,
          icon: const Icon(Icons.grid_on, color: AppColors.textSecondary),
          tooltip: "Kalibráció ellenőrzése (vonalak a videón)",
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
        // Elemzés-könyvtár: befejezett és félbehagyott elemzések egy
        // helyen — megnyitás és törlés (a dashboardra lépés nélkül).
        IconButton(
            onPressed: _openLibrary,
            tooltip: "Elemzés-könyvtár (befejezett és félbehagyott)",
            icon: const Icon(Icons.folder_open,
                color: AppColors.textSecondary)),
        IconButton(
              onPressed: _load,
              tooltip: "Meccs újratöltése",
              icon: const Icon(Icons.refresh,
                  color: AppColors.textSecondary)),
      ],
    );
  }

  /// Elemzés-könyvtár párbeszéd: fülekkel (mind/befejezett/félbehagyott),
  /// megnyitással és törléssel. A félbehagyott elemzés is teljes értékű
  /// nézetet kap (az addig feldolgozott részből), és innen törölhető is.
  Future<void> _openLibrary() async {
    List<Map<String, dynamic>> items;
    try {
      items = await _api.listMatches();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("A könyvtár nem érhető el: ${humanError(e)}")));
      return;
    }
    if (!mounted) return;
    var filter = "all";
    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlg) {
          final shown = [
            for (final m in items)
              if (filter == "all" ||
                  (filter == "partial") == ((m["partial"] as bool?) ?? false))
                m,
          ];
          final doneN =
              items.where((m) => !((m["partial"] as bool?) ?? false)).length;
          final partN = items.length - doneN;
          return AlertDialog(
            backgroundColor: AppColors.surface,
            title: const Text("Elemzés-könyvtár"),
            content: SizedBox(
              width: 560,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SegmentedButton<String>(
                    showSelectedIcon: false,
                    style: const ButtonStyle(
                        visualDensity: VisualDensity.compact),
                    segments: [
                      ButtonSegment(
                          value: "all",
                          label: Text("Mind (${items.length})")),
                      ButtonSegment(
                          value: "done",
                          label: Text("Befejezett ($doneN)")),
                      ButtonSegment(
                          value: "partial",
                          label: Text("Félbehagyott ($partN)")),
                    ],
                    selected: {filter},
                    onSelectionChanged: (s) =>
                        setDlg(() => filter = s.first),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  if (shown.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      child: Text(
                          filter == "partial"
                              ? "Nincs félbehagyott elemzés."
                              : "Nincs ilyen elemzés a könyvtárban.",
                          style: AppText.label),
                    )
                  else
                    Flexible(
                      child: SingleChildScrollView(
                        child: Column(children: [
                          for (final m in shown)
                            _libraryRow(ctx, m, items, setDlg),
                        ]),
                      ),
                    ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text("Bezár"),
              ),
            ],
          );
        },
      ),
    );
  }

  /// Egy könyvtár-sor: megnyitás (koppintásra) + törlés (kuka ikon).
  Widget _libraryRow(BuildContext ctx, Map<String, dynamic> m,
      List<Map<String, dynamic>> items, StateSetter setDlg) {
    final id = m["match_id"] as String;
    final partial = (m["partial"] as bool?) ?? false;
    final durS = ((m["duration_s"] as num?) ?? 0).toDouble();
    final mins = (durS / 60).floor();
    final secs = (durS % 60).round();
    return ListTile(
      dense: true,
      contentPadding:
          const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      title: Row(children: [
        Flexible(
          child: Text("${m["home_team"] ?? "?"} – ${m["away_team"] ?? "?"}",
              overflow: TextOverflow.ellipsis,
              style: AppText.value.copyWith(fontSize: 14)),
        ),
        if (partial) ...[
          const SizedBox(width: AppSpacing.sm),
          Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: AppColors.away.withOpacity(0.15),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text("FÉLBEHAGYOTT",
                style: AppText.label
                    .copyWith(fontSize: 10, color: AppColors.away)),
          ),
        ],
      ]),
      subtitle: Text(
          "$id · ${m["num_frames"]} kocka · $mins:${secs.toString().padLeft(2, '0')}",
          style: AppText.label.copyWith(fontSize: 11)),
      trailing: IconButton(
        tooltip: "Törlés",
        icon: const Icon(Icons.delete_outline,
            color: AppColors.textSecondary, size: 20),
        onPressed: () async {
          final ok = await showDialog<bool>(
            context: ctx,
            builder: (c2) => AlertDialog(
              backgroundColor: AppColors.surface,
              title: const Text("Elemzés törlése"),
              content: Text(
                  "${m["home_team"] ?? "?"} – ${m["away_team"] ?? "?"} "
                  "($id) végleg törlődik a könyvtárból."),
              actions: [
                TextButton(
                    onPressed: () => Navigator.of(c2).pop(false),
                    child: const Text("Mégse")),
                TextButton(
                    onPressed: () => Navigator.of(c2).pop(true),
                    child: const Text("Törlés",
                        style: TextStyle(color: AppColors.away))),
              ],
            ),
          );
          if (ok != true) return;
          try {
            await _api.deleteMatch(id);
            setDlg(() => items.removeWhere((x) => x["match_id"] == id));
          } catch (e) {
            if (!ctx.mounted) return;
            ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(
                content: Text("Törlési hiba: ${humanError(e)}")));
          }
        },
      ),
      onTap: () {
        Navigator.of(ctx).pop();
        if (id == widget.matchId) return; // már ez van nyitva
        Navigator.of(context).pushReplacement(MaterialPageRoute(
            builder: (_) => MatchScreen(matchId: id)));
      },
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
          SnackBar(content: Text("Export-hiba: ${humanError(e)}")));
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
          SnackBar(content: Text("Jelentés-hiba: ${humanError(e)}")));
    }
  }

  /// Csapatok felcserélése — ha a színfelismerés fordítva osztotta ki, melyik
  /// szín a hazai. Megerősítés után a backend átbillenti minden játékos
  /// csapat-mezőjét, és a nézet újratölt (statisztika is frissül).
  /// "p:mp" vagy puszta másodperc → másodperc. Hibás alaknál null.
  static double? _parseIdo(String s) {
    final t = s.trim();
    if (t.isEmpty) return null;
    if (t.contains(":")) {
      final d = t.split(":");
      if (d.length != 2) return null;
      final p = int.tryParse(d[0]);
      final mp = double.tryParse(d[1].replaceAll(",", "."));
      if (p == null || mp == null) return null;
      return p * 60 + mp;
    }
    return double.tryParse(t.replaceAll(",", "."));
  }

  /// Másodperc → "p:mp" (pl. 549 → "9:09").
  static String _fmtIdoPmp(double s) {
    final t = s.round();
    return "${t ~/ 60}:${(t % 60).toString().padLeft(2, '0')}";
  }

  /// UTÓLAGOS vágás a meccs-nézetből: itt látja a felhasználó a
  /// bemutatás-kori ál-eseményeket — ne kelljen a könyvtárba
  /// visszamennie a ✂-ért. Ugyanaz a végpont, mint a könyvtár-sorban,
  /// és a kezdést itt is a meccs-ablak-felismerés javaslata előtölti.
  Future<void> _trimDialog() async {
    final fromCtrl = TextEditingController();
    final toCtrl = TextEditingController();
    // Javaslat a tárolt követésből — a párbeszéd azonnal megnyílik, a
    // javaslat megérkezéskor tölti elő a mezőket (ha még üresek).
    String? javaslat; // a mutatott sor; null = még számol
    var javaslatVan = false;
    void Function(void Function())? frissit;
    _api.fetchGameWindow(widget.matchId).then((r) {
      final start = (r["start_s"] as num?)?.toDouble();
      final end = (r["end_s"] as num?)?.toDouble();
      final head = (r["head_s"] as num?)?.toDouble() ?? 0;
      final tail = (r["tail_s"] as num?)?.toDouble() ?? 0;
      if (r["found"] == true && start != null &&
          head >= 45 /* = GW_MIN_TRIM_S */) {
        if (fromCtrl.text.trim().isEmpty) {
          fromCtrl.text = _fmtIdoPmp(start);
        }
        if (end != null && tail >= 45 && toCtrl.text.trim().isEmpty) {
          toCtrl.text = _fmtIdoPmp(end);
        }
        javaslatVan = true;
        javaslat = "A felismerés szerint a meccs kb. "
            "${_fmtIdoPmp(start)}-kor kezdődik — a javaslat elő van "
            "töltve, ellenőrizd és igazítsd, ha kell.";
      } else if (r["found"] == true) {
        javaslat = "A felismerés szerint az elején nincs mit levágni — "
            "csak akkor vágj, ha mást látsz.";
      } else {
        javaslat = "A felismerés nem talált egyértelmű meccs-kezdést — "
            "add meg kézzel.";
      }
      frissit?.call(() {});
    }).catchError((_) {
      javaslat = ""; // hiba: javaslat nélkül megy tovább a kézi vágás
      frissit?.call(() {});
    });
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setDlg) {
        frissit = setDlg;
        return AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Meccs eleje/vége levágása"),
        content: SizedBox(
          width: 440,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(
                "Add meg, mikor kezdődött a meccs (az Események lista / "
                "a csúszka idő-skálája szerint) — az azelőtti rész, a "
                "bemutatás és a bemelegítés ál-eseményeivel együtt, "
                "kikerül az elemzésből.",
                style: AppText.label.copyWith(fontSize: 12.5)),
            const SizedBox(height: AppSpacing.sm),
            if (javaslat == null)
              Text("A felismerés keresi a meccs kezdetét a követésben…",
                  style: AppText.label.copyWith(
                      fontSize: 11.5, color: AppColors.textFaint))
            else if (javaslat!.isNotEmpty)
              Text(javaslat!,
                  style: AppText.label.copyWith(
                      fontSize: 11.5,
                      color: javaslatVan
                          ? AppColors.gold
                          : AppColors.textFaint)),
            const SizedBox(height: AppSpacing.sm),
            TextField(
              controller: fromCtrl,
              decoration: const InputDecoration(
                labelText: "A meccs kezdete (p:mp vagy mp)",
                hintText: "pl. 9:09 vagy 549",
                prefixIcon: Icon(Icons.content_cut, size: 18,
                    color: AppColors.gold),
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: toCtrl,
              decoration: const InputDecoration(
                labelText: "A meccs vége (üres = a felvétel vége)",
                hintText: "pl. 92:00",
                prefixIcon: Icon(Icons.content_cut, size: 18,
                    color: AppColors.textFaint),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
                "A videófájlt nem érinti, de az elemzésből VÉGLEG törli "
                "a levágott részt — az csak újrafeldolgozással jön "
                "vissza.",
                style: AppText.label.copyWith(
                    fontSize: 11, color: AppColors.gold)),
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
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Levágás"),
          ),
        ],
        );
      }),
    );
    frissit = null; // a késve érkező javaslat már ne frissítsen semmit
    if (ok != true) return;
    try {
      final r = await _api.trimMatch(widget.matchId,
          _parseIdo(fromCtrl.text) ?? 0.0,
          toS: _parseIdo(toCtrl.text));
      if (!mounted) return;
      final ele = (r["head_cut_s"] as num?)?.toDouble() ?? 0;
      final vege = (r["tail_cut_s"] as num?)?.toDouble() ?? 0;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Levágva: ${ele.toStringAsFixed(0)} mp az "
              "elejéről, ${vege.toStringAsFixed(0)} mp a végéről — az "
              "elemzés újraszámolt.")));
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(humanError(e))));
    }
  }

  /// KALIBRÁCIÓ-ELLENŐRZÉS: a motor a pályavonalakat visszarajzolja a
  /// videó kockáira (a kalibráció + a kamera-mozgás követése alapján).
  /// Három kocka — eleje, közepe, vége —, mert a svenkelés a meccs
  /// közben csúsztatja el a helyeket, nem a kalibrált kockán.
  Future<void> _calibCheckDialog() async {
    final match = _match;
    if (match == null || match.frames.isEmpty) return;
    final n = match.frames.length;
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    // A jelenlegi kocka is: ahol a felhasználó épp gyanút fogott, ott
    // nézze meg — a három fix minta a meccs egészéről szól.
    final kockak = <int>{
      _tOf(match),
      match.frames[(n * 0.05).floor().clamp(0, n - 1)].t,
      match.frames[(n * 0.5).floor().clamp(0, n - 1)].t,
      match.frames[(n * 0.95).floor().clamp(0, n - 1)].t,
    }.toList();
    String ido(int t) {
      final s = (t / fps).round();
      return "${s ~/ 60}:${(s % 60).toString().padLeft(2, "0")}";
    }

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Kalibráció ellenőrzése"),
        content: SizedBox(
          width: 900,
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(
                  "A motor a pályavonalakat (alapvonal, felező, 6 m-es "
                  "kapuelőtér, kapuk) visszarajzolja a videó kockáira. A "
                  "rajzolt vonalnak a VALÓDI vonalra kell ülnie — a meccs "
                  "elején, közepén és végén is. Ahol elcsúszik, ott a "
                  "kalibráció vagy a kamera-mozgás követése a hibás.",
                  style: AppText.label.copyWith(fontSize: 12.5)),
              const SizedBox(height: AppSpacing.sm),
              // ILLESZKEDÉS SZÁMOKBAN: a szemmel-ellenőrzés géppel — a
              // motor nyolc kockán méri, mennyire ül a rajz a valódi
              // vonalakon (0..1), és megmondja, hol a leggyengébb.
              FutureBuilder<Map<String, dynamic>>(
                future: _api.fetchCalibFit(widget.matchId),
                builder: (ctx2, snap) {
                  if (snap.connectionState != ConnectionState.done) {
                    return Text("Illeszkedés mérése a videón…",
                        style: AppText.label.copyWith(
                            fontSize: 11.5, color: AppColors.textFaint));
                  }
                  final r = snap.data;
                  final atlag = (r?["mean_fit"] as num?)?.toDouble();
                  if (snap.hasError || r == null || atlag == null) {
                    return Text(
                        "Az illeszkedés nem mérhető (régi mentés vagy a "
                        "videó nem érhető el).",
                        style: AppText.label.copyWith(
                            fontSize: 11.5, color: AppColors.textFaint));
                  }
                  final min = (r["min_fit"] as num?)?.toDouble() ?? atlag;
                  final rosszT = (r["worst_t"] as num?)?.toInt();
                  final jo = atlag >= 0.5 && min >= 0.3;
                  return Text(
                      "Illeszkedés: átlag ${(atlag * 100).round()}% · "
                      "leggyengébb ${(min * 100).round()}%"
                      "${rosszT != null ? " (${ido(rosszT)}-nál)" : ""}"
                      "${jo ? " — a kalibráció tartja." : " — ahol gyenge, ott elcsúszott a kalibráció vagy a kamera-követés."}",
                      style: AppText.label.copyWith(
                          fontSize: 12,
                          color: jo ? AppColors.accent : AppColors.gold));
                },
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final t in kockak)
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 4),
                        child: Column(children: [
                          Text(ido(t),
                              style: AppText.label.copyWith(fontSize: 11)),
                          const SizedBox(height: 4),
                          ClipRRect(
                            borderRadius: BorderRadius.circular(8),
                            child: Image.network(
                              _api.calibOverlayUrl(widget.matchId, t),
                              fit: BoxFit.contain,
                              errorBuilder: (_, __, ___) => Container(
                                padding: const EdgeInsets.all(12),
                                color: AppColors.surfaceAlt,
                                child: Text(
                                    "Nem készült kép ehhez a kockához — "
                                    "régi mentés (kalibráció-geometria "
                                    "nélkül), vagy a videó nem érhető el. "
                                    "Újrafeldolgozás után elérhető.",
                                    style: AppText.label
                                        .copyWith(fontSize: 11)),
                              ),
                            ),
                          ),
                        ]),
                      ),
                    ),
                ],
              ),
            ]),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text("Rendben")),
        ],
      ),
    );
  }

  /// Diagnosztika-JSON mentése — a fejlesztőnek szánt visszajelzés.
  /// Videót, képet, személyes adatot nem tartalmaz.
  Future<void> _saveDiagnostics() async {
    try {
      final diag = await _api.fetchDiagnostics(widget.matchId);
      if (!mounted) return;
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Diagnosztika mentése (JSON)",
        fileName: "diagnosztika_${widget.matchId}.json",
        type: FileType.custom,
        allowedExtensions: const ["json"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsString(
          const JsonEncoder.withIndent("  ").convert(diag));
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Diagnosztika mentve: $path — ezt küldd el a "
              "fejlesztőnek (videót nem tartalmaz).")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(humanError(e))));
    }
  }

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
          SnackBar(content: Text("Csere-hiba: ${humanError(e)}")));
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
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Mentési hiba: ${humanError(e)}")));
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
    final warnCount = ((q["warnings"] as List?) ?? const []).length;
    final color = score >= 70
        ? AppColors.accent
        : score >= 40
            ? AppColors.gold
            : AppColors.away;
    return Tooltip(
      message: warnCount == 0
          ? "A feldolgozás minősége — koppints a részletekért"
          : "$warnCount figyelmeztetés — koppints, hogy lásd, mit érdemes "
              "javítani",
      child: InkWell(
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
            // Ha VAN mit megnézni, a csipet ki is mondja — eddig csak a
            // pontszám színe utalt rá, és a figyelmeztetések (pl. az
            // elcsúszott kalibráció) rejtve maradtak a párbeszédben.
            if (warnCount > 0) ...[
              const SizedBox(width: 6),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(
                  color: AppColors.gold.withOpacity(0.18),
                  borderRadius: BorderRadius.circular(8),
                  border:
                      Border.all(color: AppColors.gold.withOpacity(0.6)),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  const Icon(Icons.warning_amber_rounded,
                      size: 11, color: AppColors.gold),
                  const SizedBox(width: 3),
                  Text("$warnCount",
                      style: AppText.label.copyWith(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                          color: AppColors.gold)),
                ]),
              ),
            ],
          ]),
        ),
      ),
    );
  }

  /// "Javult-e?" — a mostani pontszám a legutóbbi feldolgozáshoz mérve.
  ///
  /// Az első feldolgozásnál (nincs mihez viszonyítani) null: nem
  /// találunk ki összehasonlítást.
  String? _javulasSzoveg(Map<String, dynamic> q) {
    final elozoek = (q["previous"] as List?) ?? const [];
    if (elozoek.isEmpty) return null;
    final delta = (q["score_delta"] as num?)?.toInt();
    if (delta == null) return null;
    final elozo = (elozoek.first as Map)["score"];
    if (delta > 0) {
      return "Javult: a legutóbbi feldolgozásod $elozo/100 volt "
          "(+$delta pont).";
    }
    if (delta < 0) {
      return "Romlott: a legutóbbi feldolgozásod $elozo/100 volt "
          "($delta pont).";
    }
    return "Ugyanannyi, mint a legutóbbi feldolgozásod ($elozo/100).";
  }

  /// Másodperc → "óra:perc:mp" (egy óra alatt "perc:mp") — a videó
  /// lejátszójában ebben az alakban kereshető vissza a szakasz.
  /// A backend `_ora` segédjének tükre.
  String _ora(Object? seconds) {
    final mp = (seconds as num?)?.toDouble();
    if (mp == null || mp < 0) return "?";
    final ossz = mp.round();
    final ora = ossz ~/ 3600;
    final perc = (ossz % 3600) ~/ 60;
    final masodperc = ossz % 60;
    final mm = masodperc.toString().padLeft(2, "0");
    if (ora > 0) return "$ora:${perc.toString().padLeft(2, "0")}:$mm";
    return "$perc:$mm";
  }

  /// Mit vágott le a motor a felvétel elejéből/végéből (meccs-ablak).
  ///
  /// A backend másodpercben adja; itt percre kerekítünk, mert a
  /// felhasználó a videót percben keresi vissza. Ha nem vágott semmit,
  /// azt is kimondjuk — az a jó hír, hogy a felvétel eleve csak meccs.
  String _meccsAblakSzoveg(Map<String, dynamic> q) {
    final eleje = (q["game_trim_head_s"] as num?)?.toDouble() ?? 0.0;
    final vege = (q["game_trim_tail_s"] as num?)?.toDouble() ?? 0.0;
    if (eleje <= 0 && vege <= 0) {
      // Ezt a mondatot a felhasználó ELLENŐRIZNI tudja: ha tudja, hogy
      // a videóban benne volt a bemelegítés, akkor a felismerés
      // tévedett, és a kézi időablak a megoldás. Enélkül csak a kész
      // elemzés furcsaságaiból jönne rá — sokkal később.
      return "Meccs-ablak: a motor szerint a felvétel eleje-vége is "
          "meccs, ezért nem vágott. Ha volt rajta bemelegítés vagy "
          "csapatbemutatás, add meg kézzel a meccs időablakát.";
    }
    final reszek = <String>[];
    if (eleje > 0) reszek.add("elejéről ${(eleje / 60).round()} perc");
    if (vege > 0) reszek.add("végéről ${(vege / 60).round()} perc");
    return "Meccs-ablak: ${reszek.join(", ")} levágva "
        "(bemelegítés / meccs előtti-utáni rész)";
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
            // A lefedettség csak a LÁTOTT labdát számolja; a rövid
            // hézagok pótlása külön szám, hogy a mutató ne tűnjön
            // jobbnak a saját találgatásunktól.
            Text(
                "Labda-lefedettség: ${q["ball_coverage_pct"]}%"
                "${q["ball_filled_pct"] != null
                    ? " (+${q["ball_filled_pct"]}% pótolt)" : ""}",
                style: AppText.label),
            Text("Becsült pozíciók: ${q["estimated_ratio_pct"]}%", style: AppText.label),
            Text("Leghosszabb labda-kiesés: ${q["longest_ball_gap_s"]} mp", style: AppText.label),
            // A pályán kívülre vetülő mérések aránya: ez az elcsúszott
            // kalibráció ujjlenyomata (a motor ebből ad figyelmeztetést).
            if (q["out_of_court_pct"] != null)
              Text("Pályán kívülre eső mérés: ${q["out_of_court_pct"]}%",
                  style: AppText.label),
            // A felvétel mekkora részét dolgoztuk fel: enélkül a
            // "csak az első félidőt elemezte ki" élmény megmagyarázatlan
            // marad (megvágott feltöltés, hossz-beállítás, megszakadás).
            if (q["calibrated"] == false)
              Text("Pálya-kalibráció: NEM volt",
                  style: AppText.label.copyWith(color: AppColors.away)),
            if (q["processed_pct"] != null)
              Text(
                  "A felvétel feldolgozott része: ${q["processed_pct"]}%"
                  "${q["video_seconds"] != null ? " (a videó "
                      "${((q["video_seconds"] as num) / 60).round()} perc)"
                      : ""}",
                  style: AppText.label),
            // MELYIK szakasz: a százalék nem mondja meg, hogy az eleje
            // vagy a vége maradt ki. A felhasználó a videót
            // perc:másodpercben keresi vissza — ez azonnal ellenőrizhető.
            if (q["processed_from_s"] != null && q["processed_to_s"] != null)
              Text(
                  "Feldolgozott szakasz: "
                  "${_ora(q["processed_from_s"])}–${_ora(q["processed_to_s"])}"
                  " (a videó órája szerint)",
                  style: AppText.label),
            // MECCS-ABLAK: levágta-e a motor a bemelegítést és a
            // csapatbemutatást. Ha nem sikerült megtalálni a játék
            // kezdetét, azok BENNMARADTAK — és az álldogálás eladott
            // labdának látszik. (A null a régi mentések állapota:
            // arról nem állítunk semmit.)
            if (q["game_window_found"] == false)
              Text("Meccs-ablak: NEM sikerült megtalálni a játék kezdetét",
                  style: AppText.label.copyWith(color: AppColors.away))
            else if (q["game_window_found"] == true)
              Text(_meccsAblakSzoveg(q), style: AppText.label),
            // JAVULT-E? Aki újrakalibrál és újrafuttat, pont ezt a
            // választ keresi — a puszta "72/100" nem mondja meg, hogy
            // jó irányba ment-e. A motor a korábbi feldolgozások
            // pontszámát is kiadja.
            if (_javulasSzoveg(q) != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(_javulasSzoveg(q)!,
                  style: AppText.value.copyWith(
                      fontSize: 13,
                      color: ((q["score_delta"] as num?) ?? 0) >= 0
                          ? AppColors.accent
                          : AppColors.away)),
            ],
            // ELSŐ TEENDŐ: négy-hat figyelmeztetés mellett a
            // felhasználó nem tudja, mivel kezdje — pedig a lista eleje
            // és a vége nem egyenrangú. A motor rangsorol; itt csak
            // kiemeljük, hogy ne vesszen el a felsorolásban.
            if (q["next_action"] != null) ...[
              const SizedBox(height: AppSpacing.md),
              Container(
                decoration: BoxDecoration(
                  color: AppColors.gold.withOpacity(0.10),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: AppColors.gold.withOpacity(0.4)),
                ),
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  const Icon(Icons.flag_outlined,
                      size: 16, color: AppColors.gold),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("ELSŐ TEENDŐ", style: AppText.sectionLabel),
                          const SizedBox(height: 2),
                          Text("${q["next_action"]}",
                              style: AppText.label.copyWith(
                                  fontSize: 12.5,
                                  color: AppColors.textPrimary)),
                        ]),
                  ),
                ]),
              ),
            ],
            // KLIP, NEM MECCS: nem hiba, hanem tájékoztatás — ezért
            // nem a figyelmeztetések közt és nem riasztó színnel. Aki
            // egy három perces klipet elemez, enélkül a hallgató
            // rétegeket hiányos elemzésnek nézi.
            if (q["clip_note"] != null) ...[
              const SizedBox(height: AppSpacing.md),
              Container(
                decoration: BoxDecoration(
                  color: AppColors.surfaceAlt,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: AppColors.border),
                ),
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  const Icon(Icons.movie_outlined,
                      size: 16, color: AppColors.accent),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("KLIP, NEM TELJES MECCS",
                              style: AppText.sectionLabel),
                          const SizedBox(height: 2),
                          Text("${q["clip_note"]}",
                              style: AppText.label.copyWith(
                                  fontSize: 12.5,
                                  color: AppColors.textPrimary)),
                        ]),
                  ),
                ]),
              ),
            ],
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
            // Réteg-megbízhatóság: mely elemzésekhez nincs elég minta
            // ezen a meccsen (és miért) — csak a hiányzókat soroljuk.
            ...(() {
              final conf = ((q["confidence"] as List?) ?? const [])
                  .cast<Map<String, dynamic>>()
                  .where((r) => r["available"] == false)
                  .toList();
              if (conf.isEmpty) return const <Widget>[];
              return <Widget>[
                const SizedBox(height: AppSpacing.md),
                Text("KEVÉS MINTÁJÚ RÉTEGEK", style: AppText.sectionLabel),
                for (final r in conf)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.visibility_off_outlined,
                              size: 15, color: AppColors.textFaint),
                          const SizedBox(width: 6),
                          Expanded(
                              child: Text(
                                  "${r["label"]}: ${r["reason"]}",
                                  style: AppText.label.copyWith(
                                      fontSize: 12,
                                      color: AppColors.textFaint))),
                        ]),
                  ),
              ];
            })(),
          ],
        ),
        actions: [
          // ÚJRAFELDOLGOZÁS: a jelentés megmondja, mi a baj (jellemzően
          // a kalibráció) — a javítás után itt lehet egy kattintással
          // újrafuttatni ugyanarra a meccsre. A motor a videóhoz
          // MENTETT (tehát a frissen javított) kalibrációval indul, nem
          // a régi job-beállítással: különben ugyanazt a rossz
          // eredményt adná még egyszer, egy újabb óra árán.
          if (q["next_action"] != null && !widget.matchId.startsWith("sim-"))
            TextButton(
              onPressed: () {
                Navigator.pop(ctx);
                _reprocessThisMatch();
              },
              child: const Text("Újrafeldolgozás a friss kalibrációval"),
            ),
          // BENNMARADT BEMUTATÁS: a jelentés megtalálta a meccs kezdetét
          // — a ✂ párbeszéd elő is tölti; innen egy kattintás, nem kell
          // a könyvtárba vagy az eszköztárba menni érte.
          if (warnings.any((w) => "$w".contains("nem-játéknak látszik")) &&
              !widget.matchId.startsWith("sim-"))
            TextButton.icon(
              onPressed: () {
                Navigator.pop(ctx);
                _trimDialog();
              },
              icon: const Icon(Icons.content_cut, size: 16),
              label: const Text("Levágás a javaslat szerint"),
            ),
          // DIAGNOSZTIKA a fejlesztőnek: a képernyőkép lassú és
          // veszteséges — ez egy gép által olvasható JSON-t ment
          // (minőség + eseményszámok + beállítások, videó nélkül),
          // amiből a hiba oka kiolvasható.
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _saveDiagnostics();
            },
            child: const Text("Diagnosztika mentése"),
          ),
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Rendben")),
        ],
      ),
    );
  }

  /// Ezt a meccset dolgoztatja fel újra — a videóhoz MENTETT (tehát a
  /// javított) kalibrációval, a régi meccs helyére.
  ///
  /// A megerősítés nem formalitás: a gomb a KALIBRÁCIÓT frissíti, a
  /// többi beállítást (meccs-időablak, minőségi profil, hossz) viszont
  /// az eredeti indításból viszi. Ha a baj éppen az volt, hogy a
  /// bemelegítés bekerült az elemzésbe, ez a gomb nem oldja meg — azt
  /// az Új elemzés lapon kell megadni. Egy fél-egy órás munkát nem
  /// indítunk el ilyen félreértéssel.
  Future<void> _reprocessThisMatch() async {
    final rendben = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Újrafeldolgozás"),
        content: SizedBox(
          width: 470,
          child: Text(
            "A feldolgozás a videóhoz MENTETT (tehát a frissen javított) "
            "kalibrációval indul újra, és a régi meccs helyére dolgozik.\n\n"
            "A többi beállítást — a meccs időablakát, a minőségi profilt "
            "és a hosszt — az EREDETI indításból viszi. Ha a baj az volt, "
            "hogy a bemelegítés vagy a csapatbemutatás bekerült az "
            "elemzésbe, azt itt nem lehet megadni: indítsd inkább az Új "
            "elemzés lapról, ahol a meccs időablaka is beállítható.",
            style: AppText.label.copyWith(fontSize: 12.5),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text("Mégse"),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: AppColors.accent,
                foregroundColor: AppColors.onAccent),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text("Indítás így"),
          ),
        ],
      ),
    );
    if (rendben != true) return;
    try {
      await _api.reprocessMatch(widget.matchId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text(
              "Újrafeldolgozás elindítva a videóhoz mentett kalibrációval "
              "— a haladást a Feldolgozások lapon követheted.")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(humanError(e))));
    }
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
                  final (fromT, toT) = _periodRange();
                  _passNetwork = computePassNetwork(_match!, _events, t,
                      fromT: fromT, toT: toT);
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
        // Idő-ablak: az 1. és 2. félidő külön nézete — a fáradás és a
        // félidei taktikai váltás a térképeken és a passz-hálón így válik
        // láthatóvá.
        if (_viewMode == ViewMode.shots ||
            _viewMode == ViewMode.heatmap ||
            _viewMode == ViewMode.passes) ...[
          const SizedBox(width: AppSpacing.sm),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: DropdownButton<String>(
              value: _period,
              underline: const SizedBox(),
              dropdownColor: AppColors.surfaceAlt,
              items: const [
                DropdownMenuItem(value: "all", child: Text("Teljes meccs")),
                DropdownMenuItem(value: "h1", child: Text("1. félidő")),
                DropdownMenuItem(value: "h2", child: Text("2. félidő")),
              ],
              onChanged: (v) {
                if (v == null) return;
                setState(() {
                  _period = v;
                  final m = _match;
                  if (m != null) {
                    final (fromT, toT) = _periodRange();
                    _heatmap = computeTeamHeatmap(m, _heatmapTeam,
                        fromT: fromT, toT: toT);
                    _passNetwork = computePassNetwork(m, _events, _passTeam,
                        fromT: fromT, toT: toT);
                  }
                });
              },
            ),
          ),
        ],
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
      // Nagyítható pálya: touchpad-csippentés vagy Ctrl+görgő nagyít,
      // dupla kattintás visszaáll — a koordinátákat a Transform
      // hit-tesztje igazítja, ezért a játékos-kijelölés nagyítva is jó.
      return ZoomPanView(
          child: GestureDetector(
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
            if (_viewMode == ViewMode.heatmap && _heatmap != null)
              Positioned(left: 10, top: 10, child: _heatmapChip(match)),
            if (_viewMode == ViewMode.shots)
              Positioned.fill(
                // A nézetre váltáskor a jelölők lépcsőzve pattannak be
                // (a widget ilyenkor épül fel, tehát egyszer játszik le).
                child: TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: 1),
                  duration: reduceMotion(context)
                      ? Duration.zero
                      : const Duration(milliseconds: 900),
                  curve: Curves.easeOutCubic,
                  builder: (context, t, _) => CustomPaint(
                    painter: ShotMapPainter(
                        shots: _filteredShots(), currentFrame: _tOf(match),
                        progress: t),
                  ),
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
      ));
    });
  }

  /// Az aktuális idő-ablak [tól, ig] frame-ben (null = nincs korlát).
  (int?, int?) _periodRange() {
    final m = _match;
    if (m == null || _period == "all") return (null, null);
    final half = m.frames.isEmpty ? 0 : m.frames[m.frames.length ~/ 2].t;
    return _period == "h1" ? (null, half) : (half + 1, null);
  }

  /// A csapat- és idő-szűrőnek megfelelő lövés-jelölők.
  List<ShotMarker> _filteredShots() {
    final (fromT, toT) = _periodRange();
    Iterable<ShotMarker> out = _shots;
    if (_shotTeam != "all") {
      final team = _shotTeam == "home" ? Team.home : Team.away;
      out = out.where((s) => s.team == team);
    }
    if (fromT != null) out = out.where((s) => s.t >= fromT);
    if (toT != null) out = out.where((s) => s.t <= toT);
    return out.toList();
  }

  /// A lövéstérkép összegző kártyája (bal-felső sarok): lövések, gólok,
  /// hatékonyság + zóna-bontás (irány és távolság szerint). A csapat-
  /// szűrővel nézőpontot váltasz: a saját csapat = honnan lövünk; az
  /// ellenfél = honnan kapjuk (védekezés-elemzés).
  /// Hőtérkép-csipet: MIT JELENT a szín. A lövés- és passz-nézetnek van
  /// magyarázó csipetje, a hőtérképnek eddig nem volt — pedig itt a szín
  /// maga az adat, és magyarázat nélkül csak "valami piros folt".
  Widget _heatmapChip(Match match) {
    final hm = _heatmap!;
    final color =
        _heatmapTeam == Team.home ? AppColors.home : AppColors.away;
    final name = _heatmapTeam == Team.home
        ? match.meta.homeTeam
        : match.meta.awayTeam;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.surface.withOpacity(0.92),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text("$name — hol tölti az időt",
            style: AppText.value.copyWith(fontSize: 12)),
        const SizedBox(height: 6),
        Row(mainAxisSize: MainAxisSize.min, children: [
          Text("ritkán", style: AppText.label.copyWith(fontSize: 10.5)),
          const SizedBox(width: 6),
          // Skála-sáv: pontosan az a színátmenet, amit a rajzoló használ.
          Container(
            width: 84,
            height: 8,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(4),
              // A rajzoló VALÓDI tartománya (heatmap_painter): a folt
              // magja 0,18-tól 0,63-ig sötétedik, és a legforróbb
              // cellák magja világosodik is. A skála ne ígérjen többet.
              gradient: LinearGradient(colors: [
                color.withOpacity(0.18),
                Color.lerp(color, Colors.white, 0.35)!.withOpacity(0.63),
              ]),
            ),
          ),
          const SizedBox(width: 6),
          Text("sokat", style: AppText.label.copyWith(fontSize: 10.5)),
        ]),
        const SizedBox(height: 4),
        Text(
            "a folt SŰRŰSÉGE a cellában töltött idő · "
            "${hm.binsX}×${hm.binsY}-es rács",
            style: AppText.label
                .copyWith(fontSize: 10.5, color: AppColors.textFaint)),
      ]),
    );
  }

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
          // A jelölő MÉRETE a helyzet értéke — enélkül a nagy körök
          // csak "valamiért nagyobbak".
          if (shots.any((s) => s.xg != null))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                  "a jelölő MÉRETE a helyzet értéke (xG): a nagy körök a "
                  "nagy helyzetek",
                  style: AppText.label.copyWith(fontSize: 11)),
            ),
          if (shots.any((s) => s.free == true))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                  "szabad lövés (pontozott gyűrű): "
                  "${shots.where((s) => s.free == true).length} — a lövőnél "
                  "nem volt védő 2 m-en belül",
                  style: AppText.label.copyWith(fontSize: 11)),
            ),
          Builder(builder: (_) {
            final fastest =
                (_shotSpeeds["fastest"] as Map?)?.cast<String, dynamic>();
            final kmh = ((fastest?["speed_kmh"] as num?) ?? 0).toDouble();
            if (kmh < 60) return const SizedBox.shrink();
            final txt = kmh.toStringAsFixed(0);
            return Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text("leggyorsabb lövés: $txt km/h",
                  style: AppText.label.copyWith(fontSize: 11)),
            );
          }),
          if (shots.any((s) => s.xg != null))
            Builder(builder: (_) {
              final withXg = shots.where((s) => s.xg != null).toList();
              final sumXg = withXg.fold(0.0, (a, s) => a + (s.xg ?? 0));
              final avgXg = withXg.isEmpty ? 0.0 : sumXg / withXg.length;
              return Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                    "várható gól (xG): ${sumXg.toStringAsFixed(1)}"
                    " · átl. ${avgXg.toStringAsFixed(2)} xG/lövés"
                    " · a jelölő mérete = a helyzet értéke",
                    style: AppText.label.copyWith(fontSize: 11)),
              );
            }),
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
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(text, style: AppText.value.copyWith(fontSize: 12)),
        if (net != null && net.totalPasses > 0) ...[
          const SizedBox(height: 3),
          // A rajz két dolgot kódol méretbe/vastagságba; enélkül a háló
          // csak "valami pókháló" — a lövéstérkép és a hőtérkép is
          // kimondja, mit jelentenek a jelei.
          Text(
              "a korong mérete a passz-részvétel · a vonal vastagsága a "
              "két ember közti passzok száma",
              style: AppText.label
                  .copyWith(fontSize: 10.5, color: AppColors.textFaint)),
        ],
      ]),
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
    // 2. félidei tempó-esés (ha mérhető): a fáradás jele a buborékban.
    final fade = _playerFatigue[id];
    if (fade != null && fade.abs() >= 10) {
      final pfx = fade > 0 ? "−" : "+";
      label += " · 2. félidő: $pfx${fade.abs().toStringAsFixed(0)}% tempó";
    }
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
          SnackBar(content: Text("Mezszám-mentés hiba: ${humanError(e)}")));
    }
  }

  /// TÖMEGES mezszám-kiosztás: minden követett játékos egy listában.
  ///
  /// Miért kell: a mezszám kapuőr — nélküle a keret-lap, a toplisták és
  /// a játékos-fejlődés néma marad, mert meccsek közt csak a szám köti
  /// össze a játékost. A pályára-kattintós szerkesztő játékosonként egy
  /// külön párbeszéd; tizennégy emberre az már nem munka, hanem
  /// elrettentés — és ezért marad el.
  ///
  /// A lista JÁTÉKIDŐ szerint csökken: elöl a sokat játszó (valódi)
  /// trackek, hátul a másodperces töredékek, amiket úgysem érdemes
  /// beszámozni. Csapatonként csoportosítva, mert az edző a saját
  /// keretét egyben tartja fejben.
  Future<void> _bulkJerseys(Match match) async {
    final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
    final sorok = _stats.values.toList()
      ..sort((a, b) {
        if (a.team != b.team) return a.team == Team.home ? -1 : 1;
        return b.measuredFrames.compareTo(a.measuredFrames);
      });
    final ctrls = {
      for (final st in sorok)
        st.trackId: TextEditingController(
            text: st.jerseyNumber?.toString() ?? "")
    };
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Mezszámok kiosztása"),
        content: SizedBox(
          width: 460,
          height: 460,
          child: Column(children: [
            Text(
                "A mezszám köti össze a játékost a meccsek között: enélkül "
                "a Keret, a toplisták és a Játékos-fejlődés üres marad. "
                "Elöl a legtöbbet játszó trackek — a másodperces "
                "töredékeket nyugodtan hagyd üresen.",
                style: AppText.label.copyWith(fontSize: 11.5)),
            const SizedBox(height: AppSpacing.sm),
            Expanded(
              child: ListView.builder(
                itemCount: sorok.length,
                itemBuilder: (_, i) {
                  final st = sorok[i];
                  final perc = st.measuredFrames / fps / 60.0;
                  final hazai = st.team == Team.home;
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(children: [
                      Container(width: 8, height: 8,
                          decoration: BoxDecoration(
                              color: hazai
                                  ? AppColors.home
                                  : AppColors.away,
                              shape: BoxShape.circle)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                            "${hazai ? match.meta.homeTeam : match.meta.awayTeam}"
                            " · ${st.trackId}. track · "
                            "${perc.toStringAsFixed(1)} perc",
                            overflow: TextOverflow.ellipsis,
                            style: AppText.label.copyWith(fontSize: 12)),
                      ),
                      SizedBox(
                        width: 70,
                        child: TextField(
                          controller: ctrls[st.trackId],
                          keyboardType: TextInputType.number,
                          style: AppText.value.copyWith(fontSize: 13),
                          decoration: const InputDecoration(
                              isDense: true,
                              hintText: "szám",
                              border: OutlineInputBorder()),
                        ),
                      ),
                    ]),
                  );
                },
              ),
            ),
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
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Mentés"),
          ),
        ],
      ),
    );
    // A beírt értékeket a párbeszéd bezárása UTÁN olvassuk ki, mielőtt
    // a vezérlőket eldobjuk.
    final beirt = {
      for (final e in ctrls.entries) e.key: e.value.text.trim()
    };
    for (final c in ctrls.values) {
      c.dispose();
    }
    if (ok != true || !mounted) return;

    // Csak a VÁLTOZOTT sorokat küldjük el — egy meccsen tizennégy
    // felesleges kérés is elég ahhoz, hogy lassúnak érződjön.
    var mentve = 0;
    var hibas = 0;
    for (final st in sorok) {
      final szoveg = beirt[st.trackId] ?? "";
      final uj = szoveg.isEmpty ? null : int.tryParse(szoveg);
      if (szoveg.isNotEmpty && (uj == null || uj < 0 || uj > 99)) {
        hibas++;
        continue;
      }
      if (uj == st.jerseyNumber) continue;
      try {
        await _api.setJersey(widget.matchId, st.trackId, uj);
        for (final f in match.frames) {
          for (final p in f.players) {
            if (p.trackId == st.trackId) p.jerseyNumber = uj;
          }
        }
        mentve++;
      } catch (_) {
        hibas++;
      }
    }
    if (!mounted) return;
    setState(() {
      _stats = computePlayerStats(match);
      _passNetwork = computePassNetwork(match, _events, _passTeam);
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(hibas == 0
            ? "$mentve mezszám mentve."
            : "$mentve mezszám mentve, $hibas sor kimaradt "
                "(a szám 0 és 99 közötti lehet).")));
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
      _frameIndex = _indexOfT(match, frame);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoKey.currentState?.seekTo(match.meta.videoSecondsOfFrame(frame));
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
          tooltip: _playing ? "Szünet (szóköz)" : "Lejátszás (szóköz)",
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
                currentFrame: _tOf(match),
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
            if (_events.isNotEmpty && match.frames.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: SizedBox(
                  height: 6,
                  child: CustomPaint(
                    size: const Size(double.infinity, 6),
                    painter: _EventTickPainter(
                        events: _events,
                        tStart: match.frames.first.t,
                        tEnd: match.frames.last.t),
                  ),
                ),
              ),
          ]),
        ),
        const SizedBox(width: AppSpacing.sm),
        // Videó-idő (a kocka t címkéjéből): egyezik az Események lista, a
        // jegyzetek és a jelenet-lejátszó időskálájával vágott meccsen is.
        Text("${(_tOf(match) / fps).toStringAsFixed(1)} s", style: AppText.value),
        Text(
            "  /  ${((match.frames.isEmpty ? 0 : match.frames.last.t) / fps).toStringAsFixed(0)} s",
            style: AppText.label),
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
    final most = _tOf(match);
    int target;
    if (dir > 0) {
      target = points.firstWhere((t) => t > most,
          orElse: () => points.first); // a végén körbeér az elejére
    } else {
      target = points.lastWhere((t) => t < most,
          orElse: () => points.last); // az elején körbeér a végére
    }
    _seekToFrame(match, target);
  }

  /// Videó-kocka (t címke) → lista-INDEX: az első kocka, amelynek t-je
  /// eléri. A kettő NEM ugyanaz: utólagos ✂ vágás után a lista elejéről
  /// kockák hiányoznak, a t címkék (események, jegyzetek, javítások,
  /// videó-idő) viszont maradnak — t-vel indexelni rossz kockára vinne.
  static int _indexOfT(Match m, int t) {
    var lo = 0, hi = m.frames.length - 1;
    while (lo < hi) {
      final mid = (lo + hi) ~/ 2;
      if (m.frames[mid].t < t) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }
    return lo < 0 ? 0 : lo;
  }

  /// A mutatott kocka t címkéje (videó-kocka) — ezt hasonlítjuk az
  /// események/jegyzetek t-jéhez, és ezt mentjük jegyzet/javítás idejének.
  int _tOf(Match m) {
    if (m.frames.isEmpty) return 0;
    return m.frames[_frameIndex.clamp(0, m.frames.length - 1)].t;
  }

  /// Ugrás egy adott videó-kockára (t): megállítjuk a lejátszást, és ha
  /// van eredeti videó, azt is a jelenetre állítjuk (közös logika
  /// esemény/jegyzet/grafikon kattintáshoz).
  void _seekToFrame(Match match, int frame) {
    setState(() {
      _timer?.cancel();
      _playing = false;
      _frameIndex = _indexOfT(match, frame);
      if (match.meta.videoPath != null && VideoPanel.supported) {
        _showVideo = true;
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoKey.currentState?.seekTo(match.meta.videoSecondsOfFrame(frame));
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
            // A fül-stílust (pill-indikátor, színek) a téma adja —
            // lásd AppTheme.dark tabBarTheme.
            const TabBar(
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              padding: EdgeInsets.symmetric(horizontal: 6, vertical: 6),
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
                  StatsPanel(
                      stats: _stats,
                      homeName: match.meta.homeTeam,
                      awayName: match.meta.awayTeam,
                      onPlayerReport: (tid, label) =>
                          _savePlayerReport(match, tid, label)),
                  _summary == null
                      ? const EmptyState(
                          "Nincs edzői összefoglaló",
                          why: "Az összefoglaló a meccs betöltésekor "
                              "készül el. Ha üres maradt, töltsd újra a "
                              "meccset.",
                          icon: Icons.summarize_outlined)
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
                          training: _training,
                          keyPlayers: _keyPlayers,
                          keyMoments: _keyMoments,
                          setplayEff: _setplayEff,
                          marking: _marking,
                          blocks: _blocks,
                          ballWinners: _ballWinners,
                          onNoteMoment: (t, label) =>
                              _noteKeyMoment(match, t, label),
                          progression: _progression,
                          goalTimeline: _goalTimeline,
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
  // A mutatott kockák t-tartománya: vágott meccsen nem 0-tól indul.
  final int tStart, tEnd;
  _EventTickPainter(
      {required this.events, required this.tStart, required this.tEnd});

  @override
  void paint(Canvas canvas, Size size) {
    if (tEnd <= tStart) return;
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
      if (t < tStart || t > tEnd) continue; // levágott részre esik
      final x = size.width * (t - tStart) / (tEnd - tStart);
      final h = type == "goal" ? size.height : size.height * 0.66;
      canvas.drawLine(
          Offset(x, size.height - h), Offset(x, size.height),
          Paint()..color = color..strokeWidth = type == "goal" ? 2.5 : 1.5);
    }
  }

  @override
  bool shouldRepaint(covariant _EventTickPainter old) =>
      old.events != events || old.tStart != tStart || old.tEnd != tEnd;
}
