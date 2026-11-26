---
name: start
description: >
  セッション開始時の作業準備。引数の Issue ID を優先し、無ければブランチ名から判定する
  （main ブランチではダッシュボードモード、feature ブランチでは Issue コンテキスト読み込み）。
  第 2 引数以降の「今回の意図」が新規着手で既存の作業が無ければ feature-dev 起動の確認を必ず出す。
  トリガー: 「作業開始」「セッション開始」「今日の作業」「/start」
  引数: [Issue ID] [今回の意図]（省略可）
effort: high
allowed-tools:
  - Agent
  - Skill
  - AskUserQuestion
  - EnterWorktree
  - mcp__linear__get_issue
  - mcp__linear__list_issues
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - TodoWrite
---

# Session Start

セッション開始時にブランチ名に応じて作業準備を行う。
main/master ブランチではダッシュボードモードで全プロジェクトの状況を表示し、
feature ブランチではブランチ名から Issue を特定して関連ファイルを読み込む。

> **モードの本文は、モードごとのファイルにある**（`skills/start/references/modes/<モード>.md`）。この SKILL.md に残すのは、どのモードでも通る「ワークフロー」（Phase 0〜1.5）と、各モードの見出しと Read の行だけ。Phase 1 / 1.5 で決まったモードの見出しに来たら、Read の行が指すファイルを最初に読む。見出しだけを見て、本文を読まずに進めない（1 本のままだと Read 1 回で読み切れず、後ろのモードを読まないまま進めうる / GitHub issue #447）。本文がほかのモードの Phase を引くとき（F7 が引く Phase CTX など）は、そのモードの見出しの Read の行のファイルも読んでから従う。モードのファイルの中の `${CLAUDE_PLUGIN_ROOT}` は、この SKILL.md を Read したパスのプラグインのルートに読み替える

## ワークフロー

### Phase 0: backend 検出（全スキル共通）

<!-- BACKEND-DETECT:START -->
1. Glob で `.claude/indie/*/` と `.claude/linear/*/` を確認する。「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」場合のみ有効な backend とみなす（空 dir・残骸は無効）
2. 1 で両方とも無効なら、linked worktree の中かを確かめる（`git rev-parse --absolute-git-dir` と `git rev-parse --path-format=absolute --git-common-dir` が違えば worktree）。worktree なら、メインのチェックアウト（後者の親 dir）の下の 2 つを同じ述語で確かめ直し、以降の判定はその結果で行う。その場合の DATA_DIR はメインのチェックアウト側の絶対パス（例: `/path/to/repo/.claude/linear`）にする — Issue ファイルを gitignore している repo では worktree の中にデータ dir が無いため
   - worktree のセッションがメインのチェックアウトの `.claude/` の下（この fallback した DATA_DIR を含む）へ書く Edit / Write は、隔離された worktree のセッションだと Claude Code に止められる（`is in the base repo's shared .claude/ directory` と返る）。読むことは止められない。止められたら、メインのチェックアウトへ Bash で書く・コピーするといった回り込みをせず、その回のメイン側への書き込みはそれ以上試さない。書けなかった項目（ファイル・キー・書くはずだった値）を最終報告の「DATA_DIR に未反映」に並べ、残りの手順は進める（反映は worktree の外のセッションで行う）。ただし採番（`counter.txt`）か、Issue・follow-up ファイルの新規作成が止められた回は、止められた時点で後続の手順（ブランチ作成・他スキルへの引き継ぎ・完了の報告）へ進まずに終え、「<書けなかったファイル> を書けなかった（worktree の外のセッションで起動し直す）」と決めた内容を報告する — 採番が確定しないまま進むと、外のセッションが同じ番号を採る
3. `.claude/indie` のみ有効 → `BACKEND=local` / `DATA_DIR=.claude/indie`。`.claude/linear` のみ有効 → `BACKEND=linear` / `DATA_DIR=.claude/linear`。無効な残骸 dir がもう一方にある場合は警告を一言添えて継続する
4. **両方有効** → エラーとして停止する。両 dir の slug 一覧・issues 件数・最終更新日を並べて提示し、どちらを正とするか決めて他方を退避（rename）または削除する片寄せを案内する
5. **どちらも無効** → `/issue-workflow:init` の実行を案内して終了する

以後の `{DATA_DIR}` は検出したデータディレクトリ、`BACKEND` は判定結果を指す。
<!-- BACKEND-DETECT:END -->

