---
name: doc-sync
description: >
  repo の文書（仕様書・規約・ADR）とコードコメント・実装・決めたことの整合を確かめ、食い違いと文書への未反映を文書の行を引いて一覧にし、文書とコメントの側を直す。
  トリガー: 「文書整合」「仕様書とコードコメントの整合性を確認」「仕様書に反映されているか」「doc sync」「/doc-sync」
  引数: [--base <ref>] [--issue <path>] [--report-only]
effort: high
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Edit
  - Agent
---

# Doc Sync

実装の途中で決め直した挙動が、仕様書・規約・コードコメントのどこかに古いまま残っていないかを、commit 前・Issue を閉じる前に見つける（GitHub issue #365）。レビュー（code-review の spec-compliance）とは別に、いつでも単独で回せる。照合の規則はレビューと同じ正本を使う（下の DOC-SYNC 区間）。

コードを変えたあとに文書の更新が要るなら、承認を取らずに直す（2026-11-07 決定。直した箇所は一覧で報告し、作業ツリーの変更として残すので git で戻せる）。直さずに一覧に残すのは 2 種類: 実装の側を直すべき指摘（文書が正しく、コードが違う）と、`--report-only` の回。

**パイプラインの原則**（`docs/pipeline-design.md`）: 採用 = ファネル（決定的な所在検出 → LLM の照合）/ 段階予算（`${CLAUDE_EFFORT}` で挙動の件数と探索の広さを決める）/ モデルルーティング（探索の agent は sonnet）/ 暴走ガード（agent は最大 3 体）/ 証拠ラダー（文書の行の引用を必須にする）/ 外部オラクル（`.claude/doc-checks.sh`）。不採用 = 2 軸スコア・確信度フィールド・敵対的独立検証（直す対象は文書とコメントだけで、直した箇所は全件を報告に出し git で戻せるので、絞り込みの層を置かない。指摘は全件出す）。

## 引数

- `--base <ref>`: 比べる起点。省いたら `auto`（`origin/HEAD` → `main` → `master`）
- `--issue <path>`: Issue ファイル。省いたら `.claude/session-context.md` の `issue_id`、無ければブランチ名の Issue ID（`[A-Z]+-\d+`）から `.claude/indie/*/issues/<ID>.md` / `.claude/linear/*/issues/<ID>.md` を、作業ツリーとメインのチェックアウト（`$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")`）の両方で探す。見つからなくても続ける
- `--report-only`: 一覧を出すだけで書き換えず、doc-checks も回さない（利用者が見るだけの回）

どの回も、一覧を出した後に**ターンを終えない**。呼び出し元（軽量フロー・feature-dev・git-commit-helper・issue-maintain）の手順の途中から呼ばれるので、そこで止まると呼び出し元の残りの手順が消える。単独で呼ばれた回は報告で終える

