---
name: component-addition-advisor
description: >
  プラグインに新 skill / agent / hook / command を追加する前の「退路確保」判断。
  既存拡張で解けないかを最初に検証し、ブロッカーが出た場合のみ新規追加する。
  _requirements にフォールバック手順を書く規約をガイドする。
  トリガー: 「新しいskill追加」「新しいagent追加」「新しいhook追加」「skill追加判断」
  「退路確保」「component addition」「追加前チェック」「最小構成」「skill 分割すべき？」
effort: medium
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Component Addition Advisor

プラグインに新規 skill / agent / hook / command を追加するかどうかの判断を、「退路確保」原則に沿ってガイドする。

## 原則

**最小構成から始め、ブロッカーが実際に出たときのみ新規追加する。**

事例:
- Conform 単独 → 必要時のみ RHF にフォールバック
- Oxfmt → Prettier フォールバック
- 単一 skill で回る → 分割・新設はブロッカー発生後

新 skill / agent / hook を増やすと context / 認知負荷 / 保守コストが増える。既存で解けるなら既存を拡張する方が ROI が高い。

## 判断フロー

```
新コンポーネントを追加したい
  │
  ▼
① 既存の command / skill / agent で解けるか？
  ├─ YES → 既存を拡張する（新規追加しない）
  └─ NO ↓
  ▼
② 決定的検証（文字列・ファイル存在・JSON schema）で済むか？
  ├─ YES → Hook で強制する（skill / agent より確実）
  └─ NO ↓
  ▼
③ 呼び出しタイミングが明確で自然言語判定が必要か？
  ├─ YES → Skill（トリガーフレーズ明示）
  └─ NO ↓
  ▼
④ 自律的な多段推論が必要か？
  ├─ YES → Agent（system prompt で専門化）
  └─ NO ↓
  ▼
⑤ 恒常的な参照情報か？
  └─ CLAUDE.md / skill の references/ に追記
```

> 既存のルール配置フロー（CLAUDE.md の「ルール配置の意思決定」）と連動する。そちらは「ルール」の配置、こちらは「コンポーネント」の追加判断。

## 追加前チェックリスト

新 skill / agent / hook を追加する前に、以下を順に確認する。

### Step 1: 既存拡張の検討

```bash
# 対象プラグイン配下を検索
find {plugin-dir}/skills -name "SKILL.md"
find {plugin-dir}/commands -name "*.md"
find {plugin-dir}/agents -name "*.md"
```

**質問:**
- 既存 skill / command の allowed-tools を拡張すれば対応可能か？
- 既存 skill の workflow に phase を 1 つ増やすだけで足りるか？
- トリガーフレーズを追加するだけで既存 skill が拾えるようになるか？

YES なら新規追加しない。既存を拡張する。

### Step 2: ブロッカーの明示

NO の場合、「なぜ既存で解けないか」を 1 行で書ける必要がある。

**ブロッカーの例:**
- 既存 skill のトリガーと意味的に重ならない（混乱を招く）
- allowed-tools が衝突する（片方で禁止、片方で必須）
- 処理時間 / コンテキスト消費が大きく、常時ロードしたくない
- 別のモデル / effort で動かしたい

ブロッカーが書けない場合は追加を見送る。

### Step 3: フォールバック設計

新規追加する場合、`_requirements` にフォールバック手順を書く。

```json
{
  "_requirements": {
    "new_skill_name": {
      "preferred": "new_skill_name",
      "fallback": "既存 skill A の workflow Phase 2 を流用",
      "why": "Phase 2 では十分だが、X のケースで新 skill が必要"
    }
  }
}
```

**フォールバック記述のメリット:**
- 新 skill がロードされない環境でも退路がある
- 後から「やっぱり既存で足りた」と分かった場合に削除しやすい
- レビュー時に「なぜ追加したか」の根拠が残る

### Step 4: サイズ / スコープ確認

| 規模目安 | 推奨 |
|----|-----|
| 100 行未満 | 既存 skill に追記 |
| 100-500 行 | 新 skill（SKILL.md 単独 or references 併用） |
| 500 行以上 | references に分割、SKILL.md は lean |
| 複数 skill 連携が必要 | agent 化検討 |
| 決定的チェック可能 | hook 化（skill より確実） |

## 対話ワークフロー

ユーザーが「新 skill を追加したい」と言ったら、以下を対話で確認する。

### Phase 1: 既存拡張可能性の診断

```bash
# 対象プラグイン / 近接プラグインの skill を列挙
find {plugin-dir}/skills -name "SKILL.md" -exec head -20 {} \;
```

診断結果を **提示のみ** 行う（自動判断しない）。

