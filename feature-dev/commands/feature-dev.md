---
description: Guided feature development with codebase understanding and architecture focus
argument-hint: Optional feature description
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - TodoWrite
  - AskUserQuestion
  - Skill
---

# Feature Development

You are helping a developer implement a new feature. Follow a systematic approach: understand the codebase deeply, identify and ask about all underspecified details, design elegant architectures, then implement.

## Core Principles

- **Ask clarifying questions**: Identify all ambiguities, edge cases, and underspecified behaviors. Ask specific, concrete questions rather than making assumptions. Wait for user answers before proceeding with implementation. Ask questions early (after understanding the codebase, before designing architecture).
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

---

## Phase 1: Discovery

**Goal**: Understand what needs to be built

Initial request: $ARGUMENTS

**Actions**:
1. Create todo list with all phases
2. If feature unclear, ask user for:
   - What problem are they solving?
   - What should the feature do?
   - Any constraints or requirements?
3. Summarize understanding and confirm with user

---

## Phase 1.5: Issue Context Detection (linear-workflow / indie-workflow handoff)

**Goal**: Detect upfront Issue context handed off by linear-workflow / indie-workflow and skip redundant discovery.

**Trigger conditions** (match any in `$ARGUMENTS` or recent conversation context):

- `Issue ファイル:` followed by `.claude/linear/*/issues/*.md` or `.claude/indie/*/issues/*.md` path
- A frontmatter block with `feature_dev_plan:` already populated
- Sections labeled "Phase 2.5 関連 Knowledge" / "Phase 5.4" / "Phase 5.5" / "親 Issue サマリー"

**Actions when detected**:

