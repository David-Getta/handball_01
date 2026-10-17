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
