### 3. Linear Issue連携（該当する場合）

ブランチ名からIssue ID（`[A-Z]+-[0-9]+`パターン）を抽出し：
- `mcp__linear__get_issue` でタイトル・説明を取得し、`mcp__linear__list_comments(issueId, limit=50)` でコメントも取得する。**本文だけで description を書かない** — 実装中に決まった仕様変更・スコープ削減は Linear では本文に反映されずコメント側に残るので、本文だけを材料にすると PR の説明が実際の差分とずれる。返却が limit に達した回は古いコメントを読めていないとレポートに一言添える
- `.claude/plans/{issueId}.md` があれば Claude が読んで description 生成の参考にする。ローカルパス自体は PR 本文に出力しない（レビュアーからクリックできないため）

**Linear MCP が利用できない場合のフォールバック:**
Linear MCP が未設定または接続エラーの場合は、以下の情報のみからPR情報を生成する：
- ブランチ名（Issue IDやタスク名を抽出）
- `git log <base-branch>..HEAD` のコミット履歴
- `git diff <base-branch>...HEAD` の差分内容

Linear連携なしでも基本的なPR作成は問題なく動作する。

詳細は `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/linear-integration.md` を参照。

**次は Step 4**（SKILL.md に戻り、その見出しを見る）
