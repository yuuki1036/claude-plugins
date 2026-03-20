---
status: in-progress          # 必須。値: in-progress / completed / canceled
linear: {ISSUE-ID}           # 必須
type: bugfix                 # 必須。値: bugfix / feature / investigation
created: YYYY-MM-DD          # 必須
project: {project-name}      # 任意。Linear プロジェクト名
pr: "#{number}"              # 任意。PR 作成後に記載
parent: {ISSUE-ID}           # 任意。親 Issue
---
# {ISSUE-ID}: {タイトル（Linear から取得）}

## 概要
{Linear Issue の description、なければ手書き}

## 進捗
- [ ] タスク

## 変更ファイル
（実装後に記載）

## 更新履歴
| 日付 | 内容 |
|------|------|
| YYYY-MM-DD | 初回作成 |
