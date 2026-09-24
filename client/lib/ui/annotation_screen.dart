/// Kézi elemzés — az edző SAJÁT elemzése egy meccshez, két részben:
///
///  * ESEMÉNY-NAPLÓ: időpont (a videó ideje), csapat, esemény, mezszám, a
///    passz címzettje, kimenetel, megjegyzés — beírva, szerkeszthetően;
///  * TAKTIKAI TÁBLÁK: felülnézeti pálya mozgatható bábukkal, és
///    sorszámozott nyilakkal (passz, futás, lövés) — így mutatható meg,
///    ki kinek passzolt, ki hova futott.
///
/// Közben a MECCS IS LÁTSZIK: ha a meccs eredeti videója ezen a gépen van,
/// a képernyő tetején lejátszó fut, ami nagyítható (MacBook-touchpad
/// csippentés, Ctrl/⌘+görgő vagy a sarok-gombok), a sávja pedig az
/// elválasztó húzásával átméretezhető. Az idő a lejátszóból egy
/// kattintással átvehető, és a napló egy idejére kattintva a videó oda ugrik.
///
/// Az IDŐ mindenhol az eredeti videó ideje (másodperc) — ugyanaz, amit a
/// lejátszó mutat; a felismert pozíciókhoz a meccs kezdő-kockájával
/// számolunk át (MatchMeta.videoSecondsOfFrame).
///
/// A munka FÉLKÉSZEN is megmarad: minden változás után pár másodperccel
/// magától mentünk — előbb HELYBEN (a felhasználói adatmappába), aztán a
/// motorba. Ha a motor épp nem érhető el, a helyi piszkozat őrzi a munkát,
/// és a következő megnyitáskor (vagy amint a motor válaszol) feltöltjük.
library;

import "dart:async";
import "dart:convert";
import "dart:io";
import "dart:math" as math;

import "package:file_picker/file_picker.dart";
import "package:flutter/foundation.dart";
import "package:flutter/gestures.dart";
import "package:flutter/material.dart";
import "package:flutter/services.dart";

import "../models/tracking.dart";
import "../services/api_client.dart";
import "../services/backend_launcher.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";
import "error_text.dart";
import "video_panel.dart";
import "waiting.dart";

/// A napló esemény-típusai (a backend ANN_EVENT_TYPES-ával azonos).
const List<String> kAnnEventTypes = [
  "lövés", "passz", "eladás", "szerzés", "kiállítás", "hetes",
  "időkérés", "csere", "szabálytalanság", "egyéb",
];

/// A lövés (és a hetes) kimenetelei (a backend ANN_SHOT_OUTCOMES-ával azonos).
const List<String> kAnnShotOutcomes = ["gól", "védés", "mellé", "kapufa", "blokk"];

/// Táblánként legfeljebb ennyi bábu és nyíl (a backend korlátaival azonos).
const int kAnnMaxTokens = 24;
const int kAnnMaxArrows = 60;

/// Ennyi másodperc csend után mentünk magától.
const Duration kAnnAutosave = Duration(seconds: 3);

/// Ha a motor nem érhető el, ennyi időnként próbáljuk újra a feltöltést.
const Duration kAnnRetry = Duration(seconds: 30);

/// A videó-sáv alap-magassága (a munkaterület hányada), és a húzással
/// beállítható határai — alul marad hely a táblának.
const double kAnnVideoFrac = 0.42;
const double kAnnVideoMinFrac = 0.18;
const double kAnnVideoMaxFrac = 0.75;

/// A gyors-rögzítés gombjai: (felirat, esemény-típus, kimenetel). Egy
/// kattintás = egy esemény a videó mostani idejével, a kijelölt csapatnak.
const List<(String, String, String)> kAnnQuickEvents = [
  ("Gól", "lövés", "gól"),
  ("Védés", "lövés", "védés"),
  ("Mellé", "lövés", "mellé"),
  ("Blokk", "lövés", "blokk"),
  ("Hetes-gól", "hetes", "gól"),
  ("Eladás", "eladás", ""),
  ("Szerzés", "szerzés", ""),
  ("Kiállítás", "kiállítás", ""),
];

/// A videó billentyűs léptetése (← / →), és Shifttel a nagy lépés.
const double kAnnKeySeekS = 2.0;
const double kAnnKeySeekLongS = 10.0;

/// Az összevetés eltérés-tételére kattintva a videó ennyivel ELŐTTE
/// indul (a lövés előzménye is látsszon).
const double kAnnCompareLeadS = 3.0;

/// A taktikai tábla legnagyobb nagyítása (1× = a teljes pálya látszik).
const double kAnnBoardMaxZoom = 5.0;

/// A nagyított tábla pálya→képernyő vetítése: a teljes pályára illesztett
/// vetítés [zoom]-szorosa, [pan] képpontnyi eltolással.
CourtTransform annBoardTransform(Size size, double zoom, Offset pan) {
  final base = CourtTransform.fit(size);
  return CourtTransform(base.scale * zoom, base.originX * zoom + pan.dx,
      base.originY * zoom + pan.dy);
}

double _toD(Object? v, double d) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v) ?? d;
  return d;
}

double? _toDn(Object? v) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

/// Egy csapat összesítése a kézi naplóból.
class AnnTeamStats {
  int shots = 0; // lövés + hetes, bármilyen kimenetellel
  int goals = 0;
  int saves = 0;
  int sevenM = 0; // hetesek
  int turnovers = 0;
  int steals = 0;
  int suspensions = 0;
  // mezszám → [gól, lövés]
  final Map<String, List<int>> shooters = {};

  /// Lövés-hatékonyság százalékban (null, ha nincs lövés).
  int? get pct => shots == 0 ? null : (goals * 100 / shots).round();

  /// A legtöbb gólt szerzők (gól, majd kevesebb lövés szerint).
  List<MapEntry<String, List<int>>> topScorers(int n) {
    final l = shooters.entries.where((e) => e.value[0] > 0).toList()
      ..sort((a, b) => b.value[0] != a.value[0]
          ? b.value[0].compareTo(a.value[0])
          : a.value[1].compareTo(b.value[1]));
    return l.take(n).toList();
  }
}

/// A kézi napló összesítése csapatonként — a napló így statisztika-lap
/// is (a "lövés" és a "hetes" lövésnek számít, a "gól" kimenetel gólnak).
Map<String, AnnTeamStats> annLogStats(List<Map<String, dynamic>> events) {
  final out = {"home": AnnTeamStats(), "away": AnnTeamStats()};
  for (final e in events) {
    final st = out[e["team"]];
    if (st == null) continue;
    final type = "${e["type"] ?? ""}";
    final outcome = "${e["outcome"] ?? ""}";
    if (type == "lövés" || type == "hetes") {
      st.shots += 1;
      if (type == "hetes") st.sevenM += 1;
      final goal = outcome == "gól";
      if (goal) st.goals += 1;
      if (outcome == "védés") st.saves += 1;
      final j = "${e["jersey"] ?? ""}".trim();
      if (j.isNotEmpty) {
        final row = st.shooters.putIfAbsent(j, () => [0, 0]);
        row[1] += 1;
        if (goal) row[0] += 1;
      }
    } else if (type == "eladás") {
      st.turnovers += 1;
    } else if (type == "szerzés") {
      st.steals += 1;
    } else if (type == "kiállítás") {
      st.suspensions += 1;
    }
  }
  return out;
}

double _r2(double v) => (v * 100).roundToDouble() / 100;

String _str(Object? v) => v == null ? "" : "$v";

/// Idő beolvasása: "12:40", "1:02:03", "95" vagy "95,5" (másodperc).
double? parseAnnTime(String s) {
  final t = s.trim().replaceAll(",", ".");
  if (t.isEmpty) return null;
  final parts = t.split(":");
  if (parts.length > 3) return null;
  double total = 0;
  for (final p in parts) {
    final v = double.tryParse(p.trim());
    if (v == null || v < 0) return null;
    total = total * 60 + v;
  }
  return total;
}

/// Idő kiírása: "pp:mm" (egy óra fölött "ó:pp:mm").
String formatAnnTime(double s) {
  final t = s.round();
  final h = t ~/ 3600;
  final m = (t % 3600) ~/ 60;
  final sec = t % 60;
  String two(int v) => v.toString().padLeft(2, "0");
  return h > 0 ? "$h:${two(m)}:${two(sec)}" : "${two(m)}:${two(sec)}";
}

class _Token {
  String id;
  String team; // home | away | ball
  String label;
  double x;
  double y;

  _Token({required this.id, required this.team, required this.label,
      required this.x, required this.y});

  factory _Token.fromJson(Map<String, dynamic> m) => _Token(
        id: _str(m["id"]),
        team: _str(m["team"]).isEmpty ? "home" : _str(m["team"]),
        label: _str(m["label"]),
        x: _toD(m["x"], courtLength / 2),
        y: _toD(m["y"], courtWidth / 2),
      );

  Map<String, dynamic> toJson() =>
      {"id": id, "team": team, "label": label, "x": _r2(x), "y": _r2(y)};

  _Token copy() => _Token(id: id, team: team, label: label, x: x, y: y);
}

class _Arrow {
  String kind; // pass | run | shot
  String from;
  String to; // üres: pont-cél (x, y)
  double? x;
  double? y;

  _Arrow({required this.kind, required this.from, this.to = "", this.x, this.y});

  factory _Arrow.fromJson(Map<String, dynamic> m) => _Arrow(
        kind: _str(m["kind"]).isEmpty ? "pass" : _str(m["kind"]),
        from: _str(m["from"]),
        to: _str(m["to"]),
        x: _toDn(m["x"]),
        y: _toDn(m["y"]),
      );

  Map<String, dynamic> toJson() => to.isNotEmpty
      ? {"kind": kind, "from": from, "to": to}
      : {"kind": kind, "from": from, "to": "", "x": _r2(x ?? 0), "y": _r2(y ?? 0)};
}

class _Scene {
  String id;
  String name;
  double? tS;
  String note;
  List<_Token> tokens;
  List<_Arrow> arrows;

  _Scene({required this.id, required this.name, this.tS, this.note = "",
      required this.tokens, required this.arrows});

  factory _Scene.fromJson(Map<String, dynamic> m) {
    final tk = m["tokens"];
    final ar = m["arrows"];
    return _Scene(
      id: _str(m["id"]),
      name: _str(m["name"]),
      tS: _toDn(m["t_s"]),
      note: _str(m["note"]),
      tokens: [
        if (tk is List)
          for (final t in tk)
            if (t is Map) _Token.fromJson(Map<String, dynamic>.from(t)),
      ],
      arrows: [
        if (ar is List)
          for (final a in ar)
            if (a is Map) _Arrow.fromJson(Map<String, dynamic>.from(a)),
      ],
    );
  }

  Map<String, dynamic> toJson() => {
        "id": id,
        "name": name,
        "t_s": tS == null ? null : (tS! * 10).roundToDouble() / 10,
        "note": note,
        "tokens": tokens.map((t) => t.toJson()).toList(),
        "arrows": arrows.map((a) => a.toJson()).toList(),
      };
}

enum _Tool { move, pass, run, shot }

