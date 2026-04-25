---
name: instinct-learning
description: >
  ユーザーの訂正・好み・繰り返しパターンを instinct として記録・管理・昇格させるシステム。
  トリガー: セッション開始時の instincts.md 読み込み、ユーザーの訂正・好み・繰り返しパターンの検知時
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# Instinct Learning System

セッション中の観察からパターンを学習し、auto memory で管理するシステム。

## 設計原則: learn と instinct-promote のコンテキスト分離

パターン抽出（Generator）と MEMORY.md への昇格判定（Evaluator）は **別コマンド・別コンテキスト** で実行する:

- `/learn` (Generator): セッションを振り返って instincts.md にパターンを追加する
- `/instinct-promote` (Evaluator): instincts.md を独立したコンテキストで読み直し、重複・具体性・吸収判定をかけて MEMORY.md に昇格する

同一コンテキストで抽出と昇格を連続で行うと、抽出時の「残したい」バイアスが昇格判定を歪める。明示的にコマンドを分けることで、Evaluator は instincts.md に書かれた結果だけを根拠に判断できる。

## いつ使うか

- セッション開始時（instincts.md の読み込みと認識）
- セッション中にユーザーの訂正・好み・繰り返しパターンを検知した時
- セッション終了時（Stop hook からのリマインダーを受けた時）

## コンセプト

「instinct」= 1トリガー・1アクションの小さな行動パターン。

- 外部スクリプト不要、API コスト追加なし
- Claude 自身がセッション中に気づいて記録する
- confidence レベルで段階管理し、確定したら MEMORY.md に昇格

## ストレージ

```
~/.claude/projects/<project-path>/memory/
├── MEMORY.md       # 確定パターン（自動ロード、200行制限）
└── instincts.md    # 候補パターン（必要時に読む、サイズ制限なし）
```

## セッション開始時の動作

1. MEMORY.md は自動ロードされる
2. `memory/instincts.md` が存在するか確認し、あれば読む
3. 候補パターンを認識した上で作業開始
4. セッション中に該当パターンを見かけたら confidence を更新

## 観測トリガー

以下を検知したら instincts.md への記録を検討する:

| パターン | 例 |
|---|---|
| ユーザーの訂正 | 「そうじゃなくて X を使って」 |
| 繰り返しの指示 | 毎回同じことを言われる |
| エラー解決の再現 | 同じエラーを2回以上解決した |
| 好みの表明 | 「こっちのスタイルがいい」 |
| 明示的な記憶依頼 | 「これ覚えて」→ 即 high で MEMORY.md へ |

## 検知キーフレーズ（具体化）

Claude は曖昧な指示では控えめに動くため、以下を **mandatory マッチ対象** として走査する。キーフレーズを含む発話が見つかった時点で「観測候補」としてマークし、直後のユーザー発話内容と併せて instincts.md への追加を検討する。

### 訂正パターン（日本語）
- 否定: 「いや」「違う」「ちがう」「そうじゃなくて」「そうではなく」「違った」
- 中止: 「やめて」「止めて」「待って」「ちょっと待って」
- 訂正: 「むしろ X」「実は X」「正しくは X」「X にして」

### 訂正パターン（英語）
- 否定: "no, actually", "that's wrong", "don't do X"
- 中止: "stop that", "wait", "hold on"
- 訂正: "use X instead", "it should be X"

### 好み表明（日本語・英語共通）
- 「こっちのスタイルがいい」「〜の方が読みやすい」「もっと Y な感じで」「〇〇は使わないで」
- "I prefer X", "we don't use Y here", "keep it as X"

### 繰り返し検知
- **同セッション内**: 同一キーワード群を含む指示が 2 回以上出現 → 観測 1 回としてカウント
- **複数セッション**: 前回の `observed` 日付と比較し、異なるセッションで同一パターン → observed に日付追記

### エラー解決の再現
- 同じエラーメッセージ／トレースバックの断片（正規表現マッチ可能な部分）が再出現
- または「前にも同じエラー出たよね」とユーザーが明示的に言及

### 除外（境界ケース）
- 「no, that's fine」のような確認応答の no
- typo 修正 / 構文エラー修正（1 行訂正）
- 一般論の意見（「X のほうがいいかもね」程度の軽いトーン）

## 実行フロー

1. **セッション開始時**:
   - MEMORY.md と instincts.md を Read し、既存 instinct の trigger / observed を認識
2. **セッション中（継続的走査）**:
   - 各ユーザー発話で上記キーフレーズをマッチング
   - ヒット時:
     - 新規パターン → confidence `low` で即座に instincts.md に追加
     - 既存パターン → `observed:` にカンマ区切りで今日の日付を追記、Confidence ルールに従い更新
   - 記録時は簡潔にユーザーに報告（「この傾向を instinct として記録しました」）
3. **セッション終了時**（Stop hook からのリマインダー）:
   - 本セッションで記録した観測を振り返る
   - ユーザーが「覚えて」と明示した項目は即 `high` 昇格候補として promote を案内

## 記録しないもの

- typo や構文エラーの修正
- 一回限りの障害（API ダウン等）
- CLAUDE.md に既に書いてあること
- MEMORY.md に既に書いてあること
- 抽象的すぎて actionable じゃないもの

## Instinct のフォーマット

```markdown
### <id>
- trigger: いつ発火するか
- action: 何をするか
- confidence: low | medium | high
- domain: code-style | testing | workflow | git | tooling | preference
- observed: YYYY-MM-DD, YYYY-MM-DD, ...
- note: 観測時の補足（任意）
```

## Confidence ルール

| レベル | 条件 | 置き場所 | 扱い |
|---|---|---|---|
| low | 1回観測 | instincts.md | 記録のみ。適用しない |
| medium | 2-3回観測 | instincts.md | 関連場面でユーザーに確認を取る |
| high | 4回以上 or ユーザーが「覚えて」 | MEMORY.md に昇格 | 自動適用 |
| 削除 | ユーザーが否定 or 矛盾発見 | instincts.md から削除 | - |

## Confidence 更新の判断

- 同じパターンを再度観測 → observed に日付追加、必要なら confidence を上げる
- ユーザーが instinct と矛盾する行動を取った → confidence を下げるか削除
- 長期間（1ヶ月以上）観測されない → 次回確認時に confidence を下げることを検討

## 昇格時の品質ゲート

instinct を MEMORY.md に昇格する前に確認:

1. **重複チェック**: CLAUDE.md・MEMORY.md に同等の内容がないか
2. **吸収判定**: 既存の MEMORY.md エントリに追記で済まないか
3. **具体性**: trigger と action が十分具体的か
4. **判定**:
   - Save → MEMORY.md に追加、instincts.md から削除
   - Absorb → 既存エントリを更新、instincts.md から削除
   - Drop → instincts.md から削除（理由をユーザーに説明）

## MEMORY.md のフォーマット

```markdown
## 確定パターン

- <簡潔な説明>（domain: xxx）
- <簡潔な説明>（domain: xxx）
...

## 参照

- 候補パターン → memory/instincts.md
```

MEMORY.md は200行制限があるため、1パターン1行で簡潔に書く。
詳細が必要な場合は別ファイル（memory/details/<id>.md）にリンクする。

## プロジェクト横断の昇格

同じパターンが2つ以上のプロジェクトで確認された場合:
- グローバルの `~/.claude/memory/MEMORY.md` への昇格を提案
- ユーザー承認で昇格
