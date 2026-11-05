/// Szezon — a KÖNYVTÁR egésze egy lapon, saját menüponttal.
///
/// Eddig a szezon-összkép, a toplisták és a nyomtatható szezon-/egymás
/// elleni riportok mind a kezdőlap mélyén laktak: aki nem görgetett
/// odáig, nem is tudott róluk. Két külön nézőpont kéri ugyanezt az
/// adatot, ezért kap saját helyet a menüben:
///
///   EDZŐI szemmel: hány meccs van a könyvtárban, mennyi a mért
///   játékidő, és melyik csapatról készíthető szezon- vagy egymás
///   elleni riport (nyomtatható HTML).
///
///   JÁTÉKOS szemmel: a toplisták — gól, gólpassz, blokk, labdaszerzés,
///   védés — MEZSZÁM szerint összesítve az egész szezonra. Ez az a lap,
///   amin a játékos megkeresi magát; a mezszám nélküli trackek
///   kimaradnak (meccsek közt nincs stabil azonosítójuk), ezt ki is
///   mondjuk, hogy senki ne hiányzó teljesítménynek olvassa.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "figure_shape_painter.dart";
import "player_trend_screen.dart";
import "shell/app_shell.dart";
import "waiting.dart";

class SeasonScreen extends StatefulWidget {
  const SeasonScreen({super.key});

  @override
  State<SeasonScreen> createState() => _SeasonScreenState();
}

