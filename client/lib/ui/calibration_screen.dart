/// Kalibráló képernyő — a felhasználó a 4 pálya-sarkot ráhúzza a képkockára,
/// és ÉLŐBEN látja a pálya-modellt (négyszög + középvonal + 6 m + kapuk) ráugrani.
///
/// A 4 sarok = teljes homográfia (kép ↔ valós pálya). Ebből lesz a pontos
/// felülnézet és a pályán kívüliek (kispad/edző) szűrése. A referencia-képkockát
/// a backend adja a feltöltött videóból (/reference-frame); ha nincs backend vagy
/// videó, egy helyőrző mutatja a UX-et. A számítás a homography.dart-tal (a backend
/// tükre). Mentéskor a normalizált sarkokat a valódi képpont-koordinátára váltjuk
/// (a képkocka eredeti W×H-jából), és kiírjuk a backend --calib formátumában.
library;

import "dart:typed_data";
import "dart:ui" as ui;

import "package:flutter/material.dart";
import "package:flutter/services.dart";

import "../analytics/homography.dart";
import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";
import "shell/app_shell.dart";

/// A kalibráció eredménye — a feltöltő képernyő ezt kapja vissza, és adja
/// tovább a feldolgozásnak (POST /matches/process).
class CalibrationResult {
  /// A 4 sarok képpont-koordinátában: [[x,y],...] (bal-fent, jobb-fent,
  /// jobb-lent, bal-lent sorrendben).
  final List<List<int>> corners;

  /// Melyik területre illesztettük: "full" | "left" | "right".
  final String region;

  /// 180°-os forgatás (a kamera a túloldalról néz).
  final bool rotate;

  /// A referencia-képkocka indexe — a feldolgozásnak ETTŐL a képkockától kell
  /// indulnia, mert a pásztázás-követés ehhez az álláshoz igazítja a kamerát.
  final int startFrame;

  const CalibrationResult({
    required this.corners,
    required this.region,
    required this.rotate,
    required this.startFrame,
  });
}

/// Egy vagy több kalibráció együtt: teljes pálya (1 bejegyzés), vagy KÜLÖN
/// bal és jobb térfél (2 bejegyzés, akár különböző képkockán bejelölve) —
/// a feldolgozás mindkettőt használja, a saját térfelén a pontosabbal.
class CalibrationSet {
  final List<CalibrationResult> items;
  const CalibrationSet(this.items);

  /// A feldolgozás kezdő képkockája: a legkorábbi kalibrált kocka.
  int get startFrame =>
      items.map((c) => c.startFrame).reduce((a, b) => a < b ? a : b);

  /// Rövid, emberi leírás a feltöltő képernyő gombjára.
  String get label {
    if (items.length == 1) {
      final c = items.first;
      final area = switch (c.region) {
        "left" => "bal térfél",
        "right" => "jobb térfél",
        _ => "teljes pálya",
      };
      return "$area${c.rotate ? ", forgatva" : ""}";
    }
    return "bal + jobb térfél";
  }
}

class CalibrationScreen extends StatefulWidget {
  /// A feltöltött videó backend-oldali elérési útja (ebből tölti be a képkockát).
  /// Ha null, helyőrző jelenik meg a valódi kép helyett.
  final String? videoPath;

  /// A backend alap-URL-je; null = az aktuális alapértelmezés
  /// (ApiClient.defaultBaseUrl — a motor tartalék-portját is követi).
  final String? baseUrl;

  /// Melyik képkockát töltse be referenciának (a bevezető után, tartalmas rész).
  final int frameIndex;

  const CalibrationScreen({
    super.key,
    this.videoPath,
    this.baseUrl,
    this.frameIndex = 180,
  });

  @override
  State<CalibrationScreen> createState() => _CalibrationScreenState();
}

class _CalibrationScreenState extends State<CalibrationScreen> {
  // A képkocka mérete a vásznon (kicsinyíthető): a kép körüli sávba a
  // sarok-pontok KIHÚZHATÓK — ha a pálya széle messze kilóg a képből,
  // kicsinyítéssel annyi hely lesz körülötte, amennyi kell.
  double _imgScale = 0.76;
  double get _margin => (1 - _imgScale) / 2;
  // A 4 sarok a VÁSZON területén, arányban (0..1) — a kép a vászon közepén ül,
  // körülötte sáv, így a pontok a képen kívülre is tehetők.
  // Sorrend: távoli-bal, távoli-jobb, közeli-jobb, közeli-bal.
  List<Offset> _corners = const [
    Offset(0.25, 0.40), Offset(0.75, 0.38), Offset(0.85, 0.75), Offset(0.15, 0.80),
  ];

