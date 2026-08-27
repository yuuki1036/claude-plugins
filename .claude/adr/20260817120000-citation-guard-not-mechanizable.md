---
id: 20260817120000
status: accepted
phase: current
last-validated: 2026-08-17
supersedes: []
superseded-by: null
append_only: true
tags: [validation, hooks, guardrail, measurement]
---

# ADR-20260817120000: 公開記録の典拠検証は hook にしない（5 述語を実測して真陽性ゼロ）

## ステータス

accepted（2026-08-17）

> **2026-08-28 訂正（GitHub issue #185）**: 見出しの述語数を 4 → 5 に直した。本文の実測表は
> 当初から 5 行（述語 5 は「実在ファイルに対する節見出し引用」）で、見出しだけが実態と
> 食い違っていた。`docs/rule-placement.md` の却下事例表がこの誤りを引き写していたので、
> あわせて訂正している（発火率の記載も 34〜100% → 実測どおり 19〜86% に修正）。
> **決定そのものは変えていない**（append-only の対象は決定であって、事実の誤記ではない）。

## コンテキスト / 背景

`failure-journal` の retro（2026-08-14 / 直近 30 日）で **`claimed-fact-without-source` が 5 回**、うち 3 回が直近 7 日に集中した。窓内で唯一加速していた再発パターンで、いずれも「オーケストレーター自身が外部へ出す成果物（GitHub issue 本文・close コメント）に典拠を書く局面」で起きている。既存のガード 3 つ（reviewer-common.md のツール接地 / self-review Step 7 の訂正伝播前ガード / CLAUDE.md の context7 規約）はどれも発火局面が違い、ここだけ空白だった。

GitHub issue #130 は、この空白を **PreToolUse hook**（`gh issue create` / `gh pr comment` 等を捕まえ、本文中の repo 内ファイル参照の実在を検証する）で埋めることを提案した。`docs/rule-placement.md` の判定（`if`/`grep`/`diff` で決まるものは hook へ）にも合致するように見えた。

## 決定

**作らない。** 提案された検証はいずれも決定的に判定できず、警告として出すと偽陽性しか出さない。

## 根拠（実測）

corpus はこのリポジトリの GitHub issue 全 136 件（本文 6,345 行）。issue 本文はまさに本 hook が対象とする成果物そのものなので、代理ではなく実物で測れる。

| # | 述語 | 抽出 | 発火 | 真陽性 |
|---|------|------|------|--------|
| 1 | パス参照を repo ルート起点で `test -f` | 206 | 169（issue 68 件） | 0 |
| 2 | 同上・行内コードを除外 | 14 | 12（issue 7 件） | 0 |
| 3 | repo 内のどのパス末尾とも一致しない | 206 | 70（issue 43 件） | 0 |
| 4 | 親ディレクトリは実在するがファイルが無い | 203 | 39 | 0 |
| 5 | 実在ファイルに対する節見出し引用（保守的） | 7 | 5 | **0**（下記） |

述語 5 は「ファイルが解決できるものだけを対象にする」ので、1〜4 の偽陽性源（提案中のファイル・他 repo のファイル・placeholder・runtime ファイル）が原理的に消える設計だった。それでも 5 件全部が偽陽性で、理由は **執筆時点では実在した**こと:

```
#95  (07-29) orchestration-guide.md `## 10` → 当時: 「## 10. 反証レイヤー実行手順」
#99  (08-04) orchestration-guide.md `## 13` → 当時: 「## 13. Event Bus publish 先の固定」
#102 (08-04) 同上
#98  (08-04) reviewer-prompts.md   `## 1`  → 当時: 「## 1. 共通指示（全 reviewer 共通）」
#101 (08-04) 同上
```

hook は書き込み時点で発火するので、判定すべきは「今の内容」ではなく「書いた時点の内容」。その基準では 5/5 が正しい引用だった。今日の内容で測ると壊れて見えるのは、その後の分冊で節番号が動いたため。

### 偽陽性の内訳（1〜4 に共通する構造）

issue 本文が実在しないパスを書くのは、**大半が正当**である:

- **提案中のファイル**（`feature-dev/agents/code-reviewer.md` 等）— issue とは「まだ無いものを作れ」と書く場所
- **他プロジェクトのファイル**（`app/lib/withActionErrorHandler.ts` / `frontend/AGENTS.md`）— 消費側 repo の話をしている
- **runtime ファイル**（`.claude/events.json` が 18 件で最多 / `.claude/session-context.md`）— gitignore されており checkout に存在しない
- **placeholder**（`path/to/doc.md` / `evals/reports/recall-YYYYMMDD.md`）
- **パスでないもの**（`React/Next.js` / `README/CLAUDE.md`）

### 動機となった事例が、そもそも捕まらない

issue #130 は #128 の誤り（`docs/pipeline-design.md` に無い記述を典拠として引用）を述語 1 で捕まえられると書いていたが、**このファイルは実在する**。誤っていたのは内容の主張であってパスではない。つまり提案された機械化は、その動機となった事例に対して構造的に無力だった。

## 帰結

- **決定的にできる半分は既にある**: `validate_plugin_quality.py` の `check_doc_anchors` が repo doc 内の `<file>.md ## <番号>` 参照を検証している（v2.47.0 の分冊で 11 箇所実際に切れた実績が導入根拠）。守備範囲を CHANGELOG / `.claude/designs/` へ広げる案も測ったが、あれらは**過去の状態を記述する履歴**なので同じ anachronism の偽陽性を生む
- **残りは LLM 層に留める**: 「主張した内容が典拠に実在するか」は grep で決まらない。`reviewer-common.md` のツール接地 + `[unverified:]` タグ + CLAUDE.md 規約の現行配置を変えない
- `docs/rule-placement.md` の判定表に「`if`/`grep`/`diff` で判定できる**ように見える**が、対象が時間とともに変わる（執筆時点 vs 検査時点）ものは hook にできない」を追記する

## 却下した代替案

- **警告に留めて出す**: 発火率 34%（述語 3）で真陽性ゼロ。「⚠️ が出たときだけ行動する」契約を壊し、既存の全警告の信頼度を下げる。CLAUDE.md が明記する「入れない方がまし」に該当
- **執筆時点の内容と突合する**: hook は書き込み時に走るので作業ツリーの現在値しか見えない。「執筆時点」＝「検査時点」であり、この問題は原理的に解けない

## 関連

- GitHub issue #130（本 ADR で close を提案）
- 同型の失敗 2 件: `code-review/references/design-notes/pending-optimizations.md` `## 9`（版ラベルの追随漏れ検出 6/6 偽陽性 / 未リリース版参照 34% 偽陽性）
- [[docs/rule-placement.md]] — ルール配置の判定フロー
