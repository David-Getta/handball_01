/// 3D pálya — az elemzett meccs bejárása, mint egy videójátékban.
///
/// A jövendő termék 3D/VR-útjának ELSŐ köre (ROADMAP 6–7. fázis): a már
/// elemzett meccs followható 3D-ben, szabad mozgással — WASD + egér-húzás,
/// mint egy belső nézetes játékban. Nem kell hozzá új adat: a meglévő
/// követés (pálya-koordináták) áll térbe. A többkamerás/LiDAR bemenet és
/// a VR (WebXR) erre a nézetre épül majd rá.
///
/// A megjelenítés szoftveres távlati vetítés (CustomPaint): a Flutter-ben
/// nincs beépített 3D motor, de a pálya vonalai + 14 játékos + labda
/// vonalgrafikaként bőven valós idejű. A kamera a pálya-koordináták
/// terében mozog (méter; z felfelé).
library;

import "dart:io";
import "dart:math" as math;

import "package:flutter/gestures.dart";
import "package:flutter/material.dart";
import "package:flutter/scheduler.dart";
import "package:flutter/services.dart";

import "../analytics/court_analytics.dart";
import "../models/tracking.dart";
import "../services/api_client.dart";
import "../sim/demo_data.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";
import "error_text.dart";
import "shell/app_shell.dart";

class Court3DScreen extends StatefulWidget {
  /// Ha a könyvtárból jövünk, a megnyitandó meccs; menüből null (választó).
  final String? matchId;

  /// Ha eseményből jövünk ("Megnézem 3D-ben"), a jelenet kezdete
  /// másodpercben: a lejátszó ide ugrik, és TV-kamerával indul.
  final double? startS;

  /// Lövés/gól sorból jövünk: a lövéstérkép induló módja ("mind"), hogy
  /// a jelenet lövése a többi közt, a helyén látszódjon.
  final String? lovesTerkep;
  const Court3DScreen(
      {super.key, this.matchId, this.startS, this.lovesTerkep});

  @override
  State<Court3DScreen> createState() => _Court3DScreenState();
}

