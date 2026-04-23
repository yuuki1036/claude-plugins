# dev-workflow

Git操作とPR作成の開発ワークフロープラグイン。原子性重視のコミットとLinear Issue連携PR作成をサポートする。

## 含まれるスキル

### git-commit-helper

原子性を重視した高品質なGitコミットを作成するスキル。変更を分析して論理的な作業単位に分割し、Conventional Commits準拠の日本語メッセージでコミットする。

- Protected branchの安全性チェック
- 変更の自動分割判定（1コミット = 1作業単位）
- ファイル単位での `git add <file>` によるステージング
- Conventional Commits準拠の日本語コミットメッセージ生成

### pr-creator

差分とコミット履歴からdescriptionを自動生成してPRを作成するスキル。Linear Issue連携にも対応。

- リポジトリのPRテンプレート自動検出・準拠
- ブランチ名からLinear Issue IDを抽出して情報を取得
- タスク詳細ファイル（`.claude/plans/`）の活用
- 常にドラフトPRとして作成

## 使い方

- コミット作成: 「コミットして」「変更をコミット」と伝える
- PR作成: 「PR作って」「プルリクエスト作成」と伝える

## Linear MCP 連携（オプション）

pr-creator スキルは Linear MCP と連携して、ブランチ名から Linear Issue の情報を自動取得できます。この連携は**オプション**であり、未設定でもブランチ名とコミット履歴からPR情報を生成します。

## TDD Phase Gate（opt-in）

実装ファイル編集時に対応テストが存在するかチェックし、Red phase 逸脱を PreToolUse hook で警告します（ブロックはしません）。

**有効化:**
```bash
mkdir -p .claude && touch .claude/.tdd-phase-gate-enabled
```

**無効化:**
```bash
rm .claude/.tdd-phase-gate-enabled
```

**検知ロジック:**
- 実装ファイル（`*.ts/tsx/js/jsx/py/go/rb/vue/svelte` 等）の Edit/Write/MultiEdit 時に発動
- 同階層または `__tests__/` / `tests/` 配下に対応するテストファイル（`*.test.*` / `*.spec.*` / `test_*` / `*_test.*`）が無ければ警告
- テストファイル自身・設定ファイル（`*.config.*`）・型定義（`*.d.ts`）・Storybook（`*.stories.*`）・新規 Write は対象外
- false positive は許容（ブロックせず reminder のみ）

## 環境変数

| 変数 | 説明 |
|------|------|
| `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` | Claude 組み込みの git commit/PR 指示を無効化。dev-workflow の独自指示との競合を防止する |

## Linear MCP 連携の設定

Linear MCP を有効にするには、`.mcp.json` または Claude Code の設定に以下を追加してください：

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
