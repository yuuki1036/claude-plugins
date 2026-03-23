# フルダッシュボード 出力フォーマット

Phase D1〜D4 の出力レイアウト定義。

## 出力例

```
## Linear ダッシュボード

**ブランチ**: {branch-name}（Issue ID なし）

### プロジェクト一覧
| スラッグ | プロジェクト | ステータス | 最終更新 |
|---------|------------|----------|---------|
| team    | Project Alpha | In Progress | 2026-03-20 |

### アクティブ Issue
**team:**
- [TEAM-123] {title} — In Progress
- [TEAM-456] {title} — In Progress — 7日放置

### Next Issue 候補（優先度順）
1. [TEAM-789] [Urgent] {title}
2. [TEAM-790] [High] {title}

### 次のアクション
- Issue を選択してブランチを作成: `git checkout -b feat/TEAM-789-{desc}`
- `/linear-maintain` でプロジェクト doc を最新化
```
