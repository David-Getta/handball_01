/// Figura-tervező — az edző a felülnézeti pályán mozgatja a támadókat, és
/// lejátszatja a figurát a TANULT védelem ellen, kiértékeléssel.
///
/// HÁROM kulcs-pozíció (Kezdő / Közép / Vég) közt húzhatók a támadók — így az ív
/// (beúszás, kereszt) is megrajzolható. Lejátszáskor a pontokon át interpolálunk,
/// a védők a tanult modell szerint reagálnak. A szimuláció kliensoldalon fut
/// (analytics/play_simulation.dart).
library;

import "dart:async";
import "package:flutter/material.dart";

import "../analytics/play_simulation.dart";
import "../models/tracking.dart";
import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";
import "court_painter.dart";

class DesignerScreen extends StatefulWidget {
  final Match match; // ebből tanuljuk a védelmet
  const DesignerScreen({super.key, required this.match});

  @override
  State<DesignerScreen> createState() => _DesignerScreenState();
}

class _DesignerScreenState extends State<DesignerScreen> {
  // 5 támadó, HÁROM kulcs-pozícióval (0 = Kezdő, 1 = Közép, 2 = Vég) — így a
  // figura íve (beúszás, kereszt) is megrajzolható, nem csak egyenes vonal.
  late List<List<Offset>> _attackers;

  /// 3 kulcspozíció két végpontból (a közép a felezőpont — az edző elhúzza).
  static List<Offset> _path3(Offset a, Offset b) =>
      [a, Offset.lerp(a, b, 0.5)!, b];

  /// Egy kulcspozíció-út mintavételezése t (0..1) helyen (szakaszonként lineáris).
  static Offset _sample(List<Offset> path, double t) {
    if (path.length == 1) return path.first;
    final seg = (t * (path.length - 1)).clamp(0.0, (path.length - 1).toDouble());
    final i = seg.floor().clamp(0, path.length - 2);
    return Offset.lerp(path[i], path[i + 1], seg - i)!;
  }
  int _editStep = 0;
  int? _dragIndex;

  late int _numDefenders;
  double _lineDepth = 6.0;

  bool _playing = false;
  Match? _sim;
  SetPlayEvaluation? _eval;
  int _playIndex = 0;
  Timer? _timer;

  static const int _animSteps = 40;

  @override
  void initState() {
    super.initState();
    // A védelmet a betöltött meccsből tanuljuk (létszám + mélység).
    final learned = learnDefense(widget.match, Team.away);
    _numDefenders = learned.numDefenders;
    _lineDepth = learned.lineDepthM.clamp(4.0, 12.0).toDouble();

    // Alap figura: irányító, két átlövő, szélső, beálló — az edző átrendezi.
    _attackers = [
      _path3(const Offset(22, 10), const Offset(22, 10)), // irányító (labdás)
      _path3(const Offset(24, 5), const Offset(28, 5)),   // bal átlövő
      _path3(const Offset(24, 15), const Offset(28, 15)), // jobb átlövő
      _path3(const Offset(28, 2), const Offset(31, 2)),   // szélső
      _path3(const Offset(30, 10), const Offset(34, 10)), // beálló (a kapu felé)
    ];
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  DefenseModel get _model => DefenseModel(numDefenders: _numDefenders, lineDepthM: _lineDepth);

  void _onPan(Offset localPos, Size size, {bool start = false}) {
    if (_playing) return;
    final tr = CourtTransform.fit(size);
    final court = tr.toCourt(localPos.dx, localPos.dy);
    if (start) {
      // A legközelebbi támadó kiválasztása (kb. 2.5 m-en belül).
      int? best;
      double bestD = 2.5;
      for (int i = 0; i < _attackers.length; i++) {
        final p = _attackers[i][_editStep];
        final d = (p - court).distance;
        if (d < bestD) {
          bestD = d;
          best = i;
        }
      }
      _dragIndex = best;
    }
    if (_dragIndex != null) {
      setState(() {
        _attackers[_dragIndex!][_editStep] = Offset(
          court.dx.clamp(0.0, courtLength).toDouble(),
          court.dy.clamp(0.0, courtWidth).toDouble(),
        );
      });
    }
  }

  void _play() {
    // A kulcs-pozíciókon át (kezdő→közép→vég) szakaszonként interpolálunk.
    final interp = <List<Offset>>[];
    for (final a in _attackers) {
      final path = <Offset>[];
      for (int s = 0; s < _animSteps; s++) {
        final t = s / (_animSteps - 1);
        path.add(_sample(a, t));
      }
      interp.add(path);
    }
    final setplay = SetPlay(interp, List<int>.filled(_animSteps, 0));
    final sim = simulateSetPlay(setplay, _model);
    final eval = evaluateSetPlay(sim);

    setState(() {
      _sim = sim;
      _eval = eval;
      _playing = true;
      _playIndex = 0;
    });
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(milliseconds: 40), (_) {
      setState(() {
        if (_playIndex < _animSteps - 1) {
          _playIndex++;
        } else {
          _timer?.cancel();
        }
      });
    });
  }

