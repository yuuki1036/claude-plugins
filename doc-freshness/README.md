# doc-freshness

ドキュメント鮮度を機械的に強制するプラグイン。`last-validated` / `phase` frontmatter による stale 検出、行数ガード、internal link 検証、新規 doc grace period を提供する。

## 使い方

```
/doc-freshness-check            # プロジェクト全体を走査
/doc-freshness-check CLAUDE.md  # 単一ファイル走査
```

手動走査に加え、イベント駆動の鮮度検知 hook を持つ（`references/hook-config.md`）:

- **PostToolUse (Edit/Write/MultiEdit)**: frontmatter 必須の project doc（`.claude/designs/` `.claude/adr/`）への .md 作成/編集時に `last-validated` / `phase` の欠落を**非ブロッキング**で警告（常時 on・対象 dir 限定）
- **SessionStart (once, opt-in)**: 対象 doc の stale をセッション開始時に 1 回まとめて通知（`.claude/doc-freshness.json` の `sessionStartCheck: true` で有効化）

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
- `append_only`（任意）: `true` で **stale 判定を免除**（作成後に内容が固定される履歴文書向け。ADR が付与）

## 走査対象

- プロジェクト root 配下の `**/*.md`
- `.claude/adr/**/*.md`（adr-keeper）と `.claude/designs/**/*.md`（design-doc）を明示追加（Glob は既定で dot ディレクトリを拾わないため）
- 除外: `.git/` / `node_modules/` / 生成物、および `.claude/adr` / `.claude/designs` を除く `.claude/` 配下、プロジェクトツリー外

## チェック項目

| # | 項目 | 重大度 |
|---|------|--------|
| 1 | frontmatter 必須スキーマ（last-validated / phase） | error |
| 2 | 行数上限（CLAUDE.md / AGENTS.md: 40 warn / 65 error） | warn / error |
| 3 | internal link 検証（相対リンク先の実在） | error |
| 4 | phase 別 stale 判定（`append_only: true` は免除） | error |
| 5 | superseded への active doc からの参照禁止 | error |
| 6 | 新規 doc grace period（デフォルト 7 日。frontmatter 欠落は warn、他は info） | info / warn |

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

- **PreToolUse hook は採用しない**: 新規 doc 作成時に last-validated 不在で即 error になる failure mode を回避（観察事例あり）。frontmatter 検知は PostToolUse（書き込み後・非ブロッキング）のみ
- **hook 対象は project doc に限定**: `.claude/designs/` `.claude/adr/` のみ。プラグイン内部 doc（SKILL.md / references/ / README）は含めない（version + CHANGELOG で鮮度管理され、`last-validated` を付けると恒常 stale 化するため）
- **SessionStart stale-check は opt-in**: 毎セッションの stale 通知はノイズになりうるため既定 off。継続監視したいプロジェクトだけ `sessionStartCheck: true` で有効化する
- **knowledge-lint との責務分離**: broken wikilink / orphan は knowledge-lint、frontmatter 鮮度は doc-freshness
- **append-only 履歴文書の stale 免除**: `append_only: true` で ADR のような「作成後に内容が固定される文書」を stale error から守る。`phase: current` の閾値を当てると作成直後から恒常 stale になる委譲破綻を回避する（design doc は生きた文書なので付けない）

## 構成

| 種別 | 名前 | 説明 |
|------|------|------|
| コマンド | `/doc-freshness-check` | プロジェクト全体または指定ファイルの鮮度走査 |
| スキル | `doc-freshness` | 走査・判定・レポート生成のロジック |
| hook | `frontmatter-guard`（PostToolUse） | frontmatter 必須 project doc の frontmatter 欠落を非ブロッキング検知 |
| hook | `stale-check`（SessionStart, opt-in） | 対象 doc の stale をセッション開始時に一括通知 |
