/// Alkalmazás-shell — a MUNKAFOLYAMAT szerint csoportosított navigáció.
///
/// A menü az edző munkarendjét követi, nem a fejlesztését:
///   MUNKAFOLYAMAT: Kezdőlap → Új elemzés → Feldolgozások → Élő követés
///   ELEMZÉS:       Meccs-elemző · Ellenfél-felderítés · Meccsterv ·
///                  Figura-tervező
///   CSAPAT:        Edzésterv · Szezon · Játékos-fejlődés
/// Minden eszköz a menüből érhető el (nem képernyők mélyéről), a kijelölés
/// mindig mutatja, hol jársz. Gyors váltás billentyűzetről: Cmd/Ctrl+1..9
/// és Cmd/Ctrl+0 a tizedik elemre.
///
/// A CSAPAT csoport azért külön: az edzésterv, a szezon-toplisták és a
/// játékos-fejlődés nem EGY meccsről szól, hanem a csapat egészéről — és
/// eddig mindhárom a kezdőlap, illetve egy meccs mélyén lakott, tehát aki
/// nem görgetett odáig, nem is tudott róluk.
/// Szűk nézetben a sáv keskeny, rámutatásra kinyílik a feliratokkal.
library;

import "package:flutter/material.dart";
import "package:flutter/services.dart";

import "../../services/api_client.dart";
import "../../services/jobs_monitor.dart";
import "../../services/session_store.dart";
import "../../sim/demo_data.dart";
import "../../theme/app_theme.dart";
import "../../version.dart";
import "../account_gate.dart";
import "../dashboard_screen.dart";
import "../designer_screen.dart";
import "../error_text.dart";
import "../jobs_screen.dart";
import "../live_screen.dart";
import "../match_screen.dart";
import "../matchup_screen.dart";
import "../player_trend_screen.dart";
import "../scouting_picker_screen.dart";
import "../season_screen.dart";
import "../terms_screen.dart";
import "../training_plan_screen.dart";
import "../upload_screen.dart";

/// A navigáció elemei. (A `matches` a meccs-elemző: menüből demóval nyílik,
/// a könyvtárból a kiválasztott meccsel — a kijelölés ilyenkor is ezt jelöli.)
enum NavId {
  dashboard, upload, jobs, live, matches, scouting, matchup, designer,
  training, season, playerTrend
}

/// A menü csoportjai és elemei — EGY helyen, a sáv és a billentyű-kiosztás
/// is ebből épül (a sorrend adja a Cmd/Ctrl+1..N kiosztást).
const List<(String, List<(NavId, IconData, String)>)> kNavGroups = [
  ("MUNKAFOLYAMAT", [
    (NavId.dashboard, Icons.home_outlined, "Kezdőlap"),
    (NavId.upload, Icons.add_circle_outline, "Új elemzés"),
    (NavId.jobs, Icons.hourglass_bottom, "Feldolgozások"),
    (NavId.live, Icons.sensors, "Élő követés"),
  ]),
  ("ELEMZÉS", [
    (NavId.matches, Icons.play_circle_outline, "Meccs-elemző"),
    (NavId.scouting, Icons.travel_explore, "Ellenfél-felderítés"),
    (NavId.matchup, Icons.fact_check_outlined, "Meccsterv"),
    (NavId.designer, Icons.edit_outlined, "Figura-tervező"),
  ]),
  ("CSAPAT", [
    (NavId.training, Icons.fitness_center, "Edzésterv"),
    (NavId.season, Icons.calendar_month_outlined, "Szezon"),
    (NavId.playerTrend, Icons.timeline, "Játékos-fejlődés"),
  ]),
];

