/// Markdown → olvasható sima szöveg.
///
/// A kiadás jegyzete a CHANGELOG-ból jön, tehát markdown: `**félkövér**`,
/// `` `kód` ``, `> idézet`, `## cím`, `- felsorolás`. A GitHub-oldalon ez
/// szépen jelenik meg, egy Flutter `Text`-ben viszont a jelölők NYERSEN
/// látszanak — a felhasználó csillagokat és kettőskereszteket olvas.
///
/// Markdown-megjelenítő csomagot nem húzunk be emiatt: az app offline
/// működik, és ez a szöveg felsorolás meg bekezdés, nem táblázat. A
/// jelölők eltávolítása elég.
library;

/// A jegyzet olvasható, sima szöveges változata.
///
/// Amit csinál: leszedi a hangsúly- és kód-jelölőket, az idézet- és
/// cím-előtagokat, a felsorolás kötőjelét pontra cseréli, és összevonja
/// a három vagy több üres sort. A SZÖVEGET nem bántja.
String plainMarkdown(String md) {
  final out = <String>[];
  var blank = 0;
  for (var line in md.split("\n")) {
    line = line.trimRight();
    // Idézet-előtag ("> ") — a kiadás-jegyzet bevezetője ilyen.
    line = line.replaceFirst(RegExp(r"^\s*>\s?"), "");
    // Cím-előtag ("## ") — a szöveg marad, a kettőskereszt megy.
    line = line.replaceFirst(RegExp(r"^\s*#{1,6}\s+"), "");
    // Felsorolás: "- " / "* " → "• " (a behúzás megmarad).
    line = line.replaceFirstMapped(
        RegExp(r"^(\s*)[-*]\s+"), (m) => "${m[1]}• ");
    // Hangsúly- és kód-jelölők.
    line = line
        .replaceAll("**", "")
        .replaceAll("`", "");
    if (line.trim().isEmpty) {
      blank++;
      if (blank > 1) continue; // legfeljebb EGY üres sor egymás után
    } else {
      blank = 0;
    }
    out.add(line);
  }
  return out.join("\n").trim();
}
