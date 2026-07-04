import { JPY, USD } from "../src/currency";
import { fromStoredAmount, toStoredAmount } from "../src/money";

test("USD は副単位（セント）の整数で保存する", () => {
  expect(toStoredAmount(12.34, USD)).toBe(1234);
});

test("JPY は副単位を持たないため円のまま保存する", () => {
  expect(toStoredAmount(1500, JPY)).toBe(1500);
});

test("USD の保存値はセントからドルに戻る（round-trip）", () => {
  expect(fromStoredAmount(toStoredAmount(12.34, USD), USD)).toBe(12.34);
});

test("JPY の保存値はそのまま円に戻る（round-trip）", () => {
  expect(fromStoredAmount(toStoredAmount(1500, JPY), JPY)).toBe(1500);
});
