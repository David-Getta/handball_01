/// Alkalmazás-shell — felső breadcrumb sáv + bal oldali navigáció + tartalom.
///
/// A "Sport Machine" design szerint: legfelül egy számozott chip + útvonal, alatta
/// bal oldalon a navigáció (nyitott sidebar vagy összecsukott rail), jobbra a
/// képernyő tartalma. Minden fő képernyő ezt használja az egységes keretért.
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
  final bool collapsed;       // összecsukott rail (meccs/feltöltés nézeteknél)
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

/// Bal oldali navigáció — nyitott (címkékkel) vagy összecsukott (csak ikonok).
class _SideNav extends StatelessWidget {
  final NavId active;
  final bool collapsed;
  const _SideNav({required this.active, required this.collapsed});

  @override
  Widget build(BuildContext context) {
    final width = collapsed ? 68.0 : 236.0;
    return Container(
      width: width,
      margin: const EdgeInsets.only(left: AppSpacing.xl, bottom: AppSpacing.xl),
      decoration: AppTheme.card(color: AppColors.bgSidebar),
      padding: EdgeInsets.symmetric(horizontal: collapsed ? 10 : AppSpacing.lg, vertical: AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _brand(),
          const SizedBox(height: AppSpacing.xl),
          if (!collapsed) _sectionLabel("MENÜ"),
          _item(context, NavId.dashboard, Icons.grid_view_rounded, "Áttekintés"),
          _item(context, NavId.matches, Icons.play_circle_outline, "Meccsek", badge: "24"),
          _item(context, NavId.live, Icons.sensors, "Élő követés", dot: true),
          const SizedBox(height: AppSpacing.lg),
          if (!collapsed) _sectionLabel("ELEMZÉS"),
          _item(context, NavId.designer, Icons.edit_outlined, "Figura-tervező"),
          _item(context, NavId.upload, Icons.file_upload_outlined, "Feltöltés"),
        ],
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
    if (collapsed) return Center(child: logo);
    return Row(children: [
      logo,
      const SizedBox(width: AppSpacing.md),
      const Expanded(child: Text("SPORT MACHINE", style: AppText.brand, overflow: TextOverflow.ellipsis)),
    ]);
  }

  Widget _sectionLabel(String t) => Padding(
        padding: const EdgeInsets.only(left: 6, bottom: AppSpacing.sm, top: 4),
        child: Text(t, style: AppText.sectionLabel),
      );

  Widget _item(BuildContext context, NavId id, IconData icon, String label,
      {String? badge, bool dot = false}) {
    final selected = id == active;
    final content = Container(
      margin: const EdgeInsets.symmetric(vertical: 3),
      padding: EdgeInsets.symmetric(horizontal: collapsed ? 0 : 12, vertical: 11),
      decoration: BoxDecoration(
        color: selected ? AppColors.surfaceAlt : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: selected ? AppColors.borderStrong : Colors.transparent),
      ),
      child: Row(
        mainAxisAlignment: collapsed ? MainAxisAlignment.center : MainAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: selected ? AppColors.accent : AppColors.textFaint),
          if (!collapsed) ...[
            const SizedBox(width: AppSpacing.md),
            Expanded(child: Text(label,
                style: TextStyle(
                    color: selected ? AppColors.textPrimary : AppColors.textSecondary,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w500, fontSize: 14))),
            if (badge != null) _badge(badge),
            if (dot) const _RedDot(),
          ] else if (dot)
            const Padding(padding: EdgeInsets.only(left: 2), child: _RedDot()),
        ],
      ),
    );
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: selected ? null : () => navTo(context, id),
      child: content,
    );
  }

  Widget _badge(String t) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
        decoration: BoxDecoration(color: AppColors.surface, borderRadius: BorderRadius.circular(10), border: Border.all(color: AppColors.border)),
        child: Text(t, style: AppText.label.copyWith(fontSize: 11)),
      );
}

class _RedDot extends StatelessWidget {
  const _RedDot();
  @override
  Widget build(BuildContext context) =>
      Container(width: 8, height: 8, decoration: const BoxDecoration(color: AppColors.away, shape: BoxShape.circle));
}
