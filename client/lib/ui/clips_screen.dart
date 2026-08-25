/// Klipek — videó-dosszié az edzésre, saját menüponttal.
///
/// A klipvágás eddig csak a meccs-elemző eszköztárában élt, és ott is
/// EGY csomag egyszerre: aki a gólokat és a kihagyott ziccereket is
/// akarta, kétszer vágatott, két zip-be. Az edzés előtt viszont pont
/// az a kérdés, hogy "mit viszek le a pályára" — ehhez a csomagokat
/// SZABADON kell tudni kombinálni, és nem kell hozzá megnyitni a
/// meccset.
///
/// Ez a képernyő: meccs-választó + a klip-típusok csoportosított
/// listája (támadás · védekezés · kapus és helyzetek · a meccs
/// gerince · egyéb), tetszőleges kijelöléssel, EGY zip-be. Négy
/// gyors-összeállítás (dosszié, támadás, védekezés, csak gólok) a
/// leggyakoribb eseteket egy kattintásra adja.
///
/// A haladás LÁTSZIK: a vágás percekig tarthat, és a néma várakozás
/// olyan, mintha megakadt volna.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "shell/app_shell.dart";
import "waiting.dart";

/// Egy klip-típus: a backend kulcsa, a magyar neve és egy mondat arról,
/// MIRE jó edzésen. (A backend `types` listája ezeket a kulcsokat várja.)
typedef ClipKind = (String, String, String);

/// A klip-típusok csoportosítva — a csoport neve az edzői téma.
const List<(String, List<ClipKind>)> kClipGroups = [
  ("TÁMADÁS", [
    ("goal", "Gólok", "a befejezés — a legrövidebb visszanézés"),
    ("shot", "Minden lövés", "a lövésválasztás egészben"),
    ("missed_chance", "Kihagyott ziccerek",
        "nagy értékű helyzet, ami nem ment be — a legfájóbb anyag"),
    ("top_shooter", "A fő lövő lövései", "egy ember teljes lövés-képe"),
    ("best_figure", "A legjobb figura", "amit érdemes ismételni"),
    ("pivot_goal", "Beállós gólok", "a beadás-játék videón"),
    ("turnover", "Labdaeladások", "hol veszik el a labda"),
  ]),
  ("VÉDEKEZÉS", [
    ("block", "Blokkok", "a fal munkája"),
    ("steal", "Labdaszerzések", "a védekezés motorja"),
    ("free_shot", "Szabad lövők",
        "fedezés-hibák — kit hagytunk üresen"),
    ("breakthrough", "Betörések", "a sáv a fájlnévben van"),
  ]),
  ("KAPUS ÉS HELYZETEK", [
    ("big_save", "Nagy védések", "a kapus bravúrjai"),
    ("seven_meter", "Hétméteresek", "a büntetők egyben"),
    ("empty_net", "7 a 6 szakaszok", "a lehozott kapus jelenetei"),
  ]),
  ("A MECCS GERINCE", [
    ("key_moment", "Kulcs-pillanatok", "a meccs története képben"),
    ("turning_point", "Fordulópont", "ahol elbillent a meccs"),
    ("timeout", "Időkérések", "ami a leállás ELŐTT történt"),
    ("substitution", "Cserehullámok", "ki jött, ki ment"),
  ]),
  ("EGYÉB", [
    ("note", "Jegyzetelt pillanatok",
        "amit a meccs közben magad jelöltél meg"),
  ]),
];

/// Gyors-összeállítások: a leggyakoribb esetek egy kattintásra.
const List<(String, List<String>)> kClipPresets = [
  ("Teljes videó-dosszié", [
    "goal", "key_moment", "turning_point", "missed_chance", "big_save",
    "top_shooter", "free_shot", "best_figure", "pivot_goal",
    "breakthrough", "steal", "block", "empty_net",
  ]),
  ("Támadás-csomag", [
    "goal", "missed_chance", "best_figure", "pivot_goal", "turnover",
  ]),
  ("Védekezés-csomag", [
    "block", "steal", "free_shot", "breakthrough", "big_save",
  ]),
  ("Csak gólok", ["goal"]),
];

