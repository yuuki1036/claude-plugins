---
description: セッションからパターンを抽出し instinct として記録する
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# Learn — パターン抽出

現在のセッションを振り返り、instinct として記録すべきパターンを抽出する。

## 手順

### Step 1: セッション振り返り

このセッションで起きたことを振り返り、以下のパターンを探す:

- ユーザーの訂正（「そうじゃなくて〜」「〜を使って」）
- 繰り返し発生したエラーとその解決法
- ユーザーの好み・スタイルの表明
- 繰り返しのワークフロー

些末なもの（typo修正、一回限りの障害）は除外する。

### Step 2: 既存 instinct の読み込み

現在のプロジェクトの memory ディレクトリを特定し、既存の instincts.md を読む。
なければ新規作成する。

MEMORY.md も読み、重複がないか確認する。
CLAUDE.md（プロジェクト・グローバル両方）も確認する。

### Step 3: 品質ゲート

抽出した各パターンについて判定する:

| 判定 | 条件 | アクション |
|---|---|---|
| Save | ユニーク、具体的、再利用可能 | instincts.md に記録 |
| Absorb | 既存 instinct/MEMORY.md に追記で十分 | 既存エントリを更新 |
| Drop | 些末、重複、抽象的すぎ | 記録しない（理由を説明） |

### Step 4: ユーザー確認

抽出したパターンをユーザーに提示し、AskUserQuestion で確認を取る:
- 記録してよいか
- confidence は適切か（ユーザーが「確実」と言えば即 high）
- trigger/action の表現は正確か

### Step 5: 記録

承認されたパターンを instincts.md に追記する。

フォーマット:
```markdown
### <id>
- trigger: いつ発火するか
- action: 何をするか
- confidence: low | medium | high
- domain: code-style | testing | workflow | git | tooling | preference
- observed: YYYY-MM-DD
- note: 観測時の補足
```

### Step 6: 昇格チェック

instincts.md 内に high confidence の instinct があれば、MEMORY.md への昇格を提案する。
昇格時は instinct-learning スキルの品質ゲートに従う。