class AnnotationScreen extends StatefulWidget {
  final String matchId;
  final String homeName;
  final String awayName;

  /// A felismert meccs (a "Pozíciók a meccsből" gombhoz); lehet null.
  final Match? match;

  /// A meccs-nézet aktuális ideje (az EREDETI videó másodperce) — az új
  /// események és táblák ezzel az idővel indulnak, a videó innen indul.
  final double startSeconds;

  /// Motor nélkül (demó): csak helyi mentés.
  final bool offline;

  const AnnotationScreen({
    super.key,
    required this.matchId,
    required this.homeName,
    required this.awayName,
    this.match,
    this.startSeconds = 0,
    this.offline = false,
  });

  @override
  State<AnnotationScreen> createState() => _AnnotationScreenState();
}

class _AnnotationScreenState extends State<AnnotationScreen>
    with SingleTickerProviderStateMixin {
  final ApiClient _api = ApiClient();

  // --- a dokumentum ---
  List<Map<String, dynamic>> _events = [];
  List<_Scene> _scenes = [];
  String _status = "in_progress";
  String? _updatedAt;

  // --- mentés-állapot ---
  bool _loading = true;
  bool _saving = false;
  bool _comparing = false; // az összevetés a géppel fut
  bool _saveAgain = false;
  bool _dirty = false; // van helyben még ki nem írt változás
  bool _unsynced = false; // a motorban lévő változat régebbi a helyinél
  int _rev = 0;
  DateTime? _lastSaved;
  String? _saveError;
  Timer? _autosave;
  Timer? _retry;
  static int _idSeq = 0;

  // --- tábla ---
  int _sceneIndex = -1;
  _Tool _tool = _Tool.move;
  String? _pendingFrom; // nyíl-rajzolás: a kiválasztott kiinduló bábu
  String? _selected;
  String? _dragId;
  final TextEditingController _sceneTimeCtrl = TextEditingController();
  final TextEditingController _sceneNoteCtrl = TextEditingController();

  // --- esemény-űrlap ---
  final TextEditingController _timeCtrl = TextEditingController();
  final TextEditingController _jerseyCtrl = TextEditingController();
  final TextEditingController _toJerseyCtrl = TextEditingController();
  final TextEditingController _noteCtrl = TextEditingController();
  String _formTeam = "home";
  String _formType = "passz";
  String _formOutcome = "";
  String _formSceneId = "";
  String? _editingEventId;

  late final TabController _tabs;
  bool _wide = true;

  // --- tábla-nagyítás ---
  double _boardZoom = 1.0;
  Offset _boardPan = Offset.zero; // képpontban, (1 - zoom)·méret … 0
  bool _panningBoard = false; // üres helyről húzva a nagyított táblát
  double _pinchLast = 1.0; // a touchpad-csippentés előző szorzója

  CourtTransform _boardTr(Size size) =>
      annBoardTransform(size, _boardZoom, _boardPan);

  Offset _clampBoardPan(Offset o, Size size) => Offset(
        o.dx.clamp(size.width * (1 - _boardZoom), 0.0).toDouble(),
        o.dy.clamp(size.height * (1 - _boardZoom), 0.0).toDouble(),
      );

  /// Nagyítás a [focal] pont körül: a pont alatti pálya-hely a helyén marad.
  void _zoomBoard(Offset focal, double factor, Size size) {
    final nz = (_boardZoom * factor).clamp(1.0, kAnnBoardMaxZoom).toDouble();
    if (nz == _boardZoom) return;
    final f = nz / _boardZoom;
    setState(() {
      _boardZoom = nz;
      _boardPan = _clampBoardPan(focal - (focal - _boardPan) * f, size);
    });
  }

  void _panBoard(Offset delta, Size size) {
    if (_boardZoom <= 1.0) return;
    setState(() => _boardPan = _clampBoardPan(_boardPan + delta, size));
  }

  void _resetBoardZoom() => setState(() {
        _boardZoom = 1.0;
        _boardPan = Offset.zero;
      });

  // --- videó ---
  final GlobalKey<VideoPanelState> _videoKey = GlobalKey<VideoPanelState>();
  bool _showVideo = true;
  double _videoFrac = kAnnVideoFrac;
  double? _lastVideoS; // elrejtéskor ide tesszük, hogy onnan folytassa

  /// Van-e ezen a gépen lejátszható eredeti videó ehhez a meccshez.
  bool get _hasVideo {
    final p = widget.match?.meta.videoPath;
    return p != null && p.isNotEmpty && VideoPanel.supported;
  }

  bool get _videoOn => _hasVideo && _showVideo;

  /// A lejátszó mostani helye (másodperc) — null, ha nincs videó.
  double? get _videoNow =>
      _videoOn ? _videoKey.currentState?.positionSeconds : null;

  /// A videó adott idejére ugrás (ha rejtve van, előbb megmutatjuk).
  void _seekVideo(double s) {
    if (!_hasVideo) return;
    if (!_showVideo) {
      setState(() {
        _showVideo = true;
        _lastVideoS = s; // a felépülő lejátszó innen indul
      });
      return;
    }
    _videoKey.currentState?.seekTo(s);
  }

  /// Az idő-mező kitöltése a lejátszó mostani helyével.
  void _takeVideoTime(TextEditingController ctrl, {_Scene? scene}) {
    final t = _videoNow;
    if (t == null) {
      _snack("A videó még töltődik — pár másodperc múlva próbáld újra.");
      return;
    }
    setState(() {
      ctrl.text = formatAnnTime(t);
      if (scene != null) {
        scene.tS = t;
        _touch();
      }
    });
  }

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _timeCtrl.text = formatAnnTime(widget.startSeconds);
    _load();
    _retry = Timer.periodic(kAnnRetry, (_) {
      if (!widget.offline && _unsynced && !_saving && !_loading) _save();
    });
    HardwareKeyboard.instance.addHandler(_onKey);
  }

  /// Billentyűk a videóhoz — hogy a naplózás közben ne kelljen egérrel
  /// a lejátszóhoz nyúlni. SOSEM gépelés közben (szövegmezőben a szóköz
  /// szóköz), és csak ha ez a képernyő van elöl (nyitott dialógus,
  /// lenyíló menü alatt nem).
  ///  * Szóköz: lejátszás / szünet,
  ///  * ← / →: 2 mp vissza / előre (Shifttel 10 mp),
  ///  * T: a lejátszó ideje az esemény-űrlapba.
  bool _onKey(KeyEvent e) {
    if (e is! KeyDownEvent && e is! KeyRepeatEvent) return false;
    if (!mounted || !_videoOn) return false;
    if (ModalRoute.of(context)?.isCurrent != true) return false;
    final focus = FocusManager.instance.primaryFocus?.context;
    if (focus != null &&
        (focus.widget is EditableText ||
            focus.findAncestorWidgetOfExactType<EditableText>() != null)) {
      return false;
    }
    final v = _videoKey.currentState;
    if (v == null) return false;
    final kb = HardwareKeyboard.instance;
    if (kb.isControlPressed || kb.isMetaPressed || kb.isAltPressed) {
      return false; // a rendszer- és menü-kombinációk maradjanak érintetlenek
    }
    final key = e.logicalKey;
    if (key == LogicalKeyboardKey.space) {
      if (e is KeyDownEvent) v.togglePlay();
      return true;
    }
    if (key == LogicalKeyboardKey.arrowLeft ||
        key == LogicalKeyboardKey.arrowRight) {
      final step = kb.isShiftPressed ? kAnnKeySeekLongS : kAnnKeySeekS;
      v.seekBy(key == LogicalKeyboardKey.arrowLeft ? -step : step);
      return true;
    }
    if (key == LogicalKeyboardKey.keyT && e is KeyDownEvent) {
      _takeVideoTime(_timeCtrl);
      return true;
    }
    return false;
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_onKey);
    _autosave?.cancel();
    _retry?.cancel();
    if (!_loading && (_dirty || _unsynced)) {
      // Kilépés közben (rendszer-vissza, ablak-bezárás) is maradjon meg:
      // a helyi piszkozat SZINKRON íródik, a motorba pedig még egyszer
      // megpróbáljuk feltölteni.
      _writeDraftSync(synced: false);
      if (!widget.offline) {
        final doc = _toJson();
        final api = _api;
        final matchId = widget.matchId;
        unawaited(() async {
          try {
            await api.saveAnnotations(matchId, doc);
            _writeDraftSync(synced: true, doc: doc);
          } catch (_) {
            // A helyi piszkozat megvan; a következő megnyitás feltölti.
          }
        }());
      }
    }
    _tabs.dispose();
    _sceneTimeCtrl.dispose();
    _sceneNoteCtrl.dispose();
    _timeCtrl.dispose();
    _jerseyCtrl.dispose();
    _toJerseyCtrl.dispose();
    _noteCtrl.dispose();
    super.dispose();
  }

  // ------------------------------------------------------------------
  // Betöltés és mentés
  // ------------------------------------------------------------------

  String _newId(String prefix) {
    _idSeq += 1;
    return "$prefix${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}$_idSeq";
  }

  File? _draftFile() {
    if (kIsWeb) return null;
    try {
      final safe = widget.matchId.replaceAll(RegExp(r"[^A-Za-z0-9._-]"), "_");
      final sep = Platform.pathSeparator;
      final dir = BackendLauncher.appDataDir().path;
      return File("$dir${sep}annotations$sep$safe.json");
    } catch (_) {
      return null;
    }
  }

  Future<Map<String, dynamic>?> _readDraft() async {
    final f = _draftFile();
    if (f == null) return null;
    try {
      if (!await f.exists()) return null;
      final j = jsonDecode(await f.readAsString());
      return j is Map ? Map<String, dynamic>.from(j) : null;
    } catch (_) {
      return null;
    }
  }

  String _draftJson(bool synced, Map<String, dynamic> doc) => jsonEncode({
        "synced": synced,
        "saved_at": DateTime.now().toUtc().toIso8601String(),
        "doc": doc,
      });

  Future<void> _writeDraft({required bool synced}) async {
    final f = _draftFile();
    if (f == null) return;
    try {
      await f.parent.create(recursive: true);
      await f.writeAsString(_draftJson(synced, _toJson()));
    } catch (_) {}
  }

  void _writeDraftSync({required bool synced, Map<String, dynamic>? doc}) {
    final f = _draftFile();
    if (f == null) return;
    try {
      f.parent.createSync(recursive: true);
      f.writeAsStringSync(_draftJson(synced, doc ?? _toJson()));
    } catch (_) {}
  }

  Future<void> _load() async {
    Map<String, dynamic>? server;
    String? loadError;
    if (!widget.offline) {
      try {
        server = await _api.fetchAnnotations(widget.matchId);
      } catch (e) {
        loadError = humanError(e);
      }
    }
    final local = await _readDraft();
    Map<String, dynamic>? use;
    var unsynced = false;
    final localDoc = local?["doc"];
    if (local != null && local["synced"] != true && localDoc is Map) {
      // A helyi piszkozatban FELTÖLTETLEN munka van — az a frissebb.
      use = Map<String, dynamic>.from(localDoc);
      unsynced = !widget.offline;
    } else if (server != null) {
      use = server;
    } else if (localDoc is Map) {
      use = Map<String, dynamic>.from(localDoc);
    }
    if (!mounted) return;
    final chosen = use;
    final hasServer = server != null;
    setState(() {
      if (chosen != null) _applyDoc(chosen);
      _loading = false;
      _unsynced = unsynced;
      _saveError = (!hasServer && !widget.offline) ? loadError : null;
    });
    if (unsynced) _save();
  }

  void _applyDoc(Map<String, dynamic> d) {
    _status = d["status"] == "done" ? "done" : "in_progress";
    _updatedAt = d["updated_at"] is String ? d["updated_at"] as String : null;
    final ev = d["events"];
    _events = [
      if (ev is List)
        for (final e in ev)
          if (e is Map) _cleanEvent(Map<String, dynamic>.from(e)),
    ];
    final sc = d["scenes"];
    _scenes = [
      if (sc is List)
        for (final s in sc)
          if (s is Map) _Scene.fromJson(Map<String, dynamic>.from(s)),
    ];
    _sortEvents();
    _sceneIndex = _scenes.isEmpty ? -1 : 0;
    _syncSceneCtrls();
  }

  Map<String, dynamic> _cleanEvent(Map<String, dynamic> e) => {
        "id": _str(e["id"]).isEmpty ? _newId("e") : _str(e["id"]),
        "t_s": _toD(e["t_s"], 0),
        "team": _str(e["team"]),
        "type": _str(e["type"]).isEmpty ? "egyéb" : _str(e["type"]),
        "jersey": _str(e["jersey"]),
        "to_jersey": _str(e["to_jersey"]),
        "outcome": _str(e["outcome"]),
        "note": _str(e["note"]),
        "scene_id": _str(e["scene_id"]),
      };

  Map<String, dynamic> _toJson() => {
        "version": 1,
        "match_id": widget.matchId,
        "status": _status,
        "events": _events.map((e) => Map<String, dynamic>.from(e)).toList(),
        "scenes": _scenes.map((s) => s.toJson()).toList(),
      };

  /// Változás jelzése: a hívó setState-en belül hívja. Pár másodperc
  /// csend után magától mentünk.
  void _touch() {
    _rev += 1;
    _dirty = true;
    _unsynced = !widget.offline;
    _autosave?.cancel();
    _autosave = Timer(kAnnAutosave, () {
      _save();
    });
  }

  Future<void> _save() async {
    _autosave?.cancel();
    if (_loading) return;
    if (_saving) {
      _saveAgain = true;
      return;
    }
    setState(() => _saving = true);
    final rev = _rev;
    final doc = _toJson();
    await _writeDraft(synced: false);
    var ok = false;
    String? err;
    if (!widget.offline) {
      try {
        final resp = await _api.saveAnnotations(widget.matchId, doc);
        final u = resp["updated_at"];
        if (u is String) _updatedAt = u;
        ok = true;
      } catch (e) {
        err = humanError(e);
      }
    }
    if (!mounted) {
      _saving = false;
      return;
    }
    final unchanged = _rev == rev;
    setState(() {
      _saving = false;
      if (unchanged) _dirty = false;
      if (widget.offline) {
        _unsynced = false;
        _lastSaved = DateTime.now();
      } else if (ok) {
        if (unchanged) _unsynced = false;
        _lastSaved = DateTime.now();
        _saveError = null;
      } else {
        _unsynced = true;
        _saveError = err;
      }
    });
    if (ok && unchanged) await _writeDraft(synced: true);
    if (_saveAgain || !unchanged) {
      _saveAgain = false;
      _autosave?.cancel();
      _autosave = Timer(const Duration(milliseconds: 600), () {
        _save();
      });
    }
  }

  Future<void> _close() async {
    if (!_loading && (_dirty || _unsynced)) await _save();
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  /// A kézi napló lövései/gólai a motor felismerésével összevetve. Előbb
  /// ment (a motor a mentett naplót veti össze), az eltérés-tételre
  /// kattintva a videó pár másodperccel előtte indul.
  Future<void> _compare() async {
    await _save();
    if (!mounted) return;
    if (_unsynced) {
      _snack("A napló még nincs a motorban (nem érhető el) — az összevetés "
          "akkor megy, amikor a mentés sikerült.");
      return;
    }
    setState(() => _comparing = true);
    Map<String, dynamic>? res;
    String? err;
    try {
      res = await _api.compareAnnotations(widget.matchId);
    } catch (e) {
      err = humanError(e);
    }
    if (!mounted) return;
    setState(() => _comparing = false);
    final r = res;
    if (r == null) {
      _snack("Az összevetés nem sikerült: $err");
      return;
    }
    final seek = await showDialog<double>(
      context: context,
      builder: (ctx) => _CompareDialog(
        res: r,
        homeName: widget.homeName,
        awayName: widget.awayName,
        canSeek: _hasVideo,
      ),
    );
    if (seek != null && mounted) {
      _seekVideo(math.max(0.0, seek - kAnnCompareLeadS));
    }
  }

  Future<void> _exportCsv() async {
    await _save();
    if (_unsynced) {
      _snack("A napló még nincs a motorban (nem érhető el) — az export "
          "akkor megy, amikor a mentés sikerült.");
      return;
    }
    try {
      final bytes = await _api.fetchAnnotationsCsv(widget.matchId);
      final name = "${widget.homeName}_${widget.awayName}"
          .replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Kézi napló mentése (CSV)",
        fileName: "kezi_elemzes_$name.csv",
        type: FileType.custom,
        allowedExtensions: const ["csv"],
      );
      if (path == null) return;
      await File(path).writeAsBytes(bytes);
      _snack("Kézi napló mentve: $path — Excelben nyitható");
    } catch (e) {
      _snack("Export-hiba: ${humanError(e)}");
    }
  }

  void _snack(String msg, {SnackBarAction? action}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg), action: action));
  }

  // ------------------------------------------------------------------
  // Események
  // ------------------------------------------------------------------

  bool _hasOutcome(String type) => type == "lövés" || type == "hetes";

  void _sortEvents() {
    // Stabil rendezés idő szerint (az azonos idejűek sorrendje marad).
    final indexed = [for (var i = 0; i < _events.length; i++) MapEntry(i, _events[i])];
    indexed.sort((a, b) {
      final c = _toD(a.value["t_s"], 0).compareTo(_toD(b.value["t_s"], 0));
      return c != 0 ? c : a.key.compareTo(b.key);
    });
    _events = [for (final e in indexed) e.value];
  }

  void _submitEvent() {
    final t = parseAnnTime(_timeCtrl.text);
    if (t == null) {
      _snack("Az időt pp:mm alakban add meg (pl. 12:40), vagy másodpercben.");
      return;
    }
    final e = <String, dynamic>{
      "id": _editingEventId ?? _newId("e"),
      "t_s": (t * 10).roundToDouble() / 10,
      "team": _formTeam,
      "type": _formType,
      "jersey": _jerseyCtrl.text.trim(),
      "to_jersey": _formType == "passz" ? _toJerseyCtrl.text.trim() : "",
      "outcome": _hasOutcome(_formType) ? _formOutcome : "",
      "note": _noteCtrl.text.trim(),
      "scene_id": _formSceneId,
    };
    setState(() {
      final editing = _editingEventId;
      if (editing != null) {
        final i = _events.indexWhere((x) => x["id"] == editing);
        if (i >= 0) {
          _events[i] = e;
        } else {
          _events.add(e);
        }
      } else {
        _events.add(e);
      }
      _sortEvents();
      _editingEventId = null;
      _jerseyCtrl.clear();
      _toJerseyCtrl.clear();
      _noteCtrl.clear();
      _touch();
    });
  }

  /// Gyors rögzítés: egy kattintás = egy esemény a videó mostani idejével
  /// (videó nélkül az idő-mezőével), a kijelölt csapatnak; ha a mez-mezőbe
  /// már írtál, az is bekerül. Utólag a naplóban szerkeszthető.
  void _quickEvent(String type, String outcome) {
    final t = _videoNow ?? parseAnnTime(_timeCtrl.text) ?? widget.startSeconds;
    final e = <String, dynamic>{
      "id": _newId("e"),
      "t_s": (t * 10).roundToDouble() / 10,
      "team": _formTeam,
      "type": type,
      "jersey": _jerseyCtrl.text.trim(),
      "to_jersey": "",
      "outcome": _hasOutcome(type) ? outcome : "",
      "note": "",
      "scene_id": "",
    };
    setState(() {
      _events.add(e);
      _sortEvents();
      if (_editingEventId == null) _jerseyCtrl.clear();
      _touch();
    });
    if (!mounted) return;
    final team = _formTeam == "home" ? widget.homeName : widget.awayName;
    final m = ScaffoldMessenger.of(context);
    m.hideCurrentSnackBar();
    m.showSnackBar(SnackBar(
      duration: const Duration(seconds: 2),
      content: Text("Rögzítve: ${formatAnnTime(t)} · $type"
          "${outcome.isEmpty ? "" : " ($outcome)"} · $team"),
      action: SnackBarAction(label: "Szerkesztés", onPressed: () => _startEdit(e)),
    ));
  }

  Widget _quickRow() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          _videoOn
              ? "GYORS RÖGZÍTÉS — a videó idejével, a kijelölt csapatnak"
              : "GYORS RÖGZÍTÉS — az idő-mező idejével, a kijelölt csapatnak",
          style: AppText.label.copyWith(fontSize: 10.5),
        ),
        const SizedBox(height: 4),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final q in kAnnQuickEvents)
              ActionChip(
                visualDensity: VisualDensity.compact,
                label: Text(q.$1, style: const TextStyle(fontSize: 12)),
                avatar: Icon(
                    q.$3 == "gól"
                        ? Icons.sports_score
                        : q.$2 == "lövés"
                            ? Icons.sports_handball
                            : Icons.bolt,
                    size: 14,
                    color: _formTeam == "home" ? AppColors.home : AppColors.away),
                onPressed: () => _quickEvent(q.$2, q.$3),
              ),
          ],
        ),
      ],
    );
  }

  void _startEdit(Map<String, dynamic> e) {
    setState(() {
      _editingEventId = _str(e["id"]);
      _timeCtrl.text = formatAnnTime(_toD(e["t_s"], 0));
      _formTeam = e["team"] == "away" ? "away" : "home";
      final type = _str(e["type"]);
      _formType = kAnnEventTypes.contains(type) ? type : "egyéb";
      _jerseyCtrl.text = _str(e["jersey"]);
      _toJerseyCtrl.text = _str(e["to_jersey"]);
      final out = _str(e["outcome"]);
      _formOutcome = kAnnShotOutcomes.contains(out) ? out : "";
      _noteCtrl.text = _str(e["note"]);
      final sid = _str(e["scene_id"]);
      _formSceneId = _sceneById(sid) != null ? sid : "";
    });
    if (!_wide) _tabs.animateTo(1);
  }

  void _cancelEdit() {
    setState(() {
      _editingEventId = null;
      _jerseyCtrl.clear();
      _toJerseyCtrl.clear();
      _noteCtrl.clear();
      _formOutcome = "";
    });
  }

  void _deleteEvent(Map<String, dynamic> e) {
    final i = _events.indexOf(e);
    if (i < 0) return;
    setState(() {
      _events.removeAt(i);
      if (_editingEventId == _str(e["id"])) _editingEventId = null;
      _touch();
    });
    _snack(
      "Esemény törölve (${formatAnnTime(_toD(e["t_s"], 0))} ${_str(e["type"])}).",
      action: SnackBarAction(
        label: "Visszavonás",
        onPressed: () {
          if (!mounted) return;
          setState(() {
            _events.insert(math.min(i, _events.length), e);
            _sortEvents();
            _touch();
          });
        },
      ),
    );
  }

  /// A kijelölt tábla utolsó passz-nyilából esemény-javaslat: idő, csapat,
  /// passzoló és címzett — az edzőnek csak rá kell néznie.
  void _eventFromScene() {
    final s = _scene;
    if (s == null) return;
    setState(() {
      _editingEventId = null;
      _timeCtrl.text = formatAnnTime(s.tS ?? widget.startSeconds);
      _formSceneId = s.id;
      _Arrow? last;
      for (final a in s.arrows.reversed) {
        if (a.kind == "pass") {
          last = a;
          break;
        }
      }
      if (last != null) {
        final from = _tokenById(s, last.from);
        final to = _tokenById(s, last.to);
        _formType = "passz";
        if (from != null) {
          _formTeam = from.team == "away" ? "away" : "home";
          _jerseyCtrl.text = from.label;
        }
        _toJerseyCtrl.text = to?.label ?? "";
      }
    });
    if (!_wide) _tabs.animateTo(1);
  }

  // ------------------------------------------------------------------
  // Táblák
  // ------------------------------------------------------------------

  _Scene? get _scene =>
      (_sceneIndex >= 0 && _sceneIndex < _scenes.length) ? _scenes[_sceneIndex] : null;

  _Scene? _sceneById(String id) {
    if (id.isEmpty) return null;
    for (final s in _scenes) {
      if (s.id == id) return s;
    }
    return null;
  }

  _Token? _tokenById(_Scene s, String id) {
    if (id.isEmpty) return null;
    for (final t in s.tokens) {
      if (t.id == id) return t;
    }
    return null;
  }

  void _syncSceneCtrls() {
    final s = _scene;
    _sceneTimeCtrl.text = s?.tS == null ? "" : formatAnnTime(s!.tS!);
    _sceneNoteCtrl.text = s?.note ?? "";
    _pendingFrom = null;
    _selected = null;
  }

  /// Alap-felállás: a hazai a jobb kapura támad (irányító, két átlövő, két
  /// szélső, beálló + kapus), a vendég 6-0-s fallal véd.
  List<_Token> _defaultTokens() {
    _Token h(String id, String label, double x, double y) =>
        _Token(id: id, team: "home", label: label, x: x, y: y);
    _Token a(String id, String label, double x, double y) =>
        _Token(id: id, team: "away", label: label, x: x, y: y);
    return [
      h("h_k", "K", 2.0, 10.0),
      h("h_bsz", "BSZ", 30.0, 1.5),
      h("h_ba", "BÁ", 26.5, 5.0),
      h("h_ir", "IR", 25.5, 10.0),
      h("h_ja", "JÁ", 26.5, 15.0),
      h("h_jsz", "JSZ", 30.0, 18.5),
      // A beálló a két középső védő KÖZÖTT, a 6 m-es vonalon: a bábuk
      // (0,8 m sugár) nem fedhetik egymást — korábban a "4" eltakarta.
      h("h_be", "BE", 33.8, 10.0),
      a("a_k", "K", 38.8, 10.0),
      a("a_1", "1", 34.3, 3.0),
      a("a_2", "2", 33.1, 6.0),
      a("a_3", "3", 32.3, 8.6),
      a("a_4", "4", 32.3, 11.4),
      a("a_5", "5", 33.1, 14.0),
      a("a_6", "6", 34.3, 17.0),
      _Token(id: "ball", team: "ball", label: "", x: 26.3, y: 10.6),
    ];
  }

  void _addScene({bool continueCurrent = false}) {
    if (_scenes.length >= 300) {
      _snack("Legfeljebb 300 tábla menthető egy meccshez.");
      return;
    }
    final cur = _scene;
    final tokens = (continueCurrent && cur != null)
        ? cur.tokens.map((t) => t.copy()).toList()
        : _defaultTokens();
    final s = _Scene(
      id: _newId("s"),
      name: continueCurrent && cur != null
          ? "${cur.name} (folytatás)"
          : "Tábla ${_scenes.length + 1}",
      tS: continueCurrent && cur != null ? cur.tS : widget.startSeconds,
      tokens: tokens,
      arrows: [],
    );
    setState(() {
      final at = continueCurrent && cur != null ? _sceneIndex + 1 : _scenes.length;
      _scenes.insert(at, s);
      _sceneIndex = at;
      _syncSceneCtrls();
      _touch();
    });
  }

  Future<void> _renameScene() async {
    final s = _scene;
    if (s == null) return;
    final ctrl = TextEditingController(text: s.name);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Tábla neve"),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          maxLength: 80,
          decoration: const InputDecoration(hintText: "pl. 12:40 kereszt balra"),
          onSubmitted: (v) => Navigator.of(ctx).pop(v),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text("Mégse")),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ctrl.text), child: const Text("Mentés")),
        ],
      ),
    );
    ctrl.dispose();
    if (name == null || name.trim().isEmpty || !mounted) return;
    setState(() {
      s.name = name.trim();
      _touch();
    });
  }

  Future<void> _deleteScene() async {
    final s = _scene;
    if (s == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Tábla törlése"),
        content: Text("Biztosan törlöd a(z) \"${s.name}\" táblát? A hozzá kötött "
            "események megmaradnak, csak a tábla-hivatkozásuk törlődik."),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text("Mégse")),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text("Törlés")),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() {
      _scenes.remove(s);
      for (final e in _events) {
        if (e["scene_id"] == s.id) e["scene_id"] = "";
      }
      if (_formSceneId == s.id) _formSceneId = "";
      _sceneIndex = _scenes.isEmpty
          ? -1
          : math.min(math.max(_sceneIndex, 0), _scenes.length - 1);
      _syncSceneCtrls();
      _touch();
    });
  }

  void _selectScene(int i) {
    setState(() {
      _sceneIndex = i;
      _syncSceneCtrls();
    });
  }

  void _openSceneOfEvent(Map<String, dynamic> e) {
    final sid = _str(e["scene_id"]);
    final i = _scenes.indexWhere((s) => s.id == sid);
    if (i < 0) return;
    _selectScene(i);
    if (!_wide) _tabs.animateTo(0);
  }

  /// A felismert pozíciók a tábla idejében (vagy a meccs-nézet idejében):
  /// a bábuk a valódi helyükről indulnak, az edző csak igazít.
  Future<void> _fillFromMatch() async {
    final s = _scene;
    final m = widget.match;
    if (s == null || m == null || m.frames.isEmpty) {
      _snack("Ehhez a meccshez nincsenek felismert pozíciók.");
      return;
    }
    if (s.arrows.isNotEmpty) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text("Pozíciók a meccsből"),
          content: const Text("A bábuk a felismert helyükre kerülnek, a tábla "
              "nyilai törlődnek. Folytatod?"),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text("Mégse")),
            FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text("Igen")),
          ],
        ),
      );
      if (ok != true || !mounted) return;
    }
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    // Videó-másodperc → tracking-kocka: a feldolgozás a videó
    // startFrame-jétől indult (a videoSecondsOfFrame fordítottja).
    final offsetS = m.meta.startFrame / (fps * math.max(1, m.meta.stride));
    final target = ((s.tS ?? widget.startSeconds) - offsetS) * fps;
    Frame best = m.frames.first;
    var bestD = double.infinity;
    for (final f in m.frames) {
      final d = (f.t - target).abs();
      if (d < bestD) {
        bestD = d;
        best = f;
      }
    }
    final tokens = <_Token>[];
    for (final team in [Team.home, Team.away]) {
      var n = 0;
      for (final p in best.players) {
        if (p.team != team || n >= 9) continue;
        n += 1;
        final isGk = p.role == "kapus";
        tokens.add(_Token(
          id: "${team == Team.home ? "h" : "a"}${p.trackId}",
          team: team == Team.home ? "home" : "away",
          label: isGk ? "K" : (p.jerseyNumber?.toString() ?? ""),
          x: p.x.clamp(0.0, courtLength).toDouble(),
          y: p.y.clamp(0.0, courtWidth).toDouble(),
        ));
      }
    }
    final b = best.ball;
    tokens.add(_Token(
      id: "ball",
      team: "ball",
      label: "",
      x: (b?.x ?? courtLength / 2).clamp(0.0, courtLength).toDouble(),
      y: (b?.y ?? courtWidth / 2).clamp(0.0, courtWidth).toDouble(),
    ));
    setState(() {
      s.tokens = tokens.take(kAnnMaxTokens).toList();
      s.arrows = [];
      _pendingFrom = null;
      _selected = null;
      _touch();
    });
    _snack("Bábuk a felismert helyükön (${formatAnnTime(best.t / fps)}) — "
        "húzással igazíthatók.");
  }

  void _addToken(String team) {
    final s = _scene;
    if (s == null) return;
    if (s.tokens.length >= kAnnMaxTokens) {
      _snack("Egy táblán legfeljebb $kAnnMaxTokens bábu lehet.");
      return;
    }
    final n = s.tokens.where((t) => t.team == team).length + 1;
    setState(() {
      s.tokens.add(_Token(
        id: _newId(team == "home" ? "h" : "a"),
        team: team,
        label: "$n",
        x: team == "home" ? 18.0 : 22.0,
        y: 10.0,
      ));
      _touch();
    });
  }

  Future<void> _tokenMenu(_Token t) async {
    final s = _scene;
    if (s == null) return;
    if (t.team == "ball") return;
    final ctrl = TextEditingController(text: t.label);
    final res = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t.team == "home" ? "Hazai bábu" : "Vendég bábu"),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          maxLength: 4,
          decoration: const InputDecoration(
              labelText: "Felirat", hintText: "mezszám vagy poszt (pl. 7, IR)"),
          onSubmitted: (v) => Navigator.of(ctx).pop("label:$v"),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop("delete"),
            child: const Text("Bábu törlése", style: TextStyle(color: AppColors.away)),
          ),
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text("Mégse")),
          FilledButton(
              onPressed: () => Navigator.of(ctx).pop("label:${ctrl.text}"),
              child: const Text("Mentés")),
        ],
      ),
    );
    ctrl.dispose();
    if (res == null || !mounted) return;
    setState(() {
      if (res == "delete") {
        s.tokens.remove(t);
        s.arrows.removeWhere((a) => a.from == t.id || a.to == t.id);
        if (_pendingFrom == t.id) _pendingFrom = null;
      } else if (res.startsWith("label:")) {
        final v = res.substring(6).trim();
        t.label = v.length > 4 ? v.substring(0, 4) : v;
      }
      _touch();
    });
  }

  _Token? _hitToken(_Scene s, Offset p, {bool ballLast = true}) {
    _Token? best;
    var bestD = 1.4; // méter
    for (final t in s.tokens) {
      final d = (Offset(t.x, t.y) - p).distance;
      // A labda a játékos alatt van — a játékos nyerjen, ha átfednek.
      final penalty = (ballLast && t.team == "ball") ? 0.5 : 0.0;
      if (d + penalty < bestD) {
        bestD = d + penalty;
        best = t;
      }
    }
    return best;
  }

  Offset _clampCourt(Offset p) => Offset(
        p.dx.clamp(0.0, courtLength).toDouble(),
        p.dy.clamp(0.0, courtWidth).toDouble(),
      );

  void _onTapUp(TapUpDetails d, Size size) {
    final s = _scene;
    if (s == null) return;
    final tr = _boardTr(size);
    final p = _clampCourt(tr.toCourt(d.localPosition.dx, d.localPosition.dy));
    final hit = _hitToken(s, p);
    if (_tool == _Tool.move) {
      setState(() => _selected = hit?.id);
      return;
    }
    final from = _pendingFrom;
    if (from == null) {
      if (hit != null && hit.team != "ball") {
        setState(() => _pendingFrom = hit.id);
      }
      return;
    }
    if (hit != null && hit.id == from) {
      setState(() => _pendingFrom = null);
      return;
    }
    if (s.arrows.length >= kAnnMaxArrows) {
      _snack("Egy táblán legfeljebb $kAnnMaxArrows nyíl lehet — kezdj új táblát "
          "(\"Folytatás\").");
      return;
    }
    final kind = _tool == _Tool.pass ? "pass" : _tool == _Tool.run ? "run" : "shot";
    setState(() {
      if (_tool == _Tool.pass && hit != null && hit.team != "ball") {
        s.arrows.add(_Arrow(kind: kind, from: from, to: hit.id));
        // A labda a címzetthez kerül — a következő passz onnan indul.
        _Token? ball;
        for (final t in s.tokens) {
          if (t.team == "ball") {
            ball = t;
            break;
          }
        }
        if (ball != null) {
          ball.x = (hit.x + 0.6).clamp(0.0, courtLength).toDouble();
          ball.y = (hit.y + 0.6).clamp(0.0, courtWidth).toDouble();
        }
        // A passzoló a címzett lesz: egymás után jöhet a következő passz.
        _pendingFrom = hit.id;
      } else {
        s.arrows.add(_Arrow(kind: kind, from: from, to: "", x: p.dx, y: p.dy));
        _pendingFrom = null;
      }
      _touch();
    });
  }

  void _onPanStart(DragStartDetails d, Size size) {
    final s = _scene;
    if (s == null) return;
    final tr = _boardTr(size);
    final p = tr.toCourt(d.localPosition.dx, d.localPosition.dy);
    final hit = _hitToken(s, p, ballLast: false);
    _dragId = hit?.id;
    // Nagyítva az üres helyről indított húzás a táblát mozgatja.
    _panningBoard = hit == null && _boardZoom > 1.0;
    if (hit != null) setState(() => _selected = hit.id);
  }

  void _onPanUpdate(DragUpdateDetails d, Size size) {
    if (_panningBoard) {
      _panBoard(d.delta, size);
      return;
    }
    final s = _scene;
    final id = _dragId;
    if (s == null || id == null) return;
    final t = _tokenById(s, id);
    if (t == null) return;
    final tr = _boardTr(size);
    final p = _clampCourt(tr.toCourt(d.localPosition.dx, d.localPosition.dy));
    setState(() {
      t.x = p.dx;
      t.y = p.dy;
      _touch();
    });
  }

  void _onLongPress(LongPressStartDetails d, Size size) {
    final s = _scene;
    if (s == null) return;
    final tr = _boardTr(size);
    final p = tr.toCourt(d.localPosition.dx, d.localPosition.dy);
    final hit = _hitToken(s, p);
    if (hit != null) _tokenMenu(hit);
  }

  void _undoArrow() {
    final s = _scene;
    if (s == null || s.arrows.isEmpty) return;
    setState(() {
      s.arrows.removeLast();
      _pendingFrom = null;
      _touch();
    });
  }

  Future<void> _clearArrows() async {
    final s = _scene;
    if (s == null || s.arrows.isEmpty) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Nyilak törlése"),
        content: Text("A tábla mind a(z) ${s.arrows.length} nyila törlődik "
            "(a bábuk a helyükön maradnak)."),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text("Mégse")),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text("Törlés")),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() {
      s.arrows.clear();
      _pendingFrom = null;
      _touch();
    });
  }

  // ------------------------------------------------------------------
  // Felület
  // ------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _header(),
              const SizedBox(height: AppSpacing.md),
              Expanded(
                child: _loading
                    ? const WaitingView("A kézi elemzés betöltése…",
                        hint: "a mentett napló és táblák — pár másodperc",
                        icon: Icons.edit_note)
                    : LayoutBuilder(builder: (ctx, cons) {
                        _wide = cons.maxWidth >= 1000;
                        if (_wide) {
                          // Széles ablak: a videó a tábla FÖLÖTT, a napló
                          // teljes magasságban mellette (az űrlap hosszú).
                          return Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Expanded(child: _withVideo(_boardCard())),
                              const SizedBox(width: AppSpacing.lg),
                              SizedBox(width: 430, child: _logCard()),
                            ],
                          );
                        }
                        return _withVideo(Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            TabBar(
                              controller: _tabs,
                              labelColor: AppColors.accent,
                              unselectedLabelColor: AppColors.textSecondary,
                              indicatorColor: AppColors.accent,
                              tabs: const [
                                Tab(text: "Taktikai tábla"),
                                Tab(text: "Esemény-napló"),
                              ],
                            ),
                            const SizedBox(height: AppSpacing.sm),
                            Expanded(
                              child: TabBarView(
                                controller: _tabs,
                                // A pályán a húzás a bábué, ne lapozzon.
                                physics: const NeverScrollableScrollPhysics(),
                                children: [_boardCard(), _logCard()],
                              ),
                            ),
                          ],
                        ));
                      }),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// A videó-sáv a munkaterület fölött, köztük húzható elválasztóval.
  Widget _withVideo(Widget below) {
    if (!_videoOn) return below;
    return LayoutBuilder(builder: (ctx, cons) {
      final total = cons.maxHeight;
      final videoH = (total * _videoFrac)
          .clamp(120.0, math.max(120.0, total - 220.0))
          .toDouble();
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: videoH,
            child: VideoPanel(
              key: _videoKey,
              videoPath: widget.match!.meta.videoPath!,
              initialSeconds: _lastVideoS ?? widget.startSeconds,
              zoomButtons: true,
              hint: "Szóköz: lejátszás · ←/→: 2 mp (Shift: 10 mp) · T: idő "
                  "a naplóba · nagyítás: csippentés, Ctrl/⌘+görgő, gombok",
            ),
          ),
          _videoSplitter(total),
          Expanded(child: below),
        ],
      );
    });
  }

  /// Húzható elválasztó a videó és a tábla között (dupla kattintás:
  /// alap-arány).
  Widget _videoSplitter(double total) {
    return MouseRegion(
      cursor: SystemMouseCursors.resizeRow,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onVerticalDragUpdate: (d) => setState(() {
          if (total <= 0) return;
          _videoFrac = (_videoFrac + d.delta.dy / total)
              .clamp(kAnnVideoMinFrac, kAnnVideoMaxFrac)
              .toDouble();
        }),
        onDoubleTap: () => setState(() => _videoFrac = kAnnVideoFrac),
        child: Tooltip(
          message: "Húzd a videó-sáv átméretezéséhez",
          waitDuration: const Duration(milliseconds: 600),
          child: SizedBox(
            height: 16,
            child: Center(
              child: Container(
                width: 56,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.border,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _header() {
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        IconButton(
          onPressed: _close,
          tooltip: "Vissza (a munka mentésével)",
          icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
        ),
        const Text("KÉZI ELEMZÉS", style: AppText.brand),
        Text("· ${widget.homeName} – ${widget.awayName}", style: AppText.label),
        const SizedBox(width: AppSpacing.lg),
        _saveChip(),
        if (_hasVideo)
          FilterChip(
            avatar: const Icon(Icons.movie_outlined, size: 16),
            label: const Text("Videó"),
            tooltip: "A meccs videója a tábla fölött (nagyítható)",
            selected: _showVideo,
            onSelected: (v) => setState(() {
              if (!v) {
                _lastVideoS =
                    _videoKey.currentState?.positionSeconds ?? _lastVideoS;
              }
              _showVideo = v;
            }),
          ),
        FilterChip(
          label: const Text("Kész"),
          tooltip: "Jelöld késznek, ha végeztél — addig félkészként menthető",
          selected: _status == "done",
          onSelected: _loading
              ? null
              : (v) => setState(() {
                    _status = v ? "done" : "in_progress";
                    _touch();
                  }),
        ),
        OutlinedButton.icon(
          onPressed:
              (_loading || widget.offline || _comparing) ? null : _compare,
          icon: _comparing
              ? const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.fact_check_outlined, size: 16),
          label: Text(_comparing ? "Összevetés…" : "Összevetés a géppel"),
        ),
        OutlinedButton.icon(
          onPressed: (_loading || widget.offline) ? null : _exportCsv,
          icon: const Icon(Icons.table_chart_outlined, size: 16),
          label: const Text("Napló CSV-ben"),
        ),
        FilledButton.icon(
          onPressed: (_loading || _saving) ? null : _save,
          style: FilledButton.styleFrom(
              backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
          icon: const Icon(Icons.save_outlined, size: 18),
          label: const Text("Mentés"),
        ),
      ],
    );
  }

  Widget _saveChip() {
    final String text;
    final Color color;
    if (_saving) {
      text = "Mentés…";
      color = AppColors.textSecondary;
    } else if (_dirty) {
      text = "Nem mentett változás";
      color = AppColors.gold;
    } else if (widget.offline) {
      text = "Helyben mentve (motor nélkül)";
      color = AppColors.textSecondary;
    } else if (_unsynced) {
      text = "Helyben mentve — a motor most nem érhető el";
      color = AppColors.gold;
    } else if (_lastSaved != null) {
      final t = _lastSaved!;
      text = "Mentve · ${t.hour.toString().padLeft(2, "0")}:"
          "${t.minute.toString().padLeft(2, "0")}";
      color = AppColors.accent;
    } else if (_updatedAt != null) {
      text = "Mentve";
      color = AppColors.accent;
    } else {
      text = "Még üres — a munka magától mentődik";
      color = AppColors.textFaint;
    }
    final chip = Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.6)),
      ),
      child: Text(text, style: AppText.label.copyWith(color: color, fontSize: 12)),
    );
    final err = _saveError;
    return err == null ? chip : Tooltip(message: err, child: chip);
  }

  // --- tábla ---

  Widget _boardCard() {
    final s = _scene;
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _sceneBar(),
          const SizedBox(height: AppSpacing.sm),
          if (s == null)
            Expanded(
              child: Center(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  const Icon(Icons.sports_handball, size: 40, color: AppColors.textFaint),
                  const SizedBox(height: AppSpacing.md),
                  Text("Még nincs taktikai tábla. Egy tábla egy pálya-helyzet:\n"
                      "húzd a bábukat a helyükre, és rajzold be a passzokat.",
                      textAlign: TextAlign.center, style: AppText.label),
                  const SizedBox(height: AppSpacing.md),
                  FilledButton.icon(
                    onPressed: () => _addScene(),
                    style: FilledButton.styleFrom(
                        backgroundColor: AppColors.accent,
                        foregroundColor: AppColors.onAccent),
                    icon: const Icon(Icons.add),
                    label: const Text("Első tábla létrehozása"),
                  ),
                ]),
              ),
            )
          else ...[
            _toolBar(s),
            const SizedBox(height: AppSpacing.sm),
            Expanded(child: _boardCanvas(s)),
            const SizedBox(height: AppSpacing.xs),
            Text(_toolHint(), style: AppText.label.copyWith(fontSize: 11)),
            const SizedBox(height: AppSpacing.sm),
            _sceneFooter(s),
          ],
        ],
      ),
    );
  }

  String _toolHint() {
    switch (_tool) {
      case _Tool.move:
        return "Mozgatás: húzd a bábut (a labdát is). Hosszan nyomva: felirat "
            "(mezszám) vagy törlés.";
      case _Tool.pass:
        return _pendingFrom == null
            ? "Passz: koppints a passzolóra, majd a társra (vagy üres helyre)."
            : "Passz: most a címzettre koppints — utána onnan folytathatod.";
      case _Tool.run:
        return _pendingFrom == null
            ? "Futás: koppints a futó játékosra, majd oda, ahová fut."
            : "Futás: koppints a cél-pontra.";
      case _Tool.shot:
        return _pendingFrom == null
            ? "Lövés: koppints a lövőre, majd a kapura."
            : "Lövés: koppints a kapu felé, ahová a lövés megy.";
    }
  }

  Widget _sceneBar() {
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.xs,
      children: [
        Text("TAKTIKAI TÁBLA", style: AppText.sectionLabel),
        if (_scenes.isNotEmpty)
          DropdownButton<int>(
            value: _sceneIndex < 0 ? null : _sceneIndex,
            dropdownColor: AppColors.surface,
            underline: const SizedBox.shrink(),
            items: [
              for (var i = 0; i < _scenes.length; i++)
                DropdownMenuItem<int>(
                  value: i,
                  child: Text(
                    "${i + 1}. ${_scenes[i].name}"
                    "${_scenes[i].tS == null ? "" : " · ${formatAnnTime(_scenes[i].tS!)}"}",
                    style: AppText.value.copyWith(fontSize: 13),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
            onChanged: (i) {
              if (i != null) _selectScene(i);
            },
          ),
        IconButton(
          onPressed: () => _addScene(),
          tooltip: "Új tábla (alap-felállással)",
          icon: const Icon(Icons.add_box_outlined, color: AppColors.accent),
        ),
        if (_scene != null) ...[
          IconButton(
            onPressed: () => _addScene(continueCurrent: true),
            tooltip: "Folytatás: új tábla a mostani bábu-helyekről (nyilak nélkül)",
            icon: const Icon(Icons.skip_next_outlined, color: AppColors.accent),
          ),
          IconButton(
            onPressed: _renameScene,
            tooltip: "Tábla átnevezése",
            icon: const Icon(Icons.edit_outlined, color: AppColors.textSecondary),
          ),
          IconButton(
            onPressed: _deleteScene,
            tooltip: "Tábla törlése",
            icon: const Icon(Icons.delete_outline, color: AppColors.textSecondary),
          ),
        ],
      ],
    );
  }

  Widget _toolBar(_Scene s) {
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.xs,
      children: [
        SegmentedButton<_Tool>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: _Tool.move, icon: Icon(Icons.open_with, size: 16), label: Text("Mozgatás")),
            ButtonSegment(value: _Tool.pass, icon: Icon(Icons.east, size: 16), label: Text("Passz")),
            ButtonSegment(value: _Tool.run, icon: Icon(Icons.directions_run, size: 16), label: Text("Futás")),
            ButtonSegment(value: _Tool.shot, icon: Icon(Icons.sports_handball, size: 16), label: Text("Lövés")),
          ],
          selected: {_tool},
          onSelectionChanged: (v) => setState(() {
            _tool = v.first;
            _pendingFrom = null;
          }),
        ),
        IconButton(
          onPressed: s.arrows.isEmpty ? null : _undoArrow,
          tooltip: "Utolsó nyíl visszavonása",
          icon: const Icon(Icons.undo, color: AppColors.textSecondary),
        ),
        IconButton(
          onPressed: s.arrows.isEmpty ? null : _clearArrows,
          tooltip: "Minden nyíl törlése",
          icon: const Icon(Icons.layers_clear_outlined, color: AppColors.textSecondary),
        ),
        IconButton(
          onPressed: () => _addToken("home"),
          tooltip: "Hazai bábu hozzáadása",
          icon: const Icon(Icons.person_add_alt, color: AppColors.home),
        ),
        IconButton(
          onPressed: () => _addToken("away"),
          tooltip: "Vendég bábu hozzáadása",
          icon: const Icon(Icons.person_add_alt, color: AppColors.away),
        ),
        if (widget.match != null && widget.match!.frames.isNotEmpty)
          OutlinedButton.icon(
            onPressed: _fillFromMatch,
            icon: const Icon(Icons.my_location, size: 16),
            label: const Text("Pozíciók a meccsből"),
          ),
      ],
    );
  }

  /// A pálya-rajz. Nagyítható: MacBook-touchpad csippentés (két ujjas
  /// húzás: mozgatás), Ctrl/⌘+görgő, vagy a sarok-gombok; nagyítva az
  /// üres helyről húzás és a sima görgő is mozgatja. A bábuk húzása
  /// közben ugyanúgy működik — a touchpad-gesztusok (csippentés, két
  /// ujjas húzás) NEM érik el a bábu-húzást, azokat a Listener kapja.
  Widget _boardCanvas(_Scene s) {
    return LayoutBuilder(builder: (ctx, cons) {
      final size = Size(cons.maxWidth, cons.maxHeight);
      // Ablak-átméretezés után is maradjon a pályán az eltolás.
      _boardPan = _clampBoardPan(_boardPan, size);
      final moving = _tool == _Tool.move;
      final zoomed = _boardZoom > 1.01;
      final board = Listener(
        onPointerSignal: (e) {
          if (e is! PointerScrollEvent) return;
          final kb = HardwareKeyboard.instance;
          if (kb.isControlPressed || kb.isMetaPressed) {
            _zoomBoard(e.localPosition, math.exp(-e.scrollDelta.dy / 240.0), size);
          } else {
            _panBoard(-e.scrollDelta, size);
          }
        },
        onPointerPanZoomStart: (_) => _pinchLast = 1.0,
        onPointerPanZoomUpdate: (e) {
          final factor = e.scale / _pinchLast;
          _pinchLast = e.scale;
          if ((factor - 1.0).abs() > 1e-4) {
            _zoomBoard(e.localPosition, factor, size);
          }
          if (e.localPanDelta != Offset.zero) _panBoard(e.localPanDelta, size);
        },
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          // A touchpad-gesztus a Listeneré (nagyítás/mozgatás), ne húzzon
          // bábut; a touchpad-KATTINTÁS egér-eseményként érkezik.
          supportedDevices: const {
            PointerDeviceKind.touch,
            PointerDeviceKind.mouse,
            PointerDeviceKind.stylus,
            PointerDeviceKind.invertedStylus,
            PointerDeviceKind.unknown,
          },
          onTapUp: (d) => _onTapUp(d, size),
          onLongPressStart: (d) => _onLongPress(d, size),
          onPanStart: moving ? (d) => _onPanStart(d, size) : null,
          onPanUpdate: moving ? (d) => _onPanUpdate(d, size) : null,
          onPanEnd: moving
              ? (_) {
                  _dragId = null;
                  _panningBoard = false;
                }
              : null,
          child: ClipRect(
            child: CustomPaint(
              size: size,
              painter: _BoardPainter(
                scene: s,
                selected: _selected,
                pending: _pendingFrom,
                rev: _rev,
                zoom: _boardZoom,
                pan: _boardPan,
              ),
            ),
          ),
        ),
      );
      final center = Offset(size.width / 2, size.height / 2);
      // A gombok a gesztus-figyelőn KÍVÜL: a kattintásuk ne legyen
      // pálya-koppintás (nyíl-rajzolás, kijelölés).
      return Stack(children: [
        Positioned.fill(child: board),
        Positioned(
          right: 4,
          top: 4,
          child: Container(
            decoration: BoxDecoration(
              color: AppColors.surface.withOpacity(0.82),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: "Tábla nagyítása (csippentés, Ctrl/⌘+görgő)",
                onPressed: _boardZoom >= kAnnBoardMaxZoom - 0.01
                    ? null
                    : () => _zoomBoard(center, 1.4142, size),
                icon: const Icon(Icons.zoom_in, size: 18),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: "Tábla kicsinyítése",
                onPressed:
                    zoomed ? () => _zoomBoard(center, 1 / 1.4142, size) : null,
                icon: const Icon(Icons.zoom_out, size: 18),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: "Teljes pálya (1×)",
                onPressed: zoomed ? _resetBoardZoom : null,
                icon: const Icon(Icons.fit_screen, size: 18),
              ),
              if (zoomed)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Text("×${_boardZoom.toStringAsFixed(1)}",
                      style: AppText.label.copyWith(fontSize: 11)),
                ),
            ]),
          ),
        ),
      ]);
    });
  }

  Widget _sceneFooter(_Scene s) {
    return Row(
      children: [
        SizedBox(
          width: 90,
          child: TextField(
            controller: _sceneTimeCtrl,
            style: AppText.value.copyWith(fontSize: 13),
            decoration: const InputDecoration(
                isDense: true, labelText: "Idő", hintText: "pp:mm"),
            onChanged: (v) {
              final t = parseAnnTime(v);
              setState(() {
                s.tS = v.trim().isEmpty ? null : t ?? s.tS;
                _touch();
              });
            },
          ),
        ),
        if (_videoOn)
          IconButton(
            onPressed: () => _takeVideoTime(_sceneTimeCtrl, scene: s),
            tooltip: "Idő a videóból (a lejátszó mostani helye)",
            icon: const Icon(Icons.videocam_outlined,
                size: 18, color: AppColors.accent),
          ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: TextField(
            controller: _sceneNoteCtrl,
            style: AppText.value.copyWith(fontSize: 13),
            maxLength: 500,
            decoration: const InputDecoration(
                isDense: true,
                counterText: "",
                labelText: "Megjegyzés a táblához",
                hintText: "mi történik ebben a helyzetben"),
            onChanged: (v) => setState(() {
              s.note = v;
              _touch();
            }),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        OutlinedButton.icon(
          onPressed: _eventFromScene,
          icon: const Icon(Icons.playlist_add, size: 16),
          label: const Text("Esemény a naplóba"),
        ),
      ],
    );
  }

  // --- napló ---

  Widget _logCard() {
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: ListView(
        children: [
          Row(children: [
            Text("ESEMÉNY-NAPLÓ", style: AppText.sectionLabel),
            const Spacer(),
            Text("${_events.length} esemény", style: AppText.label),
          ]),
          const SizedBox(height: AppSpacing.sm),
          _eventForm(),
          if (_events.isNotEmpty) ...[
            const Divider(color: AppColors.border, height: AppSpacing.xl),
            _statsPanel(),
          ],
          const Divider(color: AppColors.border, height: AppSpacing.xl),
          if (_events.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
              child: Text(
                "Még nincs esemény. Írd be az időt (a videó ideje), a csapatot, "
                "az eseményt és a mezszámot — a napló magától mentődik.",
                style: AppText.label,
              ),
            )
          else
            for (final e in _events) _eventTile(e),
        ],
      ),
    );
  }

  /// Összesítés a naplóból (csapatonként lövés/gól/hatékonyság, eladás,
  /// szerzés, kiállítás, és a legjobb góllövők mezszám szerint).
  Widget _statsPanel() {
    final stats = annLogStats(_events);
    Widget col(String team, String name, Color color) {
      final st = stats[team]!;
      final top = st.topScorers(3);
      return Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_short(name),
                style: AppText.value.copyWith(fontSize: 13, color: color)),
            const SizedBox(height: 2),
            Text(
              "Gól/lövés: ${st.goals}/${st.shots}"
              "${st.pct == null ? "" : " (${st.pct}%)"}",
              style: AppText.label.copyWith(fontSize: 12),
            ),
            if (st.saves > 0 || st.sevenM > 0)
              Text("Védett: ${st.saves} · hetes: ${st.sevenM}",
                  style: AppText.label.copyWith(fontSize: 12)),
            Text(
                "Eladás: ${st.turnovers} · szerzés: ${st.steals}"
                "${st.suspensions > 0 ? " · kiállítás: ${st.suspensions}" : ""}",
                style: AppText.label.copyWith(fontSize: 12)),
            if (top.isNotEmpty)
              Text(
                  "Góllövők: ${top.map((e) => "#${e.key} ${e.value[0]}/${e.value[1]}").join(", ")}",
                  style: AppText.label.copyWith(fontSize: 12)),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text("ÖSSZESÍTÉS A NAPLÓBÓL", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.xs),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            col("home", widget.homeName, AppColors.home),
            const SizedBox(width: AppSpacing.md),
            col("away", widget.awayName, AppColors.away),
          ],
        ),
      ],
    );
  }

  Widget _eventForm() {
    final editing = _editingEventId != null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          SizedBox(
            width: 86,
            child: TextField(
              controller: _timeCtrl,
              style: AppText.value.copyWith(fontSize: 13),
              decoration: const InputDecoration(
                  isDense: true, labelText: "Idő", hintText: "pp:mm"),
            ),
          ),
          IconButton(
            onPressed: () => setState(
                () => _timeCtrl.text = formatAnnTime(widget.startSeconds)),
            tooltip: "A meccs-nézet ideje",
            icon: const Icon(Icons.history, size: 18, color: AppColors.textSecondary),
          ),
          if (_videoOn)
            IconButton(
              onPressed: () => _takeVideoTime(_timeCtrl),
              tooltip: "Idő a videóból (a lejátszó mostani helye)",
              icon: const Icon(Icons.videocam_outlined,
                  size: 18, color: AppColors.accent),
            ),
          const Spacer(),
          SegmentedButton<String>(
            showSelectedIcon: false,
            segments: [
              ButtonSegment(value: "home", label: Text(_short(widget.homeName))),
              ButtonSegment(value: "away", label: Text(_short(widget.awayName))),
            ],
            selected: {_formTeam},
            onSelectionChanged: (v) => setState(() => _formTeam = v.first),
          ),
        ]),
        if (!editing) ...[
          const SizedBox(height: AppSpacing.sm),
          _quickRow(),
          const Divider(color: AppColors.border, height: AppSpacing.lg),
        ],
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final t in kAnnEventTypes)
              ChoiceChip(
                label: Text(t, style: const TextStyle(fontSize: 12)),
                selected: _formType == t,
                visualDensity: VisualDensity.compact,
                onSelected: (_) => setState(() {
                  _formType = t;
                  if (!_hasOutcome(t)) _formOutcome = "";
                }),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(children: [
          SizedBox(
            width: 70,
            child: TextField(
              controller: _jerseyCtrl,
              style: AppText.value.copyWith(fontSize: 13),
              maxLength: 6,
              decoration: const InputDecoration(
                  isDense: true, counterText: "", labelText: "Mez"),
            ),
          ),
          if (_formType == "passz") ...[
            const SizedBox(width: AppSpacing.sm),
            SizedBox(
              width: 80,
              child: TextField(
                controller: _toJerseyCtrl,
                style: AppText.value.copyWith(fontSize: 13),
                maxLength: 6,
                decoration: const InputDecoration(
                    isDense: true, counterText: "", labelText: "Kinek"),
              ),
            ),
          ],
          if (_hasOutcome(_formType)) ...[
            const SizedBox(width: AppSpacing.sm),
            DropdownButton<String>(
              value: _formOutcome,
              dropdownColor: AppColors.surface,
              hint: const Text("Kimenetel"),
              items: [
                const DropdownMenuItem(value: "", child: Text("kimenetel?")),
                for (final o in kAnnShotOutcomes)
                  DropdownMenuItem(value: o, child: Text(o)),
              ],
              onChanged: (v) => setState(() => _formOutcome = v ?? ""),
            ),
          ],
        ]),
        TextField(
          controller: _noteCtrl,
          style: AppText.value.copyWith(fontSize: 13),
          maxLength: 500,
          decoration: const InputDecoration(
              isDense: true,
              counterText: "",
              labelText: "Megjegyzés",
              hintText: "pl. bal szélről, a beálló elzárta"),
          onSubmitted: (_) => _submitEvent(),
        ),
        if (_scenes.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            Text("Tábla:", style: AppText.label),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: DropdownButton<String>(
                isExpanded: true,
                value: _sceneById(_formSceneId) != null ? _formSceneId : "",
                dropdownColor: AppColors.surface,
                items: [
                  const DropdownMenuItem(value: "", child: Text("nincs")),
                  for (final s in _scenes)
                    DropdownMenuItem(
                        value: s.id,
                        child: Text(s.name, overflow: TextOverflow.ellipsis)),
                ],
                onChanged: (v) => setState(() => _formSceneId = v ?? ""),
              ),
            ),
          ]),
        ],
        const SizedBox(height: AppSpacing.sm),
        Row(children: [
          Expanded(
            child: FilledButton.icon(
              onPressed: _submitEvent,
              style: FilledButton.styleFrom(
                  backgroundColor: editing ? AppColors.gold : AppColors.accent,
                  foregroundColor: AppColors.onAccent),
              icon: Icon(editing ? Icons.check : Icons.add, size: 18),
              label: Text(editing ? "Módosítás mentése" : "Hozzáadás a naplóhoz"),
            ),
          ),
          if (editing) ...[
            const SizedBox(width: AppSpacing.sm),
            TextButton(onPressed: _cancelEdit, child: const Text("Mégse")),
          ],
        ]),
      ],
    );
  }

  String _short(String name) =>
      name.length <= 12 ? name : "${name.substring(0, 11)}…";

  Widget _eventTile(Map<String, dynamic> e) {
    final team = _str(e["team"]);
    final color = team == "home"
        ? AppColors.home
        : team == "away"
            ? AppColors.away
            : AppColors.textFaint;
    final parts = <String>[];
    if (_str(e["jersey"]).isNotEmpty) parts.add("#${_str(e["jersey"])}");
    if (_str(e["type"]) == "passz" && _str(e["to_jersey"]).isNotEmpty) {
      parts.add("→ #${_str(e["to_jersey"])}");
    }
    if (_str(e["outcome"]).isNotEmpty) parts.add(_str(e["outcome"]));
    final note = _str(e["note"]);
    final scene = _sceneById(_str(e["scene_id"]));
    final editing = _editingEventId == _str(e["id"]);
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      decoration: BoxDecoration(
        color: editing ? AppColors.gold.withOpacity(0.10) : null,
        borderRadius: BorderRadius.circular(8),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _startEdit(e),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 50,
                child: _hasVideo
                    // Az időre kattintva a videó oda ugrik.
                    ? Tooltip(
                        message: "Ugrás ide a videóban",
                        child: InkWell(
                          onTap: () => _seekVideo(_toD(e["t_s"], 0)),
                          child: Text(formatAnnTime(_toD(e["t_s"], 0)),
                              style: AppText.value.copyWith(
                                  fontSize: 13,
                                  color: AppColors.accent,
                                  decoration: TextDecoration.underline)),
                        ),
                      )
                    : Text(formatAnnTime(_toD(e["t_s"], 0)),
                        style: AppText.value.copyWith(fontSize: 13)),
              ),
              Padding(
                padding: const EdgeInsets.only(top: 5),
                child: Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text("${_str(e["type"])}   ${parts.join("  ")}",
                        style: AppText.value.copyWith(fontSize: 13)),
                    if (note.isNotEmpty)
                      Text(note, style: AppText.label.copyWith(fontSize: 11.5)),
                    if (scene != null)
                      InkWell(
                        onTap: () => _openSceneOfEvent(e),
                        child: Text("tábla: ${scene.name}",
                            style: AppText.label.copyWith(
                                fontSize: 11.5, color: AppColors.accent)),
                      ),
                  ],
                ),
              ),
              IconButton(
                onPressed: () => _deleteEvent(e),
                tooltip: "Törlés",
                visualDensity: VisualDensity.compact,
                icon: const Icon(Icons.close, size: 16, color: AppColors.textFaint),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Az összevetés eredménye: ítélet, típusonkénti egyezés, és a kimaradt /
/// téves tételek — a tételre kattintva a dialógus a tétel idejével zárul
/// (a hívó oda tekeri a videót).
class _CompareDialog extends StatelessWidget {
  final Map<String, dynamic> res;
  final String homeName;
  final String awayName;
  final bool canSeek;

  const _CompareDialog({
    required this.res,
    required this.homeName,
    required this.awayName,
    required this.canSeek,
  });

  static const Map<String, String> _typeHu = {"goal": "gól", "shot": "lövés"};

  String _team(Object? t) =>
      t == "home" ? homeName : (t == "away" ? awayName : "?");

  String _pct(Object? v) => v is num ? "${(v * 100).round()}%" : "–";

  Map<String, dynamic> _block(String ty) {
    final bt = res["by_type"];
    if (bt is Map && bt[ty] is Map) {
      return Map<String, dynamic>.from(bt[ty] as Map);
    }
    return const {};
  }

  Widget _row(String ty) {
    final b = _block(ty);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Text(
        "${_typeHu[ty]!.toUpperCase()}: ${b["tp"] ?? 0} egyezik · "
        "${b["fn"] ?? 0} kimaradt · ${b["fp"] ?? 0} téves  "
        "(visszahívás ${_pct(b["recall"])}, precizitás ${_pct(b["precision"])})",
        style: AppText.value.copyWith(fontSize: 13),
      ),
    );
  }

  List<Map<String, dynamic>> _items(String key) {
    final out = <Map<String, dynamic>>[];
    for (final ty in const ["goal", "shot"]) {
      final l = _block(ty)[key];
      if (l is List) {
        for (final e in l) {
          if (e is Map) out.add(Map<String, dynamic>.from(e));
        }
      }
    }
    out.sort((a, b) => _toD(a["t_s"], 0).compareTo(_toD(b["t_s"], 0)));
    return out;
  }

  Widget _list(BuildContext context, String title, String key) {
    final items = _items(key);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: AppSpacing.md),
        Text("$title (${items.length})", style: AppText.sectionLabel),
        if (items.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text("nincs", style: AppText.label),
          ),
        for (final e in items)
          InkWell(
            onTap: canSeek
                ? () => Navigator.of(context).pop(_toD(e["t_s"], 0))
                : null,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(children: [
                SizedBox(
                  width: 56,
                  child: Text(formatAnnTime(_toD(e["t_s"], 0)),
                      style: AppText.value.copyWith(
                          fontSize: 13,
                          color: canSeek ? AppColors.accent : null)),
                ),
                Expanded(
                  child: Text(
                      "${_typeHu[_str(e["type"])] ?? _str(e["type"])} · "
                      "${_team(e["team"])}",
                      style: AppText.label.copyWith(fontSize: 12.5)),
                ),
                if (canSeek)
                  const Icon(Icons.play_arrow,
                      size: 16, color: AppColors.textSecondary),
              ]),
            ),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final verdict = res["verdict"] is Map
        ? Map<String, dynamic>.from(res["verdict"] as Map)
        : const <String, dynamic>{};
    final pass = verdict["pass"];
    final color = pass == true
        ? AppColors.accent
        : pass == false
            ? AppColors.gold
            : AppColors.textSecondary;
    final win = res["window_s"];
    final String scope;
    if (win is List && win.length == 2) {
      scope = "A napló által lefedett rész: ${formatAnnTime(_toD(win[0], 0))}"
          " – ${formatAnnTime(_toD(win[1], 0))} (félkész elemzés; a "
          "\"Kész\" jelölés után az egész meccs számít).";
    } else {
      scope = "Az egész meccs (az elemzés késznek jelölve).";
    }
    final tol = _toD(res["tol_s"], 3);
    return AlertDialog(
      title: const Text("Összevetés a géppel"),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_str(verdict["text"]),
                  style: AppText.value.copyWith(color: color, fontSize: 14)),
              const SizedBox(height: AppSpacing.sm),
              Text("Kézi lövés/gól: ${res["manual_shots"] ?? 0} · $scope",
                  style: AppText.label.copyWith(fontSize: 12)),
              const SizedBox(height: AppSpacing.sm),
              _row("goal"),
              _row("shot"),
              _list(context, "KIMARADT — a naplóban van, a gép nem látta",
                  "missed"),
              _list(context, "TÉVES — a gép látta, a naplóban nincs",
                  "spurious"),
              const SizedBox(height: AppSpacing.md),
              Text(
                "Egyezés: azonos típus (és ha megadtad, csapat) "
                "±${tol.toStringAsFixed(0)} mp-en belül. "
                "${canSeek ? "A tételre kattintva a videó "
                    "${kAnnCompareLeadS.toStringAsFixed(0)} mp-cel előtte "
                    "indul — így megnézheted, ki tévedett." : ""}",
                style: AppText.label.copyWith(fontSize: 11.5),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text("Bezárás")),
      ],
    );
  }
}

