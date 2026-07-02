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
  - AskUserQuestion
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

### Phase 1.5: 階層化判定（AskUserQuestion）

Phase 2 の評価に入る前に、プロジェクトの規模に応じた構成方針をユーザーに確認する。階層化が必要ない小規模プロジェクトに過剰設計を suggest しないための分岐。

詳細は [references/hierarchical-agents-md.md](references/hierarchical-agents-md.md) を参照。

**AskUserQuestion 仕様:**

```
question: "root 以外に backend/frontend 等の階層別 AGENTS.md / CLAUDE.md を持つ規模ですか？"
header: "階層化判定"
options:
  1. label: "単一構成（root のみ）" / description: "300 行以下、機能領域 2 以下、単一スタック。階層化なしで進める"
  2. label: "機能領域別に階層化" / description: "backend / frontend / infrastructure 等の領域別に AGENTS.md を分割"
  3. label: "monorepo packages 別に階層化" / description: "packages/{name}/AGENTS.md で package 単位に分割"
  4. label: "判定不能・相談" / description: "現状を見せて improver の suggest を聞きたい"
```

選択結果は Phase 3 の suggest 内容（階層化 template 利用の可否）に反映する。

### Phase 2: Quality Assessment

For each CLAUDE.md file, evaluate against quality criteria. See [references/quality-criteria.md](references/quality-criteria.md) for detailed rubrics.

**補助観点として Diátaxis レンズを適用**（スコア外の構造診断）。詳細は [references/diataxis-framework.md](references/diataxis-framework.md) を参照。100 行超の CLAUDE.md に対してのみ適用し、セクション単位で「Tutorial / How-to / Reference / Explanation」のどのタイプかを分類して混在・Why 欠落・順序喪失を検出する。スコアには加算せず、Phase 3 の Quality Report に "Structural Observations" として併記する。

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
| Guardrail anti-bypass | High | Are lint/hook/static-check guardrails protected by an explicit "no weakening" meta-rule? See [references/meta-rules.md](references/meta-rules.md) |
| Three-tier defense | High | Are critical rules duplicated across CLAUDE.md / skill / hook layers? See [references/three-tier-defense.md](references/three-tier-defense.md) |
| Priority resolution | Medium | Is there an explicit document priority order with non-negotiable lines? See [references/priority-template.md](references/priority-template.md) |
| Static check preference | Medium | Are "○○ 禁止" rules candidates for linter / ast-grep rather than prose? See [references/meta-rules.md](references/meta-rules.md) section 2 |

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

**運用パターン充足度（6 セクション）:**

以下 6 パターンの有無を診断し、欠けているものを suggest する（自動挿入は禁止、Phase 4 の承認フローに乗せる）。

| パターン | 状態 | reference |
|----------|------|-----------|
| 1. ガードレール骨抜き禁止メタルール | ✓ / ✗ | [meta-rules.md](references/meta-rules.md) §1 |
| 2. 三段防御（CLAUDE.md → skill → hook） | ✓ / ✗ / 部分 | [three-tier-defense.md](references/three-tier-defense.md) |
| 3. AGENTS.md 階層化（規模に応じて） | ✓ / ✗ / 単一構成で OK | [hierarchical-agents-md.md](references/hierarchical-agents-md.md) |
| 4. CLAUDE.md = `@AGENTS.md` 1 行参照運用 | ✓ / ✗ | OpenAI Codex / Devin 互換性確保 |
| 5. ドキュメント優先度規約 | ✓ / ✗ | [priority-template.md](references/priority-template.md) |
| 6. 静的検査優先原則（"○○禁止" の linter 化候補抽出） | ✓ / ✗ | [meta-rules.md](references/meta-rules.md) §2 |

### 三段防御チェックリスト（重要規約ごと）

CLAUDE.md の重要規約を抽出し、CLAUDE.md / skill / hook の 3 層充足度を表で出力する。詳細は [references/three-tier-defense.md](references/three-tier-defense.md) を参照。

```
| 規約 | CLAUDE.md | Skill | Hook |
|------|-----------|-------|------|
| --no-verify 禁止 | ✓ | ? | ? |
| .env 編集禁止 | ✓ | ? | ? |
| main 直接コミット禁止 | ✓ | ? | ? |
```

`?` または `✗` の層について「該当層への実装を提案します」と suggest する。

### 静的検査化候補の抽出

CLAUDE.md から「禁止」「不可」「使わない」「避ける」を含む行を Grep し、以下の自己問いを実行する:

```bash
grep -nE '(禁止|不可|使わない|避ける|してはいけない|してはならない)' CLAUDE.md
```

各候補に対して improver は問う:

> 「これは linter / ast-grep / 型検査ルールに落とせますか？」

落とせる場合は静的検査化を suggest し、CLAUDE.md には Why（背景・例外運用）のみ残すことを提案する。

**Structural Observations (Diátaxis lens, 100 行超のみ):**
- セクション別タイプ分類（Reference / How-to / Explanation / Tutorial）
- 混在しているセクション・Why 欠落・順序喪失の指摘
- 分割提案（断定せず「読みやすくなる可能性」として提示）
- 詳細フォーマットは [references/diataxis-framework.md](references/diataxis-framework.md) の「提案フォーマット」を参照

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

追加内容の判断基準（What TO Add / What NOT to Add のカテゴリ別サンプルと Validation Checklist）は [references/update-guidelines.md](references/update-guidelines.md) を参照する。

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
