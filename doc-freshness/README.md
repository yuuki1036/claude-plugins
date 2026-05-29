# doc-freshness

ドキュメント鮮度を機械的に強制するプラグイン。`last-validated` / `phase` frontmatter による stale 検出、行数ガード、internal link 検証、新規 doc grace period を提供する。

## 使い方

```
/doc-freshness-check            # プロジェクト全体を走査
/doc-freshness-check CLAUDE.md  # 単一ファイル走査
```

## frontmatter 規約

```yaml
---
last-validated: 2026-05-29   # ISO 8601 (YYYY-MM-DD)
phase: current               # current | target | superseded
---
```

- `last-validated`: 最終検証日。手動で更新する
- `phase`:
  - `current` — 現行ドキュメント。stale 閾値: **5 日**（デフォルト）
  - `target` — 将来計画。stale 閾値: **15 日**
  - `superseded` — 廃止済み。active doc から参照されると error

## チェック項目

| # | 項目 | 重大度 |
|---|------|--------|
| 1 | frontmatter 必須スキーマ（last-validated / phase） | error |
| 2 | 行数上限（CLAUDE.md / AGENTS.md: 40 warn / 65 error） | warn / error |
| 3 | internal link 検証（相対リンク先の実在） | error |
| 4 | phase 別 stale 判定 | error |
| 5 | superseded への active doc からの参照禁止 | error |
| 6 | 新規 doc grace period（デフォルト 7 日） | info |

## 設定

`.claude/doc-freshness.json` で閾値・grace period を上書き可能（任意）:

```json
{
  "thresholds": {
    "current": 5,
    "target": 15
  },
  "gracePeriodDays": 7,
  "lineLimits": {
    "warn": 40,
    "error": 65
  },
  "harnessDocs": ["CLAUDE.md", "AGENTS.md"]
}
```

## 設計判断

- **PreToolUse hook は採用しない**: 新規 doc 作成時に last-validated 不在で即 error になる failure mode を回避（観察事例あり）
- **Phase 1 = command + skill のみ**: hook 連動は需要が顕在化したタイミングで Phase 2 として追加
- **knowledge-lint との責務分離**: broken wikilink / orphan は knowledge-lint、frontmatter 鮮度は doc-freshness

## 構成

| 種別 | 名前 | 説明 |
|------|------|------|
| コマンド | `/doc-freshness-check` | プロジェクト全体または指定ファイルの鮮度走査 |
| スキル | `doc-freshness` | 走査・判定・レポート生成のロジック |