/// A taktikai tábla rajzolója: pálya, sorszámozott nyilak, bábuk, labda.
class _BoardPainter extends CustomPainter {
  final _Scene scene;
  final String? selected;
  final String? pending;
  final int rev; // a változás-számláló: a bábuk helyben változnak
  final double zoom; // a tábla nagyítása (1× = teljes pálya)
  final Offset pan; // a nagyított tábla eltolása képpontban

  _BoardPainter({
    required this.scene,
    this.selected,
    this.pending,
    required this.rev,
    this.zoom = 1.0,
    this.pan = Offset.zero,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final tr = annBoardTransform(size, zoom, pan);
    _court(canvas, tr);
    final r = 0.8 * tr.scale;

    Offset posOf(String id) {
      for (final t in scene.tokens) {
        if (t.id == id) return tr.toScreen(t.x, t.y);
      }
      return Offset.zero;
    }

    bool hasToken(String id) {
      for (final t in scene.tokens) {
        if (t.id == id) return true;
      }
      return false;
    }

    // Nyilak (sorszámmal: a sorrend a támadás menete).
    for (var i = 0; i < scene.arrows.length; i++) {
      final a = scene.arrows[i];
      if (!hasToken(a.from)) continue;
      final start = posOf(a.from);
      final toToken = a.to.isNotEmpty && hasToken(a.to);
      final Offset end;
      if (toToken) {
        end = posOf(a.to);
      } else if (a.x != null && a.y != null) {
        end = tr.toScreen(a.x!, a.y!);
      } else {
        continue;
      }
      final d = end - start;
      final len = d.distance;
      if (len < 2) continue;
      final u = d / len;
      final s0 = start + u * r;
      final e0 = toToken ? end - u * r : end;
      final Color color;
      final double width;
      switch (a.kind) {
        case "run":
          color = AppColors.accent;
          width = 2.0;
          break;
        case "shot":
          color = AppColors.gold;
          width = 3.2;
          break;
        default:
          color = Colors.white.withOpacity(0.9);
          width = 2.2;
      }
      _arrow(canvas, s0, e0, color, width, dashed: a.kind == "run");
      // Sorszám a nyíl közepén.
      final mid = Offset.lerp(s0, e0, 0.5)!;
      canvas.drawCircle(mid, 8.5, Paint()..color = AppColors.bg);
      canvas.drawCircle(
          mid,
          8.5,
          Paint()
            ..color = color
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.2);
      _text(canvas, mid, "${i + 1}", 10, color);
    }

    // Bábuk (a labda a végén, hogy a játékosok fölött látsszon).
    for (final t in scene.tokens) {
      if (t.team == "ball") continue;
      final c = tr.toScreen(t.x, t.y);
      final color = t.team == "home" ? AppColors.home : AppColors.away;
      if (t.id == pending) {
        canvas.drawCircle(c, r + 5, Paint()..color = AppColors.gold.withOpacity(0.35));
      }
      canvas.drawCircle(c, r, Paint()..color = color);
      if (t.id == selected || t.id == pending) {
        canvas.drawCircle(
            c,
            r + 2,
            Paint()
              ..color = t.id == pending ? AppColors.gold : Colors.white
              ..style = PaintingStyle.stroke
              ..strokeWidth = 2);
      }
      if (t.label.isNotEmpty) {
        final fs = t.label.length >= 3 ? r * 0.62 : r * 0.9;
        _text(canvas, c, t.label, fs, Colors.white);
      }
    }
    for (final t in scene.tokens) {
      if (t.team != "ball") continue;
      final c = tr.toScreen(t.x, t.y);
      canvas.drawCircle(c, r * 0.45, Paint()..color = AppColors.ball);
      canvas.drawCircle(
          c,
          r * 0.45,
          Paint()
            ..color = Colors.black.withOpacity(0.5)
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1);
    }
  }

  void _arrow(Canvas canvas, Offset a, Offset b, Color color, double width,
      {bool dashed = false}) {
    final d = b - a;
    final len = d.distance;
    if (len < 1) return;
    final u = d / len;
    final head = math.min(12.0, len * 0.4);
    final line = Paint()
      ..color = color
      ..strokeWidth = width
      ..strokeCap = StrokeCap.round;
    final shaftEnd = len - head * 0.8;
    if (dashed) {
      var s = 0.0;
      while (s < shaftEnd) {
        final e = math.min(s + 7, shaftEnd);
        canvas.drawLine(a + u * s, a + u * e, line);
        s += 12;
      }
    } else {
      canvas.drawLine(a, a + u * shaftEnd, line);
    }
    final n = Offset(-u.dy, u.dx);
    final base = b - u * head;
    final p1 = base + n * (head * 0.5);
    final p2 = base - n * (head * 0.5);
    final path = Path()
      ..moveTo(b.dx, b.dy)
      ..lineTo(p1.dx, p1.dy)
      ..lineTo(p2.dx, p2.dy)
      ..close();
    canvas.drawPath(path, Paint()..color = color);
  }

  void _text(Canvas canvas, Offset center, String text, double size, Color color) {
    final tp = TextPainter(
      text: TextSpan(
          text: text,
          style: TextStyle(color: color, fontSize: size, fontWeight: FontWeight.bold)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  void _court(Canvas canvas, CourtTransform tr) {
    final fill = Paint()..color = AppColors.courtFill;
    final line = Paint()
      ..color = AppColors.courtLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    final rect = Rect.fromPoints(tr.toScreen(0, 0), tr.toScreen(courtLength, courtWidth));
    final rrect = RRect.fromRectAndRadius(rect, const Radius.circular(8));
    canvas.drawRRect(rrect, fill);
    canvas.drawRRect(rrect, line);
    canvas.drawLine(tr.toScreen(courtLength / 2, 0),
        tr.toScreen(courtLength / 2, courtWidth), line);
    canvas.drawCircle(tr.toScreen(courtLength / 2, courtWidth / 2), 2.0 * tr.scale, line);
    for (final leftSide in [true, false]) {
      final pts = goalAreaBoundary(leftSide: leftSide)
          .map((o) => tr.toScreen(o.dx, o.dy))
          .toList();
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (final pt in pts.skip(1)) {
        path.lineTo(pt.dx, pt.dy);
      }
      path.close();
      canvas.drawPath(path, Paint()..color = AppColors.accent.withOpacity(0.07));
      canvas.drawPath(path, line);
      // 9 m-es szaggatott vonal.
      final dash = Paint()
        ..color = AppColors.courtLine.withOpacity(0.75)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2
        ..strokeCap = StrokeCap.round;
      final fpts = freeThrowBoundary(leftSide: leftSide, segments: 22)
          .map((o) => tr.toScreen(o.dx, o.dy))
          .toList();
      for (var i = 0; i + 1 < fpts.length; i += 2) {
        canvas.drawLine(fpts[i], fpts[i + 1], dash);
      }
      // 7 m-es jel.
      final x7 = leftSide ? sevenMeterX : courtLength - sevenMeterX;
      canvas.drawLine(tr.toScreen(x7, courtWidth / 2 - sevenMeterHalfLen),
          tr.toScreen(x7, courtWidth / 2 + sevenMeterHalfLen), line);
      // Kapu (a gólvonalon túl).
      final gx0 = leftSide ? -0.8 : courtLength;
      final gx1 = leftSide ? 0.0 : courtLength + 0.8;
      final goal = Rect.fromPoints(
          tr.toScreen(gx0, courtWidth / 2 - goalWidth / 2),
          tr.toScreen(gx1, courtWidth / 2 + goalWidth / 2));
      canvas.drawRect(
          goal,
          Paint()
            ..color = Colors.white.withOpacity(0.55)
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.6);
    }
  }

  @override
  bool shouldRepaint(covariant _BoardPainter old) =>
      old.rev != rev ||
      old.scene != scene ||
      old.selected != selected ||
      old.pending != pending ||
      old.zoom != zoom ||
      old.pan != pan;
}
