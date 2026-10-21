# 既存の作業の検知（start の Phase F2.5）

start の Phase F2.5 が読む。`branch-setup.sh existing {ISSUE-ID}` の出力から `WORK_STATE` を決め、必要なら既存の worktree へ移り、F6 の先頭に置く判定行（`WORK_LINE`）を作る（GitHub issue #305）。今のチェックアウトの HEAD だけを見ていた頃は、main で `/start {ID}` を呼ぶと、別の worktree にコミットが積まれていても「コミット 0 件」の新規として扱い、着手の選択からブランチ作成へ進んでいた。

## 1. 出力の読み方

候補ごとに 9 行が同じ順で並ぶ（同じキーの n 番目どうしが 1 件）。最後の `found=` が候補の数で、該当なしなら `found=0` だけが出る。

| キー | 値 |
|---|---|
| `worktree=` | その候補を checkout している worktree の絶対パス。無ければ `-`（`prunable=` にパスがある候補も `-`） |
| `branch=` | ブランチ名。detached HEAD は `detached`、origin にだけあれば `origin/<名前>` |
| `ahead=` | 既定ブランチ（ローカルと `origin/<既定>` のどちらにも）に無いコミットの数。既定ブランチが分からない・git が数えられない（まだコミットの無い HEAD など）なら `-` |
| `dirty=` | 未コミットの変更の行数（`.claude/` 配下の未追跡と、worktree を作ったときに写した `.env*`（メイン側と中身が同じもの）は数えない）。worktree が無い・`git status` が失敗したら `-` |
| `matched=` | 結び付けた手がかり: `branch`（名前に ID）/ `path`（`.claude/worktrees/<ID>`）/ `session-context`（detached HEAD の worktree の `.claude/session-context.md`）のカンマ区切り |
| `current=` | 今いるチェックアウトなら `1` |
| `prunable=` | ディレクトリ（または中の `.git`）が消えて git に登録だけが残った worktree のパス。git はそのブランチをまだ checkout 済みと見るので、そこへ移ることも、`git switch` も、worktree の作成もできない。無ければ `-` |
| `locked=` | worktree の登録が `git worktree lock` されていれば `1`。`prunable=` にパスがある候補で `1` なら、`git worktree prune` はその登録を消さない。worktree の無い候補は `0` |
| `head=` | HEAD のコミット（ブランチだけの候補はその先端）。まだコミットの無い HEAD は `-` |

- **作業あり** = `ahead` か `dirty` が 1 以上、または数えられなかった（`-`）。`ahead=-` は続きに倒す（新規に倒すと、コミットのあるブランチを作業なしと読んで着手の選択へ進む）。`dirty=-` は、worktree のある候補（`git status` が失敗した）なら続きに倒し、`worktree=-`（worktree が無い）なら 0 として扱う
- `ahead=-` は、既定ブランチが分からない回は全候補に出る。1 件だけに出るのは git が数えられなかった回。判定行にはコミット数の代わりに「コミット数不明（既定ブランチが分からない / git が数えられない）」と書く
- 並びは worktree（登録だけが残ったものを含む。`git worktree list` の順）→ どこにも checkout されていないローカルのブランチ → origin にだけあるブランチ。fetch はしないので、別のマシンで積んだ直後のコミットは手元で fetch するまで見えない
- exit 2 は `found=0` として扱い、stderr を判定行に添える

## 2. WORK_STATE を決める

上の行から順に当て、最初に当たった行で決める。

| 条件 | WORK_STATE | 扱い |
|---|---|---|
| Issue ファイル（F3 で読む `{DATA_DIR}/{slug}/issues/{ISSUE-ID}.md`。無ければこの行は当たらない）の `status` が `completed` / `canceled` | `closed` | 移動もブランチ作成もしない。判定行で報告だけする。Phase CTX は書かない |
| `current=1` の候補がある（session-context だけの候補も含む） | その `current=1` の候補に作業があれば `here`、無ければ `fresh` | 作業の有無に関わらず今のチェックアウトに残る。ほかの候補は F6 に並べるだけ |
| 移れる候補（`matched` に `branch` か `path` を含む）のどれかに作業がある | 下の順で先頭の候補が worktree を持てば `moved`、`prunable=` にパスがあれば `prunable`、ブランチだけ（`worktree=-`）なら `branch` | `moved` はその worktree へ移る（3）。確認は出さない。`branch` は F7 でそのブランチへ移る。どちらも新しいブランチは作らない。`prunable` は移動もブランチ作成もせず（Phase CTX は書かない）、判定行で登録の消し方（下の `prunable` の項）を案内する |
| 作業のある session-context だけの候補がある | `detached` | 移動もブランチ作成もしない。判定行で、その worktree のセッションで続けるよう案内する。Phase CTX は書かない（今のチェックアウトが detached HEAD の worktree なら、書くと次の /start でここが `current=1` の候補になり、上の行が先に当たってこの判定が効かなくなる） |
| 移れる候補がある（どれも作業なし） | 下の順で先頭の候補の `prunable=` にパスがあれば `prunable`、無ければ `fresh` | `fresh` は、先頭の候補が worktree を持てばそこへ移る（3）。ブランチだけなら移らず、F7 の「ブランチ未作成のとき」でそのブランチを使う（新しい名前を作らない）。`prunable` は移動もブランチ作成もせず（Phase CTX は書かない）、登録の消し方（下の `prunable` の項）を案内する |
| それ以外（0 件、または作業の無い session-context だけの候補） | `none` | これまでどおり新規（F7 でブランチを作る） |

