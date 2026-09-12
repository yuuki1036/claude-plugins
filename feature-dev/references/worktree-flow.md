# worktree 分離フロー（Phase 4.8 の詳細手順）

SKILL.md 本文の Phase 4.8 は「3 状態判定 → 該当すればここを読んで従う」の骨格だけを持つ。本ファイルは worktree の作成・環境セットアップ・以降の Phase への引き継ぎ規約を持つ。**起動条件を満たしたときだけ Read する**（要求が無い回は読まない）。

## 起動条件（再掲・どちらかを満たすときだけ worktree を作る）

1. ユーザーが「worktree」を明示した（初期リクエスト・会話中の指示・`worktree` を含む引数）
2. プロジェクト指示（CLAUDE.md / memory）が worktree での作業を指示している

**自分の判断で worktree を作らない**。`EnterWorktree` は明示要求があるときだけ使うツールで、「並列で作業しそうだから」という推測で分離してはならない。

## Step 1: worktree の作成と移動（メイン clone + 明示要求あり）

`EnterWorktree` ツールで作成して移動する。`name` は機能を識別できる slug（例: `feature-dev/<短い機能名>`）にする。

移動後に `pwd` と `git rev-parse --abbrev-ref HEAD` を確認し、Phase 5 以降の Edit / Bash がすべて worktree 側で走ることをユーザーに 1 行報告する。

作成に失敗した場合（git repo でない / すでに worktree セッション中）は**分離を諦めて現ディレクトリで続行**し、理由を 1 行添える（実装自体を止めない）。

## Step 2: worktree 環境のセットアップ（DB / port 分離が要るプロジェクトのみ）

dev-workflow が**有効**で、かつ worktree-setup のマーカーが無い場合に限り提案する:

```bash
DEV_WORKFLOW=0
for f in "$HOME/.claude/settings.json" ".claude/settings.json" ".claude/settings.local.json"; do
  grep -Eq '"dev-workflow@[^"]*"[[:space:]]*:[[:space:]]*true' "$f" 2>/dev/null && DEV_WORKFLOW=1
done
[ -f envs/.backend.env.worktree ] && WT_READY=1 || WT_READY=0
```

キー存在だけを見る grep は使わない（`": false"` の無効化済みを導入済みと誤判定し、project-scoped 有効化を取りこぼす）。

- `DEV_WORKFLOW=1` かつ `WT_READY=0` かつプロジェクトが dev server / DB を持つ（`package.json` の `scripts.dev`、`docker-compose.y*ml`、`prisma/`、Rails / Django の DB 設定など）→ `AskUserQuestion` で「DB / port を worktree 用に分離する？」を確認し、「する」なら `Skill` tool で `dev-workflow:worktree-setup` を起動する
- それ以外（マーカー済み / dev-workflow 無効 / DB も dev server も持たない）→ **何も聞かず skip**（no-op を報告しない）

## Step 3: 以降の Phase への引き継ぎ規約

- **Phase 5.3 / 5.5 は worktree の cwd で走らせる**。dev server の port は Step 2 で割り当てた値を使う（メイン側で動いている dev server を掴まない）
- **Phase 6 は `code-review:self-review` のまま**。`code-review:review` は自前で `EnterWorktree` するため worktree の二重進入になる
- **Phase 7 の Event Bus publish はメインリポジトリのルートへ書く**（worktree 相対に書くと teardown で worktree ごと消えるため）。根拠と実装（`--git-common-dir` の親をメインルートにする bash）は SKILL.md Phase 7 の publish 手順が正本 — ここでは二重化せず、worktree 内で続行する回はその手順に従うことだけを押さえる
- **worktree は Phase 7 で畳まない**（commit / PR が残っている）。後片付けは `code-review:self-review` の最終ステップ、または `dev-workflow:worktree-teardown` / `dev-workflow:worktree-gc` に委ねる