  /// A figura lejátszása egy VALÓDI meccsből tanult védelem ellen: az edző
  /// kiválasztja a meccset és a védekező oldalt, a szerver megtanulja a
  /// védekezésüket, és az ellen szimulálja a figurát.
  Future<void> _playVsLearned() async {
    List<Map<String, dynamic>> matches;
    try {
      matches = await _api.listMatches();
    } catch (_) {
      matches = [];
    }
    if (!mounted) return;
    if (matches.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text("Nincs elemzett meccs a könyvtárban — előbb dolgozz "
              "fel egy videót (vagy készíts demó meccset).")));
      return;
    }

    String? matchId = matches.first["match_id"] as String;
    String side = "away";
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlg) => AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text("Melyik csapat védelme ellen?"),
          content: SizedBox(
            width: 460,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "A rendszer a kiválasztott meccsből MEGTANULJA a védekező "
                  "csapat stílusát, és az ellen játssza le a figurádat.",
                  style: AppText.label.copyWith(fontSize: 12),
                ),
                const SizedBox(height: AppSpacing.md),
                Flexible(
                  child: SingleChildScrollView(
                    child: Column(children: [
                      for (final m in matches)
                        RadioListTile<String>(
                          dense: true,
                          activeColor: AppColors.gold,
                          title: Text(
                            "${m["home_team"]} vs ${m["away_team"]}",
                            style: AppText.value.copyWith(fontSize: 13),
                            overflow: TextOverflow.ellipsis,
                          ),
                          value: m["match_id"] as String,
                          groupValue: matchId,
                          onChanged: (v) => setDlg(() => matchId = v),
                        ),
                    ]),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                SegmentedButton<String>(
                  showSelectedIcon: false,
                  style: const ButtonStyle(visualDensity: VisualDensity.compact),
                  segments: const [
                    ButtonSegment(value: "home", label: Text("Hazai véd")),
                    ButtonSegment(value: "away", label: Text("Vendég véd")),
                  ],
                  selected: {side},
                  onSelectionChanged: (s) => setDlg(() => side = s.first),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("Mégse")),
            FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: AppColors.gold, foregroundColor: AppColors.onAccent),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text("Szimuláció"),
            ),
          ],
        ),
      ),
    );
    if (ok != true || matchId == null || !mounted) return;

    // A kulcs-pozíciókból interpolált útvonalak (mint a helyi lejátszásnál).
    final attackers = <List<List<double>>>[];
    for (final a in _attackers) {
      final path = <List<double>>[];
      for (int s = 0; s < _animSteps; s++) {
        final t = s / (_animSteps - 1);
        final p = _sample(a, t);
        path.add([p.dx, p.dy]);
      }
      attackers.add(path);
    }
    try {
      final resp = await _api.simulateSetplayVsMatch(
        matchId!,
        attackers: attackers,
        ballCarrier: List<int>.filled(_animSteps, 0),
        defending: side,
      );
      final sim = Match.fromJson(resp["tracking"] as Map<String, dynamic>);
      final eval = evaluateSetPlay(sim);
      if (!mounted) return;
      setState(() {
        _sim = sim;
        _eval = eval;
        _playing = true;
        _playIndex = 0;
      });
      _timer?.cancel();
      final steps = sim.frames.length;
      _timer = Timer.periodic(const Duration(milliseconds: 40), (_) {
        setState(() {
          if (_playIndex < steps - 1) {
            _playIndex++;
          } else {
            _timer?.cancel();
          }
        });
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text("Szimulációs hiba: $e")));
    }
  }

  void _backToEdit() {
    _timer?.cancel();
    setState(() {
      _playing = false;
      _sim = null;
    });
  }

  final ApiClient _api = ApiClient();

  /// A megrajzolt figura mentése a könyvtárba (név megadásával).
  Future<void> _savePlay() async {
    final nameCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Figura mentése"),
        content: TextField(
          controller: nameCtrl,
          autofocus: true,
          decoration: const InputDecoration(labelText: "Figura neve (pl. Beúszós kereszt)"),
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
    );
    if (ok != true || !mounted) return;
    final name = nameCtrl.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Adj nevet a figurának.")));
      return;
    }
    try {
      // A kulcs-pozíciók játékosonként (kezdő/közép/vég), méterben.
      final attackers = [
        for (final a in _attackers)
          [for (final p in a) [p.dx, p.dy]],
      ];
      await _api.savePlay(name, attackers);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Figura mentve: $name")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Mentési hiba: $e")));
    }
  }

  /// Mentett figura betöltése a könyvtárból (lista + törlés lehetőség).
  Future<void> _loadPlay() async {
    List<Map<String, dynamic>> plays;
    try {
      plays = await _api.listPlays();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("A könyvtár nem érhető el: $e")));
      return;
    }
    if (!mounted) return;
    final picked = await showDialog<String>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlg) => AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text("Figura betöltése"),
          content: SizedBox(
            width: 380,
            child: plays.isEmpty
                ? Text("Még nincs mentett figura — rajzolj egyet és mentsd el.",
                    style: AppText.label)
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      for (final p in plays)
                        ListTile(
                          dense: true,
                          title: Text("${p["name"]}",
                              style: AppText.value.copyWith(fontSize: 14)),
                          subtitle: Text("${p["players"]} játékos",
                              style: AppText.label.copyWith(fontSize: 11)),
                          onTap: () => Navigator.pop(ctx, p["id"] as String),
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline,
                                size: 18, color: AppColors.textFaint),
                            onPressed: () async {
                              try {
                                await _api.deletePlay(p["id"] as String);
                                setDlg(() => plays.remove(p));
                              } catch (_) {}
                            },
                          ),
                        ),
                    ],
                  ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Bezárás")),
          ],
        ),
      ),
    );
    if (picked == null || !mounted) return;
    try {
      final play = await _api.fetchPlay(picked);
      final attackers = (play["attackers"] as List)
          .map((a) => (a as List)
              .map((p) => Offset(((p as List)[0] as num).toDouble(), (p[1] as num).toDouble()))
              .toList())
          .toList();
      if (!mounted) return;
      setState(() {
        // A tervező 3 kulcs-pozícióval dolgozik: első / középső / utolsó pont.
        _attackers = [
          for (final a in attackers)
            if (a.isNotEmpty)
              a.length >= 3
                  ? [a.first, a[a.length ~/ 2], a.last]
                  : _path3(a.first, a.last),
        ];
        _editStep = 0;
      });
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Betöltve: ${play["name"]}")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Betöltési hiba: $e")));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _header(),
              const SizedBox(height: AppSpacing.lg),
              Expanded(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(child: _courtCard()),
                    const SizedBox(width: AppSpacing.lg),
                    SizedBox(width: 300, child: _sidePanel()),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _header() => Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
          ),
          const SizedBox(width: AppSpacing.sm),
          const Text("FIGURA-TERVEZŐ", style: AppText.brand),
          const SizedBox(width: 8),
          Text("· tanult védelem ellen", style: AppText.label),
        ],
      );

  Widget _courtCard() {
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final size = Size(constraints.maxWidth, constraints.maxHeight);
          if (_playing && _sim != null) {
            // Lejátszás: a szimulált frame-et a fő pálya-rajzolóval mutatjuk.
            return CustomPaint(painter: CourtPainter(frame: _sim!.frames[_playIndex]), size: size);
          }
          // Szerkesztés: húzható támadók + a védelem előnézete.
          return GestureDetector(
            onPanStart: (d) => _onPan(d.localPosition, size, start: true),
            onPanUpdate: (d) => _onPan(d.localPosition, size),
            onPanEnd: (_) => _dragIndex = null,
            child: CustomPaint(
              painter: _DesignerPainter(attackers: _attackers, step: _editStep, model: _model),
              size: size,
            ),
          );
        },
      ),
    );
  }

  Widget _sidePanel() {
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text("KULCS-POZÍCIÓ", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          SegmentedButton<int>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment(value: 0, label: Text("Kezdő")),
              ButtonSegment(value: 1, label: Text("Közép")),
              ButtonSegment(value: 2, label: Text("Vég")),
            ],
            selected: {_editStep},
            onSelectionChanged: _playing ? null : (s) => setState(() => _editStep = s.first),
          ),
          const SizedBox(height: AppSpacing.lg),
          // Figura-könyvtár: a megrajzolt figura mentése / visszatöltése.
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _playing ? null : _savePlay,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.gold,
                  side: const BorderSide(color: AppColors.gold),
                  visualDensity: VisualDensity.compact,
                ),
                icon: const Icon(Icons.save_outlined, size: 16),
                label: const Text("Mentés", style: TextStyle(fontSize: 12)),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _playing ? null : _loadPlay,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.accent,
                  side: const BorderSide(color: AppColors.accent),
                  visualDensity: VisualDensity.compact,
                ),
                icon: const Icon(Icons.folder_open, size: 16),
                label: const Text("Betöltés", style: TextStyle(fontSize: 12)),
              ),
            ),
          ]),
          const SizedBox(height: AppSpacing.xl),
          Text("TANULT VÉDELEM", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text("Védők", style: AppText.label),
            Text("$_numDefenders", style: AppText.value),
          ]),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text("Vonalmélység", style: AppText.label),
            Text("${_lineDepth.toStringAsFixed(1)} m", style: AppText.value),
          ]),
          Slider(
            value: _lineDepth, min: 4, max: 12,
            onChanged: _playing ? null : (v) => setState(() => _lineDepth = v),
          ),
          const Spacer(),
          if (_eval != null) _evalCard(_eval!),
          const SizedBox(height: AppSpacing.md),
          _playing
              ? OutlinedButton.icon(
                  onPressed: _backToEdit,
                  icon: const Icon(Icons.edit),
                  label: const Text("Vissza a szerkesztéshez"),
                )
              : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  FilledButton.icon(
                    onPressed: _play,
                    style: FilledButton.styleFrom(backgroundColor: AppColors.accent, foregroundColor: const Color(0xFF06231F)),
                    icon: const Icon(Icons.play_arrow),
                    label: const Text("Lejátszás a védelem ellen"),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  // A VALÓDI, meccsből tanult védelem ellen (könyvtárból).
                  FilledButton.icon(
                    onPressed: _playVsLearned,
                    style: FilledButton.styleFrom(
                        backgroundColor: AppColors.gold, foregroundColor: AppColors.onAccent),
                    icon: const Icon(Icons.psychology_outlined),
                    label: const Text("Egy CSAPAT tanult védelme ellen"),
                  ),
                ]),
        ],
      ),
    );
  }

  Widget _evalCard(SetPlayEvaluation e) {
    final pct = (e.bestShotValue * 100).toStringAsFixed(0);
    final quality = e.bestShotValue >= 0.4 ? "Kiváló helyzet" : e.bestShotValue >= 0.2 ? "Ígéretes" : "Nehéz helyzet";
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.accent.withOpacity(0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("EREDMÉNY", style: AppText.sectionLabel.copyWith(color: AppColors.accent)),
          const SizedBox(height: 6),
          Text("$pct%", style: AppText.valueBig.copyWith(color: AppColors.accent)),
          Text("legjobb lövőhelyzet · $quality", style: AppText.label.copyWith(fontSize: 11)),
          if (e.attackerId != null)
            Text("játékos #${e.attackerId}", style: AppText.label.copyWith(fontSize: 11)),
        ],
      ),
    );
  }
}

