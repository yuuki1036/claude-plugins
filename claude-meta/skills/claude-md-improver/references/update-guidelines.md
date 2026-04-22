# CLAUDE.md Update Guidelines

## Core Principle

Only add information that will genuinely help future Claude sessions. The context window is precious - every line must earn its place.

## What TO Add

### 1. Commands/Workflows Discovered

```markdown
`npm run build:prod` - Full production build with optimization
`npm run build:dev` - Fast dev build (no minification)
```

### 2. Gotchas and Non-Obvious Patterns

```markdown
- Tests must run sequentially (`--runInBand`) due to shared DB state
- `yarn.lock` is authoritative; delete `node_modules` if deps mismatch
```

### 3. Package Relationships

```markdown
The `auth` module depends on `crypto` being initialized first.
Import order matters in `src/bootstrap.ts`.
```

### 4. Testing Approaches That Worked

```markdown
For API endpoints: Use `supertest` with the test helper in `tests/setup.ts`
Mocking: Factory functions in `tests/factories/` (not inline mocks)
```

### 5. Configuration Quirks

```markdown
- `NEXT_PUBLIC_*` vars must be set at build time, not runtime
- Redis connection requires `?family=0` suffix for IPv6
```

### 6. Skill Invocation Guidance

「このタスクでは X skill を使う」を明示する。Vercel eval で Skill 56% 未呼出だった問題への直接対処。

```markdown
## Skill Coordination

- **Issue 作業開始時**: `linear-workflow:session-start` を使う
- **コミット前レビュー**: `code-review:self-review` を使う
- **PR 作成**: `dev-workflow:pr-creator` を使う
```

**判断基準:**
- 頻出タスクと skill トリガーが重なる場合のみ追加
- 1 回限りの特殊タスクは書かない（ノイズになる）
- skill 名は `{plugin}:{skill}` 形式で揺らぎを減らす

**Critical — 自動挿入禁止:** claude-md-improver は候補提示のみ行う。採否はユーザー判断（自動生成 AGENTS.md は -3% / 人間作成は +4% の eval 結果より）。

## What NOT to Add

- **Obvious code info**: class names that are self-explanatory
- **Generic best practices**: "always write tests" etc.
- **One-off fixes**: specific bug fixes unlikely to recur
- **Verbose explanations**: keep it to one-liners when possible

## Diff Format for Updates

```markdown
### Update: ./CLAUDE.md

**Why:** [one-line reason]

```diff
+ [the addition]
```
```

## Validation Checklist

- [ ] Each addition is project-specific
- [ ] No generic advice or obvious info
- [ ] Commands are tested and work
- [ ] File paths are accurate
- [ ] Would a new Claude session find this helpful?
- [ ] Is this the most concise way to express the info?
- [ ] Skill invocation guidance は候補提示のみか（断定していないか）
- [ ] `{plugin}:{skill}` 形式で skill 名を正確に記載しているか
