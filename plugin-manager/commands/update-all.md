---
description: インストール済みの全プラグインをキャッシュ更新後に再インストールする
user_invocable: true
allowed-tools:
  - Bash
---

インストール済みの全プラグインを一括更新してください。

## 手順

### Phase 1: マーケットプレイスキャッシュの最新化

`claude plugin list` を実行し、出力から `name@marketplace` 形式のマーケットプレイス名を抽出する。
重複を除いた各マーケットプレイスに対して以下を実行する:

```bash
claude plugin marketplace update <marketplace-name>
```

### Phase 2: インストール済みプラグイン一覧の取得

`claude plugin list` を実行し、全プラグインの `name@marketplace` 形式の識別子を抽出する。

### Phase 3: 各プラグインの再インストール

CLIの競合を避けるため順次実行（並列不可）。
各プラグインに対して以下を順番に実行する:

```bash
claude plugin uninstall <name@marketplace>
claude plugin install <name@marketplace>
```

- uninstall または install が失敗した場合はエラーとして記録し、次のプラグインに進む

### Phase 4: 結果の報告

以下のフォーマットで報告する:

```
## プラグイン更新結果

| プラグイン | 結果 | 備考 |
|-----------|------|------|
| name@marketplace | 更新済み / エラー | エラー詳細等 |

反映にはClaude Codeの再起動が必要です。
```