class _Court3DScreenState extends State<Court3DScreen>
    with SingleTickerProviderStateMixin {
  final ApiClient _api = ApiClient();

  Match? _match;
  List<Map<String, dynamic>> _matches = [];
  String? _matchId;
  bool _demo = false;
  String? _err;
  bool _loading = true;

  // Kamera a pálya terében (méter, z felfelé). yaw=0: a +y irányba néz.
  double _cx = 20, _cy = -7, _cz = 5;
  double _yaw = 0;
  double _pitch = -0.28;

  // Lejátszás: tört frame-index, hogy a mozgás sima legyen (interpoláció).
  double _playhead = 0;
  bool _playing = false;
  double _speed = 1.0;

  // TV-KAMERA: a nézet magától követi a labdát az oldalvonal felől,
  // mint egy közvetítés gépállása. Kézi mozgásra (WASD, egér) kikapcsol
  // — aki nyúl a kamerához, az vezetni akarja.
  bool _tvKamera = false;

  // JÁTÉKOS-KAMERA: a kiválasztott mezszámú játékost követi hátulról,
  // a haladási iránya mögül — a pálya az ő szemével. A mezszám stabil
  // fogódzó (a track-azonosítók a valódi követésben töredezettek).
  String? _kovTeam; // "home" | "away"
  int? _kovMez;
  double _kovIranyX = 0, _kovIranyY = 1; // simított haladás-irány
  double? _kovElozoX, _kovElozoY;
  // A meccsen LÁTOTT mezszámok csapatonként (egyszer, betöltéskor).
  List<int> _mezekHome = const [], _mezekAway = const [];
  // A meccs eseményei (gól/lövés/eladás) t szerint növekvően — a 3D-n
  // belüli előző/következő ugráshoz és a jelenet-felirathoz, hogy ne
  // kelljen az Események listához visszajárni.
  List<Map<String, dynamic>> _esemenyek = const [];

  // KERINGÉS: a pálya közepe körül — húzás keringtet, görgetés vagy
  // csípés (trackpad, két ujj) közelít. WASD-re szabad módba vált.
  bool _kering = false;
  double _kTheta = 0, _kPhi = 0.6, _kR = 30;
  double _csipesR0 = 30;
  // JÁTÉKOS SZEMÉVEL: dupla koppintás egy figurára — a kamera a fejében
  // ül, és vele együtt halad; húzás körülnéz, Esc kilép. A célpont a
  // mezszám (ha van), különben a legutóbbi helyéhez legközelebbi
  // csapattárs 3 m-en belül (a követés-azonosítók töredezettek).
  bool _szemevel = false;
  bool _szemHome = true;
  int? _szemMez;
  double _szemX = 0, _szemY = 0;
  double _szemIrany = 0; // simított haladás-irány (yaw)
  double _szemYaw = 0, _szemPitch = -0.05; // körülnézés a fejben
  Offset? _dupla; // a dupla koppintás helye
  // A játékos megtett útja kockánként összegezve (méter), mezszámonként
  // — a HUD-nak; a lépésenkénti ugrás-szűrő MÉTER-korlát (követés-ugrás
  // nem számít, a sűrű remegés nem esik ki). Meccsenként egyszer.
  static const double _tavUgrasM = 3.0;
  Match? _tavMeccs;
  final Map<String, List<double>> _tavTabla = {};
  // LÖVÉS-MÉRÉS: koppintás a padlóra → távolság, kapu-szög, sáv.
  Offset? _meres;
  // VÉDEKEZÉS-PANEL: tankönyvi fal a kapu előtt / az élő fal.
  String _fal = ""; // "" | "elo" | sablonnév
  String _falOldal = "auto"; // "auto" | "bal" | "jobb"
  List<Map<String, dynamic>> _falSorok = const [];
  // Feltörés: hol és mivel törhető fel a csapatok védekezése (a
  // felderítés rangsorának teteje, csapatonként) — a fal mellé írjuk.
  Map<String, dynamic> _falBreak = const {};
  // Megállítás: hogyan állítható meg a csapatok támadása (a párja).
  Map<String, dynamic> _falStop = const {};
  // LÖVÉSTÉRKÉP: a meccs lövései a padlón (a /xg lövés-sorai: t kocka,
  // team, x, y, xg, outcome); koppintás egy körre — odaugrik.
  List<Map<String, dynamic>> _lovesek = const [];
  String _lovesTerkep = ""; // "" | "mind" | "eddig" | "hazai" | "vendeg"
  Map<String, dynamic>? _lovesValasztott; // a mérés-dobozban megnevezett lövés
  // PASSZOK: a futó passz vonala (adótól a fogadóig, mellmagasságban,
  // halványodva) vagy a csapat passz-hálója a padlón. Egy sor: t (kocka),
  // team, x1, y1, x2, y2 — az események passzaiból a kocka játékosaival.
  List<Map<String, dynamic>> _passzok = const [];
  String _passz = ""; // "" | "elo" | "hazai" | "vendeg"
  static const double _passzS = 1.0;
  // LABDA-NYOM: a labda útja az utolsó _nyomS másodpercben (narancs vonal).
  bool _nyom = false;
  static const double _nyomS = 3.0;
  // PASSZSÁVOK: a labdástól a társakig (a döntés-elemzés modellje).
  bool _passzsav = false;
  // FAL-RÉSEK: szervezett védekezésben a védőfal szomszédos védői közt
  // sáv a padlón — zöld zárt, piros a wallGapM-es (3,5 m) rés.
  bool _falres = false;
  // Az eszköz-panel nyitva van-e (összecsukva csak a kapcsoló látszik).
  bool _eszkozokNyitva = true;
  // DÖNTÉS-PILLANATOK: ahol jobb opció is volt (a /decision-moments
  // pillanatai) — ◀ ▶ lapoz, a pillanat körül fehér/arany vonal.
  List<Map<String, dynamic>> _dontesek = const [];
  // SZABAD LÖVŐK: a fedezés-hibák (a /free-shots pillanatai) — ◀ ▶ lapoz,
  // a pillanat körül piros kör a lövő körül és vonal a legközelebbi védőhöz.
  List<Map<String, dynamic>> _szabadok = const [];
  double _szabadSugar = 2.0;
  // LABDAVESZTÉSEK: ki, hol, kipréselve vagy magától (a /turnover-moments
  // pillanatai) — ◀ ▶ lapoz, a pillanat körül narancs kör a vesztő körül
  // (a nyomás-sugár), vonal a legközelebbi ellenfélhez, X a labdánál.
  List<Map<String, dynamic>> _eladasok = const [];
  double _eladasSugar = 2.5;
  // GÓL-AKCIÓK: a gólt megelőző passz-lánc (a /goal-build-ups góljai) —
  // ◀ ▶ lapoz, a lánc a csapat színével, arany vonal a lövéstől a kapuig.
  List<Map<String, dynamic>> _golok = const [];
  double? _golUtolso;
  // KINEK A HIBÁI: a három lapozó (Döntések, Szabad lövők, Labdavesztések)
  // mind egy csapat hibáját mutatja — "" mindkettő, "home" / "away" csak
  // az egyiké (a böngészős nézet jelenet-szűrőjének párja).
  String _jelenetCsapat = "";
  // JELENET-LISTA: a három lapozó jelenetei egy időrendi listában (a bal
  // oldalon) — koppintás egy sorra: odaugrik.
  bool _jelenetListaNyitva = false;
  // Az utoljára ugrott pillanat ideje listánként (a lapozó ettől számít,
  // amíg annak ablakában vagyunk — lásd lapozCel).
  double? _dontesUtolso, _szabadUtolso, _eladasUtolso;
  // HŐTÉRKÉP: hol tartózkodott a csapat (az elemzés rácsa: 20×10 cella,
  // csak a mért helyek) a pályára fektetve. Meccsenként egyszer számolva.
  String _hoter = ""; // "" | "hazai" | "vendeg" | "mind"
  Match? _hoMeccs;
  Heatmap? _hoHazai, _hoVendeg;
  Size _nezetMeret = Size.zero;

  late final Ticker _ticker;
  Duration _last = Duration.zero;
  final Set<LogicalKeyboardKey> _keys = {};
  final FocusNode _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_tick)..start();
    _load();
  }

  @override
  void dispose() {
    _ticker.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      _matches = await _api.listMatches();
    } catch (_) {
      _matches = [];
    }
    final kert = widget.matchId ??
        (_matches.isNotEmpty ? _matches.last["match_id"] as String : null);
    if (kert == null) {
      // Nincs még elemzett meccs: a demó mutatja meg, mit fog tudni.
      setState(() {
        _match = buildDemoMatch();
        _lovesek = buildDemoShots();
        _passzok = buildDemoPasses(_match!);
        _dontesek = buildDemoDecisions(_match!);
        _szabadok = buildDemoFreeShots();
        _eladasok = buildDemoTurnovers(_match!);
        _golok = buildDemoGoalBuildUps(_match!);
        _falSorok = buildDemoDefenceTimeline(_match!);
        _demo = true;
        _loading = false;
      });
      return;
    }
    await _open(kert);
  }

  Future<void> _open(String id) async {
    setState(() {
      _loading = true;
      _err = null;
    });
    try {
      final m = await _api.fetchMatch(id);
      if (!mounted) return;
      // Az események külön kérés — hibája nem viheti el a 3D nézetet.
      List<Map<String, dynamic>> esemenyek = const [];
      List<Map<String, dynamic>> passzok = const [];
      try {
        final mind = await _api.fetchEvents(id);
        esemenyek = mind
            .where((e) => const {"goal", "shot", "turnover"}
                .contains(e["type"]))
            .toList();
        passzok = _passzSorok(m, mind);
        // A visszatérő figura kezdete is ugrópont ("Ismert figura") —
        // a könyvtárból, több meccs kell hozzá; hibája nem viszi el a nézetet.
        try {
          for (final a in await _api.fetchFigureAlerts(id)) {
            esemenyek.add({
              "t": a["t"], "type": "figure", "team": a["team"],
              "zone": a["zone"],
            });
          }
        } catch (_) {}
        esemenyek.sort((x, y) =>
            ((x["t"] as num?) ?? 0).compareTo((y["t"] as num?) ?? 0));
      } catch (_) {
        esemenyek = const [];
      }
      if (!mounted) return;
      // A védekezés-panel élő fala — hibája nem viheti el a nézetet.
      List<Map<String, dynamic>> falSorok = const [];
      Map<String, dynamic> falBreak = const {};
      Map<String, dynamic> falStop = const {};
      try {
        final d = await _api.fetchDefenceTimeline(id);
        falSorok = ((d["rows"] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        falBreak = (d["breakpoints"] as Map?)?.cast<String, dynamic>() ??
            const {};
        falStop = (d["stoppers"] as Map?)?.cast<String, dynamic>() ??
            const {};
      } catch (_) {}
      // A szabad lövők — hibája nem viheti el a nézetet.
      List<Map<String, dynamic>> szabadok = const [];
      double szabadSugar = 2.0;
      try {
        final fs = await _api.fetchFreeShots(id);
        szabadok = ((fs["moments"] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        szabadSugar = ((fs["radius_m"] as num?) ?? 2.0).toDouble();
      } catch (_) {}
      // A gól-akciók — hibája nem viheti el a nézetet.
      List<Map<String, dynamic>> golok = const [];
      try {
        golok = (((await _api.fetchGoalBuildUps(id))["moments"] as List?) ??
                const [])
            .cast<Map<String, dynamic>>();
      } catch (_) {}
      // A labdavesztések — hibája nem viheti el a nézetet.
      List<Map<String, dynamic>> eladasok = const [];
      double eladasSugar = 2.5;
      try {
        final tm = await _api.fetchTurnoverMoments(id);
        eladasok = ((tm["moments"] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        eladasSugar = ((tm["pressure_m"] as num?) ?? 2.5).toDouble();
      } catch (_) {}
      // A döntés-pillanatok — hibája nem viheti el a nézetet.
      List<Map<String, dynamic>> dontesek = const [];
      try {
        dontesek = (((await _api.fetchDecisionMoments(id))["moments"]
                    as List?) ??
                const [])
            .cast<Map<String, dynamic>>();
      } catch (_) {}
      // A lövéstérkép a helyzetminőség lövés-soraiból — hibája nem
      // viheti el a nézetet (a térkép ilyenkor üres).
      List<Map<String, dynamic>> lovesek = const [];
      try {
        lovesek = (((await _api.fetchXg(id))["shots"] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
      } catch (_) {}
      if (!mounted) return;
      final h = <int>{}, a = <int>{};
      for (final f in m.frames) {
        for (final p in f.players) {
          final mez = p.jerseyNumber;
          if (mez == null) continue;
          (p.team == Team.home ? h : a).add(mez);
        }
      }
      // Eseményből érkezve pár másodperccel a jelenet ELŐTT kezdünk
      // (a felvezetés nélkül a jelenet értelmezhetetlen), és a
      // TV-kamera viszi a képet — kattintás nélkül nézhető.
      // A startS videó-másodperc, a lejátszófej pedig lista-INDEX — a
      // kettő vágott meccsen nem ugyanaz, ezért a t címke szerint
      // keressük meg a kockát (_tIndex).
      final fps0 = m.meta.fps > 0 ? m.meta.fps : 25.0;
      final ugras = widget.startS == null
          ? 0.0
          : _tIndex(m, (widget.startS! - 4.0) * fps0).toDouble();
      setState(() {
        _match = m;
        _matchId = id;
        _demo = false;
        _esemenyek = esemenyek;
        _playhead = ugras;
        _playing = widget.startS != null;
        _tvKamera = widget.startS != null;
        _loading = false;
        _mezekHome = h.toList()..sort();
        _mezekAway = a.toList()..sort();
        _kovTeam = null;
        _kovMez = null;
        _falSorok = falSorok;
        _falBreak = falBreak;
        _falStop = falStop;
        _lovesek = lovesek;
        _passzok = passzok;
        _dontesek = dontesek;
        _szabadok = szabadok;
        _szabadSugar = szabadSugar;
        _eladasok = eladasok;
        _eladasSugar = eladasSugar;
        _golok = golok;
        _lovesValasztott = null;
        if (widget.lovesTerkep != null) _lovesTerkep = widget.lovesTerkep!;
        _meres = null;
        _szemevel = false;
        _kering = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _err = humanError(e);
        _loading = false;
      });
    }
  }

  // ------------------------------------------------------------- mozgás

  void _tick(Duration now) {
    final dt = _last == Duration.zero
        ? 0.0
        : (now - _last).inMicroseconds / 1e6;
    _last = now;
    if (dt <= 0 || dt > 0.5) return;
    var valtozott = false;

    // WASD a talaj síkján, R/F fel-le, Shift gyorsít — játék-érzés.
    final gyors = _keys.contains(LogicalKeyboardKey.shiftLeft) ||
        _keys.contains(LogicalKeyboardKey.shiftRight);
    final sp = (gyors ? 14.0 : 6.0) * dt;
    final fx = math.sin(_yaw), fy = math.cos(_yaw);
    final rx = math.cos(_yaw), ry = -math.sin(_yaw);
    if (_keys.contains(LogicalKeyboardKey.keyW)) {
      _cx += fx * sp;
      _cy += fy * sp;
      valtozott = true;
    }
    if (_keys.contains(LogicalKeyboardKey.keyS)) {
      _cx -= fx * sp;
      _cy -= fy * sp;
      valtozott = true;
    }
    if (_keys.contains(LogicalKeyboardKey.keyA)) {
      _cx -= rx * sp;
      _cy -= ry * sp;
      valtozott = true;
    }
    if (_keys.contains(LogicalKeyboardKey.keyD)) {
      _cx += rx * sp;
      _cy += ry * sp;
      valtozott = true;
    }
    if (_keys.contains(LogicalKeyboardKey.keyR)) {
      _cz += sp;
      valtozott = true;
    }
    if (_keys.contains(LogicalKeyboardKey.keyF) ||
        _keys.contains(LogicalKeyboardKey.keyC)) {
      _cz -= sp;
      valtozott = true;
    }
    _cx = _cx.clamp(-30.0, 70.0);
    _cy = _cy.clamp(-40.0, 60.0);
    _cz = _cz.clamp(0.4, 45.0);

    final m = _match;
    if (_playing && m != null && m.frames.isNotEmpty) {
      final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
      _playhead += dt * fps * _speed;
      if (_playhead >= m.frames.length - 1) {
        _playhead = (m.frames.length - 1).toDouble();
        _playing = false;
      }
      valtozott = true;
    }
    // TV-kamera: sima követés — a kamera az oldalvonal felől tartja
    // képben a labdát (x-ben követi, a magasság és a távolság fix),
    // a nézés-irány mindig a labdára áll.
    if (_tvKamera && m != null && m.frames.isNotEmpty && dt > 0) {
      final labda = _aktualisAllapot(m).labda;
      if (labda != null) {
        final celX = labda.x.clamp(4.0, 36.0);
        const celY = -7.0, celZ = 4.5;
        final k = (dt * 2.5).clamp(0.0, 1.0);
        _cx += (celX - _cx) * k;
        _cy += (celY - _cy) * k;
        _cz += (celZ - _cz) * k;
        final dx = labda.x - _cx, dy = labda.y - _cy, dz = 0.6 - _cz;
        final vizszintes = math.sqrt(dx * dx + dy * dy);
        final celYaw = math.atan2(dx, dy);
        final celPitch = math.atan2(dz, vizszintes);
        _yaw += (celYaw - _yaw) * k;
        _pitch += (celPitch - _pitch) * k;
        valtozott = true;
      }
    }
    // Játékos-kamera: a kiválasztott mezszám mögött, a (simított)
    // haladási iránya felől — ha épp nem látszik, a kamera marad.
    if (_kovMez != null && m != null && m.frames.isNotEmpty && dt > 0) {
      _Jatekos? cel;
      for (final j in _aktualisAllapot(m).jatekosok) {
        if (j.mez == _kovMez && j.home == (_kovTeam == "home")) {
          cel = j;
          break;
        }
      }
      if (cel != null) {
        if (_kovElozoX != null && _kovElozoY != null) {
          final vx = (cel.x - _kovElozoX!) / dt;
          final vy = (cel.y - _kovElozoY!) / dt;
          final sebesseg = math.sqrt(vx * vx + vy * vy);
          if (sebesseg > 0.6) {
            // Erős simítás: a zajos követés ne rángassa a kamerát.
            final ks = (dt * 1.5).clamp(0.0, 1.0);
            _kovIranyX += (vx / sebesseg - _kovIranyX) * ks;
            _kovIranyY += (vy / sebesseg - _kovIranyY) * ks;
            final hossz = math.sqrt(
                _kovIranyX * _kovIranyX + _kovIranyY * _kovIranyY);
            if (hossz > 1e-6) {
              _kovIranyX /= hossz;
              _kovIranyY /= hossz;
            }
          }
        }
        _kovElozoX = cel.x;
        _kovElozoY = cel.y;
        final celKx = cel.x - _kovIranyX * 4.0;
        final celKy = cel.y - _kovIranyY * 4.0;
        const celKz = 2.2;
        final k = (dt * 3.0).clamp(0.0, 1.0);
        _cx += (celKx - _cx) * k;
        _cy += (celKy - _cy) * k;
        _cz += (celKz - _cz) * k;
        final dx = cel.x - _cx, dy = cel.y - _cy, dz = 1.3 - _cz;
        final viz = math.sqrt(dx * dx + dy * dy);
        final celYaw = math.atan2(dx, dy);
        final celPitch = math.atan2(dz, viz);
        // A yaw ±π-nél átfordulhat (a játékos irányt vált): a rövidebb
        // ívre igazítjuk, különben a kamera körbepördülne.
        var dYaw = celYaw - _yaw;
        while (dYaw > math.pi) {
          dYaw -= 2 * math.pi;
        }
        while (dYaw < -math.pi) {
          dYaw += 2 * math.pi;
        }
        _yaw += dYaw * k;
        _pitch += (celPitch - _pitch) * k;
        valtozott = true;
      }
    }
    // Keringés: a kamera a pálya közepe körüli gömbön, a közép felé néz.
    if (_kering) {
      final cp = math.cos(_kPhi);
      _cx = courtLength / 2 - _kR * math.sin(_kTheta) * cp;
      _cy = courtWidth / 2 - _kR * math.cos(_kTheta) * cp;
      _cz = _kR * math.sin(_kPhi);
      _yaw = _kTheta;
      _pitch = -_kPhi;
      valtozott = true;
    }
    // Játékos szemével: a fejében ülünk, a haladási irányába nézünk.
    if (_szemevel && m != null && m.frames.isNotEmpty && dt > 0) {
      final cel = _szemCel(_aktualisAllapot(m));
      if (cel != null) {
        _szemX = cel.x;
        _szemY = cel.y;
        if (cel.speed > 0.6) {
          final celIrany = math.atan2(cel.dirX, cel.dirY);
          var d = celIrany - _szemIrany;
          while (d > math.pi) {
            d -= 2 * math.pi;
          }
          while (d < -math.pi) {
            d += 2 * math.pi;
          }
          _szemIrany += d * (dt * 3).clamp(0.0, 1.0);
        }
      }
      _cx = _szemX + math.sin(_szemIrany) * 0.12;
      _cy = _szemY + math.cos(_szemIrany) * 0.12;
      _cz = 1.62;
      _yaw = _szemIrany + _szemYaw;
      _pitch = _szemPitch;
      valtozott = true;
    }
    if (valtozott && mounted) setState(() {});
  }

  /// A szemével-nézet célpontja a mostani állásban: azonos mezszám (ha
  /// van), különben a legutóbbi helyéhez legközelebbi csapattárs 3 m-en
  /// belül — null, ha épp nem látszik (a kamera ilyenkor marad).
  _Jatekos? _szemCel(_Allapot all) {
    if (_szemMez != null) {
      for (final j in all.jatekosok) {
        if (j.home == _szemHome && j.mez == _szemMez) return j;
      }
    }
    _Jatekos? legjobb;
    var tav = 3.0;
    for (final j in all.jatekosok) {
      if (j.home != _szemHome) continue;
      final d = math.sqrt(
          (j.x - _szemX) * (j.x - _szemX) + (j.y - _szemY) * (j.y - _szemY));
      if (d < tav) {
        tav = d;
        legjobb = j;
      }
    }
    return legjobb;
  }

  _Vetites _vetites() =>
      _Vetites(_cx, _cy, _cz, _yaw, _pitch, _nezetMeret);

  /// A mezszámos játékos megtett útja a kockák mentén (méter, kockánként
  /// a kezdettől). A tábla meccsenként, mezszámonként egyszer készül.
  List<double> _megtettUt(Match m, bool home, int mez) {
    if (!identical(_tavMeccs, m)) {
      _tavMeccs = m;
      _tavTabla.clear();
    }
    final kulcs = "${home ? "h" : "v"}$mez";
    return _tavTabla.putIfAbsent(kulcs, () {
      final ki = <double>[];
      double? ex, ey;
      var ossz = 0.0;
      final team = home ? Team.home : Team.away;
      for (final f in m.frames) {
        for (final p in f.players) {
          if (p.team != team || p.jerseyNumber != mez) continue;
          if (ex != null) {
            final d = math.sqrt((p.x - ex) * (p.x - ex) + (p.y - ey!) * (p.y - ey));
            if (d <= _tavUgrasM) ossz += d;
          }
          ex = p.x;
          ey = p.y;
          break;
        }
        ki.add(ossz);
      }
      return ki;
    });
  }

  /// A játékos-nézet HUD-ja: kinek a szemével, a sebessége (km/h) és a
  /// megtett útja eddig (csak mezszámmal — azonosító nélkül nincs út).
  String? _szemHud(Match m, _Allapot all) {
    if (!_szemevel) return null;
    final cel = _szemCel(all);
    if (cel == null) return null;
    final csapat = _szemHome ? m.meta.homeTeam : m.meta.awayTeam;
    final mez = _szemMez;
    var s = "$csapat${mez != null ? " #$mez" : ""} · "
        "${(cel.speed * 3.6).toStringAsFixed(1).replaceAll(".", ",")} km/h";
    if (mez != null && m.frames.isNotEmpty) {
      final ut = _megtettUt(m, _szemHome, mez);
      final i = _playhead.floor().clamp(0, ut.length - 1);
      final d = ut[i];
      s += d >= 1000
          ? " · ${(d / 1000).toStringAsFixed(2).replaceAll(".", ",")} km eddig"
          : " · ${d.round()} m eddig";
    }
    return s;
  }

  /// Keringés be/ki — onnan indul, ahol a kamera áll (nem ugrik).
  void _keringValt() {
    setState(() {
      if (_kering) {
        _kering = false;
        return;
      }
      final ox = _cx - courtLength / 2, oy = _cy - courtWidth / 2, oz = _cz;
      final r = math.sqrt(ox * ox + oy * oy + oz * oz).clamp(4.0, 80.0);
      _kR = r;
      _kPhi = math.asin((oz / r).clamp(-1.0, 1.0)).clamp(0.08, 1.5);
      _kTheta = math.atan2(-ox, -oy);
      _kering = true;
      _szemevel = false;
      _tvKamera = false;
      _kovMez = null;
    });
    _focus.requestFocus();
  }

  /// Koppintás a padlóra: lövés-mérés a pontból — vagy, ha egy
  /// lövéstérkép-körre esett, ugrás a lövéshez (4 mp-cel előtte,
  /// lejátszva) és a lövés számai a mérés-dobozban.
  void _meresKoppintas(Offset p) {
    if (_nezetMeret == Size.zero) return;
    final m = _match;
    if (m != null && _lovesKoppintas(m, p)) return;
    final pont = _vetites().padlo(p);
    if (pont == null ||
        pont.dx < -3 ||
        pont.dx > courtLength + 3 ||
        pont.dy < -3 ||
        pont.dy > courtWidth + 3) {
      return;
    }
    setState(() {
      _meres = pont;
      _lovesValasztott = null;
    });
  }

  /// A passz-események sorai az adó és a fogadó helyével (a passz
  /// kockájának játékosai, track_id szerint) — csak amelyiknek mindkét
  /// vége megvan.
  static List<Map<String, dynamic>> _passzSorok(
      Match m, List<Map<String, dynamic>> esemenyek) {
    final byT = {for (final f in m.frames) f.t: f};
    final ki = <Map<String, dynamic>>[];
    for (final e in esemenyek) {
      if (e["type"] != "pass") continue;
      final t = (e["t"] as num?)?.toInt();
      final ado = (e["player_id"] as num?)?.toInt();
      final fogado = ((e["detail"] as Map?)?["receiver_id"] as num?)?.toInt();
      final f = t == null ? null : byT[t];
      if (f == null || ado == null || fogado == null) continue;
      PlayerPosition? a, b;
      for (final p in f.players) {
        if (p.trackId == ado) a = p;
        if (p.trackId == fogado) b = p;
      }
      if (a == null || b == null) continue;
      ki.add({
        "t": t, "team": e["team"],
        "x1": a.x, "y1": a.y, "x2": b.x, "y2": b.y,
      });
    }
    return ki;
  }

  /// A passz-vonalak a festőnek: élő módban a PASSZ_S-en belüli passzok
  /// mellmagasságban, halványodva; háló módban a csapat minden passza a
  /// padlón, vékonyan.
  List<_PasszVonal> _passzVonalak(Match m) {
    if (_passz.isEmpty || m.frames.isEmpty) return const [];
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m);
    final ki = <_PasszVonal>[];
    for (final p in _passzok) {
      final home = p["team"] == "home";
      final t = ((p["t"] as num?) ?? 0).toDouble();
      double alpha, z;
      if (_passz == "elo") {
        final kora = (most - t) / fps;
        if (kora < 0 || kora > _passzS) continue;
        alpha = 1 - kora / _passzS;
        z = 1.0;
      } else {
        if (home != (_passz == "hazai")) continue;
        alpha = 0.35;
        z = 0.015;
      }
      ki.add(_PasszVonal(
          ((p["x1"] as num?) ?? 0).toDouble(),
          ((p["y1"] as num?) ?? 0).toDouble(),
          ((p["x2"] as num?) ?? 0).toDouble(),
          ((p["y2"] as num?) ?? 0).toDouble(),
          z, home, alpha));
    }
    return ki;
  }

  /// A lejátszófejnél aktív döntés-pillanat (−0,3…+2,5 mp a döntés körül),
  /// vagy null.
  Map<String, dynamic>? _aktivDontes(Match m) {
    if (_dontesekSz.isEmpty || m.frames.isEmpty) return null;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m) / fps;
    for (final d in _dontesekSz) {
      final s = ((d["s"] as num?) ?? 0).toDouble();
      if (most >= s - 0.3 && most <= s + 2.5) return d;
    }
    return null;
  }

  /// Ugrás az előző/következő döntés-pillanatra (1,5 mp-cel előtte,
  /// lejátszva) — a böngészős nézet ◀ ▶ gombjainak párja.
  void _dontesUgras(Match m, int irany) {
    final cel = _pillanatUgras(m, _dontesekSz, _dontesUtolso, irany);
    if (cel != null) _dontesUtolso = cel;
  }

  /// A szűrt pillanat-lista: a hibát elkövető csapat a `kulcs` mezőben
  /// (döntés: "team", szabad lövés: "defending", labdavesztés: "team").
  List<Map<String, dynamic>> _szurt(
          List<Map<String, dynamic>> lista, String kulcs) =>
      _jelenetCsapat.isEmpty
          ? lista
          : [for (final d in lista) if (d[kulcs] == _jelenetCsapat) d];
  List<Map<String, dynamic>> get _dontesekSz => _szurt(_dontesek, "team");
  List<Map<String, dynamic>> get _szabadokSz =>
      _szurt(_szabadok, "defending");
  List<Map<String, dynamic>> get _eladasokSz => _szurt(_eladasok, "team");

  /// Ugrás a jelenet-lista egy sorára (1,5 mp-cel előtte, lejátszva); a
  /// sor lapozója onnan lép tovább.
  void _jelenetUgras(Match m, SceneRow r) {
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    setState(() {
      if (r.tipus == "d") {
        _dontesUtolso = r.s;
      } else if (r.tipus == "sz") {
        _szabadUtolso = r.s;
      } else {
        _eladasUtolso = r.s;
      }
      _playhead = _tIndex(m, (r.s - 1.5) * fps).toDouble();
      _playing = true;
    });
    _focus.requestFocus();
  }

  /// A jelenet-lista panel: a szűrt jelenetek időrendben, a lapozók
  /// színével; az épp aktív (a legkésőbb indult) sor kiemelve.
  Widget _jelenetListaPanel(Match m) {
    final sorok = sceneRows(_dontesekSz, _szabadokSz, _eladasokSz,
        m.meta.homeTeam, m.meta.awayTeam);
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = m.frames.isEmpty ? 0.0 : _mostT(m) / fps;
    var aktiv = -1;
    for (var k = 0; k < sorok.length; k++) {
      if (most >= sorok[k].s - 0.3 && most <= sorok[k].s + 2.5) aktiv = k;
    }
    const szin = {"d": AppColors.gold, "sz": AppColors.away, "e": eladasSzin};
    return Container(
      width: 360,
      decoration: BoxDecoration(
        color: AppColors.surface.withOpacity(0.94),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.borderStrong),
      ),
      child: sorok.isEmpty
          ? Padding(
              padding: const EdgeInsets.all(10),
              child: Text("Nincs ilyen jelenet.",
                  style: AppText.label.copyWith(fontSize: 11.5)))
          : ListView.builder(
              padding: const EdgeInsets.all(6),
              itemCount: sorok.length,
              itemBuilder: (_, k) {
                final r = sorok[k];
                return InkWell(
                  onTap: () => _jelenetUgras(m, r),
                  child: Container(
                    color: k == aktiv ? AppColors.home.withOpacity(0.45) : null,
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                    child: Row(children: [
                      SizedBox(
                          width: 38,
                          child: Text(r.ido,
                              style: AppText.label.copyWith(fontSize: 11.5))),
                      Container(
                          width: 9,
                          height: 9,
                          decoration: BoxDecoration(
                              color: szin[r.tipus], shape: BoxShape.circle)),
                      const SizedBox(width: 7),
                      Expanded(
                          child: Text(r.szoveg,
                              style: AppText.label.copyWith(
                                  fontSize: 11.5,
                                  color: AppColors.textPrimary))),
                    ]),
                  ),
                );
              }),
    );
  }

  /// A közös pillanat-ugrás: a cél a lapozCel szerint (court_geometry),
  /// a lejátszófej 1,5 mp-cel elé, lejátszva. Visszaadja a cél idejét.
  double? _pillanatUgras(Match m, List<Map<String, dynamic>> lista,
      double? utolso, int irany) {
    if (lista.isEmpty || m.frames.isEmpty) return null;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m) / fps;
    final cel = lapozCel(
        [for (final d in lista) ((d["s"] as num?) ?? 0).toDouble()],
        most, utolso, irany);
    if (cel == null) return null;
    setState(() {
      _playhead = _tIndex(m, (cel - 1.5) * fps).toDouble();
      _playing = true;
    });
    _focus.requestFocus();
    return cel;
  }

  /// A lejátszófejnél aktív szabad lövés (−0,3…+2,5 mp), vagy null.
  Map<String, dynamic>? _aktivSzabad(Match m) {
    if (_szabadokSz.isEmpty || m.frames.isEmpty) return null;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m) / fps;
    for (final d in _szabadokSz) {
      final s = ((d["s"] as num?) ?? 0).toDouble();
      if (most >= s - 0.3 && most <= s + 2.5) return d;
    }
    return null;
  }

  /// Ugrás az előző/következő szabad lövésre (1,5 mp-cel előtte).
  void _szabadUgras(Match m, int irany) {
    final cel = _pillanatUgras(m, _szabadokSz, _szabadUtolso, irany);
    if (cel != null) _szabadUtolso = cel;
  }

  /// A szabad lövés felirata ("… szabadon hagyott lövő — a legközelebbi
  /// védő 3,4 m-re (GÓL, xG 0,42)").
  String? _szabadFelirat(Match m) {
    final d = _aktivSzabad(m);
    if (d == null) return null;
    final csapat =
        d["defending"] == "home" ? m.meta.homeTeam : m.meta.awayTeam;
    final tav = (d["dist"] as num?)?.toDouble();
    final xg = ((d["xg"] as num?) ?? 0).toDouble();
    return "$csapat védekezése: szabadon hagyott lövő — a legközelebbi védő "
        "${tav == null ? "nem mérhető" : "${tav.toStringAsFixed(1).replaceAll(".", ",")} m-re"}"
        " (${d["goal"] == true ? "GÓL" : "nem gól"}, xG "
        "${xg.toStringAsFixed(2).replaceAll(".", ",")})";
  }

  /// A lejátszófejnél aktív labdavesztés (−0,3…+2,5 mp), vagy null.
  Map<String, dynamic>? _aktivEladas(Match m) {
    if (_eladasokSz.isEmpty || m.frames.isEmpty) return null;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m) / fps;
    for (final d in _eladasokSz) {
      final s = ((d["s"] as num?) ?? 0).toDouble();
      if (most >= s - 0.3 && most <= s + 2.5) return d;
    }
    return null;
  }

  /// Ugrás az előző/következő labdavesztésre (1,5 mp-cel előtte).
  void _eladasUgras(Match m, int irany) {
    final cel = _pillanatUgras(m, _eladasokSz, _eladasUtolso, irany);
    if (cel != null) _eladasUtolso = cel;
  }

  /// A labdavesztés felirata ("Szeged labdavesztés — 7-es · a támadó
  /// harmadban · kipréselve (ellenfél 0,6 m-re) · 6,0 mp múlva kapott
  /// gól") — a böngészős nézet feliratának párja.
  String? _eladasFelirat(Match m) {
    final d = _aktivEladas(m);
    if (d == null) return null;
    String sz1(num v) => v.toDouble().toStringAsFixed(1).replaceAll(".", ",");
    final csapat = d["team"] == "home" ? m.meta.homeTeam : m.meta.awayTeam;
    final mez = d["jersey"];
    final ki = mez != null ? "$mez-es" : "ismeretlen játékos";
    const harmadok = {
      "saját": "a saját harmadban",
      "közép": "a középső harmadban",
      "támadó": "a támadó harmadban",
    };
    final hol = harmadok[d["zone"]] ?? "ismeretlen helyen";
    final tav = d["dist"] as num?;
    final nyomas = d["forced"] == null || tav == null
        ? "a nyomás nem mérhető"
        : (d["forced"] == true
            ? "kipréselve (ellenfél ${sz1(tav)} m-re)"
            : "magától (a legközelebbi ellenfél ${sz1(tav)} m-re)");
    final golMp = d["goal_after_s"] as num?;
    final gol = golMp != null ? " · ${sz1(golMp)} mp múlva kapott gól" : "";
    return "$csapat labdavesztés — $ki · $hol · $nyomas$gol";
  }

  /// A lejátszófejnél aktív gól-akció (az első passz −0,3 mp-étől a gól
  /// +2,5 mp-éig), vagy null.
  Map<String, dynamic>? _aktivGol(Match m) {
    if (_golok.isEmpty || m.frames.isEmpty) return null;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m) / fps;
    for (final g in _golok) {
      final s = ((g["s"] as num?) ?? 0).toDouble();
      final sg = ((g["goal_s"] as num?) ?? s).toDouble();
      if (most >= s - 0.3 && most <= sg + 2.5) return g;
    }
    return null;
  }

  /// Ugrás az előző/következő gól-akcióra (1,5 mp-cel az első passz előtt).
  void _golUgras(Match m, int irany) {
    final cel = _pillanatUgras(m, _golok, _golUtolso, irany);
    if (cel != null) _golUtolso = cel;
  }

  /// Az épp aktív pillanat-feliratok (szöveg, keretszín) a megjelenés
  /// sorrendjében: döntés, szabad lövés, labdavesztés.
  List<(String, Color)> _pillanatFeliratok(Match m) => [
        if (_dontesFelirat(m) case final d?) (d, AppColors.gold),
        if (_szabadFelirat(m) case final sz?) (sz, AppColors.away),
        if (_eladasFelirat(m) case final el?) (el, eladasSzin),
        if (_aktivGol(m) case final g?)
          (goalBuildUpCaption(g, m.meta.homeTeam, m.meta.awayTeam),
              AppColors.accent),
      ];

  /// A döntés-pillanat felirata ("jobb opció is volt: LÖVÉS (0,36) …").
  String? _dontesFelirat(Match m) {
    final d = _aktivDontes(m);
    if (d == null) return null;
    String sz(dynamic v) =>
        ((v as num?) ?? 0).toDouble().toStringAsFixed(2).replaceAll(".", ",");
    final jobb = d["best_kind"] == "shoot"
        ? "LÖVÉS (${sz(d["best_value"])})"
        : "passz a másik társhoz (${sz(d["best_value"])})";
    final csapat = d["team"] == "home" ? m.meta.homeTeam : m.meta.awayTeam;
    return "$csapat — jobb opció is volt: $jobb a választott passz "
        "(${sz(d["chosen_value"])}) helyett · különbség ${sz(d["gap"])}";
  }

  /// A labdás passzsávjai a pillanatnyi állásból (court_geometry.passLanes).
  ((bool, double, double), List<PassLane>)? _passzsavok(_Allapot all) {
    final l = all.labda;
    return passLanes([for (final j in all.jatekosok) (j.home, j.x, j.y)],
        l == null ? null : Offset(l.x, l.y));
  }

  /// A fal-rések az aktuális állásra: (rések, a védekező hazai?) — null,
  /// ha ki van kapcsolva, nincs szervezett támadás, vagy nem áll a fal.
  (WallGaps, bool)? _falresek(Match m, _Allapot all) {
    if (!_falres) return null;
    final elo = _eloFal(m);
    if (elo == null) return null;
    final home = elo["defending"] == "home";
    final r = wallGapSegments([
      for (final j in all.jatekosok) (j.home, j.x, j.y, !j.becsult, j.kapus)
    ], home, ((elo["goal_x"] as num?) ?? 0).toDouble());
    return r == null ? null : (r, home);
  }

  /// A fal-rés összegző ("Fal (Szeged, 6 védő): 2 nyitott rés — a
  /// legnagyobb 4,1 m") — a böngészős nézet összegzőjének párja.
  String? _falresOsszegzo(Match m, _Allapot all) {
    if (!_falres) return null;
    final elo = _eloFal(m);
    if (elo == null) return "Most nincs szervezett támadás — a fal nem áll.";
    final csapat =
        elo["defending"] == "home" ? m.meta.homeTeam : m.meta.awayTeam;
    final r = _falresek(m, all);
    if (r == null) {
      return "Fal ($csapat): nem áll — $wallGapMinDefenders mért védőnél "
          "kevesebb a kapu előtt.";
    }
    final g = r.$1;
    final nyilt = g.wide.where((w) => w).length;
    final max = g.maxGap.toStringAsFixed(1).replaceAll(".", ",");
    return nyilt > 0
        ? "Fal ($csapat, ${g.wall.length} védő): $nyilt nyitott rés — "
            "a legnagyobb $max m"
        : "Fal ($csapat, ${g.wall.length} védő): zárt — a legnagyobb rés "
            "$max m";
  }

  /// A passzsáv-összegző ("Labdás (Szeged): 3 nyitott, 1 kockázatos …").
  String? _passzsavOsszegzo(Match m, _Allapot all) {
    if (!_passzsav) return null;
    final r = _passzsavok(all);
    if (r == null) return "Most nincs labdás játékos.";
    final db = {"nyitott": 0, "kockázatos": 0, "zárt": 0};
    for (final l in r.$2) {
      db[l.grade] = (db[l.grade] ?? 0) + 1;
    }
    return "Labdás (${r.$1.$1 ? m.meta.homeTeam : m.meta.awayTeam}): "
        "${db["nyitott"]} nyitott, ${db["kockázatos"]} kockázatos, "
        "${db["zárt"]} zárt sáv";
  }

  /// A passz-háló összegzője ("38 passz — Szeged").
  String? _passzOsszegzo(Match m) {
    if (_passz != "hazai" && _passz != "vendeg") return null;
    final home = _passz == "hazai";
    final n = _passzok.where((p) => (p["team"] == "home") == home).length;
    return "$n passz — ${home ? m.meta.homeTeam : m.meta.awayTeam}";
  }

  /// A hőtérkép cellái a festőnek (a kiválasztott csapat(ok) rácsa, a
  /// legsűrűbb cellához mért erősséggel). A rács meccsenként egyszer
  /// készül; a mód-váltás csak a kiválogatást ismétli.
  List<_HoCella> _hoCellak(Match m) {
    if (_hoter.isEmpty) return const [];
    if (!identical(_hoMeccs, m)) {
      _hoMeccs = m;
      _hoHazai = computeTeamHeatmap(m, Team.home);
      _hoVendeg = computeTeamHeatmap(m, Team.away);
    }
    final cellak = <_HoCella>[];
    for (final (hm, home) in [(_hoHazai, true), (_hoVendeg, false)]) {
      if (hm == null || hm.maxCell <= 0) continue;
      if (_hoter != "mind" && _hoter != (home ? "hazai" : "vendeg")) continue;
      for (var iy = 0; iy < hm.binsY; iy++) {
        for (var ix = 0; ix < hm.binsX; ix++) {
          final e = hm.grid[iy][ix] / hm.maxCell;
          if (e > 0) cellak.add(_HoCella(ix, iy, hm.binsX, hm.binsY, e, home));
        }
      }
    }
    return cellak;
  }

  /// A labda útja az utolsó _nyomS másodpercben a lejátszófej előtt
  /// (pálya-méter), a kockák sorrendjében — a passz-sorozat és a lövés
  /// íve egyben látszik.
  List<Offset> _labdaNyom(Match m) {
    if (!_nyom || m.frames.isEmpty) return const [];
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m);
    final elso = _tIndex(m, most - _nyomS * fps);
    final pontok = <Offset>[];
    for (var i = elso; i < m.frames.length && m.frames[i].t <= most; i++) {
      final l = m.frames[i].ball;
      if (l != null) pontok.add(Offset(l.x, l.y));
    }
    return pontok;
  }

  /// A lejátszófejnél látható lövések (a térkép módja szerint).
  List<Map<String, dynamic>> _lathatoLovesek(Match m) {
    if (_lovesTerkep.isEmpty) return const [];
    final most = _mostT(m);
    return [
      for (final l in _lovesek)
        if (_lovesTerkep == "mind" ||
            (_lovesTerkep == "eddig" && ((l["t"] as num?) ?? 0) <= most) ||
            (_lovesTerkep == "hazai" && l["team"] == "home") ||
            (_lovesTerkep == "vendeg" && l["team"] == "away"))
          l
    ];
  }

  /// A lövés-kör sugara a padlón (méter): az xG-vel nő — ugyanaz, mint
  /// a böngészős nézetben (0,22 + 0,5·xG).
  static double _lovesSugar(Map<String, dynamic> l) =>
      0.22 + 0.5 * (((l["xg"] as num?) ?? 0).toDouble()).clamp(0.0, 1.0);

  /// Koppintás egy lövés-körre: igaz, ha talált (és odaugrott).
  bool _lovesKoppintas(Match m, Offset p) {
    final v = _vetites();
    Map<String, dynamic>? cel;
    var legjobb = double.infinity;
    for (final l in _lathatoLovesek(m)) {
      final x = ((l["x"] as num?) ?? 0).toDouble();
      final y = ((l["y"] as num?) ?? 0).toDouble();
      final o = v.kepernyo(x, y, 0.02);
      if (o == null) continue;
      // A kör képernyő-sugara: a szélső pont vetítve; legalább 12 px,
      // hogy messziről is el lehessen találni.
      final szel = v.kepernyo(x + _lovesSugar(l), y, 0.02);
      final r = math.max(12.0, szel == null ? 12.0 : (szel - o).distance);
      final d = (o - p).distance;
      if (d <= r && d < legjobb) {
        legjobb = d;
        cel = l;
      }
    }
    final l = cel;
    if (l == null) return false;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final t = ((l["t"] as num?) ?? 0).toDouble();
    setState(() {
      _meres = Offset(((l["x"] as num?) ?? 0).toDouble(),
          ((l["y"] as num?) ?? 0).toDouble());
      _lovesValasztott = l;
      _playhead = _tIndex(m, t - 4.0 * fps).toDouble();
      _playing = true;
      _kovMez = null;
    });
    return true;
  }

  /// Dupla koppintás egy figurára: az ő szemével, vele együtt.
  void _szemValasztas(Match m, Offset p) {
    if (_nezetMeret == Size.zero) return;
    final v = _vetites();
    _Jatekos? cel;
    var tav = 45.0; // képpont
    for (final j in _aktualisAllapot(m).jatekosok) {
      final o = v.kepernyo(j.x, j.y, 1.0);
      if (o == null) continue;
      final d = (o - p).distance;
      if (d < tav) {
        tav = d;
        cel = j;
      }
    }
    final c = cel;
    if (c == null) return;
    setState(() {
      _szemevel = true;
      _szemHome = c.home;
      _szemMez = c.mez;
      _szemX = c.x;
      _szemY = c.y;
      _szemIrany = c.speed > 0.6 ? math.atan2(c.dirX, c.dirY) : _yaw;
      _szemYaw = 0;
      _szemPitch = -0.05;
      _kering = false;
      _tvKamera = false;
      _kovMez = null;
      _playing = true;
    });
    _focus.requestFocus();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent e) {
    final k = e.logicalKey;
    if (e is KeyDownEvent) {
      if (k == LogicalKeyboardKey.space) {
        setState(() => _playing = !_playing);
        return KeyEventResult.handled;
      }
      if (k == LogicalKeyboardKey.keyO) {
        _keringValt();
        return KeyEventResult.handled;
      }
      // T — TV-kamera be/ki (a böngészős nézet T gombjának párja).
      if (k == LogicalKeyboardKey.keyT) {
        setState(() {
          _tvKamera = !_tvKamera;
          _kovMez = null;
          _kering = false;
          _szemevel = false;
          if (_tvKamera && !_playing) _playing = true;
        });
        return KeyEventResult.handled;
      }
      if (k == LogicalKeyboardKey.escape) {
        setState(() {
          if (_szemevel) {
            _szemevel = false;
            _cz = math.max(_cz, 1.7);
          } else {
            _meres = null;
            _lovesValasztott = null;
          }
        });
        return KeyEventResult.handled;
      }
      _keys.add(k);
      // Bármely mozgás-billentyű: a felhasználó vezeti a kamerát.
      if (const [
        LogicalKeyboardKey.keyW,
        LogicalKeyboardKey.keyA,
        LogicalKeyboardKey.keyS,
        LogicalKeyboardKey.keyD,
        LogicalKeyboardKey.keyR,
        LogicalKeyboardKey.keyF,
        LogicalKeyboardKey.keyC,
      ].contains(k)) {
        _tvKamera = false;
        _kovMez = null;
        _kering = false;
        _szemevel = false;
      }
    } else if (e is KeyUpEvent) {
      _keys.remove(k);
    }
    const sajat = [
      LogicalKeyboardKey.keyW,
      LogicalKeyboardKey.keyA,
      LogicalKeyboardKey.keyS,
      LogicalKeyboardKey.keyD,
      LogicalKeyboardKey.keyR,
      LogicalKeyboardKey.keyF,
      LogicalKeyboardKey.keyC,
    ];
    return sajat.contains(k)
        ? KeyEventResult.handled
        : KeyEventResult.ignored;
  }

  void _nezet(double x, double y, double z, double yaw, double pitch) {
    setState(() {
      _tvKamera = false;
      _kovMez = null;
      _kering = false;
      _szemevel = false;
      _cx = x;
      _cy = y;
      _cz = z;
      _yaw = yaw;
      _pitch = pitch;
    });
    _focus.requestFocus();
  }

  // ------------------------------------------------------------ felület

  @override
  Widget build(BuildContext context) {
    final m = _match;
    return AppShell(
      active: NavId.court3d,
      crumbTag: "3d",
      crumbPath: "3D PÁLYA · SZABAD BEJÁRÁS",
      child: m == null
          ? Center(
              child: _loading
                  ? const CircularProgressIndicator()
                  : Text(_err ?? "Nincs betöltött meccs",
                      style: AppText.label))
          : Column(
              children: [
                _fejlec(m),
                const SizedBox(height: AppSpacing.sm),
                Expanded(child: _nezetTer(m)),
                const SizedBox(height: AppSpacing.sm),
                _lejatszoSav(m),
              ],
            ),
    );
  }

  /// A böngészős (WebXR-képes) 3D nézet megnyitása az alapértelmezett
  /// böngészőben. VR-headsethez ugyanez az oldal kell: a WebXR
  /// biztonságos környezetet kér, a localhost az — Quest-féle headsetről
  /// USB-kábellel és "adb reverse"-szel érhető el.
  Future<void> _bongeszos3d() async {
    // A 3D fül AKTUÁLIS pillanatát és beállításait visszük át: a
    // böngészős nézet ugyanott, ugyanazzal a kamerával és rétegekkel
    // folytatja, ahol az appban tartasz. Az idő a kocka t címkéjéből
    // (videó-mp) — a lejátszófej lista-INDEX, vágott meccsen nem ugyanaz.
    final m = _match;
    final fpsB = (m != null && m.meta.fps > 0) ? m.meta.fps : 25.0;
    final tS = (m == null ? 0.0 : _mostT(m) / fpsB).toStringAsFixed(1);
    final q = <String, String>{"t": tS};
    if (_kovMez != null) q["kamera"] = "${_kovTeam == "home" ? "h" : "v"}$_kovMez";
    if (_tvKamera && _kovMez == null) q["tv"] = "1";
    if (_hoter.isNotEmpty) q["hoter"] = _hoter;
    if (_lovesTerkep.isNotEmpty) q["loves"] = _lovesTerkep;
    if (_passz.isNotEmpty) q["passz"] = _passz;
    if (_fal.isNotEmpty) q["fal"] = _fal;
    if (_falOldal != "auto") q["falOldal"] = _falOldal;
    if (_nyom) q["nyom"] = "1";
    if (_passzsav) q["passzsav"] = "1";
    if (_falres) q["falres"] = "1";
    if (_speed != 1.0) q["seb"] = _speed.toString();
    final url = Uri.parse("${_api.baseUrl}/matches/$_matchId/view3d")
        .replace(queryParameters: q)
        .toString();
    try {
      if (Platform.isMacOS) {
        await Process.run("open", [url]);
      } else if (Platform.isWindows) {
        await Process.run("cmd", ["/c", "start", "", url]);
      } else {
        await Process.run("xdg-open", [url]);
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Megnyitva a böngészőben: $url — VR-headsetben "
              "ugyanez a cím megy (internet kell hozzá).")));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Nyisd meg kézzel a böngészőben: $url")));
    }
  }

  Widget _fejlec(Match m) {
    return Row(children: [
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text("${m.meta.homeTeam} vs ${m.meta.awayTeam}",
                style: AppText.value.copyWith(fontSize: 16)),
            if (_demo) ...[
              const SizedBox(width: AppSpacing.md),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.gold.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: AppColors.gold.withOpacity(0.5)),
                ),
                child: Text("DEMÓ — elemezz egy meccset, és az jön ide",
                    style: AppText.label
                        .copyWith(fontSize: 10.5, color: AppColors.gold)),
              ),
            ],
          ]),
          Text(
              "WASD — mozgás · egér-húzás — nézelődés · R/F (C) — fel/le · "
              "Shift — gyors · Szóköz — lejátszás · O — keringés · "
              "dupla katt egy játékosra — az ő szemével (Esc) · "
              "katt a padlóra — lövés-mérés · lövéstérkép: katt egy körre — "
              "odaugrik",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
      if (_matchId != null)
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: OutlinedButton.icon(
            onPressed: _bongeszos3d,
            icon: const Icon(Icons.public, size: 16),
            label: const Text("Böngészős 3D / VR",
                style: TextStyle(fontSize: 12)),
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.textSecondary,
              side: const BorderSide(color: AppColors.borderStrong),
            ),
          ),
        ),
      if (_matches.isNotEmpty)
        DropdownButton<String>(
          value: _matchId,
          hint: Text("Meccs", style: AppText.label),
          dropdownColor: AppColors.surface,
          items: [
            for (final r in _matches)
              DropdownMenuItem(
                value: r["match_id"] as String,
                child: Text(
                    "${r["home_team"]} vs ${r["away_team"]} "
                    "(${r["match_id"]})",
                    style: AppText.label.copyWith(fontSize: 12.5)),
              ),
          ],
          onChanged: (v) {
            if (v != null) _open(v);
          },
        ),
    ]);
  }

  Widget _nezetTer(Match m) {
    return Focus(
      focusNode: _focus,
      autofocus: true,
      onKeyEvent: _onKey,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: Container(
          decoration: BoxDecoration(
            color: const Color(0xFF0A0E14),
            border: Border.all(color: AppColors.border),
            borderRadius: BorderRadius.circular(14),
          ),
          child: LayoutBuilder(builder: (context, korlat) {
            _nezetMeret = Size(korlat.maxWidth, korlat.maxHeight);
            final allapot = _aktualisAllapot(m);
            final fal = _falAllapot(m, allapot);
            final rejtett = _szemevel ? _szemCel(allapot) : null;
            return Stack(children: [
              // A gesztusok CSAK a 3D képen ülnek: a gombok testvérek
              // fölötte — különben a dupla-koppintás felismerő minden
              // gombnyomást a dupla-koppintás idejéig (300 ms) visszatart.
              Positioned.fill(child: _gesztusok(m, CustomPaint(
                painter: _Court3DPainter(
                  frame: allapot,
                  cx: _cx,
                  cy: _cy,
                  cz: _cz,
                  yaw: _yaw,
                  pitch: _pitch,
                  meres: _meres,
                  meresBalKapu: _lovesValasztott == null
                      ? null
                      : _lovesValasztott!["team"] == "away",
                  falPontok: fal.$1,
                  feltoresSav: fal.$3,
                  nyom: _labdaNyom(m),
                  hoCellak: _hoCellak(m),
                  passzok: _passzVonalak(m),
                  passzsavok: _passzsav ? _passzsavok(allapot) : null,
                  falresek: _falresek(m, allapot)?.$1,
                  dontes: _aktivDontes(m),
                  szabad: _aktivSzabad(m),
                  szabadSugar: _szabadSugar,
                  eladas: _aktivEladas(m),
                  gol: _aktivGol(m),
                  eladasSugar: _eladasSugar,
                  lovesek: [
                    for (final l in _lathatoLovesek(m))
                      _LovesJel(
                          ((l["x"] as num?) ?? 0).toDouble(),
                          ((l["y"] as num?) ?? 0).toDouble(),
                          _lovesSugar(l),
                          l["team"] == "home",
                          l["outcome"] == "goal")
                  ],
                  rejtett: rejtett,
                ),
              ))),
              // Az eszköz-panel a kép jobb szélén: magasság-korláttal
              // GÖRGETHETŐ (a rétegek szaporodtával a kép alá lógott, és
              // az alsó gombok — Madártávlat, … — kattinthatatlanok
              // lettek), és összecsukható, hogy ne takarja a pályát. A
              // lövéstérkép és a passz-háló összegzője a panel ALATT, az
              // oszlop alján ül: korábban külön rétegként a panel aljára
              // rajzolódott, és eltakarta az alsó gombokat.
              Positioned(
                right: 10,
                top: 10,
                bottom: 10,
                // A kapcsoló RÖGZÍTETT (nem görög el a panellel), alatta
                // a görgethető gomb-oszlop.
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: TextButton.icon(
                          onPressed: () {
                            setState(
                                () => _eszkozokNyitva = !_eszkozokNyitva);
                            _focus.requestFocus();
                          },
                          icon: Icon(
                              _eszkozokNyitva
                                  ? Icons.expand_less
                                  : Icons.expand_more,
                              size: 18),
                          label: Text(
                              _eszkozokNyitva ? "Eszközök ▴" : "Eszközök ▾",
                              style: const TextStyle(fontSize: 11.5)),
                        ),
                      ),
                      Expanded(
                          child: Align(
                              alignment: Alignment.topRight,
                              child: _eszkozokNyitva
                                  ? SingleChildScrollView(
                                      child: _nezetGombok())
                                  : const SizedBox.shrink())),
                      if (_passzOsszegzo(m) != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: _infoDoboz(
                              [_passzOsszegzo(m)!], AppColors.accent),
                        ),
                      if (_lovesTerkep.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: _infoDoboz(
                              _lovesOsszegzo(m), AppColors.accent),
                        ),
                    ]),
              ),
              if (_szemHud(m, allapot) != null)
                Positioned(
                  top: 12,
                  left: 0,
                  right: 0,
                  child: Center(
                      child: _infoDoboz([_szemHud(m, allapot)!],
                          AppColors.accent)),
                ),
              if (_meres != null)
                Positioned(left: 12, top: 12, child: _meresDoboz(_meres!)),
              if (fal.$2.isNotEmpty)
                Positioned(
                  left: 12,
                  top: _meres != null ? 104 : 12,
                  child: _infoDoboz(fal.$2, AppColors.gold),
                ),
              if (_passzsavOsszegzo(m, allapot) != null ||
                  _falresOsszegzo(m, allapot) != null)
                Positioned(
                  left: 12,
                  bottom: 56,
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (_falresOsszegzo(m, allapot) case final f?)
                          _infoDoboz([f], AppColors.away),
                        if (_falresOsszegzo(m, allapot) != null &&
                            _passzsavOsszegzo(m, allapot) != null)
                          const SizedBox(height: 6),
                        if (_passzsavOsszegzo(m, allapot) case final ps?)
                          _infoDoboz([ps], AppColors.accent),
                      ]),
                ),
              // Jelenet-felirat: mi történik épp (a közvetítés
              // inzertje) — a 3D-ben a labda pályája önmagában nem
              // mondja meg, hogy gól volt-e vagy védés.
              if (_jelenetListaNyitva)
                Positioned(
                    left: 12,
                    top: 12,
                    bottom: 60,
                    child: _jelenetListaPanel(m)),
              // A döntés-, a szabad-lövés és a labdavesztés felirat EGYMÁS
              // ALATT: egyszerre aktív pillanatok nem takarhatják el
              // egymást.
              if (_pillanatFeliratok(m).isNotEmpty)
                Positioned(
                  top: 12,
                  left: 0,
                  right: 0,
                  child: Center(
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                    for (final (i, (szoveg, szin))
                        in _pillanatFeliratok(m).indexed) ...[
                      if (i > 0) const SizedBox(height: 6),
                      _infoDoboz([szoveg], szin),
                    ],
                  ])),
                ),
              if (_esemenyFelirat(m) != null)
                Positioned(
                  left: 12,
                  bottom: 12,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: AppColors.surface.withOpacity(0.85),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppColors.gold),
                    ),
                    child: Text(_esemenyFelirat(m)!,
                        style: AppText.value.copyWith(
                            fontSize: 14, color: AppColors.gold)),
                  ),
                ),
            ]);
          }),
        ),
      ),
    );
  }

  /// A 3D kép gesztusai. A húzás a skála-gesztusban (onScaleUpdate): egy
  /// ujj/egér nézelődik vagy keringtet, két ujj vagy a trackpad csípése
  /// közelít. Koppintás a padlóra: lövés-mérés; dupla koppintás egy
  /// figurára: az ő szemével. Görgetés: előre ugrás / közelítés.
  Widget _gesztusok(Match m, Widget kep) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) => _focus.requestFocus(),
      onTapUp: (d) => _meresKoppintas(d.localPosition),
      onDoubleTapDown: (d) => _dupla = d.localPosition,
      onDoubleTap: () {
        final p = _dupla;
        if (p != null) _szemValasztas(m, p);
      },
      onScaleStart: (_) => _csipesR0 = _kR,
      onScaleUpdate: (d) {
        setState(() {
          if (d.scale != 1.0 && d.pointerCount >= 2) {
            if (_kering) {
              _kR = (_csipesR0 / d.scale).clamp(4.0, 80.0);
            }
            return;
          }
          final dx = d.focalPointDelta.dx, dy = d.focalPointDelta.dy;
          if (_kering) {
            _kTheta += dx * 0.006;
            _kPhi = (_kPhi + dy * 0.006).clamp(0.08, 1.5);
          } else if (_szemevel) {
            _szemYaw += dx * 0.004;
            _szemPitch = (_szemPitch - dy * 0.004).clamp(-1.2, 1.2);
          } else {
            _tvKamera = false;
            _kovMez = null;
            _yaw += dx * 0.005;
            _pitch = (_pitch - dy * 0.005).clamp(-1.45, 1.45);
          }
        });
      },
      child: Listener(
        onPointerSignal: (s) {
          if (s is PointerScrollEvent) {
            setState(() {
              if (_kering) {
                // Keringésben a görgetés közelít/távolít.
                _kR = (_kR * math.exp(s.scrollDelta.dy * 0.0012))
                    .clamp(4.0, 80.0);
                return;
              }
              if (_szemevel) return;
              // Görgetés: előre/hátra a nézés irányában (zoom-érzés).
              final lep = -s.scrollDelta.dy / 120.0;
              _cx += math.sin(_yaw) * math.cos(_pitch) * lep;
              _cy += math.cos(_yaw) * math.cos(_pitch) * lep;
              _cz = (_cz + math.sin(_pitch) * lep).clamp(0.4, 45.0);
            });
          }
        },
        child: kep,
      ),
    );
  }

  Widget _nezetGombok() {
    Widget gomb(String cimke, VoidCallback f) => Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: OutlinedButton(
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.textSecondary,
              side: const BorderSide(color: AppColors.borderStrong),
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            ),
            onPressed: f,
            child: Text(cimke, style: const TextStyle(fontSize: 11.5)),
          ),
        );
    return Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor:
                _tvKamera ? AppColors.accent : AppColors.surfaceAlt,
            foregroundColor:
                _tvKamera ? AppColors.onAccent : AppColors.textSecondary,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          ),
          onPressed: () {
            setState(() {
              _tvKamera = !_tvKamera;
              _kovMez = null;
              if (_tvKamera && !_playing) _playing = true;
            });
            _focus.requestFocus();
          },
          child: Text(_tvKamera ? "TV-kamera: BE" : "TV-kamera (labda)",
              style: const TextStyle(fontSize: 11.5)),
        ),
      ),
      // Játékos-kamera: mezszám-választó (csak ha van mezszám-adat).
      if (_mezekHome.isNotEmpty || _mezekAway.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            decoration: BoxDecoration(
              color: _kovMez != null
                  ? AppColors.accent.withOpacity(0.18)
                  : AppColors.surfaceAlt,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.borderStrong),
            ),
            child: DropdownButton<String>(
              value: _kovMez == null ? null : "$_kovTeam-$_kovMez",
              hint: Text("Játékos-kamera",
                  style: AppText.label.copyWith(fontSize: 11.5)),
              underline: const SizedBox.shrink(),
              dropdownColor: AppColors.surface,
              items: [
                const DropdownMenuItem(
                    value: "-", child: Text("kikapcsolva")),
                for (final mez in _mezekHome)
                  DropdownMenuItem(
                      value: "home-$mez",
                      child: Text("Hazai $mez",
                          style: const TextStyle(
                              fontSize: 12, color: AppColors.home))),
                for (final mez in _mezekAway)
                  DropdownMenuItem(
                      value: "away-$mez",
                      child: Text("Vendég $mez",
                          style: const TextStyle(
                              fontSize: 12, color: AppColors.away))),
              ],
              onChanged: (v) {
                setState(() {
                  if (v == null || v == "-") {
                    _kovMez = null;
                  } else {
                    final d = v.split("-");
                    _kovTeam = d[0];
                    _kovMez = int.tryParse(d[1]);
                    _kovElozoX = null;
                    _kovElozoY = null;
                    _tvKamera = false;
                    if (!_playing) _playing = true;
                  }
                });
                _focus.requestFocus();
              },
            ),
          ),
        ),
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor:
                _kering ? AppColors.accent : AppColors.surfaceAlt,
            foregroundColor:
                _kering ? AppColors.onAccent : AppColors.textSecondary,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          ),
          onPressed: _keringValt,
          child: Text(_kering ? "Keringés: BE (O)" : "Keringés (O)",
              style: const TextStyle(fontSize: 11.5)),
        ),
      ),
      if (_szemevel)
        gomb("Játékos szemével ✕ (Esc)", () {
          setState(() {
            _szemevel = false;
            _cz = math.max(_cz, 1.7);
          });
          _focus.requestFocus();
        }),
      // Védekezés-panel: tankönyvi fal a kapu elé, vagy az élő fal.
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            color: _fal.isNotEmpty
                ? AppColors.gold.withOpacity(0.15)
                : AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.borderStrong),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            DropdownButton<String>(
              value: _fal,
              underline: const SizedBox.shrink(),
              dropdownColor: AppColors.surface,
              style: AppText.label.copyWith(fontSize: 11.5),
              items: const [
                DropdownMenuItem(value: "", child: Text("Védekezés: ki")),
                DropdownMenuItem(value: "elo", child: Text("Élő fal")),
                DropdownMenuItem(value: "6-0", child: Text("6-0 sablon")),
                DropdownMenuItem(value: "5-1", child: Text("5-1 sablon")),
                DropdownMenuItem(value: "4-2", child: Text("4-2 sablon")),
                DropdownMenuItem(value: "3-2-1", child: Text("3-2-1 sablon")),
              ],
              onChanged: (v) {
                setState(() => _fal = v ?? "");
                _focus.requestFocus();
              },
            ),
            if (_fal.isNotEmpty) ...[
              const SizedBox(width: 6),
              DropdownButton<String>(
                value: _falOldal,
                underline: const SizedBox.shrink(),
                dropdownColor: AppColors.surface,
                style: AppText.label.copyWith(fontSize: 11.5),
                items: const [
                  DropdownMenuItem(value: "auto", child: Text("védett kapu")),
                  DropdownMenuItem(value: "bal", child: Text("bal kapu")),
                  DropdownMenuItem(value: "jobb", child: Text("jobb kapu")),
                ],
                onChanged: (v) {
                  setState(() => _falOldal = v ?? "auto");
                  _focus.requestFocus();
                },
              ),
            ],
          ]),
        ),
      ),
      // Passzok: a futó passz vonala, vagy a csapat passz-hálója a padlón.
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            color: _passz.isNotEmpty
                ? AppColors.accent.withOpacity(0.15)
                : AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.borderStrong),
          ),
          child: DropdownButton<String>(
            value: _passz,
            underline: const SizedBox.shrink(),
            dropdownColor: AppColors.surface,
            style: AppText.label.copyWith(fontSize: 11.5),
            items: const [
              DropdownMenuItem(value: "", child: Text("Passzok: ki")),
              DropdownMenuItem(value: "elo", child: Text("Élő passz")),
              DropdownMenuItem(
                  value: "hazai", child: Text("Hazai passz-háló")),
              DropdownMenuItem(
                  value: "vendeg", child: Text("Vendég passz-háló")),
            ],
            onChanged: (v) {
              setState(() => _passz = v ?? "");
              _focus.requestFocus();
            },
          ),
        ),
      ),
      // Hőtérkép: hol tartózkodott a csapat (az elemzés rácsa a padlón).
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            color: _hoter.isNotEmpty
                ? AppColors.accent.withOpacity(0.15)
                : AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.borderStrong),
          ),
          child: DropdownButton<String>(
            value: _hoter,
            underline: const SizedBox.shrink(),
            dropdownColor: AppColors.surface,
            style: AppText.label.copyWith(fontSize: 11.5),
            items: const [
              DropdownMenuItem(value: "", child: Text("Hőtérkép: ki")),
              DropdownMenuItem(value: "hazai", child: Text("Hazai hőtérkép")),
              DropdownMenuItem(
                  value: "vendeg", child: Text("Vendég hőtérkép")),
              DropdownMenuItem(value: "mind", child: Text("Mindkét csapat")),
            ],
            onChanged: (v) {
              setState(() => _hoter = v ?? "");
              _focus.requestFocus();
            },
          ),
        ),
      ),
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor:
                _passzsav ? AppColors.accent : AppColors.surfaceAlt,
            foregroundColor:
                _passzsav ? AppColors.onAccent : AppColors.textSecondary,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          ),
          onPressed: () {
            setState(() => _passzsav = !_passzsav);
            _focus.requestFocus();
          },
          child: Text(_passzsav ? "Passzsávok: BE" : "Passzsávok",
              style: const TextStyle(fontSize: 11.5)),
        ),
      ),
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor:
                _falres ? AppColors.accent : AppColors.surfaceAlt,
            foregroundColor:
                _falres ? AppColors.onAccent : AppColors.textSecondary,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          ),
          onPressed: () {
            setState(() => _falres = !_falres);
            _focus.requestFocus();
          },
          child: Text(_falres ? "Fal-rések: BE" : "Fal-rések",
              style: const TextStyle(fontSize: 11.5)),
        ),
      ),
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: _nyom ? AppColors.accent : AppColors.surfaceAlt,
            foregroundColor:
                _nyom ? AppColors.onAccent : AppColors.textSecondary,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          ),
          onPressed: () {
            setState(() => _nyom = !_nyom);
            _focus.requestFocus();
          },
          child: Text(_nyom ? "Labda-nyom: BE" : "Labda-nyom (3 mp)",
              style: const TextStyle(fontSize: 11.5)),
        ),
      ),
      // Lövéstérkép: a meccs lövései a padlón (kör = xG, arany gyűrű = gól).
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            color: _lovesTerkep.isNotEmpty
                ? AppColors.accent.withOpacity(0.15)
                : AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.borderStrong),
          ),
          child: DropdownButton<String>(
            value: _lovesTerkep,
            underline: const SizedBox.shrink(),
            dropdownColor: AppColors.surface,
            style: AppText.label.copyWith(fontSize: 11.5),
            items: const [
              DropdownMenuItem(value: "", child: Text("Lövéstérkép: ki")),
              DropdownMenuItem(value: "mind", child: Text("Minden lövés")),
              DropdownMenuItem(
                  value: "eddig", child: Text("Lövések eddig")),
              DropdownMenuItem(value: "hazai", child: Text("Hazai lövések")),
              DropdownMenuItem(
                  value: "vendeg", child: Text("Vendég lövések")),
            ],
            onChanged: (v) {
              setState(() => _lovesTerkep = v ?? "");
              _focus.requestFocus();
            },
          ),
        ),
      ),
      // Kinek a hibái: a jelenet-lapozók csapat-szűrője.
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            color: _jelenetCsapat.isNotEmpty
                ? AppColors.accent.withOpacity(0.15)
                : AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.borderStrong),
          ),
          child: DropdownButton<String>(
            value: _jelenetCsapat,
            underline: const SizedBox.shrink(),
            dropdownColor: AppColors.surface,
            style: AppText.label.copyWith(fontSize: 11.5),
            items: [
              const DropdownMenuItem(
                  value: "", child: Text("Hibák: mindkét csapat")),
              DropdownMenuItem(
                  value: "home",
                  child: Text("Hibák: ${_match?.meta.homeTeam ?? "hazai"}")),
              DropdownMenuItem(
                  value: "away",
                  child: Text("Hibák: ${_match?.meta.awayTeam ?? "vendég"}")),
            ],
            onChanged: (v) {
              setState(() {
                _jelenetCsapat = v ?? "";
                _dontesUtolso = null;
                _szabadUtolso = null;
                _eladasUtolso = null;
              });
              _focus.requestFocus();
            },
          ),
        ),
      ),
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: _jelenetListaNyitva
                ? AppColors.accent
                : AppColors.surfaceAlt,
            foregroundColor: _jelenetListaNyitva
                ? AppColors.onAccent
                : AppColors.textSecondary,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          ),
          onPressed: () {
            setState(() => _jelenetListaNyitva = !_jelenetListaNyitva);
            _focus.requestFocus();
          },
          child: Text(
              _jelenetListaNyitva ? "Jelenet-lista: BE" : "Jelenet-lista",
              style: const TextStyle(fontSize: 11.5)),
        ),
      ),
      // Döntés-pillanatok: ahol jobb opció is volt (◀ ▶).
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text("Döntések:", style: AppText.label.copyWith(fontSize: 11.5)),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: "Előző döntés-pillanat",
            onPressed: _dontesekSz.isEmpty || _match == null
                ? null
                : () => _dontesUgras(_match!, -1),
            icon: const Icon(Icons.chevron_left, size: 20),
          ),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: "Következő döntés-pillanat",
            onPressed: _dontesekSz.isEmpty || _match == null
                ? null
                : () => _dontesUgras(_match!, 1),
            icon: const Icon(Icons.chevron_right, size: 20),
          ),
          Text(_dontesekSz.isEmpty ? "nincs" : "${_dontesekSz.length}",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
      // Szabad lövők: a fedezés-hibák (◀ ▶).
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text("Szabad lövők:", style: AppText.label.copyWith(fontSize: 11.5)),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: "Előző szabadon hagyott lövő",
            onPressed: _szabadokSz.isEmpty || _match == null
                ? null
                : () => _szabadUgras(_match!, -1),
            icon: const Icon(Icons.chevron_left, size: 20),
          ),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: "Következő szabadon hagyott lövő",
            onPressed: _szabadokSz.isEmpty || _match == null
                ? null
                : () => _szabadUgras(_match!, 1),
            icon: const Icon(Icons.chevron_right, size: 20),
          ),
          Text(_szabadokSz.isEmpty ? "nincs" : "${_szabadokSz.length}",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
      // Labdavesztések: ki, hol, kipréselve vagy magától (◀ ▶).
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text("Labdavesztések:",
              style: AppText.label.copyWith(fontSize: 11.5)),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: "Előző labdavesztés",
            onPressed: _eladasokSz.isEmpty || _match == null
                ? null
                : () => _eladasUgras(_match!, -1),
            icon: const Icon(Icons.chevron_left, size: 20),
          ),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: "Következő labdavesztés",
            onPressed: _eladasokSz.isEmpty || _match == null
                ? null
                : () => _eladasUgras(_match!, 1),
            icon: const Icon(Icons.chevron_right, size: 20),
          ),
          Text(_eladasokSz.isEmpty ? "nincs" : "${_eladasokSz.length}",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
      // Gól-akciók: a gólt megelőző passz-lánc (◀ ▶).
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text("Gól-akciók:", style: AppText.label.copyWith(fontSize: 11.5)),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: "Előző gól-akció",
            onPressed: _golok.isEmpty || _match == null
                ? null
                : () => _golUgras(_match!, -1),
            icon: const Icon(Icons.chevron_left, size: 20),
          ),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: "Következő gól-akció",
            onPressed: _golok.isEmpty || _match == null
                ? null
                : () => _golUgras(_match!, 1),
            icon: const Icon(Icons.chevron_right, size: 20),
          ),
          Text(_golok.isEmpty ? "nincs" : "${_golok.length}",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
      ),
      gomb("Lelátó", () => _nezet(20, -12, 9, 0, -0.5)),
      gomb("Kapu mögül", () => _nezet(-6, 10, 2.5, math.pi / 2, -0.12)),
      gomb("Pálya-szint", () => _nezet(20, 4, 1.7, 0, 0.0)),
      gomb("Madártávlat", () => _nezet(20, 10, 34, 0, -1.45)),
    ]);
  }

  /// Az élő fal a lejátszófejnél: a legutóbbi idővonal-sor, ha 1,5
  /// mp-nél nem régebbi — különben épp nincs szervezett támadás.
  Map<String, dynamic>? _eloFal(Match m) {
    if (_falSorok.isEmpty || m.frames.isEmpty) return null;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m) / fps;
    Map<String, dynamic>? talalt;
    for (final r in _falSorok) {
      final s = ((r["s"] as num?) ?? 0).toDouble();
      if (s > most) break;
      talalt = r;
    }
    if (talalt == null) return null;
    final s = ((talalt["s"] as num?) ?? 0).toDouble();
    return most - s <= 1.5 ? talalt : null;
  }

  /// A védekezés-panel állapota: a kirajzolandó sablon-pontok és a
  /// kiírandó sorok (az élő fal neve, a sablon helye, az eltérés).
  (List<Offset>, List<String>, Rect?) _falAllapot(Match m, _Allapot all) {
    if (_fal.isEmpty) return (const [], const [], null);
    final elo = _eloFal(m);
    final sorok = <String>[];
    final eloCimke = elo?["label"] as String?;
    final eloHazai = elo?["defending"] == "home";
    final eloGoalX = ((elo?["goal_x"] as num?) ?? -1).toDouble();
    if (elo != null) {
      final csapat = eloHazai ? m.meta.homeTeam : m.meta.awayTeam;
      sorok.add("Most: $csapat védekezik — $eloCimke");
    } else {
      sorok.add("Most nincs szervezett támadás — a fal nem áll.");
    }
    // Feltörés: a védekező csapat falának leggyengébb pontja — hol és
    // mivel kell támadni ellene (a felderítés rangsorának teteje).
    Rect? sav;
    if (elo != null) {
      final f = ((_falBreak[eloHazai ? "home" : "away"] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
      if (f.isNotEmpty) {
        sorok.add("Feltörés: ${f.first["hol"]} — ${f.first["mivel"]}");
      }
      // Megállítás: a TÁMADÓ csapat támadásának leggyengébb pontja — mivel
      // állíthatja meg a védekező csapat.
      final st = ((_falStop[eloHazai ? "away" : "home"] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
      if (st.isNotEmpty) {
        sorok.add("Megállítás: ${st.first["hol"]} — ${st.first["mivel"]}");
      }
      // Az első sávos tétel piros sávként a padlón, a védett kapu előtt.
      for (final t in f) {
        sav = breakpointZoneBand(t["sav"] as String?, eloGoalX);
        if (sav != null) {
          sorok.add("piros sáv: ide kell betörni");
          break;
        }
      }
    }
    final nev = _fal == "elo" ? eloCimke : _fal;
    double? goalX;
    if (_falOldal == "bal") {
      goalX = 0;
    } else if (_falOldal == "jobb") {
      goalX = courtLength;
    } else if (elo != null) {
      goalX = eloGoalX;
    }
    if (nev == null || !formationTemplates.containsKey(nev)) {
      if (_fal == "elo" && elo != null) {
        sorok.add("(ehhez a formához nincs tankönyvi sablon)");
      }
      return (const [], sorok, sav);
    }
    if (goalX == null) {
      sorok.add("Válassz kaput, vagy várj egy szervezett támadásra.");
      return (const [], sorok, sav);
    }
    final pontok = formationPositions(nev, goalX);
    final jobb = goalX > courtLength / 2;
    sorok.add("$nev sablon a ${jobb ? "jobb" : "bal"} kapu előtt "
        "(sárga körök)");
    if (elo != null && eloGoalX == goalX) {
      final vedok = [
        for (final j in all.jatekosok)
          if (j.home == eloHazai && !j.kapus && (j.x - goalX).abs() > 2.0)
            Offset(j.x, j.y)
      ];
      if (vedok.length >= 4) {
        final e = formationDeviation(vedok, pontok);
        if (e != null) {
          sorok.add("Átlagos eltérés a tankönyvi faltól: "
              "${e.toStringAsFixed(1).replaceAll(".", ",")} m");
        }
      }
    }
    return (pontok, sorok, sav);
  }

  /// A lövéstérkép összegzője: hány lövés látszik, ebből hány gól, és
  /// a jelmagyarázat.
  List<String> _lovesOsszegzo(Match m) {
    if (_lovesek.isEmpty) return const ["Ehhez a meccshez nincs felismert lövés."];
    final lat = _lathatoLovesek(m);
    final gol = lat.where((l) => l["outcome"] == "goal").length;
    return [
      "${lat.length} lövés, $gol gól — kék: ${m.meta.homeTeam}, "
          "piros: ${m.meta.awayTeam}",
      "kör = xG (nagyobb = jobb helyzet), arany gyűrű = gól; "
          "koppints egy körre — odaugrik",
    ];
  }

  Widget _infoDoboz(List<String> sorok, Color szin, {Widget? zaro}) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 340),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.surface.withOpacity(0.88),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: szin),
      ),
      child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Flexible(
              child: Text(sorok.join("\n"),
                  style: AppText.label.copyWith(
                      fontSize: 12.5, color: AppColors.textPrimary)),
            ),
            if (zaro != null) zaro,
          ]),
    );
  }

  /// A lövés-mérés doboza: távolság, kapufa-távolság, kapu-szög, sáv.
  Widget _meresDoboz(Offset p) {
    // Lövéstérkép-körről: a TÁMADOTT kapura mérünk (a vendég balra lő a
    // backend alapértelmezése szerint), és a lövés sora áll elöl.
    final l = _lovesValasztott;
    final g = shotGeometry(p.dx, p.dy,
        leftGoal: l == null ? null : l["team"] == "away");
    String sz(double v) => v.toStringAsFixed(1).replaceAll(".", ",");
    final m = _match;
    String? lovesSor;
    if (l != null && m != null) {
      final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
      final mp = (((l["t"] as num?) ?? 0) / fps).floor();
      final kimenet = const {"goal": "gól", "save": "védés"}[l["outcome"]] ??
          "mellé/kapufa";
      final xg = ((l["xg"] as num?) ?? 0).toDouble();
      lovesSor = "${l["team"] == "home" ? m.meta.homeTeam : m.meta.awayTeam}"
          " lövése ${mp ~/ 60}:${(mp % 60).toString().padLeft(2, "0")}"
          " · $kimenet · xG ${xg.toStringAsFixed(2).replaceAll(".", ",")}";
    }
    return _infoDoboz([
      if (lovesSor != null) lovesSor,
      "Lövés-mérés (${g.leftGoal ? "bal" : "jobb"} kapu)",
      "${sz(g.distance)} m a kapu közepétől · kapufától ${sz(g.postDistance)} m",
      "Kapu-szög: ${sz(g.angleDeg)}° · sáv: ${g.zone}",
    ], AppColors.accent,
        zaro: IconButton(
          visualDensity: VisualDensity.compact,
          iconSize: 16,
          tooltip: "Törlés (Esc)",
          onPressed: () => setState(() {
            _meres = null;
            _lovesValasztott = null;
          }),
          icon: const Icon(Icons.close),
        ));
  }

  /// Videó-kocka (t címke) → frame-lista index (az első kocka, amelynek
  /// t-je eléri). A kettő NEM ugyanaz: utólagos vágás után a lista
  /// elejéről kockák hiányoznak, a t címkék viszont maradnak — az
  /// esemény t-jére indexszel ugrani rossz jelenetre vinne.
  static int _tIndex(Match m, double t) {
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

  /// A lejátszófej alatti kocka t címkéje (videó-kocka).
  int _mostT(Match m) {
    if (m.frames.isEmpty) return 0;
    return m.frames[_playhead.floor().clamp(0, m.frames.length - 1)].t;
  }

  /// Ugrás az előző/következő eseményre — a jelenet előtt 4 mp-cel,
  /// TV-kamerával, lejátszva (mint az Események listából érkezve).
  /// Egy másodpercnyi holt sáv, hogy az épp nézett esemény ne "ragadjon".
  void _esemenyUgras(Match m, int irany) {
    if (_esemenyek.isEmpty || m.frames.isEmpty) return;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m);
    Map<String, dynamic>? talalt;
    if (irany > 0) {
      for (final e in _esemenyek) {
        if (((e["t"] as num?) ?? 0) > most + fps) {
          talalt = e;
          break;
        }
      }
    } else {
      for (final e in _esemenyek.reversed) {
        if (((e["t"] as num?) ?? 0) < most - fps) {
          talalt = e;
          break;
        }
      }
    }
    if (talalt == null) return;
    final celT = ((talalt["t"] as num?) ?? 0).toDouble();
    setState(() {
      _playhead = _tIndex(m, celT - 4.0 * fps).toDouble();
      _playing = true;
      _tvKamera = true;
      _kovMez = null;
    });
  }

  /// A lejátszófejhez tartozó esemény felirata a jelenet közben
  /// ("GÓL — Kiel"): az esemény előtt 0,3 mp-től utána 2,5 mp-ig.
  String? _esemenyFelirat(Match m) {
    if (_esemenyek.isEmpty || m.frames.isEmpty) return null;
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final most = _mostT(m);
    for (final e in _esemenyek) {
      final t = ((e["t"] as num?) ?? 0).toDouble();
      if (most < t - 0.3 * fps) break; // időrendben: a többi későbbi
      if (most > t + 2.5 * fps) continue;
      final nev = switch (e["type"]) {
        "goal" => "GÓL",
        "shot" => "Lövés",
        "figure" => "Ismert figura (${e["zone"] ?? "?"})",
        _ => "Labdaeladás",
      };
      final csapat =
          e["team"] == "home" ? m.meta.homeTeam : m.meta.awayTeam;
      return "$nev — $csapat";
    }
    return null;
  }

  Widget _lejatszoSav(Match m) {
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final osszes = m.frames.isEmpty ? 1 : m.frames.length;
    // Az idő a kocka t címkéjéből (videó-idő): így egyezik az Események
    // lista és a jelenet-lejátszó időskálájával vágott meccsen is.
    String ido(int t) {
      final s = (t / fps).round();
      return "${s ~/ 60}:${(s % 60).toString().padLeft(2, "0")}";
    }

    return Row(children: [
      IconButton(
        onPressed: _esemenyek.isEmpty ? null : () => _esemenyUgras(m, -1),
        icon: const Icon(Icons.skip_previous, size: 22),
        tooltip: "Előző esemény (gól / lövés / eladás)",
      ),
      IconButton(
        onPressed: () => setState(() => _playing = !_playing),
        icon: Icon(_playing ? Icons.pause_circle : Icons.play_circle,
            color: AppColors.accent, size: 32),
        tooltip: _playing ? "Szünet (Szóköz)" : "Lejátszás (Szóköz)",
      ),
      IconButton(
        onPressed: _esemenyek.isEmpty ? null : () => _esemenyUgras(m, 1),
        icon: const Icon(Icons.skip_next, size: 22),
        tooltip: "Következő esemény (gól / lövés / eladás)",
      ),
      Expanded(
        child: Slider(
          value: _playhead.clamp(0, (osszes - 1).toDouble()),
          min: 0,
          max: (osszes - 1).toDouble(),
          onChanged: (v) => setState(() => _playhead = v),
        ),
      ),
      Text(
          "${ido(_mostT(m))} / "
          "${ido(m.frames.isEmpty ? 0 : m.frames.last.t)}",
          style: AppText.label.copyWith(fontSize: 12.5)),
      const SizedBox(width: AppSpacing.md),
      DropdownButton<double>(
        value: _speed,
        dropdownColor: AppColors.surface,
        items: const [
          DropdownMenuItem(value: 0.5, child: Text("0,5×")),
          DropdownMenuItem(value: 1.0, child: Text("1×")),
          DropdownMenuItem(value: 2.0, child: Text("2×")),
          DropdownMenuItem(value: 4.0, child: Text("4×")),
        ],
        onChanged: (v) => setState(() => _speed = v ?? 1.0),
      ),
    ]);
  }

  /// A lejátszófej KÉT szomszédos frame közé eshet — a közös track-eket
  /// lineárisan interpoláljuk, hogy a mozgás sima legyen (a követés a
  /// termékben ritkított: ~8 kép/mp, interpoláció nélkül darabos lenne).
  _Allapot _aktualisAllapot(Match m) {
    if (m.frames.isEmpty) return _Allapot(const [], null);
    final i0 = _playhead.floor().clamp(0, m.frames.length - 1);
    final i1 = (i0 + 1).clamp(0, m.frames.length - 1);
    final t = (_playhead - i0).clamp(0.0, 1.0);
    final a = m.frames[i0];
    final b = m.frames[i1];
    final bMap = {for (final p in b.players) p.trackId: p};
    final jatekosok = <_Jatekos>[];
    final fpsA = m.meta.fps > 0 ? m.meta.fps : 25.0;
    for (final p in a.players) {
      final q = bMap[p.trackId];
      final x = q == null ? p.x : p.x + (q.x - p.x) * t;
      final y = q == null ? p.y : p.y + (q.y - p.y) * t;
      // Haladás a két kocka közt: irány + sebesség (a figura ebbe fordul
      // és ezzel lendít). Követés-ugrásnál (>8 m/s) nem hisszük el.
      final dx = q == null ? 0.0 : q.x - p.x;
      final dy = q == null ? 0.0 : q.y - p.y;
      final lepes = math.sqrt(dx * dx + dy * dy);
      final seb = lepes * fpsA / math.max(1, b.t - a.t);
      final hihet = seb <= 8.0;
      jatekosok.add(_Jatekos(
          x: x,
          y: y,
          home: p.team == Team.home,
          becsult: p.isEstimated,
          mez: p.jerseyNumber,
          dirX: hihet ? dx : 0.0,
          dirY: hihet ? dy : 0.0,
          speed: hihet ? seb : 0.0,
          trackId: p.trackId,
          kapus: p.role == "kapus"));
    }
    _Labda? labda;
    if (a.ball != null && b.ball != null) {
      labda = _Labda(
          a.ball!.x + (b.ball!.x - a.ball!.x) * t,
          a.ball!.y + (b.ball!.y - a.ball!.y) * t);
    } else if (a.ball != null) {
      labda = _Labda(a.ball!.x, a.ball!.y);
    }
    return _Allapot(jatekosok, labda, tSec: _playhead / fpsA);
  }
}