  // Az aktuális referencia-képkocka indexe — léptethető, hogy olyan állást
  // válassz, ahol a bejelölendő terület a legjobban látszik.
  late int _frameIdx = widget.frameIndex;
  int? _drag;
  bool _saved = false;

  // Melyik területet jelöljük be: teljes pálya vagy csak az egyik térfél
  // (pásztázó kameránál az induló képen sokszor csak egy térfél látszik).
  String _region = "full"; // full | left | right
  // 180°-os forgatás: ha a kamera a túloldali lelátóról néz.
  bool _rotate = false;

  // KÜLÖN elmentett bal/jobb térfél-kalibrációk (akár külön képkockán) —
  // a Kész gombbal együtt kerülnek vissza a feltöltő képernyőre.
  CalibrationResult? _savedLeft;
  CalibrationResult? _savedRight;

  // ÖSSZENÉZET (6 pontos finomhangolás): a két térfél EGY nézetben — a 4
  // pályasarok ÉS a felezővonal két vége is külön állítható.
  bool _fineTune = false;
  // Sorrend: távoli-bal, felező-távoli, távoli-jobb, közeli-jobb,
  // felező-közeli, közeli-bal.
  List<Offset> _six = const [
    Offset(0.16, 0.38), Offset(0.50, 0.36), Offset(0.84, 0.38),
    Offset(0.92, 0.78), Offset(0.50, 0.82), Offset(0.08, 0.78),
  ];

  /// Az éppen szerkesztett pontlista (4 sarok VAGY a 6 pontos összenézet).
  List<Offset> get _activePts => _fineTune ? _six : _corners;

