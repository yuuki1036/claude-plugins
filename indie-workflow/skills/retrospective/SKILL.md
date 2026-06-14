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
  - Bash
---

# 振り返り（Retrospective）

## 概要

`.claude/indie/` 内のプロジェクトデータを分析し、指定期間の振り返りレポートを生成する。
完了実績・作業期間・スコープ精度・knowledge 切り出し・技術的負債の増減を定量的に把握し、
反復テーマからは概念ページ（concept）への統合を提案する。
Good / Problem / Try の振り返りフレームで対話的に学びを抽出する。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/retrospective` | 過去2週間の振り返り |
| `/retrospective 1w` | 過去1週間の振り返り |
| `/retrospective 1m` | 過去1ヶ月の振り返り |

---

## Phase 1: データ収集

### Source 1: Event Bus（優先、軽量）

`.claude/events.jsonl` が存在する場合、まず Event Bus から完了 Issue を収集する。`on-issue-change.sh` hook が status: completed への遷移を即時記録しているため、ファイル更新日のヒューリスティックより信頼度が高い。

```bash
# 直近 200 件の issue:completed イベントを取得
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null
event_bus_tail "issue:completed" 200
```

各行は JSON Lines 形式: `{"ts":"<ISO8601>","plugin":"...","event":"issue:completed","payload":{"issue_id":"...","slug":"...","file":"..."}}`

- 期間フィルタ: `ts` を指定期間と比較
- dedup: 同じ `issue_id` + `slug` の組合せが複数イベントある場合、最新の ts を採用（同 Issue で status が toggle した想定）
- payload の `file` を直接 Read することで、Issue ファイルの詳細（type / scope_size / 完了タスク数）を取得

### Source 2: Issue ファイル走査（fallback / 補完）

events.jsonl が存在しない、または直近のイベントが期間より古い場合（hook 導入前の Issue を含めたい場合）は以下にフォールバックする。

1. `.claude/indie/` 内の全プロジェクトディレクトリを走査
2. 指定期間（デフォルト: 過去2週間）の **completed** Issue を収集
   - `更新履歴` の最新日付、または フロントマターの `last_active` で期間判定
   - フロントマターの `status: completed` で完了判定
3. 同期間の **canceled** Issue も収集
   - フロントマターの `status: canceled` で判定

### Source 3: failure:logged（再発失敗、任意）

failure-journal プラグインが publish する `failure:logged` イベントを振り返りの素材として取り込む。failure-journal 未導入でも壊れないよう graceful に扱う。

```bash
# 直近 200 件の failure:logged イベントを取得（events.jsonl / イベントが無ければ空を返す）
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null
event_bus_tail "failure:logged" 200
```

各行は JSON Lines 形式: `{"ts":"<ISO8601>","plugin":"failure-journal","event":"failure:logged","payload":{"tag":"...","...":"..."}}`

- 期間フィルタ: `ts` を指定期間と比較
- `.claude/events.jsonl` が無い / `failure:logged` イベントが 0 件の場合は何も取得できないので、この Source 全体を **graceful に skip** する（failure-journal 未導入の前提で動く）
- payload の `tag`（kebab-case の現象タグ）を Phase 2 の「再発失敗パターン」集計に渡す

### Source 統合

両 Source から取得した Issue を `slug + issue_id` で dedup する。Event Bus 側で取得できた Issue は file 経由で詳細を Read し、ファイル走査側のヒューリスティック判定をスキップしてよい（より高速）。canceled は Event Bus には現状流れないため、Source 2 のロジックで補う。

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

### 6. 前回 retro との比較

`.claude/indie/retrospectives/*.md` を Glob で列挙し、最新 1 件（今回生成前の最終ファイル）を Read する。存在しない場合はスキップ。

前回の `Try` セクションの各項目について、今回の期間内の Issue / knowledge / Good / Problem を参照して以下を判定する:

| 前回 Try の状態 | 判定 |
|----------------|------|
| 今回 Good に同系のテーマが出現 | ✅ 改善が効いた |
| 今回 Problem に同系のテーマが再出 | ⚠️ 未解決 |
| どちらにも現れない | ❓ 忘れられた可能性 |

キーワード照合は単純な部分一致でよい（完全な NLP は不要）。

### 7. 反復テーマの検出と概念ページ化

期間中に作成された source（`.claude/indie/*/knowledge/*.md`、`concepts/` 配下は除く）のフロントマター `tags:` を集計する。

- 同じタグが 2 件以上の source に現れた場合、反復テーマとして警告
- `tags` がない knowledge は集計対象外
- **既存 concept の照合**: その反復タグを扱う概念ページ（`knowledge/concepts/*.md`）が既にあるか確認する
- 警告フォーマット:
  ```
  🔁 反復警告
    - タグ「{tag}」が {N} 件の source に現れています:
      - {knowledge-file-1.md}
      - {knowledge-file-2.md}
    - 横断する共通パターン・根本原因がある可能性があります。
    - {既存 concept があれば「→ 概念ページ concepts/{xxx}.md が関連します」を併記}
  ```

反復テーマは「複数 source を横断する共通テーマ」であり、概念ページ（concept）に統合する最有力候補。Phase 2.5 で concept 化を提案する。

閾値（デフォルト 2 件）は SKILL.md のこの定義に従う。

### 8. 再発失敗パターン（任意・failure:logged）

Phase 1 の Source 3 で取得した `failure:logged` イベントを集計する（取得できなかった場合はこの指標全体を skip）。

- 期間内の `failure:logged` を payload の `tag` 別に件数集計する
- 同一 `tag` が **3 回以上**再発しているものを「再発失敗パターン」として振り返りで取り上げる
- 報告フォーマット例:
  ```
  ⚠️ 再発失敗パターン
    - タグ「{tag}」が期間内に {N} 回記録されています
  ```

**責務の境界**: retrospective は再発失敗を**振り返りの素材として提示するだけ**にとどめる。「この失敗を CLAUDE.md / hook / skill のどこに反映すべきか」という規約還流の提案は `failure-journal:retro` の責務であり、ここでは行わない（重複を避ける）。3 回以上のパターンを見つけたら `failure-journal:retro` の実行を案内するに留める。

---

## Phase 2.5: 概念ページ化の提案

反復テーマ（Phase 2 の指標 7）で検出した「横断する共通タグ」は、複数 source を繋いで初めて見える知見＝概念ページ（concept）の素材になる。要約の寄せ集めではなく「繋げる」ことが knowledge の価値の本体であり、retrospective はその俯瞰的な発見の場として機能する。

### 提案ロジック

反復タグごとに次を判定して提案する:

1. **既存 concept がある**: その concept に未統合の source があれば、`/indie-issue-maintain` の波及フロー（「関連ソース」への `[[ ]]` 追加・「横断的知見」更新）を案内する
2. **既存 concept が無い & 該当 source が 2 件以上**: 新規概念ページの作成を **AskUserQuestion** で提案する
   - question: "反復テーマ「{tag}」を概念ページ（concept）に統合しますか？"
   - header: "概念ページ化"
   - options:
     1. label: "ドラフト作成" / description: "concepts/{tag}.md のドラフトを作り、関連 source を [[ ]] で繋ぐ"
     2. label: "あとで" / description: "提案だけ残してレポートに記録"
     3. label: "不要" / description: "概念ページ化しない"

### ドラフト作成

「ドラフト作成」が選ばれた場合、`.claude/indie/{slug}/knowledge/concepts/{concept-slug}.md` を作成する:

- セクション構成・frontmatter（`kind: concept`）は indie-issue-maintain スキルの「概念ページへの波及」節のテンプレートに従う
- 「関連ソース」に反復タグを持つ source を `[[name]] — 観点` で列挙する
- 「横断的知見」は反復 source を読んで共通パターン・矛盾を埋める。埋められない部分は「未解決の問い」に回す
- 作成後 `knowledge/index.md` を更新する（ファイル列は `concepts/{slug}.md`）
- 作成前に内容をユーザーに提示し承認を得る

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
2. .claude/events.jsonl の issue:completed を期間フィルタで収集（Source 1）
3. .claude/indie/ 内の全プロジェクトを走査して期間内の completed/canceled Issue を収集（Source 2、Event Bus に無い分の補完 + canceled 対応）
4. .claude/events.jsonl の failure:logged を期間フィルタで収集（Source 3、任意。events.jsonl / イベントが無ければ skip）
5. Source 1 と Source 2 を slug+issue_id で dedup・統合
6. Phase 2 の各指標（1〜8）を算出
   - 前回 retro との比較（6）: retrospectives/ を Glob で列挙し最新 1 件と照合
   - 反復テーマ検出（7）: 期間中の source の tags を集計（`concepts/` は除外）
   - 再発失敗パターン（8）: Source 3 の failure:logged を tag 別集計（3 回以上のみ取り上げ。取得不可なら skip）
7. 分析結果をユーザーに提示（反復警告・再発失敗・前回比較を冒頭で目立たせる）
8. Phase 2.5 概念ページ化の提案（反復テーマを concept に統合するか。承認時はドラフト作成 + index.md 更新）
9. Phase 3 の振り返りフレーム（Good → Problem → Try の順に対話）
10. テンプレートに沿ってレポートを生成
11. レポート内容をユーザーに提示し、承認を得る
12. .claude/indie/retrospectives/YYYY-MM-DD.md に保存
```

---

## 注意事項

- データが少ない場合（完了 Issue が0件など）でも振り返りフレームは実施する
- canceled Issue は完了実績には含めず、別途「キャンセル: X件」として報告する
- スコープ精度は `scope_size` フロントマターがない Issue はスキップする
- 前回 retro との比較は最新 1 件のみ対象とする（複雑化を避けるため、それ以上の履歴比較は別機能）
- 初回実行（過去ファイルなし）の場合は前回比較セクションをスキップする
