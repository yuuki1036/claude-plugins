# CLAUDE.md Templates

## Key Principles

- **Concise**: Dense, human-readable content; one line per concept when possible
- **Actionable**: Commands should be copy-paste ready
- **Project-specific**: Document patterns unique to this project, not generic advice
- **Current**: All info should reflect actual codebase state

---

## Recommended Sections

Use only the sections relevant to the project. Not all sections are needed.

各セクション見出しの後ろに **Diátaxis タイプ** を併記する。1 セクション 1 タイプを基本とし、混在は分割を検討する（詳細は [diataxis-framework.md](diataxis-framework.md)）。

### Commands

Diátaxis: **Reference**（コマンド事典。手順や前提条件が混入する場合は Setup へ切り出す）

```markdown
## Commands

| Command | Description |
|---------|-------------|
| `<install command>` | Install dependencies |
| `<dev command>` | Start development server |
| `<build command>` | Production build |
| `<test command>` | Run tests |
| `<lint command>` | Lint/format code |
```

### Architecture

Diátaxis: **Reference** + **Explanation**（構造図と「なぜこの構造か」を 1 段落以内で）

```markdown
## Architecture

```
<root>/
  <dir>/    # <purpose>
  <dir>/    # <purpose>
```
```

### Key Files

```markdown
## Key Files

- `<path>` - <purpose>
- `<path>` - <purpose>
```

### Code Style

```markdown
## Code Style

- <convention>
- <preference over alternative>
```

### Environment

```markdown
## Environment

Required:
- `<VAR_NAME>` - <purpose>

Setup:
- <setup step>
```

### Testing

```markdown
## Testing

- `<test command>` - <what it tests>
- <testing convention or pattern>
```

### Gotchas

Diátaxis: **Explanation** + **Reference**（事実 + Why を 1 行で。Why 欠落は再発防止に弱い）

```markdown
## Gotchas

- <non-obvious thing that causes issues> — Why: <reason / past incident>
- <ordering dependency or prerequisite> — Why: <reason>
- <common mistake to avoid> — Why: <consequence>
```

### Skill Coordination

Diátaxis: **How-to**（「X するときは Y を使う」形式。説明文を長く書かない）

頻出タスクと対応する skill を明示し、Claude の呼び出し率を高める。候補を列挙したあと、人間レビューで取捨選択すること（自動生成は逆効果）。

```markdown
## Skill Coordination

- **<頻出タスク>**: `{plugin-name}:{skill-name}` を使う
- **<別のタスク>**: `{plugin-name}:{skill-name}` を使う
```

**記入ルール:**
- 1 プロジェクトで常用する skill に絞る（全 skill を列挙しない）
- skill 名は `{plugin}:{skill}` 形式で統一
- 「使うかもしれない」程度なら書かない（ノイズ増加で逆効果）

---

## Template: Project Root (Minimal)

```markdown
# <Project Name>

<One-line description>

## Commands

| Command | Description |
|---------|-------------|
| `<command>` | <description> |

## Architecture

```
<structure>
```

## Gotchas

- <gotcha>
```

## Template: Project Root (Comprehensive)

```markdown
# <Project Name>

<One-line description>

## Commands

| Command | Description |
|---------|-------------|
| `<command>` | <description> |

## Architecture

```
<structure with descriptions>
```

## Key Files

- `<path>` - <purpose>

## Code Style

- <convention>

## Environment

- `<VAR>` - <purpose>

## Testing

- `<command>` - <scope>

## Gotchas

- <gotcha>
```

## Template: Package/Module

```markdown
# <Package Name>

<Purpose of this package>

## Usage

```
<import/usage example>
```

## Key Exports

- `<export>` - <purpose>

## Notes

- <important note>
```

## Template: Monorepo Root

```markdown
# <Monorepo Name>

<Description>

## Packages

| Package | Description | Path |
|---------|-------------|------|
| `<name>` | <purpose> | `<path>` |

## Commands

| Command | Description |
|---------|-------------|
| `<command>` | <description> |

## Cross-Package Patterns

- <shared pattern>
```
