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
