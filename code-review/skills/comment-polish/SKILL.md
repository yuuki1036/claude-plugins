---
name: comment-polish
description: >
  diff で追加・変更したコード内コメントを精査して直す。2 観点（読み手に必要な情報か / 冗長表現の排除）での推敲と、
  git 外の参照 ID（Linear Issue ID / Linear URL）の除去を 1 コマンドで行う。差分提示 → 承認 → 適用。
  self-review からは --embed で全件適用される。
  トリガー: 「コメント精査」「コメント整理」「コメントを直して」「コメントの ID を消して」「コメント推敲して適用」「/comment-polish」
  引数: [base branch] [--staged] [--embed] [--from-findings <path>] [--github]
effort: medium
allowed-tools:
  - Bash
  - Read
  - Edit
  - AskUserQuestion
---

# comment-polish

diff で追加・変更した**コード内コメント**を 2 観点で推敲し、git 外の参照 ID を除去する。推敲の提案だけで終わらせず、承認を得て Edit で適用するところまでを担う。

## self-review との関係

self-review はレビュー時にコメント推敲提案（B 系統）を**出す**が、適用はしない。本 skill は:

- **単独起動**: self-review を通さない小さな変更で、コメントだけ精査したいとき
- **self-review からの委譲**: self-review Step 7 で修正を選ぶと `--embed --from-findings <path>` で呼ばれ、B 系統の提案を**全件適用**する（再推敲しない）

## 適用範囲（厳守）

- 対象は **diff で追加・変更されたコード内コメント行のみ**。既存コメントの全面推敲はしない（scope 逸脱）
- **md 散文（SKILL.md / README / CHANGELOG / doc）は対象外**（コメント規約の適用範囲。`.claude-plugin/lib/comment-rule.md`）
- コメント以外のコード行は触らない

## 実行手順

### 1. diff 収集

```bash
# base 検出（引数優先。--staged ならステージ済み）
BASE="${1:-$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')}"
[ -z "$BASE" ] && BASE=main
```

`--staged` 指定時は `git diff --cached`、無ければ `git diff <BASE>...HEAD` で追加・変更コメントを把握する。

### 2. git 外 ID の機械検出

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-external-ids.sh" "$BASE" ${STAGED:+--staged} ${GITHUB:+--github}
```

- 既定は Linear Issue ID（`ABC-123`）と Linear URL を検出する（JSON Lines: `file` / `line` / `match`）
- GitHub `#N` は既定で拾わない（正当な why 参照が多く偽陽性になりやすい。実測で確定。`--github` で opt-in）
- exit 1 = 検出あり / 0 = なし / 2 = 判定不能（git/python 不在。その旨を報告して ID 除去は skip、推敲は続行）

### 3. コメントの推敲（2 観点）

**2 観点の定義は複製しない**。`${CLAUDE_PLUGIN_ROOT}/references/prompts/focus/comment-polish.md` の `COMMENT-RULE:START`〜`END` 区間を Read して適用する（正本は `.claude-plugin/lib/comment-rule.md`）。要旨だけ再掲:

- 観点 1: 読み手に必要な情報のみか（コードから自明な再述でないか）
- 観点 2: 冗長表現の排除（重複・長い前置き・1 語で足りる句）
- **判断に迷ったら残す側に倒す**。非自明な why / 外部制約 / 実測値 / ハマりどころは長くても残す

各コメントについて、2 観点の推敲結果と Step 2 の ID 検出結果を統合し、before → after の一覧を作る。ID 除去は「ID だけ落として背景の文は残す」を既定にする（背景ごと消さない）。

### 4. 提示と適用

一覧を次の形式で出す（1 件 4 行）:

```
<file>:<line> [不要|冗長|ID]
  before: <現在のコメント全文>
  after:  <推敲後> または (削除)
  理由:   <1 行>
```

- `[不要]` = 観点 1 / `[冗長]` = 観点 2 / `[ID]` = git 外 ID の除去

**適用の分岐**:

- **`--embed` 指定時（self-review からの委譲）**: 提示のみ簡潔にして**全件を Edit で適用**する。AskUserQuestion は出さない（self-review Step 7 で既に修正方針の承認が済んでいる）。`--from-findings <path>` があれば self-review が書き出した B 系統提案を読み、再推敲せずそれを適用する
- **単独起動時**: AskUserQuestion で確認する
  - question: 「コメント精査の適用方針は？」
  - header: 「コメント精査」
  - options: 1.「全部適用」 2.「選んで適用」 3.「適用しない（一覧だけ）」
  - 「選んで適用」なら multiSelect でファイル×件を選ばせ、選択分だけ Edit

### 5. 報告

適用件数と、ID を除去した行の一覧（file:line）を報告する。該当 0 件なら「精査対象のコメント変更なし」と明記する（silent skip と区別）。

## 絶対厳守ルール

- diff で追加・変更したコメント以外は触らない（既存コメントの一括推敲・コード行の変更の禁止）
- md 散文は対象外
- 2 観点の定義を本文に複製しない（正本 → prompts/focus/comment-polish.md の区間を Read）
- ID 除去は背景の文を残し ID だけ落とす。`Refs #N` 等の正当な参照は検出側で除外済み
- 意味が変わらない同義変換（「〜する」↔「〜を行う」）は出さない

## Additional Resources

- `${CLAUDE_PLUGIN_ROOT}/references/prompts/focus/comment-polish.md` — 2 観点の正本複製（COMMENT-RULE 区間）
- `${CLAUDE_PLUGIN_ROOT}/scripts/detect-external-ids.sh` — git 外 ID の機械検出