### Phase 0.7: Linear MCP 利用可能性チェック（BACKEND=linear のみ）

1. 軽量な Linear MCP 呼び出し（`mcp__linear__get_issue` など）を試みる
2. ツールが見つからない・接続エラーの場合:
   - **AskUserQuestion** で続行/中断を確認する:
     - question: "Linear MCP が利用できません。MCP なしで続行するとローカルファイルの情報のみでセッションを開始します（Linear からの Issue 取得・同期は不可）。"
     - header: "Linear MCP 未検出"
     - options:
       1. label: "続行" / description: "ローカルファイルのみでセッション開始する"
       2. label: "中断" / description: "スキルを中断する"
   - 「中断」選択時: スキルを終了する
   - 「続行」選択時: Linear MCP を使う Phase（1.5, Q2, P1〜P2, F3.5 の Linear Sync Agent）をスキップし、ローカルファイルのみで進行する
3. 正常に応答が返った場合: そのまま Phase 1 に進む

### Phase 1: 対象 Issue の決定と分岐

0. **引数が最優先**: 呼び出し元から渡された引数を次のように解釈する。

   ```
   {ISSUE-ID} [今回の意図（自由記述）]
   ```

   - **第 1 トークン**: Issue ID（`[A-Z]+-\d+` 形式）。あればそれを対象 Issue ID として採用し、**ブランチ名を見ずに Feature ブランチモード（Phase F2 以降）へ直行する**（Phase F1 の抽出は skip）。ブランチが main/master のままでも同様（ブランチを切る前に Issue のコンテキストだけ読みたい、が典型）。その Issue のブランチ・worktree が既にあるかは Phase F2.5 が別の worktree まで見て調べ、無ければ Phase F7 で作る
   - **残りの文字列**: 今回のセッションの意図（`TASK_INTENT`）。次の 3 値に分類して Phase F7 の分岐に使う:

     | TASK_INTENT | 判定 | 例 |
     |---|---|---|
     | `new` | これから着手する宣言。「新規タスク」「新規」「new」「これから作る」「着手する」など、**やることの中身を含まない着手宣言** | `TEAM-123 新規タスク` |
     | `continue` | 具体的なやることが書かれている（中身がある） | `TEAM-123 ログイン画面のバリデーション直す` |
     | `auto` | 意図の記述が無い（Issue ID のみ、または引数なし） | `TEAM-123` |

     判別は「やることの中身が書かれているか」で行う。書かれていなければ `new`、書かれていれば `continue`。
     `continue` の文言は Phase F6 の報告で「今回のセッションでやること」として明示し、F3.7 の knowledge 検索キーワードにも加える。

1. 引数に Issue ID が無い場合: `git branch --show-current` でカレントブランチ名を取得する（Bash）
2. **BACKEND=local の場合:**
   - ブランチ名が `main` または `master` → **ダッシュボードモード**（Phase D1〜D4）へ進む
   - それ以外 → **Feature ブランチモード**（Phase F1〜F7）へ進む
3. **BACKEND=linear の場合:**
   - ブランチ名から Issue ID（正規表現 `[A-Z]+-\d+`）を抽出できない（main, develop 等）→ **Quick Pick モード**（Phase Q1〜Q3）へ進む
   - Issue ID を抽出できた → **Phase 1.5** へ進む

### Phase 1.5: 子 Issue 有無チェック（BACKEND=linear のみ）

1. `mcp__linear__list_issues(parentId={issueId}, limit=1)` を呼び出す
   - `limit: 1` で1件だけ取得（存在チェックのみ）
2. 結果が1件以上: **親 Issue 軽量サマリーモード**（Phase P1〜P2）へ進む
3. 結果が0件: **Feature ブランチモード**（Phase F1〜F7）へ進む

---

## Quick Pick モード（BACKEND=linear・Issue ID なしブランチ）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/start/references/modes/quick-pick.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## 親 Issue 軽量サマリーモード（BACKEND=linear・子 Issue あり）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/start/references/modes/parent-summary.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## ダッシュボードモード（BACKEND=local・main/master ブランチ時）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/start/references/modes/dashboard.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## Feature ブランチモード

このモードの回は、F7 に入る前に「セッションコンテキスト書き出し」の見出しの Read の行のファイルも読む（F7 は feature-dev・軽量フローへ処理を渡して start に戻らない）。

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/start/references/modes/feature-branch.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## セッションコンテキスト書き出し（Feature ブランチモード共通）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/start/references/modes/session-context-write.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。
