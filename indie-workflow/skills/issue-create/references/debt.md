---
status: in-progress          # 必須。値: in-progress / completed / canceled
id: {ISSUE-ID}               # 必須。例: MYAPP-3
type: debt                   # 必須。値: bugfix / feature / investigation / debt
scope_size: small            # 必須。値: small / medium / large
created: YYYY-MM-DD          # 必須
last_active: YYYY-MM-DD      # 必須
pr: ""                       # 任意。PR 作成後に記載
---
# {ISSUE-ID}: {タイトル}

## 概要
{何が負債か、なぜ発生したか}

## 影響範囲
{どのコード/機能に影響するか}

## 放置リスク
{放置するとどうなるか。低/中/高}

## 対応方針
{どう解消するか}

## 進捗
- [ ] タスク

## 変更ファイル
（実装後に記載）

## 更新履歴
| 日付 | 内容 |
|------|------|
| YYYY-MM-DD | 初回作成 |
