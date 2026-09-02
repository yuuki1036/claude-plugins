# Linear Issue連携

## Issue ID抽出

ブランチ名からパターン `[A-Z]+-[0-9]+` でIssue IDを抽出する。

例:
- `feat/TEAM-123-add-login` → `TEAM-123`
- `fix/PROJ-456` → `PROJ-456`

## 情報取得

### Linear MCP

```
mcp__linear__get_issue(issue_id: "TEAM-123")
→ タイトル、説明、ステータス等を取得

mcp__linear__list_comments(issueId: "TEAM-123", limit: 50)
→ 実装中に決まった仕様変更・スコープ削減・保留理由を取得
```

**2 つはセットで呼ぶ。** Linear の description は起票時のスナップショットで、その後の決定は
コメント側に積まれる。本文だけを材料に description を生成すると、PR の説明が実際の差分と
ずれる（「本文に無いのに直っている」「本文にあるのに入っていない」の両方が起きる）。

返却が `limit` に達した回は古いコメントまで読めていないので、その旨を Step 5 のレポートに
一言添える。黙って最新 50 件だけで結論を出さない。

### タスク詳細ファイル

`.claude/plans/{linearIssueId}.md` が存在する場合、Claude が読んで description 生成の参考にする。このローカルパス自体は PR 本文に出力しない（GitHub からクリックできないため）。

参考にする情報:
- 概要・課題の説明
- 実装計画・調査結果
- 進捗チェックリスト
- 技術的な決定事項

## タイトル生成

Linear Issue が取得できた場合、Issue のタイトル本文のみを PR タイトルとして使用する。Issue ID prefix（`TEAM-123:` 等）はタイトルに含めない。

Issue ID は PR 本文側に記載する（本文に `TEAM-123` と書くと GitHub が Linear への auto-link を生成する、または Linear Issue の URL を明示的に書く）。