/// A szerkesztő-réteg rajzolója: pálya + húzható támadók + védelem-előnézet.
class _DesignerPainter extends CustomPainter {
  final List<List<Offset>> attackers;
  final int step;
  final DefenseModel model;

  _DesignerPainter({required this.attackers, required this.step, required this.model});

  @override
  void paint(Canvas canvas, Size size) {
    final tr = CourtTransform.fit(size);
    _drawCourt(canvas, tr);

    // Védelem-előnézet (a labda az 1. támadónál).
    final ballY = attackers[0][step].dy;
    final defs = model.respond(ballY, courtLength);
    for (final d in defs) {
      final c = tr.toScreen(d.dx, d.dy);
      canvas.drawCircle(c, 0.6 * tr.scale, Paint()..color = AppColors.away.withOpacity(0.45));
    }

    // Útvonal-előnézet: halvány vonal a kulcs-pozíciókon át (látszik az ív).
    final routePaint = Paint()
      ..color = AppColors.home.withOpacity(0.35)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6;
    for (final a in attackers) {
      if (a.length < 2) continue;
      final rp = Path()..moveTo(tr.toScreen(a.first.dx, a.first.dy).dx, tr.toScreen(a.first.dx, a.first.dy).dy);
      for (final kp in a.skip(1)) {
        final sp = tr.toScreen(kp.dx, kp.dy);
        rp.lineTo(sp.dx, sp.dy);
      }
      canvas.drawPath(rp, routePaint);
    }

    // Támadók (húzható tokenek).
    for (int i = 0; i < attackers.length; i++) {
      final p = attackers[i][step];
      final c = tr.toScreen(p.dx, p.dy);
      canvas.drawCircle(c, 0.85 * tr.scale, Paint()..color = AppColors.home.withOpacity(0.18));
      canvas.drawCircle(c, 0.65 * tr.scale, Paint()..color = AppColors.home);
      _label(canvas, c, "${i + 1}", 0.65 * tr.scale);
    }

    // Labda (az 1. támadónál).
    final b = tr.toScreen(attackers[0][step].dx, attackers[0][step].dy);
    canvas.drawCircle(b, 0.32 * tr.scale, Paint()..color = AppColors.ball);
  }