class _Jatekos {
  final double x, y;
  final bool home;
  final bool becsult;
  final int? mez;
  // A haladás iránya (méter/kocka, nem normált) és sebessége (m/s) — a
  // figura ebbe fordul, és ezzel arányosan lendíti a lábát-karját. A
  // track-azonosító a lépés-fázis eltolásához (ne egyszerre lépjenek).
  final double dirX, dirY, speed;
  final int trackId;
  // Kapus: a követés "kapus" szerepe — külön mezt kap (mint a valóságban).
  final bool kapus;
  _Jatekos(
      {required this.x,
      required this.y,
      required this.home,
      required this.becsult,
      this.mez,
      this.dirX = 0.0,
      this.dirY = 0.0,
      this.speed = 0.0,
      this.trackId = 0,
      this.kapus = false});
}

class _Labda {
  final double x, y;
  _Labda(this.x, this.y);
}

/// Egy passz-vonal: az adó és a fogadó helye, magasság, csapat, átlátszóság.
class _PasszVonal {
  final double x1, y1, x2, y2, z, alpha;
  final bool home;
  const _PasszVonal(
      this.x1, this.y1, this.x2, this.y2, this.z, this.home, this.alpha);
}

/// Egy hőtérkép-cella: rács-index és -méret, erősség (0–1), csapat.
class _HoCella {
  final int ix, iy, binsX, binsY;
  final double erosseg;
  final bool home;
  const _HoCella(
      this.ix, this.iy, this.binsX, this.binsY, this.erosseg, this.home);
}

