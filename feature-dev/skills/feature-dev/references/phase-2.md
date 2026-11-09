## Phase 2: Codebase Exploration

**Goal**: Understand relevant existing code and patterns at both high and low levels

**Actions**:
1. Launch the N code-explorer agents specified by the Phase 1.7 configuration table in parallel (single message, multiple Agent tool calls). Agents always start in the background (CC 2.1.302+) and each result arrives later as a completion notification — **do not move on until every explorer's result has arrived**. Each agent receives:
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

**次は Phase 3**（SKILL.md に戻り、その見出しの入口の条件を見る）
