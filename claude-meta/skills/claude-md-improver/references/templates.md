# CLAUDE.md Templates

## Key Principles

- **Concise**: Dense, human-readable content; one line per concept when possible
- **Actionable**: Commands should be copy-paste ready
- **Project-specific**: Document patterns unique to this project, not generic advice
- **Current**: All info should reflect actual codebase state

---

## Recommended Sections

Use only the sections relevant to the project. Not all sections are needed.

### Commands

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

```markdown
## Gotchas

- <non-obvious thing that causes issues>
- <ordering dependency or prerequisite>
- <common mistake to avoid>
```

### Skill Coordination

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
