---
name: cc-catch-up
description: >-
  Claude Code の最新アップデートをキャッチアップし、既存プラグインへの改善を提案・適用する。
  トリガー: 「キャッチアップ」「CC更新確認」「プラグイン改善」「新機能適用」「/catch-up」
  「Claude Codeの更新についていく」「プラグインをアップデート対応」「新機能を取り込む」
  「リリースノート確認」「CC最新バージョンの機能確認」
effort: high
allowed-tools:
  - WebSearch
  - WebFetch
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Agent
---

# CC Catch-Up: Claude Code アップデート追従スキル

Claude Code の最新リリースからプラグイン開発に関連する新機能を抽出し、開発中の全プラグインに対する改善を提案・適用するワークフロー。

## 前提

- 作業ディレクトリがプラグインリポジトリ（marketplace 構成）であること
- `${CLAUDE_PLUGIN_DATA}/catch-up-state.json` で前回キャッチアップ状態を追跡

## ワークフロー

### Phase 0: スコープ決定

1. `${CLAUDE_PLUGIN_DATA}/catch-up-state.json` を読み込む（存在しなければ初回）
2. 現在の Claude Code バージョンを取得: `claude --version` (Bash)
3. 前回のキャッチアップバージョンとの差分範囲を特定
4. AskUserQuestion で確認:
   - **フルスキャン**: 全機能カタログに対してプラグインを評価
   - **差分キャッチアップ**: 前回バージョン以降の新機能のみ
   - **特定バージョン範囲**: ユーザー指定の範囲

### Phase 1: Changelog 取得

1. WebSearch で `"Claude Code changelog"` または `"Claude Code release notes"` を検索
2. WebFetch で changelog ページを取得
3. Phase 0 で決定した範囲のエントリを抽出
4. 取得に失敗した場合: `references/plugin-features.md` のカタログをベースにフルスキャンへフォールバック

### Phase 2: プラグイン関連機能の抽出

取得した changelog エントリから、以下のカテゴリに分類して抽出:

| カテゴリ | 対象 |
|---------|------|
| **Hook** | 新イベント、ハンドラタイプ、条件フィールド |
| **Agent** | フロントマターフィールド、実行オプション |
| **Skill** | フロントマターフィールド、変数、ライフサイクル |
| **Command** | フロントマターフィールド、引数処理 |
| **Manifest** | plugin.json フィールド、userConfig、channels |
| **Variable** | 新しい `${...}` 変数、環境変数 |
| **MCP** | 統合機能、エリシテーション、サーバー設定 |
| **Runtime** | CLI フラグ、実行モード |

抽出基準: `references/plugin-features.md` のカテゴリ構造に照合し、既知の機能は差分のみ、未知の機能は新規としてマーク。

### Phase 3: プラグインスキャン

**並列 Agent で各プラグインをスキャンする。** Phase 1-2（Changelog 分析）と並列実行可能。各エージェントの担当:

1. `plugin.json` — マニフェストフィールドの使用状況
2. `hooks/hooks.json` — 使用中のフックイベント・ハンドラタイプ・条件フィールド
3. `skills/*/SKILL.md` — スキルフロントマターの使用フィールド
4. `agents/*.md` — エージェントフロントマターの使用フィールド
5. `commands/*.md` — コマンドフロントマターの使用フィールド

各プラグインの **機能使用プロファイル** を構築:

```
{plugin-name}:
  hooks: [SessionStart, PreToolUse(if条件あり), ...]
  agents: [doc-resolver(effort,model), ...]
  skills: [session-start(effort,paths未使用), ...]
  manifest: [userConfig使用, channels未使用, ...]
```

### Phase 4: Gap 分析

Phase 2 の新機能リストと Phase 3 のプラグインプロファイルを突合:

1. `references/improvement-patterns.md` のデシジョンツリーを適用
2. 各プラグイン × 各新機能について **適用可能性** を判定:
   - **適用推奨** — 明確なメリットがある
   - **検討余地** — ユースケース次第
   - **対象外** — プラグインの機能スコープに合わない
3. 優先度を付与: **High** (安全性・UX 改善) > **Medium** (機能強化) > **Low** (最適化)

### Phase 5: Gap レポート出力

**改善を適用する前に、必ずレポートを出力する。**

出力フォーマット:

```markdown
## CC Catch-Up レポート
**対象範囲**: v{from} → v{to}
**新機能数**: {n} 件（プラグイン関連）
**改善提案数**: {m} 件

### 新機能サマリ
| # | 機能 | カテゴリ | 概要 |
|---|------|---------|------|

### Gap マトリクス
| 新機能 | plugin-a | plugin-b | ... | 適用方法 |
|--------|----------|----------|-----|---------|
| if条件フック | - | ✅ High | ... | PreToolUse簡素化 |

### 改善提案（優先度順）
#### 1. [High] {plugin-name}: {改善タイトル}
- **新機能**: {feature}
- **現状**: {current}
- **改善後**: {improved}
- **変更ファイル**: {files}
```

### Phase 6: 適用（ユーザー承認制）

1. AskUserQuestion で適用スコープを確認:
   - **全件適用**: 全提案を適用
   - **選択適用**: 番号指定で個別選択
   - **レポートのみ**: 適用せず終了
2. 選択された改善を適用（Edit/Write）
3. 各プラグインの `plugin.json` バージョンバンプ
4. `CHANGELOG.md` に変更を追記
5. `.claude-plugin/marketplace.json` を同期

### Phase 7: 状態更新

キャッチアップ完了後、`${CLAUDE_PLUGIN_DATA}/catch-up-state.json` を更新:

```json
{
  "lastCatchUpVersion": "2.1.86",
  "lastCatchUpDate": "2026-03-29",
  "appliedFeatures": ["if-conditional-hooks", "effort-frontmatter", ...],
  "skippedFeatures": ["lsp-server", ...]
}
```

## Reference Files

- **`${CLAUDE_SKILL_DIR}/references/plugin-features.md`** — CC のプラグイン関連機能カタログ（カテゴリ別・バージョン付き）。フルスキャン時のベースライン、および changelog 解析時の分類基準として使用
- **`${CLAUDE_SKILL_DIR}/references/improvement-patterns.md`** — 機能→改善のデシジョンツリーと before/after パターン集。Gap 分析（Phase 4）の判定ロジックとして使用

## 注意事項

- Changelog 取得に失敗した場合は `plugin-features.md` ベースのフルスキャンにフォールバック
- 改善適用時は既存の pre-commit hook（バージョンバンプ・CHANGELOG 必須）に従う
- `marketplace.json` の同期を忘れないこと
- 適用後は `/quality-check` での検証を推奨
