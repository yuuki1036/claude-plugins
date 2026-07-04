import { ActionFailure, mapActionError } from "./errorMapping";

// server action 共通のエラーハンドラ。全 action はこれで包む（CLAUDE.md 参照）
export function withActionErrorHandler<A extends unknown[], R>(
  fn: (...args: A) => Promise<R>,
): (...args: A) => Promise<R | ActionFailure> {
  return async (...args: A) => {
    try {
      return await fn(...args);
    } catch (err) {
      return mapActionError(err);
    }
  };
}
