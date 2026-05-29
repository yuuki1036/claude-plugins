---
name: doc-freshness
description: >
  ドキュメントの鮮度を機械的に検証する。
  last-validated / phase frontmatter による stale 判定、行数ガード、internal link 検証、
  superseded 参照禁止、新規 doc grace period をチェックする。
  トリガー: 「doc 鮮度」「ドキュメント鮮度」「stale doc 検出」「doc lint」「ドキュメントが古い」
  「/doc-freshness-check」「last-validated チェック」「phase superseded 検出」
effort: medium
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Doc Freshness

ドキュメント鮮度を機械的に検証するスキル。`last-validated` / `phase` frontmatter を起点に、stale 判定・行数ガード・internal link 整合・superseded 参照禁止を検出する。

詳細仕様は `references/` を参照:

- `references/frontmatter-spec.md` — frontmatter スキーマ定義
- `references/thresholds.md` — 閾値のデフォルト値と上書き方法

---

## Phase 0: 設定ロード

1. `.claude/doc-freshness.json` の存在を確認（Read、存在しなければデフォルト値で続行）
2. 設定値:
   - `thresholds.current` (デフォルト `5` 日)
   - `thresholds.target` (デフォルト `15` 日)
   - `gracePeriodDays` (デフォルト `7` 日)
   - `lineLimits.warn` / `lineLimits.error` (デフォルト `40` / `65`)
   - `harnessDocs` (デフォルト `["CLAUDE.md", "AGENTS.md"]`)

詳細は `references/thresholds.md` を参照。

---

## Phase 1: 対象ファイル特定

1. 引数があれば単一ファイルとして処理（後段の Phase 2〜6 を直接適用）
2. 引数なしならプロジェクト全体走査:
   - `**/*.md` を Glob（`.git/` / `node_modules/` / プラグイン外を除外）
   - `CLAUDE.md` / `AGENTS.md` はリポジトリ root + 各サブディレクトリ両方を対象
3. **新規ファイル grace period 判定**: 各ファイルの作成日時を Bash で取得し、`gracePeriodDays` 以内なら以降のチェックを **info** 扱いにスキップ
   ```bash
   # macOS / Linux 両対応の作成日時取得（厳密な birth time は非対応 fs もあるので mtime fallback）
   stat -f '%B' "$f" 2>/dev/null || stat -c '%W' "$f" 2>/dev/null || stat -f '%m' "$f" 2>/dev/null || stat -c '%Y' "$f"
   ```

---

## Phase 2: frontmatter 検証（error）

各ファイル先頭の YAML frontmatter を Read で取得し、以下を検証する。

| 項目 | 判定 | 重大度 |
|---|---|---|
| frontmatter 自体が無い | grace period 外なら error | 🔴 |
| `last-validated` キー欠落 | error | 🔴 |
| `last-validated` が `YYYY-MM-DD` 形式でない | error | 🔴 |
| `phase` キー欠落 | error | 🔴 |
| `phase` が `current` / `target` / `superseded` 以外 | error | 🔴 |

詳細は `references/frontmatter-spec.md` を参照。

---

## Phase 3: phase 別 stale 判定（error）

`last-validated` と現在日付の差分を計算し、`phase` ごとの閾値と比較する。

```bash
# macOS BSD date / Linux GNU date 両対応
date_to_ts() {
  local d="$1"
  date -j -f "%Y-%m-%d" "$d" "+%s" 2>/dev/null \
    || date -d "$d" "+%s"
}
now=$(date "+%s")
ts=$(date_to_ts "$validated")
age_days=$(( (now - ts) / 86400 ))
```

| phase | 閾値（デフォルト） | 超過時 |
|---|---|---|
| `current` | 5 日 | 🔴 error |
| `target` | 15 日 | 🔴 error |
| `superseded` | 判定対象外 | - |

---

## Phase 4: 行数ガード（warn / error）

`harnessDocs` に該当するファイルのみ対象。

