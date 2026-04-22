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
- `${CLAUDE_PLUGIN_ROOT}/skills/cc-catch-up/state.json` で前回キャッチアップ状態を追跡

## ワークフロー

### Phase 0: スコープ決定

1. `${CLAUDE_PLUGIN_ROOT}/skills/cc-catch-up/state.json` を読み込む（存在しなければ初回）
2. 現在の Claude Code バージョンを取得: `claude --version` (Bash)
3. 現在のモデル family ID を取得（環境変数 or `claude config` から。失敗時はユーザーに確認）
4. 前回のキャッチアップバージョンとの差分範囲を特定
5. **モデル世代変更の検知**: `state.json.lastCatchUpModel` と現在のモデル family を比較
   - 異なる場合、または `lastPruningDate` から 90 日以上経過している場合は **剪定モードを推奨** として提示
6. AskUserQuestion でモードを選択:
   - **差分キャッチアップ**: 前回バージョン以降の新機能のみ（Phase 1-7）
   - **フルスキャン**: 全機能カタログに対してプラグインを評価（Phase 1-7）
   - **剪定モード**: 不要になった制約の棚卸しのみ（Phase P → Phase 7）
   - **キャッチアップ + 剪定**: 両方実行（Phase 1-7 → Phase P）
   - **特定バージョン範囲**: ユーザー指定の範囲（Phase 1-7）

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

### Phase P: 剪定モード（モデル世代ごとの制約棚卸し）

**トリガー**: Phase 0 で「剪定モード」または「キャッチアップ + 剪定」が選択された場合。

**参照**: `${CLAUDE_SKILL_DIR}/references/pruning-heuristics.md`（剪定カテゴリ C-1〜C-5、判定フロー、レポート形式、対話フロー）

#### P.1: 剪定候補スキャン

各プラグインに対して並列 Agent で以下を走査:

1. `hooks/hooks.json` + `hooks/scripts/*` — C-2（ハーネス重複）候補
2. `skills/*/SKILL.md` — C-1（モデル挙動ガード）、C-4（旧 effort 設定）、C-5（過剰手順）候補
3. `agents/*.md` — C-1、C-4（retired model ID）候補
4. `rules/*.md` / `CLAUDE.md` — C-1、C-3（組み込み置換可能）、C-5 候補

**除外**: `state.json.preservedConstraints` にマークされた項目はスキップ

#### P.2: カテゴリ分類と優先度付与

各候補を C-1〜C-5 に分類し、`pruning-heuristics.md` の判定フローを適用:

1. 決定的検証として残す価値があるか？ → あれば保持 or hook 化
2. 新モデルで自然に守られるか？ → はい なら剪定候補
3. モデル非依存のドメインルールか？ → はい なら保持

優先度:
- **High**: C-2（ハーネス重複、機械的に安全）、C-4（retired ID 等の明確な dead code）
- **Medium**: C-1（挙動ガード、効果測定しづらい）、C-3（組み込み置換）
- **Low**: C-5（ワークフロー簡素化、影響範囲大）

#### P.3: 剪定レポート出力

`pruning-heuristics.md` の「レポート形式」に従って出力。必ず適用前にユーザーへ提示する。

#### P.4: 対話的レビュー（AskUserQuestion）

候補ごとに以下 4 択で確認（`pruning-heuristics.md` の「対話フロー」準拠）:

- **削除する**（推奨・該当行/ファイルを削除）
- **hook 化する**（決定的検証に格上げ → 新規 hook 作成は別途 plugin-dev で）
- **保留**（今回は触らない。次回も候補化）
- **保持する**（永続的に剪定対象外としてマーク → `preservedConstraints` 追加）

候補が 10 件超の場合、High のみ個別確認、Medium/Low は「全件まとめて削除 / 全件保留」の 2 択に集約。

#### P.5: 適用と記録

1. 「削除」選択分を Edit で適用
2. 影響プラグインの `plugin.json` バージョンバンプ（PATCH 相当）
3. 各 `CHANGELOG.md` に `### Removed` セクションで記録
4. `.claude-plugin/marketplace.json` 同期
5. `state.json.prunedConstraints` / `preservedConstraints` に追記
6. 剪定後は `/quality-check` と eval-runner 実行を案内

### Phase 7: 状態更新

キャッチアップ完了後、`${CLAUDE_PLUGIN_ROOT}/skills/cc-catch-up/state.json` を更新:

```json
{
  "lastCatchUpVersion": "2.1.86",
  "lastCatchUpModel": "claude-opus-4-7",
  "lastCatchUpDate": "2026-03-29",
  "lastPruningDate": "2026-03-29",
  "appliedFeatures": ["if-conditional-hooks", "effort-frontmatter", ...],
  "skippedFeatures": ["lsp-server", ...],
  "prunedConstraints": [
    {"id": "dev-workflow/rules/no-grep-bash", "category": "C-1", "reason": "...", "at": "2026-03-29"}
  ],
  "preservedConstraints": [
    {"id": "indie-workflow/SKILL.md/scope-size-warning", "reason": "...", "at": "2026-03-29"}
  ]
}
```

## Reference Files

- **`${CLAUDE_SKILL_DIR}/references/plugin-features.md`** — CC のプラグイン関連機能カタログ（カテゴリ別・バージョン付き）。フルスキャン時のベースライン、および changelog 解析時の分類基準として使用
- **`${CLAUDE_SKILL_DIR}/references/improvement-patterns.md`** — 機能→改善のデシジョンツリーと before/after パターン集。Gap 分析（Phase 4）の判定ロジックとして使用
- **`${CLAUDE_SKILL_DIR}/references/pruning-heuristics.md`** — モデル世代ごとの制約棚卸し基準（C-1〜C-5 カテゴリ、判定フロー、レポート/対話仕様）。Phase P（剪定モード）で使用

## 注意事項

- Changelog 取得に失敗した場合は `plugin-features.md` ベースのフルスキャンにフォールバック
- 改善適用時は既存の pre-commit hook（バージョンバンプ・CHANGELOG 必須）に従う
- `marketplace.json` の同期を忘れないこと
- 適用後は `/quality-check` での検証を推奨
