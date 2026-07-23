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

failure journal を集計し、再発する失敗パターンを検出して規約還流（AGENTS.md/CLAUDE.md・hook・skill）を提案するスキル。責務は「再発パターンの検出と還流」であり、主観的なセッション振り返りは対象外（`indie-workflow:retrospective` の責務）。

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

## Phase 2: tag 別集計（Bash + jq）

30 日境界を算出し、窓内のレコードを tag で group して count する。境界算出は macOS BSD date / Linux GNU date 両対応:

```bash
# 30 日前の境界（macOS / Linux 両対応）
since="$(date -u -v-30d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ)"

jq -s --arg since "$since" '
  map(select(.timestamp >= $since))
  | group_by(.tag)
  | map({tag: .[0].tag, count: length})
  | sort_by(-.count)
' .claude/failure-journal/journal.jsonl
```

詳細・代替コマンドは `references/aggregation-rules.md`。

---

## Phase 3: 閾値超え tag の抽出

Phase 2 の集計結果から `count >= 3` の tag を抽出する。0 件なら「閾値超えの再発パターンはありません」と報告して終了（Phase 5 で空レポート）。

閾値超えが 0 件で、かつ Phase 0.5 のサルベージ候補も 0 件だった場合は、**「失敗が少ない」ではなく「検知できていない」可能性**に触れる（`references/transcript-salvage.md` の「制約と既知の穴」）。無言で直した失敗・英語セッションはシグナルが残らない。

---

## Phase 4: 還流先提案

閾値超え tag ごとに、以下を生成する:

1. **還流先の判定**: AGENTS.md/CLAUDE.md（規約・背景）/ hook（決定的検証）/ skill（文脈判断）のどれに反映すべきか
   - 決定的検証で判定可能（文字列・ファイル存在・exit code 等） → hook
   - 自然言語判断が必要（意図推定・レビュー等） → skill
   - 恒常的に参照したい規約・背景 → AGENTS.md/CLAUDE.md
2. **既存ガードレールでカバーできていない理由**: なぜ既存の hook/skill/規約で防げなかったのか

判定ロジックの詳細は `references/aggregation-rules.md`。

---

## Phase 5: レポート出力

```
## Failure Retro Report (直近 30 日)

### 再発パターン（閾値: 3 回以上）
| tag | count | 還流先提案 |
|-----|-------|-----------|
| spec-skipped-without-rationale | 4 | hook (PreToolUse で spec.md 不在を検出) |
| version-bump-omitted | 3 | hook (pre-commit で version 差分を検証) |

### 詳細

🔁 spec-skipped-without-rationale (4 回)
  還流先: hook (PreToolUse)
  理由: 既存 skill は spec 生成を促すが強制力がない（遵守率 ~80%）。
        決定的に spec.md 不在を検出できるので hook 昇格が ROI 高。

🔁 version-bump-omitted (3 回)
  還流先: hook (pre-commit)
  理由: CLAUDE.md に明記済みだが読み落としで再発。diff で検証可能。
```

閾値超え 0 件なら「再発パターンはありません」と報告する。

---

## Phase 6: 還流アクション確認（任意）

閾値超えが 1 件以上ある場合、**AskUserQuestion** で対応方針を確認する:

- question: "検出された再発パターンへの還流方針を選んでください"
- header: "還流方針"
- options:
  1. label: "提案のみ" / description: "レポートを残し、還流は手動で実施"
  2. label: "Issue 化" / description: "閾値超え tag を plugin-feedback / Issue 管理へ連携（別途実行）"
  3. label: "対応しない" / description: "レポート確認のみ"

> 実際の AGENTS.md/hook/skill 編集は本スキルの責務外（還流先の判断と提案に専念）。編集は対応する plugin/手動で行う。

---

## 処理フロー

```
1. Phase 0:   journal 読み込み（retro 実行中のみ Read）
2. Phase 0.5: 候補レビュー（candidates.jsonl → 承認 → journal 昇格 → verdict 書き戻し）
3. Phase 0.6: transcript サルベージ（フォールバック: --salvage 明示 or 候補 0 件のみ）
4. Phase 1:   窓・閾値の決定（30 日 / 3 回）
5. Phase 2:   tag 別集計（jq、30 日境界フィルタ → group → count）
6. Phase 3:   閾値超え tag 抽出（count >= 3）
7. Phase 4:   還流先提案（hook / skill / 規約 + 未カバー理由）
8. Phase 5:   レポート出力
9. Phase 6:   還流アクション確認（任意、AskUserQuestion）
```

---

## 注意事項

- **副作用は承認後のみ**: Phase 0.5 / 0.6 の journal append・verdict 書き戻しと Phase 6 の還流アクションのみが書き込み。いずれも承認を経る。Phase 1〜5 は read-only
- **サルベージの自動 append 禁止**: 検知は grep で決定的だが precision は約 35%。誤起票は閾値集計を直接汚すため、必ず一覧提示 → 承認を挟む
- **journal / candidates は retro 実行中のみ Read**: 集計のために読むのは本スキル実行中だけ。常時 Read すると fingerprint が AI の出力に汚染され集計が不安定になる（candidates への **append** はセッション中いつでもよい — 自己申告ルールの責務。Read だけを禁じる）
- **還流先の判断のみ**: 実際の AGENTS.md/hook/skill 編集は責務外。「どこに何を反映すべきか」の提案までを担う
- **date の OS 差異**: 30 日境界算出は macOS BSD date (`-v-30d`) と Linux GNU date (`-d '30 days ago'`) を両対応でフォールバックする
- **retrospective との責務分離**: 主観的なセッション振り返り・見積もり精度分析は `indie-workflow:retrospective`。本スキルは機械集計による再発検出に専念する
