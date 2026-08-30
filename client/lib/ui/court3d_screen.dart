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

import "dart:math" as math;

import "package:flutter/gestures.dart";
import "package:flutter/material.dart";
import "package:flutter/scheduler.dart";
import "package:flutter/services.dart";

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
  const Court3DScreen({super.key, this.matchId});

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
      final h = <int>{}, a = <int>{};
      for (final f in m.frames) {
        for (final p in f.players) {
          final mez = p.jerseyNumber;
          if (mez == null) continue;
          (p.team == Team.home ? h : a).add(mez);
        }
      }
      setState(() {
        _match = m;
        _matchId = id;
        _demo = false;
        _playhead = 0;
        _loading = false;
        _mezekHome = h.toList()..sort();
        _mezekAway = a.toList()..sort();
        _kovTeam = null;
        _kovMez = null;
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
    if (_keys.contains(LogicalKeyboardKey.keyF)) {
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
    if (valtozott && mounted) setState(() {});
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent e) {
    final k = e.logicalKey;
    if (e is KeyDownEvent) {
      if (k == LogicalKeyboardKey.space) {
        setState(() => _playing = !_playing);
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
      ].contains(k)) {
        _tvKamera = false;
        _kovMez = null;
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
    ];
    return sajat.contains(k)
        ? KeyEventResult.handled
        : KeyEventResult.ignored;
  }

  void _nezet(double x, double y, double z, double yaw, double pitch) {
    setState(() {
      _tvKamera = false;
      _kovMez = null;
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
              "WASD — mozgás · egér-húzás — nézelődés · R/F — fel/le · "
              "Shift — gyors · Szóköz — lejátszás",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ]),
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
      child: GestureDetector(
        onTapDown: (_) => _focus.requestFocus(),
        onPanUpdate: (d) {
          setState(() {
            _tvKamera = false;
            _kovMez = null;
            _yaw += d.delta.dx * 0.005;
            _pitch = (_pitch - d.delta.dy * 0.005).clamp(-1.45, 1.45);
          });
        },
        child: Listener(
          onPointerSignal: (s) {
            if (s is PointerScrollEvent) {
              // Görgetés: előre/hátra a nézés irányában (zoom-érzés).
              final lep = -s.scrollDelta.dy / 120.0;
              setState(() {
                _cx += math.sin(_yaw) * math.cos(_pitch) * lep;
                _cy += math.cos(_yaw) * math.cos(_pitch) * lep;
                _cz = (_cz + math.sin(_pitch) * lep).clamp(0.4, 45.0);
              });
            }
          },
          child: ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF0A0E14),
                border: Border.all(color: AppColors.border),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Stack(children: [
                Positioned.fill(
                  child: CustomPaint(
                    painter: _Court3DPainter(
                      frame: _aktualisAllapot(m),
                      cx: _cx,
                      cy: _cy,
                      cz: _cz,
                      yaw: _yaw,
                      pitch: _pitch,
                    ),
                  ),
                ),
                Positioned(right: 10, top: 10, child: _nezetGombok()),
              ]),
            ),
          ),
        ),
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
      gomb("Lelátó", () => _nezet(20, -12, 9, 0, -0.5)),
      gomb("Kapu mögül", () => _nezet(-6, 10, 2.5, math.pi / 2, -0.12)),
      gomb("Pálya-szint", () => _nezet(20, 4, 1.7, 0, 0.0)),
      gomb("Madártávlat", () => _nezet(20, 10, 34, 0, -1.45)),
    ]);
  }

  Widget _lejatszoSav(Match m) {
    final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
    final osszes = m.frames.isEmpty ? 1 : m.frames.length;
    String ido(double f) {
      final s = (f / fps).round();
      return "${s ~/ 60}:${(s % 60).toString().padLeft(2, "0")}";
    }

    return Row(children: [
      IconButton(
        onPressed: () => setState(() => _playing = !_playing),
        icon: Icon(_playing ? Icons.pause_circle : Icons.play_circle,
            color: AppColors.accent, size: 32),
        tooltip: _playing ? "Szünet (Szóköz)" : "Lejátszás (Szóköz)",
      ),
      Expanded(
        child: Slider(
          value: _playhead.clamp(0, (osszes - 1).toDouble()),
          min: 0,
          max: (osszes - 1).toDouble(),
          onChanged: (v) => setState(() => _playhead = v),
        ),
      ),
      Text("${ido(_playhead)} / ${ido((osszes - 1).toDouble())}",
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
    for (final p in a.players) {
      final q = bMap[p.trackId];
      final x = q == null ? p.x : p.x + (q.x - p.x) * t;
      final y = q == null ? p.y : p.y + (q.y - p.y) * t;
      jatekosok.add(_Jatekos(
          x: x,
          y: y,
          home: p.team == Team.home,
          becsult: p.isEstimated,
          mez: p.jerseyNumber));
    }
    _Labda? labda;
    if (a.ball != null && b.ball != null) {
      labda = _Labda(
          a.ball!.x + (b.ball!.x - a.ball!.x) * t,
          a.ball!.y + (b.ball!.y - a.ball!.y) * t);
    } else if (a.ball != null) {
      labda = _Labda(a.ball!.x, a.ball!.y);
    }
    return _Allapot(jatekosok, labda);
  }
}

class _Jatekos {
  final double x, y;
  final bool home;
  final bool becsult;
  final int? mez;
  _Jatekos(
      {required this.x,
      required this.y,
      required this.home,
      required this.becsult,
      this.mez});
}

class _Labda {
  final double x, y;
  _Labda(this.x, this.y);
}

class _Allapot {
  final List<_Jatekos> jatekosok;
  final _Labda? labda;
  _Allapot(this.jatekosok, this.labda);
}

/// Szoftveres távlati vetítés: pálya-koordináta (méter, z felfelé) →
/// képernyő-pixel. A kamera yaw/pitch szögekkel néz; a közeli sík előtti
/// pontokat vágjuk (a vonalakat a síkon metszve), hogy háttal állva ne
/// "forduljon ki" a kép.
class _Court3DPainter extends CustomPainter {
  final _Allapot frame;
  final double cx, cy, cz, yaw, pitch;
  _Court3DPainter(
      {required this.frame,
      required this.cx,
      required this.cy,
      required this.cz,
      required this.yaw,
      required this.pitch});

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
      final (jobb, fel, mely) = _kamera(j.x, j.y, 0.9);
      if (mely < _kozel) continue;
      final szin = (j.home ? AppColors.home : AppColors.away)
          .withOpacity(j.becsult ? 0.45 : 0.95);
      final test = Paint()
        ..color = szin
        ..strokeWidth = (34.0 / mely).clamp(1.5, 26.0)
        ..strokeCap = StrokeCap.round;
      _vonal(canvas, test, j.x, j.y, 0.15, j.x, j.y, 1.55);
      final fejP = _kamera(j.x, j.y, 1.72);
      if (fejP.$3 >= _kozel) {
        canvas.drawCircle(_kepernyo(fejP.$1, fejP.$2, fejP.$3),
            (0.14 * _f / fejP.$3).clamp(1.0, 20.0), Paint()..color = szin);
      }
      if (j.mez != null && mely < 30) {
        final cimkeP = _kamera(j.x, j.y, 2.05);
        if (cimkeP.$3 >= _kozel) {
          final tp = TextPainter(
            text: TextSpan(
                text: "${j.mez}",
                style: TextStyle(
                    color: Colors.white.withOpacity(0.9),
                    fontSize: (11.0 * 6 / mely).clamp(8.0, 15.0),
                    fontWeight: FontWeight.bold)),
            textDirection: TextDirection.ltr,
          )..layout();
          final o = _kepernyo(cimkeP.$1, cimkeP.$2, cimkeP.$3);
          tp.paint(canvas, o - Offset(tp.width / 2, tp.height / 2));
        }
      }
    }

    // Labda.
    final l = frame.labda;
    if (l != null) {
      final (jobb, fel, mely) = _kamera(l.x, l.y, 0.6);
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