  void _drawCourt(Canvas canvas, CourtTransform tr) {
    final fill = Paint()..color = AppColors.courtFill;
    final line = Paint()
      ..color = AppColors.courtLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    final rect = Rect.fromPoints(tr.toScreen(0, 0), tr.toScreen(courtLength, courtWidth));
    final rrect = RRect.fromRectAndRadius(rect, const Radius.circular(10));
    canvas.drawRRect(rrect, fill);
    canvas.drawRRect(rrect, line);
    canvas.drawLine(tr.toScreen(courtLength / 2, 0), tr.toScreen(courtLength / 2, courtWidth), line);
    for (final leftSide in [true, false]) {
      final pts = goalAreaBoundary(leftSide: leftSide).map((o) => tr.toScreen(o.dx, o.dy)).toList();
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (final pt in pts.skip(1)) {
        path.lineTo(pt.dx, pt.dy);
      }
      path.close();
      canvas.drawPath(path, Paint()..color = AppColors.accent.withOpacity(0.07));
      canvas.drawPath(path, line);
    }
  }

  void _label(Canvas canvas, Offset center, String text, double radius) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: TextStyle(color: Colors.white, fontSize: radius * 0.85, fontWeight: FontWeight.bold)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant _DesignerPainter old) =>
      old.attackers != attackers || old.step != step || old.model.lineDepthM != model.lineDepthM;
}
