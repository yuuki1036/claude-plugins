---
name: retro
description: >
  failure journal を集計し、直近 30 日で同一 tag が 3 回以上再発したパターンを抽出して規約還流提案を生成する。
  閾値超え tag ごとに「AGENTS.md/CLAUDE.md・hook・skill のどれに反映すべきか」と「既存ガードレールでカバーできていない理由」を出力する。
  トリガー: 「retro」「振り返り集計」「再発パターン抽出」「failure 集計」
  「同じ失敗を何回踏んだ」「規約還流」「/retro」
effort: medium
allowed-tools:
  - Read
  - Bash
  - Grep
  - AskUserQuestion
---

# Retro

failure journal を集計し、再発する失敗パターンを検出して規約還流（AGENTS.md/CLAUDE.md・hook・skill）を提案するスキル。責務は「再発パターンの検出と還流」であり、主観的なセッション振り返りは対象外（`indie-workflow:retrospective` の責務）。

詳細仕様は `references/` を参照:

- `references/aggregation-rules.md` — 集計窓・閾値・jq 集計コマンド（macOS/Linux 両対応）/ 還流先判定ルール

---

## Phase 0: journal 読み込み

1. journal パス: `.claude/failure-journal/journal.jsonl`
2. **journal の Read は retro 実行中のみ**（fingerprint の AI 出力汚染を避ける運用。README 参照）
3. ファイルが存在しない or 空なら「記録された failure がありません」と報告して終了

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
1. Phase 0: journal 読み込み（retro 実行中のみ Read）
2. Phase 1: 窓・閾値の決定（30 日 / 3 回）
3. Phase 2: tag 別集計（jq、30 日境界フィルタ → group → count）
4. Phase 3: 閾値超え tag 抽出（count >= 3）
5. Phase 4: 還流先提案（hook / skill / 規約 + 未カバー理由）
6. Phase 5: レポート出力
7. Phase 6: 還流アクション確認（任意、AskUserQuestion）
```

---

## 注意事項

- **読み取り中心、副作用は AskUserQuestion 承認後のみ**: Phase 5 まではすべて read-only
- **journal は retro 実行中のみ Read**: 集計のために journal を読むのは本スキル実行中だけ。常時 Read すると fingerprint が AI の出力に汚染され集計が不安定になる
- **還流先の判断のみ**: 実際の AGENTS.md/hook/skill 編集は責務外。「どこに何を反映すべきか」の提案までを担う
- **date の OS 差異**: 30 日境界算出は macOS BSD date (`-v-30d`) と Linux GNU date (`-d '30 days ago'`) を両対応でフォールバックする
- **retrospective との責務分離**: 主観的なセッション振り返り・見積もり精度分析は `indie-workflow:retrospective`。本スキルは機械集計による再発検出に専念する
