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
---


# Feature Development

You are helping a developer implement a new feature. Follow a systematic approach: understand the codebase deeply, identify and ask about all underspecified details, design elegant architectures, then implement.

## 適用範囲（起動したらまずここで足切りする）

このワークフローは **新機能を設計から作る**ためのもの。次に当てはまるなら 8 phase を回さず、
「feature-dev の規模ではないので直接実装する」と 1 文断って通常の実装に移ること:

- typo・設定値変更・文言修正
- 影響範囲が数ファイル・数十行に閉じる bugfix（原因が分かっているもの。原因不明なら `dev-workflow:diagnose`）
- 既存 spec / 設計書どおりに書くだけで、設計判断が残っていないタスク
- レビュー指摘の反映・リファクタのみ

逆に、設計判断が未確定・複数レイヤーにまたがる・既存パターンの調査が要る場合は最後まで回す。

## Core Principles

- **Grill, don't list**: Identify all ambiguities, edge cases, and underspecified behaviors, then resolve them as a grill (Phase 3) — self-answer what the codebase answers, ask the rest one at a time in dependency order, each with a recommended answer. Don't dump a flat question list. Grill early (after understanding the codebase, before designing architecture). See `${CLAUDE_PLUGIN_ROOT}/references/grill-protocol.md`.
- **Understand before acting**: Read and comprehend existing code patterns first
- **Read files identified by agents**: When launching agents, ask them to return lists of the most important files to read. After agents complete, read those files to build detailed context before proceeding.
- **Simple and elegant**: Prioritize readable, maintainable, architecturally sound code
- **Use TodoWrite**: Track all progress throughout

## Effort Adaptation

Current effort: `${CLAUDE_EFFORT}`. The exact agent count for each phase is determined at **Phase 1.7 (Triage)** based on feature characteristics × effort. See `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` Section 5 for the upper-bound table.

Summary:
- `low`: 4-phase compressed flow (Discovery → Design → Implementation → Smoke test). Explorer skipped, single architect, single reviewer.
- `medium`: Light explorer (≤2), single architect, light reviewer (≤2).
- `high` (default): Standard 8-phase flow with triage-driven counts (explorer ≤3, architect ≤2, reviewer ≤3).
- `xhigh`: Multi-explorer (≤5), multi-architect (≤3), redundant reviewers (≤6).
- `max`: Full upper bounds — explorer ≤6, architect ≤3, reviewer ≤8.

## Cost×Precision Pipeline Principles (adopted / dropped)

