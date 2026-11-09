## Phase 1.7: Triage（動的エージェント構成決定）

**Goal**: Decide how many explorer / architect agents to launch in subsequent phases, with concrete focus assignments. Phase 6 reviewers are left to code-review's triage (`triage-guide.md` Section 6).

**Why this phase exists**: Static "always 2-3 explorers + 3 reviewers" configuration wastes tokens on simple tasks and under-covers complex ones. Phase 1.7 inspects feature characteristics × `${CLAUDE_EFFORT}` and produces an agent configuration table that subsequent phases read.

**Run in main context (do NOT use the Agent tool here).**

### Step 1: Read the triage guide

Read `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` and apply its 2-stage logic.

### Step 2: Stage 1 — Type judgment

Identify:
- **Feature type**: bugfix / extension / new-feature / refactor / migration / cross-cutting (multiple allowed)
- **Explorer necessity**: skip if Issue context provides a complete `feature_dev_plan:` AND the feature is isolated; otherwise required
- **Architect focuses**: always include `minimal-changes`; add `clean-architecture` / `pragmatic-balance` / `migration-strategy` per the guide

Consider these signals:
- `package.json` major dependencies (React/Next.js → vercel-best-practices for architects)
- CLAUDE.md presence
- Issue context content (if Phase 1.5 detected one)

### Step 3: Stage 2 — Count and focus

Apply the count tables in `triage-guide.md` Section 4, capped by the effort upper bounds in Section 5.

**Minimum guarantee** (across all effort levels):
- architect ≥ 1
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
```

Subsequent phases consume this table directly.

**次は Phase 1.8**（SKILL.md に戻り、その見出しの入口の条件を見る）
