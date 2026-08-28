/// Keret — a csapat MINDEN mezszáma egy táblában, saját menüponttal.
///
/// A szezon-toplisták az öt legjobbat adják. A játékos viszont nem a
/// gólkirályt keresi, hanem a SAJÁT sorát; az edző pedig a teljes
/// keretet nézi végig, nem a kiugró neveket. Erre eddig nem volt hely
/// a felületen: a mezszám-alapú összegek megvoltak a motorban, de csak
/// a top 5 jutott ki belőlük.
///
/// A tábla rendezhető (koppints az oszlopfejre), és egy sorra koppintva
/// a játékos fejlődés-görbéje nyílik — előre kitöltve, nem üres űrlap.
///
/// Itt lehet NEVET adni a mezszámoknak (ceruza-ikon). A név
/// csapat-szintű, nem meccsenkénti: a mezszám a szezonban stabil, a
/// track-azonosító nem — egy helyen felvitt név minden korábbi és
/// későbbi meccsen is látszik (toplisták, szezon-lap).
///
/// A "meccs" oszlop szándékosan az első szám: enélkül egy alacsony
/// gólszám félrevezet — kevés játék vagy gyenge forma? Két külön
/// kérdés, két külön teendő.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "player_trend_screen.dart";
import "shell/app_shell.dart";
import "waiting.dart";

/// A tábla oszlopai: a válasz kulcsa és a fejléc-felirat.
const List<(String, String)> kRosterColumns = [
  ("matches", "Meccs"),
  ("goals", "Gól"),
  ("assists", "Gólpassz"),
  ("blocks", "Blokk"),
  ("steals", "Szerzés"),
  ("saves", "Védés"),
];

class RosterScreen extends StatefulWidget {
  const RosterScreen({super.key});

  @override
  State<RosterScreen> createState() => _RosterScreenState();
}