Of the 10 principles in root CLAUDE.md「コスト×精度パイプライン設計指針」, this workflow **adopts: 1 (funnel = Phase 1.7 triage gates expensive explorer/architect/reviewer counts) / 3 (staged budget = `${CLAUDE_EFFORT}` → agent counts above) / 4 (model routing = explorer:sonnet / architect:opus / review delegated to code-review's routing) / 8 (external oracle + fail-closed = Phase 5.3 type/lint/test gate before LLM review, and Phase 6 fail-fast when code-review is not installed)**. **Dropped**: 2/10 (scoring lives in code-review:self-review, which Phase 6 delegates to), 5 (no unbounded iteration — the G-V fix loop has a fixed retry cap), 6 (evidence accumulation is failure-journal's role), 7 (adversarial verification is code-review's Phase 5.9, not duplicated here).

---

## Phase 1: Discovery

**Goal**: Understand what needs to be built

Initial request: 呼び出し元から渡された引数（`/feature-dev` 経由なら command が展開して渡す）。引数が空なら Step 2 でユーザーに尋ねる。以降この節では **初期リクエスト** と呼ぶ。

**Actions**:
1. Create todo list with all phases
2. If feature unclear, ask user for:
   - What problem are they solving?
   - What should the feature do?
   - Any constraints or requirements?
3. Summarize understanding and confirm with user

---

## Phase 1.3: BDD Spec Creation (bdd-spec plugin handoff)

**Goal**: bdd-spec が入っていれば BDD `spec.md` を生成し、Phase 4 architect が読む真実にする（曖昧な Issue から実装が暴走する失敗を構造的に潰す）。未インストール時は何もしない（後方互換）。

```bash
if grep -q '"bdd-spec@' "$HOME/.claude/settings.json" 2>/dev/null; then BDD_SPEC_AVAILABLE=1; else BDD_SPEC_AVAILABLE=0; fi
```

- `BDD_SPEC_AVAILABLE=0` → **skip して Phase 1.5 へ**（既存の Issue 解釈フローがそのまま動く）
- 初期リクエストに `spec=<path>` があれば生成せずそれを `BDD_SPEC_PATH` に採用し Phase 4 へ渡す
- それ以外で `BDD_SPEC_AVAILABLE=1` → `${CLAUDE_PLUGIN_ROOT}/references/plugin-handoffs.md` の「Phase 1.3」を読み、その手順（既存 spec 確認 → AskUserQuestion → `bdd-spec:create-spec` 非対話呼び出し → fallback）に従う

**Output**: `BDD_SPEC_PATH=<path>` または `""`（未生成）。Phase 4 architect の "BDD Spec Injection" と Phase 1.7 の Issue context completeness 判定に使う。

---

## Phase 1.4: BDD Spec Evaluation (bdd-spec:evaluate-spec handoff)

**Goal**: Phase 1.3 で spec.md を生成した場合、architect の入力にする前に品質ゲート（網羅性・トレーサビリティ）を通す。穴のある spec を真実として渡すと穴が実装に伝播するため、安いオラクルを実装前に挟む。

- `BDD_SPEC_PATH` が空（未生成 / 未インストール / skip） → **Phase 1.4 を skip して Phase 1.5 へ**
- `BDD_SPEC_PATH` がセット済み → `${CLAUDE_PLUGIN_ROOT}/references/plugin-handoffs.md` の「Phase 1.4」を読み、その手順（`bdd-spec:evaluate-spec --embed` 呼び出し → 🔴 critical があれば AskUserQuestion で修正を既定に、🟡 以下は情報提示のみ → fallback）に従う

---

## Phase 1.5: Issue Context Detection (issue-workflow handoff)

**Goal**: Detect upfront Issue context handed off by issue-workflow and skip redundant discovery.

**Trigger conditions** (match any in the 初期リクエスト or recent conversation context):

- `Issue ファイル:` followed by `.claude/linear/*/issues/*.md` or `.claude/indie/*/issues/*.md` path
- A frontmatter block with `feature_dev_plan:` already populated
- Sections labeled "Phase 2.5 関連 Knowledge" / "Phase 5.4" / "Phase 5.5" / "親 Issue サマリー"

**Actions when detected**:

1. Notify the user: "Linear/Indie からの upfront 引き継ぎを検出しました。Discovery と Codebase Exploration（Phase 2 探索）はスキップしますが、Phase 1.6 (Vault Recall) → Phase 1.7 (Triage) は通過し、引き継ぎ context を起点に Phase 3 へ進みます。"（引き継ぎ context が揃っているケースこそ横断知見が効くため、detected 経路でも Phase 1.6 は skip しない）
2. Read the Issue file to extract: title, summary, parent issue summary, related knowledge, existing `feature_dev_plan:`.
3. **If `feature_dev_plan:` already exists**: Treat it as a baseline. Propose deltas rather than redesigning from scratch. Confirm with user whether to reuse or revise.
4. Signal Phase 1.7 that **Issue context is complete** (Phase 1.7 will likely assign 0 explorers, effectively skipping Phase 2). If the Issue context is sparse or contradicts the user's request, signal `partial` so Phase 1.7 can still launch 1-2 explorers for validation.
5. Pass the Issue context verbatim into Phase 4 architect prompts (the architect's "Issue Context Injection" section will consume it).

**Actions when NOT detected**: Proceed normally to Phase 1.6.

---

## Phase 1.6: Vault Recall (knowledge vault retrieval handoff)

**Goal**: 過去プロジェクト横断の知見（落とし穴・設計判断・移行ノウハウ）を knowledge vault から recall し、Phase 4 architect に advisory 注入する。recall をモデルの文脈判断に委ねると省略されうるため、設計着手直前の必須ステップとして埋め込み「引き忘れ」を構造的に防ぐ。注入知見は advisory で、現コードベースのパターンと矛盾する場合は現コードベースを優先する。

kvault は feature-dev 外の外部 CLI。CLI 本体 + vault dir の二段で存在確認し、いずれか欠けたら skip する（後方互換）:

```bash
# vault の場所は KNOWLEDGE_VAULT_ROOT で指定（個人環境パスをハードコードしない）。未設定なら skip。
if [ -n "$KNOWLEDGE_VAULT_ROOT" ] && command -v kvault >/dev/null 2>&1 && [ -d "$KNOWLEDGE_VAULT_ROOT" ]; then
  VAULT_AVAILABLE=1
else
  VAULT_AVAILABLE=0
fi
```

- `VAULT_AVAILABLE=0` → **Phase 1.6 を skip して Phase 1.7 へ**。skip 理由を 1 行 notify（未設定 / 未導入 / vault dir 不在）
- `VAULT_AVAILABLE=1` → `${CLAUDE_PLUGIN_ROOT}/references/plugin-handoffs.md` の「Phase 1.6」を読み、その手順（キーワード列クエリ構築 → `kvault recall` → rank+gap で関連判定 → advisory 注入。絶対閾値で足切りしない等の運用知見つき）に従う

**Output**: `VAULT_KNOWLEDGE=<関連知見の要約>` または `""`（未取得 / 関連なし / skip）。Phase 4 architect の "Vault Knowledge Injection" に渡す。

---

## Phase 1.7: Triage（動的エージェント構成決定）

**Goal**: Decide how many explorer / architect / reviewer agents to launch in subsequent phases, with concrete focus assignments.

**Why this phase exists**: Static "always 2-3 explorers + 3 reviewers" configuration wastes tokens on simple tasks and under-covers complex ones. Phase 1.7 inspects feature characteristics × `${CLAUDE_EFFORT}` and produces an agent configuration table that subsequent phases read.

**Run in main context (do NOT use the Agent tool here).**

### Step 1: Read the triage guide

Read `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` and apply its 2-stage logic.

### Step 2: Stage 1 — Type judgment

Identify:
- **Feature type**: bugfix / extension / new-feature / refactor / migration / cross-cutting (multiple allowed)
- **Explorer necessity**: skip if Issue context provides a complete `feature_dev_plan:` AND the feature is isolated; otherwise required
- **Architect focuses**: always include `minimal-changes`; add `clean-architecture` / `pragmatic-balance` / `migration-strategy` per the guide
- **Reviewer focuses (provisional)**: `bug-detection` always; add `claude-md-compliance` / `security` / `performance` / `api-design` / `ui-quality` / `type-design` / `migration-safety` per the guide

Consider these signals:
- `package.json` major dependencies (React/Next.js → vercel-best-practices, etc.)
- CLAUDE.md presence
- Issue context content (if Phase 1.5 detected one)

### Step 3: Stage 2 — Count, focus, redundancy

Apply the count tables in `triage-guide.md` Section 4, capped by the effort upper bounds in Section 5.

**Minimum guarantee** (across all effort levels):
- architect ≥ 1
- reviewer ≥ 1 (bug-detection is mandatory)
- explorer may be 0 (when Issue context is complete)

### Step 4: Output the configuration table

Present the table in the format defined in `triage-guide.md` Section 7. Example:

```
## Phase 1.7 トリアージ結果

### 特性
- スコープ: medium
- 種別: extension
- リスク因子: [auth]
- Issue context: partial
- React/Next.js: yes

### エージェント構成

#### Phase 2 探索（explorer）
| # | focus | 対象 | 指示 |
| E1 | similar-features | src/auth/ | ... |

#### Phase 4 設計（architect）
| # | focus | 指示 |
| A1 | minimal-changes | ... |

#### Phase 6 レビュー（reviewer）— 暫定（Phase 6 で diff 再判定）
| # | focus | angle | 指示 |
| R1 | bug-detection | data-flow | ... |
```

Subsequent phases consume this table directly.

---

## Phase 2: Codebase Exploration

**Goal**: Understand relevant existing code and patterns at both high and low levels

**Skip condition**: Phase 1.7 assigned 0 explorers. Skip directly to Phase 3.

**Actions**:
1. Launch the N code-explorer agents specified by the Phase 1.7 configuration table in parallel (single message, multiple Agent tool calls, each with `run_in_background: false` — the Agent tool defaults to background since CC 2.1.198, and omitting it means results are not awaited). Each agent receives:
   - Its assigned `focus` (similar-features / architecture-mapping / shared-modules / history-context / dependency-trace / layer-mapping)
   - Its target scope (specific directory / module / abstraction layer)
   - A request to return 5-10 key files to read

   **Focus templates**:
   - `similar-features`: "Find features similar to [feature] and trace through their implementation"
   - `architecture-mapping`: "Map the architecture and abstractions for [feature area], tracing through the code"
   - `shared-modules`: "Identify shared modules (`utils/`, `lib/`, `helpers/`) that this feature will touch and document their consumers"
   - `history-context`: "Use git log to understand how [area] evolved and surface prior decisions / abandoned approaches"
   - `dependency-trace`: "Trace upstream/downstream dependencies of [target module] across the codebase"
   - `layer-mapping`: "Map the UI / API / data layer separately for [feature area]"

2. Once the agents return, read all files identified by agents to build deep understanding
3. Present a summary of findings and patterns discovered

**Partial failure tolerance**: If individual explorers fail, continue with the remaining results. Record failed explorers in a `missing_coverage` list to surface in Phase 7.

---

## Phase 3: Clarifying Questions (Grill)

**Goal**: Fill in gaps and resolve all ambiguities before designing — by **grilling**, not by dumping a flat question list

**CRITICAL**: This is one of the most important phases. DO NOT SKIP.

**Why grill instead of a list**: A flat list forces the user to answer everything at once — including questions the codebase already answers — and hides the dependency order between decisions. The grill protocol resolves the design tree one branch at a time, self-answering what the code can answer and recommending an answer for the rest. Full protocol: `${CLAUDE_PLUGIN_ROOT}/references/grill-protocol.md`.

### Step 1: Enumerate candidate ambiguities

Review the Phase 2 codebase findings + original request. List every underspecified aspect: edge cases, error handling, integration points, scope boundaries, design preferences, backward compatibility, performance needs.

### Step 2: Self-resolve from the codebase (grill principle ①)

For each candidate, ask "can this be answered by what we already know?" — Phase 2 explorer findings, a quick `Grep` / `Glob`, the BDD spec (Phase 1.3), or the Issue context (Phase 1.5). If yes, **resolve it yourself, drop it from the list, and record it as a 確定した前提** to surface in Step 5. Do NOT ask the user something the code already answers.

### Step 3: Order by design-tree dependency

Sort the remaining questions so that **upstream decisions come first** — those that constrain or eliminate downstream questions (e.g. "replace vs augment existing auth?" gates a dozen follow-ups).

### Step 4: Grill one at a time (grill principles ②③)

For each remaining question, in dependency order:

1. Ask it with `AskUserQuestion` — **one question per call** — with a **recommended answer as the first option suffixed `(Recommended)`** plus a one-line rationale.
2. After the answer, re-evaluate the remaining questions: a prior answer may resolve, reshape, or reveal a downstream branch. Collapse resolved ones; insert newly-revealed ones.
3. If the user says "whatever you think is best", take the recommended option and continue.

Stop when no open branch remains. **Proportionality**: if only 1-2 questions remain and the direction is obvious, batch them into a single `AskUserQuestion` rather than grilling serially (avoid over-questioning).

### Step 5: Confirm the design contract

Summarize before Phase 4: (a) the **確定した前提** auto-resolved in Step 2, (b) every user decision from Step 4. This is the implicit contract the Phase 4 architects must honor.

---

## Phase 4: Architecture Design

**Goal**: Design implementation approaches with different trade-offs

**Actions**:
1. Launch the N code-architect agents specified by the Phase 1.7 configuration table in parallel (each with `run_in_background: false` — same rationale as Phase 2). Each agent receives its assigned `focus`:
   - `minimal-changes`: smallest change, maximum reuse of existing code
   - `clean-architecture`: maintainability, elegant abstractions, long-term evolvability
   - `pragmatic-balance`: speed + quality tradeoff explicitly weighed
   - `migration-strategy`: phased migration steps with rollback points (migration tasks only)
   - `delta-proposal`: when Issue context provides existing `feature_dev_plan:` — propose deltas only, do not redesign

   **BDD spec injection**: Phase 1.3 で `BDD_SPEC_PATH` が設定された場合、各 architect の prompt に以下を追加する:
   - `BDD spec path: <BDD_SPEC_PATH>` — architect は冒頭でこのファイルを Read し、Feature / Scenario / Examples / 同値分割表を **authoritative requirements** として扱う
   - 設計は spec.md の AC ↔ Scenario マッピングを保つこと（架空の Scenario を増やさない、削らない）
   - 詳細は `agents/code-architect.md` の "BDD Spec Injection" セクション

   **Vault knowledge injection**: Phase 1.6 で `VAULT_KNOWLEDGE` が非空の場合、各 architect の prompt に以下を追加する:
   - `Vault Knowledge:` ブロックとして関連知見（`path` / `title` / `excerpt`）を列挙する
   - これは **別プロジェクト横断の参考知見 (advisory)** であり、BDD spec のような authoritative requirement ではない。現コードベースのパターンと矛盾する場合は **現コードベースを優先** する
   - 関連する過去の落とし穴があれば設計の Critical Details に反映させ、採用した知見は出典 (`title`) を明記させる
   - 詳細は `agents/code-architect.md` の "Vault Knowledge Injection" セクション

2. Review all approaches and form your opinion on which fits best for this specific task
3. Present to user: brief summary of each approach, trade-offs comparison, **your recommendation with reasoning**, concrete implementation differences
4. **Ask user which approach they prefer**

**Partial failure tolerance**: If individual architects fail and at least 1 succeeded, continue with the successful results. If all architects failed, fall back to a single architect invocation with `minimal-changes` focus before surfacing the issue.

---

## Phase 4.5: Design Doc Export (design-doc plugin handoff)

**Goal**: Phase 4 の architect 比較とユーザー採用決定（プロンプト内で揮発する）を design doc として `.claude/designs/` に永続化する。後続の同領域開発の参照元・実装後の as-built 記録（`phase: target → current`）として再利用できる。design-doc 未インストール時は何もしない（後方互換）。

```bash
if grep -q '"design-doc@' "$HOME/.claude/settings.json" 2>/dev/null; then DESIGN_DOC=1; else DESIGN_DOC=0; fi
```

- `DESIGN_DOC=0` → 本 Phase を skip して Phase 5 へ
- `DESIGN_DOC=1` → `${CLAUDE_PLUGIN_ROOT}/references/plugin-handoffs.md` の「Phase 4.5」を読み、その手順（AskUserQuestion → `design-doc:design-doc` の export 非対話呼び出し → fallback）に従う

**Output**: `DESIGN_DOC_PATH=<path>`（生成時）。Phase 7 サマリに含め、実装完了後の `phase: target → current` 更新案内に使う。

---

## Phase 5: Implementation

**Goal**: Build the feature (Normal Mode) or apply targeted fixes (Fix Mode)

### Mode Detection

Phase 5 has two modes — check the invocation context:

- **Normal Mode**: Triggered by Phase 4 completion. Implements the feature from scratch.
- **Fix Mode**: Triggered by Phase 6 Generator-Verifier loop (Step 3). Applies only the specific reviewer-flagged critical issues. **DO NOT START WITHOUT USER APPROVAL** is waived for Fix Mode (the loop is automatic; reaching the user-decision step happens at Phase 6 Step 4).

### Normal Mode

**DO NOT START WITHOUT USER APPROVAL**

**Actions**:
1. Wait for explicit user approval
2. Read all relevant files identified in previous phases
3. Implement following chosen architecture
4. Follow codebase conventions strictly
5. Write clean, well-documented code
6. Update todos as you progress

### Fix Mode

**Triggered by**: Phase 6 Step 3 G-V loop with a list of auto-fix target issues (`BLOCKER` any-confidence OR `CRITICAL && confidence ≥ 90` from `code-review:self-review` output).

**Constraints**:
- **Scope is strictly limited** to the reviewer-flagged file:line locations
- The architect design chosen in Phase 4 must be preserved
- No scope expansion, no refactoring of unrelated code

**Actions**:
1. Read each flagged file at the indicated line range
2. Apply the reviewer's suggested fix (or a minimal equivalent that resolves the issue)
3. If the fix requires design-level changes, escalate by launching `code-architect` (with `run_in_background: false`) with focus `delta-proposal` and **consume 1 loop iteration**. Otherwise apply directly with Edit.
4. Update the loop state file (`/tmp/feature-dev-loop-state.json`) — see Phase 6 Step 3 for the format
5. Return to Phase 6 Step 3 (do NOT re-run Phase 5.5 unless the fix is runtime-sensitive and effort ≥ `medium`)

---

## Phase 5.3: 静的オラクルゲート（fail-closed / 決定的検証）

**Goal**: runtime smoke test（Phase 5.5）と LLM レビュー（Phase 6 = 多体 agent）に進む**手前**で、型チェック・lint・テストという**決定的オラクル**を変更範囲に絞って走らせ、機械的に落とせる欠陥をここで潰す。

**Why this phase exists**: Phase 5.5 は *runtime* smoke test、Phase 6 は *LLM* レビューで、型/テストを exit code で判定する決定的ゲートがパイプラインに無かった。型エラー・テスト赤はサーバ起動（5.5）や multi-agent レビュー（6）に投げるより先に、最も安いオラクルで落とすのが Clearwing 原則 8（外部オラクル + fail-closed）。ルート CLAUDE.md「コスト×精度パイプライン設計指針」参照。最安オラクルを先頭に置くため Phase 5.5 より前に配置し、Phase 5.5 が skip される静的変更でも必ず通す。

### Step 1: オラクル検出（無ければ graceful skip）

```bash
git diff --name-only HEAD 2>/dev/null > /tmp/feature-dev-changed-files.txt
ORACLE_TC=""; ORACLE_LINT=""; ORACLE_TEST=""
if [ -f package.json ]; then
  grep -q '"typecheck"' package.json && ORACLE_TC="npm run typecheck"
  [ -z "$ORACLE_TC" ] && grep -q '"tsc"' package.json && ORACLE_TC="npm run tsc"
  grep -q '"lint"' package.json && ORACLE_LINT="npm run lint"
  grep -q '"test"' package.json && ORACLE_TEST="npm test"
  # npm init 既定のプレースホルダ（"test": "echo ... exit 1"）は実テストではないので除外（恒常赤の誤爆防止）
  grep -Eq '"test"[[:space:]]*:[[:space:]]*"echo' package.json && ORACLE_TEST=""
fi
# 他エコシステムのフォールバック（存在するもののみ採用）
[ -z "$ORACLE_TC" ] && [ -f tsconfig.json ] && command -v npx >/dev/null && ORACLE_TC="npx tsc --noEmit"
[ -z "$ORACLE_TEST" ] && [ -f Cargo.toml ] && ORACLE_TEST="cargo test"
[ -z "$ORACLE_TEST" ] && [ -f go.mod ] && ORACLE_TEST="go test ./..."
[ -z "$ORACLE_TC" ] && [ -f pyproject.toml ] && command -v mypy >/dev/null && ORACLE_TC="mypy ."
```

### Step 2: 実行（変更範囲に絞る。全ビルド/全テストは重いので避ける）

- 型チェック・lint は常時実行（安い）。テストは effort に応じて出し分ける（`triage-guide.md` の effort 予算に接続）:
  - `low` / `medium`: 型チェック（+ lint）のみ。テストは Phase 5.5 と Phase 6 に委ねる
  - `high` 以上: 型チェック + lint + テスト。テストは可能なら**変更ファイルに関連するもののみ**（例: jest なら `npx jest --findRelatedTests $(cat /tmp/feature-dev-changed-files.txt)`、他は最小スコープ）
- 各コマンドの exit code を記録する。

### Step 3: 判定（fail-closed）

- **全て緑（exit 0）**: Phase 5.5 へ進む。この結果は Phase 6 の focus 判定でも「静的検証済み」として扱ってよい。
- **いずれか赤（exit≠0）**: Phase 5.5 / Phase 6 へ**進まず**、エラー出力を Phase 5 Fix Mode に渡して決定的に修正 → 本ゲートを再実行。
- **オラクル不在（検出ゼロ）**: gate できないので Phase 5.5 へ進むが、Phase 7 summary に「静的オラクル無し（型/テスト未検証）」と明記する（fail-open は「検証手段が無い」ときだけ許容。曖昧・実行エラー時は赤扱いで保留に倒す）。

**暴走ガード**: 本ゲート ↔ Fix Mode の往復は**最大 2 回**まで。2 回修正しても赤が残る場合はループを止め、`AskUserQuestion` で「手動修正して再開 / 承知の上で Phase 5.5 へ進む / abandon」をユーザーに委ねる（同一エラーの無限往復を防ぐ）。`low` effort では本ゲート自体を skip 可（速度優先。ただし skip した旨は summary に残す）。

---

## Phase 5.5: Runtime Smoke Test

**Goal**: Catch runtime initialization bugs that static checks (tsc / lint / build) cannot detect, before reaching Quality Review.

**Why this phase exists**: Past incidents (e.g. Prisma v7 adapter requirement) showed bugs that pass all static checks but fail on first request — proxy lazy-init, env var loading, middleware misconfiguration, DB client initialization. Catching these before Phase 6 prevents "review passes but deploy blocks" loops.

### Step 0-1: Self-lock guard と runtime-sensitive 検出

詳細な bash は `${CLAUDE_PLUGIN_ROOT}/references/smoke-test.md` にある。本文では判定結果だけ使う:

1. **Self-lock guard**（将来 PostToolUse hook で自動トリガーする構成に備えた TTL ベースの自己再帰防止）を評価する。lock が active なら `SKIP_PHASE_5_5=1` として Step 2〜4 を skip し **Phase 6** へ進む（command 経由の手動実行では通常 active にならない）。
2. **Deterministic detection**: 作業ツリーの diff を references の pattern（DB/ORM 初期化・環境変数 wiring・middleware/proxy/lazy-init・新規 route）と照合し、1 つでも当たれば **REQUIRED**、無ければ **OPTIONAL** と判定する。判定理由（当たった pattern）を保持して Step 2 の確認に添える。

### Step 2: User Confirmation

Present the detection result with `AskUserQuestion`:

- **If REQUIRED**: Ask "smoke test を実行しますか？" with options `[実行する (推奨) / skip して Phase 6 へ]`. Strongly recommend execution.
- **If OPTIONAL**: Ask "静的変換のみの変更でした。smoke test を実行しますか？" with options `[skip (推奨) / 実行する]`.

### Step 3: Execute via dev-workflow:ui-verify

If the user chose to execute:

1. Identify smoke test targets from the architect's `Runtime Smoke Test Targets` output (Phase 4). Fall back to "all newly added or modified routes" detected in Step 1 if not specified.
2. Invoke the `dev-workflow:ui-verify` skill via the Skill tool with:
   - Target routes / URLs to access
   - Pass criteria: **console error 0, network 4xx/5xx 0**
3. If chrome-devtools MCP is unavailable (the dev-workflow SessionStart hook warns when unset), fall back to manual verification:
   - Print the dev server start command and target URLs
   - Ask the user to manually verify and report back
   - Do NOT hard-fail; record as "manual check pending"

### Step 4: Triage Findings

- **Pass (no errors)**: Proceed to Phase 6
- **Fail (errors detected)**: Present findings, do NOT proceed to Phase 6 until the user decides:
  - Fix now → return to Phase 5
  - Acknowledge and proceed → record as a known issue and continue to Phase 6
- **Skipped / manual pending**: Note in the Phase 7 summary, proceed to Phase 6

---

## Phase 6: Quality Review

**Goal**: `code-review:self-review` skill に委譲して品質ゲートを通し、致命指摘を Generator-Verifier ループで自動 fix する

**設計判断**: v2.0.0 で feature-dev 内蔵の `code-reviewer` agent を廃止し、`code-review` plugin の `self-review` skill に品質基準を一本化した。理由は (a) 同リポジトリ内で reviewer ロジックが二重化していた DRY 違反、(b) `code-review` の 2 軸スコアリング × 15 観点 × specialist × meta-reviewer 構造の方が遥かに堅牢だから。`code-review` plugin は `_requirements` で `required: false` 宣言（claude-plugins 規約で plugin 間の強制依存を避ける）だが、Phase 6 では fail-fast する。

### Step 0: Existence Check (code-review plugin)

Phase 6 は `code-review:self-review` skill に依存する。冒頭で plugin の存在を確認し、未インストール時は **fail-fast** する:

```bash
if ! grep -q '"code-review@' "$HOME/.claude/settings.json" 2>/dev/null; then
  echo "❌ Phase 6 は code-review plugin に依存します。先にインストール:"
  echo "   claude plugin install code-review@yuuki1036-claude-plugins"
  echo ""
  echo "Phase 5 までの成果物は維持されています。インストール後、Phase 6 から再開してください。"
  exit 1
fi
```

ユーザーに「インストールして再開 / Phase 6 を skip して Phase 7 へ / abandon」を `AskUserQuestion` で確認するのも可。SessionStart hook (`hooks/scripts/check-deps.sh`) が事前に warning を出しているはずだが、ここで再確認することでセッション中盤のインストールにも対応する。

### Step 1: Mini-triage (diff-based focus list)

Phase 1.7 は **provisional** な reviewer focus list を出している。実装後の diff を読んで focus を refine し、self-review に渡す `--focus` 引数を確定する。

```bash
# Capture the implementation diff (Phase 5.5 でも同じファイルを使う前提)
git diff HEAD 2>/dev/null > /tmp/feature-dev-final-diff.txt
git diff --name-only HEAD 2>/dev/null > /tmp/feature-dev-final-files.txt
```

Apply diff-based pattern matching:

- try-catch / catch ブロック追加 → add `error-handling`
- テストファイル（`.test.` / `.spec.` / `__tests__/`）変更 → add `test-quality`
- 型定義（`type` / `interface` / `enum`）追加 → add `type-design`
- 認証・暗号関連ファイル変更 → upgrade `security`
- DB / migration ファイル変更 → add `migration-safety`
- フロントエンド変更 → add `ui-quality`

Merge with the Phase 1.7 provisional list, then cap by the current effort upper bound (`triage-guide.md` Section 5).

**Minimum guarantee**: `bug-detection` + `claude-md-compliance` (when CLAUDE.md exists) を必ず含める。

最終 focus list を `,` 区切りで整形（例: `bug-detection,claude-md-compliance,security,type-design`）。

### Step 2: Invoke code-review:self-review

`Skill` tool で `code-review:self-review` を呼ぶ。引数:

- `--focus <comma-separated focus list from Step 1>`
- `--embed`（**必須**: feature-dev は自前で findings を集約するため、self-review 終端の修正方針確認 AskUserQuestion を skip させる）
- base branch は省略（self-review が `git remote show origin | grep "HEAD branch"` で自動検出）
- 未コミット diff は self-review 側で `git diff` / `git diff --cached` を併用して取得

self-review 内部の動き（詳細は `code-review:self-review` skill の SKILL.md 参照）:

- Phase 0 triage で reviewer 体数を `${CLAUDE_EFFORT}` 連動で決定（feature-dev の effort をそのまま継承）
- Phase 3/4 で explorer + reviewer 並列起動
- Phase 4.5 adaptive deepening（reviewer が unmet_information を申告した場合、追加 explorer 最大 3 体 + 再起動 reviewer 最大 3 体）
- Phase 4.6 meta-reviewer ラウンド（BLOCKER/CRITICAL 検出時、`${CLAUDE_EFFORT}` が xhigh/max のとき動作）
- Phase 5 で **2 軸スコアリング** (confidence 0-100 × severity BLOCKER/CRITICAL/MAJOR/MINOR)
- Phase 6 でレポート出力（severity 別グループ、欠損観点、総括）
- Phase 6.5（**code-review ≥ 2.18.0**）で `--embed` 時に **構造化 findings JSON ブロック**を markdown レポート直後に出力（`<!-- FINDINGS_JSON_START -->` / `<!-- FINDINGS_JSON_END -->` で囲む）
- Phase 7 は `--embed` 指定により skip（末尾 marker `[embed-mode: findings-only, no-prompt]` を確認）

**embed mode の利点**: ユーザー操作が 1 回減り、findings をそのまま Step 3 の G-V loop と Step 4 の集約処理に流せる。`--embed` 未対応の旧 code-review (< 2.17.0) では Step 7 の AskUserQuestion がそのまま出るが、Step 0 は **存在チェックのみ**で version は確認していない。旧版が混在しうる前提で、JSON ブロック不在時は markdown フォールバックへ、AskUserQuestion 出力時はそれを findings 提示として吸収する（version ゲートは張らない）。

**構造化 findings の消費（dual format）**: Step 3 / Step 4 は self-review 出力を、`<!-- FINDINGS_JSON_START -->`〜`END` の JSON ブロックがあれば決定的にパースし、無ければ markdown を正規表現でフォールバックパースする。schema 契約と詳細は `${CLAUDE_PLUGIN_ROOT}/references/review-loop.md` を参照。

**Partial failure tolerance**: self-review 自体が失敗した場合は warning を出して Step 3 を skip し、Step 4 で「Phase 6 not executed」状態をユーザー提示する。

### Step 3: Generator-Verifier Loop (automatic critical-issue fix)

self-review の出力を severity × confidence で auto-fix トリガーに変換し、致命指摘を Phase 5 Fix Mode で自動修正して再レビューするループ。

| self-review 出力 | feature-dev 扱い |
|---|---|
| `BLOCKER` (any confidence) | **auto-fix 対象**（最高優先度） |
| `CRITICAL && confidence ≥ 90` | **auto-fix 対象** |
| `CRITICAL && confidence < 90` | 報告のみ（Step 4 で提示） |
| `MAJOR` / `MINOR` (any confidence) | 報告のみ |

**Rationale**: BLOCKER は security/data-loss class なので confidence を問わず即修正。CRITICAL は confidence ≥ 90 閾値を維持して誤検知を防ぐ。

ループの初期化（`${CLAUDE_EFFORT}` → `max_iterations`）・実行（filter → fingerprint → regression/budget チェック → Fix → 再レビュー）・終了ログの手順は `${CLAUDE_PLUGIN_ROOT}/references/review-loop.md` に従う。`low` effort は `max_iterations=0` で Step 3 を skip し Step 4 へ直行する。

### Step 4: Consolidate and present

1. **集約**: self-review の最終出力（post-loop）を読み、全ての BLOCKER / CRITICAL / MAJOR / MINOR を列挙
2. **タグ付け**: Step 3 で解決したものは `[auto-fixed]`、ループ後も残ったものは `[persisting]`
3. **Recommend**: 手動修正を推奨する高 severity issue を identify
4. **Present findings and ask**:
   - Step 3 が `success` で終了: 確認のみで Phase 7 へ
   - Step 3 が `regression` / `budget` で終了: persisting critical issues を提示し、ユーザーに（手動修正 / 受け入れて続行 / abandon）を聞く
   - Step 3 が skip（`low` effort）: 全 critical を提示してユーザー判断
   - self-review が失敗: warning を提示し、ユーザー判断（リトライ / skip / abandon）
5. ユーザー判断に従って対応

---

## Phase 7: Summary

**Goal**: Document what was accomplished

**Actions**:
1. Mark all todos complete
2. Summarize:
   - What was built
   - Key decisions made
   - Files modified
   - Suggested next steps
   - **Design doc follow-up** (Phase 4.5 で `DESIGN_DOC_PATH` がある場合のみ): 実装が完了したので、doc の frontmatter を `phase: target → current` に更新するよう案内する（実装と設計が乖離した箇所があれば doc への追記 or supersede も）。更新は design-doc プラグイン側の運用（ユーザー操作）に委ねる
3. **G-V loop summary** (if Step 3 of Phase 6 ran):
   - Read `/tmp/feature-dev-loop-state.json`
   - Report: iteration count, termination reason, auto-fixed issue count, persisting issues
   - If `termination_reason: "regression"` or `"budget"`, surface the persisting fingerprints prominently — they need human attention
4. **Event Bus publish (`feature:implemented`)**:
   - 完了直前に `feature:implemented` イベントを `.claude/events.jsonl` へ追記する。subscriber がいなくても無害（fire-and-forget）
   - feature-dev は `hooks/lib/safe-hook.sh` を同梱しているため、`event_bus_publish` 経由で追記する（規約どおり 1 行 1 イベント）。`SAFE_HOOK_NAME` を `feature-dev` に上書きして publisher を識別する
   - payload は最小限の JSON: `{"feature":"<short description>","files_changed":<count>,"phases_completed":[...]}`
   - `feature` は 80 文字以内・ダブルクオート/バックスラッシュ/改行は除去。`files_changed` は今セッションで触ったファイル数（git diff の `--name-only` を `wc -l`）。`phases_completed` は実際に走った phase 番号の JSON 配列
   - 実行コマンド例（`<...>` を Phase 7 のサマリ情報で埋めてから走らせる）:
     ```bash
     source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null && \
       SAFE_HOOK_NAME="feature-dev" event_bus_publish "feature:implemented" \
       '{"feature":"<sanitized desc>","files_changed":<n>,"phases_completed":["1","2","..."]}'
     ```
   - 失敗しても Phase 7 全体は成功扱い（イベント送信は best-effort）

---
