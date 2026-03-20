# Skills推奨パターン

Skillsはワークフロー、参照資料、ベストプラクティスをパッケージ化したもの。
`.claude/skills/<name>/SKILL.md` に作成。`/skill-name` でユーザーが呼び出し可能。

## 公式プラグイン経由で利用可能なスキル

| コードベースシグナル | スキル | プラグイン |
|-------------------|--------|----------|
| プラグイン開発 | skill-development | plugin-dev |
| Gitコミット | commit | commit-commands |
| React/Vue/Angular | frontend-design | frontend-design |
| オートメーションルール | writing-rules | hookify |
| 機能開発 | feature-dev | feature-dev |

## カスタムスキルのパターン

### スキル構造

```
.claude/skills/
└── my-skill/
    ├── SKILL.md           # メイン指示（必須）
    ├── template.yaml      # テンプレート
    ├── scripts/
    │   └── validate.sh    # 実行スクリプト
    └── examples/          # 参照例
```

### Frontmatter

```yaml
---
name: skill-name
description: 説明とトリガー条件
disable-model-invocation: true  # ユーザーのみ呼び出し可（副作用あり）
user-invocable: false           # Claude自動呼び出しのみ（バックグラウンド知識）
allowed-tools: Read, Grep, Glob # ツール制限
context: fork                   # 分離サブエージェントで実行
---
```

### 推奨カスタムスキル

| コードベースシグナル | スキル | 呼び出し |
|-------------------|--------|---------|
| APIルート | api-doc (OpenAPIテンプレート付き) | 両方 |
| DBプロジェクト | create-migration (バリデーション付き) | ユーザーのみ |
| テストスイート | gen-test (テスト例付き) | ユーザーのみ |
| コンポーネントライブラリ | new-component (テンプレート付き) | ユーザーのみ |
| PRワークフロー | pr-check (チェックリスト付き) | ユーザーのみ |
| リリース | release-notes (git履歴活用) | ユーザーのみ |
| コードスタイル | project-conventions | Claude自動 |
| オンボーディング | setup-dev (前提条件スクリプト付き) | ユーザーのみ |

### 動的コンテキスト注入

```yaml
## 現在の状態
- ブランチ: !`git branch --show-current`
- ステータス: !`git status --short`
```

コマンド出力がスキル実行前にプレースホルダーを置換する。
