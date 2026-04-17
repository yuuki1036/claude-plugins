---
status: in-progress          # 必須。値: in-progress / completed / canceled
id: {ISSUE-ID}               # 必須。例: MYAPP-3
type: feature                # 必須。値: bugfix / feature / investigation / debt
scope_size: {size}           # 必須。値: small / medium / large
created: YYYY-MM-DD          # 必須
last_active: YYYY-MM-DD      # 必須
pr: ""                       # 任意。PR 作成後に記載
---
# {ISSUE-ID}: {タイトル}

## 概要
{機能の説明・目的}

## 調査結果
{コードベースの調査で分かったこと}

## 計画
{実装アプローチ、設計判断と理由}

## スコープ外
{意図的に除外するもの（別 Issue 候補）}

## 進捗
- [ ] タスク

## 変更ファイル
（実装後に記載）

## 備考
{作業中の副次的な発見}

## 更新履歴
| 日付 | 内容 |
|------|------|
| YYYY-MM-DD | 初回作成 |

---

## 即クローズケースの書き方

Issue 起票後に実装せずにクローズする場合（「すでに実装済みだった」「要件が変わった」「別アプローチで解決した」など）、以下の構造で経緯を残す。

`status: completed` は維持したまま、本文セクションを次のように置き換える:

```markdown
## 結論
{なぜクローズしたかの 1-2 文。例: Home ページは既に Hero / Works / Shop セクションが実装済みと判明}

## スコープ外
{仮に将来やるならこの部分、という切り出し候補。例: ファーストビューの微調整は別 Issue}

## 備考
{学び、再発防止ポイント。例: 起票前に page.tsx を読むべきだった}
```

- `canceled` とは異なる扱い（`completed` のまま経緯だけを残すパターン）
- キャンセル理由は `projects doc` の備考に必ず残す
