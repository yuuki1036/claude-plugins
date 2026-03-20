# Hooks推奨パターン

Hooksは Claude Code のイベントに応じて自動的にコマンドを実行する。

**注意**: これは一般的なパターン。コードベース固有のツール/フレームワークに合った hook も検索して推奨すること。

## Auto-Formatting Hooks

| 検出条件 | ツール | 推奨Hook |
|---------|--------|---------|
| `.prettierrc`, `prettier.config.js` | Prettier | PostToolUse: Edit/Write時にauto-format |
| `.eslintrc`, `eslint.config.js` | ESLint | PostToolUse: Edit/Write時にauto-fix |
| `pyproject.toml` with black/isort | Black/isort | PostToolUse: Pythonファイルフォーマット |
| `ruff.toml`, `pyproject.toml` with ruff | Ruff | PostToolUse: lint + format |
| `go.mod` | gofmt | PostToolUse: gofmt実行 |
| `Cargo.toml` | rustfmt | PostToolUse: rustfmt実行 |

## Type Checking Hooks

| 検出条件 | ツール | 推奨Hook |
|---------|--------|---------|
| `tsconfig.json` | TypeScript | PostToolUse: tsc --noEmit |
| `mypy.ini`, pyproject.toml with mypy | mypy/pyright | PostToolUse: 型チェック |

## Protection Hooks

| 検出条件 | 推奨Hook | 代替手段 |
|---------|---------|---------|
| `.env`, `.env.local` | PreToolUse: .envファイル編集ブロック | permissions.deny でも対応可 |
| `credentials.json`, `secrets.yaml` | PreToolUse: 機密ファイル編集ブロック | permissions.deny でも対応可 |
| `package-lock.json`, `yarn.lock` | PreToolUse: lockファイル直接編集ブロック | - |

**ユーザーレイヤーとの重複チェック**: `permissions.deny` に `Read(.env*)` や `Write(.env*)` がある場合、.env保護hookは不要。

## Test Runner Hooks

| 検出条件 | ツール | 推奨Hook |
|---------|--------|---------|
| `jest.config.js`, package.json内jest | Jest | PostToolUse: 関連テスト実行 |
| `pytest.ini`, pyproject.toml内pytest | pytest | PostToolUse: 変更ファイルのテスト実行 |

## Notification Hooks

| Matcher | 用途 | 推奨 |
|---------|------|------|
| `permission_prompt` | 権限要求時のアラート | サウンド再生やデスクトップ通知 |
| `idle_prompt` | 入力待ち通知（60秒以上） | サウンドや通知 |

### 設定例

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [{ "type": "command", "command": "afplay /System/Library/Sounds/Ping.aiff" }]
      }
    ]
  }
}
```

## Hook設置先

`.claude/settings.json` に記載。プロジェクト/ユーザーどちらでも可。
