# Aggregation Rules

retro スキルの集計仕様。

## 窓と閾値

| 項目 | デフォルト | 説明 |
|---|---|---|
| 集計窓 | 直近 30 日 | `timestamp` が窓境界以降のレコードを**分母**にする |
| 有効境界 | 窓境界と最後の還流日の**遅い方** | この境界以降の発生だけを**分子**にする（GitHub issue #193） |
| 閾値 | 同一 tag 3 回以上 | `count_effective` が閾値に達した tag を「再発パターン」として抽出 |

引数で窓日数を上書きできる（例: `/retro 60` → 直近 60 日）。閾値は Phase 1 では固定。

### なぜ分子を還流日以降に限るか

**還流済みの発生を分子に残すと、対策を打った後も窓を抜けるまで同じ tag が鳴り続け、次の retro が同じ手を再提案する。** 実際に 2026-08-30 の retro で、前日の還流（`ac8214d`）とほぼ同じ内容の issue を起票する直前まで進んだ（GitHub issue #193）。retro のレポートには「この tag には既に手を打った」が現れないので、同型の再提案は検出が難しい。

**ただし分母と除外件数は必ず併記する。** 黙って分子を減らすと「収まった」と誤読される（`code-review` の `review-retro.sh` が抑止件数を明示するのと同じ扱い）。

## 集計コマンド

集計は同梱スクリプトで行う。窓境界の算出（BSD / GNU date 差の吸収）・不正行のスキップ・還流記録との join がまとまっている:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/retro-aggregate.sh"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/retro-aggregate.sh" --days 60 --threshold 3
```

| オプション | 既定 |
|---|---|
| `--journal PATH` | `.claude/failure-journal/journal.jsonl` |
| `--remediations PATH` | `.claude/failure-journal/remediations.jsonl` |
| `--days N` / `--threshold N` | 30 / 3 |
| `--now ISO8601` | `date -u`（テストで窓を固定するため） |

exit code は **0 集計成功 / 2 判定不能**（jq 不在・引数不正）。2 のときは「失敗 0 件」と読まずに原因を報告する。

### 出力の読み方

```json
{
  "window": {"days": 30, "since": "2026-07-31T12:00:00Z", "now": "2026-08-30T12:00:00Z"},
  "threshold": 3,
  "tags": [
    {"tag": "delegated-run-without-isolation",
     "count_window": 3, "count_effective": 3, "excluded_by_remediation": 0,
     "last_remediated_at": null, "over_threshold": true, "quiet_since_remediation": false},
    {"tag": "claimed-fact-without-source",
     "count_window": 9, "count_effective": 0, "excluded_by_remediation": 9,
     "effective_since": "2026-08-28T00:00:00Z", "last_remediated_at": "2026-08-28T00:00:00Z",
     "days_since_remediation": 2, "remediations": [{"target": "convention", "ref": "ac8214d"}],
     "over_threshold": false, "quiet_since_remediation": true}
  ]
}
```

| フィールド | 意味 |
|---|---|
| `count_window` | 窓内の全発生（**分母**。必ずレポートに出す） |
| `count_effective` | 有効境界以降の発生（**分子**。閾値判定はこれ） |
| `excluded_by_remediation` | 還流日以前として分子から外した件数（**必ず併記**） |
| `over_threshold` | `count_effective` が閾値に達した → Phase 4 の還流先提案の対象 |
| `quiet_since_remediation` | 還流実績があり、その後の発生が 0 件 → **対策が効いている可能性のシグナル** |
| `remediations` | その tag への還流実績（全期間）。Phase 4 で必ず併記する |

> `quiet_since_remediation` は「鳴らない」とは意味が違う。**還流していない tag の 0 件は無情報**（発生していないだけ）だが、**還流後の 0 件は対策の観測**になる。両者を同じ「該当なし」に潰さない。

> 還流実績があって窓内の発生が 0 件の tag も行として出る。**シグナルはそこにしか現れない**ので、`count_window` が 0 の行を落とさない。

## 還流先判定ルール

閾値超え tag ごとに、CLAUDE.md の「ルール配置の意思決定」に準拠して還流先を提案する:

| 失敗の性質 | 還流先 | 理由 |
|---|---|---|
| 決定的検証で判定可能（文字列・ファイル存在・JSON スキーマ・exit code・diff） | **hook**（PreToolUse / PostToolUse / pre-commit 等） | 遵守率 100%。CLAUDE.md の ~80% より ROI 高 |
| 文脈判断・自然言語理解が必要（意図推定・レビュー・要約） | **skill / agent** | 呼び出せば確実（~90%） |
| 恒常的に参照したい規約・背景情報 | **AGENTS.md / CLAUDE.md** | 例外が多い / リカバリ容易な場合 |

判定の補助質問:

- その失敗は `if` / `grep` / `diff` で機械判定できるか？ → Yes なら hook
- 文脈依存で例外が多いか？ → Yes なら CLAUDE.md / skill に留める
- 既存の hook/skill/規約が既にあるのに再発したか？ → 「なぜ防げなかったか」を未カバー理由として明記（規約 → hook 昇格の判断材料）

## 未カバー理由の言語化

各 tag について、既存ガードレールでなぜ防げなかったかを明示する:

- 規約はあるが読み落とし（遵守率問題） → hook 昇格を提案
- そもそも規約・検証が存在しない → 新規 hook / skill / CLAUDE.md 追記を提案
- 検証はあるが判定が甘い（false negative） → 既存 hook の判定ロジック強化を提案
