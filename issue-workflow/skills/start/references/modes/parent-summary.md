## 親 Issue 軽量サマリーモード（BACKEND=linear・子 Issue あり）

最小限の情報を表示し、詳細は `/dashboard` に委譲する。

### Phase P1: 親 Issue の基本情報取得

1. `mcp__linear__get_issue(id={issueId})` で親 Issue のタイトル・ステータスを取得する
2. `mcp__linear__list_issues(parentId={issueId}, limit=50)` で子 Issue 件数とステータス内訳を取得する

### Phase P2: サマリー表示 + 案内

1. 以下の軽量サマリーを表示する:
   ```
   **親 Issue**: [{ISSUE-ID}] {title}
   **ステータス**: {status}
   **子 Issue**: {total}件（完了: {done}, 進行中: {in_progress}, 未着手: {todo}）
   ```
2. 案内を表示する:
   - 「`/dashboard {ISSUE-ID}` で子 Issue の詳細進捗を確認できます」
   - In Progress の子 Issue がある場合: 「`git checkout -b feat/{CHILD-ID}-{desc}` で作業を継続」
   - 全子 Issue が Done の場合: 「全子 Issue 完了。親 Issue のクローズを検討してください。」
