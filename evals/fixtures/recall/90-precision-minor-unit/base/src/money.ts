import { Currency } from "./currency";

// 金額は最小単位の整数で保存する（USD はセント、JPY は円のまま）
export function toStoredAmount(amount: number, currency: Currency): number {
  return Math.round(amount * 10 ** currency.minorUnitDigits);
}
