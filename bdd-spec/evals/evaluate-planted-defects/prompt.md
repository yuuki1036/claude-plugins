---
max_turns: 20
allowed_tools: [Read, Glob, Grep, Skill]
---

次の BDD spec を評価してください。ファイルは手元に無いので、以下に貼った 2 ファイルの本文をそのまま評価対象にしてください（パスは `features/login-lockout/spec.md` と `features/login-lockout/epic.md` とみなす。`common_spec.md` / `all_spec.md` / `.claude/bdd-spec.json` は存在しない前提で、その不在は指摘しなくてよい）。同値分割表と Scenario の対応漏れ、epic.md の受入条件との対応も見てください。

修正の適用は不要です。評価レポートだけ出してください。

## features/login-lockout/spec.md

~~~markdown
---
last-validated: 2026-09-01
phase: current
role: 一般ユーザー
epic: ./epic.md
---

# Feature: 連続ログイン失敗でアカウントを一時ロックする

> User story: Userは、**一般ユーザー** として、**パスワードを連続で間違えたときに第三者の総当たりから守られ** たい
> Why: 詳細は [epic.md](./epic.md) を参照

## Background

- 共通仕様は [../common_spec.md](../common_spec.md) を参照
- 用語定義は [../all_spec.md](../all_spec.md) を参照

このフィーチャー固有の前提:

```gherkin
Given 登録済みユーザー alice が存在する
And alice の失敗回数は 0 である
```

---

## Scenarios

### Scenario 1: 5 回目の失敗でロックされる

> Trace: [epic.md AC-1](./epic.md#acceptance-criteria受入条件)

```gherkin
Given alice の失敗回数が 4 である
When alice が誤ったパスワードでログインする
Then ログインは拒否される
And alice は 15 分間ロックされる
And 「アカウントがロックされました。15 分後に再試行してください」と表示される
```

**カバーする因子**: 失敗回数=正常範囲（上限）, パスワード=誤り

---

### Scenario 2: ロック中は正しいパスワードでも拒否される

> Trace: [epic.md AC-2](./epic.md#acceptance-criteria受入条件)

```gherkin
Scenario Outline: ロック中のログイン試行
  Given alice がロックされてから <elapsed> 分経過している
  When alice が正しいパスワードを入力し、ログインボタンを押して、ダッシュボードを開く
  Then 結果は <expected> になる

  #### Examples

  | minutes | expected              | 因子           |
  |---------|-----------------------|----------------|
  | 0       | 拒否（残り 15 分）    | 経過時間=下限  |
  | 14      | 拒否（残り 1 分）     | 経過時間=境界内 |
```

**カバーする因子**: 経過時間=ロック中, パスワード=正しい

---

## 同値分割・境界値分析表

| 因子 | 同値クラス | 代表値 | カバー Scenario |
|------|-----------|--------|------------------|
| 失敗回数 | 正常範囲（上限） | 4 → 5 | Scenario 1 |
| 失敗回数 | 正常範囲（中央） | 2 | Scenario 1 |
| 経過時間 | ロック中（下限） | 0 分 | Scenario 2 |
| 経過時間 | ロック中（境界内） | 14 分 | Scenario 2 |
| パスワード | 正しい | - | Scenario 2 |
| パスワード | 誤り | - | Scenario 1 |
| パスワード | 空 / null | (empty) | Scenario 4 |

## トレーサビリティ

| AC | Scenario | カバー因子 |
|----|----------|------------|
| AC-1 | Scenario 1 | 失敗回数（上限）, パスワード（誤り） |
| AC-2 | Scenario 2 | 経過時間（ロック中）, パスワード（正しい） |

---

## エラーケース

| エラーID | 発生条件 | メッセージ | 対応 |
|----------|---------|-----------|------|
| ERR-LOCK-001 | ロック中のログイン試行 | アカウントがロックされています。あと {n} 分後に再試行してください | 待つ |

## 用語

- 失敗回数: 直近の成功以降に連続して失敗した回数

## 関連

- 依存フィーチャー: なし
- 後続フィーチャー: 管理者によるロック解除
~~~

## features/login-lockout/epic.md

~~~markdown
---
last-validated: 2026-09-01
phase: current
role: 一般ユーザー
---

# Epic: 連続ログイン失敗でアカウントを一時ロックする

## User Story

Userは、**一般ユーザー** として、**パスワードを連続で間違えたときに第三者の総当たりから守られ** たい。

## Why（動機）

現状はログイン失敗回数に上限が無く、総当たり攻撃を止める仕組みが無い。監査で指摘を受けており、次のリリースまでに一時ロックを入れる必要がある。

## What（成果物の輪郭）

このエピックが完了した時、以下が達成されている:

- [ ] 5 回連続で失敗すると 15 分間ログインできなくなる
- [ ] ロック中は正しいパスワードでもログインできず、残り時間を含むメッセージが出る
- [ ] ロック解除後にログインに成功すると失敗回数が 0 に戻る

## Acceptance Criteria（受入条件）

以下の Scenario が `spec.md` で定義され、全て pass する:

- [ ] AC-1: 5 回目の失敗でロックされる → `spec.md:#scenario-1`
- [ ] AC-2: ロック中は正しいパスワードでも拒否される → `spec.md:#scenario-2`
- [ ] AC-3: ロック解除後の成功で失敗回数がリセットされる → `spec.md:#scenario-3`

## スコープ外

- 管理者による手動ロック解除
- CAPTCHA の導入
- ロック発生のメール通知

## 関連 epic

- 依存: なし
- 後続: 管理者によるロック解除

## 用語

- ロック: 一定時間ログイン試行を受け付けない状態
~~~