/// Egy lövés a térképen: hely, sugár (méter), csapat, gól-e.
class _LovesJel {
  final double x, y, r;
  final bool home, gol;
  const _LovesJel(this.x, this.y, this.r, this.home, this.gol);
}

class _Allapot {
  final List<_Jatekos> jatekosok;
  final _Labda? labda;
  // A lejátszófej ideje (mp) — a figurák lépés-fázisa ebből fut.
  final double tSec;
  _Allapot(this.jatekosok, this.labda, {this.tSec = 0.0});
}

/// Szoftveres távlati vetítés: pálya-koordináta (méter, z felfelé) →
/// képernyő-pixel. A kamera yaw/pitch szögekkel néz; a közeli sík előtti
/// pontokat vágjuk (a vonalakat a síkon metszve), hogy háttal állva ne
/// "forduljon ki" a kép.
/// A festő vetítésének tükre a gesztusokhoz (koppintás → padló-pont,
/// figura → képernyő-pont). UGYANAZ a kamera-bázis és fókusz, mint a
/// `_Court3DPainter._keszit`-ben — a találat és a rajz így egyezik.
class _Vetites {
  final double cx, cy, cz;
  final Size size;
  late final double fx, fy, fz, rx, ry, ux, uy, uz, f;
  _Vetites(this.cx, this.cy, this.cz, double yaw, double pitch, this.size) {
    final cp = math.cos(pitch), sp = math.sin(pitch);
    fx = math.sin(yaw) * cp;
    fy = math.cos(yaw) * cp;
    fz = sp;
    rx = math.cos(yaw);
    ry = -math.sin(yaw);
    ux = ry * fz;
    uy = -rx * fz;
    uz = rx * fy - ry * fx;
    f = (size.height / 2) / math.tan(0.5);
  }

