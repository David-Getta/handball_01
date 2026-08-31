/// Beépített címkéző — a tanítóadat átnézése és javítása az appban.
///
/// A finomhangolás-lánc középső lépése (gyűjtés → ÁTNÉZÉS → tanítás)
/// eddig külső eszközt kért (CVAT/LabelImg) — regisztráció, import,
/// export. Itt ugyanez három gombbal megy: doboz rajzolása húzással,
/// osztály-váltás, törlés; a mentés szabványos YOLO-sorokat ír, tehát
/// a kimenet külső eszközzel is kompatibilis marad.
///
/// A leggyakoribb munka a HIÁNYZÓ LABDA pótlása — ezért a rajzolás
/// alapértelmezett osztálya váltható, és a lista mutatja, melyik képen
/// hány doboz van (a 0 dobozos kép gyanús).
library;

import "dart:typed_data";

import "package:flutter/material.dart";
import "package:http/http.dart" as http;

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "waiting.dart";

class LabelScreen extends StatefulWidget {
  const LabelScreen({super.key});

  @override
  State<LabelScreen> createState() => _LabelScreenState();
}

class _LabelScreenState extends State<LabelScreen> {
  final ApiClient _api = ApiClient();

  List<Map<String, dynamic>> _kepek = [];
  int _index = -1;
  Uint8List? _kepBytes;
  // Dobozok normált alakban: [osztály, cx, cy, w, h] (0..1).
  List<List<num>> _dobozok = [];
  int? _kijelolt;
  int _rajzOsztaly = 1; // alapból LABDA — az a leggyakoribb pótlás
  bool _modositott = false;
  String? _uzenet;
  Offset? _huzasKezdet, _huzasVege; // normált (0..1) koordináták

  @override
  void initState() {
    super.initState();
    _betolt();
  }

  Future<void> _betolt() async {
    try {
      final r = await _api.fetchDatasetImages();
      if (!mounted) return;
      setState(() {
        _kepek = r;
        _uzenet = r.isEmpty
            ? "Még nincs gyűjtött kép — előbb a Kezdőlap → Továbbiak → "
                "Tanítóadat gyűjtése."
            : null;
      });
      if (r.isNotEmpty) await _valaszt(0);
    } catch (e) {
      if (!mounted) return;
      setState(() => _uzenet = humanError(e));
    }
  }

