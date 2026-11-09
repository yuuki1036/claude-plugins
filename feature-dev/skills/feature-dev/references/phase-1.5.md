## Phase 1.5: Issue Context Detection (issue-workflow handoff)

**Goal**: Detect upfront Issue context handed off by issue-workflow and skip redundant discovery.

**Trigger conditions** (match any in the 初期リクエスト or recent conversation context):

- `Issue ファイル:` followed by `.claude/linear/*/issues/*.md` or `.claude/indie/*/issues/*.md` path
- A frontmatter block with `feature_dev_plan:` already populated
- `design=<path>` in the 初期リクエスト (a design doc under `.claude/designs/`, typically copied from its 実装ブリッジ)
- Sections labeled "Phase 2.5 関連 Knowledge" / "Phase 5.4" / "Phase 5.5" / "親 Issue サマリー"

**Actions when detected**:

1. Notify the user: "Linear/Indie からの upfront 引き継ぎを検出しました。Discovery と Codebase Exploration（Phase 2 探索）はスキップしますが、Phase 1.6 (Vault Recall) → Phase 1.7 (Triage) は通過し、引き継ぎ context を起点に Phase 3 へ進みます。"（引き継ぎ context が揃っているケースこそ横断知見が効くため、detected 経路でも Phase 1.6 は skip しない）
2. Read the Issue file to extract: title, summary, parent issue summary, related knowledge, existing `feature_dev_plan:`.
3. **If `feature_dev_plan:` already exists**: Treat it as a baseline. Propose deltas rather than redesigning from scratch. Confirm with user whether to reuse or revise.
   **If `design=<path>` was passed**: Read the design doc. Its adopted approach, 決定事項 and 実装ブリッジ are the baseline in the same way (Phase 4 runs one `delta-proposal` architect against it). If its `status` is not `approved` (draft / superseded), say so and ask whether to proceed. Phase 3 then asks **only the premise checks** (grill-protocol.md「採用する決定の前提を問う」) — do not reopen what the design doc decided, but do not treat it as an unconditional contract either: a broken premise or a conflict with `REQUIRED_DOCS` / ADRs is still asked (GitHub issue #233). Set `DESIGN_DOC_PATH=<path>` so Phase 4.5 skips exporting a new doc and Phase 7 points the as-built update (`phase: target → current`) at this one.
4. Signal Phase 1.7 that **Issue context is complete** (Phase 1.7 will likely assign 0 explorers, effectively skipping Phase 2). If the Issue context is sparse or contradicts the user's request, signal `partial` so Phase 1.7 can still launch 1-2 explorers for validation.
5. Pass the Issue context verbatim into Phase 4 architect prompts (the architect's "Issue Context Injection" section will consume it).

**Actions when NOT detected**: Proceed normally to Phase 1.6.

**次は Phase 1.6**（SKILL.md に戻り、その見出しの入口の条件を見る）
