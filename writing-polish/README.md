# writing-polish

文章を語句レベルで推敲・添削する Claude Code プラグイン。RFC / Issue / PR 本文 / コミットメッセージ / レビューコメントを対象に、冗長・曖昧・トーンのぶれを直す。日英両対応。

## できること

- 冗長・二重表現の削り
- 曖昧語（「ちょっと」「いい感じ」「ざっくり」）の具体化
- 文体（敬体/常体）のぶれ統一、トーンの整え
- AI っぽさ（過剰な箇条書き・過剰強調・hype 表現・絵文字）の除去
- 用語の一貫性チェック、能動態への寄せ
- （任意）気の利いた言い換え提案
- **textlint 連携（任意）**: textlint 導入時は日本語の表記・文法・冗長構文を決定的にチェック。未導入時は LLM 判定にフォールバック

すべて**最小差分の diff 提示 → 採否フロー**で返す。全文を勝手に書き換えない。

## 使い方

```
/writing-polish <text>            # テキストを直接渡す
/writing-polish path/to/file.md   # ファイルを読んで推敲
/writing-polish                   # 省略時は直近の自分の生成テキストを対象
```

オプション:

- `--tone <種別>`: 文書種別を明示（commit / pr / issue / rfc / review）
- `--aggressive`: 任意の言い換え提案まで広く出す
- `--embed`: 採否確認を出さず推敲結果のみ返す（他プラグインからの呼び出し用）

自然言語でも起動する（例: 「この PR 本文を推敲して」「コミットメッセージを添削して」）。

## 設計原則

校正を文章生成ではなく**編集**として扱う。一次研究（arXiv 2512.12544 HyperEdit / 2502.13358 FineEdit）が示す**過剰修正（over-correction）**——文法的に正しい箇所を流暢性の名目で書き換える失敗——を避けるため、次を絶対制約にする。

1. 最小・標的型の差分で直す（全文再生成しない）
2. 変更不要箇所を保全する
3. 原文の声・個性を保つ
4. 構造（prefix / テンプレート / コードブロック / 固有名）を壊さない

## 校正ルールの正本

`skills/writing-polish/references/tone-guide.md` が校正ルールの SSOT。textlint の `preset-ja-technical-writing` / `preset-japanese` / `preset-ai-writing` / `preset-JTF-style` と Vale の 11 チェックタイプ、Google / Microsoft style guide を統合したカテゴリ分類を持つ。

## 他プラグインとの連携（soft 委譲）

`pr-creator` / `git-commit-helper` / `issue-design`（linear / indie）が、本文をユーザー提示する直前に `--embed` 付きで writing-polish を呼べる。writing-polish 未インストール時は各プラグインは従来どおり動作する（dormant・後方互換）。

## ライセンス

リポジトリのルート LICENSE に従う。
