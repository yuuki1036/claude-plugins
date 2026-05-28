# 保護対象ファイル: 推奨デフォルトリスト

プラグイン自体は **デフォルトで保護対象ゼロ**（誤爆防止のため opt-in）。
プロジェクト側が `.claude/guardrail-protect.json` で明示的に宣言する。

以下は「典型的に保護したくなる lint / hook 設定」の参考リスト。プロジェクトに合わせて取捨選択する。

## 推奨保護対象（言語横断）

```json
{
  "protected_basenames": [
    ".golangci.yml",
    ".golangci.yaml",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.cjs",
    "eslint.config.js",
    "eslint.config.mjs",
    ".rubocop.yml",
    ".rubocop.yaml",
    "ruff.toml",
    "pyproject.toml",
    ".flake8",
    ".pylintrc",
    "lefthook.yml",
    "lefthook.yaml",
    "pre-commit-config.yaml",
    ".pre-commit-config.yaml",
    ".husky",
    "redocly.yaml",
    "redocly.yml",
    "tsconfig.json",
    "tsconfig.base.json"
  ]
}
```

## カテゴリ別

### Linter 設定

- Go: `.golangci.yml` / `.golangci.yaml`
- JavaScript/TypeScript: `.eslintrc*`, `eslint.config.*`
- Ruby: `.rubocop.yml` / `.rubocop.yaml`
- Python: `ruff.toml`, `pyproject.toml` の `[tool.ruff]` セクション、`.flake8`, `.pylintrc`

### Git hooks 管理

- `lefthook.yml` / `lefthook.yaml`
- `.pre-commit-config.yaml`
- `.husky/*`

### API / Schema 検証

- `redocly.yaml` / `redocly.yml`
- `openapi-config.yml`

### 型システム設定

- `tsconfig.json`, `tsconfig.base.json`
- `mypy.ini`, `pyrightconfig.json`

### CI/CD ワークフロー

- `.github/workflows/*.yml`（ファイル名固有なので basename マッチが弱い、`-` 付きの厳密な basename を列挙する想定）

## プロジェクトに応じた追加・除外

プロジェクト固有の検証ロジック（カスタム linter 設定、社内規約 hook など）も追加可能。例:

```json
{
  "protected_basenames": [
    ".golangci.yml",
    "lefthook.yml",
    "our-team-style.yml",
    "internal-security-rules.json"
  ]
}
```

逆に「ここは試行錯誤フェーズなので protect しない」というプロジェクトでは、空配列 (`{"protected_basenames": []}`) または **設定ファイル自体を作らない** という選択も OK（その場合 hook は no-op）。

## 上書きルール

- プロジェクトが宣言した `protected_basenames` がそのまま使われる（プラグイン側で merge しない）
- このファイルはあくまで参考。コピペして使いたい場合は `.claude/guardrail-protect.json` に貼り付ける

## 関連

- メタルール本文: [meta-rule.md](meta-rule.md)
- README: `../README.md`