/// Átnavigál a kiválasztott képernyőre. Minden elem ugyanúgy működik
/// (csere-navigáció) — nincs "eldugott" képernyő és nincs visszagomb-káosz.
void navTo(BuildContext context, NavId id) {
  final Widget page = switch (id) {
    NavId.dashboard => const DashboardScreen(),
    NavId.upload => const UploadScreen(),
    NavId.jobs => const JobsScreen(),
    NavId.live => const LiveScreen(),
    NavId.matches => const MatchScreen(),
    NavId.scouting => const ScoutingPickerScreen(),
    NavId.matchup => const MatchupScreen(),
    NavId.designer => DesignerScreen(match: buildDemoMatch()),
    NavId.training => const TrainingPlanScreen(),
    NavId.season => const SeasonScreen(),
    NavId.playerTrend => const PlayerTrendScreen(),
  };
  Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => page));
}

/// A gyorsbillentyűk EGY helyen — a súgó minden képernyőről nyílik
/// (felső sáv billentyű-ikonja, illetve ? vagy F1).
///
/// Miért itt: eddig csak a meccs-elemzőben létezett egy lista, és az
/// app-szintű navigációs billentyűket nem is említette. Két külön lista
/// előbb-utóbb széttart; ez a közös.
const List<(String, List<(String, String)>)> kShortcutGroups = [
  ("Bárhol", [
    ("Cmd/Ctrl + 1..9, 0",
     "váltás a menü első tíz eleme közt (a menü sorrendjében; a 0 a "
     "tizedik) — a további elemek egérrel érhetők el"),
    ("? vagy F1", "ez a súgó"),
  ]),
  ("Meccs-elemzőben", [
    ("Szóköz", "lejátszás / szünet"),
    ("← / →", "1 képkocka vissza / előre"),
    ("Shift + ← / →", "5 másodperc vissza / előre"),
    ("Q / E  vagy  ↑ / ↓",
     "előző / következő ugrópont az aktív szűrő szerint"),
  ]),
];

/// A gyorsbillentyű-súgó megnyitása (bárhonnan).
void showShortcutHelp(BuildContext context) {
  showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      backgroundColor: AppColors.surface,
      title: const Text("Gyorsbillentyűk"),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final (group, rows) in kShortcutGroups) ...[
              Padding(
                padding: const EdgeInsets.only(
                    top: AppSpacing.sm, bottom: 4),
                child: Text(group.toUpperCase(),
                    style: AppText.sectionLabel),
              ),
              for (final (key, what) in rows)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(children: [
                    Container(
                      width: 150,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceAlt,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: AppColors.borderStrong),
                      ),
                      child: Text(key,
                          style: AppText.value.copyWith(fontSize: 12)),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                        child: Text(what,
                            style: AppText.label.copyWith(
                                fontSize: 12.5,
                                color: AppColors.textPrimary))),
                  ]),
                ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text("Bezárás")),
      ],
    ),
  );
}

/// A shell keret: felső sáv + sidebar + tartalom.
class AppShell extends StatelessWidget {
  final NavId active;
  // A korábbi fejlesztői címke (pl. "1b") — már nem jelenik meg, a hívók
  // kompatibilitása miatt marad a paraméter.
  final String crumbTag;
  final String crumbPath; // pl. "DASHBOARD · MECCSEK ÁTTEKINTÉSE"
  final bool collapsed;   // keskeny sáv (rámutatásra kinyílik)
  final Widget child;

  const AppShell({
    super.key,
    required this.active,
    this.crumbTag = "",
    this.crumbPath = "",
    required this.child,
    this.collapsed = false,
  });

