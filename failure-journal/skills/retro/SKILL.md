---
name: retro
description: >
  failure journal を集計し、直近 30 日で同一 tag が 3 回以上再発したパターンを抽出して規約還流提案を生成する。
  集計前に candidates.jsonl（セッション中の自己訂正を Claude 自身が記録した候補）をレビューして journal に昇格し、
  候補が無い期間は transcript サルベージにフォールバックして取りこぼしを回収する。
  閾値超え tag ごとに「AGENTS.md/CLAUDE.md・hook・skill のどれに反映すべきか」と「既存ガードレールでカバーできていない理由」を出力する。
  トリガー: 「retro」「振り返り集計」「再発パターン抽出」「failure 集計」
  「同じ失敗を何回踏んだ」「規約還流」「未起票の失敗を拾って」「/retro」
effort: medium
allowed-tools:
  - Read
  - Bash
  - Agent
  - AskUserQuestion
---

# Retro

failure journal を集計し、再発する失敗パターンを検出して規約還流（AGENTS.md/CLAUDE.md・hook・skill）を提案するスキル。責務は「再発パターンの検出と還流」であり、主観的なセッション振り返りは対象外（`issue-workflow:retrospective` の責務）。

詳細仕様は `references/` を参照:

- `references/aggregation-rules.md` — 集計窓・閾値・jq 集計コマンド（macOS/Linux 両対応）/ 還流先判定ルール
- `references/transcript-salvage.md` — transcript 走査による未起票失敗のサルベージ手順・precision・制約

---

## Phase 0: journal 読み込み

1. journal パス: `.claude/failure-journal/journal.jsonl`
2. **journal の Read は retro 実行中のみ**（fingerprint の AI 出力汚染を避ける運用。README 参照）
3. ファイルが存在しない or 空でも終了しない（Phase 0.5 のサルベージで起票される可能性があるため）。空の場合はその旨を記録して Phase 0.5 へ進む

---

## Phase 0.5: 候補レビュー（candidates → journal 昇格）

log-failure は手動起票のため、**Claude が自己訂正した失敗は人間の目に触れず journal に入らない**（実測の起票率 ≒2.5%）。このギャップは SessionStart hook が注入する自己申告ルール（`rules/self-report-rule.md`）で埋める: Claude は自己訂正した瞬間に `.claude/failure-journal/candidates.jsonl` へ候補を 1 行 append しており、本 Phase はその候補を承認レビューで journal に昇格する。

1. `candidates.jsonl` の `verdict: null` 行を読み込む（ファイル不在・0 件なら Phase 0.6 へ）
2. 各候補を log-failure と同じ単一基準（**同じ状況で再発しうるか**）で REAL / NOISE に分類し、一覧提示して承認を得る
3. 承認された REAL は tag 規約（`../log-failure/references/journal-schema.md`）に従って tag を付与し journal へ append する。`timestamp` は候補の `ts` を使う。既存 journal とは tag の意味的一致で重複排除する
4. **レビューした全行に verdict を書き戻す**（`accepted` / `rejected`）。却下候補が次回 retro で再浮上するのを防ぐ（旧 transcript サルベージ設計の既知の穴への対処）
   - `candidates.jsonl` は journal と違い append-only ではない。ただし許可されるのは **verdict フィールドの書き戻しのみ**（行の削除・summary の書き換えはしない）

> candidates が 1 件以上あった場合、Phase 0.6 のサルベージは既定でスキップする（自己申告ルールが機能している環境では、precision 35% の transcript 走査を重ねる価値が薄い）。

## Phase 0.6: transcript サルベージ（フォールバック）

以下の**いずれか**の場合のみ実行する（該当しなければ skip して Phase 1 へ）:

- 引数 `--salvage` が明示された（candidates と併用して網羅性を上げたいとき）
- Phase 0.5 の候補が 0 件だった（自己申告ルール導入前の期間・ルール未浸透環境の後方互換）

手順の詳細は `references/transcript-salvage.md`。要点:

1. `~/.claude/projects/<cwd の / を - に置換>/` 配下の transcript を、集計窓と同じ期間で対象にする
2. assistant 発話を抽出する。**`isSidechain != true` で subagent の発話を除外**（除外しないと agent プロンプトが大量に誤検出される）
3. 自己訂正シグナルを grep で絞る
4. **LLM で REAL / NOISE を分類**する（grep の precision は約 35%）。判定軸は log-failure と同じ「同じ状況で再発しうるか」の単一基準
5. **並列分類した場合は tag を正規化する**（必須）。並列 agent は互いの語彙を見ないため同一の失敗に別 tag が付き、分散したままだと閾値 3 回に届かず還流提案が出ない
6. 既存 journal と重複排除する（tag の意味的一致で判定。timestamp は起票時刻であり失敗発生時刻とは限らない）
7. REAL 候補を一覧提示し、**承認を得てから append** する

