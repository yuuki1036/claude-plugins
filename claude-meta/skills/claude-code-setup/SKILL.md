---
name: claude-code-setup
description: >
  コードベースを分析し、ユーザーレイヤーの既存設定を考慮した上でClaude Codeオートメーション（hooks, skills, MCP servers, subagents, plugins）を推奨する。
  トリガー: 「セットアップ推奨」「オートメーション推奨」「Claude Codeのセットアップ」「どんなhookを使うべき？」「自動化の提案」「recommend automations」
effort: high
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
---

# Claude Automation Recommender (User-Layer Aware)

コードベースのパターンを分析し、Claude Codeオートメーションをカテゴリ横断で推奨する。
**ユーザーレイヤー（~/.claude/）の既存設定を確認し、重複を避けた推奨を行う。**

**このスキルは読み取り専用。** 分析と推奨のみ行い、ファイルの作成・変更は行わない。
Bash は情報収集目的（設定ファイルの確認、ディレクトリ一覧の取得等）のみで使用し、ファイルの書き込みや変更には使用しない。

## 出力ガイドライン

- **各タイプ1-2個を推奨**: 圧倒しない - カテゴリごとに最も価値のある1-2個のみ
- **特定タイプを聞かれた場合**: そのタイプに集中し、3-5個の推奨を提供
- **参照リスト以外も提案**: 参照ファイルは一般的なパターンだが、コードベース固有のツール・フレームワーク・ライブラリに特化した推奨も行う
- **追加推奨の案内**: 各カテゴリの追加推奨をリクエストできることを末尾に記載

## オートメーションタイプ概要

| タイプ | 用途 |
|--------|------|
| **Hooks** | ツールイベントに対する自動アクション（フォーマット、lint、編集ブロック） |
| **Subagents** | 並列で動く専門レビュアー/アナライザー |
| **Skills** | パッケージ化された専門知識・ワークフロー・反復タスク |
| **Plugins** | インストール可能なスキルのコレクション |
| **MCP Servers** | 外部ツール統合（DB、API、ブラウザ、ドキュメント） |

## ワークフロー

### Phase 0: ユーザーレイヤーの既存設定を収集

**重要: プロジェクト分析の前に、必ずユーザーレイヤーを確認する。**

```bash
# ユーザーレイヤーの設定を確認
cat ~/.claude/settings.json 2>/dev/null

# ユーザーレイヤーのMCP設定を確認
cat ~/.claude/mcp.json 2>/dev/null

# ユーザーレイヤーのスキル一覧
ls ~/.claude/skills/ 2>/dev/null

# ユーザーレイヤーのエージェント一覧
ls ~/.claude/agents/ 2>/dev/null

# ユーザーレイヤーのコマンド一覧
ls ~/.claude/commands/ 2>/dev/null
```

**収集する情報:**

| カテゴリ | 確認先 | 収集内容 |
|---------|--------|----------|
| Hooks | `~/.claude/settings.json` → `hooks` | 既存のPreToolUse/PostToolUse/Stop/Notification hooks |
| MCP Servers | `~/.claude/mcp.json` | 接続済みのMCPサーバー名と設定 |
| Skills | `~/.claude/skills/` | インストール済みスキルのディレクトリ名 |
| Agents | `~/.claude/agents/` | 定義済みサブエージェントのファイル名 |
| Plugins | `~/.claude/settings.json` → `enabledPlugins` | 有効化済みプラグイン |
| Permissions | `~/.claude/settings.json` → `permissions` | deny/allowルール（保護系hookと重複の可能性） |
| Commands | `~/.claude/commands/` | 定義済みスラッシュコマンド |

この情報を **`existing_user_config`** として保持する。

### Phase 1: コードベース分析

プロジェクトのコンテキストを収集する:

```bash
# プロジェクトタイプとツールを検出
ls -la package.json pyproject.toml Cargo.toml go.mod pom.xml 2>/dev/null
cat package.json 2>/dev/null | head -50

# MCP推奨のための依存関係確認
cat package.json 2>/dev/null | grep -E '"(react|vue|angular|next|express|fastapi|django|prisma|supabase|stripe)"'

# 既存のプロジェクトレベルClaude Code設定を確認
ls -la .claude/ CLAUDE.md 2>/dev/null
cat .claude/settings.json 2>/dev/null
cat .mcp.json 2>/dev/null
ls .claude/skills/ 2>/dev/null
ls .claude/agents/ 2>/dev/null

# プロジェクト構造の分析
ls -la src/ app/ lib/ tests/ components/ pages/ api/ 2>/dev/null
```

**キーインジケーター:**

| カテゴリ | 確認対象 | 推奨に影響 |
|---------|---------|-----------|
| 言語/フレームワーク | package.json, pyproject.toml, importパターン | Hooks, MCP |
| フロントエンド | React, Vue, Angular, Next.js | Playwright MCP, フロントエンドスキル |
| バックエンド | Express, FastAPI, Django | APIドキュメントツール |
| データベース | Prisma, Supabase, raw SQL | DB系MCP |
| 外部API | Stripe, OpenAI, AWS SDK | context7 MCP |
| テスト | Jest, pytest, Playwright設定 | テスト系hook, subagent |
| CI/CD | GitHub Actions, CircleCI | GitHub MCP |
| Issue管理 | Linear, Jira参照 | Issue tracker MCP |
| ドキュメント | OpenAPI, JSDoc, docstrings | ドキュメントスキル |

### Phase 2: 重複フィルタリングと推奨生成

**重要: Phase 0で収集した `existing_user_config` と照合し、以下のルールで推奨をフィルタリングする。**

