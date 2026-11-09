## Phase 4: Architecture Design

**Goal**: Design implementation approaches with different trade-offs

**Actions**:
1. Launch the N code-architect agents specified by the Phase 1.7 configuration table in parallel (single message; wait for every architect's result, as in Phase 2). Each agent receives its assigned `focus`:
   - `minimal-changes`: smallest change, maximum reuse of existing code
   - `clean-architecture`: maintainability, elegant abstractions, long-term evolvability. Pass `Module design vocabulary: ${CLAUDE_PLUGIN_ROOT}/references/module-design.md` in its prompt (the agent Reads it; do not paste the body)
   - `pragmatic-balance`: speed + quality tradeoff explicitly weighed
   - `migration-strategy`: phased migration steps with rollback points (migration tasks only)
   - `delta-proposal`: when Issue context provides existing `feature_dev_plan:` or `design=` passed a design doc — propose deltas only, do not redesign

   **BDD spec injection**: Phase 1.3 で `BDD_SPEC_PATH` が設定された場合、各 architect の prompt に以下を追加する:
   - `BDD spec path: <BDD_SPEC_PATH>` — architect は冒頭でこのファイルを Read し、Feature / Scenario / Examples / 同値分割表を **authoritative requirements** として扱う
   - 設計は spec.md の AC ↔ Scenario マッピングを保つこと（架空の Scenario を増やさない、削らない）
   - 詳細は `agents/code-architect.md` の "BDD Spec Injection" セクション

   **Required docs injection**: Phase 1.8 で `REQUIRED_DOCS` が非空の場合、各 architect の prompt に `Required Docs:` ブロックとして**全件**（パス / 節 / 当てはまった種別）を列挙する。architect 自身に Read させる。一部だけ選んで渡さない。詳細は `agents/code-architect.md` の "Required Docs Injection" セクション

   **Vault knowledge injection**: Phase 1.6 で `VAULT_KNOWLEDGE` が非空の場合、各 architect の prompt に以下を追加する:
   - `Vault Knowledge:` ブロックとして関連知見（`path` / `title` / `excerpt`）を列挙する
   - これは **別プロジェクト横断の参考知見 (advisory)** であり、BDD spec のような authoritative requirement ではない。現コードベースのパターンと矛盾する場合は **現コードベースを優先** する
   - 関連する過去の落とし穴があれば設計の Critical Details に反映させ、採用した知見は出典 (`title`) を明記させる
   - 詳細は `agents/code-architect.md` の "Vault Knowledge Injection" セクション

2. Review all approaches and form your opinion on which fits best for this specific task
3. Present to user: brief summary of each approach, trade-offs comparison (include **depth / locality / seam placement** per approach — the axes in `${CLAUDE_PLUGIN_ROOT}/references/module-design.md`), **your recommendation with reasoning**, concrete implementation differences
4. **Ask user which approach they prefer**

**Partial failure tolerance**: If individual architects fail and at least 1 succeeded, continue with the successful results. If all architects failed, fall back to a single architect invocation with `minimal-changes` focus before surfacing the issue.

**次は Phase 4.5**（SKILL.md に戻り、その見出しの入口の条件を見る）
