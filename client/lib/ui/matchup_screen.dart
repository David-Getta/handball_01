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

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
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
    });
    try {
      final r = await _api.fetchMatchup(_itemsOf(own), _itemsOf(opp));
      if (!mounted) return;
      setState(() {
        _result = r;
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
    return ListView(children: [
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
      const SizedBox(height: AppSpacing.lg),
      Text("STÍLUS", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      _styleCard(style),
    ]);
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
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(children: [
                Expanded(
                    child: Text("${(row as Map)["axis"]}",
                        style: AppText.label.copyWith(fontSize: 12))),
                Text("mi ${(row)["own"]} · ők ${(row)["opp"]}",
                    style: AppText.value.copyWith(fontSize: 12)),
              ]),
            ),
        ],
      ]),
    );
  }
}
