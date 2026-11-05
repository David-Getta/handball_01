/// Meccsterv — "hogyan verjük meg ŐKET", saját menüponttal.
///
/// A meccsterv-illesztés (a mi profilunk × az ő profiljuk) eddig csak a
/// felderítő jelentés egyik kártyája volt: ahhoz, hogy az edző lássa, a
/// felderítésben kézzel kellett kijelölnie MINDEN meccset, amelyiken az
/// ellenfél játszott — és külön a sajátjait is. A meccs előtti este
/// viszont pont ez az EGY kérdés érdekli.
///
/// Ez a képernyő két csapatnevet kér (mi · ők), és a könyvtárból MAGA
/// gyűjti össze mindkettő összes meccsét — a felhasználónak nem kell
/// tudnia, melyik meccsen melyik oldalon játszottak.
///
/// Két rész:
///   TERV: a páros-specifikus tanácsok (az ő gyengéjük × a mi
///         erősségünk) — sorszámozott, edzői mondatok;
///   STÍLUS: mennyire hasonlít a két játék (0–100), és melyik tengelyen
///         a legnagyobb az eltérés — tükör-meccsen a részletek
///         döntenek, ellentétes stílusnál az, ki kényszeríti rá a
///         sajátját.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "figure_shape_painter.dart";
import "shell/app_shell.dart";
import "waiting.dart";

class MatchupScreen extends StatefulWidget {
  const MatchupScreen({super.key});

  @override
  State<MatchupScreen> createState() => _MatchupScreenState();
}

