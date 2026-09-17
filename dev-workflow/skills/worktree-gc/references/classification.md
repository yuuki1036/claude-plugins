# worktree-gc の分類規則（正本）

`scan.sh` が各 worktree を 1 行 1 JSON で出力し、`reap.sh` がその行だけを消す。表示と削除の一致を「reap は scan の出力行しか受けない」入力契約で担保する（ADR-20260912142858）。

## scan.sh の出力フィールド（1 行 = 1 worktree）

| フィールド | 型 | 意味 |
|---|---|---|
| `repo` | path | その worktree が属する main repo（`--all` では行ごとに異なる） |
| `path` | path | worktree の絶対パス |
| `branch` | string / null | チェックアウト中のブランチ（detached は null） |
| `head` | sha / null | HEAD のコミット。detached の PR 解決と merged / ahead 判定に使う |
| `kind` | `review` / `agent` / `dev` / `other` / `prunable` | 種別（下記） |
| `nested_parent` | path / null | `agent` の親 review worktree |
| `self` | bool | scan を起動した cwd を含む |
| `primary` | bool | メインの作業ツリー（`--git-dir == --git-common-dir`） |
| `dirty` / `untracked` | bool | `git status --porcelain` の結果。**ネストした agent worktree の dir（`?? .claude/worktrees/`）は数えない**（親 review worktree がそれを抱えるだけで keep になっていた / GitHub issue #224。ネスト側は自分の行で dirty を持つ） |
| `ahead_of_main` | int | `origin/main..branch` のコミット数（origin/main 不在なら 0） |
| `pr` | `{number, state}` / null | ブランチあり: リポごとに 1 回引いた `gh pr list --state all --limit 200` の辞書（無ければ `--head <branch>` で 1 回）。detached: `gh api commits/<head>/pulls`（merged_at あり → `MERGED` / open → `OPEN` / それ以外 → `CLOSED`）。gh 不在なら null |
| `merged_into_main` | bool | ブランチあり: `git branch --merged origin/main` に含まれる。detached: `head` が origin/main の祖先 |
| `issue` | `{id, state, closed}` / null | ブランチ名から取った Issue ID（`[A-Z][A-Z0-9]+-[0-9]+`）。`state` / `closed` は `--issue-status <file>` で渡された値から（無ければ `null` / `false`） |
| `live_pids` | int[] | cwd が path 配下のプロセス（`lsof`） |
| `live_unknown` | bool | lsof を使わなかった（unknown 扱い） |
| `marker` | `{db_name}` / null | `envs/.backend.env.worktree` の `DB_NAME` |
| `db_guess` | string[] | drop 候補の DB 名（**marker のある行のみ**。無ければ `[]`） |
| `verdict` | `reap` / `keep` | 分類結果 |
| `reasons` | string[] | verdict の根拠 |

### kind の判定

- `*/.claude/worktrees/<name>/...`（さらにネスト）→ **agent**（`nested_parent` に親 review worktree）
- `*/.claude/worktrees/<name>` → **review**
- `envs/.backend.env.worktree` or `.frontend.env.worktree` あり → **dev**
- それ以外 → **other**
- `git worktree list` が prunable と印を付けたもの（dir が消えた残骸）→ **prunable**

kind は表示と DB drop 要否にだけ使う。**安全ゲートは kind 別に変えない**（review / dev / other は同じゲート）。

## 安全ゲート（1 つでも真なら keep）

1. `self`（scan を起動した cwd を含む）
2. `primary`（メインの作業ツリー）
3. `dirty` または `untracked`
4. `live_pids` が空でない、または `live_unknown`（生存プロセスの有無が確認できない）
5. `pr` が `OPEN`
6. `pr` が null かつ `merged_into_main` が false — **ただし `issue.closed` が true なら適用しない**
7. `pr` が null かつ `ahead_of_main` が正（gh 不在時の保守側フォールバック）— **同上**

すべて通過したら `reap`。**`pr` が merged / closed なら `ahead_of_main` が正でも `reap`**（統合ブランチ経由 merge の落とし穴 / GitHub issue #223）。

