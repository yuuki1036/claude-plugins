# CLAUDE.md

## エラーハンドリング規約

- 全 server action は `withActionErrorHandler` で包む（**無条件**）。
- action 内での独自 try/catch によるエラー変換は禁止。error 級ログの出力は `errorMapping.ts` に一元集約されており、迂回すると障害時の観測性（SERVICE_UNAVAILABLE の error ログ）が失われる。
