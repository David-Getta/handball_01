/// Feltöltés — meccsvideó → Tracking, a feldolgozási pipeline állapotával.
///
/// A "Sport Machine" design feltöltő képernyője: a dropzone-ra kattintva natív
/// fájlválasztóval kiválasztott videót a backendre TÖLTI (POST /upload, streamelve),
/// majd a "Feldolgozás indítása" a valós pipeline-t indítja (POST /matches/process),
/// és a kör-progress + az [A]–[H] lépések a valódi job-állapotból (GET /jobs/{id})
/// frissülnek.
library;

import "dart:async";

import "package:file_picker/file_picker.dart";
import "package:flutter/foundation.dart" show kIsWeb;
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../services/backend_launcher.dart";
import "../theme/app_theme.dart";
import "calibration_screen.dart";
import "match_screen.dart";
import "shell/app_shell.dart";

/// A pipeline-lépések sorrendje (a backend ezeket a kódokat adja a job stage-ében).
const List<List<String>> _pipelineSteps = [
  ["A", "Kalibráció"],
  ["B", "Detektálás (YOLO)"],
  ["C", "Követés + ReID"],
  ["D", "Csapatszín / kapus / bíró"],
  ["E", "Pálya-koordináta"],
  ["F", "Képen kívüli becslés"],
  ["H", "Statisztika + hőtérkép"],
];

class UploadScreen extends StatefulWidget {
  const UploadScreen({super.key});

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  // A backend-oldali videó elérési útja (lokális mód). A kalibráló képernyő ebből
  // tölti be a valódi referencia-képkockát a /reference-frame végponton keresztül.
  final _pathCtrl = TextEditingController();
  // Csapatnevek — a feldolgozott meccs, a könyvtár és a felderítő jelentés is
  // ezeket használja (utólag is átírhatók a könyvtárban).
  final _homeCtrl = TextEditingController();
  final _awayCtrl = TextEditingController();
  final _api = ApiClient();

  // Aktuális feldolgozási munka állapota (a backendtől, GET /jobs/{id}).
  String? _jobId;
  String? _matchId; // a kész Tracking azonosítója (ezzel nyílik a meccs-nézet)
  bool _navigated = false; // egyszeri automatikus átugrás a done pillanatában
  String _status = "idle"; // idle | running | done | error
  String _stage = "A";
  double _progress = 0.0;
  String _message = "";
  String? _error;
  Timer? _poll;

  // Feltöltés állapota (a dropzone folyamatjelzőjéhez).
  bool _uploading = false;
  double _uploadProgress = 0.0;
  String? _uploadedName;

  // Egyszerre TÖBB felvétel is feltölthető (pl. 1. és 2. félidő): az első a
  // fő videó (ez kalibrálható itt), a többi backend-oldali útja itt gyűlik —
  // a "Feldolgozás indítása" MINDET sorba állítja a szerveren, mindegyiket a
  // saját elmentett kalibrációjával (ha van).
  final List<String> _batchPaths = [];

  // Feldolgozási beállítások: minőségi profil + rövid próba mód.
  // A profilok (stride, imgsz): gyors = ritkább mintavétel kisebb képen;
  // pontos = sűrűbb mintavétel nagy felbontáson (lassabb, de jobb labda-követés).
  String _quality = "balanced"; // fast | balanced | precise
  bool _jerseyOcr = false; // KÍSÉRLETI: mezszám-OCR a feldolgozás alatt
  // Feldolgozott hossz: "trial" (~2 perc, gyors ellenőrzés) | "half" (~35
  // perc — ha a videóban az egész meccs van, de csak egy félidő kell;
  // a kezdőpontot a kalibrált képkocka adja) | "full" (a teljes videó).
  String _length = "full";

  // A kalibráló képernyőről visszakapott eredmény: 1 kalibráció (teljes
  // pálya / egy térfél) VAGY 2 (külön bal és jobb térfél, akár külön
  // képkockán) — ezzel lesz PONTOS a pálya-koordináta és a szűrés.
  CalibrationSet? _calib;

