---
name: claude-md-improver
description: >
  CLAUDE.md ファイルの監査・改善。全 CLAUDE.md をスキャンし、品質レポート出力後に改善を適用。
  トリガー: 「CLAUDE.md監査」「CLAUDE.md改善」「CLAUDE.mdチェック」「CLAUDE.mdの品質確認」
  「CLAUDE.mdメンテナンス」「audit CLAUDE.md」
effort: high
allowed-tools:
  - Read
  - Edit
  - Glob
  - Grep
  - Bash
---

# CLAUDE.md Improver

Audit, evaluate, and improve CLAUDE.md files across a codebase to ensure Claude Code has optimal project context.

**This skill can write to CLAUDE.md files.** After presenting a quality report and getting user approval, it updates CLAUDE.md files with targeted improvements.

## Workflow

### Phase 1: Discovery

Find all CLAUDE.md files in the repository:

```bash
find . -name "CLAUDE.md" -o -name ".claude.md" -o -name ".claude.local.md" 2>/dev/null | head -50
```

**File Types & Locations:**

| Type | Location | Purpose |
|------|----------|---------|
| Project root | `./CLAUDE.md` | Primary project context (checked into git, shared with team) |
| Local overrides | `./.claude.local.md` | Personal/local settings (gitignored, not shared) |
| Global defaults | `~/.claude/CLAUDE.md` | User-wide defaults across all projects |
| Package-specific | `./packages/*/CLAUDE.md` | Module-level context in monorepos |
| Subdirectory | Any nested location | Feature/domain-specific context |

**Note:** Claude auto-discovers CLAUDE.md files in parent directories, making monorepo setups work automatically.

### Phase 2: Quality Assessment

For each CLAUDE.md file, evaluate against quality criteria. See [references/quality-criteria.md](references/quality-criteria.md) for detailed rubrics.

**Quick Assessment Checklist:**

| Criterion | Weight | Check |
|-----------|--------|-------|
| Commands/workflows documented | High | Are build/test/deploy commands present? |
| Architecture clarity | High | Can Claude understand the codebase structure? |
| Non-obvious patterns | Medium | Are gotchas and quirks documented? |
| Conciseness | Medium | No verbose explanations or obvious info? |
| Currency | High | Does it reflect current codebase state? |
| Actionability | High | Are instructions executable, not vague? |
| Skill coordination | High | Are installed skills referenced with explicit invocation guidance? |

> **Why skill coordination matters:** Vercel の eval では Skill が 56% 未呼出。description マッチだけでは不十分で、CLAUDE.md に「このタスクでは X スキルを使う」と明示することで呼び出し率が改善する。自動生成 AGENTS.md は -3%、人間作成は +4% という結果もあり、人間レビュー誘導型の診断が重要。

**Quality Scores:**
- **A (90-100)**: Comprehensive, current, actionable
- **B (70-89)**: Good coverage, minor gaps
- **C (50-69)**: Basic info, missing key sections
- **D (30-49)**: Sparse or outdated
- **F (0-29)**: Missing or severely outdated

### Phase 3: Quality Report Output

**ALWAYS output the quality report BEFORE making any updates.**

Format:

```
## CLAUDE.md Quality Report

### Summary
- Files found: X
- Average score: X/100
- Files needing update: X

### File-by-File Assessment

#### 1. ./CLAUDE.md (Project Root)
**Score: XX/100 (Grade: X)**

| Criterion | Score | Notes |
|-----------|-------|-------|
| Commands/workflows | X/15 | ... |
| Architecture clarity | X/15 | ... |
| Non-obvious patterns | X/15 | ... |
| Conciseness | X/15 | ... |
| Currency | X/15 | ... |
| Actionability | X/10 | ... |
| Skill coordination | X/15 | ... |

**Issues:**
- [List specific problems]

**Recommended additions:**
- [List what should be added]

### Skill Invocation Guidance Audit

**Purpose:** CLAUDE.md 単体で skill 呼び出しを後押しできているか、診断のみ行う（自動挿入せず、人間レビュー前提）。

**Discovery Sources:**

```bash
# インストール済み skill の列挙
find .claude/plugins -name "SKILL.md" -path "*/skills/*" 2>/dev/null
find ~/.claude/plugins -name "SKILL.md" -path "*/skills/*" 2>/dev/null
# marketplace.json / plugin.json から plugin 名を参照し `{plugin}:{skill}` 形式で整理
```

**Diagnostic Output Format:**

```
#### Skill Invocation Guidance

