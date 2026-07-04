import { Db } from "./db";
import { ExpenseRecord } from "./domain";

export async function insertExpense(db: Db, rec: ExpenseRecord): Promise<void> {
  await db.query("INSERT INTO expenses (title, amount) VALUES ($1, $2)", [
    rec.title,
    rec.amount,
  ]);
}
