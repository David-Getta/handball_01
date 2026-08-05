/// Üres állapot — mondjuk meg, MIÉRT üres, és mit lehet tenni.
///
/// A néma üres panel ugyanaz a hiba, mint a néma pörgettyű (lásd
/// `waiting.dart`): a felhasználó nem tudja eldönteni, hogy a program
/// romlott el, vagy tényleg nincs adat. A statisztika-panel például
/// nulla felismert játékosnál is kirajzolta a fejléceket és a
/// rendezés-gombokat — alattuk semmivel.
///
/// Két különböző dolgot kell szétválasztani, mert a teendő is más:
///   - NINCS ADAT (a feldolgozás nem talált semmit) → mit nézzen meg,
///   - NINCS TALÁLAT (van adat, csak a szűrő nem ereszt át semmit) →
///     lazítsa a szűrőt.
library;

import "package:flutter/material.dart";

import "../theme/app_theme.dart";

/// Üres állapot egy panel közepén.
///
/// - [what]: mi hiányzik, egy mondatban ("Nincs felismert játékos").
/// - [why]: miért lehet üres, és mit tegyen a felhasználó. Ne hagyd
///   üresen: a "miért" nélkül az üres panel hibának látszik.
/// - [icon]: a témához illő ikon.
class EmptyState extends StatelessWidget {
  const EmptyState(this.what, {this.why, this.icon, this.action, super.key});

  final String what;
  final String? why;
  final IconData? icon;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon ?? Icons.inbox_outlined, size: 34,
              color: AppColors.textFaint),
          const SizedBox(height: AppSpacing.md),
          Text(what, style: AppText.value.copyWith(fontSize: 15),
              textAlign: TextAlign.center),
          if (why != null) ...[
            const SizedBox(height: 6),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 380),
              child: Text(why!, style: AppText.label,
                  textAlign: TextAlign.center),
            ),
          ],
          if (action != null) ...[
            const SizedBox(height: AppSpacing.lg),
            action!,
          ],
        ]),
      ),
    );
  }
}

/// Egyetlen soros "itt nincs semmi" jelzés listán belül.
///
/// Ott használjuk, ahol a panel nem üres — csak egy szakasza (pl. az
/// egyik csapatnak nincs felismert játékosa). Egy teljes üres-állapot
/// ilyenkor túl hangos lenne, a néma hiány viszont hibának látszik.
Widget emptyRow(String text) => Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: Text(text,
          style: AppText.label.copyWith(color: AppColors.textFaint)),
    );