  @override
  Widget build(BuildContext context) {
    // Gyors navigáció: Cmd/Ctrl + 1..N a menü sorrendjében.
    final items = [for (final (_, group) in kNavGroups) ...group];
    const digits = [
      LogicalKeyboardKey.digit1, LogicalKeyboardKey.digit2,
      LogicalKeyboardKey.digit3, LogicalKeyboardKey.digit4,
      LogicalKeyboardKey.digit5, LogicalKeyboardKey.digit6,
      LogicalKeyboardKey.digit7, LogicalKeyboardKey.digit8,
      LogicalKeyboardKey.digit9,
      // A tizedik menüpont a 0-ra esik (a számsor végén) — így a
      // billentyű-kiosztás nem szakad meg a menü bővülésekor.
      LogicalKeyboardKey.digit0,
    ];
    final bindings = <ShortcutActivator, VoidCallback>{};
    for (var i = 0; i < items.length && i < digits.length; i++) {
      void go() {
        if (items[i].$1 != active) navTo(context, items[i].$1);
      }
      bindings[SingleActivator(digits[i], meta: true)] = go;    // macOS
      bindings[SingleActivator(digits[i], control: true)] = go; // Win/Linux
    }
    // A súgó mindenhonnan elérhető, ne csak a meccs-elemzőből.
    void help() => showShortcutHelp(context);
    bindings[const SingleActivator(LogicalKeyboardKey.f1)] = help;
    bindings[const SingleActivator(LogicalKeyboardKey.slash, shift: true)] =
        help;
    return Scaffold(
      body: SafeArea(
        child: CallbackShortcuts(
          bindings: bindings,
          child: Focus(
            autofocus: false,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _TopBar(active: active, path: crumbPath),
                // "Kész!" bejelentés BÁRHOL: a burok minden képernyőn
                // ott van, tehát a percekig futó feldolgozás vége akkor
                // is megtalálja a felhasználót, ha közben máshol dolgozik.
                const _FinishedBanner(),
                Expanded(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _SideNav(active: active, collapsed: collapsed),
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(
                              AppSpacing.xl, AppSpacing.lg,
                              AppSpacing.xl, AppSpacing.xl),
                          child: child,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// "Kész!" — a most befejeződött feldolgozás bejelentése, bárhonnan.
///
/// A feldolgozás percekig fut, a felhasználó közben más képernyőn
/// dolgozik (vagy egészen máshol jár a gép mellől). Eddig CSAK úgy
/// tudta meg, hogy kész, ha visszament megnézni: a menü-jelvény
/// eltűnése néma. Ez a sáv szól neki — és rögtön ad egy gombot a
/// leggyakoribb következő lépésre (a kész meccs megnyitása), illetve
/// hiba esetén a részletekre.
///
/// Egyszer szól, aztán elrejthető: nem az a dolga, hogy ott maradjon.
class _FinishedBanner extends StatelessWidget {
  const _FinishedBanner();

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Map<String, dynamic>?>(
      valueListenable: JobsMonitor.instance.lastFinished,
      builder: (context, job, _) {
        if (job == null) return const SizedBox.shrink();
        final status = (job["status"] as String?) ?? "";
        final hiba = status != "done" && status != "finished";
        final matchId = job["match_id"] as String?;
        final err = (job["error"] as String?) ?? "";
        final szin = hiba ? AppColors.away : AppColors.accent;
        return Padding(
          padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl, 0, AppSpacing.xl, AppSpacing.md),
          child: Container(
            decoration: BoxDecoration(
              color: szin.withOpacity(0.10),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: szin.withOpacity(0.45)),
            ),
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg, vertical: AppSpacing.md),
            child: Row(children: [
              Icon(hiba ? Icons.error_outline : Icons.check_circle_outline,
                  size: 18, color: szin),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(
                    hiba
                        ? (err.isNotEmpty
                            ? "A feldolgozás megállt: $err"
                            : "A feldolgozás hibával állt meg.")
                        : "Kész a feldolgozás"
                            "${matchId != null ? " — $matchId" : ""}.",
                    style: AppText.value.copyWith(fontSize: 13),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis),
              ),
              const SizedBox(width: AppSpacing.md),
              if (!hiba && matchId != null)
                OutlinedButton.icon(
                  onPressed: () {
                    JobsMonitor.instance.dismissFinished();
                    Navigator.of(context).pushReplacement(MaterialPageRoute(
                        builder: (_) => MatchScreen(matchId: matchId)));
                  },
                  style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.accent,
                      side: const BorderSide(color: AppColors.accent)),
                  icon: const Icon(Icons.play_circle_outline, size: 16),
                  label: const Text("Megnyitás"),
                )
              else
                OutlinedButton.icon(
                  onPressed: () {
                    JobsMonitor.instance.dismissFinished();
                    navTo(context, NavId.jobs);
                  },
                  style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.away,
                      side: const BorderSide(color: AppColors.away)),
                  icon: const Icon(Icons.list_alt, size: 16),
                  label: const Text("Részletek"),
                ),
              IconButton(
                tooltip: "Elrejtés",
                onPressed: JobsMonitor.instance.dismissFinished,
                icon: const Icon(Icons.close,
                    size: 16, color: AppColors.textFaint),
              ),
            ]),
          ),
        );
      },
    );
  }
}

