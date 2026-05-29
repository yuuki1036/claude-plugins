# 閾値設定

doc-freshness が使う各種閾値のデフォルト値と、プロジェクト側で上書きする方法。

## デフォルト値

| 項目 | デフォルト | 意味 |
|---|---|---|
| `thresholds.current` | `5` 日 | `phase: current` の stale 閾値 |
| `thresholds.target` | `15` 日 | `phase: target` の stale 閾値 |
| `gracePeriodDays` | `7` 日 | 新規ファイルの猶予期間 |
| `lineLimits.warn` | `40` 行 | harness doc の行数 warn 閾値 |
| `lineLimits.error` | `65` 行 | harness doc の行数 error 閾値 |
| `harnessDocs` | `["CLAUDE.md", "AGENTS.md"]` | 行数ガード対象ファイル名 |

## プロジェクト側の上書き

`.claude/doc-freshness.json` を置けば全項目を上書きできる:

```json
{
  "thresholds": {
    "current": 7,
    "target": 30
  },
  "gracePeriodDays": 14,
  "lineLimits": {
    "warn": 50,
    "error": 80
  },
  "harnessDocs": ["CLAUDE.md", "AGENTS.md", "docs/conventions.md"]
}
```

- 部分上書きは可（指定したキーのみ反映、未指定はデフォルト）
- JSON が parse できない場合はデフォルトで続行し warn 出力

## 閾値の根拠

### `thresholds.current = 5`

現行ドキュメントは週次でレビューされる前提（営業日ベースで 5 日）。これを超えると「先週確認した内容」となり信頼性が落ちる。

### `thresholds.target = 15`

将来計画は週次レビュー対象にならないが、2-3 週間放置すると古い前提のまま残り mismatch を生む。15 日は週次の 3 倍で「半月レビュー」の感覚。

### `gracePeriodDays = 7`

新規 doc 作成直後は frontmatter / レビューが整っていない。観察事例で「PreToolUse hook が新規 doc 作成を阻害する failure mode」が報告されており、Phase 1 では PostToolUse hook も持たないが将来追加時の備えとして grace period を持つ。7 日は「次の週次レビューまで」の意。

### `lineLimits = {40, 65}`

LLM の context window への影響を考慮。harness doc は毎セッション読まれるため、長すぎると他の context を圧迫する。

- 40 行: 概ね「画面 1 ページ」「コンテキスト窓の 1% 未満」
- 65 行: 「画面 1.5 ページ」を超えたら分割を検討すべき水準

## 上書き例

### 厳しめに運用したい

```json
{
  "thresholds": { "current": 3, "target": 7 },
  "lineLimits": { "warn": 30, "error": 50 }
}
```

### ゆるめに運用したい（個人プロジェクト等）

```json
{
  "thresholds": { "current": 14, "target": 60 },
  "gracePeriodDays": 30
}
```

### harness doc を増やしたい

```json
{
  "harnessDocs": [
    "CLAUDE.md",
    "AGENTS.md",
    ".cursor/rules/main.md",
    "docs/coding-conventions.md"
  ]
}
```
