---
name: pr-creator
description: |
  PRを作成し、差分とコミット履歴からdescriptionを自動生成する。
  ドラフトPRとして作成し、リポジトリのPRテンプレート・PR作成ルールがあれば自動準拠する。
  PR本文はユーザー承認を得てから作成する（人間確認必須）。
  Linear Issue連携: ブランチ名からIssue IDを抽出し、タイトル・説明とコメントを取得する。
  トリガー: ユーザーが「PR作って」「/pr-creator」「プルリクエスト作成」と言った時。
effort: medium
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - Skill
  - mcp__linear__get_issue
  - mcp__linear__list_comments
  - mcp__github__create_pull_request
  - mcp__github__update_pull_request
---

# PR Creator

## 実行手順

### 1. リポジトリの PR 作成ルールを確認

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-1.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 2. 状態確認

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-2.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 3. Linear Issue連携（該当する場合）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-3.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4. PR情報を生成

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-4.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.5 Screenshots 添付（UI PR のみ）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-4.5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.6 説明図の添付（UI 変更の有無を問わない / GitHub issue #287）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-4.6.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.7 概要の三要素セルフチェック

次の 4.3 は番号の順でなく実行の順（4.7 の後・4.9 の前。本文が最終形になった時点）に置いてある。

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-4.7.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.3 writing-polish 連携（PR 本文添削・必須）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-4.3.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.9 PR body の最終検証（gitignored パス検出）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-4.9.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.93 必須サブステップの pre-flight ゲート（fail-closed）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-4.93.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.95 PR 本文の人間確認（必須）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-4.95.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 5. PRを作成

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

## 厳守ルール

- **必須サブステップの pre-flight チェックリスト（Step 4.93）を出力し、全行を `done` / `N-A: 理由` で埋めてから Step 4.95 の提示に進む**。writing-polish（有効時）・三要素セルフチェック・body の機械検証は `N-A` にできない。動作確認は大セクションとして生成し、チェックリスト 1 行に潰さない
- **PR 本文（title / body）はユーザーの承認を得てから作成する**（Step 4.95）。承認前の `gh pr create` / `mcp__github__create_pull_request` は禁止。唯一の例外は同一セッション内でユーザーが承認プロセスの省略を明示した場合のみ（Step 4.95 の例外定義に従う。包括的・曖昧な指示は例外にしない）
- **作業リポジトリの PR 作成ルール（テンプレート・CONTRIBUTING・CLAUDE.md 等）を遵守する**。本スキルの既定と矛盾する場合はリポジトリ側を優先し、上書きした点は確認時に明示する（Step 1）。ただし優先できるのは Step 1 の限定列挙の範囲のみで、**承認ゲート・ローカルパス非出力・機密チェック・AI 署名禁止はリポジトリ規約でも上書き不可**
- 常にドラフトPRとして作成（リポジトリ規約が draft 以外を指定する場合はそちらに従い、Step 4.95 で提示した種別どおりに作成する）
- テンプレートのセクションは空欄にせず内容を埋める。書くことがなければセクションごと削除する
- AI 署名（Generated with 等）は付けない
- 本文は人間向け、末尾の `<details>` 折りたたみは AI 向けの補足情報。レビュアーが行動を変える情報を折りたたみに隠さない
- 文体は体言止め・常体に統一する。敬体（です・ます）は使わない。コミットメッセージの文体と揃える
- 箇条書きの乱発を避ける（並列性のない情報を無理に箇条書きにしない）。並列の手順 / 変更項目 / 動作確認ケースが複数ある場合は箇条書きで OK
- 太字の乱用と装飾絵文字（✅ ❌ 🤖 など）は避ける
- 概要は `What / Why / Outcome` の三要素（変更対象 / 動機 / 結果）を満たすこと。実装手段（How）は「変更点」セクションに書く
- 本文量の上限を数値で守る（質的記述だけだと冗長化するため数値で制限）: **概要は What/Why/Outcome の bullet 3 本（各 1 文）/ 「変更点」は 1〜5 bullet / 「レビューしてほしいところ」は 1〜3 件**。上限を超える場合は情報を圧縮するか PR 分割を検討する。Screenshots 節は frontend（UI 拡張子）変更を含む場合のみ追加する（Step 4.5 の判定に従う）。説明図は 2 枚まで（Step 4.6）
- 概要の 3 bullet は **What / Why / Outcome のどれも省かない**。brevity を優先して Why / Outcome を空にするのは違反。散文テンプレ repo では 3 要素を各々明示する。生成後に Step 4.7 のセルフチェックで 3 要素の充足を確認する
- PR title に Issue ID prefix（`TEAM-123:` 等）を含めない。Issue ID は PR 本文側にリンク・参照として記載する
- PR 本文（本文・`<details>` 折りたたみ問わず）にローカルパス（`.claude/plans/...` / `.claude/screenshots/...` 等）を出力しない。GitHub からクリックできないため。唯一の例外は `--attach` に渡したファイルへの Markdown 画像参照で、作成時に gh がアップロード先 URL へ書き換える（Step 4.5 / 4.9）
- レビュアーがアクセスできないローカル限定ドキュメント（`.claude/` 配下の knowledge / plans / issues 等）は、**パス文字列の有無に関わらず**本文で参照しない。「knowledge に詳細」「設計メモ参照」のような自然言語の言及も含む。必要な情報は本文へインライン要約する（参照させるのではなく要点を書き写す）
- Screenshots と説明図は `gh pr create --attach` で PR 作成と同時にアップロードする。独自のアセットブランチ・GitHub Release・tag は作らない
- 機密情報（ログイン画面、社内 URL、実データ等）が写っていないか撮影前に確認する。説明図も、図に書いたテキストを同じ基準で確認する（Step 4.6）。添付は PR を閲覧できる人全員に見える（public repo なら誰でも）