- **選ぶ順**: `ahead` が多い順 → 同じなら `dirty` が多い順 → それも同じなら出力の順。`-` は 0 として比べる（既定ブランチが分からない回は `ahead=-` が全候補に出るので、`dirty` と出力の順で決まる）
- **`prunable`**: worktree のディレクトリ（または中の `.git`）を `git worktree remove` / `move` を通さずに消した・動かした跡。`git worktree prune` が消すのはその登録で、ブランチは残る。prune の後の /start では、そのブランチは `branch` / `fresh` の候補になる。prune はこちらで打たない（外付けのディスクなどで一時的に見えないだけの worktree の登録も消える）。判定行の案内は `git worktree prune` の後の /start が基本で、次の 2 つは書き足す:
  - `locked=1`: prune はその登録を消さないので、prune だけを案内すると同じ判定が繰り返される。外付けのディスクなどならつなぎ直して /start し直す、不要なら `git worktree unlock <prunable の値>` の後に prune する、と書く
  - `branch=detached` で `ahead` が 0 でない（`-` を含む）: そのコミットは、ほかのブランチに無ければ登録の HEAD からしか辿れず、prune で登録と一緒に辿れなくなる（次の /start は `none` になり、ブランチを新しく作る）。prune の前に `git branch <名前> <head の値>` で残すよう書く
- **session-context だけの候補**（`matched=session-context`）には移らない。Claude アプリが作る detached HEAD の worktree で、別の稼働中のセッションが使っていることがある。作業があり、`current=1` の候補が無く、移れる候補にも作業が無ければ `detached` にする — ここで新規として始めると、その worktree の続きと並行に同じ Issue を作り直すことになる。ほかの WORK_STATE に決まった回も、作業があれば 4 の書式で判定行と F6 に並べる。作業なしなら捨てる（session-context が残っているだけ）
- `detached` の回に利用者がここで新しく始めると言ったら（その worktree が古い残りだった、など）、`detached` の行を飛ばして下の行で決め直す
- `TASK_INTENT = new` で作業のある `here` / `moved` / `branch` に決まった回（F7 は着手の選択を出さず続きとして扱う）に、利用者が既存は捨てて新しく始めたいと言ったら、ブランチ・worktree・コミットはこちらで消さない（`git branch -D` / `git worktree remove` は取り消せない）。行を飛ばして F7 のブランチ作成にも進めない — ID を含む今のブランチや `.claude/worktrees/<ID>` は既存のものがそのまま使われ（branch-setup.md の 0 / 3）、別の名前で切っても次の /start は上の選ぶ順で `ahead` の多い既存の方を選び直す。候補を結び付ける手がかり（1 の `matched=`）が 1 つでも残ると次の /start も同じ候補に決まるので、残るものごとに次の手順を案内し、利用者が済ませた後の /start で決め直す（どれも残らなければ `none` で新規になる）:
  - ブランチ名の ID: そのブランチを消すか、ID を含まない名前に変える（`git branch -m`）。origin に push 済みなら `origin/<名前>` が残り、ローカルを消しても名前を変えても候補に残る。リモートのブランチも消すか名前を変えるよう案内する（リモートへの操作はこちらで打たない）
  - `.claude/worktrees/<ID>` の worktree: ブランチの名前を変えてもパスで結び付く。`git worktree remove` するか、ID を含まないパスへ `git worktree move` する
  - detached HEAD の worktree: `.claude/session-context.md` が ID を持つ間は、`git worktree move` で動かしても session-context で結び付く。worktree を remove するか、その session-context を消す
- `{WORK_DIR}` は、移った回（`moved` と、worktree へ移った `fresh`）は移り先の worktree、それ以外（`branch`・`closed`・`detached`・`prunable` を含む）は今のチェックアウトの root を指す。F3.5 の Agent #2 に渡す
- 確認なしで移るのは、移り先が後から `EnterWorktree`（または `ExitWorktree`）で直せるため。意図しない回は判定行を見て戻す

## 3. 既存の worktree へ移る

`${CLAUDE_PLUGIN_ROOT}/references/branch-setup.md` の 4（作業ディレクトリを移す）と、5 の「既存の worktree へ移った回」に従う。

