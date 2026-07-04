import { AppError } from "../errors";

export type SyncResult = { ok: true } | { ok: false; code: string };

// プロフィール同期: 外部プロフィール API から最新情報を取り込む
export async function syncProfile(userId: string): Promise<SyncResult> {
  try {
    await fetchRemoteProfile(userId);
    return { ok: true };
  } catch (err) {
    // AppError はコードをそのまま返す
    if (err instanceof AppError) {
      return { ok: false, code: err.code };
    }
    return { ok: false, code: "SERVICE_UNAVAILABLE" };
  }
}

async function fetchRemoteProfile(userId: string): Promise<void> {
  if (!userId) throw new AppError("VALIDATION_ERROR", "userId is required");
  // ... 外部 API 呼び出し（ネットワークエラー等は生の Error のまま throw される）
}