/// Felső sáv: hol vagyok (szekció → képernyő), fejlesztői címkék nélkül.
class _TopBar extends StatelessWidget {
  final NavId active;
  final String path;
  const _TopBar({required this.active, required this.path});

  @override
  Widget build(BuildContext context) {
    // A szekció + elem neve a menü-definícióból (a címke mindig egyezik
    // a sidebar feliratával); a hívó `crumbPath`-ja finomít, ha van.
    String section = "";
    String label = "";
    for (final (groupName, group) in kNavGroups) {
      for (final (id, _, itemLabel) in group) {
        if (id == active) {
          section = groupName;
          label = itemLabel;
        }
      }
    }
    // A képernyő al-címe (pl. "PÁLYA-KALIBRÁCIÓ") a crumbPath-ból, ha
    // többet mond, mint a menü-címke.
    final sub = path.contains("·") ? path.split("·").last.trim() : "";
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.md),
      child: Row(
        children: [
          Text(section,
              style: AppText.label.copyWith(
                  fontSize: 10.5, letterSpacing: 1.2,
                  color: AppColors.textFaint)),
          if (section.isNotEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: Icon(Icons.chevron_right, size: 14,
                  color: AppColors.textFaint),
            ),
          Text(label.toUpperCase(), style: AppText.crumb),
          if (sub.isNotEmpty && sub.toUpperCase() != label.toUpperCase()) ...[
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: Icon(Icons.chevron_right, size: 14,
                  color: AppColors.textFaint),
            ),
            Text(sub, style: AppText.crumb.copyWith(
                color: AppColors.textSecondary)),
          ],
          const Spacer(),
          // Eddig ez csak egy tooltipes ikon volt — kattintani lehetett
          // rajta, csak nem történt semmi. Most megnyitja a súgót.
          IconButton(
            onPressed: () => showShortcutHelp(context),
            tooltip: "Gyorsbillentyűk (? vagy F1)",
            iconSize: 16,
            splashRadius: 16,
            icon: const Icon(Icons.keyboard_outlined,
                color: AppColors.textFaint),
          ),
          // Fiók: ki van belépve, a feltételek megnyitása és a kilépés.
          const _AccountMenu(),
        ],
      ),
    );
  }
}

/// Fiók-menü a felső sávban: a belépett fiók, a felhasználási feltételek
/// és a kilépés. A kilépés a munkamenet-kulcsot a motoron ÉS a gépen is
/// érvényteleníti, és visszavisz a belépő képernyőre.
class _AccountMenu extends StatefulWidget {
  const _AccountMenu();

  @override
  State<_AccountMenu> createState() => _AccountMenuState();
}

class _AccountMenuState extends State<_AccountMenu> {
  Map<String, dynamic>? _me;

  @override
  void initState() {
    super.initState();
    _load();
    // A feldolgozás-figyelő minden képernyőn fut (a burok mindenhol ott
    // van), így a menü jelvénye BÁRHOL mutatja, hány elemzés dolgozik —
    // ez teszi visszatalálhatóvá a futó munkát.
    JobsMonitor.instance.start();
  }

  Future<void> _load() async {
    final me = await ApiClient().fetchMe();
    if (!mounted) return;
    setState(() => _me = me);
  }