- **detached（review / agent worktree）** もゲートは同じ。ブランチが無いので PR は `head` から引く。gh が無い / PR に紐づかない detached はゲート 6 で keep に落ちる（消さない側）
- **Issue が閉じている（`issue.closed`）** ブランチはゲート 6 / 7 を外す（調査だけで完結し PR を作らない Issue の worktree / GitHub issue #240）。`git worktree remove` はブランチを消さないので ahead のコミットは失われない。他のゲート（dirty / live / pr-open 等）は変えない
- `reasons` の `issue-closed:<ID>:<状態>` / `issue-open:<ID>:<状態>` は**情報であって keep 要因ではない**（表で Issue を開かずに判断できるように添える）

- `prunable` は無条件で `reap`（`git worktree prune` が回収するだけ。dir は既に無い）
- 判定に必要な情報が取れない行（path が dir でない等）は `keep` + `reasons: ["unclassified"]`。誤って残す方が誤って消すより安い

## `--issue-status <file>` の形式

`{"<ID>": {"state": "<表示名>", "type": "<workflow state type>"}}` の辞書。`type` が `completed` / `canceled` なら閉じている。`type` が無い（または値が文字列だけ）のときは名前で判定する（`done` / `completed` / `canceled` / `cancelled` / `closed` / `duplicate`。大文字小文字は無視）。**名前はユーザーがカスタマイズできるので type が正**。ファイルが読めない / オブジェクトでないときは exit 2（黙って無視して「状態を見たつもり」で reap に倒れる経路を作らない）。scan 自身は外部サービスを叩かず、値は呼び出し側（SKILL の Step 1.5・Linear MCP）が書く。

## `--all [root]` の走査

- `find <root> -maxdepth <depth>`（既定 4・`--depth` で変更）で `.git` を探す。`node_modules` / `Library` / `.Trash` / `.cache` / `.npm` は prune
- `.git` がディレクトリなら main repo。ファイル（gitlink）なら common-dir を辿り、`<repo>/.git` の形なら main repo として採用する。submodule の common-dir は `<super>/.git/modules/<name>` で採用されない
- **worktree の列挙は各 main repo の `git worktree list` に委ねる**（find で見つけた gitlink を直接候補にしない）。`git worktree list` に現れないものは対象にならない
- `gh pr list --state all --limit 200` はリポごとに 1 回。root の既定は環境変数 `DEV_WORKFLOW_WORKTREE_GC_ROOT` → `.claude/dev-workflow.json` の `worktree_gc_root` → `$HOME`

## reap.sh の入力契約

- stdin は scan の出力行（1 行 1 JSON）。呼び出し側は行を**選ぶ**ことはできるが**書き換えない**
- `verdict != "reap"` の行が 1 行でも混じれば全体を **exit 2** で拒否（承認フローの迂回を機械的に塞ぐ）
- `path` が現在の `git worktree list` に実在しない行は **SKIP + WARN**（scan 後に消えた stale な承認を弾く）
- 削除直前に `live_pids` を再取得し、非空なら **SKIP + WARN**（scan → 承認 → reap の間に使い始めた became-live race を塞ぐ）。ADR-20260912142858 の「判定を再実行しない」は verdict の再計算の禁止であって、削除直前の安全再確認とは両立する
- 順序は nested（agent）→ 親（review）。行の `repo` ごとに `remove` を終えてから `prune`（`repo` の無い行は cwd のリポで扱う。旧版 scan の出力との後方互換）
- `dirty` な行は承認済みでも `--force` の前に WARN を残す
- **DB drop は marker のある行の `db_name` のみ**。PostgreSQL 前提で、psql が使え DB が存在するときだけ drop。それ以外（psql 不在 / 別 engine）は WARN で手動案内。marker 無し行は DB に一切触れない（名前一致は所有権を証明しない / F1）

## 外部入力の扱い

`branch` / `path` / `db_name` は PR 作者やディスク状態が制御する外部入力。git ref 規則は `$` / バッククォート / `;` / `|` を禁じないため、**シェルで再評価される経路を作らない**（`gh` へは引数で、`jq` へは `--arg` で渡す。`eval` やコマンド文字列の組み立てをしない）。`detect-dev-worktree.sh` と同じ脅威モデル。
