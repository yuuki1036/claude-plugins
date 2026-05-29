# Aggregation Rules

retro スキルの集計仕様。

## 窓と閾値

| 項目 | デフォルト | 説明 |
|---|---|---|
| 集計窓 | 直近 30 日 | `timestamp >= (now - 30d)` のレコードのみ対象 |
| 閾値 | 同一 tag 3 回以上 | `count >= 3` の tag を「再発パターン」として抽出 |

引数で窓日数を上書きできる（例: `/retro 60` → 直近 60 日）。閾値は Phase 1 では固定。

## 30 日境界の算出（OS 両対応）

macOS の BSD date と Linux の GNU date でオプションが異なるため、フォールバックで両対応する:

```bash
# macOS BSD date を先に試し、失敗したら Linux GNU date
since="$(date -u -v-30d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ)"
```

日数を可変にする場合:

```bash
days=30
since="$(date -u -v-"${days}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -d "${days} days ago" +%Y-%m-%dT%H:%M:%SZ)"
```

> `timestamp` は ISO8601 UTC（`Z` 終端）なので、文字列比較 `>=` で時系列フィルタが成立する（辞書順 = 時系列順）。

## tag 別集計（jq）

```bash
jq -s --arg since "$since" '
  map(select(.timestamp >= $since))   # 窓内に絞る
  | group_by(.tag)                    # tag でグルーピング
  | map({tag: .[0].tag, count: length})
  | sort_by(-.count)                  # 多い順
' .claude/failure-journal/journal.jsonl
```

閾値超えだけ抽出する場合:

```bash
jq -s --arg since "$since" '
  map(select(.timestamp >= $since))
  | group_by(.tag)
  | map({tag: .[0].tag, count: length})
  | map(select(.count >= 3))
  | sort_by(-.count)
' .claude/failure-journal/journal.jsonl
```

- `jq -s`（slurp）で JSON Lines 全行を配列として読む
- 不正な行が混ざっても落ちにくいよう、必要なら `jq -R 'fromjson? // empty'` で前処理してから slurp する

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
