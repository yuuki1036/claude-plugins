import { ExpenseInput } from "./schema";

export interface ExpenseRecord {
  title: string;
  amount: number;
}

export function toExpenseRecord(input: ExpenseInput): ExpenseRecord {
  return { title: input.title, amount: Number(input.amount) };
}

export interface DraftRecord {
  title: string;
  amount: string | null; // 未入力は NULL で保存する
}

export function toDraftRecord(input: ExpenseInput): DraftRecord {
  // 金額未入力の下書きは NULL として保存する
  return { title: input.title, amount: input.amount ?? null };
}