  /// Pálya-pont (méter, z felfelé) → képernyő; null, ha a kamera mögött.
  Offset? kepernyo(double x, double y, double z) {
    final px = x - cx, py = y - cy, pz = z - cz;
    final mely = px * fx + py * fy + pz * fz;
    if (mely < 0.15) return null;
    final jobb = px * rx + py * ry;
    final fel = px * ux + py * uy + pz * uz;
    return Offset(size.width / 2 + jobb * f / mely,
        size.height / 2 - fel * f / mely);
  }

  /// Képernyő-pont → a padló (z = 0) pontja a sugár mentén; null, ha a
  /// sugár nem a padló felé megy (a horizont fölé kattintottak).
  Offset? padlo(Offset p) {
    final a = (p.dx - size.width / 2) / f;
    final b = -(p.dy - size.height / 2) / f;
    final dx = fx + rx * a + ux * b;
    final dy = fy + ry * a + uy * b;
    final dz = fz + uz * b;
    if (dz >= -1e-6) return null;
    final t = -cz / dz;
    return Offset(cx + dx * t, cy + dy * t);
  }
}

/// A labdavesztés-réteg színe (narancs) — a böngészős nézet 0xff9f43-ja.
const Color eladasSzin = Color(0xFFFF9F43);

class _Court3DPainter extends CustomPainter {
  final _Allapot frame;
  final double cx, cy, cz, yaw, pitch;
  // Lövés-mérés pontja (pálya-méter), a védekezés-sablon pontjai, és a
  // szemével-nézet játékosa (a saját testét nem rajzoljuk: a fejében ülünk).
  final Offset? meres;
  // A mérés kapuja (null: a közelebbi); a lövéstérkép körei.
  final bool? meresBalKapu;
  final List<Offset> falPontok;
  // A feltörés sávja a padlón (pálya-méter): piros, áttetsző téglalap.
  final Rect? feltoresSav;
  final List<_LovesJel> lovesek;
  // A labda útja az utolsó másodpercekben (pálya-méter, időrendben).
  final List<Offset> nyom;
  // A hőtérkép cellái a padlón (a parketta fölött, a vonalak alatt).
  final List<_HoCella> hoCellak;
  // Passz-vonalak (élő: mellmagasságban; háló: a padlón).
  final List<_PasszVonal> passzok;
  // A labdás passzsávjai (labdás, sávok) — null: kikapcsolva / nincs labdás.
  final ((bool, double, double), List<PassLane>)? passzsavok;
  // A védőfal rései (court_geometry.wallGapSegments) — null: nincs.
  final WallGaps? falresek;
  // Az aktív döntés-pillanat (a /decision-moments egy sora) vagy null.
  final Map<String, dynamic>? dontes;
  // Az aktív szabad lövés (a /free-shots egy sora) és a fedezés-sugár.
  final Map<String, dynamic>? szabad;
  final double szabadSugar;
  // Az aktív gól-akció (a /goal-build-ups egy sora) vagy null.
  final Map<String, dynamic>? gol;
  // Az aktív labdavesztés (a /turnover-moments egy sora) és a nyomás-sugár.
  final Map<String, dynamic>? eladas;
  final double eladasSugar;
  final _Jatekos? rejtett;
  _Court3DPainter(
      {required this.frame,
      required this.cx,
      required this.cy,
      required this.cz,
      required this.yaw,
      required this.pitch,
      this.meres,
      this.meresBalKapu,
      this.falPontok = const [],
      this.feltoresSav,
      this.lovesek = const [],
      this.nyom = const [],
      this.hoCellak = const [],
      this.passzok = const [],
      this.passzsavok,
      this.falresek,
      this.dontes,
      this.szabad,
      this.szabadSugar = 2.0,
      this.gol,
      this.eladas,
      this.eladasSugar = 2.5,
      this.rejtett});

