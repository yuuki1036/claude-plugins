---
description: インストール済みの全プラグインを最新版に一括アップデートする
user_invocable: true
allowed-tools:
  - Bash
---

インストール済みの全プラグインを一括更新してください。

## 手順

### Phase 1: マーケットプレイスキャッシュの最新化

`claude plugin list` を実行し、出力から `name@marketplace` 形式のマーケットプレイス名（`@` 以降の部分）を抽出する。
重複を除いた各マーケットプレイスに対して以下を順番に実行する:

1. ローカルキャッシュを削除する（古いバージョンが残っていると install 時に反映されない）:

```bash
rm -rf ~/.claude/plugins/cache/<marketplace-name>
```

2. マーケットプレイスキャッシュをリモートから再取得する:

```bash
claude plugin marketplace update <marketplace-name>
```

### Phase 2: インストール済みプラグイン一覧とバージョンの記録

Phase 1 で実行した `claude plugin list` の出力を再利用し、全プラグインの以下の情報を記録する:

- `name@marketplace` 形式の識別子
- 現在のバージョン（Before バージョンとして保持する）

> `claude plugin list` の出力例:
> ```
> name@marketplace (v1.2.0)
>   Description: ...
>   Scope: user
> ```

### Phase 3: 各プラグインの再インストール

CLI の競合を避けるため順次実行（並列不可）。
各プラグインに対して以下を実行する:

#### 3-1. アンインストール（フォールバック付き）

以下の順で試行し、いずれかが成功したら 3-2 に進む:

1. `claude plugin uninstall <name@marketplace>`
2. 失敗した場合: `claude plugin uninstall <name@marketplace> --scope user`
3. 失敗した場合: `claude plugin uninstall <name@marketplace> --scope project`
4. すべて失敗した場合: `~/.claude/plugins/installed_plugins.json` を読み込み、該当プラグインのエントリを JSON から削除して書き戻す（手動削除フォールバック）

#### 3-2. インストール

```bash
claude plugin install <name@marketplace>
```

- install が失敗した場合はエラーとして記録し、次のプラグインに進む

### Phase 4: 更新後バージョンの取得

`claude plugin list` を実行し、各プラグインの更新後バージョン（After）を取得する。

### Phase 4.5: 更新内容の取得

Phase 4 で「更新済み」と判定されたプラグイン（Before ≠ After）に対して、CHANGELOG.md から更新内容を抽出する。

1. キャッシュ内の CHANGELOG.md を読み込む:

```bash
cat ~/.claude/plugins/cache/<marketplace-name>/<plugin-name>/<After-version>/CHANGELOG.md
```

2. CHANGELOG.md から Before バージョンより新しいエントリを抽出する:
   - `## [<After-version>]` から `## [<Before-version>]` の直前までを取得
   - Before と After の間に複数バージョンがある場合は全て含める
   - `### Added` / `### Fixed` / `### Changed` 等のサブセクションをそのまま保持

3. CHANGELOG.md が存在しない場合や読み取りに失敗した場合は「CHANGELOG なし」として記録する

### Phase 5: 結果の報告

以下のフォーマットで報告する:

```
## プラグイン更新結果

| プラグイン | Before | After | 結果 |
|-----------|--------|-------|------|
| name@marketplace | 1.0.0 | 1.1.0 | 更新済み |
| name@marketplace | 1.0.0 | 1.0.0 | 変更なし |
| name@marketplace | 1.0.0 | - | エラー |

### 更新内容

#### name (1.0.0 → 1.1.0)
- Added: 新機能の説明
- Fixed: バグ修正の説明

反映にはClaude Codeの再起動が必要です。
```

結果の判定ルール:
- Before と After のバージョンが異なる → **更新済み**
- Before と After のバージョンが同じ → **変更なし**
- install に失敗した → **エラー**（After は `-` と表示）

「更新内容」セクションは更新済みプラグインが1つ以上ある場合のみ表示する。
全プラグインが「変更なし」の場合はこのセクションを省略する。