  /// Jelszócsere-párbeszéd: a régi jelszó megadásával — a csere minden
  /// korábbi munkamenetet érvénytelenít, de az ittenit a motor új
  /// kulccsal pótolja, tehát a felhasználó bent marad.
  Future<void> _changePassword() async {
    final oldCtrl = TextEditingController();
    final newCtrl = TextEditingController();
    String? error;
    var busy = false;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlg) => AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text("Jelszócsere"),
          content: SizedBox(
            width: 380,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: oldCtrl,
                  obscureText: true,
                  decoration:
                      const InputDecoration(labelText: "Jelenlegi jelszó"),
                ),
                const SizedBox(height: AppSpacing.md),
                TextField(
                  controller: newCtrl,
                  obscureText: true,
                  decoration: const InputDecoration(
                      labelText: "Új jelszó (legalább 8 karakter)"),
                ),
                if (error != null) ...[
                  const SizedBox(height: AppSpacing.md),
                  Text(error!,
                      style: AppText.label.copyWith(color: AppColors.away)),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: busy ? null : () => Navigator.of(ctx).pop(false),
              child: const Text("Mégse"),
            ),
            FilledButton(
              onPressed: busy
                  ? null
                  : () async {
                      setDlg(() {
                        busy = true;
                        error = null;
                      });
                      try {
                        await ApiClient()
                            .changePassword(oldCtrl.text, newCtrl.text);
                        if (ctx.mounted) Navigator.of(ctx).pop(true);
                      } catch (e) {
                        setDlg(() {
                          busy = false;
                          error = humanError(e);
                        });
                      }
                    },
              style: FilledButton.styleFrom(
                  backgroundColor: AppColors.accent,
                  foregroundColor: AppColors.onAccent),
              child: const Text("Csere"),
            ),
          ],
        ),
      ),
    );
    oldCtrl.dispose();
    newCtrl.dispose();
    if (ok == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text("A jelszó lecserélve — a többi gépen/ablakban "
              "nyitott belépések érvénytelenek lettek.")));
    }
  }

  Future<void> _logout() async {
    await ApiClient().logoutAccount();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const AccountGate()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final me = _me;
    final who = me == null
        ? (SessionStore.guestMode ? "Vendég-munkamenet" : "Nincs bejelentkezve")
        : ((me["name"] as String?)?.isNotEmpty == true
            ? me["name"] as String
            : me["email"] as String? ?? "Fiók");
    return PopupMenuButton<String>(
      tooltip: "Fiók",
      iconSize: 16,
      splashRadius: 16,
      color: AppColors.surface,
      icon: const Icon(Icons.account_circle_outlined,
          color: AppColors.textFaint),
      onSelected: (v) {
        if (v == "logout") {
          _logout();
        } else if (v == "login") {
          // Vendégből fiókba: a kapu belépője jön; sikeres belépésnél a
          // vendég-munkamenet lezárul, és a munka MEGMARAD (a kapu
          // intézi).
          Navigator.of(context).pushReplacement(MaterialPageRoute(
              builder: (_) =>
                  const AccountGate(preserveGuestWork: true)));
        } else if (v == "devmode") {
          // Fejlesztői mód: a vendég-munkamenet munkája az app
          // bezárásakor is megmarad. Fejlesztési fázisra való.
          SessionStore.setDevMode(!SessionStore.devMode)
              .then((_) => mounted ? setState(() {}) : null);
        } else if (v == "terms") {
          Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => const TermsScreen(readOnly: true),
          ));
        } else if (v == "password") {
          _changePassword();
        }
      },
      itemBuilder: (_) => [
        PopupMenuItem<String>(
          enabled: false,
          child: Text(who, style: AppText.label),
        ),
        const PopupMenuDivider(),
        const PopupMenuItem<String>(
          value: "terms",
          child: Text("Felhasználási feltételek", style: AppText.value),
        ),
        if (me == null)
          const PopupMenuItem<String>(
            value: "login",
            child: Text("Belépés / fiók létrehozása", style: AppText.value),
          ),
        if (me != null)
          const PopupMenuItem<String>(
            value: "password",
            child: Text("Jelszócsere", style: AppText.value),
          ),
        if (me != null)
          const PopupMenuItem<String>(
            value: "logout",
            child: Text("Kilépés a fiókból", style: AppText.value),
          ),
        PopupMenuItem<String>(
          value: "devmode",
          child: Text(
              SessionStore.devMode
                  ? "Fejlesztői mód: BE (vendég-munka megmarad)"
                  : "Fejlesztői mód: KI (vendég-munka elvész)",
              style: AppText.value),
        ),
      ],
    );
  }
}

