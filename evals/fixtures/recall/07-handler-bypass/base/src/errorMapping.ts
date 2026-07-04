import { AppError } from "./errors";
import { logger } from "./logger";

export interface ActionFailure {
  ok: false;
  code: string;
}

// 全 action のエラーはここで一元変換する（error 級ログを必ず残す）
export function mapActionError(err: unknown): ActionFailure {
  if (err instanceof AppError) {
    logger.error(err.code, err);
    return { ok: false, code: err.code };
  }
  logger.error("SERVICE_UNAVAILABLE", err);
  return { ok: false, code: "SERVICE_UNAVAILABLE" };
}
