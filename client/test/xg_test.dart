// A termék xG-je Dart-tükörben: a várt értékek a backend
// xg.xg_of_position függvényéből számolva (kapu x = 40), hogy a figura
// pontszáma a kliensen és a szerveren ne térjen el.
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/analytics/decisions.dart";

void main() {
  test("xgOfPosition a backend értékeit adja", () {
    expect(xgOfPosition(34.0, 10.0, 40.0), closeTo(0.477, 1e-9));
    expect(xgOfPosition(31.0, 10.0, 40.0), closeTo(0.268, 1e-9));
    expect(xgOfPosition(28.0, 10.0, 40.0), closeTo(0.101, 1e-9));
    expect(xgOfPosition(33.0, 4.0, 40.0), closeTo(0.242, 1e-9));
    expect(xgOfPosition(36.0, 2.0, 40.0), closeTo(0.238, 1e-9));
    expect(xgOfPosition(27.0, 15.0, 40.0), closeTo(0.052, 1e-9));
    expect(xgOfPosition(39.8, 10.0, 40.0), closeTo(0.85, 1e-9));
    expect(xgOfPosition(20.0, 10.0, 40.0), closeTo(0.05, 1e-9));
  });

  test("a 13 m-es szabad lövés kevesebbet ér, mint a 6 m-es", () {
    expect(xgOfPosition(27.0, 10.0, 40.0), lessThan(xgOfPosition(34.0, 10.0, 40.0)));
  });
}