  static const Map<String, (int, int, String)> _qualityPresets = {
    "fast": (5, 960, "Gyors"),
    "balanced": (3, 1280, "Kiegyensúlyozott"),
    "precise": (2, 1920, "Pontos"),
  };

  @override
  void dispose() {
    _poll?.cancel();
    _pathCtrl.dispose();
    _homeCtrl.dispose();
    _awayCtrl.dispose();
    super.dispose();
  }

  /// Natív fájlválasztó → videó feltöltése a backendre → a visszakapott
  /// backend-oldali utat beírja a mezőbe (ezt használja a kalibráció + feldolgozás).
  Future<void> _pickAndUpload() async {
    final res = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ["mp4", "mov", "avi", "mkv"],
      withData: kIsWeb, // weben bájtok kellenek; desktopon elég az elérési út
      allowMultiple: true, // több felvétel (pl. 1. és 2. félidő) egyszerre
    );
    if (res == null || res.files.isEmpty) return; // a felhasználó megszakította
    final files = res.files;

    // A feltöltés a helyi motorra megy — ha az nem fut, a nyers hálózati
    // hiba ("Connection refused") semmitmondó. Előbb ellenőrizzük, és ha
    // kell, megpróbáljuk ÚJRAINDÍTANI a motort (karantén-öngyógyítással).
    if (!await _api.isHealthy()) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text("A motor nem fut — újraindítás…")));
      final status = await (BackendLauncher.instance ?? BackendLauncher())
          .ensureRunning();
      if (!mounted) return;
      if (status.phase != BackendPhase.ready) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            duration: const Duration(seconds: 12),
            content: Text("A motor nem indult el: ${status.message}\n"
                "Próbáld újraindítani a programot; ha marad, a napló "
                "megmondja az okot (engine-app.log a SportMachine "
                "adatmappában).")));
        return;
      }
    }
    setState(() {
      _uploading = true;
      _uploadProgress = 0.0;
      _uploadedName = files.first.name;
    });
    var okCount = 0;
    try {
      // A fájlok EGYMÁS UTÁN töltődnek fel; az első lesz a fő videó (az
      // kalibrálható itt), a többi a köteg-listába kerül.
      for (var i = 0; i < files.length; i++) {
        final f = files[i];
        if (!mounted) return;
        setState(() {
          _uploadProgress = 0.0;
          _uploadedName =
              files.length > 1 ? "${f.name} (${i + 1}/${files.length})" : f.name;
        });
        Map<String, dynamic> saved;
        if (!kIsWeb && f.path != null) {
          saved = await _api.uploadVideoFromPath(f.path!, f.name,
              onProgress: (p) { if (mounted) setState(() => _uploadProgress = p); });
        } else if (f.bytes != null) {
          saved = await _api.uploadVideoBytes(f.bytes!, f.name);
        } else {
          throw Exception("a kiválasztott fájl nem olvasható");
        }
        okCount++;
        if (!mounted) return;
        final savedPath = saved["path"] as String;
        if (i == 0) {
          setState(() => _pathCtrl.text = savedPath); // a backend-oldali út
          _loadSavedCalibration(savedPath);
        } else {
          setState(() => _batchPaths.add(savedPath));
        }
      }
      if (!mounted) return;
      setState(() {
        _uploading = false;
        _uploadProgress = 1.0;
      });
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(okCount == 1
              ? "Feltöltve: ${files.first.name}"
              : "$okCount videó feltöltve — a feldolgozás mindet sorba állítja.")));
    } catch (e) {
      if (!mounted) return;
      setState(() => _uploading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Feltöltési hiba: $e")),
      );
    }
  }

  String _mb(Object? bytes) {
    final b = (bytes is num) ? bytes.toDouble() : 0.0;
    return "${(b / (1024 * 1024)).toStringAsFixed(1)} MB";
  }

  /// A kalibrációk hálózati (JSON) alakja — mentéshez és feldolgozáshoz.
  List<Map<String, dynamic>> _calibMaps(CalibrationSet set) => [
        for (final c in set.items)
          {
            "corners": c.corners,
            "region": c.region,
            "rotate": c.rotate,
            "frame": c.startFrame,
          },
      ];

  /// A videóhoz korábban ELMENTETT kalibráció betöltése (ha van) — a gomb
  /// azonnal "kész" állapotot mutat, és a feldolgozás használja.
  Future<void> _loadSavedCalibration(String path) async {
    try {
      final maps = await _api.fetchCalibration(path);
      final items = <CalibrationResult>[];
      for (final m in maps) {
        final raw = (m["corners"] as List?) ?? const [];
        final corners = [
          for (final p in raw)
            if (p is List && p.length >= 2)
              [(p[0] as num).toInt(), (p[1] as num).toInt()],
        ];
        if (corners.length != 4) continue;
        items.add(CalibrationResult(
          corners: corners,
          region: (m["region"] as String?) ?? "full",
          rotate: (m["rotate"] as bool?) ?? false,
          startFrame: (m["frame"] as num?)?.toInt() ?? 0,
        ));
      }
      if (items.isEmpty || !mounted) return;
      setState(() => _calib = CalibrationSet(items));
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(
              "Elmentett kalibráció betöltve (${_calib!.label}) — nem kell újra bejelölni.")));
    } catch (_) {
      // nincs mentett kalibráció / nem elérhető — csendben megyünk tovább
    }
  }

  /// Elindítja a feldolgozást a megadott videó-úton, majd időzítővel lekérdezi
  /// a haladást (GET /jobs/{id}) és frissíti a kártyát.
  Future<void> _startProcessing() async {
    final path = _pathCtrl.text.trim();
    if (path.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Adj meg egy backend-oldali videó-utat.")),
      );
      return;
    }
    setState(() {
      _status = "running";
      _stage = "A";
      _progress = 0.0;
      _message = "indítás";
      _error = null;
      _navigated = false;
    });
    // A kiválasztott profil paraméterei; próba módban csak a videó eleje
    // (~2 percnyi feldolgozott kocka) készül el — gyors ellenőrzéshez.
    final (stride, imgsz, _) = _qualityPresets[_quality]!;
    // A hossz-korlát FELDOLGOZOTT kockában értendő (25 fps-sel számolva):
    // próba ~2 perc, félidő ~35 perc, 0 = a videó vége.
    final max = switch (_length) {
      "trial" => (3000 / stride).round(),
      "half" => (52500 / stride).round(),
      _ => 0,
    };
    try {
      final r = await _api.startProcessing(
        path,
        weights: "yolov8n.pt",
        stride: stride,
        imgsz: imgsz,
        max: max,
        homeTeam: _homeCtrl.text.trim(),
        awayTeam: _awayCtrl.text.trim(),
        // A kalibrációk (ha elkészültek): pontos pálya-koordináta + szűrés.
        // A feldolgozás a legkorábbi kalibrált képkockától indul (a
        // pásztázás-követés ehhez igazít; a második térfél-kalibrációt a
        // szerver a pásztázás-mátrixszal vezeti vissza az alap-kockára).
        calibs: _calib == null ? null : _calibMaps(_calib!),
        start: _calib?.startFrame ?? 0,
        jerseyOcr: _jerseyOcr,
      );
      _jobId = r["job_id"] as String;
      _matchId = r["match_id"] as String?;
      _poll?.cancel();
      _poll = Timer.periodic(const Duration(milliseconds: 800), (_) => _pollJob());
      // A köteg többi videója is sorba kerül — mindegyik a SAJÁT elmentett
      // kalibrációjával (ha van), ugyanazzal a minőség/hossz beállítással.
      if (_batchPaths.isNotEmpty) {
        final batch = List<String>.from(_batchPaths);
        setState(() => _batchPaths.clear());
        var queued = 0;
        for (final p in batch) {
          try {
            List<Map<String, dynamic>>? calibs;
            var startFrame = 0;
            try {
              final saved = await _api.fetchCalibration(p);
              if (saved.isNotEmpty) {
                calibs = saved;
                startFrame = saved
                    .map((c) => (c["frame"] as num?)?.toInt() ?? 0)
                    .reduce((a, b) => a < b ? a : b);
              }
            } catch (_) {} // nincs mentett kalibráció — enélkül megy
            await _api.startProcessing(
              p,
              weights: "yolov8n.pt",
              stride: stride,
              imgsz: imgsz,
              max: max,
              homeTeam: _homeCtrl.text.trim(),
              awayTeam: _awayCtrl.text.trim(),
              calibs: calibs,
              start: startFrame,
              jerseyOcr: _jerseyOcr,
            );
            queued++;
          } catch (e) {
            if (!mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                content: Text("Nem sikerült sorba állítani: ${p.split("/").last} — $e")));
          }
        }
        if (queued > 0 && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text("További $queued videó sorba állítva — egymás után "
                  "dolgozza fel őket a motor (állapot: Kezdőlap).")));
        }
      }
    } catch (e) {
      setState(() {
        _status = "error";
        _error = "$e";
        _message = "nem sikerült elindítani";
      });
    }
  }

  /// Egy lekérdezés a job állapotára; leállítja az időzítőt, ha vége.
  Future<void> _pollJob() async {
    final id = _jobId;
    if (id == null) return;
    try {
      final j = await _api.fetchJob(id);
      if (!mounted) return;
      setState(() {
        _status = (j["status"] as String?) ?? "running";
        _stage = (j["stage"] as String?) ?? _stage;
        _progress = (j["progress"] as num?)?.toDouble() ?? _progress;
        _message = (j["message"] as String?) ?? "";
        _error = j["error"] as String?;
      });
      if (_status == "done" || _status == "error" || _status == "cancelled") {
        _poll?.cancel();
      }
      // A done pillanatában EGYSZER automatikusan megnyitjuk az eredményt.
      if (_status == "done" && !_navigated) {
        _navigated = true;
        _openResult();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _status = "error";
        _error = "$e";
      });
      _poll?.cancel();
    }
  }

  /// Futó feldolgozás megszakítása — a szerver a következő képkockánál áll le.
  Future<void> _cancelProcessing() async {
    final id = _jobId;
    if (id == null) return;
    try {
      await _api.cancelJob(id);
      if (!mounted) return;
      setState(() => _message = "megszakítás folyamatban…");
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text("Megszakítási hiba: $e")));
    }
  }

  /// Megnyitja a kész meccs felülnézeti elemző nézetét a friss match_id-vel.
  void _openResult() {
    final id = _matchId;
    if (id == null || !mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => MatchScreen(matchId: id)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.upload,
      crumbTag: "1f",
      crumbPath: "FELTÖLTÉS · FELDOLGOZÁSI PIPELINE",
      collapsed: true,
      child: ListView(
        children: [
          Text("Videó feltöltése", style: AppText.title),
          const SizedBox(height: 4),
          Text("Pásztázó-kamerás meccsvideó → Tracking adatmodell", style: AppText.subtitle),
          const SizedBox(height: AppSpacing.xl),
          _dropzone(),
          const SizedBox(height: AppSpacing.md),
          // Lokális mód: a backend-oldali videó útja, hogy a kalibráció a valódi
          // képkockát töltse be (fájlválasztó nélkül is működjön a desktop-teszt).
          TextField(
            controller: _pathCtrl,
            style: AppText.value.copyWith(fontSize: 13),
            decoration: InputDecoration(
              isDense: true,
              hintText: "Backend-oldali videó útja (pl. /home/.../match.mp4)",
              hintStyle: AppText.label.copyWith(fontSize: 12),
              prefixIcon: const Icon(Icons.folder_open, size: 18, color: AppColors.textSecondary),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: AppColors.borderStrong),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: AppColors.accent),
              ),
            ),
          ),
          // A kötegben várakozó további felvételek (a fő videón felül) —
          // a feldolgozás indításakor mind sorba kerül; az X-szel kivehető.
          if (_batchPaths.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.xs,
              children: [
                for (final p in _batchPaths)
                  Chip(
                    label: Text(p.split("/").last,
                        style: AppText.label.copyWith(fontSize: 12)),
                    avatar: const Icon(Icons.movie_outlined,
                        size: 16, color: AppColors.textSecondary),
                    backgroundColor: AppColors.surfaceAlt,
                    side: const BorderSide(color: AppColors.border),
                    deleteIcon: const Icon(Icons.close, size: 16),
                    onDeleted: () => setState(() => _batchPaths.remove(p)),
                  ),
              ],
            ),
          ],
          const SizedBox(height: AppSpacing.md),
          // Csapatnevek: a könyvtár és a felderítő jelentés ezeket mutatja.
          Row(children: [
            Expanded(child: _teamField(_homeCtrl, "Hazai csapat (pl. Veszprém)", AppColors.home)),
            const SizedBox(width: AppSpacing.md),
            Expanded(child: _teamField(_awayCtrl, "Vendég csapat (pl. Szeged)", AppColors.away)),
          ]),
          const SizedBox(height: AppSpacing.md),
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton.icon(
              onPressed: () async {
                final path = _pathCtrl.text.trim();
                final res = await Navigator.of(context).push<CalibrationSet>(
                  MaterialPageRoute(
                    builder: (_) => CalibrationScreen(
                      videoPath: path.isEmpty ? null : path,
                    ),
                  ),
                );
                if (res != null && mounted) {
                  setState(() => _calib = res);
                  // A kalibrációt a videóhoz is elmentjük — újrafeldolgozásnál
                  // (vagy az app újraindítása után) nem kell újra bejelölni.
                  try {
                    await _api.saveCalibration(path, _calibMaps(res));
                  } catch (_) {}
                }
              },
              style: OutlinedButton.styleFrom(
                foregroundColor: _calib != null ? AppColors.gold : AppColors.accent,
                side: BorderSide(
                    color: _calib != null ? AppColors.gold : AppColors.accent),
              ),
              icon: Icon(_calib != null ? Icons.check_circle : Icons.grid_on, size: 18),
              label: Text(_calib != null
                  ? "Kalibráció kész (${_calib!.label})"
                  : "Pálya-kalibráció (4 sarok)"),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          // Feldolgozási beállítások: minőség + próba mód. Alapból a TELJES
          // videó készül el a kiegyensúlyozott profillal.
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SegmentedButton<String>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: [
                  for (final e in _qualityPresets.entries)
                    ButtonSegment(value: e.key, label: Text(e.value.$3)),
                ],
                selected: {_quality},
                onSelectionChanged: _status == "running"
                    ? null
                    : (s) => setState(() => _quality = s.first),
              ),
              SegmentedButton<String>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: const [
                  ButtonSegment(value: "trial", label: Text("Próba (~2 p)")),
                  ButtonSegment(value: "half", label: Text("Félidő (~35 p)")),
                  ButtonSegment(value: "full", label: Text("Teljes videó")),
                ],
                selected: {_length},
                onSelectionChanged: (s) => setState(() => _length = s.first),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            switch (_length) {
              "trial" =>
                "Csak a videó eleje készül el — gyors ellenőrzéshez (kalibráció, színek).",
              "half" =>
                "~35 percnyi játék készül el a kalibrált képkockától — ha a videóban "
                    "az egész meccs van, de csak ez a félidő kell.",
              _ =>
                "A teljes videó feldolgozása — egy félidő a gép erejétől függően "
                    "10–60 perc is lehet, a haladás és a hátralévő idő végig látszik.",
            },
            style: AppText.label.copyWith(fontSize: 11),
          ),
          const SizedBox(height: 6),
          // KÍSÉRLETI: mezszám-OCR a feldolgozás alatt — a felismert
          // számokat a szavazó csak elég bizonyíték esetén hirdeti ki,
          // és a kézi hozzárendelés mindig felülírhatja.
          Row(mainAxisSize: MainAxisSize.min, children: [
            SizedBox(
              height: 28,
              child: Switch(
                value: _jerseyOcr,
                onChanged: (v) => setState(() => _jerseyOcr = v),
              ),
            ),
            const SizedBox(width: 6),
            Text("Mezszám-felismerés (kísérleti) — a leolvasott számok "
                "kézzel javíthatók a meccs-nézetben",
                style: AppText.label.copyWith(fontSize: 11)),
          ]),
          const SizedBox(height: AppSpacing.md),
          Row(children: [
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
              onPressed: _uploading ? null : _startProcessing,
              icon: const Icon(Icons.play_arrow, size: 18),
              // Futó feldolgozás mellett is indítható újabb: a szerver
              // SORBA teszi, és egymás után dolgozza fel őket.
              label: Text(_batchPaths.isNotEmpty
                  ? "Feldolgozás indítása (${_batchPaths.length + 1} videó)"
                  : _status == "running" || _status == "queued"
                      ? "Új videó sorba állítása"
                      : "Feldolgozás indítása"),
            ),
            if (_status == "running") ...[
              const SizedBox(width: AppSpacing.md),
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.away,
                  side: const BorderSide(color: AppColors.away),
                ),
                onPressed: _cancelProcessing,
                icon: const Icon(Icons.stop_circle_outlined, size: 18),
                label: const Text("Megszakítás"),
              ),
            ],
          ]),
          const SizedBox(height: AppSpacing.xl),
          Text("Feldolgozás állapota", style: AppText.value.copyWith(fontSize: 17)),
          const SizedBox(height: AppSpacing.md),
          _processingCard(),
          // Kész eredmény: kézi megnyitás (az automatikus átugrás mellett — ha
          // visszaléptél a meccs-nézetről, innen újra megnyithatod).
          if (_status == "done" && _matchId != null) ...[
            const SizedBox(height: AppSpacing.md),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
                onPressed: _openResult,
                icon: const Icon(Icons.open_in_new, size: 18),
                label: const Text("Eredmény megnyitása"),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Csapatnév-mező (a csapat megjelenítési színével jelölve).
  Widget _teamField(TextEditingController ctrl, String hint, Color color) {
    return TextField(
      controller: ctrl,
      style: AppText.value.copyWith(fontSize: 13),
      decoration: InputDecoration(
        isDense: true,
        hintText: hint,
        hintStyle: AppText.label.copyWith(fontSize: 12),
        prefixIcon: Icon(Icons.groups, size: 18, color: color),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AppColors.borderStrong),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: color),
        ),
      ),
    );
  }

  Widget _dropzone() {
    return InkWell(
      onTap: _uploading ? null : _pickAndUpload,
      borderRadius: BorderRadius.circular(14),
      child: DottedBorderBox(
        child: Row(
          children: [
            Container(
              width: 56, height: 56,
              decoration: BoxDecoration(color: AppColors.surfaceAlt, borderRadius: BorderRadius.circular(14)),
              child: _uploading
                  ? const Padding(
                      padding: EdgeInsets.all(15),
                      child: CircularProgressIndicator(strokeWidth: 3, color: AppColors.accent))
                  : const Icon(Icons.file_upload_outlined, color: AppColors.accent, size: 26),
            ),
            const SizedBox(width: AppSpacing.lg),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _uploading
                        ? "Feltöltés… ${(_uploadProgress * 100).round()}%  ${_uploadedName ?? ""}"
                        : "Kattints a meccsvideó(k) kiválasztásához",
                    style: AppText.value.copyWith(fontSize: 16),
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Text("MP4 / MOV / MKV · egyszerre több felvétel is választható "
                      "(pl. 1. és 2. félidő) · 720p–4K",
                      style: AppText.label.copyWith(fontSize: 12)),
                  if (_uploading) ...[
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: _uploadProgress == 0 ? null : _uploadProgress,
                        minHeight: 4,
                        backgroundColor: AppColors.surfaceAlt,
                        valueColor: const AlwaysStoppedAnimation(AppColors.accent),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _processingCard() {
    // A jelenlegi stage indexe a lépéslistában (a done/active/pending eldöntéséhez).
    final curIdx = _pipelineSteps.indexWhere((s) => s[0] == _stage);
    final path = _pathCtrl.text.trim();
    final fileName = path.isEmpty ? "nincs kiválasztott videó" : path.split("/").last;

    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _RingProgress(value: _progress),
              const SizedBox(width: AppSpacing.xl),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      const Icon(Icons.movie_outlined, size: 18, color: AppColors.textSecondary),
                      const SizedBox(width: 8),
                      Expanded(child: Text(fileName, style: AppText.value.copyWith(fontSize: 15), overflow: TextOverflow.ellipsis)),
                    ]),
                    const SizedBox(height: 6),
                    Text(_statusLine(), style: AppText.label.copyWith(
                        fontSize: 12,
                        color: _status == "error" ? AppColors.away : AppColors.textSecondary)),
                    // A motor az apppal együtt áll le — hosszú feldolgozásnál
                    // ez sok elveszett munka lenne, ezért kiírjuk.
                    if (_status == "running") ...[
                      const SizedBox(height: 4),
                      Text(
                        "Ne zárd be az appot feldolgozás közben — a motor vele "
                        "együtt leáll, és a munka elveszik.",
                        style: AppText.label.copyWith(fontSize: 11, color: AppColors.gold),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xl),
          for (int i = 0; i < _pipelineSteps.length; i++)
            _step(
              _pipelineSteps[i][1], _pipelineSteps[i][0],
              // "done" ha korábbi lépés, vagy a job kész; "active" ha az aktuális
              // és fut; hibánál az aktuális lépés hibás.
              done: _status == "done" || (curIdx >= 0 && i < curIdx),
              active: _status == "running" && i == curIdx,
              error: _status == "error" && i == curIdx,
            ),
        ],
      ),
    );
  }

  /// A kártya alcíme: állapottól függő, olvasható szöveg.
  String _statusLine() {
    switch (_status) {
      case "idle":
        return "Nincs feldolgozás — add meg a videó-utat és indítsd el.";
      case "queued":
        return "Sorban áll — előtte másik feldolgozás fut.";
      case "running":
        return "Feldolgozás… ${(_progress * 100).round()}% · $_message";
      case "done":
        return "Kész · $_message";
      case "cancelled":
        return "Megszakítva — indíthatsz új feldolgozást.";
      case "error":
        return "Hiba · ${_error ?? _message}";
      default:
        return _message;
    }
  }

  Widget _step(String name, String tag, {bool done = false, bool active = false, bool error = false}) {
    final Color c = error
        ? AppColors.away
        : done
            ? AppColors.accent
            : active
                ? AppColors.gold
                : AppColors.textFaint;
    final IconData icon = error
        ? Icons.error_outline
        : done
            ? Icons.check_circle
            : active
                ? Icons.autorenew
                : Icons.circle_outlined;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 18, color: c),
          const SizedBox(width: AppSpacing.md),
          Text(name, style: AppText.value.copyWith(
              color: (done || active || error) ? AppColors.textPrimary : AppColors.textFaint,
              fontWeight: FontWeight.w500)),
          const SizedBox(width: 6),
          Text("[$tag]", style: AppText.label.copyWith(fontSize: 11, color: AppColors.textFaint)),
          const Spacer(),
          if (active) Text("folyamatban…", style: AppText.label.copyWith(fontSize: 11, color: AppColors.gold)),
          if (error) Text("hiba", style: AppText.label.copyWith(fontSize: 11, color: AppColors.away)),
        ],
      ),
    );
  }
}