  static const double _kozel = 0.15; // közeli vágósík (méter)

  late double _fx, _fy, _fz; // előre
  late double _rx, _ry; // jobbra (vízszintes)
  late double _ux, _uy, _uz; // felfelé
  late double _f; // fókusz (pixel)
  late Size _size;

  void _keszit(Size size) {
    _size = size;
    final cp = math.cos(pitch), sp = math.sin(pitch);
    _fx = math.sin(yaw) * cp;
    _fy = math.cos(yaw) * cp;
    _fz = sp;
    _rx = math.cos(yaw);
    _ry = -math.sin(yaw);
    // up = right × forward (jobbkezes, z felfelé rendszerben felfelé mutat)
    _ux = _ry * _fz;
    _uy = -_rx * _fz;
    _uz = _rx * _fy - _ry * _fx;
    _f = (size.height / 2) / math.tan(0.5); // ~57° függőleges látószög
  }

  /// Kamera-tér: (jobbra, fel, mélység) — a mélység a vetítés osztója.
  (double, double, double) _kamera(double x, double y, double z) {
    final px = x - cx, py = y - cy, pz = z - cz;
    final jobb = px * _rx + py * _ry;
    final fel = px * _ux + py * _uy + pz * _uz;
    final mely = px * _fx + py * _fy + pz * _fz;
    return (jobb, fel, mely);
  }