  // A betöltött referencia-képkocka és eredeti mérete (a képpont-export miatt).
  Uint8List? _frameBytes;
  Size? _frameSize;
  bool _loading = false;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    _loadReferenceFrame();
  }

  /// Betölti a referencia-képkockát a backendtől; hiba esetén helyőrzőre esünk vissza.
  Future<void> _loadReferenceFrame() async {
    if (widget.videoPath == null) return; // nincs videó → marad a helyőrző
    setState(() => _loading = true);
    try {
      final api = ApiClient(baseUrl: widget.baseUrl);
      final bytes = await api.fetchReferenceFrame(widget.videoPath!, t: _frameIdx);
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final img = frame.image;
      if (!mounted) return;
      setState(() {
        _frameBytes = bytes;
        _frameSize = Size(img.width.toDouble(), img.height.toDouble());
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadError = "$e";
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.upload,
      crumbTag: "1e",
      crumbPath: "KALIBRÁCIÓ · PÁLYA ILLESZTÉSE",
      collapsed: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("Pálya-kalibráció", style: AppText.title),
          const SizedBox(height: 4),
          Text(
              "Húzd a 4 sarkot a pálya sarkaira — a kép KÖRÜLI sávba is húzhatod, "
              "ha a pálya széle kilóg a képből. A képkocka léptethető.",
              style: AppText.subtitle),
          const SizedBox(height: AppSpacing.lg),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(child: _frameCard()),
                const SizedBox(width: AppSpacing.lg),
                SizedBox(width: 280, child: _sidePanel()),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _frameCard() {
    return Container(
      decoration: AppTheme.card(),
      clipBehavior: Clip.antiAlias,
      child: LayoutBuilder(
        builder: (context, c) {
          final size = Size(c.maxWidth, c.maxHeight);
          final pts = [for (final f in _activePts) Offset(f.dx * size.width, f.dy * size.height)];
          return GestureDetector(
            onPanStart: (d) {
              double best = 32;
              _drag = null;
              for (int i = 0; i < pts.length; i++) {
                final dist = (pts[i] - d.localPosition).distance;
                if (dist < best) { best = dist; _drag = i; }
              }
            },
            onPanUpdate: (d) {
              if (_drag == null) return;
              setState(() {
                final next = [..._activePts];
                next[_drag!] = Offset(
                  (d.localPosition.dx / size.width).clamp(0.0, 1.0),
                  (d.localPosition.dy / size.height).clamp(0.0, 1.0),
                );
                if (_fineTune) {
                  _six = next;
                } else {
                  _corners = next;
                }
                _saved = false;
              });
            },
            onPanEnd: (_) => _drag = null,
            // A valódi képkocka a sarkok ALATT, a vászon közepén, körülötte
            // sávval — így a pontok a képen KÍVÜLRE is húzhatók (pl. ha a
            // közeli pályaszél kilóg a képből). Exportnál a sávot levonjuk.
            child: Stack(
              fit: StackFit.expand,
              children: [
                Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: size.width * _margin,
                    vertical: size.height * _margin,
                  ),
                  child: _frameBytes != null
                      ? Image.memory(_frameBytes!, fit: BoxFit.fill, gaplessPlayback: true)
                      : _placeholder(),
                ),
                CustomPaint(
                  painter: _CalibPainter(pts,
                      region: _region,
                      rotate: _rotate,
                      margin: _margin,
                      fine: _fineTune,
                      drawBackground: _frameBytes == null),
                  size: size,
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  /// Helyőrző, ha nincs valódi képkocka (nincs videó vagy backend).
  Widget _placeholder() {
    return Container(
      color: const Color(0xFF0C1119),
      alignment: Alignment.topLeft,
      padding: const EdgeInsets.all(16),
      child: Text(
        _loading
            ? "referencia képkocka betöltése…"
            : _loadError != null
                ? "nincs képkocka (backend/videó nélkül) — helyőrző"
                : "referencia képkocka (helyőrző)",
        style: AppText.label.copyWith(color: AppColors.textFaint),
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
          Text("KÉPKOCKA", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          // Léptetés a videóban: válassz olyan képkockát, ahol a bejelölendő
          // terület a LEGJOBBAN látszik. A feldolgozás ettől a kockától indul,
          // a pásztázás-követés innen követi a kamerát a többi állásra.
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _stepBtn("−30s", -750),
              _stepBtn("−5s", -125),
              _stepBtn("+5s", 125),
              _stepBtn("+30s", 750),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            "~${(_frameIdx / 25).round()} mp ($_frameIdx. kocka) — a feldolgozás "
            "innen indul",
            style: AppText.label.copyWith(fontSize: 11),
          ),
          const SizedBox(height: AppSpacing.md),
          Text("KÉP MÉRETE", style: AppText.sectionLabel),
          const SizedBox(height: 2),
          // Kicsinyítés: ha a pálya sarka messze kilóg a képből, vedd kisebbre
          // a képet — annyi hely lesz körülötte, amennyi kell.
          Row(children: [
            IconButton(
              onPressed: _imgScale > 0.26
                  ? () => _setScale((_imgScale - 0.12).clamp(0.25, 1.0))
                  : null,
              icon: const Icon(Icons.zoom_out, size: 20, color: AppColors.textSecondary),
              tooltip: "Kép kicsinyítése (több hely a sarkoknak)",
            ),
            Expanded(
              child: Text(
                "${(_imgScale * 100).round()}% — kicsinyítsd, ha a sarok nem fér el",
                style: AppText.label.copyWith(fontSize: 11),
                textAlign: TextAlign.center,
              ),
            ),
            IconButton(
              onPressed: _imgScale < 0.99
                  ? () => _setScale((_imgScale + 0.12).clamp(0.25, 1.0))
                  : null,
              icon: const Icon(Icons.zoom_in, size: 20, color: AppColors.textSecondary),
              tooltip: "Kép nagyítása",
            ),
          ]),
          const SizedBox(height: AppSpacing.md),
          if (!_fineTune) ...[
          Text("TERÜLET", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          // Ha csak az egyik térfél látszik a képen, a 4 pontot a TÉRFÉL
          // sarkaira kell húzni (a felezővonal két vége is "sarok").
          SegmentedButton<String>(
            showSelectedIcon: false,
            style: const ButtonStyle(visualDensity: VisualDensity.compact),
            segments: const [
              ButtonSegment(value: "full", label: Text("Teljes")),
              ButtonSegment(value: "left", label: Text("Bal fél")),
              ButtonSegment(value: "right", label: Text("Jobb fél")),
            ],
            selected: {_region},
            onSelectionChanged: (s) => setState(() {
              _region = s.first;
              _saved = false;
            }),
          ),
          const SizedBox(height: AppSpacing.sm),
          // Forgatás: ha a pálya "fejjel lefelé" látszik (túloldali kamera).
          Row(children: [
            Expanded(
              child: Text("Forgatás 180°",
                  style: AppText.label.copyWith(color: AppColors.textPrimary)),
            ),
            Switch(
              value: _rotate,
              activeColor: AppColors.accent,
              onChanged: (v) => setState(() {
                _rotate = v;
                _saved = false;
              }),
            ),
          ]),
          ],
          const SizedBox(height: AppSpacing.md),
          Text(_fineTune ? "PONTOK (ÖSSZENÉZET)" : "SARKOK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          if (_fineTune) ...[
            _cornerRow("Távoli-bal", 0),
            _cornerRow("Felező-távoli", 1),
            _cornerRow("Távoli-jobb", 2),
            _cornerRow("Közeli-jobb", 3),
            _cornerRow("Felező-közeli", 4),
            _cornerRow("Közeli-bal", 5),
          ] else ...[
            _cornerRow("Távoli-bal", 0),
            _cornerRow("Távoli-jobb", 1),
            _cornerRow("Közeli-jobb", 2),
            _cornerRow("Közeli-bal", 3),
          ],
          const Spacer(),
          Text(
            _fineTune
                ? "ÖSSZENÉZET: a teljes pálya 6 ponttal — a 4 sarok ÉS a "
                    "felezővonal két vége is húzható. Mindkét fél modellje "
                    "élőben illeszkedik."
                : _region == "full"
                    ? "Tipp: ha csak az egyik térfél látszik a képen, válaszd a "
                        "Bal/Jobb fél gombot — a pontokat a térfél sarkaira húzd "
                        "(a felezővonal két vége is sarok)."
                    : "A 4 pontot a KIVÁLASZTOTT TÉRFÉL sarkaira húzd: 2 valódi "
                        "pályasarok + a felezővonal két vége.",
            style: AppText.label.copyWith(fontSize: 11, color: AppColors.gold),
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            _frameSize != null
                ? "Kép: ${_frameSize!.width.toInt()}×${_frameSize!.height.toInt()} px. "
                    "Mentéskor a sarkokat a valódi képpontokra váltjuk és a "
                    "vágólapra másoljuk (--calib formátum)."
                : "Éles használatban ide a feltöltött videó egy képkockája kerül; a 4 "
                    "sarokból a rendszer kiszámolja a homográfiát, és a pályán kívüli "
                    "személyeket (kispad, edző) automatikusan kiszűri.",
            style: AppText.label.copyWith(fontSize: 11),
          ),
          const SizedBox(height: AppSpacing.md),
          // Az elmentett térfél-kalibrációk állapota.
          if (_savedLeft != null || _savedRight != null) ...[
            Row(children: [
              Icon(_savedLeft != null ? Icons.check_circle : Icons.circle_outlined,
                  size: 15, color: _savedLeft != null ? AppColors.gold : AppColors.textFaint),
              const SizedBox(width: 6),
              Text(
                  _savedLeft != null
                      ? "Bal fél: mentve (${_savedLeft!.startFrame}. kocka)"
                      : "Bal fél: nincs",
                  style: AppText.label.copyWith(fontSize: 11)),
            ]),
            const SizedBox(height: 2),
            Row(children: [
              Icon(_savedRight != null ? Icons.check_circle : Icons.circle_outlined,
                  size: 15, color: _savedRight != null ? AppColors.gold : AppColors.textFaint),
              const SizedBox(width: 6),
              Text(
                  _savedRight != null
                      ? "Jobb fél: mentve (${_savedRight!.startFrame}. kocka)"
                      : "Jobb fél: nincs",
                  style: AppText.label.copyWith(fontSize: 11)),
            ]),
            const SizedBox(height: AppSpacing.sm),
          ],
          if (_fineTune) ...[
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: AppColors.gold, foregroundColor: AppColors.onAccent),
              onPressed: _finishFine,
              icon: const Icon(Icons.done_all),
              label: const Text("Kész (összeillesztett pálya)"),
            ),
            const SizedBox(height: AppSpacing.sm),
            TextButton.icon(
              onPressed: () => setState(() => _fineTune = false),
              icon: const Icon(Icons.undo, size: 16),
              label: const Text("Vissza a térfelekhez"),
            ),
          ] else ...[
            FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
              onPressed: _save,
              icon: const Icon(Icons.check),
              label: Text(switch (_region) {
                "left" => "Bal térfél mentése",
                "right" => "Jobb térfél mentése",
                _ => _saved ? "Kalibráció mentve" : "Kalibráció mentése",
              }),
            ),
            // Összenézet: a két mentett térfél összeillesztése és finomhangolása.
            if (_savedLeft != null && _savedRight != null) ...[
              const SizedBox(height: AppSpacing.sm),
              OutlinedButton.icon(
                onPressed: _enterFineTune,
                style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.gold,
                    side: const BorderSide(color: AppColors.gold)),
                icon: const Icon(Icons.join_full, size: 18),
                label: const Text("Összenézet: 6 pontos finomhangolás"),
              ),
            ],
            // Térfél-kalibrációnál: visszatérés az elmentett felekkel.
            if (_savedLeft != null || _savedRight != null) ...[
              const SizedBox(height: AppSpacing.sm),
              FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: AppColors.gold, foregroundColor: AppColors.onAccent),
                onPressed: _finish,
                icon: const Icon(Icons.done_all),
                label: Text(_savedLeft != null && _savedRight != null
                    ? "Kész (bal + jobb térfél)"
                    : "Kész (1 térféllel)"),
              ),
            ],
          ],
        ],
      ),
    );
  }

  /// Az aktuális beállítás (sarkok + terület + forgatás + képkocka) egy
  /// CalibrationResult-tá alakítva, képpont-koordinátákkal.
  CalibrationResult _currentResult() {
    final w = _frameSize?.width ?? 1920.0;
    final h = _frameSize?.height ?? 1080.0;
    // A vászon-koordinátából levonjuk a kép körüli sávot: a [margó..1-margó]
    // tartomány felel meg a képkockának. A sávba húzott pont képen KÍVÜLI
    // (negatív vagy W/H fölötti) képpontot ad — a homográfiának ez így jó.
    double toImg(double v) => (v - _margin) / (1 - 2 * _margin);
    return CalibrationResult(
      corners: [
        for (final cn in _corners)
          [(toImg(cn.dx) * w).round(), (toImg(cn.dy) * h).round()],
      ],
      region: _region,
      rotate: _rotate,
      startFrame: _frameIdx,
    );
  }

  /// Mentés: teljes pályánál azonnal visszatér; térfélnél a bal/jobb HELYRE
  /// menti el (így KÜLÖN kalibrálható a két térfél, akár külön képkockán),
  /// és a Kész gombbal együtt kerülnek vissza a feltöltő képernyőre.
  Future<void> _save() async {
    final res = _currentResult();
    // A vágólapra is (CLI-hez / hibakereséshez).
    final json =
        "[${res.corners.map((p) => "[${p[0]},${p[1]}]").join(",")}]";
    await Clipboard.setData(ClipboardData(text: json));
    if (!mounted) return;

    if (_region == "full") {
      setState(() => _saved = true);
      Navigator.of(context).pop(CalibrationSet([res]));
      return;
    }
    setState(() {
      if (_region == "left") {
        _savedLeft = res;
      } else {
        _savedRight = res;
      }
      _saved = true;
    });
    final other = _region == "left" ? "jobb" : "bal";
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text("A(z) ${_region == "left" ? "bal" : "jobb"} térfél "
            "elmentve. Jelölheted a $other térfelet is (léptethetsz másik "
            "képkockára), vagy nyomd meg a Kész gombot.")));
  }

  /// Belépés az ÖSSZENÉZETBE: a 6 pont a mentett bal/jobb kalibrációból áll
  /// össze (a felezővonal két vége a két oldal jelölésének átlaga).
  void _enterFineTune() {
    final l = _savedLeft, r = _savedRight;
    if (l == null || r == null) return;
    final w = _frameSize?.width ?? 1920.0;
    final h = _frameSize?.height ?? 1080.0;
    Offset toCanvas(List<int> p) => Offset(
        _margin + p[0] / w * (1 - 2 * _margin),
        _margin + p[1] / h * (1 - 2 * _margin));
    Offset mid(Offset a, Offset b) =>
        Offset((a.dx + b.dx) / 2, (a.dy + b.dy) / 2);
    setState(() {
      _six = [
        toCanvas(l.corners[0]), // távoli-bal
        mid(toCanvas(l.corners[1]), toCanvas(r.corners[0])), // felező-távoli
        toCanvas(r.corners[1]), // távoli-jobb
        toCanvas(r.corners[2]), // közeli-jobb
        mid(toCanvas(l.corners[2]), toCanvas(r.corners[3])), // felező-közeli
        toCanvas(l.corners[3]), // közeli-bal
      ];
      _fineTune = true;
      _saved = false;
    });
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text("Összenézet: a 4 sarok ÉS a felezővonal két vége is "
            "húzható. Ha a két felet külön képkockán jelölted, léptess olyan "
            "kockára, ahol az egész pálya látszik.")));
  }

  /// Az összenézet mentése: a 6 pontból KÉT térfél-kalibráció készül
  /// (ugyanarra a képkockára), és visszatérünk a feltöltő képernyőre.
  void _finishFine() {
    final w = _frameSize?.width ?? 1920.0;
    final h = _frameSize?.height ?? 1080.0;
    double toImg(double v) => (v - _margin) / (1 - 2 * _margin);
    List<int> px(Offset o) =>
        [(toImg(o.dx) * w).round(), (toImg(o.dy) * h).round()];
    final fl = px(_six[0]), mf = px(_six[1]), fr = px(_six[2]);
    final nr = px(_six[3]), mn = px(_six[4]), nl = px(_six[5]);
    Navigator.of(context).pop(CalibrationSet([
      // Bal fél: távoli-bal, felező-távoli, felező-közeli, közeli-bal.
      CalibrationResult(corners: [fl, mf, mn, nl], region: "left",
          rotate: false, startFrame: _frameIdx),
      // Jobb fél: felező-távoli, távoli-jobb, közeli-jobb, felező-közeli.
      CalibrationResult(corners: [mf, fr, nr, mn], region: "right",
          rotate: false, startFrame: _frameIdx),
    ]));
  }

  /// Visszatérés az elmentett térfél-kalibrációkkal (1 vagy 2 bejegyzés).
  void _finish() {
    final items = [
      // A korábbi képkockán lévő az első — a feldolgozás onnan indul.
      if (_savedLeft != null) _savedLeft!,
      if (_savedRight != null) _savedRight!,
    ]..sort((a, b) => a.startFrame.compareTo(b.startFrame));
    if (items.isEmpty) return;
    Navigator.of(context).pop(CalibrationSet(items));
  }

  /// Kép-kicsinyítés/nagyítás: a sarkokat átszámoljuk, hogy a KÉPHEZ képesti
  /// helyükön maradjanak (ne csússzanak el a kép alatt a méretváltáskor).
  void _setScale(double next) {
    final mOld = _margin;
    final mNew = (1 - next) / 2;
    setState(() {
      // NINCS levágás: a pont a KÉPHEZ képesti helyén marad akkor is, ha
      // így a vásznon kívülre kerül — kicsinyítéskor újra elérhető.
      List<Offset> remap(List<Offset> pts) => [
            for (final c in pts)
              Offset(
                mNew + (c.dx - mOld) / (1 - 2 * mOld) * (1 - 2 * mNew),
                mNew + (c.dy - mOld) / (1 - 2 * mOld) * (1 - 2 * mNew),
              ),
          ];
      _corners = remap(_corners);
      _six = remap(_six);
      _imgScale = next;
      _saved = false;
    });
  }

  /// Léptető gomb a referencia-képkockához (a delta 25 fps-sel számolt kocka).
  Widget _stepBtn(String label, int delta) => OutlinedButton(
        style: OutlinedButton.styleFrom(
          visualDensity: VisualDensity.compact,
          padding: const EdgeInsets.symmetric(horizontal: 8),
          foregroundColor: AppColors.textSecondary,
          side: const BorderSide(color: AppColors.borderStrong),
        ),
        onPressed: () {
          setState(() {
            _frameIdx = (_frameIdx + delta).clamp(0, 1 << 20);
            _saved = false;
          });
          _loadReferenceFrame();
        },
        child: Text(label, style: const TextStyle(fontSize: 11)),
      );

  Widget _cornerRow(String name, int i) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Row(children: [
            Container(width: 10, height: 10, decoration: const BoxDecoration(color: AppColors.accent, shape: BoxShape.circle)),
            const SizedBox(width: 8),
            Text(name, style: AppText.label.copyWith(color: AppColors.textPrimary)),
          ]),
          Text("${(_activePts[i].dx * 100).round()}, ${(_activePts[i].dy * 100).round()}",
              style: AppText.label.copyWith(fontSize: 11)),
        ]),
      );
}