/// Bal oldali navigáció — feliratos elemek, hover-kiemelés, kitöltött
/// kijelölés; `collapsed` esetén keskeny, rámutatásra kinyílik.
class _SideNav extends StatefulWidget {
  final NavId active;
  final bool collapsed;
  const _SideNav({required this.active, required this.collapsed});

  @override
  State<_SideNav> createState() => _SideNavState();
}

class _SideNavState extends State<_SideNav> {
  bool _hover = false;

  bool get _open => !widget.collapsed || _hover;

  @override
  Widget build(BuildContext context) {
    var shortcut = 0;
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        width: _open ? 224.0 : 64.0,
        margin: const EdgeInsets.only(left: AppSpacing.xl, bottom: AppSpacing.xl),
        decoration: AppTheme.card(color: AppColors.bgSidebar),
        padding: EdgeInsets.symmetric(
            horizontal: _open ? 12 : 8, vertical: AppSpacing.lg),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _brand(),
            const SizedBox(height: AppSpacing.xl),
            for (final (groupName, group) in kNavGroups) ...[
              _sectionLabel(groupName),
              for (final (id, icon, label) in group)
                _NavItem(
                  id: id,
                  icon: icon,
                  label: label,
                  shortcut: ++shortcut,
                  selected: id == widget.active,
                  open: _open,
                  live: id == NavId.live,
                  // A futó feldolgozások száma BÁRHONNAN látszik: ez
                  // teszi visszatalálhatóvá az elemzést, ha a
                  // felhasználó közben mást néz az appban.
                  badge: id == NavId.jobs,
                ),
              const SizedBox(height: AppSpacing.lg),
            ],
            const Spacer(),
            if (_open)
              Padding(
                padding: const EdgeInsets.only(left: 6, top: 4),
                child: Text("SPORT MACHINE · v$appVersion",
                    style: AppText.label.copyWith(
                        fontSize: 9.5, letterSpacing: 1.2,
                        color: AppColors.textFaint)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _brand() {
    final logo = Container(
      width: 34, height: 34,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
            colors: [AppColors.accent, Color(0xFF1B8F82)]),
        borderRadius: BorderRadius.circular(10),
        // Puha márka-ragyogás — összhangban a belépő képernyő logójával.
        boxShadow: [
          BoxShadow(
              color: AppColors.accent.withOpacity(0.30),
              blurRadius: 18,
              offset: const Offset(0, 4)),
        ],
      ),
      child: const Icon(Icons.change_history_rounded,
          color: AppColors.onAccent, size: 18),
    );
    if (!_open) return Center(child: logo);
    return Row(children: [
      logo,
      const SizedBox(width: AppSpacing.md),
      const Expanded(
          child: Text("SPORT MACHINE",
              style: AppText.brand, overflow: TextOverflow.ellipsis)),
    ]);
  }

  Widget _sectionLabel(String t) => AnimatedOpacity(
        duration: const Duration(milliseconds: 150),
        opacity: _open ? 1 : 0,
        child: SizedBox(
          height: 22,
          child: _open
              ? Padding(
                  padding: const EdgeInsets.only(left: 6, top: 2),
                  child: Text(t, style: AppText.sectionLabel),
                )
              : null,
        ),
      );
}

/// Egyetlen menüelem: hover-kiemelés, kijelölve kitöltött accent-"pill";
/// nyitott sávban a billentyű-gyorsító is látszik (⌘1 stílusban).
class _NavItem extends StatefulWidget {
  final NavId id;
  final IconData icon;
  final String label;
  final int shortcut; // 1-től; 0 = nincs
  final bool selected;
  final bool open;
  final bool live;

  /// Mutasson-e ÉLŐ darabszám-jelvényt a futó feldolgozásokról.
  final bool badge;

  const _NavItem({
    required this.id,
    required this.icon,
    required this.label,
    required this.shortcut,
    required this.selected,
    required this.open,
    this.live = false,
    this.badge = false,
  });