```
## 既存コンポーネント診断

### 近い目的の既存 skill
- `{plugin}:{skill}` — {description 要約} / 拡張余地: {あり|なし}

### 既存拡張で解ける可能性
- [ ] トリガーフレーズ追加で対応可能
- [ ] allowed-tools 追加で対応可能
- [ ] workflow phase 追加で対応可能
```

### Phase 2: AskUserQuestion で意思決定

既存拡張が候補としてある場合、AskUserQuestion で確認する。

```
question: 既存 {skill} の拡張で対応するか、新 skill を追加するか？
options:
  - 既存を拡張（推奨）: {skill} に phase を追加する
  - 新 skill を追加: ブロッカー理由を記録した上で新規作成
  - 判断保留: 一旦既存のまま様子見（1 回で済むなら追加しない）
```

### Phase 3: ブロッカー記録

「新 skill 追加」を選んだ場合、ブロッカー理由を 1 行で記録させる。

記録先:
- `plugin.json` の `_requirements.{skill}.why`
- CHANGELOG の該当バージョンエントリ

### Phase 4: フォールバック明示

新規追加時は `_requirements.{skill}.fallback` 欄を必ず埋める。空欄のまま追加しない（将来の剪定で判断材料になる）。

## Red Flags（追加を見送るサイン）

- 「あると便利そう」だけで具体的ブロッカーがない
- 既存 skill とトリガーフレーズが 70% 以上重複する
- 使うのは 1 回限りの特殊ケース
- 既存 skill の workflow phase 追加で 30 行以内に収まる
- まだ 1 度も困っていない（ブロッカー未発生）

## 判定表

| 状況 | 推奨アクション |
|------|--------------|
| 既存 skill のトリガーに追記で解ける | 既存拡張 |
| 既存 skill の workflow に phase 追加 | 既存拡張 |
| 決定的検証（lint / diff / grep）で十分 | Hook 追加 |
| 自然言語判定 + 明示的呼び出し | 新 Skill |
| 多段推論 + 自律実行 | 新 Agent |
| 参照情報の追加のみ | references/ に追記 |

## _requirements フォールバック規約

プラグインの `plugin.json` に以下フォーマットで追加する（既存 `_requirements` がある場合は拡張）。

```json
{
  "_requirements": {
    "{component-name}": {
      "type": "skill|agent|hook|command",
      "preferred": "{plugin}:{component-name}",
      "fallback": "既存 {other-component} で代替可能、{条件} の場合のみ新コンポーネント必須",
      "blocker": "なぜ既存で解けないかの 1 行説明",
      "added_at": "YYYY-MM-DD"
    }
  }
}
```

**利点:**
- コンポーネント乱立を抑制
- 後から削除・統合する判断材料になる
- `cc-catch-up` の剪定モードで使える

## 他スキルとの連携

- **`plugin-dev:plugin-validator`**: 構造検証はこちらに任せる
- **`plugin-dev:skill-reviewer`**: 作成後の品質レビューはこちらに任せる
- **`claude-meta:cc-catch-up`**: Phase P（剪定モード）の判定材料として本 skill の `_requirements` を参照する
- **`claude-meta:claude-md-improver`**: Skill Coordination セクションで新 skill を参照すべきかを判定する

本 skill は **追加前のゲート** を担当。作成後のレビューは plugin-dev の agent team に委譲する。

## 使用例

### Example 1: 新 skill を提案された

```
User: Git の blame 情報を整理する skill を追加したい

Advisor:
  Phase 1: 既存診断
  - dev-workflow:git-commit-helper が blame 周辺を扱う
  - 拡張余地: workflow Phase 追加で対応可能に見える

  Phase 2: AskUserQuestion
  Q: git-commit-helper の Phase 拡張 vs 新 skill、どちら？
  → ユーザー選択

  Phase 3-4: ブロッカー記録 / フォールバック明示
```

### Example 2: 明確なブロッカーあり

```
User: TDD の Red/Green phase を検知する hook を追加したい

Advisor:
  Phase 1: 既存診断
  - PreToolUse hook なし
  - 決定的検証（テストファイル存在 / パス状態）で判定可能

  → 判定フロー Step 2 で "決定的検証 YES" なので Hook が妥当
  → 新 skill ではなく hook として追加
  → _requirements に fallback 記述
```

## 要点

- 既存拡張が第一選択。新規追加はブロッカーが出たときのみ
- 「あると便利」では追加しない（context / 保守コストが増える）
- `_requirements` にフォールバックと blocker 理由を記録する
- 判断は診断 → 提示 → AskUserQuestion。自動追加はしない