1. Notify the user: "Linear/Indie からの upfront 引き継ぎを検出しました。Discovery と Codebase Exploration はスキップし、引き継ぎ context を起点に Phase 3 へ進みます。"
2. Read the Issue file to extract: title, summary, parent issue summary, related knowledge, existing `feature_dev_plan:`.
3. **If `feature_dev_plan:` already exists**: Treat it as a baseline. Propose deltas rather than redesigning from scratch. Confirm with user whether to reuse or revise.
4. Signal Phase 1.7 that **Issue context is complete** (Phase 1.7 will likely assign 0 explorers, effectively skipping Phase 2). If the Issue context is sparse or contradicts the user's request, signal `partial` so Phase 1.7 can still launch 1-2 explorers for validation.
5. Pass the Issue context verbatim into Phase 4 architect prompts (the architect's "Issue Context Injection" section will consume it).

**Actions when NOT detected**: Proceed normally to Phase 1.7.

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
1. Launch the N code-explorer agents specified by the Phase 1.7 configuration table in parallel (single message, multiple Agent tool calls). Each agent receives:
   - Its assigned `focus` (similar-features / architecture-mapping / shared-modules / history-context / dependency-trace / layer-mapping)
   - Its target scope (specific directory / module / abstraction layer)
   - A request to return 5-10 key files to read

   **Focus templates**:
   - `similar-features`: "Find features similar to [feature] and trace through their implementation comprehensively"
   - `architecture-mapping`: "Map the architecture and abstractions for [feature area], tracing through the code comprehensively"
   - `shared-modules`: "Identify shared modules (`utils/`, `lib/`, `helpers/`) that this feature will touch and document their consumers"
   - `history-context`: "Use git log to understand how [area] evolved and surface prior decisions / abandoned approaches"
   - `dependency-trace`: "Trace upstream/downstream dependencies of [target module] across the codebase"
   - `layer-mapping`: "Map the UI / API / data layer separately for [feature area]"

2. Once the agents return, read all files identified by agents to build deep understanding
3. Present comprehensive summary of findings and patterns discovered

**Partial failure tolerance**: If individual explorers fail, continue with the remaining results. Record failed explorers in a `missing_coverage` list to surface in Phase 7.

---

## Phase 3: Clarifying Questions

**Goal**: Fill in gaps and resolve all ambiguities before designing

**CRITICAL**: This is one of the most important phases. DO NOT SKIP.

**Actions**:
1. Review the codebase findings and original feature request
2. Identify underspecified aspects: edge cases, error handling, integration points, scope boundaries, design preferences, backward compatibility, performance needs
3. **Present all questions to the user in a clear, organized list**
4. **Wait for answers before proceeding to architecture design**

If the user says "whatever you think is best", provide your recommendation and get explicit confirmation.

---

## Phase 4: Architecture Design

**Goal**: Design implementation approaches with different trade-offs

**Actions**:
1. Launch the N code-architect agents specified by the Phase 1.7 configuration table in parallel. Each agent receives its assigned `focus`:
   - `minimal-changes`: smallest change, maximum reuse of existing code
   - `clean-architecture`: maintainability, elegant abstractions, long-term evolvability
   - `pragmatic-balance`: speed + quality tradeoff explicitly weighed
   - `migration-strategy`: phased migration steps with rollback points (migration tasks only)
   - `delta-proposal`: when Issue context provides existing `feature_dev_plan:` — propose deltas only, do not redesign

2. Review all approaches and form your opinion on which fits best for this specific task
3. Present to user: brief summary of each approach, trade-offs comparison, **your recommendation with reasoning**, concrete implementation differences
4. **Ask user which approach they prefer**

**Partial failure tolerance**: If individual architects fail and at least 1 succeeded, continue with the successful results. If all architects failed, fall back to a single architect invocation with `minimal-changes` focus before surfacing the issue.

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

**Triggered by**: Phase 6 Step 3 G-V loop with a list of `confidence ≥ 90` issues.

**Constraints**:
- **Scope is strictly limited** to the reviewer-flagged file:line locations
- The architect design chosen in Phase 4 must be preserved
- No scope expansion, no refactoring of unrelated code

**Actions**:
1. Read each flagged file at the indicated line range
2. Apply the reviewer's suggested fix (or a minimal equivalent that resolves the issue)
3. If the fix requires design-level changes, escalate by launching `code-architect` with focus `delta-proposal` and **consume 1 loop iteration**. Otherwise apply directly with Edit.
4. Update the loop state file (`/tmp/feature-dev-loop-state.json`) — see Phase 6 Step 3 for the format
5. Return to Phase 6 Step 3 (do NOT re-run Phase 5.5 unless the fix is runtime-sensitive and effort ≥ `medium`)

---

## Phase 5.5: Runtime Smoke Test

**Goal**: Catch runtime initialization bugs that static checks (tsc / lint / build) cannot detect, before reaching Quality Review.

**Why this phase exists**: Past incidents (e.g. Prisma v7 adapter requirement) showed bugs that pass all static checks but fail on first request — proxy lazy-init, env var loading, middleware misconfiguration, DB client initialization. Catching these before Phase 6 prevents "review passes but deploy blocks" loops.

### Step 1: Deterministic Detection (gate check)

Run the following Bash check to decide whether smoke test is **required** or **optional**:

```bash
# Detect runtime-sensitive changes in the working tree
git diff --name-only HEAD 2>/dev/null > /tmp/feature-dev-changed-files.txt
git diff HEAD 2>/dev/null > /tmp/feature-dev-diff.txt

REQUIRED_REASONS=()

# Pattern 1: DB client / ORM initialization
grep -qE "(PrismaClient|createClient|drizzle\(|new Sequelize|mongoose\.connect|TypeORM)" /tmp/feature-dev-diff.txt && \
  REQUIRED_REASONS+=("DB client / ORM 初期化変更")

# Pattern 2: Environment variable wiring
grep -qE "(process\.env\.|import\.meta\.env\.|getEnv\()" /tmp/feature-dev-diff.txt && \
  REQUIRED_REASONS+=("環境変数依存の追加・変更")

# Pattern 3: Middleware / proxy / lazy-init
grep -qE "(middleware|Proxy\(|defineProxy|lazy\(|createServer|app\.use)" /tmp/feature-dev-diff.txt && \
  REQUIRED_REASONS+=("middleware / proxy / lazy-init 変更")

# Pattern 4: New route files (Next.js / SvelteKit / Remix / generic routes)
grep -qE "(pages/.*\.(tsx?|jsx?)$|app/.*/(page|route)\.(tsx?|jsx?)$|routes/.*\.(ts|js)$)" /tmp/feature-dev-changed-files.txt && \
  REQUIRED_REASONS+=("新規 route の追加・変更")

if [ ${#REQUIRED_REASONS[@]} -gt 0 ]; then
  echo "REQUIRED: smoke test 必須"
  printf '  - %s\n' "${REQUIRED_REASONS[@]}"
else
  echo "OPTIONAL: 静的変換のみの変更。skip 候補だがユーザ判断"
fi
```

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

**Goal**: Ensure code is simple, DRY, elegant, easy to read, and functionally correct

### Step 1: Mini-triage (diff-based re-judgment)

Phase 1.7 produced a **provisional** reviewer configuration without seeing the implementation diff. Now that the diff exists, refine the configuration:

```bash
# Capture the implementation diff
git diff HEAD 2>/dev/null > /tmp/feature-dev-final-diff.txt
git diff --name-only HEAD 2>/dev/null > /tmp/feature-dev-final-files.txt
```

Apply diff-based pattern matching (mirroring `code-review`'s Phase 0 logic):

- try-catch / catch ブロック追加 → add `error-handling` reviewer
- テストファイル（`.test.` / `.spec.` / `__tests__/`）変更 → add `test-quality` reviewer
- 型定義（`type` / `interface` / `enum`）追加 → add `type-design` reviewer
- 認証・暗号関連ファイル変更 → upgrade `security` reviewer (add or duplicate with auth angle)
- DB / migration ファイル変更 → add `migration-safety` reviewer
- フロントエンド変更 → add `ui-quality` reviewer

Merge the diff-derived focuses with the Phase 1.7 provisional list, then cap by the current effort upper bound (`triage-guide.md` Section 5).

**Minimum guarantee**: `bug-detection` + `claude-md-compliance` (when CLAUDE.md exists) always run.

### Step 2: Launch reviewers (initial pass)

Launch the finalized N code-reviewer agents in parallel (single message, multiple Agent tool calls). Each reviewer receives:
- Its assigned `focus` (and `angle` if part of a redundant pair)
- The full diff (`/tmp/feature-dev-final-diff.txt`)
- Relevant CLAUDE.md content if `claude-md-compliance` focus
- Phase 4 architect output as context (the chosen design)

**Partial failure tolerance**: Continue with successful reviewers. The minimum guarantee (bug-detection) must succeed; if it fails, retry once before failing.

### Step 3: Generator-Verifier Loop (automatic critical-issue fix)

The reviewer's `confidence ≥ 90` indicates a high-certainty critical issue. Such issues are auto-fixed via a bounded loop. See `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` Section 10 for the loop budget rules.

#### Step 3.1: Initialize loop state

Determine `max_iterations` based on `${CLAUDE_EFFORT}`:

| effort | max_iterations |
|---|---|
| `low` | 0 (skip Step 3 entirely — go straight to Step 4) |
| `medium` | 1 |
| `high` | 2 |
| `xhigh` | 3 |
| `max` | 3 |

If `max_iterations == 0`, skip Step 3 and proceed to Step 4. Otherwise initialize the loop state file:

```bash
cat > /tmp/feature-dev-loop-state.json <<EOF
{
  "run_id": "$(uuidgen 2>/dev/null || date +%s)",
  "max_iterations": <N>,
  "current_iteration": 0,
  "iterations": []
}
EOF
```

#### Step 3.2: Loop

Repeat the following until a termination condition fires:

1. **Filter**: From the latest reviewer output, extract issues with `confidence ≥ 90`. If 0 issues, **terminate with success** → Step 4.
2. **Fingerprint**: For each critical issue, compute `fingerprint = "file:line:focus"`. Append to the current iteration's `fingerprints` array.
3. **Regression check**: If the current iteration's `fingerprints` overlap with the previous iteration's `fingerprints` by ≥ 1 entry (= same issue persisted), **terminate with "regression detected"** → Step 4 with a warning.
4. **Budget check**: If `current_iteration >= max_iterations`, **terminate with "budget exhausted"** → Step 4 with a warning.
5. **Notify user**: Print a single-line update — e.g. `🔄 Iteration {N+1}/{max}: auto-fixing {K} critical issues...`
6. **Fix** (Phase 5 Fix Mode):
   - For each critical issue, read the flagged file:line and apply the reviewer's suggested fix via Edit
   - If a fix requires design-level changes, launch `code-architect` with focus `delta-proposal` (consumes 1 iteration)
7. **Re-review**: Re-launch ONLY the reviewer focuses that flagged critical issues. Other reviewers from Step 2 are not re-run.
8. **Update loop state**: Increment `current_iteration`, append the new iteration entry with fingerprints.
9. Return to step 1.

**Reviewer launch in re-review**:
- Same `model: opus`, `effort: max` settings as the initial Step 2 launch
- Pass the updated diff (`git diff HEAD`) and the list of file:line that were just edited

#### Step 3.3: Loop termination logging

When the loop exits, append a summary to the loop state file:

```json
{
  "terminated_at": "<timestamp>",
  "termination_reason": "success | regression | budget | manual",
  "remaining_critical": <count>,
  "auto_fixed_count": <count>
}
```

This file is referenced in Phase 7 summary.

### Step 4: Consolidate and present

1. Consolidate the **latest** reviewer findings (post-loop); report all confidence ≥ 80
2. Tag each issue with `[auto-fixed]` if it was resolved during Step 3, `[persisting]` if it remains after the loop
3. Identify highest severity issues that you recommend fixing manually
4. **Present findings to user and ask what they want to do**:
   - If Step 3 terminated with `success`: confirm and proceed to Phase 7
   - If terminated with `regression` / `budget`: present the persisting critical issues with an explanation, ask user (fix manually now / acknowledge and proceed / abandon)
   - If Step 3 was skipped (`low` effort): present all critical issues for user decision
5. Address issues based on user decision

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
3. **G-V loop summary** (if Step 3 of Phase 6 ran):
   - Read `/tmp/feature-dev-loop-state.json`
   - Report: iteration count, termination reason, auto-fixed issue count, persisting issues
   - If `termination_reason: "regression"` or `"budget"`, surface the persisting fingerprints prominently — they need human attention
4. **Event Bus publish (`feature:implemented`)**:
   - 完了直前に Bash で `feature:implemented` イベントを `.claude/events.jsonl` へ追記する。subscriber がいなくても無害（fire-and-forget）
   - feature-dev は hooks/lib を持たないため、ここでは safe-hook.sh を経由せず JSON Lines を直接書き込む（規約に従い 1 行 1 イベント）
   - payload は最小限の JSON: `{"feature":"<short description>","files_changed":<count>,"phases_completed":[...]}`
   - `feature` は 80 文字以内・ダブルクオート/バックスラッシュ/改行は除去。`files_changed` は今セッションで触ったファイル数（git diff の `--name-only` を `wc -l`）。`phases_completed` は実際に走った phase 番号の JSON 配列
   - 実行コマンド例（`<...>` を Phase 7 のサマリ情報で埋めてから走らせる）:
     ```bash
     mkdir -p .claude
     ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
     printf '{"ts":"%s","plugin":"feature-dev","event":"feature:implemented","payload":%s}\n' \
       "$ts" '{"feature":"<sanitized desc>","files_changed":<n>,"phases_completed":["1","2","..."]}' \
       >> .claude/events.jsonl
     ```
   - 失敗しても Phase 7 全体は成功扱い（イベント送信は best-effort）

---