> **自動 append は禁止。** precision 35% で誤起票すると journal が汚れ、閾値集計の信頼性を直接損なう。
> append する `timestamp` はサルベージ実行時刻ではなく、**失敗が発生した transcript 上の時刻**を使う（窓集計の正確性のため）。

### effort 適応（`${CLAUDE_EFFORT}`）

走査と分類は effort で深さを変える。現在の effort は `${CLAUDE_EFFORT}`。

| effort | 走査窓 | 分類 |
|---|---|---|
| low / medium | 集計窓を上限 7 日に縮める | 逐次分類のみ（Agent 並列化しない）。候補 30 件超なら上位のみ提示し、打ち切った件数を明示する |
| high（既定） | 集計窓どおり（既定 30 日） | 候補 30 件超で Agent 並列分類 + tag 正規化 |
| xhigh / max | 集計窓どおり | 全件を Agent 並列分類。バッチを細かく割り、tag 正規化を独立コンテキストで実行する |

> Agent を並列起動するときは各 call に **`run_in_background: false` を必ず明示**する。CC 2.1.198+ は既定が background のため、省略すると分類結果が揃う前に tag 正規化・承認フェーズへ進んでしまう。

> **打ち切りは必ず可視化する**（`log()` 相当の明示）。黙って上位 N 件に絞ると「これで全部」と読まれる。

引数 `--no-salvage` が指定された場合、または transcript ディレクトリが存在しない場合は本 Phase をスキップして Phase 1 へ進む（`--no-salvage` でも Phase 0.5 の候補レビューは実行する）。**ただしディレクトリ不在は無言でスキップせず、探したパスを提示する**（slug 導出ミスが「失敗 0 件」に化けるのを防ぐため）。

> **既知の盲点（sidechain）**: subagent は SessionStart ルールを受けないため候補を書かない。subagent 内の失敗は candidates に載らず、transcript サルベージも `isSidechain != true` で除外している（意図的。agent プロンプトの誤検出回避を優先）。多段 agent スキル内の失敗はオーケストレーターが訂正した時点で候補化されることに期待する設計。

---

## Phase 1: 窓・閾値の決定

| 項目 | デフォルト | 上書き |
|---|---|---|
| 集計窓 | 直近 30 日 | 引数で日数指定（例: `60`） |
| 閾値 | 同一 tag が 3 回以上 | （Phase 1 では固定） |

詳細は `references/aggregation-rules.md`。

---

## Phase 2: tag 別集計（同梱スクリプト）

