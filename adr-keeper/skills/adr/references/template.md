# ADR 本文テンプレ

新規 ADR 作成時にこのテンプレを Read し、`{...}` プレースホルダを置換して Write する。

## プレースホルダ一覧

| プレースホルダ | 置換値 | 取得方法 |
|---|---|---|
| `{ID}` | timestamp（`YYYYMMDDhhmmss`） | Bash `date +%Y%m%d%H%M%S` |
| `{TITLE}` | ADR のタイトル（原文ママ） | 引数 `<title>` |
| `{STATUS}` | `proposed` / `accepted` / `superseded` | 既定 `accepted` |
| `{PHASE}` | `current` / `target` / `superseded` | 既定 `current` |
| `{TODAY}` | 本日（`YYYY-MM-DD`） | Bash `date +%Y-%m-%d` |
| `{SUPERSEDES}` | 置き換える ADR の id 配列 | 通常 `[]`、supersede 時 `["<old-id>"]` |
| `{SUPERSEDED_BY}` | この ADR を置き換えた ADR の id | 通常 `null` |

---

## テンプレ本体（ここから下を書き出す）

```markdown
---
id: {ID}
status: {STATUS}
phase: {PHASE}
last-validated: {TODAY}
supersedes: {SUPERSEDES}
superseded-by: {SUPERSEDED_BY}
tags: []
---

# ADR-{ID}: {TITLE}

## ステータス

{STATUS}（{TODAY}）

## コンテキスト / 背景

<!-- どんな状況・制約・課題からこの判断が必要になったか。技術的・組織的な前提を書く -->

## 決定

<!-- 何を決めたか。曖昧さを残さず、断定形で書く -->

## 影響 (Consequences)

- **良い影響**: <!-- この決定で得られるもの -->
- **悪い影響**: <!-- この決定で失うもの・新たに生じる制約 -->
- **トレードオフ**: <!-- 何と何を天秤にかけたか -->

## 適用方法 (Enforcement)

<!--
この決定を lint / test / hook で機械強制できないか必ず検討する。
- 機械強制できる → 具体的手段（どの lint ルール / どの test / どの hook で、どう検出するか）
- 機械強制できない → その理由（文脈依存・例外多数・自然言語判断が必要 等）

決定的検証（exit code / 文字列 / スキーマ）で守れるなら、CLAUDE.md より hook に昇格させたほうが遵守率が高い。
死に文書化（書いたが守られない ADR）を防ぐための必須欄。
-->

## 検討した代替案

<!-- 採用しなかった選択肢と、なぜ採用しなかったか。1 案ずつ箇条書き -->

## 関連

<!-- 関連 ADR / Issue / knowledge へのリンク。wikilink [[...]] も可 -->
- 関連 ADR:
- 関連 Issue:
- 関連 knowledge:
```
