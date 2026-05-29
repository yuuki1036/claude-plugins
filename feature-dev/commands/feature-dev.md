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

**Triggered by**: Phase 6 Step 3 G-V loop with a list of auto-fix target issues (`BLOCKER` any-confidence OR `CRITICAL && confidence ≥ 90` from `code-review:self-review` output).

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

### Step 0: Self-lock guard (PostToolUse 自己再帰防止)

**目的**: 将来 feature-dev に PostToolUse hook が入って Phase 5.5 を自動トリガーする構成になった場合、Phase 5.5 内の Edit / Bash が再度 PostToolUse を発火させ、無限ループに陥る可能性がある。TTL ベースの self-lock を持つことで、同一プロジェクトで短期間に Phase 5.5 が重複起動するのを防ぐ。

**現状の振る舞い**: command 経由の手動実行ではループは発生しないが、PostToolUse hook を将来導入する際に lock 機構が無いと事故るため、template を先に入れる。lock が active な場合は Phase 5.5 全体を skip して Phase 6 へ進む（hook 経由起動の場合は `exit 0` 相当でハーネス側が早期復帰）。

```bash
TARGET_PATH=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
HASH=$(echo "$TARGET_PATH" | shasum | cut -c1-12)
LOCK=/tmp/feature-dev-${HASH}.lock
TTL=600

if [ -f "$LOCK" ]; then
  # macOS BSD: stat -f %m / Linux GNU: stat -c %Y の dual path で portability 確保
  MTIME=$(stat -f %m "$LOCK" 2>/dev/null || stat -c %Y "$LOCK" 2>/dev/null || echo 0)
  AGE=$(($(date +%s) - MTIME))
  if [ "$AGE" -lt "$TTL" ]; then
    echo "[self-lock] active (age=${AGE}s < ttl=${TTL}s), skipping Phase 5.5"
    # command 内実行時は Phase 6 へ進む / hook 経由起動時は ハーネスが exit 0 として扱う
    SKIP_PHASE_5_5=1
  fi
fi

if [ -z "$SKIP_PHASE_5_5" ]; then
  touch "$LOCK"   # 新規取得 or TTL 切れ → 取り直し
fi
```

`SKIP_PHASE_5_5` が `1` の場合は Step 1〜4 を skip して **Phase 6** へ進む。

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

self-review 内部の動き（詳細は `${CLAUDE_PLUGIN_ROOT}/../code-review/skills/self-review/SKILL.md` 参照）:

- Phase 0 triage で reviewer 体数を `${CLAUDE_EFFORT}` 連動で決定（feature-dev の effort をそのまま継承）
- Phase 3/4 で explorer + reviewer 並列起動
- Phase 4.5 adaptive deepening（reviewer が unmet_information を申告した場合、追加 explorer 最大 3 体 + 再起動 reviewer 最大 3 体）
- Phase 4.6 meta-reviewer ラウンド（BLOCKER/CRITICAL 検出時、`${CLAUDE_EFFORT}` が xhigh/max のとき動作）
- Phase 5 で **2 軸スコアリング** (confidence 0-100 × severity BLOCKER/CRITICAL/MAJOR/MINOR)
- Phase 6 でレポート出力（severity 別グループ、欠損観点、総括）
- Phase 7 は `--embed` 指定により skip（末尾 marker `[embed-mode: findings-only, no-prompt]` を確認）

**embed mode の利点**: ユーザー操作が 1 回減り、findings をそのまま Step 3 の G-V loop と Step 4 の集約処理に流せる。`--embed` 未対応の旧 code-review (< 2.17.0) では Step 7 の AskUserQuestion がそのまま出るため、code-review plugin の version 確認を Step 0 で済ませている前提。

**Partial failure tolerance**: self-review 自体が失敗した場合は warning を出して Step 3 を skip し、Step 4 で「Phase 6 not executed」状態をユーザー提示する。

### Step 3: Generator-Verifier Loop (automatic critical-issue fix)

self-review の出力（severity × confidence）を以下マッピングで auto-fix トリガーに変換する:

| self-review 出力 | feature-dev 扱い |
|---|---|
| `BLOCKER` (any confidence) | **auto-fix 対象**（最高優先度） |
| `CRITICAL && confidence ≥ 90` | **auto-fix 対象** |
| `CRITICAL && confidence < 90` | 報告のみ（Step 4 で提示） |
| `MAJOR` / `MINOR` (any confidence) | 報告のみ |

**Rationale**: BLOCKER は security/data-loss class なので confidence を問わず即修正。CRITICAL は従来の confidence ≥ 90 閾値を維持して誤検知を防ぐ。

詳細なループ予算ルールは `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` Section 10 を参照。

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

1. **Filter**: self-review 出力から上記マッピングで auto-fix 対象を抽出。0 件なら **terminate with success** → Step 4。
2. **Fingerprint**: 各 issue から `fingerprint = "file:line:focus"` を算出し、current iteration の `fingerprints` 配列に append。
3. **Regression check**: 現 iteration の `fingerprints` と前 iteration の `fingerprints` が 1 件以上 overlap したら **terminate with "regression detected"** → Step 4。
4. **Budget check**: `current_iteration >= max_iterations` なら **terminate with "budget exhausted"** → Step 4。
5. **Notify user**: 1 行 update — `🔄 Iteration {N+1}/{max}: auto-fixing {K} critical issues...`
6. **Fix** (Phase 5 Fix Mode):
   - 各 issue について flagged file:line を読み、self-review が提示した suggested fix を Edit で適用
   - 設計レベル変更が必要なら `code-architect` を `delta-proposal` focus で起動（1 iteration 消費）
7. **Re-review**: `Skill code-review:self-review` を再呼び出し。引数:
   - `--focus <persisting issue の focus 集合>`
   - `--exclude <既に解決した focus 集合>` で重複検査をスキップ可
   - `--embed`（loop 中も AskUserQuestion を skip させる）
8. **Update loop state**: `current_iteration` をインクリメントし、新 iteration エントリを append。
9. Return to step 1。

#### Step 3.3: Loop termination logging

ループ終了時に loop state file へ集約を append:

```json
{
  "terminated_at": "<timestamp>",
  "termination_reason": "success | regression | budget | manual",
  "remaining_critical": <count>,
  "auto_fixed_count": <count>
}
```

このファイルは Phase 7 summary で参照される。

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
