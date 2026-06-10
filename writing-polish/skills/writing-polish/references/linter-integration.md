# linter 連携手順

決定的に拾える観点を linter に委譲し、LLM は文脈判断に集中するための連携手順。tone-guide「textlint / Vale 委譲境界」と対応する。

## 概要

決定的に拾える観点（表記・文法・二重否定・助詞連続・確実な冗長構文「〜を行う→する」・文長/読点しきい値）は linter に委譲する。誤検知が少なく再現性が高い領域は機械判定が LLM 判定より ROI が高い。

linter が未導入の環境では LLM 判定にフォールバックする（同じ観点を LLM が判定する。決定性・再現性は劣るが検出は試みる）。導入済みなら linter の決定的判定を優先し、LLM はそれに乗らない指摘（名詞化の良性/悪性・衒学語の言い換え・density 判断）に集中する。

## textlint（日本語）

### 存在チェック

```bash
command -v textlint >/dev/null 2>&1
```

未導入なら以降を skip し、LLM 判定のみで続行する（fail させない）。

### 実行（stdin 経由・一時ファイル不要）

```bash
printf '%s' "$TARGET_TEXT" | textlint --stdin --stdin-filename target.md \
  --config "${CLAUDE_PLUGIN_ROOT}/skills/writing-polish/references/textlintrc.json" \
  --format json
```

同梱 config は `references/textlintrc.json`。preset 本体・ルールはユーザーの textlint global install 側に存在する前提で、この config を `--config` で指して使う。

### 出力の読み方

出力は JSON。形は次のとおり。

```json
[{ "messages": [{ "ruleId": "...", "message": "...", "line": 1, "severity": 2 }] }]
```

各 `ruleId` を下表で tone-guide カテゴリにマップし、diff 候補に統合する。

### ruleId → tone-guide カテゴリ対応表

| ruleId | tone-guide カテゴリ |
|---|---|
| `sentence-length` | カテゴリ 1（冗長・密度） |
| `max-ten` | カテゴリ 1（冗長・密度） |
| `max-kanji-continuous-len` | カテゴリ 1（冗長・密度） |
| `no-double-negative-ja` | カテゴリ 1〜2（読みにくさ） |
| `no-doubled-joshi` | カテゴリ 1〜2（読みにくさ） |
| `no-mix-dearu-desumasu` | 文体メタルール |
| `ja-no-redundant-expression` | カテゴリ 1（冗長構文「〜を行う→する」） |

### 重要: 機械判定を盲従しない

linter 指摘も**最小差分・採否フロー・over-correction 抑制に乗せる**。linter が出した指摘でも、文脈で不要なら採用しない（textlint の機械判定を盲従しない）。決定的判定は候補を漏れなく拾う手段であって、採否は中核原則に従って LLM が判断する。

### 導入方法

```bash
npm i -g textlint textlint-rule-preset-ja-technical-writing textlint-rule-ja-no-redundant-expression
```

## 将来の拡張

別の linter を足すときも同じ型でこの reference に節を追加する。SKILL 本文は薄いまま保つ。

### Vale（英語・未実装）

英語対象に Vale を同じ型で追加する雛形（手順のみ。実装はしない）。

- 存在チェック: `command -v vale >/dev/null 2>&1`
- 実行: `vale --output=JSON <file>`
- 出力の各アラートを tone-guide カテゴリ 6（英語）にマップして候補に統合する。
- linter 指摘の採否は textlint と同様、最小差分・over-correction 抑制に乗せる。
