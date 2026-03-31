---
name: retrospective
description: >
  個人開発の振り返り。完了 Issue の分析、見積もり精度の確認、
  学びの抽出を行う。週次や月次の振り返りに使う。
  トリガー: 「振り返り」「ふりかえり」「retrospective」「レトロ」「/retrospective」
effort: high
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
---

# 振り返り（Retrospective）

## 概要

`.claude/indie/` 内のプロジェクトデータを分析し、指定期間の振り返りレポートを生成する。
完了実績・作業期間・スコープ精度・knowledge 切り出し・技術的負債の増減を定量的に把握し、
Good / Problem / Try の振り返りフレームで対話的に学びを抽出する。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/retrospective` | 過去2週間の振り返り |
| `/retrospective 1w` | 過去1週間の振り返り |
| `/retrospective 1m` | 過去1ヶ月の振り返り |

---

## Phase 1: データ収集

1. `.claude/indie/` 内の全プロジェクトディレクトリを走査
2. 指定期間（デフォルト: 過去2週間）の **completed** Issue を収集
   - `更新履歴` の最新日付、または フロントマターの `last_active` で期間判定
   - フロントマターの `status: completed` で完了判定
3. 同期間の **canceled** Issue も収集
   - フロントマターの `status: canceled` で判定

### 期間の解釈

| 引数 | 期間 |
|------|------|
| `1w` | 過去1週間 |
| `2w`（デフォルト） | 過去2週間 |
| `1m` | 過去1ヶ月 |
| `3m` | 過去3ヶ月 |

---

## Phase 2: 分析

収集したデータから以下の指標を算出する。

### 1. 完了実績

完了 Issue 数と type 別の内訳を集計する:

| type | 説明 |
|------|------|
| feature | 新機能追加 |
| bugfix | バグ修正 |
| investigation | 調査・検証 |
| debt | 技術的負債の解消 |

### 2. 作業期間

各 Issue の `created`（フロントマター）から完了日までの日数を算出:
- 平均日数
- 最短（Issue ID 付き）
- 最長（Issue ID 付き）

### 3. スコープ精度

フロントマターの `scope_size` と、実際の完了タスク数（`[x]` の数）を比較:

| scope_size | 想定タスク数 |
|------------|-------------|
| small | 3個以下 |
| medium | 4〜7個 |
| large | 8個以上 |

判定ロジック:
- 宣言が small で実際5個以上 → **スコープ膨張**
- 宣言が medium で実際3個以下 → **過大見積もり**
- 宣言が medium で実際8個以上 → **スコープ膨張**
- 宣言が large で実際5個以下 → **過大見積もり**
- それ以外 → **適正**

### 4. knowledge 切り出し

期間中に作成された knowledge ファイル数をカウント:
- `.claude/indie/*/knowledge/` 配下のファイルを対象
- ファイルの作成日（`git log` またはフロントマターの日付）で期間判定

### 5. 技術的負債（debt）の増減

- 期間中に新規作成された debt Issue 数
- 期間中に完了した debt Issue 数
- 現在残っている debt Issue 数（全期間）

---

## Phase 3: 振り返りフレーム

分析結果を提示した後、ユーザーに以下を問いかけて対話的に振り返りを促す:

1. **Good**: うまくいったこと、効率的だったアプローチ
2. **Problem**: 困ったこと、時間がかかったこと
3. **Try**: 次にやってみたいこと、改善したいこと

- 各項目について1つずつ質問する（一度に全部聞かない）
- ユーザーの回答を受けて、分析データと照らし合わせた気づきがあればコメントする
- ユーザーが「特になし」「スキップ」と言った場合は次に進む

---

## Phase 4: レポート保存

振り返り結果を `.claude/indie/retrospectives/YYYY-MM-DD.md` に保存する。

- テンプレートは以下を参照:
  → Read `${CLAUDE_SKILL_DIR}/references/retrospective-template.md`
- ディレクトリが存在しない場合は作成する
- 保存前にレポート内容をユーザーに提示し、承認を得る

---

## 処理フロー

```
1. 引数から期間を解釈（デフォルト: 2w）
2. .claude/indie/ 内の全プロジェクトを走査
3. 期間内の completed / canceled Issue を収集
4. Phase 2 の各指標を算出
5. 分析結果をユーザーに提示
6. Phase 3 の振り返りフレーム（Good → Problem → Try の順に対話）
7. テンプレートに沿ってレポートを生成
8. レポート内容をユーザーに提示し、承認を得る
9. .claude/indie/retrospectives/YYYY-MM-DD.md に保存
```

---

## 注意事項

- データが少ない場合（完了 Issue が0件など）でも振り返りフレームは実施する
- canceled Issue は完了実績には含めず、別途「キャンセル: X件」として報告する
- スコープ精度は `scope_size` フロントマターがない Issue はスキップする
- 過去のレトロスペクティブとの比較は行わない（将来拡張として検討）