/// Szaggatott keretű doboz (a dropzone-hoz).
class DottedBorderBox extends StatelessWidget {
  final Widget child;
  const DottedBorderBox({super.key, required this.child});
  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _DashedRectPainter(),
      child: Padding(padding: const EdgeInsets.all(AppSpacing.xl), child: child),
    );
  }
}

class _DashedRectPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.borderStrong
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    final rrect = RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(14));
    final path = Path()..addRRect(rrect);
    // Szaggatás: a path mentén rövid szakaszokat rajzolunk.
    for (final metric in path.computeMetrics()) {
      double dist = 0;
      while (dist < metric.length) {
        final seg = metric.extractPath(dist, dist + 7);
        canvas.drawPath(seg, paint);
        dist += 13;
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// Kör alakú folyamatjelző százalékkal.
class _RingProgress extends StatelessWidget {
  final double value;
  const _RingProgress({required this.value});
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 78, height: 78,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: 78, height: 78,
            child: CircularProgressIndicator(
              value: value,
              strokeWidth: 6,
              backgroundColor: AppColors.surfaceAlt,
              valueColor: const AlwaysStoppedAnimation(AppColors.accent),
            ),
          ),
          Text("${(value * 100).round()}%", style: AppText.value.copyWith(fontSize: 16)),
        ],
      ),
    );
  }
}
