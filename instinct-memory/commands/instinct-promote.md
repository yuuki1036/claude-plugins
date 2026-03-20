---
description: high confidence の instinct を MEMORY.md に昇格する
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "AskUserQuestion"]
---

# Instinct Promote — MEMORY.md への昇格

instincts.md 内の high confidence パターンを MEMORY.md に昇格する。

## 手順

### Step 1: 昇格候補の特定

instincts.md を読み、以下の条件を満たす instinct を候補にする:
- confidence が high
- observed の日付が2回以上ある（ユーザー明示の「覚えて」は1回でもOK）

### Step 2: 品質ゲート

各候補について確認:

1. **重複チェック**: MEMORY.md に同等の内容がないか grep で確認
2. **CLAUDE.md チェック**: プロジェクト・グローバルの CLAUDE.md と重複しないか確認
3. **吸収判定**: 既存の MEMORY.md エントリに追記で済まないか
4. **具体性**: trigger と action が十分具体的で actionable か

判定:
- **Save**: MEMORY.md に新規追加
- **Absorb**: 既存エントリを更新
- **Drop**: 昇格不要（理由を説明）

### Step 3: ユーザー確認

昇格候補をユーザーに提示し、AskUserQuestion で承認を得る。
MEMORY.md に書く1行の表現も確認する。

### Step 4: 昇格実行

- MEMORY.md の「確定パターン」セクションに追加（1パターン1行、簡潔に）
- instincts.md から該当エントリを削除

### Step 5: プロジェクト横断チェック

同じパターンが他プロジェクトの instincts.md/MEMORY.md にも存在するか確認:
- `~/.claude/projects/*/memory/instincts.md` を glob で検索
- 2つ以上のプロジェクトで確認されたら、グローバル `~/.claude/memory/MEMORY.md` への昇格を提案

### Step 6: MEMORY.md の行数チェック

昇格後、MEMORY.md が200行に近づいていないか確認。
180行を超えていたら警告し、古いパターンの整理を提案する。