| 行数 | 判定 |
|---|---|
| `lineLimits.warn`（40）超 | 🟡 warn |
| `lineLimits.error`（65）超 | 🔴 error |

```bash
wc -l < "$f"
```

> harness 向け doc は LLM が毎回読むため、長すぎると context を圧迫する。閾値は調整可（`references/thresholds.md`）。

---

## Phase 5: internal link 検証（error）

本文中の Markdown 相対リンク `[label](./path)` / `[label](../path)` / `[label](path.md)` を抽出し、リンク先ファイルの実在を検証する。

- 検出パターン: `\[[^\]]*\]\(([^)]+)\)` のうち、`http://` / `https://` / `mailto:` を含まない & `#` のみで始まらないもの
- リンク先がファイル末尾 `.md` で実在しない → 🔴 error
- リンク先が `#fragment` 付きの場合は基底パスの存在のみ検証（fragment 整合性はスコープ外）

---

## Phase 6: superseded 参照禁止（error）

`phase: superseded` のファイル一覧を Phase 2 で収集しておく。

active doc（`phase: current` / `target`）の本文中に、`superseded` ファイルへの相対リンクが含まれていれば 🔴 error として報告する。

---

## Phase 7: レポート出力

```
## Doc Freshness Report

### サマリー
| 項目 | error | warn | info |
|------|-------|------|------|
| frontmatter | 0 | 0 | 0 |
| stale (phase) | 2 | 0 | 0 |
| 行数ガード | 0 | 1 | 0 |
| internal link | 1 | 0 | 0 |
| superseded 参照 | 0 | 0 | 0 |
| grace period | 0 | 0 | 3 |

### 詳細

🔴 stale (current, 8日 > 5日): docs/architecture.md
🔴 stale (target, 22日 > 15日): docs/roadmap-2026q3.md
🔴 broken link: CLAUDE.md → ./missing.md
🟡 行数超過 (44 > 40): CLAUDE.md
ℹ️ grace period 中（新規 doc）: src/feature-x/README.md
```

- error が 1 件以上 → 終了ステータス相当の警告を末尾に表示
- 検出 0 件なら「Doc は健全です」と報告

---

## Phase 8: 修正提案（任意）

検出件数が多い場合 **AskUserQuestion** で対応方針を確認する:

- question: "検出された問題への対応方針を選んでください"
- header: "対応方針"
- options:
  1. label: "frontmatter 一括追加" / description: "frontmatter 欠落ファイルに雛形を Edit で追記"
  2. label: "last-validated 更新" / description: "stale 判定された doc の last-validated を本日に更新"
  3. label: "個別対応" / description: "レポートだけ残してファイルごとに判断"
  4. label: "対応しない" / description: "レポート確認のみ"

> 自動修正は frontmatter 追加と last-validated 更新のみ。superseded 参照解消・行数削減・broken link 修正は人手判断が必要なため提案しない。

---

## 処理フロー

```
1. Phase 0: .claude/doc-freshness.json 読み込み（または default）
2. Phase 1: 対象ファイル特定 + grace period 判定
3. Phase 2: frontmatter スキーマ検証
4. Phase 3: phase 別 stale 判定
5. Phase 4: harness doc 行数ガード
6. Phase 5: internal link 検証
7. Phase 6: superseded 参照禁止
8. Phase 7: レポート出力
9. Phase 8: 修正提案（任意、AskUserQuestion）
```

---

## 注意事項

- **読み取り中心、副作用は AskUserQuestion 承認後のみ**: Phase 7 まではすべて read-only
- **knowledge-lint との責務分離**: broken wikilink (`[[name]]` 記法) と orphan は knowledge-lint の責務。doc-freshness は frontmatter / Markdown link / 行数ガードに専念
- **PreToolUse hook は採用しない**: 新規 doc 作成時に last-validated 不在で即 error になる failure mode を回避（Phase 2 として hook 連動を検討する場合は PostToolUse のみ）
- **fs の birth time 非対応**: 一部 fs（ext4 など）は作成日時を返さないため、mtime にフォールバックする。grace period 判定が緩めになるが安全側
