import { Db } from "./db";
import { AppError } from "./errors";
import { toExpenseRecord } from "./domain";
import { insertExpense } from "./repository";
import { ExpenseInput, validateExpense } from "./schema";

export type ActionResult = { ok: true } | { ok: false; code: string };

export async function createExpense(
  db: Db,
  input: ExpenseInput,
): Promise<ActionResult> {
  try {
    const rec = toExpenseRecord(validateExpense(input));
    await insertExpense(db, rec);
    return { ok: true };
  } catch (err) {
    if (err instanceof AppError) return { ok: false, code: err.code };
    throw err; // 想定外エラーは上位で 500 に変換される
  }
}