class _MatchupScreenState extends State<MatchupScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  bool _working = false;
  String? _error;

  List<Map<String, dynamic>> _matches = [];
  List<String> _teams = [];
  String? _own;
  String? _opp;

  Map<String, dynamic>? _result;
  // A meccs-előrejelzés (GET /library/forecast): külön hívás, a hibája
  // nem viszi el a tervet.
  Map<String, dynamic>? _forecast;
  // Az AI-edzésterv a meccsre (GET /library/next-match-plan).
  List<Map<String, dynamic>> _plan = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final ms = await _api.listMatches();
      if (!mounted) return;
      final names = <String>{};
      for (final m in ms) {
        for (final k in const ["home_team", "away_team"]) {
          final n = m[k] as String?;
          if (n != null && n.isNotEmpty) names.add(n);
        }
      }
      final sorted = names.toList()..sort();
      setState(() {
        _matches = ms;
        _teams = sorted;
        _own = sorted.isNotEmpty ? sorted.first : null;
        _opp = sorted.length > 1 ? sorted[1] : null;
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

  /// A csapat ÖSSZES meccse a könyvtárból, oldallal együtt — a felderítés
  /// `items` alakjában. Ezt eddig kézzel kellett összekattintani.
  List<Map<String, dynamic>> _itemsOf(String team) {
    final out = <Map<String, dynamic>>[];
    for (final m in _matches) {
      final id = m["match_id"] as String?;
      if (id == null) continue;
      if (m["home_team"] == team) {
        out.add({"match_id": id, "team": "home"});
      } else if (m["away_team"] == team) {
        out.add({"match_id": id, "team": "away"});
      }
    }
    return out;
  }

  Future<void> _build() async {
    final own = _own;
    final opp = _opp;
    if (own == null || opp == null) return;
    setState(() {
      _working = true;
      _error = null;
      _result = null;
      _forecast = null;
      _plan = const [];
    });
    try {
      final r = await _api.fetchMatchup(_itemsOf(own), _itemsOf(opp));
      Map<String, dynamic>? f;
      try {
        f = await _api.fetchLibraryForecast(own, opp);
      } catch (_) {}
      List<Map<String, dynamic>> terv = const [];
      try {
        terv = await _api.fetchNextMatchPlan(own, opp);
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _result = r;
        _forecast = f;
        _plan = terv;
        _working = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _working = false;
        _error = "A meccsterv nem készült el: ${humanError(e)}";
      });
    }
  }

  /// A meccsterv nyomtatható lapja — a meccs előtti este a papírt
  /// viszi az edző, nem a laptopot.
  Future<void> _exportPlan() async {
    final own = _own;
    final opp = _opp;
    if (own == null || opp == null || _working) return;
    setState(() => _working = true);
    try {
      final bytes =
          await _api.fetchMatchupExport(_itemsOf(own), _itemsOf(opp));
      if (!mounted) return;
      String safe(String s) =>
          s.replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Meccsterv mentése (HTML)",
        fileName: "meccsterv_${safe(own)}_vs_${safe(opp)}.html",
        type: FileType.custom,
        allowedExtensions: const ["html"],
      );
      if (path != null) {
        await File(path).writeAsBytes(bytes);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text("Meccsterv mentve: $path — böngészőből "
                "nyomtatható")));
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = "A meccsterv-lap nem készült el: "
          "${humanError(e)}");
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.matchup,
      crumbPath: "ELEMZÉS · MECCSTERV",
      child: _loading
          ? const WaitingView("Meccs-könyvtár olvasása…",
              icon: Icons.fact_check_outlined)
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Meccsterv", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "a MI profilunk × az Ő profiljuk: mit csináljunk "
                  "konkrétan ellenük — minden meccsükből, amit ismerünk",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              _picker(),
              const SizedBox(height: AppSpacing.md),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(_error!,
                      style: AppText.label.copyWith(color: AppColors.away)),
                ),
              if (_working)
                const Expanded(
                    child: WaitingView("Meccsterv készül…",
                        hint: "Mindkét csapat ÖSSZES meccsét átnézzük — "
                            "több meccsnél ez percekbe telhet.",
                        icon: Icons.fact_check_outlined))
              else if (_result != null)
                Expanded(child: _body())
              else
                Expanded(child: _hint()),
            ]),
    );
  }

  Widget _hint() {
    if (_teams.length < 2) {
      return Text(
          "Meccstervhez legalább két különböző csapat kell a "
          "könyvtárban — dolgozz fel még egy meccset.",
          style: AppText.label);
    }
    final own = _own, opp = _opp;
    final n1 = own == null ? 0 : _itemsOf(own).length;
    final n2 = opp == null ? 0 : _itemsOf(opp).length;
    return Text(
        "Válaszd ki, KI vagy MI és KI az ellenfél, aztán készítsd el a "
        "tervet. Most $n1 saját és $n2 ellenfél-meccs van a "
        "könyvtárban — minél több, annál megbízhatóbb a kép "
        "(egyetlen meccs még lehet napi forma).",
        style: AppText.label);
  }

  Widget _picker() {
    Widget drop(String label, String? value, void Function(String?) on) {
      return Row(mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: AppText.sectionLabel),
        const SizedBox(width: AppSpacing.sm),
        DropdownButton<String>(
          value: value,
          dropdownColor: AppColors.surface,
          style: AppText.value.copyWith(fontSize: 13),
          items: [
            for (final t in _teams) DropdownMenuItem(value: t, child: Text(t)),
          ],
          onChanged: (v) => setState(() => on(v)),
        ),
      ]);
    }

    final ready = _own != null && _opp != null && _own != _opp;
    return Wrap(
      spacing: AppSpacing.lg,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        drop("MI", _own, (v) => _own = v),
        drop("ŐK", _opp, (v) => _opp = v),
        FilledButton.icon(
          onPressed: ready && !_working ? _build : null,
          style: FilledButton.styleFrom(
              backgroundColor: AppColors.accent,
              foregroundColor: AppColors.onAccent),
          icon: const Icon(Icons.fact_check_outlined, size: 18),
          label: const Text("Meccsterv"),
        ),
        // A nyomtatható lap az elkészült terv MELLETT jár: a meccs
        // előtti este a papírt viszi az edző, nem a laptopot.
        if (_result != null)
          OutlinedButton.icon(
            onPressed: _working ? null : _exportPlan,
            icon: const Icon(Icons.print_outlined, size: 16),
            label: const Text("Nyomtatható meccsterv"),
          ),
        if (_own != null && _opp != null && _own == _opp)
          Text("ugyanaz a csapat — válassz másik ellenfelet",
              style: AppText.label.copyWith(color: AppColors.away)),
      ],
    );
  }

  // ---- Eredmény ------------------------------------------------------

  Widget _body() {
    final r = _result!;
    final plan = ((r["plan"] as List?) ?? const []).cast<String>();
    final style = (r["style"] as Map?) ?? const {};
    final fText = _forecast?["text"];
    final fProba = _forecast?["proba_text"];
    // A várható gólszerzők: "home" = MI, "away" = ŐK (a hívás sorrendje).
    final gsz = (_forecast?["golszerzok_text"] as Map?) ?? const {};
    final gProba = (_forecast?["golszerzo_proba"] as Map?)?["verdict"];
    final vedOk = ((_forecast?["vedekezes_text"] as Map?) ?? const {})["away"];
    final kulcs = (_forecast?["kulcsember_text"] as Map?) ?? const {};
    // Mi lenne a kulcsemberük nélkül (a várható góljuk).
    final hiany = ((_forecast?["kulcs_hiany"] as Map?)?["away"]
        as Map?)?["text"];
    // Melyik kapusunk álljon az ő lövőik ellen ("home" = MI).
    final kapus = ((_forecast?["kapus_javaslat"] as Map?)?["home"]
        as Map?)?["verdict"];
    final figProba = (_forecast?["figura_proba"] as Map?)?["verdict"];
    final vedProba = (_forecast?["vedekezes_proba"] as Map?)?["verdict"];
    final kvProba =
        (_forecast?["kapus_valasztas_proba"] as Map?)?["verdict"];
    final fdProba = (_forecast?["felderites_proba"] as Map?)?["verdict"];
    // Ki dobja a hetest ("home" = MI) — és a választás próbája.
    final hetes = ((_forecast?["hetes_dobo"] as Map?)?["home"]
        as Map?)?["verdict"];
    final hetesProba = (_forecast?["hetes_proba"] as Map?)?["verdict"];
    return ListView(children: [
      // ELŐREJELZÉS: a két csapat könyvtári meccseiből tanult csapat-modell
      // várakozása (lövés-mennyiség és -minőség sávonként, befejezés,
      // kapus) — a próbával, hogy látsszon, mennyire lehet rá építeni.
      if (fText is String) ...[
        Text("ELŐREJELZÉS", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        Container(
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: AppTheme.card(),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(fText,
                    style: AppText.value.copyWith(
                        fontSize: 13, color: AppColors.textPrimary)),
                if (fProba is String) ...[
                  const SizedBox(height: 4),
                  Text("A próba a könyvtárban: $fProba.",
                      style: AppText.label.copyWith(fontSize: 11.5)),
                ],
                // Kire figyeljen a védekezés, és kire járassuk a labdát.
                if (gsz["away"] is String) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text("Az ő várható gólszerzőik: ${gsz["away"]}.",
                      style: AppText.label.copyWith(
                          fontSize: 12.5, color: AppColors.textPrimary)),
                ],
                // A kulcsember: a legnagyobb gól-értékű lövő (ugyanannyi
                // lövésből ennyivel többet ér a csapat többi lövőjénél).
                if (kulcs["away"] is String) ...[
                  const SizedBox(height: 4),
                  Text("Kulcsemberük — vegyétek ki a játékból: "
                      "${kulcs["away"]}"
                      "${hiany is String ? " ($hiany)" : ""}.",
                      style: AppText.label.copyWith(
                          fontSize: 12.5, color: AppColors.gold)),
                ],
                if (gsz["home"] is String) ...[
                  const SizedBox(height: 4),
                  Text("A mi várható gólszerzőink: ${gsz["home"]}.",
                      style: AppText.label.copyWith(
                          fontSize: 12.5, color: AppColors.textPrimary)),
                ],
                if (kulcs["home"] is String) ...[
                  const SizedBox(height: 4),
                  Text("Kulcsemberünk — juttassátok lövéshez: "
                      "${kulcs["home"]}.",
                      style: AppText.label.copyWith(
                          fontSize: 12.5, color: AppColors.gold)),
                ],
                if (gProba is String) ...[
                  const SizedBox(height: 4),
                  Text("A gólszerző-becslés próbája: $gProba.",
                      style: AppText.label.copyWith(fontSize: 11.5)),
                ],
                // Melyik fal ellen tervezzük a figurákat.
                if (vedOk is String) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text("Várható védekezésük: $vedOk.",
                      style: AppText.label.copyWith(
                          fontSize: 12.5, color: AppColors.textPrimary)),
                ],
                if (vedProba is String) ...[
                  const SizedBox(height: 4),
                  Text("A védekezés-becslés próbája: $vedProba.",
                      style: AppText.label.copyWith(fontSize: 11.5)),
                ],
                if (kapus is String) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text("Kapus ellenük: $kapus.",
                      style: AppText.label.copyWith(
                          fontSize: 12.5, color: AppColors.textPrimary)),
                ],
                // A kapus-választás próbája: igazolódott-e a könyvtárban.
                if (kapus is String && kvProba is String) ...[
                  const SizedBox(height: 4),
                  Text("A kapus-választás próbája: $kvProba.",
                      style: AppText.label.copyWith(fontSize: 11.5)),
                ],
                if (hetes is String) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text("Hetes-dobónk: $hetes.",
                      style: AppText.label.copyWith(
                          fontSize: 12.5, color: AppColors.textPrimary)),
                ],
                if (hetes is String && hetesProba is String) ...[
                  const SizedBox(height: 4),
                  Text("A hetes-dobó választás próbája: $hetesProba.",
                      style: AppText.label.copyWith(fontSize: 11.5)),
                ],
                // A figura-felderítés súlya: visszatérnek-e a figurák.
                if (figProba is String) ...[
                  const SizedBox(height: 4),
                  Text("A figura-felderítés próbája: $figProba.",
                      style: AppText.label.copyWith(fontSize: 11.5)),
                ],
                // A felderítés súlya: visszaköszönnek-e a kulcsai.
                if (fdProba is String) ...[
                  const SizedBox(height: 4),
                  Text("A felderítés próbája: $fdProba.",
                      style: AppText.label.copyWith(fontSize: 11.5)),
                ],
              ]),
        ),
        const SizedBox(height: AppSpacing.lg),
      ],
      // EDZÉSTERV A MECCSRE: a modellek meccs előtti képéből egy rövid,
      // indokolt lista — a hét edzéseinek váza.
      if (_plan.isNotEmpty) ...[
        Text("EDZÉSTERV A MECCSRE (AI)", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        for (final (i, t) in _plan.indexed)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: AppTheme.card(),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text("${i + 1}. ${t["title"] ?? ""}",
                        style: AppText.value.copyWith(
                            fontSize: 13, color: AppColors.gold)),
                    const SizedBox(height: 2),
                    Text("${t["why"] ?? ""}.",
                        style: AppText.label.copyWith(
                            fontSize: 12, color: AppColors.textPrimary)),
                    const SizedBox(height: 2),
                    Text("Gyakorlat: ${t["drill"] ?? ""}.",
                        style: AppText.label.copyWith(fontSize: 11.5)),
                  ]),
            ),
          ),
        const SizedBox(height: AppSpacing.md),
      ],
      Text("TERV", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      if (plan.isEmpty)
        Text(
            "Ebből az anyagból nem jött ki páros-specifikus tanács. Ez "
            "nem hiba: a terv akkor szólal meg, ha az Ő mérhető "
            "gyengéjük találkozik a MI mérhető erősségünkkel — kevés "
            "meccsből ez gyakran még nem áll össze.",
            style: AppText.label)
      else
        for (var i = 0; i < plan.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: AppTheme.card(),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 24,
                      child: Text("${i + 1}.",
                          style: AppText.value
                              .copyWith(color: AppColors.gold)),
                    ),
                    Expanded(
                        child: Text(plan[i],
                            style: AppText.label.copyWith(
                                fontSize: 13,
                                color: AppColors.textPrimary))),
                  ]),
            ),
          ),
      // A visszatérő figurák rajzzal: az övék ("erre készüljetek") és a
      // miénk ("ezt hozzuk") — a könyvtárból, több meccs kell hozzá.
      ..._figuresSection("AZ Ő VISSZATÉRŐ FIGURÁIK",
          (r["opp_figures"] as List?) ?? const [], "${r["opp_team"] ?? ""}",
          "erre készüljetek: videó, bejátszott védekezés, a súlypont "
          "sávjának lezárása"),
      ..._figuresSection("A MI VISSZATÉRŐ FIGURÁINK",
          (r["own_figures"] as List?) ?? const [], "${r["own_team"] ?? ""}",
          "ezt hozzuk meccsről meccsre — az ellenfél is látja: legyen "
          "második befejezés"),
      // Az ellenfél repertoár-változása a kijelölt meccsei két fele
      // között: az utóbbi meccseken bejött figurára a régi felderítés
      // nem készít fel; az eltűntre egyedül ne készüljetek.
      ..._figuresSection("ÚJ FIGURÁJUK AZ UTÓBBI MECCSEKEN",
          ((r["opp_repertoire"] as Map?)?["new"] as List?) ?? const [],
          "${r["opp_team"] ?? ""}",
          "ez az utóbbi meccseken jött be — a régi felderítés nem készít "
          "fel rá: erről külön videó és bejátszott védekezés"),
      ..._figuresSection("ELTŰNT FIGURÁJUK",
          ((r["opp_repertoire"] as Map?)?["dropped"] as List?) ?? const [],
          "${r["opp_team"] ?? ""}",
          "az első meccseken hozták, az utóbbiakon nem — egyedül erre ne "
          "készüljetek, de a videóban maradjon"),
      const SizedBox(height: AppSpacing.lg),
      Text("STÍLUS", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      _styleCard(style),
    ]);
  }

  /// Egy csapat visszatérő figurái mini-pályán (név vagy zóna, meccs /
  /// támadás / gól). Üres listánál a szakasz elmarad.
  List<Widget> _figuresSection(
      String cim, List figures, String team, String tanacs) {
    if (figures.isEmpty) return const [];
    return [
      const SizedBox(height: AppSpacing.lg),
      Text(cim, style: AppText.sectionLabel),
      const SizedBox(height: 4),
      Text("$team · $tanacs", style: AppText.label),
      const SizedBox(height: AppSpacing.sm),
      for (final f in figures.take(4))
        if (f is Map)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: AppTheme.card(),
              child: Row(children: [
                SizedBox(
                    width: 120, height: 60,
                    child: CustomPaint(
                        painter: FigureShapePainter(
                            ((f["shape"] as List?) ?? const [])
                                .map((v) => (v as num).toDouble())
                                .toList()))),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                          (f["name"] as String?)?.isNotEmpty == true
                              ? "${f["name"]} · ${f["zone"] ?? "?"}"
                              : "${f["zone"] ?? "?"}",
                          style: AppText.value.copyWith(fontSize: 13)),
                      const SizedBox(height: 2),
                      Text(
                          "${f["matches"]} meccsen ${f["attacks"]} támadás, "
                          "${f["goals"]} gól "
                          "(${((f["goal_pct"] as num?) ?? 0).round()}%)",
                          style: AppText.label),
                    ],
                  ),
                ),
              ]),
            ),
          ),
    ];
  }

  /// A 0..1 skálájú tengely-érték olvasható alakja.
  String _pct(dynamic v) {
    final n = (v as num?)?.toDouble();
    if (n == null) return "—";
    return "${(n * 100).round()}%";
  }

  /// Mit jelent a MAGASABB érték az adott tengelyen. A puszta szám
  /// önmagában nem tanács: az edzőnek azt kell tudnia, melyik irány
  /// mit jelent a pályán. (A tengely-nevek a motorból jönnek.)
  String? _axisHint(String axis) {
    switch (axis) {
      case "lövés-távolság":
        return "magasabb = többet lő távolról";
      case "tempó":
        return "magasabb = több támadás percenként";
      case "lerohanás":
        return "magasabb = többet kontrázik";
      case "elzárás":
        return "magasabb = többet játszik elzárásból";
      case "beállós játék":
        return "magasabb = többet játszik a beállóval";
      case "keménység":
        return "magasabb = több kiállítás és okozott hetes";
      default:
        return null;
    }
  }

  Widget _styleCard(Map style) {
    final score = style["score_pct"];
    final verdict = style["verdict"] as String?;
    final axes = (style["axes"] as List?) ?? const [];
    if (score == null) {
      return Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: AppTheme.card(),
        child: Text(
            "A stílus-hasonlításhoz kevés a KÖZÖS mért tengely — több "
            "meccs kell valamelyik csapattól.",
            style: AppText.label),
      );
    }
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: AppTheme.card(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text("$score%", style: AppText.statBig),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
              child: Text("stílus-hasonlóság",
                  style: AppText.label.copyWith(fontSize: 12))),
        ]),
        if (verdict != null && verdict.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(verdict,
              style: AppText.label.copyWith(
                  fontSize: 12.5, color: AppColors.textPrimary)),
        ],
        if (axes.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          // A LEGNAGYOBB eltérésű tengely a terv tétje: azt kell a
          // magunk javára billenteni. A backend növekvő eltérés szerint
          // adja a sorokat, ezért a végéről mutatjuk a hármat.
          Text("A legnagyobb eltérések", style: AppText.sectionLabel),
          const SizedBox(height: 4),
          for (final row in axes.reversed.take(3))
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(
                        child: Text("${(row as Map)["axis"]}",
                            style:
                                AppText.label.copyWith(fontSize: 12))),
                    // Százalékban: a 0..1 nyers szám nem mond semmit
                    // annak, aki nem a képletet nézi.
                    Text("mi ${_pct((row)["own"])} · "
                        "ők ${_pct((row)["opp"])}",
                        style: AppText.value.copyWith(fontSize: 12)),
                  ]),
                  if (_axisHint("${(row)["axis"]}") != null)
                    Text(_axisHint("${(row)["axis"]}")!,
                        style: AppText.label.copyWith(
                            fontSize: 10.5, color: AppColors.textFaint)),
                ],
              ),
            ),
        ],
      ]),
    );
  }
}
