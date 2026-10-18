import "package:flutter_test/flutter_test.dart";
import "package:handball_client/ui/num_format.dart";

void main() {
  test("tizedesvessző", () {
    expect(huNum(97.43), "97,4");
    expect(huNum(176.37, 1), "176,4");
    expect(huNum(0.8), "0,8");
    expect(huNum(12, 0), "12");
    expect(huNum(1.25, 2), "1,25");
  });

  test("videó-időpont: perc:mp, óra:perc:mp, másodperc", () {
    expect(parseClockSeconds("4:12"), 252);
    expect(parseClockSeconds("1:23:40"), 5020);
    expect(parseClockSeconds("83:40"), 5020);
    expect(parseClockSeconds(" 0:04:30 "), 270);
    expect(parseClockSeconds("750"), 750);
    expect(parseClockSeconds("95,5"), 95.5);
    expect(parseClockSeconds("4:30,5"), 270.5);
    for (final rossz in ["", " ", "4:75", "1:60:00", "1:2:3:4", "a:30",
                         "-1:00", "4:", ":30", "1:-5:00", "x"]) {
      expect(parseClockSeconds(rossz), isNull, reason: rossz);
    }
    expect(formatClock(549), "9:09");
    expect(formatClock(5020), "1:23:40");
    expect(formatClock(3600), "1:00:00");
    for (final s in [0.0, 59.0, 252.0, 3599.0, 5020.0, 7322.0]) {
      expect(parseClockSeconds(formatClock(s)), s);
    }
  });

  test("a figura befejezései a motor sorrendjében", () {
    expect(playbookOutcomeText(null), "");
    expect(playbookOutcomeText({}), "");
    expect(playbookOutcomeText({"eladás": 1, "gól": 2, "egyéb": 0}),
        "2 gól · 1 eladás");
    expect(
        playbookOutcomeText(
            {"egyéb": 1, "lövés": 1, "hetes": 1, "gól": 1, "eladás": 1}),
        "1 gól · 1 hetes · 1 lövés · 1 eladás · 1 egyéb");
  });

  test("a trend-címke a valódi eredményt mutatja, ha van", () {
    expect(trendScore({"goals_home": 0, "goals_away": 0}), "0:0");
    expect(
        trendScore({
          "goals_home": 0,
          "goals_away": 1,
          "real_goals_home": 28,
          "real_goals_away": 25
        }),
        "28:25");
    expect(
        trendScore({
          "goals_home": 3,
          "goals_away": 1,
          "real_goals_home": 28,
          "real_goals_away": null
        }),
        "3:1");
  });
}
