# ブランチの作成（start / issue-create 共通の手順）

Issue のブランチをまだ切っていないとき、start（Phase F7 ほか）と issue-create（Phase 7）はこの手順でブランチを作る。今のチェックアウトで切るか、worktree に分けてセッションごとそこへ移るかを決める（GitHub issue #280）。

## 0. 対象とブランチ名

今のブランチ名に `{ISSUE-ID}` が含まれていれば、ブランチは作成済みなので何もしない。

ブランチ名は `{BRANCH}` = `{type}/{ISSUE-ID}-{description}`:

- type は Issue の type から: bugfix → `fix`、feature → `feat`、investigation → `investigate`、debt → `chore`
- description はタイトルから作る短い英語の kebab-case
- 例: `feat/MYAPP-3-add-auth`、`fix/TEAM-123-fix-typo`

## 1. 状態を取る

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/branch-setup.sh" status
```

出力の `dirty`（未コミットの変更の行数）・`in_worktree`・`branch`・`main_root` を控える。

## 2. 作り方を決める

**AskUserQuestion** で 1 回だけ聞く。推奨は `dirty` で決める:

- `dirty` が 1 以上 → **worktree を推奨**。今のチェックアウトで `git checkout -b` すると、別の作業の未コミットの変更が新しいブランチに持ち越される
- `dirty=0` → 今のチェックアウトを推奨

- question: "ブランチ `{BRANCH}` をどこに作りますか？"（`dirty` が 1 以上なら「今のチェックアウトに未コミットの変更が {dirty} 件あります」を添える）
- header: "ブランチ"
- options（推奨の選択肢を先頭にして label に ` (推奨)` を付ける）:
  1. label: "worktree に作って移る" / description: "`.claude/worktrees/{ISSUE-ID}` に作り、.env* の複製と依存のインストールをして、セッションの作業ディレクトリもそこへ移す"
  2. label: "このチェックアウトで切る" / description: "`git checkout -b {BRANCH}`（未コミットの変更はそのまま持ち越される）"
  3. label: "スキップ" / description: "ブランチは自分で作る"

「このチェックアウトで切る」→ `git checkout -b {BRANCH}` を実行して終わる。「スキップ」→ 何もしない。「worktree に作って移る」→ 3 へ。

## 3. worktree を作る

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/branch-setup.sh" worktree "{BRANCH}" --name "{ISSUE-ID}"
```

- 起点は既定ブランチ（`origin/<既定>` があればそちら）。今いるブランチからは切らない — 別の作業のブランチの上に積まないため。別の起点が要るときだけ `--base <ref>` を付ける
- `{BRANCH}` が既にあれば、そのブランチで worktree を作る（出力は `base=-`）
- exit 1 / 2 → stderr をそのまま伝え、今のチェックアウトで切るかを聞き直す
- `install=` の行があれば、worktree の中で順に実行する（`cd "{WORKTREE}" && <コマンド>`）。失敗しても worktree は残して進め、失敗したコマンドを報告に含める
- `.claude/worktrees/` が gitignore されていなければ、スクリプトが `.git/info/exclude` に足す（`excluded=1`）。リポジトリの `.gitignore` は触らない

以降の `{WORKTREE}` は出力の `worktree=` の値を指す。

## 4. セッションの作業ディレクトリを移す

worktree を作っただけでは、diff ペイン・Bash の cwd・プロジェクト設定（hook / CLAUDE.md）は元のチェックアウトのまま。作った直後に移す:

- CLI: `EnterWorktree` に `path: "{WORKTREE}"` を渡す。`name` を渡すと別の worktree が新しく作られる
- デスクトップアプリ: 作業ディレクトリを変えるツール（`change_directory` など）で `{WORKTREE}` へ移す
- どちらも使えない・失敗した → `{WORKTREE}` でセッションを開き直すよう案内する。この会話では以降すべて絶対パスで作業する

**移動の反映が次の返答からになる環境がある**。`pwd` が `{WORKTREE}` を返すまでは、Bash は `cd "{WORKTREE}" && …` で始め、Read / Edit / Write は絶対パスを使う。

## 5. 移した後の決まりごと

- **DATA_DIR**: この skill の残りでは、`{DATA_DIR}` が相対パスなら `{main_root}/{DATA_DIR}` に読み替える（移動後の相対パスは worktree を指す）。移動後に起動する skill は、Phase 0 の backend 検出が worktree にデータ dir が無いときにメインのチェックアウトへ fallback する
- **DATA_DIR を git で追跡している repo**（`git -C "{main_root}" check-ignore -q "{DATA_DIR}"` が偽）: worktree には起点のブランチの `{DATA_DIR}` が入っており、この skill がメイン側で作った・書き換えたファイル（issue-create なら Issue ファイルと `counter.txt`）はまだ無い。worktree の同じパスへ写し、以降の編集は worktree 側で行う（ブランチと一緒にコミットされる）。メイン側にも同じ変更が残ることを報告に書く。gitignore している repo では写さない
- **session-context.md**: start の Phase CTX は `{WORKTREE}/.claude/session-context.md` に書く。code-review と issue-band は、作業しているチェックアウトの `.claude/session-context.md` を読む
- **feature-dev へ渡す**: 続けて起動するときは、引数に「worktree: `{WORKTREE}`（作成・移動済み。新しく作らない）」を添える。feature-dev の Phase 4.8 は worktree の中として扱い、環境のセットアップと Phase 7 の publish 先の規約に従う
- **報告**: worktree のパス・ブランチ・起点・複製した .env*（`env_copied=` の行。0 件なら「なし」）・依存のインストールの結果・作業ディレクトリを移せたか
- **後片付け**: issue-maintain の worktree teardown 連携、または dev-workflow の worktree-teardown / worktree-gc に任せる
