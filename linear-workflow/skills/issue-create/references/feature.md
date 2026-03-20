---
status: in-progress          # 必須。値: in-progress / completed / canceled
linear: {ISSUE-ID}           # 必須
type: feature                # 必須。値: bugfix / feature / investigation
created: YYYY-MM-DD          # 必須
project: {project-name}      # 任意。Linear プロジェクト名
pr: "#{number}"              # 任意。PR 作成後に記載
parent: {ISSUE-ID}           # 任意。親 Issue
---
# {ISSUE-ID}: {タイトル}

## 概要
{Linear Issue の description}

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
