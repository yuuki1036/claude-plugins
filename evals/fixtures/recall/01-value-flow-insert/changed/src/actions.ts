import { Db } from "./db";
import { AppError } from "./errors";
import { toDraftRecord, toExpenseRecord } from "./domain";
import { insertDraft, insertExpense } from "./repository";
import { ExpenseInput, validateDraft, validateExpense } from "./schema";

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

// 下書き保存: 入力途中の経費をあとで再開できるように保存する
export async function saveDraft(
  db: Db,
  input: ExpenseInput,
): Promise<ActionResult> {
  try {
    const rec = toDraftRecord(validateDraft(input));
    await insertDraft(db, rec);
    return { ok: true };
  } catch (err) {
    if (err instanceof AppError) return { ok: false, code: err.code };
    throw err; // 想定外エラーは上位で 500 に変換される
  }
}