## Phase 0: 所在

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/doc_locate.py" --base <base> --list [--ref <Issue ファイル>] [--ref .claude/session-context.md]
```

`--ref` は実在するファイルだけ渡す。出力は `base=` の行と、`touched`（diff が触った文書）・`ref`（Issue・session-context が言及した文書）・`doc`（repo の文書の一覧）の TSV 行。種別は `spec`（パスの要素に docs / spec / adr / designs / features などを持つ文書）と `rule`（CLAUDE.md / AGENTS.md / CONTRIBUTING.md）。exit 2 は stderr を出して終える。

- `doc` の行が 0 件 → 文書を持たない repo。`DOC_SYNC_RESULT=skipped` / `DOC_SYNC_REASON=no-docs` を出して終える（何も読まない）
以下の `<base>` は、出力の `base=` の行の値（`auto` を解決した後の ref）。

- 分岐点から作業ツリーまでの変更（`git diff --name-only "$(git merge-base <base> HEAD)"`。コミット済み・staged・未コミットを含む）と未追跡のファイル（`git ls-files --others --exclude-standard`）が 0 件 → `DOC_SYNC_RESULT=skipped` / `DOC_SYNC_REASON=no-diff` を出して終える（`<base>...` の three-dot は作業ツリーの変更を含まないので使わない。コミット前に回すので未コミットの変更が本体になる）

**完了基準**: `doc` の件数と変更ファイルの件数が分かっている。

## Phase 1: 変えた挙動を挙げる

diff（`git diff "$(git merge-base <base> HEAD)"` と未追跡のファイル）の hunk から、変えた挙動を 1 件 1 行で挙げる。キーにするのは、文書やコメントに書かれていそうな語: 識別子・フラグ・既定値・条件（どの画面・経路・状態のときか）・エラー文言・例外の扱い。あわせて、このセッションで決めたこと（会話で決め直した挙動）と、Issue ファイルの決定・スコープの記述を挙げる。

実行時の effort で範囲を決める。値は Bash の `echo "$CLAUDE_EFFORT"` で取り、空なら command 本文の「このセッションの effort」の行、それも無ければ `high`（SKILL.md は Read で読むので、本文の `${CLAUDE_EFFORT}` は展開されない）:

- `low` / `medium`: 挙動は変更行の多い順に 10 件まで。探す先は `touched` / `ref` の文書と、Phase 2 の Grep に当たった文書だけ
- `high`（既定）: 挙動は全件。`doc` の一覧全体を Grep の対象にする
- `xhigh` / `max`: `high` と同じ範囲で、Phase 2 の探索を挙動のまとまりごとに `model: sonnet` の agent に分ける（**最大 3 体**。全 Agent call を同じメッセージで発行し、全員の結果が届くまで Phase 3 へ進まない）。agent には挙動の行・文書の一覧・Grep のキーを渡し、当たった file:line と該当行を返させる。照合はメインが判定する

**完了基準**: 挙動の一覧（件数つき）と、決めたことの一覧がある。

## Phase 2: 突き合わせる

挙動ごとに、それを書いている文書（`spec` と `rule`。ADR は `spec` に入る）とコードコメント（変更したファイルと、その呼び出し元・呼び出し先）を Grep で探し、当たった節を Read する。`touched` の文書は、変更した行の節を節ごと読む。次の規則を全件に当てる。

<!-- DOC-SYNC:START -->
**決めたことが文書に入っているか**（照合元の文書がある回だけ見る）:

1. **決定の未反映**: Issue（本文とコメント）・PR 本文・session-context・このセッションで決めた挙動が、それを書くべき文書の節に無い。足りない決定を 1 文で示し、足す先の見出しを挙げる
2. **同じ節の古い説明**: 変更した行と同じ節（直前の見出しから、同じか上のレベルの次の見出しまで）に、変更後の内容と矛盾する説明が残っている。1 行だけ直して周りの文が古いまま、の型。矛盾する行を引用する
3. **文書と実装の食い違い**: 文書が述べる挙動（受入条件・規約・例外の列挙）が、diff の後のコードと違う。どちらの画面・経路・条件の話かが書かれておらず、別の実装と食い違って読める記述もここに入れる

**書き方**:

4. 各指摘に、文書の file:line と該当行をそのまま引用する。実装・決定の側も出典（file:line・Issue / PR のどの記述か）を添える
5. 旧の振る舞いを出典付きで書いた節（経緯・履歴・移行前の挙動・ADR の決定記録・CHANGELOG）は、今の実装と違っていても食い違いとして数えない。直し方は、その節を書き換えず「新しく決めたこと」に当たる節へ足す形にする（その節が無ければ、作る位置を示す）
<!-- DOC-SYNC:END -->

コードコメントについては、上の規則に加えて次の 2 方向を見る:

- **コメントと実装**: diff の中か近くのコメントが、変更後のコードと違うことを書いている
- **文書とコメント**: コメントと文書が同じ挙動を違うふうに書いている（片方だけ新しい挙動になっている）。どちらが正しいかは実装と決めたことで決め、古い側を直す案にする

**完了基準**: Phase 1 の挙動と決めたことの全件について、当たった文書・コメントの有無を判定した（当たらなかったものも「文書に記述なし」として数えた）。

## Phase 3: 文書の機械チェック

repo が `.claude/doc-checks.sh` を置いていれば回す（存在自体が opt-in。索引の同期・frontmatter の lint など、文書の決定的な検査を宣言する。契約は exit 0 = 緑 / 1 = 検出あり / 2 = 判定不能）。repo のコードとして実行するので、回す前に次の 2 つで分ける:

- `--report-only` の回 → 回さず、一覧の冒頭に `doc-checks: 未実行（report-only）` と出す
- `.claude/doc-checks.sh` 自体が今回の変更に入っている（Phase 0 の変更ファイルか未追跡に含まれる）回 → 回さず、`doc-checks: 未実行（doc-checks.sh 自体が変更に入っている）` と出す（承認を取らずに進むので、変更したばかりの repo のスクリプトを確認なしで走らせない。中身を確かめたら利用者が回す）

それ以外の回は次で回す（Bash の `timeout` は 600000）:

```bash
T=$(git rev-parse --show-toplevel)
if [ -f "$T/.claude/doc-checks.sh" ]; then ( cd "$T" && bash .claude/doc-checks.sh ); echo "doc_checks_rc=$?"; else echo "doc_checks=none"; fi
```

- `0` → 緑。一覧の冒頭に `doc-checks: green`
- `1` → 出力の検出を 1 件ずつ一覧に入れる（種別 `doc-checks`）
- `2`・それ以外・打ち切り → 一覧の外に `doc-checks: 判定不能（<出力の要点>）` と 1 行出す（緑として扱わない）
- `none` → `doc-checks: 宣言なし`

## Phase 4: 適用と報告

`--report-only` でなければ、文書とコメントの側を直す指摘を **承認を取らずに** Edit で直す（Phase 2 で出した直し方の案のとおり。直す前に該当の節を Read し直す）。直さずに一覧に残すのは次の 2 つ:

- 実装を直すべきもの（文書が正しく、コードが違う）。「実装を直す」と書き、ここでは直さない（実装の修正は呼び出し元の手順 — 実装 → 検証 — で行う）
- `doc-checks` の検出（どう直すかは検査の出力しだい）

直したら、直したファイルについて Phase 3 の doc-checks を回し直す（回した回だけ。赤なら直した内容を見直す）。

```
## 文書整合（doc-sync）
対象: 挙動 N 件 / 決めたこと K 件 / 文書 M 件（仕様書 a・規約 b）/ doc-checks: <green | red | 判定不能 | 宣言なし | 未実行>

| # | 種別 | 文書・コメントの行（file:line と引用） | 実装・決定（出典） | 直し方 | 状態 |
|---|------|------------------------------------|------------------|-------|------|

DOC_SYNC_RESULT=<clean | findings | skipped>
DOC_SYNC_FIXED=<直した件数>
DOC_SYNC_FINDINGS=<残った件数>
DOC_SYNC_REASON=<no-docs | no-diff | ->
```

- 種別は `決定の未反映` / `同節の旧説明` / `文書↔実装` / `コメント↔実装` / `文書↔コメント` / `doc-checks` のどれか
- 直し方は、足す・直した文をそのまま書く（文書の節の見出しと、足す位置の行）
- 状態は `直した` / `実装を直す` / `未適用（report-only）` のどれか
- 残った指摘（状態が `直した` でないもの）が 0 件なら `DOC_SYNC_RESULT=clean`（直した分があっても clean。doc-checks が未実行・判定不能でも clean にし、冒頭の `doc-checks:` の行でその状態を残す。呼び出し元はその行を報告に添える）
- 直した文書・コメントは作業ツリーの変更として残す（コミットしない）。呼び出し元がコミットに含める。単独で呼ばれた回は、直したファイルの一覧を報告の最後に添える