集計は同梱スクリプトで行う。窓境界の算出（BSD / GNU date 差の吸収）・不正行のスキップ・**還流記録との join** がまとまっている:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/retro-aggregate.sh"
```

- 窓日数の上書きは `--days N`（Phase 1 で決めた値）
- **exit 2 は判定不能**（jq 不在・引数不正）で「失敗 0 件」ではない。原因を報告して終了する

出力フィールドの意味は `references/aggregation-rules.md`。

---

## Phase 3: 閾値超え tag の抽出

`over_threshold: true` の tag を抽出する。**閾値判定の分子は `count_effective`（最後の還流日以降の発生）** で、還流済みの発生は分子から外れる（GitHub issue #193）。還流を打った後も窓を抜けるまで鳴り続けると、次の retro が同じ手を再提案する。

抽出した tag には**必ず**次を併記する:

- **分母**（`count_window`）と**除外件数**（`excluded_by_remediation`）。黙って分子を減らすと「収まった」と誤読される
- **還流実績**（`last_remediated_at` / `remediations`）。還流後に再発したという事実そのものが Phase 4 の判断材料になる

閾値超えが 0 件なら「閾値超えの再発パターンはありません」と報告して Phase 5 へ。ただし **0 件でも黙らないケースが 2 つある**:

1. **`quiet_since_remediation: true` の tag** — 「還流後 N 日で再発なし」を**シグナルとして出す**。還流していない tag の 0 件は無情報（発生していないだけ）だが、**還流後の 0 件は対策が効いている可能性の観測**で、意味が違う。同じ「該当なし」に潰さない
2. **閾値超え 0 件かつ Phase 0.5 の候補も 0 件** — 「失敗が少ない」ではなく**「検知できていない」可能性**に触れる（`references/transcript-salvage.md` の「制約と既知の穴」）。無言で直した失敗・英語セッションはシグナルが残らない

---

## Phase 4: 還流先提案

閾値超え tag ごとに、以下を生成する:

0. **分割宣言の確認（他のどのステップより先）**: `split_declared_at` が非 null なら、その tag は**既に分割宣言済み**。内訳から分割の要否を再導出しない（宣言済みの分割を再提案するのは、`remediations` を見ずに同じ還流を再提案するのと同型の失敗）
   - `split_not_adopted: true` → 報告すべきは失敗型そのものではなく**「分割が起票側に降りていない」**。還流先は新しい規約ではなく **log-failure Phase 2（skill 層）**。宣言後の umbrella 発生の内訳を書き出し、既存 `sub_tags` のどれにも当たらないものが多いなら**新しいサブ tag の宣言**を提案する（GitHub issue #195）
   - `split_not_adopted: false` → 分割は機能している。`sub_tags` の各行を集計から拾い、**サブ tag ごとに**還流先を判定する（umbrella 1 行に 1 つの還流先を選ばない）
   - **宣言済みの tag には下の 4「umbrella tag の判定」を適用しない**
1. **既存の還流実績の併記（必須）**: `remediations` が空でないなら「この tag には <target>（<ref>）で既に手を打っている。それでも <count_effective> 件再発した」の形で書き出す。**この項を飛ばすと、既に入れた対策とほぼ同じ提案を再度出す**（GitHub issue #193 の実害はこれ）。還流実績があるのに再発しているなら、打ち手の候補は「同じ層の強化」ではなく**層の変更**（規約 → hook）か**tag の分割**を先に検討する
2. **還流先の判定**: AGENTS.md/CLAUDE.md（規約・背景）/ hook（決定的検証）/ skill（文脈判断）のどれに反映すべきか
   - 決定的検証で判定可能（文字列・ファイル存在・exit code 等） → hook
   - 自然言語判断が必要（意図推定・レビュー等） → skill
   - 恒常的に参照したい規約・背景 → AGENTS.md/CLAUDE.md
3. **既存ガードレールでカバーできていない理由**: なぜ既存の hook/skill/規約で防げなかったのか
4. **umbrella tag の判定**: 内訳を書き出して**還流先が 2 つ以上に割れる**か、**既に還流した対策より後に別機構で再発している**なら、その tag は複数の失敗型を束ねている。1 つの還流先を選ばず、**tag の分割を提案する**（規約と実例は `../log-failure/references/journal-schema.md`）。分割せずに還流を重ねると、対策は毎回「今回の 1 件」にしか当たらず閾値だけが鳴り続ける。**ただし 0 で分割宣言が見つかった tag は対象外**（提案ではなく採用状況の報告に切り替える）

判定ロジックの詳細は `references/aggregation-rules.md`。

---

## Phase 5: レポート出力

```
## Failure Retro Report (直近 30 日)

### 再発パターン（閾値: 3 回以上 / 分子は最後の還流日以降）
| tag | 分子 | 分母 | 除外 | 還流実績 | 還流先提案 |
|-----|-----:|-----:|-----:|---------|-----------|
| delegated-run-without-isolation | 3 | 3 | 0 | なし | hook (PreToolUse で隔離なしの実行を検出) |
| version-bump-omitted | 3 | 5 | 2 | 規約 (ac8214d) | hook 昇格 (規約では止まらなかった) |

### 還流後に再発していない tag
- claimed-fact-without-source: 窓内 9 件はすべて還流前。**還流後 2 日で再発 0 件**（convention / ac8214d）

### 分割が降りていない tag
- claimed-fact-without-source: 分割宣言 2026-08-31 / 宣言後の umbrella 起票 2 件
  → 打ち手は新しい規約ではなく log-failure Phase 2 の照会（サブ tag が現象を覆えているか）

### 詳細

🔁 delegated-run-without-isolation (3 回 / 分母 3・除外 0)
  還流実績: なし
  還流先: hook (PreToolUse)
  理由: 指示ベースの隔離は守られない。実行前に決定的に判定できる。

🔁 version-bump-omitted (3 回 / 分母 5・除外 2)
  還流実績: 規約 ac8214d (2026-08-28) — **打った後に 3 件再発**
  還流先: hook (pre-commit) ← 層を変える
  理由: 規約は入っているが読み落としで再発。diff で検証可能。
