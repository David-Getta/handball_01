/// Alkalmazás-shell — felső breadcrumb sáv + bal oldali navigáció + tartalom.
///
/// macOS-stílusú oldalsáv: mindig FELIRATOS elemek, finom hover-kiemelés,
/// a kijelölt elem kitöltött (accent) "pill" — mint a Finder/Notes sávja.
/// Szűk nézeteknél (collapsed) a sáv keskeny, de RÁMUTATÁSRA kinyílik a
/// feliratokkal (auto-hide viselkedés), így a menü mindig érthető marad.
library;

import "package:flutter/material.dart";

import "../../sim/demo_data.dart";
import "../../theme/app_theme.dart";
import "../dashboard_screen.dart";
import "../designer_screen.dart";
import "../live_screen.dart";
import "../match_screen.dart";
import "../upload_screen.dart";

/// A navigáció elemei.
enum NavId { dashboard, matches, live, designer, upload }

/// Átnavigál a kiválasztott képernyőre (a sidebarból).
void navTo(BuildContext context, NavId id) {
  Widget page;
  switch (id) {
    case NavId.dashboard:
      page = const DashboardScreen();
    case NavId.matches:
      page = const MatchScreen();
    case NavId.live:
      page = const LiveScreen();
    case NavId.upload:
      page = const UploadScreen();
    case NavId.designer:
      // A tervező saját, teljes képernyős felület — push-oljuk (működjön a vissza).
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => DesignerScreen(match: buildDemoMatch())));
      return;
  }
  Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => page));
}

/// A shell keret: felső sáv + sidebar + tartalom.
class AppShell extends StatelessWidget {
  final NavId active;
  final String crumbTag;      // pl. "1b"
  final String crumbPath;     // pl. "DASHBOARD · MECCSEK ÁTTEKINTÉSE"
  final bool collapsed;       // keskeny sáv (rámutatásra kinyílik)
  final Widget child;

  const AppShell({
    super.key,
    required this.active,
    required this.crumbTag,
    required this.crumbPath,
    required this.child,
    this.collapsed = false,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _TopBar(tag: crumbTag, path: crumbPath),
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _SideNav(active: active, collapsed: collapsed),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xl),
                      child: child,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  final String tag;
  final String path;
  const _TopBar({required this.tag, required this.path});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.md),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(color: AppColors.accent, borderRadius: BorderRadius.circular(8)),
            child: Text(tag, style: const TextStyle(color: AppColors.onAccent, fontWeight: FontWeight.w800, fontSize: 12)),
          ),
          const SizedBox(width: AppSpacing.lg),
          Text(path, style: AppText.crumb),
        ],
      ),
    );
  }
}

/// Bal oldali navigáció — macOS-stílus: feliratos elemek, hover-kiemelés,
/// kitöltött kijelölés. `collapsed` esetén keskeny, de rámutatásra kinyílik.
class _SideNav extends StatefulWidget {
  final NavId active;
  final bool collapsed;
  const _SideNav({required this.active, required this.collapsed});

  @override
  State<_SideNav> createState() => _SideNavState();
}

class _SideNavState extends State<_SideNav> {
  bool _hover = false;

  /// Nyitott-e a sáv (feliratokkal): normál nézetben mindig; keskeny
  /// nézetben rámutatásra nyílik ki (auto-hide, mint macOS-en).
  bool get _open => !widget.collapsed || _hover;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        width: _open ? 216.0 : 64.0,
        margin: const EdgeInsets.only(left: AppSpacing.xl, bottom: AppSpacing.xl),
        decoration: AppTheme.card(color: AppColors.bgSidebar),
        padding: EdgeInsets.symmetric(horizontal: _open ? 12 : 8, vertical: AppSpacing.lg),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _brand(),
            const SizedBox(height: AppSpacing.xl),
            _sectionLabel("MENÜ"),
            _item(NavId.dashboard, Icons.grid_view_rounded, "Áttekintés"),
            _item(NavId.matches, Icons.play_circle_outline, "Meccsek"),
            _item(NavId.live, Icons.sensors, "Élő követés", dot: true),
            const SizedBox(height: AppSpacing.lg),
            _sectionLabel("ELEMZÉS"),
            _item(NavId.designer, Icons.edit_outlined, "Figura-tervező"),
            _item(NavId.upload, Icons.file_upload_outlined, "Feltöltés"),
            const Spacer(),
            if (_open)
              Padding(
                padding: const EdgeInsets.only(left: 6, top: 4),
                child: Text("SPORT MACHINE",
                    style: AppText.label.copyWith(fontSize: 9.5, letterSpacing: 1.5, color: AppColors.textFaint)),
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
        gradient: const LinearGradient(colors: [AppColors.accent, Color(0xFF1B8F82)]),
        borderRadius: BorderRadius.circular(10),
      ),
      child: const Icon(Icons.change_history_rounded, color: AppColors.onAccent, size: 18),
    );
    if (!_open) return Center(child: logo);
    return Row(children: [
      logo,
      const SizedBox(width: AppSpacing.md),
      const Expanded(child: Text("SPORT MACHINE", style: AppText.brand, overflow: TextOverflow.ellipsis)),
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

  Widget _item(NavId id, IconData icon, String label, {bool dot = false}) {
    return _NavItem(
      id: id,
      icon: icon,
      label: label,
      dot: dot,
      selected: id == widget.active,
      open: _open,
    );
  }
}

/// Egyetlen menüelem — macOS-stílus: hover-kiemelés (finom, animált),
/// kijelölve kitöltött accent-"pill" fehér szöveggel/ikonnal.
class _NavItem extends StatefulWidget {
  final NavId id;
  final IconData icon;
  final String label;
  final bool dot;
  final bool selected;
  final bool open;

  const _NavItem({
    required this.id,
    required this.icon,
    required this.label,
    required this.selected,
    required this.open,
    this.dot = false,
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
      mainAxisAlignment: w.open ? MainAxisAlignment.start : MainAxisAlignment.center,
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
          if (w.dot) const _RedDot(),
        ] else if (w.dot)
          const Padding(padding: EdgeInsets.only(left: 2), child: _RedDot()),
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
          padding: EdgeInsets.symmetric(horizontal: w.open ? 10 : 0, vertical: 9),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(8),
          ),
          child: row,
        ),
      ),
    );

    // Keskeny (csukott) állapotban felirat helyett buborék-súgó.
    return w.open ? item : Tooltip(message: w.label, child: item);
  }
}

class _RedDot extends StatelessWidget {
  const _RedDot();
  @override
  Widget build(BuildContext context) =>
      Container(width: 8, height: 8, decoration: const BoxDecoration(color: AppColors.away, shape: BoxShape.circle));
}