#### フィルタリングルール

| 状況 | 判定 | アクション |
|------|------|-----------|
| ユーザーレイヤーに同じものがある | **スキップ** | 「既にユーザーレイヤーで設定済み」セクションに記載 |
| ユーザーレイヤーに類似機能がある | **注記付き推奨** | 差分・競合の可能性を明記 |
| ユーザーレイヤーに無い | **通常推奨** | 新規として推奨 |
| ユーザーレイヤーにあるがプロジェクト共有したい | **チーム共有として推奨** | `.mcp.json`や`.claude/`に追加する価値を説明 |

#### 具体的なチェック項目

**Hooks:**
- ユーザーの `settings.json` → `hooks` に同じイベント+matcherの組み合わせがあるか
- ユーザーの `permissions.deny` で既に保護されているパスと hook の保護対象が重複しないか
  - 例: `deny: ["Read(.env.*)"]` があれば `.env` ブロック hook は不要

**MCP Servers:**
- ユーザーの `mcp.json` に同じサーバーが設定済みか
- プロジェクトの `.mcp.json` にも同じサーバーがあるか

**Skills:**
- ユーザーの `~/.claude/skills/` に同名・同機能のスキルがあるか
- 有効化済みプラグインに含まれるスキルと重複しないか

**Plugins:**
- ユーザーの `enabledPlugins` に既に有効化されているか

**Subagents:**
- ユーザーの `~/.claude/agents/` に同名・同機能のエージェントがあるか

#### カテゴリ別推奨の生成

参照ファイルを活用:
- [references/mcp-servers.md](references/mcp-servers.md) - MCP詳細パターン
- [references/skills-reference.md](references/skills-reference.md) - スキル詳細
- [references/hooks-patterns.md](references/hooks-patterns.md) - Hook設定パターン
- [references/subagent-templates.md](references/subagent-templates.md) - サブエージェントテンプレート
- [references/plugins-reference.md](references/plugins-reference.md) - プラグイン一覧

### Phase 3: 推奨レポートの出力

以下のフォーマットで出力する。**既存設定セクションを必ず含める。**

```markdown
## Claude Code オートメーション推奨

コードベースを分析し、ユーザーレイヤーの既存設定を考慮した推奨です。

### コードベースプロファイル
- **言語**: [検出された言語/ランタイム]
- **フレームワーク**: [検出されたフレームワーク]
- **主要ライブラリ**: [検出された関連ライブラリ]

---

### ユーザーレイヤーで設定済み（推奨不要）

以下は既に `~/.claude/` で設定されているため、追加不要です:

| カテゴリ | 設定内容 | 設定場所 |
|---------|---------|---------|
| Hook | [既存hook名] | ~/.claude/settings.json |
| MCP | [既存MCP名] | ~/.claude/mcp.json |
| Skill | [既存skill名] | ~/.claude/skills/ |
| Plugin | [既存plugin名] | ~/.claude/settings.json |
| Agent | [既存agent名] | ~/.claude/agents/ |

---

### 新規推奨

#### MCP Servers

##### [サーバー名]
**理由**: [検出されたライブラリに基づく具体的理由]
**インストール**: `claude mcp add [name]`
**設定先**: プロジェクト（`.mcp.json`）/ ユーザー（`~/.claude/mcp.json`）

---

#### Skills

##### [スキル名]
**理由**: [具体的理由]
**作成先**: `.claude/skills/[name]/SKILL.md`
**呼び出し**: ユーザー / 両方 / Claude自動
**プラグインでも利用可**: [plugin-name]（該当する場合）

---

#### Hooks

##### [hook名]
**理由**: [検出された設定に基づく具体的理由]
**設定先**: `.claude/settings.json`
**注意**: [ユーザーレイヤーとの競合がある場合はここに記載]

---

#### Subagents

##### [エージェント名]
**理由**: [コードベースパターンに基づく具体的理由]
**作成先**: `.claude/agents/[name].md`

---

### チーム共有を検討すべき設定

ユーザーレイヤーに設定済みだが、チームメンバーも利用できるようプロジェクトレイヤーへの追加を検討:

| 設定 | 理由 |
|------|------|
| [設定名] | [チーム共有する価値がある理由] |

---

**追加推奨が必要？** 特定カテゴリの追加推奨をリクエストできます（例: 「もっとMCPサーバーの選択肢を見せて」「他にどんなhookが使える？」）

**設定のお手伝い？** 上記の推奨のセットアップをお手伝いできます。
```

## 判断フレームワーク

### 推奨先の判断（ユーザー vs プロジェクト）

| 条件 | 推奨先 | 理由 |
|------|--------|------|
| 個人の好みに依存 | ユーザーレイヤー | 他プロジェクトでも使える |
| プロジェクト固有のツール | プロジェクトレイヤー | そのプロジェクトでのみ必要 |
| チーム全員が使うべき | プロジェクトレイヤー（`.mcp.json`をgit管理） | チーム標準化 |
| 既にユーザーにあるがチームにも必要 | プロジェクトレイヤーに追加 | チーム共有 |

### 重複時の優先度

Claude Codeの設定マージ順序: `user → project → runtime`

| 設定タイプ | 重複時の挙動 | 注意点 |
|-----------|-------------|--------|
| Hooks | 両方実行される | 二重実行に注意 |
| Skills | 名前が同じなら競合の可能性 | 明示的に区別が必要 |
| MCP Servers | 両方接続 | 同じサーバーの二重起動に注意 |
| Permissions | マージ（厳しい方が優先） | 競合は少ない |
