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
import "shell/app_shell.dart";
import "../services/browser_open.dart";
import "court_painter.dart";
import "error_text.dart";
import "num_format.dart";

class DesignerScreen extends StatefulWidget {
  final Match match; // ebből tanuljuk a védelmet
  /// Kezdő figura egy meccs támadásából (GET …/attack-figure — a 3D
  /// "✎ Figurává" gombja): az utak, a labdás-sor, a csapat; a védelem a
  /// meccs másik csapatáé (a 3D/VR is ellene nyit).
  final Map<String, dynamic>? initial;
  const DesignerScreen({super.key, required this.match, this.initial});

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
  // Kulcs-pozíciónként a labdás támadó (0-tól): ahol a következő pontnál
  // más, ott PASSZ — a figura így nem csak futás, a labda is jár.
  List<int> _labda = [0, 0, 0];
  bool get _vanPassz => _labda.any((v) => v != 0);
  int get _pontok => _attackers.isEmpty ? 3 : _attackers.first.length;

  /// Új kulcs-pozíció a mostani UTÁN (a következő pont felé félúton — a
  /// végén a mostani másolata); a labdás a mostanié. Kereszt, visszaadás:
  /// három ponttal nem rajzolható.
  void _pontBe() {
    if (_playing || _pontok >= designerMaxPoints) return;
    final i = _editStep;
    setState(() {
      for (final a in _attackers) {
        final uj = i + 1 < a.length ? Offset.lerp(a[i], a[i + 1], 0.5)! : a[i];
        a.insert(i + 1, uj);
      }
      _labda.insert(i + 1, _labda[i]);
      _editStep = i + 1;
    });
  }

  /// A mostani kulcs-pozíció törlése (legalább kettő marad).
  void _pontKi() {
    if (_playing || _pontok <= 2) return;
    final i = _editStep;
    setState(() {
      for (final a in _attackers) {
        a.removeAt(i);
      }
      _labda.removeAt(i);
      _editStep = i.clamp(0, _pontok - 1);
    });
  }

  late int _numDefenders;
  double _lineDepth = 6.0;

  bool _playing = false;
  // A legutóbbi "tanult védelem" (meccs + védekező oldal) és a figura
  // neve (mentve / betöltve) — a böngészős 3D ugyanazt mutatja.
  String? _tanultMeccs;
  String _tanultOldal = "away";
  String? _nev;
  Match? _sim;
  SetPlayEvaluation? _eval;
  int _playIndex = 0;
  Timer? _timer;

  static const int _animSteps = 40;

  @override
  void initState() {
    super.initState();
    // Alapból 6-0-s fal a hatoson kívül (a fal-geometriát a
    // DefenseModel.respond adja); a mélység-csúszkával tolható feljebb.
    _numDefenders = 6;
    _lineDepth = 6.0;

    final kezdo = widget.initial;
    if (kezdo != null && _kezdoFiguraBetolt(kezdo)) return;
    // Alap figura: irányító, két átlövő, szélső, beálló — az edző átrendezi.
    _attackers = [
      _path3(const Offset(22, 10), const Offset(22, 10)), // irányító (labdás)
      _path3(const Offset(24, 5), const Offset(28, 5)),   // bal átlövő
      _path3(const Offset(24, 15), const Offset(28, 15)), // jobb átlövő
      _path3(const Offset(28, 2), const Offset(31, 2)),   // szélső
      _path3(const Offset(30, 10), const Offset(34, 10)), // beálló (a kapu felé)
    ];
  }

