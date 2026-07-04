import { JPY, USD } from "../src/currency";
import { toStoredAmount } from "../src/money";

test("USD は副単位（セント）の整数で保存する", () => {
  expect(toStoredAmount(12.34, USD)).toBe(1234);
});

test("JPY は副単位を持たないため円のまま保存する", () => {
  expect(toStoredAmount(1500, JPY)).toBe(1500);
});