**Installed skills (sample):**
- `{plugin-name}:{skill-name}` — {description から抜粋}

**CLAUDE.md references:**
- [x] `{skill-name}` が CLAUDE.md から参照されている（セクション: {場所}）
- [ ] `{skill-name}` は未参照 — トリガー: {主要トリガーフレーズ}

**Invocation guidance strength:**
- 明示的な「このタスクでは X スキルを使う」指示: {N 件}
- タスク→スキル対応表の有無: {あり|なし}
- 重要制約の skill 側への委譲指示: {あり|なし}

**Recommendations (human review required):**
- 頻出タスクと skill トリガーが重なる場合のみ、CLAUDE.md に明示呼び出しガイドを追加することを**提案**する
- 断定的に「追加すべき」とは書かず、ユーザーが採否を判断できる形で列挙する
```

**Critical:** Skill Invocation Guidance の追加提案は、必ず Phase 4 の承認フローに乗せる。自動挿入は禁止（人間レビューが精度を上げる）。

#### 2. ./packages/api/CLAUDE.md (Package-specific)
...
```

### Phase 4: Targeted Updates

After outputting the quality report, ask user for confirmation before updating.

**Update Guidelines (Critical):**

1. **Propose targeted additions only** - Focus on genuinely useful info:
   - Commands or workflows discovered during analysis
   - Gotchas or non-obvious patterns found in code
   - Package relationships that weren't clear
   - Testing approaches that work
   - Configuration quirks

2. **Keep it minimal** - Avoid:
   - Restating what's obvious from the code
   - Generic best practices already covered
   - One-off fixes unlikely to recur
   - Verbose explanations when a one-liner suffices

3. **Show diffs** - For each change, show:
   - Which CLAUDE.md file to update
   - The specific addition (as a diff or quoted block)
   - Brief explanation of why this helps future sessions

**Diff Format:**

```markdown
### Update: ./CLAUDE.md

**Why:** Build command was missing, causing confusion about how to run the project.

```diff
+ ## Quick Start
+
+ ```bash
+ npm install
+ npm run dev  # Start development server on port 3000
+ ```
```
```

### Phase 5: Apply Updates

After user approval, apply changes using the Edit tool. Preserve existing content structure.

## Templates

See [references/templates.md](references/templates.md) for CLAUDE.md templates by project type.

## Common Issues to Flag

1. **Stale commands**: Build commands that no longer work
2. **Missing dependencies**: Required tools not mentioned
3. **Outdated architecture**: File structure that's changed
4. **Missing environment setup**: Required env vars or config
5. **Broken test commands**: Test scripts that have changed
6. **Undocumented gotchas**: Non-obvious patterns not captured
7. **Missing skill invocation guidance**: インストール済み skill が CLAUDE.md から参照されていない、または「このタスクでは X を使う」という明示ガイドが欠落している
8. **Auto-generated boilerplate**: 人間レビューを経ていない自動生成風の記述（一般論の羅列、プロジェクト固有性の欠如）

## User Tips to Share

When presenting recommendations, remind users:

- **`#` key shortcut**: During a Claude session, press `#` to have Claude auto-incorporate learnings into CLAUDE.md
- **Keep it concise**: CLAUDE.md should be human-readable; dense is better than verbose
- **Actionable commands**: All documented commands should be copy-paste ready
- **Use `.claude.local.md`**: For personal preferences not shared with team (add to `.gitignore`)
- **Global defaults**: Put user-wide preferences in `~/.claude/CLAUDE.md`

## What Makes a Great CLAUDE.md

**Key principles:**
- Concise and human-readable
- Actionable commands that can be copy-pasted
- Project-specific patterns, not generic advice
- Non-obvious gotchas and warnings

**Recommended sections** (use only what's relevant):
- Commands (build, test, dev, lint)
- Architecture (directory structure)
- Key Files (entry points, config)
- Code Style (project conventions)
- Environment (required vars, setup)
- Testing (commands, patterns)
- Gotchas (quirks, common mistakes)
- Workflow (when to do what)
- Skill Coordination (インストール済み skill の呼び出しガイド — 頻出タスクとの対応表)
