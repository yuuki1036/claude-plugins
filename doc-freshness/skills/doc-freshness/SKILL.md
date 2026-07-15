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
  - Edit
  - Write
  - AskUserQuestion
---

# Doc Freshness

ドキュメント鮮度を機械的に検証するスキル。`last-validated` / `phase` frontmatter を起点に、stale 判定・行数ガード・internal link 整合・superseded 参照禁止を検出する。

詳細仕様は `references/` を参照:

- `references/frontmatter-spec.md` — frontmatter スキーマ定義
- `references/thresholds.md` — 閾値のデフォルト値と上書き方法
- `references/hook-config.md` — イベント駆動の鮮度検知 hook（PostToolUse frontmatter 警告 / SessionStart stale 一括警告）の設定

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
   - `**/*.md` を Glob
   - **dot ディレクトリ配下の doc を明示追加**: Glob の `**` は既定で dot ディレクトリ（`.claude/` 等）を拾わないため、以下を個別に Glob して対象に加える:
     - `.claude/adr/**/*.md`（adr-keeper が鮮度 lint を委譲する ADR）
     - `.claude/designs/**/*.md`（design-doc が鮮度 lint を委譲する design doc）
     - `.claude/living-specs/**/*.md`（living-spec-workflow が鮮度 lint を委譲する living spec）
   - `CLAUDE.md` / `AGENTS.md` はリポジトリ root + 各サブディレクトリ両方を対象
   - **除外**: 以下は走査対象から外す:
     - `.git/` / `node_modules/` / `dist/` / `build/` / `vendor/` 配下（生成物・依存ライブラリ）
     - `.claude/adr/` / `.claude/designs/` / `.claude/living-specs/` を除く `.claude/` 配下（session-context.md 等の gitignored な運用ファイル。frontmatter を前提にしない）
     - **プラグイン外を除外** = プロジェクトのソースツリー外（`$HOME/.claude/` 配下にインストールされたプラグイン本体の doc 等）は対象にしない。走査は常に**カレントプロジェクト root 配下**に限定する
3. **新規ファイル grace period 判定**: 各ファイルの作成日時を Bash で取得し、`gracePeriodDays` 以内なら重大度を緩める:
   - stale（Phase 3）/ 行数（Phase 4）/ link（Phase 5）/ superseded 参照（Phase 6）の検出 → **info** に降格（新規 doc の整備途中を error にしない）
   - **frontmatter 欠落（Phase 2）のみ warn**（scaffold 直後でも frontmatter 付与忘れは気づけるようにする）。grace period 外に出たら error に昇格する
   ```bash
   # macOS / Linux 両対応の作成日時取得。
   # macOS(BSD stat): %B が birth time。Linux(GNU stat): %W が birth time だが
   # ext4 等 birth time 非対応 fs は 0 を返すため、0 のときは mtime(%Y) にフォールバックする。
   created=$(stat -f '%B' "$f" 2>/dev/null)          # macOS: birth time
   if [ -z "$created" ]; then
     created=$(stat -c '%W' "$f" 2>/dev/null)        # Linux: birth time（未対応 fs は 0）
     if [ -z "$created" ] || [ "$created" = "0" ]; then
       created=$(stat -c '%Y' "$f")                  # Linux fallback: mtime
     fi
   fi
   ```

---

## Phase 2: frontmatter 検証

各ファイル先頭の YAML frontmatter を Read で取得し、以下を検証する。

| 項目 | 判定 | 重大度 |
|---|---|---|
| frontmatter 自体が無い | grace period 内は warn、grace period 外は error | 🟡/🔴 |
| `last-validated` キー欠落 | grace period 内は warn、grace period 外は error | 🟡/🔴 |
| `last-validated` が `YYYY-MM-DD` 形式でない | error | 🔴 |
| `phase` キー欠落 | grace period 内は warn、grace period 外は error | 🟡/🔴 |
| `phase` が `current` / `target` / `superseded` 以外 | error | 🔴 |

> grace period 内/外の重大度は 3 箇所（このスキル・Phase 1 の grace period 判定・`references/frontmatter-spec.md`）で **grace period 内 = warn / grace period 外 = error** に統一している。

**append_only マーカーの収集**: `append_only: true` を持つファイルは Phase 3（stale 判定）を免除する（下記）。Phase 2 でこのフラグを収集しておく。

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

### append-only な履歴文書の stale 免除（error 化しない）

**`append_only: true` を frontmatter に持つファイルは phase に関わらず stale 判定を免除する**（Phase 2 で収集済み）。

- 理由: ADR（`.claude/adr/`）のように「決定した時点の記録を append-only で残す」文書は、作成後に内容が変わらないのが正常挙動。`phase: current` の stale 閾値（5 日）を当てると、作成 5 日後から恒常的に stale error になり委譲が破綻する。
- 免除するのは **Phase 3 の stale 判定のみ**。frontmatter スキーマ（Phase 2）・link（Phase 5）・superseded 参照（Phase 6）は通常どおり検証する。
- レポートでは「append-only（stale 免除）」として info 表示する（黙って skip しない）。
- **付与側の責務**: このマーカーは adr-keeper のテンプレが accepted ADR に `append_only: true` を付ける。design-doc は `phase: target → current` の遷移で鮮度を測る「生きた文書」なので付けない（下記「設計判断」）。

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
| append-only (stale 免除) | 0 | 0 | 4 |

### 詳細

🔴 stale (current, 8日 > 5日): docs/architecture.md
🔴 stale (target, 22日 > 15日): docs/roadmap-2026q3.md
🔴 broken link: CLAUDE.md → ./missing.md
🟡 行数超過 (44 > 40): CLAUDE.md
ℹ️ grace period 中（新規 doc）: src/feature-x/README.md
ℹ️ append-only（stale 免除）: .claude/adr/20260529143012-api-versioning-strategy.md
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

- **読み取り中心、副作用は AskUserQuestion 承認後のみ**: Phase 7 まではすべて read-only。Phase 8 の自動修正（frontmatter 一括追加 / last-validated 更新）だけが Edit / Write を使う。それ以外の書き込みはしない
- **knowledge-lint との責務分離**: broken wikilink (`[[name]]` 記法) と orphan は knowledge-lint の責務。doc-freshness は frontmatter / Markdown link / 行数ガードに専念
- **hook 連動（Phase 2、実装済み）**: frontmatter 欠落の検知は PostToolUse hook（`frontmatter-guard.sh`、非ブロッキング）、stale の継続監視は SessionStart hook（`stale-check.sh`、opt-in）に委ねる。**PreToolUse は採用しない**（新規 doc 作成時に last-validated 不在で即 error になる failure mode を回避）。設定は `references/hook-config.md` を参照。本スキル（手動走査）と hook は役割分担: hook は「欠落の即時検知」と「stale の一括通知」だけを担い、行数ガード・link 検証・superseded 参照・修正提案は本スキルが担う
- **fs の birth time 非対応**: 一部 fs（ext4 など）は作成日時を返さないため、mtime にフォールバックする。grace period 判定が緩めになるが安全側
- **append-only 免除は stale 判定のみ**: `append_only: true` は「作成後に内容が固定される履歴文書」（ADR 等）を stale error から守るためのマーカー。frontmatter スキーマ・link・superseded 参照は通常どおり検証する。design doc は `phase: target → current` で鮮度を測る生きた文書なので付けない（住み分けは付与側プラグインの責務）
