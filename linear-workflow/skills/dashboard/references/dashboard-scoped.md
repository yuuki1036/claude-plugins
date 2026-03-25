# スコープドダッシュボード 出力フォーマット

Phase S1〜S4 の出力レイアウト定義。

## 出力例

```
## Linear スコープドダッシュボード

**親 Issue**: [{ISSUE-ID}] {parent-title}
**ブランチ**: {branch-name}
**進捗**: {done}/{total} 件完了

### 子 Issue 一覧

**In Progress:**
- [{CHILD-ID}] {title}

**Todo:**
- [{CHILD-ID}] {title} [ファイルあり]
- [{CHILD-ID}] {title}

**Done:**
- [{CHILD-ID}] {title}

### Next Issue 候補（子 Issue / 優先度順）
1. [{CHILD-ID}] [High] {title}

### 次のアクション
- `git checkout -b feat/{CHILD-ID}-{desc}` でブランチ作成
- `/issue-create` で Issue ファイルを作成
```