  Offset _kepernyo(double jobb, double fel, double mely) => Offset(
      _size.width / 2 + jobb * _f / mely,
      _size.height / 2 - fel * _f / mely);

  /// 3D szakasz a közeli síkra vágva; null, ha teljesen mögöttünk van.
  (Offset, Offset)? _szakasz(double x1, double y1, double z1, double x2,
      double y2, double z2) {
    var (j1, f1, m1) = _kamera(x1, y1, z1);
    var (j2, f2, m2) = _kamera(x2, y2, z2);
    if (m1 < _kozel && m2 < _kozel) return null;
    if (m1 < _kozel || m2 < _kozel) {
      final t = (_kozel - m1) / (m2 - m1);
      final j = j1 + (j2 - j1) * t;
      final f = f1 + (f2 - f1) * t;
      if (m1 < _kozel) {
        j1 = j;
        f1 = f;
        m1 = _kozel;
      } else {
        j2 = j;
        f2 = f;
        m2 = _kozel;
      }
    }
    return (_kepernyo(j1, f1, m1), _kepernyo(j2, f2, m2));
  }

  void _vonal(Canvas c, Paint p, double x1, double y1, double z1, double x2,
      double y2, double z2) {
    final sz = _szakasz(x1, y1, z1, x2, y2, z2);
    if (sz != null) c.drawLine(sz.$1, sz.$2, p);
  }

  void _talajUtvonal(Canvas c, Paint p, List<Offset> pontok,
      {bool szaggatott = false}) {
    for (var i = 0; i + 1 < pontok.length; i++) {
      if (szaggatott && i.isOdd) continue;
      _vonal(c, p, pontok[i].dx, pontok[i].dy, 0, pontok[i + 1].dx,
          pontok[i + 1].dy, 0);
    }
  }

  /// Kitöltött korong a padlón (sugár méterben): a kerület vetített
  /// pontjaiból sokszög; ha bármely pont a közeli sík mögé esik, nem
  /// rajzoljuk (a kör-kontúr ilyenkor is megvan a `_kor`-ral).
  void _korong(Canvas c, Paint p, double x, double y, double r) {
    const n = 20;
    final pontok = <Offset>[];
    for (var i = 0; i < n; i++) {
      final a = i / n * 2 * math.pi;
      final (jb, fe, me) =
          _kamera(x + math.cos(a) * r, y + math.sin(a) * r, 0.02);
      if (me < _kozel) return;
      pontok.add(_kepernyo(jb, fe, me));
    }
    c.drawPath(Path()..addPolygon(pontok, true), p);
  }

  /// Kör a padlón (sugár méterben), szakaszokból — a vágás így a
  /// közeli síkon is helyes.
  void _kor(Canvas c, Paint p, double x, double y, double r) {
    const n = 20;
    for (var i = 0; i < n; i++) {
      final a1 = i / n * 2 * math.pi, a2 = (i + 1) / n * 2 * math.pi;
      _vonal(c, p, x + math.cos(a1) * r, y + math.sin(a1) * r, 0.02,
          x + math.cos(a2) * r, y + math.sin(a2) * r, 0.02);
    }
  }