- `{WORKTREE}` は選んだ候補の `worktree=` の値。新しい worktree もブランチも作らない（`.env*` の複製・依存のインストールもしない）
- 移り先がメインのチェックアウトや `../<name>` で `EnterWorktree` が受け付けないときは、同 doc の 4 にある「開き直しの案内と絶対パスでの作業」に落ちる
- `{DATA_DIR}` を git で追跡している repo では、F3 の Issue ファイルは `{WORKTREE}` 側を読む（そのブランチで書いた進捗が入っている）。gitignore している repo ではメイン側を読む
- 移ったかどうかは判定行に書く。移れなかったときもその旨を書き、以降は絶対パスで作業する

## 4. 判定行（WORK_LINE）

F6 の先頭に置く 1 行。結果と根拠（ブランチ・場所・コミット数・未コミットの変更）を書く。パスはメインのチェックアウトの下なら相対で書く。WORK_STATE ごとの例（行頭のラベルは書かない）:

```
moved     判定: 続き — `feat/TEAM-12-x` を `.claude/worktrees/TEAM-12` で 3 コミット・未コミット 2 件（そこへ移った。別のセッションがこの worktree で作業中なら並行編集になる）
here      判定: 続き — 今のチェックアウト（`feat/TEAM-12-x`）で 3 コミット・未コミット 1 件
branch    判定: 続き — `feat/TEAM-12-x` に 3 コミット（checkout している worktree は無い。F7 でそのブランチへ移る）
detached  判定: 続きは別の worktree — `.claude/worktrees/happy-x`（detached HEAD。session-context が TEAM-12）で 2 コミット・未コミット 1 件。移らずブランチも作らない。続けるならその worktree のセッションで /start する
fresh     判定: 新規 — `feat/TEAM-12-x` を `.claude/worktrees/TEAM-12` で checkout しているが、既定ブランチに無いコミットも未コミットの変更も無い（そこへ移った。別のセッションがこの worktree で作業中なら並行編集になる）
fresh     判定: 新規 — `feat/TEAM-12-x` はあるが、既定ブランチに無いコミットは無い（checkout している worktree は無い。F7 でこのブランチを使う）
none      判定: 新規 — TEAM-12 を含むブランチも worktree も無い
closed    判定: 完了済み（status: completed）— 移動もブランチ作成もしない。再開するなら status を戻してから /start する
prunable  判定: 続き（移れない）— `feat/TEAM-12-x` に 3 コミット。checkout していた worktree `.claude/worktrees/TEAM-12` はディレクトリ（または中の .git）が無く、git に登録だけが残っている。移動もブランチ作成もしない。`git worktree prune` の後に /start し直す
prunable  判定: 続き（移れない）— `.claude/worktrees/TEAM-12`（detached HEAD）に 2 コミット。ディレクトリ（または中の .git）が無く、git に登録だけが残っている。移動もブランチ作成もしない。`git branch <名前> 1a2b3c4` でコミットを残し、`git worktree prune` の後に /start し直す
```

- **別の worktree へ移った回**（`moved` と、worktree へ移った `fresh`）は、末尾の括弧に「別のセッションがこの worktree で作業中なら並行編集になる」を添える。使っているセッションがあるかはこちらから判定できない
- `TASK_INTENT = new` で作業ありのときは食い違いを書く（`here` / `moved` / `branch` なら F7 は着手の選択を出さず続きとして扱う。GitHub issue #305 の完了条件）: 「判定: 続き（引数は新規）— `feat/TEAM-12-x` に 3 コミット。着手の選択は出さず、ブランチも作らず既存を続ける」
- 候補が 2 件以上なら末尾に「ほかに N 件」を足し、F6 の Git 状態に全候補の worktree・ブランチ・コミット数・未コミットの変更を並べる
- `detached` 以外の回で、作業のある session-context だけの候補があれば、末尾に「`<path>`（detached HEAD）にも作業がある。続けるならその worktree のセッションで /start する」を足す

## 5. 判定行と F6 の Git 状態の食い違い

判定行（`existing` の値）と F6 の Git 状態（F3.5 の Agent #2 の値）は数え方が違う。`existing` の `ahead` は `origin/<既定>` にあるコミットも除き、`dirty` は `.claude/` 配下の未追跡と写した `.env*` を除く。Agent #2 はローカルの `main`（無ければ `master`）との merge-base から数え、`git status --short` を全行数える。worktree は `origin/<既定>` から切るので、ローカルの既定ブランチが遅れているだけで数が違ってくる。数が違えば `WORK_STATE` に関わらず判定行を正とし、F6 の Git 状態に差の理由を 1 句添える。

`branch` は移動が F7（F6 の後）なので、Agent #2 は移る前のチェックアウト（main など）の Git 状態を集める。`detached` と `prunable` は移らないので、集めるのは作業の無い今のチェックアウトの値になる。どれも F6 の Git 状態にはその旨も添える。