```

**分母・除外件数・還流実績は省略しない。** 分子だけを出すと、還流で減ったのか発生が止まったのかが読めない。

閾値超え 0 件でも、`quiet_since_remediation` の tag があれば「還流後に再発していない tag」の節は出す（Phase 3 の 1）。**`split_not_adopted: true` の tag があれば「分割が降りていない tag」の節も閾値と無関係に出す**（分割の非追随は閾値には現れない）。すべて 0 件なら「再発パターンはありません」と報告する。

---

## Phase 6: 還流アクション確認（任意）

閾値超えが 1 件以上ある場合、**AskUserQuestion** で対応方針を確認する:

- question: "検出された再発パターンへの還流方針を選んでください"
- header: "還流方針"
- options:
  1. label: "提案のみ" / description: "レポートを残し、還流は手動で実施"
  2. label: "Issue 化" / description: "閾値超え tag を plugin-feedback / Issue 管理へ連携（別途実行）"
  3. label: "還流 / 分割を記録" / description: "打った手を remediations.jsonl へ、宣言した分割を splits.jsonl へ append する"
  4. label: "対応しない" / description: "レポート確認のみ"

> 実際の AGENTS.md/hook/skill 編集は本スキルの責務外（還流先の判断と提案に専念）。編集は対応する plugin/手動で行う。

### 還流 / 分割の記録（option 3）

**閾値超えの tag が、実は既に還流済みだったと分かったとき**（記録が漏れていた場合を含む）に append する。スキーマと手順は `../log-failure/references/journal-schema.md` の remediations.jsonl 節。

- `timestamp` は**還流が landed した日時**（コミット日時）。retro の実行時刻ではない
- **提案しただけ・着手しただけでは書かない。** この記録より前の発生は次回の分子から外れるため、先に書くと再発を見逃す
- 対象 tag・還流先の層・commit / ファイルパスを提示し、**承認を得てから append** する（副作用は承認後のみ）

分割を宣言する場合は `.claude/failure-journal/splits.jsonl` へ append する（スキーマと手順は `../log-failure/references/journal-schema.md` の splits.jsonl 節）。

- `declared_at` は**宣言した日**。遡って書かない（宣言前の umbrella 起票は append-only の規約どおり正しく、遡ると初回から偽陽性が出る）
- **サブ tag には `mechanism` を必ず書く** — 起票側が読むのはその 1 行だけ
- 分割は還流ではないので `remediations.jsonl` には書かない（分子が動いてアラームが消える）

---

## 処理フロー

```
1. Phase 0:   journal 読み込み（retro 実行中のみ Read）
2. Phase 0.5: 候補レビュー（candidates.jsonl → 承認 → journal 昇格 → verdict 書き戻し）
3. Phase 0.6: transcript サルベージ（フォールバック: --salvage 明示 or 候補 0 件のみ）
4. Phase 1:   窓・閾値の決定（30 日 / 3 回）
5. Phase 2:   tag 別集計（retro-aggregate.sh: 窓フィルタ → 還流記録と join → count）
6. Phase 3:   閾値超え tag 抽出（分子は最後の還流日以降の発生。分母・除外件数を併記）
7. Phase 4:   還流先提案（分割宣言の確認 → hook / skill / 規約 + 未カバー理由）
8. Phase 5:   レポート出力
9. Phase 6:   還流アクション確認（任意、AskUserQuestion。還流の記録もここ）
```

---

## 注意事項

- **副作用は承認後のみ**: Phase 0.5 / 0.6 の journal append・verdict 書き戻しと Phase 6 の還流アクション・remediations append のみが書き込み。いずれも承認を経る。Phase 1〜5 は read-only
- **サルベージの自動 append 禁止**: 検知は grep で決定的だが precision は約 35%。誤起票は閾値集計を直接汚すため、必ず一覧提示 → 承認を挟む
- **journal / candidates は retro 実行中のみ Read**: 集計のために読むのは本スキル実行中だけ。常時 Read すると fingerprint が AI の出力に汚染され集計が不安定になる（candidates への **append** はセッション中いつでもよい — 自己申告ルールの責務。Read だけを禁じる）
- **還流先の判断のみ**: 実際の AGENTS.md/hook/skill 編集は責務外。「どこに何を反映すべきか」の提案までを担う
- **還流済みの発生は分子から外す**: 対策を打った後も窓を抜けるまで鳴り続けると、次の retro が同じ手を再提案する（GitHub issue #193）。ただし**分母と除外件数を必ず併記**する — 黙って分子を減らすと「収まった」と誤読される
- **分割済み tag に分割を再提案しない**: `split_declared_at` が非 null なら宣言済み。`split_not_adopted: true` は「失敗が続いている」ではなく「**宣言が起票側に降りていない**」で、打ち手は skill 層（GitHub issue #195）
- **「還流後 0 件」と「鳴らない」を分ける**: 還流していない tag の 0 件は無情報だが、還流後の 0 件は対策の観測。同じ「該当なし」に潰さない
- **date の OS 差異**: 窓境界の算出は `retro-aggregate.sh` が jq 側で行うため、BSD / GNU date の差を呼び出し側が意識する必要はない
- **retrospective との責務分離**: 主観的なセッション振り返り・見積もり精度分析は `issue-workflow:retrospective`。本スキルは機械集計による再発検出に専念する