  /// A meccs támadásából kapott kezdő figura (a 3D "✎ Figurává"): igaz,
  /// ha használható volt.
  bool _kezdoFiguraBetolt(Map<String, dynamic> f) {
    try {
      final utak = [
        for (final a in (f["attackers"] as List))
          [
            for (final p in a as List)
              Offset(((p as List)[0] as num).toDouble(), (p[1] as num).toDouble())
          ]
      ];
      if (utak.length < 2 || utak.any((u) => u.isEmpty)) return false;
      final k = utak.first.length.clamp(2, designerMaxPoints);
      _attackers = [for (final u in utak) resamplePath(u, k)];
      final l = [
        for (final v in (f["labda"] as List?) ?? const [])
          (v as num).toInt().clamp(0, _attackers.length - 1)
      ];
      _labda = [for (int i = 0; i < k; i++) i < l.length ? l[i] : (l.isEmpty ? 0 : l.last)];
      final t0 = ((f["t0_s"] as num?) ?? 0).toInt();
      _nev = "${f["csapat"] ?? "Támadás"} támadása "
          "${t0 ~/ 60}:${(t0 % 60).toString().padLeft(2, "0")}";
      // A védelem: a meccs MÁSIK csapatáé (a 3D is ellene nyit).
      if (f["match_id"] is String) {
        _tanultMeccs = f["match_id"] as String;
        _tanultOldal = f["csapat_oldal"] == "home" ? "away" : "home";
      }
      return true;
    } catch (_) {
      return false;
    }
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
    final setplay = SetPlay(interp, setplayBallSteps(_labda, _animSteps));
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
        ballCarrier: setplayBallSteps(_labda, _animSteps),
        defending: side,
      );
      final sim = Match.fromJson(resp["tracking"] as Map<String, dynamic>);
      final eval = evaluateSetPlay(sim);
      if (!mounted) return;
      _tanultMeccs = matchId;
      _tanultOldal = side;
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
          .showSnackBar(SnackBar(content: Text("Szimulációs hiba: ${humanError(e)}")));
    }
  }

  /// A figura böngészős 3D-ben / VR-ben (a motor /figura3d oldala):
  /// valós tempóban, kapussal, ismétlődve — a játékos a saját útját a
  /// saját szemével járja be. A védelem a legutóbbi "tanult védelem"
  /// (meccs + oldal), különben a kézi fal (védőszám, mélység). A csapat
  /// várólapja (/kovet) is linkeli.
  Future<void> _bongeszos3d() =>
      _figura3dNyit(_attackers, _labda, _nev);

  /// A /figura3d megnyitása adott utakkal, labdás-sorral és névvel (a
  /// tervező mostani figurája, vagy egy mentett a listából).
  Future<void> _figura3dNyit(
      List<List<Offset>> utak, List<int> labda, String? nev) async {
    final q = <String, String>{"u": setplay3dPoints(utak)};
    if (labda.any((v) => v != 0)) q["l"] = labda.join(",");
    if ((nev ?? "").isNotEmpty) q["cim"] = nev!;
    final m = _tanultMeccs;
    if (m != null) {
      q["meccs"] = m;
      q["vedo"] = _tanultOldal;
    } else {
      q["vedok"] = "$_numDefenders";
      q["melyseg"] = _lineDepth.toStringAsFixed(1);
    }
    final url = Uri.parse("${_api.baseUrl}/figura3d")
        .replace(queryParameters: q)
        .toString();
    final ok = await openInBrowser(url);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(ok
            ? "A figura a böngészőben, 3D-ben — VR-ben bejárható; a csapat "
                "a /kovet várólapon is eléri (▶ Figura)."
            : "Nyisd meg kézzel a böngészőben: $url")));
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
      await _api.savePlay(name, attackers, labda: _vanPassz ? _labda : null);
      _nev = name;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Figura mentve: $name")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Mentési hiba: ${humanError(e)}")));
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
          SnackBar(content: Text("A könyvtár nem érhető el: ${humanError(e)}")));
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
                          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                            // Egy kattintással 3D-ben (a passzaival) —
                            // betöltés nélkül.
                            IconButton(
                              tooltip: "3D / VR — a böngészőben",
                              icon: const Icon(Icons.view_in_ar_outlined,
                                  size: 18, color: AppColors.accent),
                              onPressed: () async {
                                try {
                                  final play = await _api
                                      .fetchPlay(p["id"] as String);
                                  final utak = [
                                    for (final a in play["attackers"] as List)
                                      [
                                        for (final pt in a as List)
                                          Offset(
                                              ((pt as List)[0] as num).toDouble(),
                                              (pt[1] as num).toDouble())
                                      ]
                                  ];
                                  final labda = [
                                    for (final v
                                        in (play["labda"] as List?) ?? const [])
                                      (v as num).toInt()
                                  ];
                                  await _figura3dNyit(
                                      utak, labda, "${play["name"] ?? ""}");
                                } catch (e) {
                                  if (!mounted) return;
                                  ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(
                                          content: Text(
                                              "A figura nem nyílt meg: ${humanError(e)}")));
                                }
                              },
                            ),
                            IconButton(
                              icon: const Icon(Icons.delete_outline,
                                  size: 18, color: AppColors.textFaint),
                              onPressed: () async {
                                try {
                                  await _api.deletePlay(p["id"] as String);
                                  setDlg(() => plays.remove(p));
                                } catch (_) {}
                              },
                            ),
                          ]),
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
        // A mentett kulcs-pozíciók (legfeljebb designerMaxPoints, és
        // minimum 3 — a régi kétpontos mentés közép-pontot kap); minden
        // játékos ugyanannyi ponton.
        final k = attackers
            .map((a) => a.length)
            .fold<int>(3, (m, n) => n > m ? n : m)
            .clamp(3, designerMaxPoints);
        _attackers = [
          for (final a in attackers)
            if (a.isNotEmpty) resamplePath(a, k),
        ];
        _editStep = 0;
        _nev = "${play["name"] ?? ""}";
        // A mentett labdás-sor (a passzok) a pontokra vetítve, a létező
        // játékosokra szorítva; régi mentésnél végig az 1.
        final l = [
          for (final v in (play["labda"] as List?) ?? const [])
            (v as num).toInt().clamp(0, _attackers.length - 1)
        ];
        _labda = [
          for (int i = 0; i < k; i++)
            l.isEmpty
                ? 0
                : l[(l.length == 1 ? 0 : (i * (l.length - 1) / (k - 1)).round())]
        ];
      });
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Betöltve: ${play["name"]}")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Betöltési hiba: ${humanError(e)}")));
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
            // A tervező menüből (csere-navigációval) is nyílhat — ha nincs
            // hova visszalépni, a Kezdőlapra megyünk (nincs zsákutca).
            onPressed: () {
              final nav = Navigator.of(context);
              if (nav.canPop()) {
                nav.pop();
              } else {
                navTo(context, NavId.dashboard);
              }
            },
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
              painter: _DesignerPainter(
                  attackers: _attackers, step: _editStep, model: _model,
                  labda: _labda),
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
      // A felső rész görgethető: alacsony ablakban (700×600) a lenti
      // gombok (a "3D / VR ↗"-val együtt) így is a helyükön maradnak.
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
         Expanded(
          child: SingleChildScrollView(
           child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
          Row(children: [
            Expanded(
                child: Text("KULCS-POZÍCIÓ", style: AppText.sectionLabel)),
            // Több pont: kereszt, visszaadás (a 3D is viszi).
            IconButton(
              tooltip: "Új kulcs-pozíció a mostani után (legfeljebb "
                  "$designerMaxPoints) — kereszt, visszaadás",
              visualDensity: VisualDensity.compact,
              iconSize: 18,
              onPressed: _playing || _pontok >= designerMaxPoints
                  ? null
                  : _pontBe,
              icon: const Icon(Icons.add_circle_outline),
            ),
            IconButton(
              tooltip: "A mostani kulcs-pozíció törlése",
              visualDensity: VisualDensity.compact,
              iconSize: 18,
              onPressed: _playing || _pontok <= 2 ? null : _pontKi,
              icon: const Icon(Icons.remove_circle_outline),
            ),
          ]),
          const SizedBox(height: AppSpacing.sm),
          SegmentedButton<int>(
            showSelectedIcon: false,
            segments: [
              for (int i = 0; i < _pontok; i++)
                ButtonSegment(value: i, label: Text(keypointLabel(i, _pontok))),
            ],
            selected: {_editStep},
            onSelectionChanged: _playing ? null : (s) => setState(() => _editStep = s.first),
          ),
          const SizedBox(height: AppSpacing.sm),
          // A labdás ennél a kulcs-pozíciónál: ha a következő pontnál más,
          // ott passz (a 3D-ben a labda repül).
          Tooltip(
            message: "Kinél van a labda ennél a kulcs-pozíciónál? Ha a "
                "következő pontnál másnál, az passz — a 3D-ben a labda "
                "átrepül, és a padlón sárga nyíl mutatja.",
            child: Text("LABDA ENNÉL A PONTNÁL",
                style: AppText.label.copyWith(fontSize: 10.5)),
          ),
          const SizedBox(height: 4),
          Wrap(spacing: 4, runSpacing: 4, children: [
            for (int i = 0; i < _attackers.length; i++)
              ChoiceChip(
                label: Text("${i + 1}"),
                visualDensity: VisualDensity.compact,
                selected: _labda[_editStep] == i,
                onSelected: _playing
                    ? null
                    : (_) => setState(() => _labda[_editStep] = i),
              ),
          ]),
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
          Text("VÉDŐFAL (ALAP: 6-0, A HATOSON KÍVÜL)",
              style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text("Védők", style: AppText.label),
            Text("$_numDefenders", style: AppText.value),
          ]),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text("Vonalmélység", style: AppText.label),
            Text("${huNum(_lineDepth)} m", style: AppText.value),
          ]),
          Slider(
            value: _lineDepth, min: 6, max: 12,
            onChanged: _playing ? null : (v) => setState(() => _lineDepth = v),
          ),
            ]),
          ),
         ),
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
                  const SizedBox(height: AppSpacing.sm),
                  // A figura 3D-ben / VR-ben (a böngészőben, bejárható).
                  Tooltip(
                    message: "A figura a böngészős 3D-ben (VR-ben is): valós "
                        "tempóban, kapussal, ismétlődve — a játékos a saját "
                        "útját a saját szemével járja be. A védelem a "
                        "legutóbbi tanult védelem, különben a fenti fal; a "
                        "csapat a /kovet várólapon is eléri.",
                    child: OutlinedButton.icon(
                      onPressed: _bongeszos3d,
                      icon: const Icon(Icons.view_in_ar_outlined, size: 18),
                      label: const Text("3D / VR ↗"),
                    ),
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
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.4)),
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
  final List<int> labda; // kulcs-pozíciónként a labdás

  _DesignerPainter(
      {required this.attackers,
      required this.step,
      required this.model,
      required this.labda});

  int get _labdas => labda[step].clamp(0, attackers.length - 1);

  @override
  void paint(Canvas canvas, Size size) {
    final tr = CourtTransform.fit(size);
    _drawCourt(canvas, tr);

    // Védelem-előnézet (a labdára reagál).
    final ballY = attackers[_labdas][step].dy;
    final defs = model.respond(ballY, courtLength);
    for (final d in defs) {
      final c = tr.toScreen(d.dx, d.dy);
      canvas.drawCircle(c, 0.6 * tr.scale, Paint()..color = AppColors.away.withValues(alpha: 0.45));
    }

    // Útvonal-előnézet: halvány vonal a kulcs-pozíciókon át (látszik az ív).
    final routePaint = Paint()
      ..color = AppColors.home.withValues(alpha: 0.35)
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
      canvas.drawCircle(c, 0.85 * tr.scale, Paint()..color = AppColors.home.withValues(alpha: 0.18));
      canvas.drawCircle(c, 0.65 * tr.scale, Paint()..color = AppColors.home);
      _label(canvas, c, "${i + 1}", 0.65 * tr.scale);
    }

    // A passz, ami ERRE a pontra érkezik (az előző pont labdásától).
    if (step > 0) {
      final elozo = labda[step - 1].clamp(0, attackers.length - 1);
      if (elozo != _labdas) {
        canvas.drawLine(
            tr.toScreen(attackers[elozo][step].dx, attackers[elozo][step].dy),
            tr.toScreen(attackers[_labdas][step].dx, attackers[_labdas][step].dy),
            Paint()
              ..color = AppColors.ball.withValues(alpha: 0.8)
              ..strokeWidth = 2.2);
      }
    }
    // Labda (a labdásnál).
    final b = tr.toScreen(
        attackers[_labdas][step].dx, attackers[_labdas][step].dy);
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
      canvas.drawPath(path, Paint()..color = AppColors.accent.withValues(alpha: 0.07));
      canvas.drawPath(path, line);
    }
    // 9 m-es szaggatott szabaddobási vonal — a figura-tervezőben ez a
    // vonatkoztatás: a fal és az indulási helyek ehhez képest olvashatók
    // (a felülnézeti meccs-kép ugyanezt rajzolja).
    final dash = Paint()
      ..color = AppColors.courtLine.withValues(alpha: 0.75)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..strokeCap = StrokeCap.round;
    for (final leftSide in [true, false]) {
      final pts = freeThrowBoundary(leftSide: leftSide, segments: 22)
          .map((o) => tr.toScreen(o.dx, o.dy))
          .toList();
      for (var i = 0; i + 1 < pts.length; i += 2) {
        canvas.drawLine(pts[i], pts[i + 1], dash);
      }
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
