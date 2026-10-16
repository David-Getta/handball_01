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
}
