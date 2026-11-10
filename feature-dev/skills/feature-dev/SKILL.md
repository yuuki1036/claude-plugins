---
name: feature-dev
description: >
  新機能をコードベース理解 → 設計 → 実装 → 検証まで 8 phase で一気通貫に進める。explorer/architect agent・BDD spec ゲート・静的オラクル・self-review 委譲を内蔵する。
  トリガー: 「機能開発」「新機能を実装」「この機能を作りたい」「実装計画を立てて」「設計から実装まで」「一気通貫で実装」「/feature-dev」
  引数: [機能の説明・Issue ID（省略可）]
effort: high
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Agent
  - TodoWrite
  - AskUserQuestion
  - Skill
  - EnterWorktree
  - ExitWorktree
---


# Feature Development

<!-- SSOT: feature-dev/references/grill-protocol.md @f90e4324 -->

> **各 phase の手順は phase ごとのファイルにある**（`skills/feature-dev/references/phase-<番号>.md`）。phase の見出しに来たら入口の条件を見て、skip しないなら Read の行のファイルを最初に読む。読んだら手順を終え、ファイル末尾の「次は」の phase の見出しへ SKILL.md に戻る（本文の分岐が戻り先を書いている回はそちらに従う。Fix Mode は入口で戻り先が違い、phase-5.md の Fix Mode の 4. が持つ）。見出しだけを見て、本文を読まずに進めない（続きを読まずに進めた回は Phase 6.9 と 7 を飛ばした / GitHub issue #350・#426）。phase ファイルの中の `${CLAUDE_PLUGIN_ROOT}` は、この SKILL.md を Read したパスのプラグインのルートに読み替える

You are helping a developer implement a new feature. Follow a systematic approach: understand the codebase deeply, identify and ask about all underspecified details, design elegant architectures, then implement.

## 適用範囲（起動したらまずここで足切りする）

このワークフローは **新機能を設計から作る**ためのもの。次に当てはまるなら設計までの phase（Phase 1〜4.8）を回さず、
下の停止点を通ってから実装し、**実装の後の検証（Phase 5.3 以降）はそのまま通す**こと:

- typo・設定値変更・文言修正
- 影響範囲が数ファイル・数十行に閉じる bugfix（原因が分かっているもの。原因不明なら `dev-workflow:diagnose`）
- 既存 spec / 設計書どおりに書くだけで、設計判断が残っていないタスク
- レビュー指摘の反映・リファクタのみ

逆に、設計判断が未確定・複数レイヤー（DB・API・UI・URL など）にまたがる・数ファイル・数十行を超える（見積もりが大きい）・新しい部品やモジュールを作る・既存パターンの調査が要る場合は、上の項目（spec どおり・リファクタを含む）に当たっていても最後まで回す（GitHub issue #375）。

**足切りで飛ばすのは設計までで、検証は飛ばさない**（GitHub issue #319）: 実装の後は Phase 5.3（静的オラクル）→ 5.5（動作確認）→ 6（self-review と G-V ループ）→ 6.7（コメント精査）→ 6.9（レビュー後の変更の確認）→ 7（申し送りと読み合わせ）を、8 phase の回と同じ手順で通す。Phase 4 の設計を指す箇所は、停止点で承認された方針に読み替える（Fix Mode の `The architect design chosen in Phase 4 must be preserved` は承認された方針を保つ。Phase 5.5 の smoke の target は architect の出力が無いので Step 1 の検出に任せる）。以前は停止点の後に実装へ移るところで手順が終わっていたため、実装 → build → 動作確認まで進めても self-review を一度も回さずにコミットの確認に入った。

**足切りしたときの停止点**: 足切りしても、書き始める前に 1 回止まる。8 phase を回すときは Phase 5 の承認がモデルの切り替え点になるが、足切りするとそこを通らないので、ここで代わりに止まる。次の 3 つを出してターンを終え、返信を待ってから実装する:

- 足切りしたこと: 上のどの項目に当たったかを 1 つ挙げ、「Phase 1〜4.8 を飛ばし、実装の後は Phase 5.3（静的オラクル）・6（self-review）を含む検証を通す」と書く。起動のされ方（`/feature-dev` での起動・issue-workflow の start で「feature-dev」が選ばれた回）によらず足切りしてよいが、「8 phase で回すなら返信でそう書いてください」と添える。利用者が feature-dev を選んだのは 8 phase を求めてのことかもしれず、起動のされ方からは見分けられないので、ここで選び直せるようにする
- 変更方針: 何をどう変えるか・触るファイルを 2〜3 行で書く。モデルを切り替えると、切り替え先は切り替え前のモデルの思考過程を読めないので、実装に要る判断は本文に残す
- 末尾にこの案内をそのまま添える:

  > 🔀 **モデル切り替えポイント**: 実装を別のモデルで行う場合は、**この返信の前に**アプリのモデル選択で切り替えてください。切り替え先には上の方針だけが引き継がれるので、足りない判断があれば返信に書き足してください。このまま進める場合もそのまま返信で構いません。

