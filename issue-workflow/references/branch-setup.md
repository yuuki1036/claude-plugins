# ブランチの作成（start / issue-create 共通の手順）

Issue のブランチをまだ切っていないとき、start（Phase F7 ほか）と issue-create（Phase 7）はこの手順でブランチを作る。今のチェックアウトで切るか、worktree に分けてセッションごとそこへ移るかを決める（GitHub issue #280）。start の Phase F2.5 が既存の worktree へ移るときも 4 と 5 を使う（既存の作業の見つけ方は `${CLAUDE_PLUGIN_ROOT}/skills/start/references/existing-work.md`）。

## 0. 対象とブランチ名

今のブランチ名に `{ISSUE-ID}` が含まれていれば、ブランチは作成済みなので何もしない。start の Phase F2.5 が既存のブランチ（ローカル / origin）を見つけた回は、`{BRANCH}` をその名前（`origin/` は外す）にして新しい名前を作らない。

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

「このチェックアウトで切る」→ `git checkout -b {BRANCH}` を実行して終わる。既存のブランチなら `git switch {BRANCH}`（origin にだけあれば、それを追跡するブランチができる。`already used by worktree at <path>` で失敗し、その path が無ければ、3 の登録だけが残った worktree の回と同じく案内して止まる）。「スキップ」→ 何もしない。「worktree に作って移る」→ 3 へ。

## 3. worktree を作る

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/branch-setup.sh" worktree "{BRANCH}" --name "{ISSUE-ID}"
```

- 起点は既定ブランチ（`origin/<既定>` があればそちら）。今いるブランチからは切らない — 別の作業のブランチの上に積まないため。別の起点が要るときだけ `--base <ref>` を付ける
- `{BRANCH}` が既にあれば、そのブランチで worktree を作る（出力は `base=-`）。origin にだけあれば、それを追跡するブランチとして取り出す（`base=origin/{BRANCH}`）
- `{BRANCH}` を別の path の worktree で checkout 済みなら、作らずにその worktree を返す（`created=0`、`worktree=` がその path。メインのチェックアウトのこともある）。既存のチェックアウトなので `env_copied=` / `install=` の行は出ず、依存のインストールもしない。移るときは 5 の「既存の worktree へ移った回」に従う
- `.claude/worktrees/{ISSUE-ID}` に別のブランチ（または detached HEAD）の worktree があれば exit 1（頼まれた `{BRANCH}` の名前で返さない）
- `{BRANCH}` か `.claude/worktrees/{ISSUE-ID}` を、ディレクトリ（または中の `.git`）が消えて git に登録だけが残った worktree（prunable）が持っていれば、何も書き換えずに exit 1 で、stderr に登録の消し方が出る（`git worktree prune`。locked な登録は prune で消えないので unlock も、detached HEAD ならコミットを残す `git branch` も）。この回は今のチェックアウトで切るかを聞き直さない（`git switch {BRANCH}` も `already used by worktree` で失敗する）。stderr を伝え、その手順の後にやり直すよう案内して止まる。prune / unlock はこちらで打たない（一時的に見えないだけの worktree の登録も消える）
- それ以外の exit 1 / 2 → stderr をそのまま伝え、今のチェックアウトで切るかを聞き直す
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
- **既存の worktree へ移った回**（start の Phase F2.5、または 3 で別の path が返った回）: `{DATA_DIR}` を追跡している repo では worktree 側を正として読み、worktree に既にあるファイルをメイン側の版で上書きしない（そのブランチで書いた進捗が入っている）。この skill がメイン側で新しく作ったファイル（issue-create の Issue ファイルなど）が worktree に無いときだけ、上の DATA_DIR の項どおり写す。報告は worktree のパス・ブランチ・コミット数・未コミットの変更だけにする（起点・`.env*`・依存のインストールは扱っていない）。session-context.md と feature-dev へ渡す決まりは上と同じ