/// Kirajzolja a húzható sarkokat + a pálya-modellt (a képkocka fölé).
class _CalibPainter extends CustomPainter {
  final List<Offset> corners; // 4 kép-pont (pixel)
  final String region; // full | left | right — mire illesztjük a 4 pontot
  final bool rotate; // 180°-os forgatás (túloldali kamera)
  final double margin; // a képkocka körüli sáv aránya (kicsinyítésnél nő)
  final bool fine; // összenézet: 6 pont (4 sarok + felezővonal két vége)
  final bool drawBackground; // helyőrző háttér (ha nincs valódi képkocka)
  _CalibPainter(this.corners,
      {this.region = "full", this.rotate = false, this.margin = 0.12,
       this.fine = false, this.drawBackground = true});

  @override
  void paint(Canvas canvas, Size size) {
    if (drawBackground) {
      canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF0C1119));
    }

    // A képkocka széle (a körülötte lévő sávban a pontok képen KÍVÜLI
    // helyet jelölnek — pl. a levágott közeli pályaszélet).
    canvas.drawRect(
      Rect.fromLTRB(margin * size.width, margin * size.height,
          (1 - margin) * size.width, (1 - margin) * size.height),
      Paint()
        ..color = const Color(0x668492A6)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );

    // ÖSSZENÉZET: 6 pontból a KÉT térfél homográfiája — mindkét fél
    // modellje élőben illeszkedik, a felezővonal a két fél közös éle.
    if (fine && corners.length == 6) {
      _paintFine(canvas);
      _drawHandles(canvas);
      return;
    }

    // A kijelölt terület (teljes pálya vagy térfél) sarkai méterben.
    final (x0, x1) = switch (region) {
      "left" => (0.0, courtLength / 2),
      "right" => (courtLength / 2, courtLength),
      _ => (0.0, courtLength),
    };
    var courtCorners = [
      [x0, 0.0], [x1, 0.0], [x1, courtWidth], [x0, courtWidth],
    ];
    if (rotate) {
      // 180°: a képen bejelölt sarkok a terület átellenes sarkainak felelnek meg.
      courtCorners = [courtCorners[2], courtCorners[3], courtCorners[0], courtCorners[1]];
    }
    final dst = [for (final c in corners) [c.dx, c.dy]];
    final h = homographyFromPoints(courtCorners, dst);
    Offset p(double mx, double my) {
      final r = applyHomography(h, mx, my);
      return Offset(r[0], r[1]);
    }

    final line = Paint()..color = AppColors.accent..style = PaintingStyle.stroke..strokeWidth = 2.5;
    final gold = Paint()..color = AppColors.gold..style = PaintingStyle.stroke..strokeWidth = 2;
    final goalP = Paint()..color = AppColors.away..style = PaintingStyle.stroke..strokeWidth = 4;

    final path = Path()..moveTo(corners[0].dx, corners[0].dy);
    for (int i = 1; i < 4; i++) { path.lineTo(corners[i].dx, corners[i].dy); }
    path.close();
    canvas.drawPath(path, line);
    // Felezővonal — csak ha a kijelölt területre esik (térfélnél a széle).
    if (courtLength / 2 >= x0 && courtLength / 2 <= x1) {
      canvas.drawLine(p(courtLength / 2, 0), p(courtLength / 2, courtWidth), line);
    }

    const cy = courtWidth / 2;
    // Kapuk + 6 m-es kapuelőtér — csak a látható területen lévő kapukra.
    // A vonal a SZABÁLYKÖNYVI alak (goalAreaBoundary): a két kapufától húzott
    // 6 m-es negyedkörív, köztük a kapu előtt 3 m-es egyenes — NEM félkör.
    for (final gx in [0.0, courtLength]) {
      if (gx < x0 - 0.01 || gx > x1 + 0.01) continue; // ez a kapu nem látszik
      canvas.drawLine(p(gx, cy - 1.5), p(gx, cy + 1.5), goalP);
      Offset? prev;
      for (final b in goalAreaBoundary(leftSide: gx == 0.0, segments: 20)) {
        final cur = p(b.dx, b.dy);
        if (prev != null) canvas.drawLine(prev, cur, gold);
        prev = cur;
      }
    }

    _drawHandles(canvas);
  }

  /// A húzható pontok (fogantyúk) kirajzolása.
  void _drawHandles(Canvas canvas) {
    for (final c in corners) {
      canvas.drawCircle(c, 11, Paint()..color = AppColors.accent.withOpacity(0.25));
      canvas.drawCircle(c, 7, Paint()..color = AppColors.accent);
      canvas.drawCircle(c, 7, Paint()..color = Colors.white..style = PaintingStyle.stroke..strokeWidth = 1.5);
    }
  }

  /// Összenézet: a 6 pontból (4 sarok + felezővonal két vége) a két térfél
  /// KÜLÖN homográfiája — kapuk + 6 m-es ívek mindkét oldalon.
  void _paintFine(Canvas canvas) {
    final fl = corners[0], mf = corners[1], fr = corners[2];
    final nr = corners[3], mn = corners[4], nl = corners[5];
    final line = Paint()..color = AppColors.accent..style = PaintingStyle.stroke..strokeWidth = 2.5;
    final gold = Paint()..color = AppColors.gold..style = PaintingStyle.stroke..strokeWidth = 2;
    final goalP = Paint()..color = AppColors.away..style = PaintingStyle.stroke..strokeWidth = 4;

    // Külső keret + felezővonal (a két fél közös éle).
    final outer = Path()
      ..moveTo(fl.dx, fl.dy)
      ..lineTo(mf.dx, mf.dy)
      ..lineTo(fr.dx, fr.dy)
      ..lineTo(nr.dx, nr.dy)
      ..lineTo(mn.dx, mn.dy)
      ..lineTo(nl.dx, nl.dy)
      ..close();
    canvas.drawPath(outer, line);
    canvas.drawLine(mf, mn, line);

    const cy = courtWidth / 2;
    final half = courtLength / 2;
    // (négyszög, kapu x-koordinátája, a fél pálya-sarkai méterben)
    final halves = [
      ([fl, mf, mn, nl], 0.0,
       [[0.0, 0.0], [half, 0.0], [half, courtWidth], [0.0, courtWidth]]),
      ([mf, fr, nr, mn], courtLength,
       [[half, 0.0], [courtLength, 0.0], [courtLength, courtWidth], [half, courtWidth]]),
    ];
    for (final (quad, gx, courtPts) in halves) {
      final h = homographyFromPoints(
          courtPts, [for (final q in quad) [q.dx, q.dy]]);
      Offset p(double mx, double my) {
        final r = applyHomography(h, mx, my);
        return Offset(r[0], r[1]);
      }

      canvas.drawLine(p(gx, cy - 1.5), p(gx, cy + 1.5), goalP);
      // Szabálykönyvi kapuelőtér-vonal (negyedkörívek + 3 m egyenes).
      Offset? prev;
      for (final b in goalAreaBoundary(leftSide: gx == 0.0, segments: 20)) {
        final cur = p(b.dx, b.dy);
        if (prev != null) canvas.drawLine(prev, cur, gold);
        prev = cur;
      }
    }
  }

  @override
  bool shouldRepaint(covariant _CalibPainter old) =>
      old.corners != corners ||
      old.region != region ||
      old.rotate != rotate ||
      old.margin != margin ||
      old.fine != fine ||
      old.drawBackground != drawBackground;
}
