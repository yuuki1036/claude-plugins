import { ExpenseInput } from "./schema";

export interface ExpenseRecord {
  title: string;
  amount: number;
}

export function toExpenseRecord(input: ExpenseInput): ExpenseRecord {
  return { title: input.title, amount: Number(input.amount) };
}
