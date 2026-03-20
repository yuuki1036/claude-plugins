---
description: インストール済みの全プラグインを一括更新する
user_invocable: true
allowed-tools: Bash
---

インストール済みの全プラグインを一括更新してください。

## 手順

1. `claude plugin list` でインストール済みプラグインの一覧を取得
2. 出力からプラグイン名（`name@marketplace` 形式）を抽出
3. 各プラグインに対して `claude plugin update <name@marketplace>` を順次実行
4. 結果をまとめて報告

## 実行ルール

- CLIの競合を避けるため順次実行（並列不可）
- 更新完了後、以下のフォーマットで報告する：

```
## プラグイン更新結果

| プラグイン | 結果 | 備考 |
|-----------|------|------|
| name@marketplace | 更新済み / 最新 / エラー | バージョン等 |

反映にはClaude Codeの再起動が必要です。
```
