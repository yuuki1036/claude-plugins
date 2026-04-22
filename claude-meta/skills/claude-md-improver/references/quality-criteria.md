# CLAUDE.md Quality Criteria

## Scoring Rubric

合計 100 点。各項目は独立評価。**Skill Coordination** は Vercel eval で「Skill 56% 未呼出」「自動生成 AGENTS.md は -3%、人間作成は +4%」の知見を反映し、人間レビュー誘導型の監査を強化するために追加。

### 1. Commands/Workflows (15 points)

**15 points**: All essential commands documented with context
- Build, test, lint, deploy commands present
- Development workflow clear
- Common operations documented

**11 points**: Most commands present, some missing context

**7 points**: Basic commands only, no workflow

**3 points**: Few commands, many missing

**0 points**: No commands documented

### 2. Architecture Clarity (15 points)

**15 points**: Clear codebase map
- Key directories explained
- Module relationships documented
- Entry points identified
- Data flow described where relevant

**11 points**: Good structure overview, minor gaps

**7 points**: Basic directory listing only

**3 points**: Vague or incomplete

**0 points**: No architecture info

### 3. Non-Obvious Patterns (15 points)

**15 points**: Gotchas and quirks captured
- Known issues documented
- Workarounds explained
- Edge cases noted
- "Why we do it this way" for unusual patterns

**10 points**: Some patterns documented

**5 points**: Minimal pattern documentation

**0 points**: No patterns or gotchas

### 4. Conciseness (15 points)

**15 points**: Dense, valuable content
- No filler or obvious info
- Each line adds value
- No redundancy with code comments

**10 points**: Mostly concise, some padding

**5 points**: Verbose in places

**0 points**: Mostly filler or restates obvious code

### 5. Currency (15 points)

**15 points**: Reflects current codebase
- Commands work as documented
- File references accurate
- Tech stack current

**10 points**: Mostly current, minor staleness

**5 points**: Several outdated references

**0 points**: Severely outdated

### 6. Actionability (10 points)

**10 points**: Instructions are executable
- Commands can be copy-pasted
- Steps are concrete
- Paths are real

**7 points**: Mostly actionable

**3 points**: Some vague instructions

**0 points**: Vague or theoretical

### 7. Skill Coordination (15 points)

CLAUDE.md 単体で Claude の skill 呼び出しを後押しできているか。3 つの観点で評価。

**判定観点:**

| 観点 | 配点 | チェック項目 |
|------|------|-----|
| 明示的な skill 呼び出しガイド | 5 pt | 「このタスクでは `{plugin}:{skill}` を使う」形式の指示が、頻出タスクに対して用意されているか |
| 重要 skill の CLAUDE.md 参照 | 5 pt | インストール済みの重要 skill（プロジェクトに密接なもの）が CLAUDE.md から名前で参照されているか |
| 人間レビュー誘導の診断型記述 | 5 pt | 自動生成テンプレートのコピペではなく、プロジェクト固有の判断・背景が記されているか（診断→提案→人間判断の導線） |

**15 points**: 全 3 観点でプロジェクト固有の明示ガイドあり。重要 skill はすべて命名参照され、人間レビューを経た痕跡（why, how to apply）が見える

**10 points**: 2 観点満たす。1 観点に抜けあり

**5 points**: 1 観点のみ満たす。skill 名参照が部分的 or ガイドが一般論止まり

**0 points**: skill が一切参照されない、または自動生成風のボイラープレートのみ

**Why separate category:**

- Vercel eval: Skill 56% 未呼出。description マッチのみでは invocation が揺らぐ
- 人間作成 AGENTS.md は +4%、自動生成は -3%。**「人間がレビューして書いた」ことが効く**
- このカテゴリは「読んでも呼べない」状態を検知するためのレーダー

## Assessment Process

1. Read the CLAUDE.md file completely
2. Cross-reference with actual codebase:
   - Run documented commands (mentally or actually)
   - Check if referenced files exist
   - Verify architecture descriptions
3. Score each criterion
4. Calculate total and assign grade
5. List specific issues found
6. Propose concrete improvements

## Red Flags

- Commands that would fail (wrong paths, missing deps)
- References to deleted files/folders
- Outdated tech versions
- Copy-paste from templates without customization
- Generic advice not specific to the project
- "TODO" items never completed
- Duplicate info across multiple CLAUDE.md files
- **インストール済みの主要 skill が 1 つも命名参照されていない**（例: `linear-workflow:session-start` を常用しているのに CLAUDE.md に出てこない）
- **自動生成風のボイラープレート**（一般論の羅列・プロジェクト固有の判断が見えない）
- **タスク→skill 対応表が欠落**しており、Claude が類推でしか呼び出せない

## Skill Coordination 判定のヒント

- **読む順序:** CLAUDE.md → `find ~/.claude/plugins -name "SKILL.md" -path "*/skills/*"` → 主要 skill の frontmatter description とトリガーを照合
- **頻出タスク抽出:** プロジェクトの README / CHANGELOG / 最近のコミットから「よく行うタスク」を拾い、対応 skill があるか確認
- **判定は診断のみ:** このスキルは「追加すべき」と断定せず、ユーザーの採否判断を待つ（自動生成は逆効果）
