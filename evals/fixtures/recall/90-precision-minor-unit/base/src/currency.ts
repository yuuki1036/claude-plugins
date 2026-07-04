export interface Currency {
  code: string;
  minorUnitDigits: number; // 副単位の桁数（USD=2: セント, JPY=0: 副単位なし）
}

export const JPY: Currency = { code: "JPY", minorUnitDigits: 0 };
export const USD: Currency = { code: "USD", minorUnitDigits: 2 };
