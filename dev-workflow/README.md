# dev-workflow

Git 操作・PR 作成・UI 動作確認・git worktree 並列環境セットアップを束ねた開発ワークフロープラグイン。原子性重視のコミット、Linear Issue 連携 PR、chrome-devtools MCP による UI 自動化、worktree 単位の DB / port 分離をサポートする。

## コマンド一覧

| コマンド | 対応スキル | 役割 |
|----------|-----------|------|
| `/commit` | git-commit-helper | 変更を分析して原子性重視の高品質コミットを作成 |
| `/pr` | pr-creator | 差分とコミット履歴からドラフト PR を自動作成 |
| `/ui-verify` | ui-verify | Web UI の動作確認・スタイル調整・スクリーンショット取得 |

worktree-setup / worktree-teardown はコマンドを持たず、トリガーフレーズまたはスキル直接呼び出しで起動する。

## 含まれるスキル

### git-commit-helper

原子性を重視した高品質な Git コミットを作成するスキル。変更を分析して論理的な作業単位に分割し、Conventional Commits 準拠の日本語メッセージでコミットする。

- Protected branch の安全性チェック
- 変更の自動分割判定（1 コミット = 1 作業単位）
- ファイル単位での `git add <file>` によるステージング
- Conventional Commits 準拠の日本語コミットメッセージ生成（subject 行の品質規約つき）
- writing-polish soft 連携（opt-in）でコミットメッセージを推敲

**トリガー例**: 「コミットして」「変更をコミット」「/commit」

**引数**: `--no-protect`（Protected branch への直接コミット許可） / `--with-push`（コミット後に自動プッシュ）

### pr-creator

差分とコミット履歴から description を自動生成してドラフト PR を作成するスキル。Linear Issue 連携にも対応。

- リポジトリの PR テンプレート自動検出・準拠
- ブランチ名から Linear Issue ID を抽出して情報を取得
- 概要を What / Why / Outcome の三要素で記述（字数制約と両立）
- gitignored パス・ローカル限定ドキュメント参照の検出
- 常にドラフト PR として作成

**トリガー例**: 「PR 作って」「プルリクエスト作成」「/pr」

### ui-verify

chrome-devtools MCP を使って Web UI の動作確認・スタイル調整・スクリーンショット取得を自動化するスキル。dev server の起動確認から console / network エラー監視、複数 viewport 撮影まで一貫サポートする。

- `verify`: 動作確認（console / network エラー検知、主要シナリオ smoke test）
- `tune`: スタイル調整ループ（撮影 → 編集 → リロード → 再撮影）
- `snap`: スクリーンショット収集（デフォルト desktop 1 枚、`--viewports=...` で複数 viewport 撮影）
- dev server はセッション中保持し、タスク完了ごとの再起動を避ける
- 複数ステップの E2E が必要な場合は公式 skill `webapp-testing` へ委譲

**トリガー例**: 「動作確認」「UI チェック」「スクリーンショット」「スタイル調整」「レスポンシブ確認」「/ui-verify」

**引数**: `[verify|tune|snap] [target-url-or-path]`

### worktree-setup

git worktree ベースの並列開発環境をセットアップするスキル。worktree 名から DB 名と port を動的に導出し、メイン clone および他 worktree との衝突を防ぐ。Claude Code を複数並列で走らせる際の DB レコード競合・port 衝突の回避に使う。

- 3 状態判定（main / worktree-ready / worktree-unconfigured）で分岐
- worktree 名から DB 名・backend / frontend / db port を動的割当
- worktree 用 env ファイル（`envs/*.worktree`）を実 env と分離して書き出し
- DB 作成・マイグレーションは必ずユーザー確認を取ってから実行

**トリガー例**: 「worktree 作成」「並列開発環境セットアップ」「worktree セットアップ」「/worktree-setup」

### worktree-teardown

`worktree-setup` で作った worktree 環境を安全に破棄するスキル。DB drop / port 解放 / env クリーンアップを cleanup チェックリストで順次確認し、teardown 漏れ（DB drop 失敗・port leak）を WARNING で検知する。

- プロセス停止 / DB drop / port 解放 / env マーカー削除 / uncommitted 確認 / git worktree remove の 6 項目チェックリスト
- DB drop・プロセス kill・`--force` 削除は必ずユーザー確認を取ってから実行
- 兄弟 worktree の port は kill 対象にしない

**トリガー例**: 「worktree 破棄」「worktree 削除」「並列開発環境クリーンアップ」「/worktree-teardown」

## chrome-devtools MCP の同梱

ui-verify が使う chrome-devtools MCP は `.mcp.json` で同梱配布される。プラグインインストールで自動的に MCP サーバーが有効化され、起動時のツールロード往復を抑えるため `alwaysLoad: true` を設定している。

## Event Bus 連携

git commit が成功すると、PostToolUse hook（`git commit *` matcher）が `commit:created` イベントを Event Bus（`.claude/events.jsonl`）に publish する。payload は `{"sha":"<short>","type":"<conventional commit type>","files":<count>}`。`--amend` / `--dry-run` 系は除外する。

## 使い方

- コミット作成: 「コミットして」「変更をコミット」と伝える
- PR 作成: 「PR 作って」「プルリクエスト作成」と伝える
- UI 動作確認: 「動作確認」「スクリーンショット」と伝える
- 並列開発環境: 「worktree 作成」「worktree 破棄」と伝える

## Linear MCP 連携（オプション）

pr-creator スキルは Linear MCP と連携して、ブランチ名から Linear Issue の情報を自動取得できる。この連携は**オプション**であり、未設定でもブランチ名とコミット履歴から PR 情報を生成する。

## PostToolUse 自動 lint チェーン（opt-in）

`.claude/dev-workflow.json` の `lint.enabled=true` 時のみ、Edit / Write / MultiEdit で `fmt-fix → lint-fix → check` の 3 段を実行する。fix 段は黙って直し、check 段で残った違反だけを Claude に返す。未設定時は完全に dormant。設定スキーマは `references/lint-config.md` を参照。

## TDD Phase Gate（opt-in）

実装ファイル編集時に対応テストが存在するかチェックし、Red phase 逸脱を PreToolUse hook で警告する（ブロックはしない）。

**有効化:**
```bash
mkdir -p .claude && touch .claude/.tdd-phase-gate-enabled
```

**無効化:**
```bash
rm .claude/.tdd-phase-gate-enabled
```

**検知ロジック:**
- 実装ファイル（`*.ts/tsx/js/jsx/py/go/rb/vue/svelte` 等）の Edit / Write / MultiEdit 時に発動
- 同階層または `__tests__/` / `tests/` 配下に対応するテストファイル（`*.test.*` / `*.spec.*` / `test_*` / `*_test.*`）が無ければ警告
- テストファイル自身・設定ファイル（`*.config.*`）・型定義（`*.d.ts`）・Storybook（`*.stories.*`）・新規 Write は対象外
- false positive は許容（ブロックせず reminder のみ）

## 環境変数

| 変数 | 説明 |
|------|------|
| `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` | Claude 組み込みの git commit/PR 指示を無効化。dev-workflow の独自指示との競合を防止する |

## Linear MCP 連携の設定

Linear MCP を有効にするには、`.mcp.json` または Claude Code の設定に以下を追加する：

```json
{
  "mcpServers": {
    "linear": {
      "command": "npx",
      "args": ["-y", "@anthropic/linear-mcp-server"],
      "env": {
        "LINEAR_API_KEY": "<your-linear-api-key>"
      }
    }
  }
}
```
