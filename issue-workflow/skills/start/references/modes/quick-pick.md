## Quick Pick モード（BACKEND=linear・Issue ID なしブランチ）

最小限の情報で素早く次のタスクを選べるようにする。

### Phase Q1: アクティブ Issue クイックチェック

1. Grep で `{DATA_DIR}/` 配下の `status: in-progress` を一括検索する
   - `Grep(pattern="status: in-progress", path="{DATA_DIR}/", file_pattern="*.md")`
2. マッチしたファイル数をカウントする（内容は読まない）
3. `{DATA_DIR}/*/follow-ups/*.md` を Glob で列挙し、各ファイルの frontmatter `status: open` をカウントする
4. 表示:
   ```
   アクティブ Issue: {N}件（詳細は `/dashboard`）
   open な follow-up: {M}件
   ```
   - follow-up が0件の場合は行を省略する

### Phase Q2: Next Issue ピック

1. `mcp__linear__list_issues(assignee="me", state="unstarted", limit=5)` を呼び出す
   - 自分にアサインされた未着手 Issue を取得
2. 取得結果を priority フィールドで並べ替える（1=Urgent → 4=Low の順）
3. 候補を提示する:
   ```
   **次に着手できる Issue（優先度順）:**
   1. [{ISSUE-ID}] [{priority}] {title}
   2. ...
   ```

### Phase Q3: アクション提案

- Issue を選択 → `/issue-create`（ブランチは issue-create の Phase 7 で作る。worktree に分けるかもそこで決める）
- 詳細を確認 → `/dashboard`
- プロジェクト同期 → `/linear-maintain`
