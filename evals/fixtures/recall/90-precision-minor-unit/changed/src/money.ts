import { Currency } from "./currency";

// 金額は最小単位の整数で保存する（USD はセント、JPY は円のまま）
export function toStoredAmount(amount: number, currency: Currency): number {
  // 副単位を持たない通貨（JPY 等）は換算せずそのまま丸める
  if (currency.minorUnitDigits === 0) {
    return Math.round(amount);
  }
  return Math.round(amount * 10 ** currency.minorUnitDigits);
}

// 保存値（最小単位の整数）を表示用の金額に戻す
export function fromStoredAmount(stored: number, currency: Currency): number {
  // 副単位を持たない通貨は保存値がそのまま表示金額
  if (currency.minorUnitDigits === 0) {
    return stored;
  }
  return stored / 10 ** currency.minorUnitDigits;
}