class _RosterScreenState extends State<RosterScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  bool _rowsLoading = false;
  String? _error;
  List<String> _teams = [];
  String? _team;
  List<Map<String, dynamic>> _players = [];
  String _note = "";
  // Mezszám → hány gyakorlandója van a szezonban (az egyéni
  // edzés-tervből). A keret-lap így nem csak azt mutatja, ki mit
  // teljesített, hanem azt is, kivel van dolga az edzőnek.
  Map<int, int> _focusCount = {};

  /// Rendezés: melyik oszlop szerint, és csökkenő-e. A mezszám az
  /// alapértelmezés (a keret-lap "névsora"), az teljesítmény-semleges.
  String _sortKey = "jersey";
  bool _desc = false;

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
        _teams = sorted;
        _team = sorted.isNotEmpty ? sorted.first : null;
        _loading = false;
      });
      if (_team != null) {
        _loadRoster();
        _loadFocus();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "A meccs-könyvtár nem érhető el: ${humanError(e)}";
        _loading = false;
      });
    }
  }

  Future<void> _loadRoster() async {
    final team = _team;
    if (team == null) return;
    setState(() {
      _rowsLoading = true;
      _error = null;
    });
    try {
      final r = await _api.fetchTeamRoster(team);
      if (!mounted) return;
      setState(() {
        _players = [
          for (final p in (r["players"] as List? ?? []))
            Map<String, dynamic>.from(p as Map)
        ];
        _note = (r["note"] as String?) ?? "";
        _rowsLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _rowsLoading = false;
        _error = "A keret nem érhető el: ${humanError(e)}";
      });
    }
  }

  /// A csapat egyéni edzés-terve — EGY kérés az egész keretre.
  ///
  /// Külön hívás: minden meccset átnéz, a keret-tábla pedig nélküle is
  /// teljes. Hibánál csendben elmarad (a szám-oszlopok érvényesek
  /// maradnak).
  Future<void> _loadFocus() async {
    final team = _team;
    if (team == null) return;
    setState(() => _focusCount = {});
    try {
      final terv = await _api.fetchTeamPlayerPlan(team);
      if (!mounted) return;
      final map = <int, int>{};
      for (final p in terv) {
        final j = (p["jersey"] as num?)?.toInt();
        final n = ((p["items"] as List?) ?? const []).length;
        if (j != null && n > 0) map[j] = n;
      }
      setState(() => _focusCount = map);
    } catch (_) {
      // a keret enélkül is teljes
    }
  }

  List<Map<String, dynamic>> get _sorted {
    final rows = List<Map<String, dynamic>>.of(_players);
    rows.sort((a, b) {
      int c;
      if (_sortKey == "name") {
        // Névsor: a névtelenek a lista VÉGÉRE kerülnek (növekvő
        // rendezésnél), mert ott nem zavarnak — nem hiányzó
        // teljesítmény, csak hiányzó név.
        final x = (a["name"] as String?) ?? "";
        final y = (b["name"] as String?) ?? "";
        if (x.isEmpty && y.isEmpty) {
          c = 0;
        } else if (x.isEmpty) {
          c = 1;
        } else if (y.isEmpty) {
          c = -1;
        } else {
          c = x.toLowerCase().compareTo(y.toLowerCase());
        }
        return _desc ? -c : c;
      }
      final x = (a[_sortKey] as num?) ?? 0;
      final y = (b[_sortKey] as num?) ?? 0;
      c = x.compareTo(y);
      return _desc ? -c : c;
    });
    return rows;
  }

  /// Név felvitele / módosítása egy mezszámhoz.
  Future<void> _editName(Map<String, dynamic> p) async {
    final team = _team;
    if (team == null) return;
    final jersey = (p["jersey"] as num?)?.toInt() ?? 0;
    final ctrl = TextEditingController(text: (p["name"] as String?) ?? "");
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text("#$jersey neve"),
        content: SizedBox(
          width: 320,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
              controller: ctrl,
              autofocus: true,
              style: AppText.value.copyWith(fontSize: 14),
              decoration: const InputDecoration(
                  hintText: "pl. Kovács Bence",
                  border: OutlineInputBorder()),
              onSubmitted: (_) => Navigator.pop(ctx, true),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
                "A név a CSAPATHOZ és a mezszámhoz tartozik, nem egy "
                "meccshez: minden korábbi és későbbi meccsen is "
                "látszik. Üresen hagyva törlöd.",
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
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Mentés"),
          ),
        ],
      ),
    );
    final nev = ctrl.text.trim();
    ctrl.dispose();
    if (ok != true || !mounted) return;
    try {
      await _api.setPlayerName(team, jersey, nev);
      if (!mounted) return;
      // A helyi sor azonnal frissül — ne kelljen újratölteni az egész
      // keretet egy név miatt.
      setState(() => p["name"] = nev.isEmpty ? null : nev);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("A név mentése nem sikerült: "
              "${humanError(e)}")));
    }
  }

  void _sortBy(String key) {
    setState(() {
      if (_sortKey == key) {
        _desc = !_desc;
      } else {
        _sortKey = key;
        // Teljesítmény-oszlopnál a nagy szám érdekes elöl; a mezszám és
        // a név viszont névsor-szerű, ott a növekvő a természetes.
        _desc = key != "jersey" && key != "name";
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.roster,
      crumbPath: "CSAPAT · KERET",
      child: _loading
          ? const WaitingView("Meccs-könyvtár olvasása…",
              icon: Icons.groups_outlined)
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Keret", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "a csapat minden mezszáma egy táblában — koppints egy "
                  "sorra a játékos fejlődés-görbéjéhez",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              if (_teams.isEmpty)
                Text(
                    "Még nincs elemzett meccs — előbb dolgozz fel egy "
                    "videót az Új elemzés menüben.",
                    style: AppText.label)
              else ...[
                _teamPicker(),
                const SizedBox(height: AppSpacing.md),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: Text(_error!,
                        style:
                            AppText.label.copyWith(color: AppColors.away)),
                  ),
                if (_rowsLoading)
                  const Expanded(
                      child: WaitingView("Keret összeállítása…",
                          hint: "Minden tárolt meccset átnézünk.",
                          icon: Icons.groups_outlined))
                else if (_players.isEmpty)
                  Expanded(
                    child: Text(
                        _note.isNotEmpty
                            ? _note
                            : "Ebben a csapatban egyetlen mezszám sincs "
                                "kiosztva.",
                        style: AppText.label),
                  )
                else ...[
                  Expanded(child: _table()),
                  const SizedBox(height: AppSpacing.sm),
                  Text(_note, style: AppText.label.copyWith(fontSize: 11.5)),
                ],
              ],
            ]),
    );
  }

  Widget _teamPicker() {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text("CSAPAT", style: AppText.sectionLabel),
      const SizedBox(width: AppSpacing.sm),
      DropdownButton<String>(
        value: _team,
        dropdownColor: AppColors.surface,
        style: AppText.value.copyWith(fontSize: 13),
        items: [
          for (final t in _teams) DropdownMenuItem(value: t, child: Text(t)),
        ],
        onChanged: _rowsLoading
            ? null
            : (v) {
                setState(() => _team = v);
                _loadRoster();
                _loadFocus();
              },
      ),
      const SizedBox(width: AppSpacing.md),
      // Szezon-kimutatás Excelbe: "küldd el, ki hány gólnál jár" — a
      // hét végi vezetőségi feladat. Eddig a képernyőről kellett
      // kimásolni.
      OutlinedButton.icon(
        onPressed: _team == null ? null : _exportCsv,
        icon: const Icon(Icons.table_view_outlined, size: 16),
        label: const Text("Kimutatás (CSV)"),
      ),
    ]);
  }

  /// A keret-tábla mentése CSV-be. Ugyanabból a számolásból él, mint a
  /// képernyő (a backend közös útján) — a kimutatás nem tarthat szét
  /// attól, amit az edző lát.
  Future<void> _exportCsv() async {
    final team = _team;
    if (team == null) return;
    try {
      final bytes = await _api.fetchTeamRosterCsv(team);
      if (!mounted) return;
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Szezon-kimutatás mentése (CSV)",
        fileName: "szezon_$team.csv".replaceAll(
            RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ.-]+"), "_"),
        type: FileType.custom,
        allowedExtensions: const ["csv"],
      );
      if (path == null) return;
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Kimutatás mentve: $path — Excelben nyitható.")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Nem sikerült a kimutatás: ${humanError(e)}")));
    }
  }

  Widget _table() {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _headerRow(),
      const SizedBox(height: AppSpacing.xs),
      Expanded(
        child: ListView.builder(
          itemCount: _sorted.length,
          itemBuilder: (_, i) => _row(_sorted[i]),
        ),
      ),
    ]);
  }

  Widget _cell(String text, {bool header = false, int flex = 1}) {
    return Expanded(
      flex: flex,
      child: Text(text,
          textAlign: TextAlign.right,
          overflow: TextOverflow.ellipsis,
          style: header
              ? AppText.sectionLabel
              : AppText.value.copyWith(fontSize: 13)),
    );
  }

  Widget _headerRow() {
    Widget head(String key, String label, {int flex = 1}) {
      final on = _sortKey == key;
      return Expanded(
        flex: flex,
        child: InkWell(
          onTap: () => _sortBy(key),
          child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
            Flexible(
              child: Text(label,
                  textAlign: TextAlign.right,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.sectionLabel.copyWith(
                      color:
                          on ? AppColors.accent : AppColors.textSecondary)),
            ),
            if (on)
              Icon(_desc ? Icons.arrow_drop_down : Icons.arrow_drop_up,
                  size: 16, color: AppColors.accent),
          ]),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      child: Row(children: [
        head("jersey", "MEZ", flex: 2),
        head("name", "NÉV", flex: 4),
        for (final (key, label) in kRosterColumns)
          head(key, label.toUpperCase()),
        SizedBox(
          width: 34,
          child: Tooltip(
            message: "Gyakorolnivaló az egyéni edzés-tervből",
            child: Text("EDZ",
                textAlign: TextAlign.right,
                style: AppText.sectionLabel),
          ),
        ),
      ]),
    );
  }

  Widget _row(Map<String, dynamic> p) {
    final jersey = (p["jersey"] as num?)?.toInt() ?? 0;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.xs),
      child: InkWell(
        onTap: () {
          final team = _team;
          if (team == null) return;
          Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => PlayerTrendScreen(
              teams: _teams,
              initialTeam: team,
              initialJersey: jersey,
            ),
          ));
        },
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md, vertical: AppSpacing.sm),
          decoration: AppTheme.card(),
          child: Row(children: [
            Expanded(
              flex: 2,
              child: Row(children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceAlt,
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: AppColors.borderStrong),
                  ),
                  child: Text("#$jersey",
                      style: AppText.value.copyWith(fontSize: 13)),
                ),
              ]),
            ),
            Expanded(
              flex: 4,
              child: Row(children: [
                Flexible(
                  child: Text(
                      (p["name"] as String?)?.isNotEmpty == true
                          ? p["name"] as String
                          : "névtelen",
                      overflow: TextOverflow.ellipsis,
                      style: AppText.value.copyWith(
                          fontSize: 13,
                          color: (p["name"] as String?)?.isNotEmpty == true
                              ? AppColors.textPrimary
                              : AppColors.textFaint)),
                ),
                IconButton(
                  tooltip: "Név megadása",
                  iconSize: 15,
                  visualDensity: VisualDensity.compact,
                  constraints: const BoxConstraints(),
                  padding: const EdgeInsets.only(left: 6),
                  icon: const Icon(Icons.edit_outlined,
                      color: AppColors.textFaint),
                  onPressed: () => _editName(p),
                ),
              ]),
            ),
            for (final (key, _) in kRosterColumns)
              _cell("${(p[key] as num?)?.toInt() ?? 0}"),
            // Gyakorolnivaló: hány tétel áll a nevén az egyéni
            // edzés-tervben. A sorra koppintva a görbéjén ott a
            // részletes "Mit gyakorolj".
            SizedBox(
              width: 34,
              // Üres cella, ha nincs gyakorolnivaló — táblázatban ez a
              // helyes "semmi": a sor többi száma hordozza a jelentést.
              child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    if ((_focusCount[jersey] ?? 0) > 0) ...[
                      const Icon(Icons.fitness_center,
                          size: 13, color: AppColors.gold),
                      const SizedBox(width: 3),
                      Text("${_focusCount[jersey]}",
                          style: AppText.value.copyWith(
                              fontSize: 12, color: AppColors.gold)),
                    ],
                  ]),
            ),
          ]),
        ),
      ),
    );
  }
}