返信で 8 phase を求められたら Phase 1 から回す。そうでなければ、実装に入る前に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-5.md` を Read し（Normal Mode の 2. の作業ファイルの clear と 4.、Phase 6 から戻る Fix Mode の制約はそこにある）、TodoWrite へ「実装（phase-5.md）/ Phase 5.3 / 5.5 / 6 / 6.7 / 6.9 / 7」を積む（足切りの回は phase の見出しを順に追わないので、こうして残りの検証を落とさない）。実装中に承認した方針を変えるときは、Phase 5 Normal Mode の 4. に従って止まる。

## Core Principles

- **Grill, don't list**: Identify all ambiguities, edge cases, and underspecified behaviors, then resolve them as a grill (Phase 3) — self-answer facts the codebase answers, leave decisions to the user unless an explicit decision record (ADR / Issue decision / spec) answers them, ask the rest one at a time in dependency order, each with a recommended answer. Don't dump a flat question list. Grill early (after understanding the codebase, before designing architecture). See `${CLAUDE_PLUGIN_ROOT}/references/grill-protocol.md`.
- **Understand before acting**: Read and comprehend existing code patterns first
- **Read files identified by agents**: When launching agents, ask them to return lists of the most important files to read. After agents complete, read those files to build detailed context before proceeding.
- **Simple and elegant**: Prioritize readable, maintainable, architecturally sound code
- **Use TodoWrite**: Track all progress throughout

## Effort Adaptation

Current effort: `${CLAUDE_EFFORT}`. The exact agent count for each phase is determined at **Phase 1.7 (Triage)** based on feature characteristics × effort. See `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` Section 5 for the upper-bound table.

Summary:
- `low`: 4-phase compressed flow (Discovery → Design → Implementation → Smoke test). Explorer skipped, single architect.
- `medium`: Light explorer (≤2), single architect.
- `high` (default): Standard 8-phase flow with triage-driven counts (explorer ≤3, architect ≤2).
- `xhigh`: Multi-explorer (≤5), multi-architect (≤3).
- `max`: Full upper bounds — explorer ≤6, architect ≤3.

Phase 6 reviewer counts are not decided here: self-review's own triage sizes the fleet from the diff under the same `${CLAUDE_EFFORT}`.

## Cost×Precision Pipeline Principles (adopted / dropped)

Of the 10 principles in root CLAUDE.md「コスト×精度パイプライン設計指針」, this workflow **adopts: 1 (funnel = Phase 1.7 triage gates expensive explorer/architect counts; reviewer counts are gated by code-review's triage) / 3 (staged budget = `${CLAUDE_EFFORT}` → agent counts above) / 4 (model routing = explorer:sonnet / architect:opus / review delegated to code-review's routing) / 8 (external oracle + fail-closed = Phase 5.3 type/lint/test gate before LLM review, and Phase 6 fail-fast when code-review is not installed)**. **Dropped**: 2/10 (scoring lives in code-review:self-review, which Phase 6 delegates to), 5 (no unbounded iteration — the G-V fix loop has a fixed retry cap), 6 (evidence accumulation is failure-journal's role), 7 (adversarial verification is code-review's Phase 5.9, not duplicated here).

---

## Phase 1: Discovery

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-1.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 1.3: BDD Spec Creation (bdd-spec plugin handoff)

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-1.3.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 1.4: BDD Spec Evaluation (bdd-spec:evaluate-spec handoff)

入口の条件: `BDD_SPEC_PATH` が空（未生成 / 未インストール / skip）なら Read せず Phase 1.5 へ。

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-1.4.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 1.5: Issue Context Detection (issue-workflow handoff)

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-1.5.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 1.6: Vault Recall (knowledge vault retrieval handoff)

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-1.6.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 1.7: Triage（動的エージェント構成決定）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-1.7.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 1.8: プロジェクト宣言の必読 doc（fail-closed / explorer 0 体でも skip しない）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-1.8.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 2: Codebase Exploration

入口の条件: Phase 1.7 の構成表で explorer が 0 体なら Read せず Phase 3 へ。

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-2.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 3: Clarifying Questions (Grill)

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-3.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 4: Architecture Design

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-4.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 4.5: Design Doc Export (design-doc plugin handoff)

入口の条件: `design=` で design doc を受け取った回（`DESIGN_DOC_PATH` が既にある）なら Read せず Phase 4.8 へ（同じ設計の doc を二重に作らない）。

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-4.5.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 4.8: 実装環境の分離（worktree・opt-in）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-4.8.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 5: Implementation

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-5.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 5.3: 静的オラクルゲート（fail-closed / 決定的検証）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-5.3.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 5.5: Runtime Smoke Test と動作確認

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-5.5.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 6: Quality Review

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-6.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 6.7: コードコメント精査（comment-polish 委譲）

入口の条件: `code-review` が有効でない（Phase 6 Step 0 で fail-fast した）なら Read せず Phase 6.9 へ。

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-6.7.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 6.9: レビュー後の変更の確認

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-6.9.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。

---

## Phase 7: Summary

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/references/phase-7.md` を Read する（手順・分岐・次の phase はそのファイルにある。見出しだけで進めない）。
