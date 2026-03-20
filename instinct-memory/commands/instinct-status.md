---
description: 現在の instinct 一覧と confidence を表示する
allowed-tools:
  - Read
  - Glob
---

# Instinct Status — 一覧表示

現在のプロジェクトと、グローバルの instinct を一覧表示する。

## 手順

### Step 1: プロジェクトの instincts.md を読む

現在のプロジェクトの memory ディレクトリから instincts.md を探して読む。
なければ「候補パターンはまだありません」と報告。

### Step 2: プロジェクトの MEMORY.md を読む

MEMORY.md の確定パターンセクションを読む。

### Step 3: グローバルの確認

`~/.claude/memory/instincts.md` と `~/.claude/memory/MEMORY.md` も確認する。

### Step 4: レポート表示

以下の形式で表示する:

```
## プロジェクト: <プロジェクト名>

### 確定パターン（MEMORY.md）
- <パターン> (domain)
...

### 候補パターン（instincts.md）
| ID | trigger | confidence | domain | 観測回数 |
|----|---------|------------|--------|----------|
| xx | ...     | medium     | ...    | 3        |
...

## グローバル
（同様の形式）

## サマリー
- 確定: N件
- 候補: N件（high: N, medium: N, low: N）
- 昇格可能: N件
```

### Step 5: 昇格候補の提示

high confidence の instinct があれば、`/instinct-promote` の実行を提案する。
