/// Alkalmazás-shell — a MUNKAFOLYAMAT szerint csoportosított navigáció.
///
/// A menü az edző munkarendjét követi, nem a fejlesztését:
///   MUNKAFOLYAMAT: Kezdőlap → Új elemzés → Élő követés
///   ELEMZÉS:       Meccs-elemző · Ellenfél-felderítés · Játékos-fejlődés ·
///                  Figura-tervező
/// Minden eszköz a menüből érhető el (nem képernyők mélyéről), a kijelölés
/// mindig mutatja, hol jársz. Gyors váltás billentyűzetről: Cmd/Ctrl+1..7.
/// Szűk nézetben a sáv keskeny, rámutatásra kinyílik a feliratokkal.
library;

import "package:flutter/material.dart";
import "package:flutter/services.dart";

import "../../sim/demo_data.dart";
import "../../theme/app_theme.dart";
import "../../version.dart";
import "../dashboard_screen.dart";
import "../designer_screen.dart";
import "../live_screen.dart";
import "../match_screen.dart";
import "../player_trend_screen.dart";
import "../scouting_picker_screen.dart";
import "../upload_screen.dart";

/// A navigáció elemei. (A `matches` a meccs-elemző: menüből demóval nyílik,
/// a könyvtárból a kiválasztott meccsel — a kijelölés ilyenkor is ezt jelöli.)
enum NavId { dashboard, upload, live, matches, scouting, playerTrend, designer }

/// A menü csoportjai és elemei — EGY helyen, a sáv és a billentyű-kiosztás
/// is ebből épül (a sorrend adja a Cmd/Ctrl+1..N kiosztást).
const List<(String, List<(NavId, IconData, String)>)> kNavGroups = [
  ("MUNKAFOLYAMAT", [
    (NavId.dashboard, Icons.home_outlined, "Kezdőlap"),
    (NavId.upload, Icons.add_circle_outline, "Új elemzés"),
    (NavId.live, Icons.sensors, "Élő követés"),
  ]),
  ("ELEMZÉS", [
    (NavId.matches, Icons.play_circle_outline, "Meccs-elemző"),
    (NavId.scouting, Icons.travel_explore, "Ellenfél-felderítés"),
    (NavId.playerTrend, Icons.timeline, "Játékos-fejlődés"),
    (NavId.designer, Icons.edit_outlined, "Figura-tervező"),
  ]),
];

/// Átnavigál a kiválasztott képernyőre. Minden elem ugyanúgy működik
/// (csere-navigáció) — nincs "eldugott" képernyő és nincs visszagomb-káosz.
void navTo(BuildContext context, NavId id) {
  final Widget page = switch (id) {
    NavId.dashboard => const DashboardScreen(),
    NavId.upload => const UploadScreen(),
    NavId.live => const LiveScreen(),
    NavId.matches => const MatchScreen(),
    NavId.scouting => const ScoutingPickerScreen(),
    NavId.playerTrend => const PlayerTrendScreen(),
    NavId.designer => DesignerScreen(match: buildDemoMatch()),
  };
  Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => page));
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
    ];
    final bindings = <ShortcutActivator, VoidCallback>{};
    for (var i = 0; i < items.length && i < digits.length; i++) {
      void go() {
        if (items[i].$1 != active) navTo(context, items[i].$1);
      }
      bindings[SingleActivator(digits[i], meta: true)] = go;    // macOS
      bindings[SingleActivator(digits[i], control: true)] = go; // Win/Linux
    }
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
          Tooltip(
            message: "Gyors váltás: Cmd/Ctrl + 1..7",
            child: Icon(Icons.keyboard_outlined, size: 16,
                color: AppColors.textFaint),
          ),
        ],
      ),
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

  const _NavItem({
    required this.id,
    required this.icon,
    required this.label,
    required this.shortcut,
    required this.selected,
    required this.open,
    this.live = false,
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
          if (!w.live && w.shortcut > 0 && (_hover || w.selected))
            Text("⌘${w.shortcut}",
                style: TextStyle(
                    fontSize: 10.5,
                    color: w.selected
                        ? AppColors.onAccent.withOpacity(0.7)
                        : AppColors.textFaint)),
        ] else if (w.live)
          const Padding(
              padding: EdgeInsets.only(left: 2), child: _RedDot()),
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
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(8),
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

class _RedDot extends StatelessWidget {
  const _RedDot();
  @override
  Widget build(BuildContext context) => Container(
      width: 8, height: 8,
      decoration:
          const BoxDecoration(color: AppColors.away, shape: BoxShape.circle));
}
