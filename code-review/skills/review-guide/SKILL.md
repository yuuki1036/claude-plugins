---
name: review-guide
description: >
  PR（または base 指定のローカル diff）を人間が後から理解するための読み順ガイドを出す。精読に値するファイルだけを 1〜5 件選び、実装の流れ順（入口 → ロジック → 永続化 → テスト）に並べ、各ファイルに 何をした / 難点 / 見る行 / レビュー観点 を付ける。投稿・永続化はしない。--walkthrough では精読を 1 件ずつ解説し、見つけた修正をその場で入れる（読み合わせ）。--hide-guide はガイドと解説を表示せずに読み合わせと同じ工程を踏み、締めだけを出す。
  トリガー: 「PR の読み方」「読み順」「この PR を解説して」「このPR何やってる」「PR を理解したい」「読み合わせ」「/review-guide」
  引数: [PR番号 | --base <ref>] [--top N] [--walkthrough] [--hide-guide]（省略時は現在ブランチの PR）
effort: medium
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
  - Edit
  - AskUserQuestion
---

# review-guide

PR を**読む人間**を支援する skill。指摘を出す（review / self-review）でも付いた指摘に応える（review-triage）でもなく、**diff のどこをどの順で読めばよいか**を案内する。主用途は自分の PR を後から理解すること、副用途は他者 PR に review を回した後の学習。もう 1 つの用途が**コミット前の読み合わせ**（`--walkthrough`）: self-review の後に精読を 1 件ずつ解説し、利用者が変更を理解しながら、解説の中で見つかった修正をその場で入れる。読み合わせの工程（精読を選び、レビュー観点に答え、直せるものを直す）はガイドを読まない回にもコードの質を上げるので、`--hide-guide` ではガイドと解説を表示せずに同じ工程を踏み、締めだけを出す。

正本設計: `.claude/designs/20260916-code-review-review-guide-skill.md`。

## review / self-review / review-triage との違い

- review / self-review は severity 付き findings を**出す**。本 skill は findings を出さない。「レビュー観点」は「このファイルで何を見るか」の問いであって判定ではない。読み合わせ（Step 6）では、その問いに自分で答えた結果を解説に添える（判定の一覧は作らない）
- 出力は**セッション内のみ**。ファイルを書かない・コメントを投稿しない。コードを直すのは読み合わせの中だけ（Step 6・7。条件は絶対厳守ルール）。他の書き込みは base モードの読み順の記録 1 件だけ（Step 5）
- 全ファイルは解説しない。精読は**精読に値するものだけを 1〜5 件**選び（`--top N` で上限を下げられる）、数合わせで埋めない。残りは 1 行で流し読み / 不要に振る

## 絶対厳守ルール

- **書き込みは 2 つに限る**。ファイル作成・コメント投稿・push・commit・Issue 起票は一切しない。許される書き込みは次の 2 つだけ:
  1. base モードの Step 5 で `guide-order.sh` が git dir（作業ツリーの外。diff にも status にも出ない）に書く読み順の記録 1 件。`/guide-diff`（code-review の mod）の入力になる。毎回上書きし、mods が無い環境では読まれないだけ
  2. 読み合わせ（Step 6・7）で入れるコードの修正。`--walkthrough` / `--hide-guide` で起動した回（`WALKTHROUGH=1`）か、利用者が解説の途中で直すよう言った回に限り、**対象が今チェックアウトしている作業ツリーの変更のとき**だけ Edit で直す（Step 0 の `FIX_OK`）。直してよい範囲と、直さずに聞くものの線引きは Step 6
- **各主張に `file:line` を添える**。「この PR で何をした」「難点」「主張 vs diff」に書く事実は、確認した `file:line` を根拠にする。確かめられないことは書かない（「難点: 特になし」を許す）。記録・コミットメッセージ・PR 本文の主張をそのまま採用せず、diff とコードで確かめる。例外は同じセッションでユーザーが伝えた前提・決定で、根拠を「セッション中の決定」と書く（Step 1.5）。コードの事実の根拠をこれで置き換えない
- **精読を数合わせで埋めない**。上限（既定 5）は読み手の負担の上限であって目標ではない。精読に値するものが 2 件なら 2 件で出す（Step 2）
- **精読の上限で切っても core を落とさない**。上限で core は流し読みに落ちても「不要」には落とさない

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md の 10 原則のうち **採用: 1（ファネル = triage-signals の分類で精読を 1〜5 件に絞ってから agent を当てる）/ 3（段階予算 = `${CLAUDE_EFFORT}` で explorer 0/2/3 体）/ 4（モデルルーティング = explorer は `sonnet`・統合は `opus`＝メインコンテキスト）/ 5（暴走ガード = explorer 体数上限・精読の上限 5）/ 9（構造化受け渡し = diff はパス渡し、explorer は事実のみ返す）**。**捨てた**: 2・10（severity / confidence を付けない。判定ではなく説明）/ 6（蓄積しない。永続化なし）/ 7（反証レイヤーなし。説明文の根拠を `file:line` で強制し、無い主張は書かない。読み合わせで入れた修正は利用者が解説と並べて確かめ（`--hide-guide` の回は締めの前置きに変更前後と確かめ方を並べ）、Step 7 の判断で 2 回目の self-review か決定的な検証に回す）/ 8（静的な読解に機械判定オラクルが無い。読み合わせの締めで変異テストを提案するが、提案だけで回すのは呼び出し元なので捨てたまま）。

## 実行手順

### 0. 入力確定と diff 収集

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-0.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 1. PR コンテキスト（PR モードのみ）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-1.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 1.5 セッション中に伝えられた前提・決定（PR / base モード共通 / GitHub issue #291）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-1.5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 2. 重要度スコアと 3 段振り分け（メインコンテキスト・agent なし）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-2.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 3. 流れの把握（`${CLAUDE_EFFORT}` 分岐 / 実行時値: `${CLAUDE_EFFORT}`）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-3.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4. 統合・執筆（メインコンテキスト）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-4.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 5. レポート出力

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 6. 精読の解説（読み合わせ / レポートの後 / GitHub issue #291）

`WALKTHROUGH=1` の回、または利用者がレポートの後に精読を 1 件ずつ解説させる回だけ入る（それ以外の回は Step 5 で終える）。

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-6.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 7. 読み合わせの締め（最後の精読の後）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/references/step-7.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

## Additional Resources

- `${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh` — diff 収集と分類・リスク信号（`--pr` / `--base`）
- `${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh` — PR 本文・コメントの取得（`--save`）
- `${CLAUDE_PLUGIN_ROOT}/scripts/diff-slice.sh` — 精読ファイルの hunk 切り出し
- `${CLAUDE_PLUGIN_ROOT}/scripts/guide-order.sh` — base モードの読み順の記録（Step 5。`/guide-diff` の入力）
- `${CLAUDE_PLUGIN_ROOT}/scripts/detect-recent-review.sh` — 直近のレビューとの突き合わせ（Step 7 の self-review 以降の変更）
- `${CLAUDE_PLUGIN_ROOT}/scripts/detect-mutation-tool.sh` — 変異テストの道具の検出（Step 7 の 4.。宣言 `.claude/mutation-test.sh` か、ルートの設定ファイルからの推測）
- `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` — explorer 起動の共通詳細（Step 3 の high 以上で Read）
- `${CLAUDE_PLUGIN_ROOT}/references/review-guide-format.md` — レポート形式と 4 項目の書き方（Step 4 で Read）・精読の解説と締めの形式（Step 6・7）
- `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 3` — レビュー観点判定表（正本・複製しない）