  Future<void> _valaszt(int i) async {
    if (i < 0 || i >= _kepek.length) return;
    if (_modositott) await _ment(csendes: true);
    final kep = _kepek[i];
    setState(() {
      _index = i;
      _kepBytes = null;
      _dobozok = [];
      _kijelolt = null;
      _modositott = false;
    });
    try {
      final split = kep["split"] as String, nev = kep["name"] as String;
      final img = await http.get(Uri.parse(
          "${_api.baseUrl}/dataset/image/$split/$nev"));
      final cimkek = await _api.fetchDatasetLabels(split, nev);
      if (!mounted || _index != i) return;
      setState(() {
        _kepBytes = img.bodyBytes;
        _dobozok = cimkek;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _uzenet = humanError(e));
    }
  }

  Future<void> _ment({bool csendes = false}) async {
    if (_index < 0) return;
    final kep = _kepek[_index];
    try {
      await _api.saveDatasetLabels(
          kep["split"] as String, kep["name"] as String, _dobozok);
      if (!mounted) return;
      setState(() {
        _modositott = false;
        _kepek[_index]["boxes"] = _dobozok.length;
      });
      if (!csendes) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            duration: Duration(seconds: 1),
            content: Text("Címkék mentve.")));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(humanError(e))));
    }
  }

  // A megjelenített kép téglalapja a vásznon (BoxFit.contain szerint).
  Rect _kepRect(Size vaszon, Size kep) {
    final arany = kep.width / kep.height;
    var w = vaszon.width, h = w / arany;
    if (h > vaszon.height) {
      h = vaszon.height;
      w = h * arany;
    }
    return Rect.fromLTWH(
        (vaszon.width - w) / 2, (vaszon.height - h) / 2, w, h);
  }

  Offset? _normalt(Offset lokal, Rect r) {
    final nx = (lokal.dx - r.left) / r.width;
    final ny = (lokal.dy - r.top) / r.height;
    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
    return Offset(nx, ny);
  }

  void _koppint(Offset norm) {
    // A legkisebb doboz nyer, amelyik tartalmazza a pontot — így a
    // labda a játékos-doboz belsejében is kijelölhető.
    int? talalat;
    double talalatTerulet = double.infinity;
    for (var i = 0; i < _dobozok.length; i++) {
      final b = _dobozok[i];
      final cx = b[1].toDouble(), cy = b[2].toDouble();
      final w = b[3].toDouble(), h = b[4].toDouble();
      if ((norm.dx - cx).abs() <= w / 2 && (norm.dy - cy).abs() <= h / 2) {
        final t = w * h;
        if (t < talalatTerulet) {
          talalat = i;
          talalatTerulet = t;
        }
      }
    }
    setState(() => _kijelolt = talalat);
  }

  void _ujDoboz(Offset a, Offset b) {
    final x1 = a.dx < b.dx ? a.dx : b.dx, x2 = a.dx < b.dx ? b.dx : a.dx;
    final y1 = a.dy < b.dy ? a.dy : b.dy, y2 = a.dy < b.dy ? b.dy : a.dy;
    final w = x2 - x1, h = y2 - y1;
    if (w < 0.004 || h < 0.004) return; // véletlen kattintás, nem doboz
    setState(() {
      _dobozok.add([_rajzOsztaly, x1 + w / 2, y1 + h / 2, w, h]);
      _kijelolt = _dobozok.length - 1;
      _modositott = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        title: const Text("Címkéző — tanítóadat átnézése"),
        actions: [
          if (_modositott)
            TextButton(
                onPressed: _ment, child: const Text("Mentés")),
          const SizedBox(width: 8),
        ],
      ),
      body: _uzenet != null && _kepek.isEmpty
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(_uzenet!, style: AppText.label),
              ),
            )
          : Row(children: [
              // Kép-lista: a 0 dobozos kép gyanús (hiányzó címkék).
              SizedBox(
                width: 230,
                child: ListView.builder(
                  itemCount: _kepek.length,
                  itemBuilder: (_, i) {
                    final k = _kepek[i];
                    final n = (k["boxes"] as num?)?.toInt() ?? 0;
                    return ListTile(
                      dense: true,
                      selected: i == _index,
                      selectedTileColor: AppColors.surfaceAlt,
                      title: Text(k["name"] as String,
                          overflow: TextOverflow.ellipsis,
                          style: AppText.label.copyWith(fontSize: 11.5)),
                      trailing: Text("$n",
                          style: AppText.label.copyWith(
                              fontSize: 11,
                              color: n == 0
                                  ? AppColors.gold
                                  : AppColors.textFaint)),
                      onTap: () => _valaszt(i),
                    );
                  },
                ),
              ),
              const VerticalDivider(width: 1),
              Expanded(
                child: Column(children: [
                  _eszkozsor(),
                  Expanded(child: _vaszon()),
                ]),
              ),
            ]),
    );
  }

  Widget _eszkozsor() {
    Widget cimke(String t, Color c) => Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
              color: c.withOpacity(0.15),
              border: Border.all(color: c),
              borderRadius: BorderRadius.circular(6)),
          child: Text(t, style: AppText.label.copyWith(fontSize: 11, color: c)),
        );
    final kivalasztott = _kijelolt != null && _kijelolt! < _dobozok.length
        ? _dobozok[_kijelolt!]
        : null;
    return Padding(
      padding: const EdgeInsets.all(8),
      child: Wrap(spacing: 10, runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center, children: [
        Text("Húzással új doboz:", style: AppText.label.copyWith(fontSize: 12)),
        ChoiceChip(
          label: const Text("labda", style: TextStyle(fontSize: 11.5)),
          selected: _rajzOsztaly == 1,
          onSelected: (_) => setState(() => _rajzOsztaly = 1),
        ),
        ChoiceChip(
          label: const Text("játékos", style: TextStyle(fontSize: 11.5)),
          selected: _rajzOsztaly == 0,
          onSelected: (_) => setState(() => _rajzOsztaly = 0),
        ),
        const SizedBox(width: 8),
        if (kivalasztott != null) ...[
          cimke(kivalasztott[0] == 1 ? "kijelölve: labda" : "kijelölve: játékos",
              kivalasztott[0] == 1 ? AppColors.ball : AppColors.home),
          TextButton(
            onPressed: () => setState(() {
              _dobozok[_kijelolt!][0] =
                  _dobozok[_kijelolt!][0] == 1 ? 0 : 1;
              _modositott = true;
            }),
            child: const Text("Osztály-váltás"),
          ),
          TextButton(
            onPressed: () => setState(() {
              _dobozok.removeAt(_kijelolt!);
              _kijelolt = null;
              _modositott = true;
            }),
            child: const Text("Törlés"),
          ),
        ],
        const SizedBox(width: 8),
        IconButton(
            tooltip: "Előző kép",
            onPressed: _index > 0 ? () => _valaszt(_index - 1) : null,
            icon: const Icon(Icons.chevron_left)),
        Text("${_index + 1} / ${_kepek.length}",
            style: AppText.label.copyWith(fontSize: 12)),
        IconButton(
            tooltip: "Következő kép",
            onPressed: _index < _kepek.length - 1
                ? () => _valaszt(_index + 1)
                : null,
            icon: const Icon(Icons.chevron_right)),
      ]),
    );
  }

  Widget _vaszon() {
    final bytes = _kepBytes;
    if (bytes == null) {
      return const WaitingView("Kép betöltése…",
          hint: "a gyűjtött tanítókép és a címkéi jönnek");
    }
    return LayoutBuilder(builder: (ctx, korlat) {
      return FutureBuilder<Size>(
        future: _kepMeret(bytes),
        builder: (ctx, meret) {
          if (!meret.hasData) {
            return const WaitingView("Kép kirajzolása…");
          }
          final vaszon = Size(korlat.maxWidth, korlat.maxHeight);
          final r = _kepRect(vaszon, meret.data!);
          return GestureDetector(
            onTapUp: (d) {
              final n = _normalt(d.localPosition, r);
              if (n != null) _koppint(n);
            },
            onPanStart: (d) {
              _huzasKezdet = _normalt(d.localPosition, r);
              _huzasVege = _huzasKezdet;
            },
            onPanUpdate: (d) {
              final n = _normalt(d.localPosition, r);
              if (n != null) setState(() => _huzasVege = n);
            },
            onPanEnd: (_) {
              if (_huzasKezdet != null && _huzasVege != null) {
                _ujDoboz(_huzasKezdet!, _huzasVege!);
              }
              setState(() {
                _huzasKezdet = null;
                _huzasVege = null;
              });
            },
            child: Stack(children: [
              Positioned.fill(
                  child: Image.memory(bytes, fit: BoxFit.contain)),
              Positioned.fill(
                child: CustomPaint(
                  painter: _DobozPainter(
                      dobozok: _dobozok,
                      kijelolt: _kijelolt,
                      kepRect: r,
                      huzasA: _huzasKezdet,
                      huzasB: _huzasVege),
                ),
              ),
            ]),
          );
        },
      );
    });
  }

  static final Map<int, Size> _meretCache = {};
  Future<Size> _kepMeret(Uint8List bytes) async {
    final kulcs = bytes.length ^ bytes.hashCode;
    final volt = _meretCache[kulcs];
    if (volt != null) return volt;
    final img = await decodeImageFromList(bytes);
    final meret = Size(img.width.toDouble(), img.height.toDouble());
    _meretCache[kulcs] = meret;
    return meret;
  }
}

