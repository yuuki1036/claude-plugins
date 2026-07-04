import { ValidationError } from "./errors";

// フォーム入力は文字列で受ける
export interface ExpenseInput {
  title: string;
  amount: string;
}

const NUMERIC = /^\d+(\.\d+)?$/;

export function validateExpense(input: ExpenseInput): ExpenseInput {
  if (!input.title) throw new ValidationError("title is required");
  if (!NUMERIC.test(input.amount)) {
    throw new ValidationError("amount must be numeric");
  }
  return input;
}
