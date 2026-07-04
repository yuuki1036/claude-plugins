import { AppError } from "../errors";
import { withActionErrorHandler } from "../withActionErrorHandler";

export const createUser = withActionErrorHandler(async (name: string) => {
  if (!name) throw new AppError("VALIDATION_ERROR", "name is required");
  // ... ユーザー作成処理
  return { ok: true as const };
});