class _DobozPainter extends CustomPainter {
  final List<List<num>> dobozok;
  final int? kijelolt;
  final Rect kepRect;
  final Offset? huzasA, huzasB;
  _DobozPainter(
      {required this.dobozok,
      required this.kijelolt,
      required this.kepRect,
      this.huzasA,
      this.huzasB});

  @override
  void paint(Canvas canvas, Size size) {
    for (var i = 0; i < dobozok.length; i++) {
      final b = dobozok[i];
      final szin = b[0] == 1 ? AppColors.ball : AppColors.home;
      final p = Paint()
        ..color = szin
        ..style = PaintingStyle.stroke
        ..strokeWidth = i == kijelolt ? 3.0 : 1.5;
      canvas.drawRect(_rect(b), p);
    }
    if (huzasA != null && huzasB != null) {
      final p = Paint()
        ..color = AppColors.gold
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5;
      canvas.drawRect(
          Rect.fromPoints(_pont(huzasA!), _pont(huzasB!)), p);
    }
  }

  Offset _pont(Offset n) => Offset(kepRect.left + n.dx * kepRect.width,
      kepRect.top + n.dy * kepRect.height);

  Rect _rect(List<num> b) {
    final cx = b[1].toDouble(), cy = b[2].toDouble();
    final w = b[3].toDouble(), h = b[4].toDouble();
    return Rect.fromCenter(
        center: _pont(Offset(cx, cy)),
        width: w * kepRect.width,
        height: h * kepRect.height);
  }

  @override
  bool shouldRepaint(covariant _DobozPainter old) => true;
}