class _SeasonScreenState extends State<SeasonScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  String? _error;
  Map<String, dynamic> _summary = {};
  Map<String, dynamic> _leaders = {};
  // A lövő-modell próbája (a könyvtáron): üres, ha nem becsülhető.
  Map<String, dynamic> _modelCheck = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final s = await _api.fetchLibrarySummary();
      _loadFigureLibraries(s);
      final l = await _api.fetchLibraryLeaders();
      if (!mounted) return;
      setState(() {
        _summary = s;
        _leaders = l;
        _loading = false;
      });
      _loadModelCheck();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "A szezon-összkép nem érhető el: ${humanError(e)}";
        _loading = false;
      });
    }
  }

  // Csapatonként a meccsről meccsre visszatérő figurák (a könyvtárból) —
  // csak azok a csapatok, amelyeknél van ilyen (több meccs kell hozzá).
  final Map<String, List<Map<String, dynamic>>> _figures = {};

  List<String> get _teams =>
      [for (final t in (_summary["teams"] as List? ?? [])) t as String];

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.season,
      crumbPath: "CSAPAT · SZEZON",
      child: _loading
          ? const WaitingView("Szezon-összkép számítása…",
              hint: "A teljes meccs-könyvtárat összesítjük.",
              icon: Icons.calendar_month_outlined)
          : ListView(children: [
              Text("Szezon", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "a teljes könyvtár egy lapon: összkép, toplisták és "
                  "nyomtatható riportok",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text(_error!,
                      style: AppText.label.copyWith(color: AppColors.away)),
                ),
              _totals(),
              const SizedBox(height: AppSpacing.lg),
              Text("TOPLISTÁK", style: AppText.sectionLabel),
              const SizedBox(height: AppSpacing.sm),
              _leaderBoards(),
              ..._figureLibraries(),
              ..._repertoireChanges(),
              ..._modelCheckSection(),
              const SizedBox(height: AppSpacing.lg),
              Text("RIPORTOK", style: AppText.sectionLabel),
              const SizedBox(height: AppSpacing.sm),
              _reports(),
            ]),
    );
  }

  /// A csapatok figura-könyvtárai — csapatonként külön kérés, hibánál
  /// csendben kimarad (a szezon-kép nélküle is teljes).
  Future<void> _loadFigureLibraries(Map<String, dynamic> summary) async {
    final nevek = <String>{};
    for (final m in (summary["per_match"] as List? ?? const [])) {
      if (m is! Map) continue;
      for (final k in const ["home_team", "away_team"]) {
        final n = m[k];
        if (n is String && n.isNotEmpty) nevek.add(n);
      }
    }
    for (final t in nevek) {
      try {
        final lib = await _api.fetchTeamFigureLibrary(t);
        final rec = ((lib["recurring"] as List?) ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
        if (!mounted) return;
        if (rec.isNotEmpty) setState(() => _figures[t] = rec);
      } catch (_) {}
      try {
        final rep = await _api.fetchTeamFigureRepertoire(t);
        if (!mounted) return;
        // Csak a VÁLTOZÁST mutatjuk: új vagy eltűnt figura kell hozzá
        // (a "maradt" sorok a változás mellé kerülnek, hozammal).
        final vanValtozas = ((rep["new"] as List?) ?? const []).isNotEmpty ||
            ((rep["dropped"] as List?) ?? const []).isNotEmpty;
        if (vanValtozas) setState(() => _repertoire[t] = rep);
      } catch (_) {}
    }
  }

  /// A lövő-modell próbája — külön kérés, hibánál csendben kimarad.
  Future<void> _loadModelCheck() async {
    try {
      final mc = await _api.fetchPlayerModelCheck();
      if (!mounted) return;
      setState(() => _modelCheck = mc);
    } catch (_) {}
  }

  /// A MODELLEK PRÓBÁJA: a lövő-, a kapus- és a döntés-modell
  /// könyvtári összesítője és csapatonként a motor mondata, alatta a
  /// meccs-előrejelzés, a várható gólszerzők, az élő esély, a várható
  /// védekezés és a napi forma próbája (/library/player-model-check).
  /// Nincs ítélet → a szakasz elmarad.
  List<Widget> _modelCheckSection() {
    List<Map<String, dynamic>> sorok(String k) =>
        ((_modelCheck[k] as List?) ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
    final teams = sorok("teams");
    final kapusok = sorok("kapusok");
    final vedok = sorok("vedok");
    final dontesek = sorok("dontesek");
    final eloreSzoveg = _modelCheck["elorejelzes_text"];
    final golSzoveg = (_modelCheck["golszerzo_proba"] as Map?)?["verdict"];
    final eloSzoveg = (_modelCheck["elo_esely_proba"] as Map?)?["verdict"];
    final vedSzoveg = (_modelCheck["vedekezes_proba"] as Map?)?["verdict"];
    final formaSzoveg = (_modelCheck["forma_proba"] as Map?)?["verdict"];
    final figSzoveg = (_modelCheck["figura_proba"] as Map?)?["verdict"];
    final kfSzoveg = (_modelCheck["kapus_forma_proba"] as Map?)?["verdict"];
    final idoSzoveg = (_modelCheck["idokeres_proba"] as Map?)?["verdict"];
    final kvSzoveg =
        (_modelCheck["kapus_valasztas_proba"] as Map?)?["verdict"];
    final fdSzoveg = (_modelCheck["felderites_proba"] as Map?)?["verdict"];
    final hetesSzoveg = (_modelCheck["hetes_proba"] as Map?)?["verdict"];
    if (teams.isEmpty && kapusok.isEmpty && dontesek.isEmpty &&
        vedok.isEmpty &&
        eloreSzoveg is! String && golSzoveg is! String &&
        eloSzoveg is! String && vedSzoveg is! String &&
        formaSzoveg is! String && figSzoveg is! String &&
        kfSzoveg is! String && idoSzoveg is! String &&
        kvSzoveg is! String && fdSzoveg is! String &&
        hetesSzoveg is! String) {
      return const [];
    }
    final dOsszes =
        (_modelCheck["dontes_osszes"] as Map?)?.cast<String, dynamic>();
    final osszes = (_modelCheck["osszes"] as Map?)?.cast<String, dynamic>();
    final kOsszes =
        (_modelCheck["kapus_osszes"] as Map?)?.cast<String, dynamic>();
    return [
      const SizedBox(height: AppSpacing.lg),
      Text("A MODELLEK PRÓBÁJA", style: AppText.sectionLabel),
      const SizedBox(height: 4),
      // Az összkép: hány próba ítélt és hány bizonyított.
      if ((_modelCheck["ai_osszkep"] as Map?)?["verdict"] is String) ...[
        Text("Összkép: ${(_modelCheck["ai_osszkep"] as Map)["verdict"]}.",
            style: AppText.value.copyWith(fontSize: 13, color: AppColors.gold)),
        const SizedBox(height: 4),
      ],
      Text("A meccsek időrendjében minden modell CSAK a korábbi meccsekből "
          "jósol, és a pálya dönt: a lövő- és a kapus-szorzó a nyers "
          "várható gólhoz, a döntés-tanács a többi döntéshez, az "
          "előrejelzés a formához mérve. Ahol a modell pontosabb, a "
          "mondataira lehet építeni.",
          style: AppText.label),
      const SizedBox(height: AppSpacing.sm),
      if (osszes?["verdict"] is String)
        Text("${osszes!["verdict"]}.",
            style: AppText.value.copyWith(fontSize: 13)),
      const SizedBox(height: 4),
      for (final t in teams)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Text("${t["team"]}: ${t["verdict"]}.",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ),
      if (kOsszes?["verdict"] is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("${kOsszes!["verdict"]}.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      for (final t in kapusok)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Text("${t["team"]} kapusa: ${t["verdict"]}.",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ),
      // A védő-modell próbája: egyénre szabható-e a fal.
      for (final t in vedok)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Text("${t["team"]} védői: ${t["verdict"]}.",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ),
      if (dOsszes?["verdict"] is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Döntések a könyvtárban: ${dOsszes!["verdict"]}.",
            style: AppText.value.copyWith(fontSize: 13)),
        // Helyzetenként: hol igazolja a pálya a modell legjobb opcióját.
        for (final h in ((dOsszes["helyzetek"] as List?) ?? const [])
            .whereType<Map>())
          Padding(
            padding: const EdgeInsets.only(left: 12, top: 2),
            child: Text("· ${h["verdict"]}",
                style: AppText.label.copyWith(fontSize: 11.5)),
          ),
      ],
      for (final t in dontesek)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Text("${t["team"]} döntései: ${t["verdict"]}.",
              style: AppText.label.copyWith(fontSize: 11.5)),
        ),
      // A meccs-előrejelzés próbája a könyvtár időrendjében: a két csapat
      // korábbi meccseiből jósolt eredmény a formához mérve.
      if (eloreSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Meccs-előrejelzés: $eloreSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // A várható gólszerzők próbája: a "rá figyeljetek" mondat súlya.
      if (golSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Várható gólszerzők: $golSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // Az élő esély próbája: hozzátesz-e a csapat-modell az álláshoz.
      if (eloSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Élő esély: $eloSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // A várható védekezési rendszer próbája.
      if (vedSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Védekezési rendszer: $vedSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // A forró kéz próbája: kitart-e a napi forma, vagy a modell a jobb.
      if (formaSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Napi forma: $formaSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // A kapus-választás próbája: a lövők szerinti választás a sima
      // mérlegnél többet tud-e.
      if (kvSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Kapus-választás: $kvSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // A kapus napi formájának próbája: kitart-e egy jó / rossz félidő.
      if (kfSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("A kapus napi formája: $kfSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // Az időkérés próbája: megtöri-e a sorozatot a könyvtár meccsein.
      if (idoSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Időkérés a sorozat ellen: $idoSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // A felderítés próbája: visszaköszönnek-e a kulcsai a következő
      // meccsen (a liga általános kulcsaihoz mérve).
      if (fdSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Felderítés: $fdSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // A hetes-dobó választás próbája: a könyvtár dobója jobb-e.
      if (hetesSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Hetes-dobó: $hetesSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
      // A figuráik próbája: visszatérnek-e a felderítés figurái.
      if (figSzoveg is String) ...[
        const SizedBox(height: AppSpacing.sm),
        Text("Figurák: $figSzoveg.",
            style: AppText.value.copyWith(fontSize: 13)),
      ],
    ];
  }

  // Csapatonként a repertoár-változás a szezon két fele között — csak
  // ahol új vagy eltűnt figura van.
  final Map<String, Map<String, dynamic>> _repertoire = {};

  /// REPERTOÁR-VÁLTOZÁS csapatonként: ÚJ / ELTŰNT / maradt (a két fél
  /// gólarányával), rajzzal. Nincs változó csapat → a szakasz elmarad.
  List<Widget> _repertoireChanges() {
    if (_repertoire.isEmpty) return const [];
    List<Map<String, dynamic>> lista(Map<String, dynamic> rep, String k) =>
        ((rep[k] as List?) ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
    String nev(Map<String, dynamic> f) =>
        (f["name"] as String?)?.isNotEmpty == true
            ? "${f["name"]}"
            : "${f["zone"] ?? "?"}";
    String pct(dynamic v) => "${((v as num?) ?? 0).round()}%";
    Widget csempe(Map<String, dynamic> f, String cimke, Color szin,
        String reszlet) {
      return Container(
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: BoxDecoration(
          color: AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: szin.withValues(alpha: 0.6)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          SizedBox(
              width: 96, height: 48,
              child: CustomPaint(
                  painter: FigureShapePainter(
                      ((f["shape"] as List?) ?? const [])
                          .map((v) => (v as num).toDouble())
                          .toList()))),
          const SizedBox(width: AppSpacing.sm),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(cimke,
                  style: AppText.label
                      .copyWith(fontSize: 10.5, color: szin, letterSpacing: 0.6)),
              Text(nev(f), style: AppText.value.copyWith(fontSize: 12.5)),
              Text(reszlet, style: AppText.label.copyWith(fontSize: 11.5)),
            ],
          ),
        ]),
      );
    }
    return [
      const SizedBox(height: AppSpacing.lg),
      Text("REPERTOÁR-VÁLTOZÁS", style: AppText.sectionLabel),
      const SizedBox(height: 4),
      Text("A szezon első és második felének figurái összevetve — mi jött "
          "be, mi tűnt el, mi maradt. A saját csapatnál: él-e még a "
          "figura; az ellenfélnél: van-e új, amire a régi felderítés nem "
          "készít fel.",
          style: AppText.label),
      const SizedBox(height: AppSpacing.sm),
      for (final e in _repertoire.entries) ...[
        Text(e.key, style: AppText.value.copyWith(fontSize: 13)),
        if ((e.value["verdict"] as String?)?.isNotEmpty == true)
          Text("${e.value["verdict"]}",
              style: AppText.label.copyWith(fontSize: 11.5)),
        const SizedBox(height: 4),
        Wrap(spacing: AppSpacing.md, runSpacing: AppSpacing.sm, children: [
          for (final f in lista(e.value, "new").take(3))
            csempe(f, "ÚJ A MÁSODIK FÉLBEN", AppColors.accent,
                "${f["attacks"]} támadás · ${f["goals"]} gól"),
          for (final f in lista(e.value, "dropped").take(3))
            csempe(f, "ELTŰNT", AppColors.away,
                "${f["attacks"]} támadás · ${f["goals"]} gól az első félben"),
          for (final f in lista(e.value, "kept").take(3))
            csempe(
                f,
                "MARADT",
                AppColors.textFaint,
                "${(f["older"] as Map?)?["attacks"]} támadás "
                "(${pct((f["older"] as Map?)?["goal_pct"])}) → "
                "${(f["newer"] as Map?)?["attacks"]} támadás "
                "(${pct((f["newer"] as Map?)?["goal_pct"])})"),
        ]),
        const SizedBox(height: AppSpacing.sm),
      ],
    ];
  }

  /// VISSZATÉRŐ FIGURÁK csapatonként, rajzzal — amit meccsről meccsre
  /// hoznak. Nincs ilyen csapat → a szakasz elmarad.
  List<Widget> _figureLibraries() {
    if (_figures.isEmpty) return const [];
    return [
      const SizedBox(height: AppSpacing.lg),
      Text("VISSZATÉRŐ FIGURÁK", style: AppText.sectionLabel),
      const SizedBox(height: 4),
      Text("Amit egy csapat meccsről meccsre hoz — a saját csapatnál "
          "ez a repertoár, az ellenfélnél a felkészülés lapja.",
          style: AppText.label),
      const SizedBox(height: AppSpacing.sm),
      for (final e in _figures.entries) ...[
        Text(e.key, style: AppText.value.copyWith(fontSize: 13)),
        const SizedBox(height: 4),
        Wrap(spacing: AppSpacing.md, runSpacing: AppSpacing.sm, children: [
          for (final f in e.value.take(4))
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: BoxDecoration(
                color: AppColors.surfaceAlt,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.border),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                SizedBox(
                    width: 96, height: 48,
                    child: CustomPaint(
                        painter: FigureShapePainter(
                            ((f["shape"] as List?) ?? const [])
                                .map((v) => (v as num).toDouble())
                                .toList()))),
                const SizedBox(width: AppSpacing.sm),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                        (f["name"] as String?)?.isNotEmpty == true
                            ? "${f["name"]}"
                            : "${f["zone"] ?? "?"}",
                        style: AppText.value.copyWith(fontSize: 12.5)),
                    Text(
                        "${f["matches"]} meccs · ${f["attacks"]} támadás · "
                        "${f["goals"]} gól",
                        style: AppText.label.copyWith(fontSize: 11.5)),
                  ],
                ),
              ]),
            ),
        ]),
        const SizedBox(height: AppSpacing.sm),
      ],
    ];
  }

  // ---- Összkép -------------------------------------------------------

  Widget _totals() {
    final perc = ((_summary["total_duration_s"] as num?) ?? 0) / 60.0;
    final cells = <(String, String)>[
      ("Meccs", "${_summary["matches"] ?? 0}"),
      ("Mért játékidő", "${perc.round()} perc"),
      ("Gól", "${_summary["goals"] ?? 0}"),
      ("Lövés", "${_summary["shots"] ?? 0}"),
      ("Védés", "${_summary["saves"] ?? 0}"),
      ("Sprint", "${_summary["sprints"] ?? 0}"),
      ("Megtett táv", "${_summary["distance_km"] ?? 0} km"),
    ];
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final (label, value) in cells)
          Container(
            width: 150,
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: AppTheme.card(),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(value, style: AppText.statBig),
                  const SizedBox(height: 2),
                  Text(label, style: AppText.label.copyWith(fontSize: 11)),
                ]),
          ),
      ],
    );
  }

  // ---- Toplisták -----------------------------------------------------

  Widget _leaderBoards() {
    const boards = <(String, String, IconData)>[
      ("goals", "Gól", Icons.sports_score),
      ("assists", "Gólpassz", Icons.share_outlined),
      ("blocks", "Blokk", Icons.pan_tool_outlined),
      ("steals", "Labdaszerzés", Icons.back_hand_outlined),
      ("saves", "Védés", Icons.sports_handball),
    ];
    final vanBarmi = boards.any(
        (b) => ((_leaders[b.$1] as List?) ?? const []).isNotEmpty);
    if (!vanBarmi) {
      return Text(
          "Még nincs toplista. A szezon-listák MEZSZÁM alapján "
          "összesítenek — a mezszám nélküli játékosok kimaradnak, mert "
          "meccsek közt nincs stabil azonosítójuk. A mezszámokat a "
          "meccs-elemzőben lehet hozzárendelni, és onnantól minden "
          "korábbi meccs is beszámít.",
          style: AppText.label);
    }
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final (key, label, icon) in boards)
          _board(label, icon, (_leaders[key] as List?) ?? const []),
      ],
    );
  }

  Widget _board(String label, IconData icon, List<dynamic> rows) {
    return Container(
      width: 260,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: AppTheme.card(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, size: 16, color: AppColors.accent),
          const SizedBox(width: 6),
          Text(label, style: AppText.value),
        ]),
        const SizedBox(height: AppSpacing.sm),
        if (rows.isEmpty)
          Text("nincs adat", style: AppText.label.copyWith(fontSize: 11.5))
        else
          for (var i = 0; i < rows.length; i++)
            // A játékos megkeresi magát a listán — és onnan a saját
            // lapjára akar jutni, nem egy másik menüpontba.
            InkWell(
              onTap: () => _openPlayer(rows[i] as Map),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  SizedBox(
                      width: 18,
                      child: Text("${i + 1}.",
                          style: AppText.label.copyWith(fontSize: 11.5))),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceAlt,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text("#${(rows[i] as Map)["jersey"]}",
                        style: AppText.value.copyWith(fontSize: 11.5)),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    // Ha van felvitt NÉV, az kerül előre — az edző nem
                    // számokban gondolkodik. Név nélkül marad a csapat.
                    child: Text(
                        ((rows[i] as Map)["name"] as String?)?.isNotEmpty ==
                                true
                            ? "${(rows[i] as Map)["name"]}"
                            : "${(rows[i] as Map)["team"]}",
                        overflow: TextOverflow.ellipsis,
                        style: AppText.label.copyWith(fontSize: 11.5)),
                  ),
                  Text("${(rows[i] as Map)["value"]}",
                      style: AppText.value.copyWith(fontSize: 12.5)),
                  const Icon(Icons.chevron_right,
                      size: 14, color: AppColors.textFaint),
                ]),
              ),
            ),
      ]),
    );
  }

  /// A toplista sorából a játékos saját lapjára (görbe + "mit
  /// gyakorolj"), előre kitöltve.
  void _openPlayer(Map row) {
    final team = row["team"] as String?;
    final jersey = (row["jersey"] as num?)?.toInt();
    if (team == null || jersey == null) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PlayerTrendScreen(
        teams: _teams,
        initialTeam: team,
        initialJersey: jersey,
      ),
    ));
  }

  // ---- Riportok ------------------------------------------------------

  Widget _reports() {
    if (_teams.isEmpty) {
      return Text("Riporthoz legalább egy feldolgozott meccs kell.",
          style: AppText.label);
    }
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final t in _teams)
          OutlinedButton.icon(
            onPressed: () => _saveSeasonReport(t),
            icon: const Icon(Icons.description_outlined, size: 16),
            label: Text("$t szezon-riport"),
          ),
        if (_teams.length >= 2)
          OutlinedButton.icon(
            onPressed: _headToHead,
            icon: const Icon(Icons.compare_arrows, size: 16),
            label: const Text("Egymás ellen riport"),
          ),
      ],
    );
  }

  /// A letöltött HTML mentése — a böngészőből Ctrl+P → PDF.
  Future<void> _saveBytes(
      List<int> bytes, String dialogTitle, String fileName) async {
    final path = await FilePicker.platform.saveFile(
      dialogTitle: dialogTitle,
      fileName: fileName,
      type: FileType.custom,
      allowedExtensions: const ["html"],
    );
    if (path == null) return; // a felhasználó megszakította
    await File(path).writeAsBytes(bytes);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text("Mentve: $path — böngészőből nyomtatható")));
  }

  String _safe(String s) =>
      s.replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");

  Future<void> _saveSeasonReport(String team) async {
    try {
      final bytes = await _api.fetchSeasonReport(team);
      if (!mounted) return;
      await _saveBytes(bytes, "Szezon-riport mentése (HTML)",
          "szezon_riport_${_safe(team)}.html");
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Szezon-riport hiba: ${humanError(e)} — legalább "
              "2 meccs kell a csapattól")));
    }
  }

  Future<void> _headToHead() async {
    String? a = _teams.first;
    String? b = _teams.length > 1 ? _teams[1] : null;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setLocal) {
        Widget picker(String label, String? value, void Function(String?) on) {
          return Row(children: [
            SizedBox(width: 70, child: Text(label, style: AppText.label)),
            Expanded(
              child: DropdownButton<String>(
                value: value,
                isExpanded: true,
                dropdownColor: AppColors.surface,
                style: AppText.value.copyWith(fontSize: 13),
                items: [
                  for (final t in _teams)
                    DropdownMenuItem(value: t, child: Text(t)),
                ],
                onChanged: (v) => setLocal(() => on(v)),
              ),
            ),
          ]);
        }

        return AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text("Egymás ellen riport"),
          content: SizedBox(
            width: 380,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              picker("Csapat A", a, (v) => a = v),
              picker("Csapat B", b, (v) => b = v),
              const SizedBox(height: AppSpacing.sm),
              Text(
                  "A riport a két csapat KÖZÖS meccseiből készül — ha még "
                  "nem játszottak egymással a könyvtárban, üres marad.",
                  style: AppText.label.copyWith(fontSize: 11.5)),
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
              onPressed: (a == null || b == null || a == b)
                  ? null
                  : () => Navigator.pop(ctx, true),
              child: const Text("Riport"),
            ),
          ],
        );
      }),
    );
    if (ok != true || a == null || b == null || !mounted) return;
    try {
      final bytes = await _api.fetchHeadToHead(a!, b!);
      if (!mounted) return;
      await _saveBytes(bytes, "Egymás ellen riport mentése (HTML)",
          "egymas_ellen_${_safe(a!)}_vs_${_safe(b!)}.html");
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Egymás ellen hiba: ${humanError(e)} — csak közös "
              "meccsel rendelkező pároshoz készül riport")));
    }
  }
}