class ClipsScreen extends StatefulWidget {
  const ClipsScreen({super.key});

  @override
  State<ClipsScreen> createState() => _ClipsScreenState();
}

class _ClipsScreenState extends State<ClipsScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _matches = [];
  String? _matchId;

  final Set<String> _selected = {"goal"};

  // Vágás közben: a job üzenete és haladása — a néma várakozás
  // megakadásnak látszik.
  bool _working = false;
  double _progress = 0;
  String _stageMsg = "";

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final ms = await _api.listMatches();
      if (!mounted) return;
      setState(() {
        _matches = ms;
        _matchId = ms.isNotEmpty ? ms.first["match_id"] as String : null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "A meccs-könyvtár nem érhető el: ${humanError(e)}";
        _loading = false;
      });
    }
  }

  String _matchName() {
    final m = _matches.firstWhere((e) => e["match_id"] == _matchId,
        orElse: () => const <String, dynamic>{});
    final home = (m["home_team"] as String?) ?? "Hazai";
    final away = (m["away_team"] as String?) ?? "Vendég";
    return "${home}_$away".replaceAll(
        RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
  }

  Future<void> _export() async {
    final id = _matchId;
    if (id == null || _selected.isEmpty || _working) return;
    setState(() {
      _working = true;
      _progress = 0;
      _stageMsg = "klipvágás indítása";
      _error = null;
    });
    try {
      final jobId = await _api.startClipExport(id, _selected.toList());
      String doneMsg = "";
      while (true) {
        await Future.delayed(const Duration(seconds: 1));
        if (!mounted) return; // elnavigáltak — a job magától befejeződik
        final job = await _api.fetchJob(jobId);
        final status = job["status"] as String?;
        setState(() {
          _progress = ((job["progress"] as num?) ?? 0).toDouble();
          _stageMsg = (job["message"] as String?) ?? _stageMsg;
        });
        if (status == "done") {
          doneMsg = (job["message"] as String?) ?? "";
          break;
        }
        if (status == "error") {
          throw Exception(job["error"] ?? "ismeretlen hiba");
        }
      }
      final bytes = await _api.fetchClipsZip(id);
      if (!mounted) return;
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Videóklipek mentése (zip)",
        fileName: "klipek_${_matchName()}.zip",
        type: FileType.custom,
        allowedExtensions: const ["zip"],
      );
      if (path != null) {
        await File(path).writeAsBytes(bytes);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text("Klipek mentve: $path — kicsomagolás után "
                "lejátszhatók"
                "${doneMsg.contains("kimaradt") ? " · $doneMsg" : ""}")));
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = "Klip-export hiba: ${humanError(e)}");
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.clips,
      crumbPath: "ELEMZÉS · KLIPEK",
      child: _loading
          ? const WaitingView("Meccs-könyvtár olvasása…",
              icon: Icons.video_library_outlined)
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Klipek", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "amit levinnél a pályára: jelöld ki, mely jelenetekből "
                  "kérsz vágást — mind EGY zip-be kerül",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              if (_matches.isEmpty)
                Text(
                    "Még nincs elemzett meccs — előbb dolgozz fel egy "
                    "videót az Új elemzés menüben.",
                    style: AppText.label)
              else ...[
                _head(),
                const SizedBox(height: AppSpacing.md),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: Text(_error!,
                        style:
                            AppText.label.copyWith(color: AppColors.away)),
                  ),
                if (_working) _progressCard(),
                Expanded(child: _groups()),
                const SizedBox(height: AppSpacing.sm),
                _footer(),
              ],
            ]),
    );
  }

  Widget _head() {
    return Wrap(
      spacing: AppSpacing.lg,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Row(mainAxisSize: MainAxisSize.min, children: [
          Text("MECCS", style: AppText.sectionLabel),
          const SizedBox(width: AppSpacing.sm),
          DropdownButton<String>(
            value: _matchId,
            dropdownColor: AppColors.surface,
            style: AppText.value.copyWith(fontSize: 13),
            items: [
              for (final m in _matches)
                DropdownMenuItem(
                  value: m["match_id"] as String,
                  child: Text(
                      "${m["home_team"] ?? "Hazai"} – "
                      "${m["away_team"] ?? "Vendég"}",
                      overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: _working ? null : (v) => setState(() => _matchId = v),
          ),
        ]),
        for (final (name, types) in kClipPresets)
          OutlinedButton(
            onPressed: _working
                ? null
                : () => setState(() {
                      _selected
                        ..clear()
                        ..addAll(types);
                    }),
            child: Text(name),
          ),
      ],
    );
  }

  Widget _progressCard() {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: AppTheme.card(),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("Klipvágás folyamatban — $_stageMsg",
                  style: AppText.value.copyWith(fontSize: 13)),
              const SizedBox(height: AppSpacing.sm),
              LinearProgressIndicator(
                value: _progress > 0 ? _progress.clamp(0, 1) : null,
                backgroundColor: AppColors.surfaceAlt,
                color: AppColors.accent,
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                  "A vágás a videó hosszától és a kijelölt csomagoktól "
                  "függően percekbe telhet — közben nyugodtan átmehetsz "
                  "másik képernyőre, a munka nem áll le.",
                  style: AppText.label.copyWith(fontSize: 11.5)),
            ]),
      ),
    );
  }

  Widget _groups() {
    return ListView(children: [
      for (final (group, kinds) in kClipGroups) ...[
        Padding(
          padding: const EdgeInsets.only(
              top: AppSpacing.sm, bottom: AppSpacing.xs),
          child: Text(group, style: AppText.sectionLabel),
        ),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [for (final k in kinds) _kindTile(k)],
        ),
      ],
    ]);
  }

  Widget _kindTile(ClipKind kind) {
    final (key, name, why) = kind;
    final on = _selected.contains(key);
    return SizedBox(
      width: 280,
      child: InkWell(
        onTap: _working
            ? null
            : () => setState(() {
                  if (on) {
                    _selected.remove(key);
                  } else {
                    _selected.add(key);
                  }
                }),
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: AppTheme.card(
              borderColor: on ? AppColors.accent : null),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(on ? Icons.check_box : Icons.check_box_outline_blank,
                size: 18,
                color: on ? AppColors.accent : AppColors.textFaint),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name, style: AppText.value.copyWith(fontSize: 13)),
                    const SizedBox(height: 2),
                    Text(why,
                        style: AppText.label.copyWith(fontSize: 11.5)),
                  ]),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _footer() {
    final n = _selected.length;
    return Row(children: [
      Expanded(
        child: Text(
            n == 0
                ? "Jelölj ki legalább egy csomagot."
                : n == 1
                    ? "1 csomag kijelölve."
                    : "$n csomag kijelölve — egy zip-be kerülnek, "
                        "csomagonként külön mappába.",
            style: AppText.label.copyWith(fontSize: 12)),
      ),
      TextButton(
        onPressed: _working || n == 0
            ? null
            : () => setState(() => _selected.clear()),
        child: const Text("Kijelölés törlése"),
      ),
      const SizedBox(width: AppSpacing.sm),
      FilledButton.icon(
        onPressed: (_working || n == 0 || _matchId == null) ? null : _export,
        style: FilledButton.styleFrom(
            backgroundColor: AppColors.accent,
            foregroundColor: AppColors.onAccent),
        icon: const Icon(Icons.movie_creation_outlined, size: 18),
        label: const Text("Klipek vágása"),
      ),
    ]);
  }
}