  @override
  State<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends State<_NavItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final w = widget;
    final Color bg = w.selected
        ? AppColors.accent
        : _hover
            ? AppColors.surfaceAlt
            : Colors.transparent;
    final Color fg = w.selected
        ? AppColors.onAccent
        : _hover
            ? AppColors.textPrimary
            : AppColors.textSecondary;
    final Color ic = w.selected
        ? AppColors.onAccent
        : _hover
            ? AppColors.accent
            : AppColors.textFaint;

    final row = Row(
      mainAxisAlignment:
          w.open ? MainAxisAlignment.start : MainAxisAlignment.center,
      children: [
        Icon(w.icon, size: 18, color: ic),
        if (w.open) ...[
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              w.label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: fg,
                fontWeight: w.selected ? FontWeight.w600 : FontWeight.w500,
                fontSize: 13.5,
              ),
            ),
          ),
          if (w.live) const _RedDot(),
          if (w.badge) const _JobsBadge(),
          if (!w.live && w.shortcut > 0 && (_hover || w.selected))
            Text("⌘${w.shortcut}",
                style: TextStyle(
                    fontSize: 10.5,
                    color: w.selected
                        ? AppColors.onAccent.withOpacity(0.7)
                        : AppColors.textFaint)),
        ] else if (w.live)
          const Padding(
              padding: EdgeInsets.only(left: 2), child: _RedDot())
        else if (w.badge)
          const Padding(
              padding: EdgeInsets.only(left: 2), child: _JobsBadge()),
      ],
    );

    final item = MouseRegion(
      cursor: w.selected ? MouseCursor.defer : SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: w.selected ? null : () => navTo(context, w.id),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          curve: Curves.easeOut,
          margin: const EdgeInsets.symmetric(vertical: 2),
          padding:
              EdgeInsets.symmetric(horizontal: w.open ? 10 : 0, vertical: 9),
          // A kijelölt elem "világító pill": enyhe színátmenet + puha
          // akcentus-ragyogás — a szem egyből tudja, hol van.
          decoration: BoxDecoration(
            color: w.selected ? null : bg,
            gradient: w.selected
                ? const LinearGradient(
                    colors: [AppColors.accent, Color(0xFF25BFAC)])
                : null,
            borderRadius: BorderRadius.circular(8),
            boxShadow: w.selected
                ? [
                    BoxShadow(
                        color: AppColors.accent.withOpacity(0.28),
                        blurRadius: 14,
                        offset: const Offset(0, 3)),
                  ]
                : const [],
          ),
          child: row,
        ),
      ),
    );

    return w.open
        ? item
        : Tooltip(
            message: w.shortcut > 0
                ? "${w.label} (Cmd/Ctrl+${w.shortcut})"
                : w.label,
            child: item);
  }
}

/// A futó feldolgozások száma a menüponton — ÉLŐ.
///
/// Ez a kis szám a lényeg: egy meccs feldolgozása percekig fut, és
/// eddig a haladás csak a kezdőlapon látszott. Aki közben átment másik
/// képernyőre, elvesztette szem elől, és nem volt hová visszamennie.
/// Innen egy kattintás a Feldolgozások lap.
class _JobsBadge extends StatelessWidget {
  const _JobsBadge();

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<List<Map<String, dynamic>>>(
      valueListenable: JobsMonitor.instance.jobs,
      builder: (context, jobs, _) {
        final n = jobs.where(JobsMonitor.isActive).length;
        if (n == 0) return const SizedBox.shrink();
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
          decoration: BoxDecoration(
            color: AppColors.accent,
            borderRadius: BorderRadius.circular(9),
          ),
          child: Text("$n",
              style: const TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.w700,
                  color: AppColors.onAccent)),
        );
      },
    );
  }
}

class _RedDot extends StatelessWidget {
  const _RedDot();
  @override
  Widget build(BuildContext context) => Container(
      width: 8, height: 8,
      decoration:
          const BoxDecoration(color: AppColors.away, shape: BoxShape.circle));
}