  /// EMBERSZERŰ figura: fej, mez (törzs), nadrág, karok, lábak — a
  /// haladás irányába fordulva, a sebességgel arányos láb- és
  /// karlendítéssel, talaj-árnyékkal, mezszámmal a mezen. A demóban is
  /// ez fut. Szoftveres vetítés: minden testpont a pálya terében
  /// (méter, z felfelé), a figura saját "előre/jobbra" tengelyén.
  void _figura(Canvas canvas, _Jatekos j, double tSec) {
    final melyKozep = _kamera(j.x, j.y, 0.9).$3;
    if (melyKozep < _kozel) return;
    // Irány: a haladásé; álló játékos a kamera felé fordul.
    double fx = j.dirX, fy = j.dirY;
    var hossz = math.sqrt(fx * fx + fy * fy);
    if (hossz < 1e-6) {
      fx = cx - j.x;
      fy = cy - j.y;
      hossz = math.sqrt(fx * fx + fy * fy);
      if (hossz < 1e-6) {
        fx = 0;
        fy = 1;
        hossz = 1;
      }
    }
    fx /= hossz;
    fy /= hossz;
    final rx = fy, ry = -fx; // a figura jobbja

    // Lendítés: a sebességgel nő az amplitúdó és a lépés-ütem; a
    // track-azonosító eltolja a fázist, hogy ne egyszerre lépjenek.
    final seb = j.speed.clamp(0.0, 8.0);
    final amp = (seb / 5.0).clamp(0.0, 1.0);
    final utem = 1.2 + seb * 0.35;
    final fazis = tSec * 2 * math.pi * utem + (j.trackId % 7) * 0.9;
    final leng = math.sin(fazis) * amp;

    final alpha = j.becsult ? 0.45 : 1.0;
    // A kapus a valóságban is ELTÉRŐ mezt hord (a szabály is ezt kéri):
    // a csapatszínéből világosabb, zöldes árnyalat — messziről is
    // megkülönböztethető a mezőnyjátékosoktól.
    final csapat = j.kapus
        ? Color.lerp(j.home ? AppColors.home : AppColors.away,
            const Color(0xFF7BE3A0), 0.55)!
        : (j.home ? AppColors.home : AppColors.away);
    final mez = csapat.withOpacity(alpha);
    final nadrag = Color.lerp(csapat, Colors.black, 0.5)!.withOpacity(alpha);
    final bor = const Color(0xFFE3B98F).withOpacity(alpha);
    final haj = const Color(0xFF3A2A1E).withOpacity(alpha);
    final zokni = Colors.white.withOpacity(0.85 * alpha);

    // Lokális (előre, jobbra, magasság) → képernyő; null, ha mögöttünk.
    Offset? pont(double e, double o, double z) {
      final (jb, fe, me) =
          _kamera(j.x + fx * e + rx * o, j.y + fy * e + ry * o, z);
      if (me < _kozel) return null;
      return _kepernyo(jb, fe, me);
    }

    double vastag(double meter) => (meter * _f / melyKozep).clamp(1.0, 40.0);
    Paint vonalFestek(Color c, double meter) => Paint()
      ..color = c
      ..strokeWidth = vastag(meter)
      ..strokeCap = StrokeCap.round;
    void sokszog(List<Offset?> p, Color c) {
      if (p.any((o) => o == null)) return;
      canvas.drawPath(Path()..addPolygon(p.cast<Offset>(), true),
          Paint()..color = c);
    }

    // Árnyék a talajon (a figura alatt, kissé a haladás mögött).
    final arny = <Offset>[];
    for (var k = 0; k < 12; k++) {
      final a = k / 12 * 2 * math.pi;
      final o = pont(math.cos(a) * 0.34 - 0.05, math.sin(a) * 0.24, 0.0);
      if (o != null) arny.add(o);
    }
    if (arny.length >= 3) {
      canvas.drawPath(Path()..addPolygon(arny, true),
          Paint()..color = Colors.black.withOpacity(0.35 * alpha));
    }

    // Láb: csípő → térd → boka (ellenütemben a két oldal).
    void lab(double oldal, double lend) {
      final csipo = pont(0.0, oldal * 0.11, 0.92);
      final terd = pont(lend * 0.22 + (lend > 0 ? 0.06 : 0.0),
          oldal * 0.12, 0.50);
      final boka = pont(lend * 0.38, oldal * 0.13, 0.06);
      if (csipo == null || terd == null || boka == null) return;
      canvas.drawLine(csipo, terd, vonalFestek(bor, 0.12));
      canvas.drawLine(terd, boka, vonalFestek(zokni, 0.10));
      // Cipő: sötét, kissé előre nyúló talp.
      final orr = pont(lend * 0.38 + 0.12, oldal * 0.13, 0.04);
      if (orr != null) {
        canvas.drawLine(boka, orr,
            vonalFestek(const Color(0xFF22262E).withOpacity(alpha), 0.11));
      }
    }

    // Kar: váll → könyök → kéz (a lábakkal ellentétes ütemben).
    void kar(double oldal, double lend) {
      final vall = pont(0.0, oldal * 0.23, 1.42);
      final konyok = pont(lend * 0.16, oldal * 0.27, 1.12);
      final kez = pont(lend * 0.30 + 0.05, oldal * 0.26, 0.86);
      if (vall == null || konyok == null || kez == null) return;
      canvas.drawLine(vall, konyok, vonalFestek(mez, 0.09));
      canvas.drawLine(konyok, kez, vonalFestek(bor, 0.07));
    }

    // A kamerától távolabbi oldal előbb (takarás a figurán belül).
    final jobbMely = _kamera(j.x + rx * 0.3, j.y + ry * 0.3, 0.9).$3;
    final balMely = _kamera(j.x - rx * 0.3, j.y - ry * 0.3, 0.9).$3;
    final tavol = jobbMely > balMely ? 1.0 : -1.0;
    final kozel = -tavol;

    lab(tavol, -tavol * leng);
    kar(tavol, tavol * leng);
    // Nadrág: csípő → comb; mez: váll → csípő (a nadrág fölé).
    sokszog([
      pont(0.0, -0.17, 0.95), pont(0.0, 0.17, 0.95),
      pont(0.02, 0.19, 0.70), pont(0.02, -0.19, 0.70),
    ], nadrag);
    // A mez két fele: a kamerától távolabbi árnyékos — ettől van
    // "térfogata" a törzsnek egyetlen sík helyett.
    final arnyekos = Color.lerp(mez, Colors.black, 0.28)!;
    sokszog([
      pont(0.0, tavol * 0.22, 1.45), pont(0.0, 0.0, 1.47),
      pont(0.0, 0.0, 0.93), pont(0.0, tavol * 0.16, 0.93),
    ], arnyekos);
    sokszog([
      pont(0.0, 0.0, 1.47), pont(0.0, kozel * 0.22, 1.45),
      pont(0.0, kozel * 0.16, 0.93), pont(0.0, 0.0, 0.93),
    ], mez);
    lab(kozel, -kozel * leng);
    kar(kozel, kozel * leng);

    // Fej: bőr + haj-sapka a tetején.
    final fejK = _kamera(j.x + fx * 0.02, j.y + fy * 0.02, 1.66);
    if (fejK.$3 >= _kozel) {
      final o = _kepernyo(fejK.$1, fejK.$2, fejK.$3);
      final r = (0.12 * _f / fejK.$3).clamp(1.0, 22.0);
      canvas.drawCircle(o, r, Paint()..color = bor);
      canvas.drawArc(Rect.fromCircle(center: o, radius: r), math.pi,
          math.pi, true, Paint()..color = haj);
    }

    // Mezszám a mezen (közelről olvasható).
    if (j.mez != null && melyKozep < 30) {
      final cimke = pont(0.0, 0.0, 1.22);
      if (cimke != null) {
        final tp = TextPainter(
          text: TextSpan(
              text: "${j.mez}",
              style: TextStyle(
                  color: Colors.white.withOpacity(0.95 * alpha),
                  fontSize: (11.0 * 6 / melyKozep).clamp(7.0, 16.0),
                  fontWeight: FontWeight.bold)),
          textDirection: TextDirection.ltr,
        )..layout();
        tp.paint(canvas, cimke - Offset(tp.width / 2, tp.height / 2));
      }
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    _keszit(size);

    final vonal = Paint()
      ..color = AppColors.courtLine.withOpacity(0.9)
      ..strokeWidth = 1.4
      ..style = PaintingStyle.stroke;
    final halvany = Paint()
      ..color = AppColors.courtLine.withOpacity(0.22)
      ..strokeWidth = 1.0;

    // Talaj-rács a mélység-érzethez (5 m-enként, a pályán kívül is egy sáv).
    for (double x = -10; x <= 50; x += 5) {
      _vonal(canvas, halvany, x, -10, 0, x, 30, 0);
    }
    for (double y = -10; y <= 30; y += 5) {
      _vonal(canvas, halvany, -10, y, 0, 50, y, 0);
    }

    // PARKETTA: a pálya 5x5 m-es lapokból, váltakozó fa-árnyalattal — a
    // lapok külön vetülnek (a kamera mögé eső lap egyszerűen kimarad),
    // így közelről és madártávlatból is tartja a formát.
    for (var ix = 0; ix < 8; ix++) {
      for (var iy = 0; iy < 4; iy++) {
        final sarkok = <Offset>[];
        var jo = true;
        for (final (dx, dy) in [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]) {
          final (jb, fe, me) = _kamera(ix * 5.0 + dx, iy * 5.0 + dy, 0.0);
          if (me < _kozel) {
            jo = false;
            break;
          }
          sarkok.add(_kepernyo(jb, fe, me));
        }
        if (!jo) continue;
        final sotet = (ix + iy).isOdd;
        canvas.drawPath(
            Path()..addPolygon(sarkok, true),
            Paint()
              ..color = (sotet ? const Color(0xFF6E4728) : const Color(0xFF7A5030))
                  .withOpacity(0.55));
      }
    }

    // Hőtérkép-cellák: áttetsző, a csapat színével, a legsűrűbb cellához
    // mért erősséggel — a parketta fölött, a vonalak alatt.
    for (final c in hoCellak) {
      final w = courtLength / c.binsX, h = courtWidth / c.binsY;
      final x0 = c.ix * w, y0 = c.iy * h;
      final sarkok = <Offset>[];
      var jo = true;
      for (final (dx, dy) in [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]) {
        final (jb, fe, me) = _kamera(x0 + dx, y0 + dy, 0.005);
        if (me < _kozel) {
          jo = false;
          break;
        }
        sarkok.add(_kepernyo(jb, fe, me));
      }
      if (!jo) continue;
      canvas.drawPath(
          Path()..addPolygon(sarkok, true),
          Paint()
            ..color = (c.home ? AppColors.home : AppColors.away)
                .withOpacity(0.1 + 0.65 * c.erosseg));
    }

    // Pálya-vonalak (méretek: court_geometry — a szabálykönyvből).
    _vonal(canvas, vonal, 0, 0, 0, courtLength, 0, 0);
    _vonal(canvas, vonal, 0, courtWidth, 0, courtLength, courtWidth, 0);
    _vonal(canvas, vonal, 0, 0, 0, 0, courtWidth, 0);
    _vonal(canvas, vonal, courtLength, 0, 0, courtLength, courtWidth, 0);
    _vonal(canvas, vonal, courtLength / 2, 0, 0, courtLength / 2,
        courtWidth, 0);
    _talajUtvonal(canvas, vonal, goalAreaBoundary(leftSide: true));
    _talajUtvonal(canvas, vonal, goalAreaBoundary(leftSide: false));
    _talajUtvonal(canvas, vonal,
        freeThrowBoundary(leftSide: true, segments: 32),
        szaggatott: true);
    _talajUtvonal(canvas, vonal,
        freeThrowBoundary(leftSide: false, segments: 32),
        szaggatott: true);
    // Hetes- és kapusvonalak mindkét oldalon.
    for (final bal in [true, false]) {
      final x7 = bal ? sevenMeterX : courtLength - sevenMeterX;
      final x4 = bal ? keeperLineX : courtLength - keeperLineX;
      final cy0 = courtWidth / 2;
      _vonal(canvas, vonal, x7, cy0 - sevenMeterHalfLen, 0, x7,
          cy0 + sevenMeterHalfLen, 0);
      _vonal(canvas, vonal, x4, cy0 - keeperLineHalfLen - 0.4, 0, x4,
          cy0 + keeperLineHalfLen + 0.4, 0);
    }

    // Cserevonal-jelek az oldalvonalon (a félpályától 4,5 m-re).
    for (final x in [
      courtLength / 2 - substitutionLineX,
      courtLength / 2 + substitutionLineX
    ]) {
      _vonal(canvas, vonal, x, -0.15, 0, x, 0.15, 0);
    }

    // Lövés-mérés: a pontból a két kapufáig húzott "lövő-háromszög" —
    // ennyi kaput lát a lövő —, és a kapu közepéig a távolság-vonal.
    // Lövéstérkép: kitöltött korong a lövés helyén (csapatszín, az xG-vel
    // növő sugár; gól telt + arany gyűrű, védés/mellé halvány).
    for (final l in lovesek) {
      final szin = l.home ? AppColors.home : AppColors.away;
      _korong(canvas, Paint()..color = szin.withOpacity(l.gol ? 0.9 : 0.45),
          l.x, l.y, l.r);
      if (l.gol) {
        _kor(
            canvas,
            Paint()
              ..color = AppColors.gold
              ..strokeWidth = 2.0,
            l.x,
            l.y,
            l.r + 0.08);
      }
    }

    // Passzsávok: a labdástól a társakig, a passz-esély fokozata szerint.
    // Fal-rések: a fal szomszédos védői közt vastag vonal a padlón — zöld
    // zárt, piros a wallGapM-es rés (ott nyílik a fal).
    final fr = falresek;
    if (fr != null) {
      for (var i = 0; i + 1 < fr.wall.length; i++) {
        final a = fr.wall[i], b = fr.wall[i + 1];
        _vonal(
            canvas,
            Paint()
              ..color = (fr.wide[i] ? AppColors.away : AppColors.accent)
                  .withOpacity(0.9)
              ..strokeWidth = fr.wide[i] ? 5.0 : 3.0
              ..strokeCap = StrokeCap.round,
            a.dx,
            a.dy,
            0.04,
            b.dx,
            b.dy,
            0.04);
      }
    }

    final ps = passzsavok;
    if (ps != null) {
      for (final l in ps.$2) {
        final szin = l.grade == "nyitott"
            ? AppColors.accent
            : (l.grade == "kockázatos" ? AppColors.gold : AppColors.away);
        _vonal(
            canvas,
            Paint()
              ..color = szin.withOpacity(0.9)
              ..strokeWidth = 2.6,
            ps.$1.$2,
            ps.$1.$3,
            1.1,
            l.x,
            l.y,
            1.1);
      }
    }

    // Szabad lövés: piros kör a lövő körül (a fedezés-sugár) és szaggatott
    // vonal a legközelebbi mezőnyvédőhöz.
    final sz = szabad;
    if (sz != null) {
      final lo = [for (final e in (sz["shooter"] as List)) (e as num).toDouble()];
      final piros = Paint()
        ..color = AppColors.away
        ..strokeWidth = 2.4;
      _kor(canvas, piros, lo[0], lo[1], szabadSugar);
      final ve = sz["defender"] as List?;
      if (ve != null) {
        _talajUtvonal(
            canvas,
            piros,
            [
              for (var i = 0; i <= 12; i++)
                Offset(
                    lo[0] + ((ve[0] as num).toDouble() - lo[0]) * i / 12,
                    lo[1] + ((ve[1] as num).toDouble() - lo[1]) * i / 12)
            ],
            szaggatott: true);
      }
    }

    // Gól-akció: a lánc passzai mellmagasságban a csapat színével (a
    // régebbi halványabb), arany vonal a lövőtől a kapu közepéig.
    final gk = gol;
    if (gk != null) {
      final szin = gk["team"] == "home" ? AppColors.home : AppColors.away;
      final lanc = ((gk["passes"] as List?) ?? const []).cast<Map>();
      for (var i = 0; i < lanc.length; i++) {
        final a = lanc[i]["from"] as List?, b = lanc[i]["to"] as List?;
        if (a == null || b == null) continue;
        _vonal(
            canvas,
            Paint()
              ..color = szin.withOpacity(0.35 + 0.65 * (i + 1) / lanc.length)
              ..strokeWidth = 2.4,
            (a[0] as num).toDouble(), (a[1] as num).toDouble(), 1.0,
            (b[0] as num).toDouble(), (b[1] as num).toDouble(), 1.0);
      }
      final lo = gk["shooter"] as List?, kapu = gk["goal"] as List?;
      if (lo != null && kapu != null) {
        _vonal(
            canvas,
            Paint()
              ..color = AppColors.gold
              ..strokeWidth = 2.8,
            (lo[0] as num).toDouble(), (lo[1] as num).toDouble(), 1.2,
            (kapu[0] as num).toDouble(), (kapu[1] as num).toDouble(), 1.0);
      }
    }

    // Labdavesztés: narancs kör a vesztő körül (a nyomás-sugár: ezen belül
    // álló ellenfél = kipréselt eladás), szaggatott vonal a legközelebbi
    // ellenfélhez, X a labda helyén.
    final el = eladas;
    if (el != null) {
      final narancs = Paint()
        ..color = eladasSzin
        ..strokeWidth = 2.4;
      final ve = el["loser"] as List?;
      final ell = el["opponent"] as List?;
      if (ve != null) {
        final vx = (ve[0] as num).toDouble(), vy = (ve[1] as num).toDouble();
        _kor(canvas, narancs, vx, vy, eladasSugar);
        if (ell != null) {
          final ox = (ell[0] as num).toDouble(), oy = (ell[1] as num).toDouble();
          _talajUtvonal(
              canvas,
              narancs,
              [
                for (var i = 0; i <= 12; i++)
                  Offset(vx + (ox - vx) * i / 12, vy + (oy - vy) * i / 12)
              ],
              szaggatott: true);
        }
      }
      final lb = el["ball"] as List?;
      if (lb != null) {
        final bx = (lb[0] as num).toDouble(), by = (lb[1] as num).toDouble();
        _vonal(canvas, narancs, bx - 0.45, by - 0.45, 0.06, bx + 0.45,
            by + 0.45, 0.06);
        _vonal(canvas, narancs, bx - 0.45, by + 0.45, 0.06, bx + 0.45,
            by - 0.45, 0.06);
      }
    }

    // Döntés-pillanat: a választott passz FEHÉR, a jobb opció ARANY vonal
    // a passzolótól (lövésnél a kapu közepére).
    final dn = dontes;
    if (dn != null) {
      List<double> xy(dynamic v) =>
          [for (final e in (v as List)) (e as num).toDouble()];
      final p0 = xy(dn["passer"]), ch = xy(dn["chosen"]), be = xy(dn["best"]);
      _vonal(
          canvas,
          Paint()
            ..color = Colors.white
            ..strokeWidth = 2.6,
          p0[0], p0[1], 1.15, ch[0], ch[1], 1.15);
      _vonal(
          canvas,
          Paint()
            ..color = AppColors.gold
            ..strokeWidth = 2.8,
          p0[0], p0[1], 1.15, be[0], be[1], 1.15);
    }

    // Passz-vonalak: az adótól a fogadóig, a csapat színével.
    for (final p in passzok) {
      _vonal(
          canvas,
          Paint()
            ..color = (p.home ? AppColors.home : AppColors.away)
                .withOpacity(p.alpha)
            ..strokeWidth = p.z > 0.5 ? 2.4 : 1.2,
          p.x1,
          p.y1,
          p.z,
          p.x2,
          p.y2,
          p.z);
    }

    // Labda-nyom: narancs vonal labda-magasságban, a régebbi szakasz
    // halványabb — az irány így olvasható (honnan hová).
    for (var i = 0; i + 1 < nyom.length; i++) {
      final a = (0.25 + 0.75 * (i + 1) / nyom.length).clamp(0.0, 1.0);
      _vonal(
          canvas,
          Paint()
            ..color = AppColors.ball.withOpacity(a)
            ..strokeWidth = 2.2,
          nyom[i].dx,
          nyom[i].dy,
          0.45,
          nyom[i + 1].dx,
          nyom[i + 1].dy,
          0.45);
    }

    final mp = meres;
    if (mp != null) {
      final g = shotGeometry(mp.dx, mp.dy, leftGoal: meresBalKapu);
      final y1 = courtWidth / 2 - goalWidth / 2;
      final y2 = courtWidth / 2 + goalWidth / 2;
      final kek = Paint()
        ..color = AppColors.accent
        ..strokeWidth = 2.0;
      final csucsok = <Offset>[];
      for (final (x, y) in [(mp.dx, mp.dy), (g.goalX, y1), (g.goalX, y2)]) {
        final (jb, fe, me) = _kamera(x, y, 0.02);
        if (me >= _kozel) csucsok.add(_kepernyo(jb, fe, me));
      }
      if (csucsok.length == 3) {
        canvas.drawPath(Path()..addPolygon(csucsok, true),
            Paint()..color = AppColors.accent.withOpacity(0.28));
      }
      _vonal(canvas, kek, mp.dx, mp.dy, 0.02, g.goalX, y1, 0.02);
      _vonal(canvas, kek, mp.dx, mp.dy, 0.02, g.goalX, y2, 0.02);
      _talajUtvonal(
          canvas,
          Paint()
            ..color = Colors.white.withOpacity(0.85)
            ..strokeWidth = 1.2,
          [
            for (var i = 0; i <= 20; i++)
              Offset(mp.dx + (g.goalX - mp.dx) * i / 20,
                  mp.dy + (courtWidth / 2 - mp.dy) * i / 20)
          ],
          szaggatott: true);
      _kor(canvas, Paint()..color = Colors.white..strokeWidth = 2.0,
          mp.dx, mp.dy, 0.3);
    }

    // A feltörés sávja: piros, áttetsző téglalap a védett kapu előtt.
    final fs = feltoresSav;
    if (fs != null) {
      final sarkok = <Offset>[];
      var jo = true;
      for (final (x, y) in [
        (fs.left, fs.top), (fs.right, fs.top), (fs.right, fs.bottom),
        (fs.left, fs.bottom)
      ]) {
        final (jb, fe, me) = _kamera(x, y, 0.012);
        if (me < _kozel) {
          jo = false;
          break;
        }
        sarkok.add(_kepernyo(jb, fe, me));
      }
      if (jo) {
        canvas.drawPath(Path()..addPolygon(sarkok, true),
            Paint()..color = AppColors.away.withOpacity(0.22));
      }
    }

    // Védekezés-sablon: sárga körök a tankönyvi védő-helyeken.
    final sarga = Paint()
      ..color = AppColors.gold.withOpacity(0.9)
      ..strokeWidth = 2.2;
    for (final p in falPontok) {
      _kor(canvas, sarga, p.dx, p.dy, 0.42);
    }

    // Kapuk: 3 m széles, 2 m magas keret + jelzés-háló.
    final kapu = Paint()
      ..color = AppColors.gold.withOpacity(0.85)
      ..strokeWidth = 2.0;
    for (final x in [0.0, courtLength]) {
      final y1 = courtWidth / 2 - goalWidth / 2;
      final y2 = courtWidth / 2 + goalWidth / 2;
      _vonal(canvas, kapu, x, y1, 0, x, y1, 2);
      _vonal(canvas, kapu, x, y2, 0, x, y2, 2);
      _vonal(canvas, kapu, x, y1, 2, x, y2, 2);
      final hatra = x == 0.0 ? -1.0 : 1.0;
      _vonal(canvas, halvany, x, y1, 2, x + hatra, y1, 0);
      _vonal(canvas, halvany, x, y2, 2, x + hatra, y2, 0);
      _vonal(canvas, halvany, x + hatra, y1, 0, x + hatra, y2, 0);
    }

    // Játékosok hátulról előre (festő-algoritmus), hogy a közeli takarjon.
    final sorrend = [...frame.jatekosok];
    double melyseg(_Jatekos j) => _kamera(j.x, j.y, 1.0).$3;
    sorrend.sort((a, b) => melyseg(b).compareTo(melyseg(a)));
    for (final j in sorrend) {
      if (identical(j, rejtett)) continue; // a szemével-nézet saját teste
      _figura(canvas, j, frame.tSec);
    }

    // Labda. Ha VAN birtokosa (a legközelebbi játékos karnyújtásnyira
    // van), a labda a KEZÉBEN van — nem a földszint fölött lebeg: kéz-
    // magasságban, a haladás irányában kissé előtte. Enélkül a jelenet
    // úgy néz ki, mintha a labda magától úszna a pályán.
    final l = frame.labda;
    if (l != null) {
      var bx = l.x, by = l.y, bz = 0.6;
      _Jatekos? birtokos;
      var legkozelebb = 1.2; // karnyújtásnyi (méter)
      for (final j in frame.jatekosok) {
        final d = math.sqrt((j.x - l.x) * (j.x - l.x) +
            (j.y - l.y) * (j.y - l.y));
        if (d < legkozelebb) {
          legkozelebb = d;
          birtokos = j;
        }
      }
      if (birtokos != null) {
        var fx = birtokos.dirX, fy = birtokos.dirY;
        final h = math.sqrt(fx * fx + fy * fy);
        if (h > 1e-6) {
          fx /= h;
          fy /= h;
        } else {
          fx = cx - birtokos.x;
          fy = cy - birtokos.y;
          final h2 = math.sqrt(fx * fx + fy * fy);
          if (h2 > 1e-6) {
            fx /= h2;
            fy /= h2;
          }
        }
        bx = birtokos.x + fx * 0.32;
        by = birtokos.y + fy * 0.32;
        bz = 1.28; // kéz-magasság
      }
      final (jobb, fel, mely) = _kamera(bx, by, bz);
      if (mely >= _kozel) {
        canvas.drawCircle(_kepernyo(jobb, fel, mely),
            (0.12 * _f / mely).clamp(1.5, 14.0),
            Paint()..color = AppColors.ball);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _Court3DPainter old) => true;
}
