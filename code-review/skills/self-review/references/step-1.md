### 1. diff 収集とコンテキスト準備

**Step 1 と 1.4 は 1 つの Bash 呼び出しにまとめる**（GitHub issue #147）。間に LLM の判断が挟まらない — 後段は前段の**出力を読んで決める**のではなく、同じシェルの変数とファイルを使うだけなので、分けると往復ぶんの `cache_read` を払うだけになる。**1.7 の機械層はここに含めない**（理由は 1.7 側に記載）。

```bash
# 所要時間計測の開始マーカー t0 を記録（Step 6.4 の payload で使用）。
# 以降 t1（一括発行の直前）/ wave --explorer（explorer 回収直後）/ wave（agent wave 回収の直後・毎回）/ t2（レポート出力直後）を
# 同じスクリプトで追記する。パス導出・区間の意味の正本: orchestration-measurement.md `## 13.1` `## 14`
# 1.4 で「中止する」を選んだ回は同じスクリプトの discard で打点ファイルを捨てる
# （publish しない回を Stop hook が「publish 漏れ」と拾わないように / #247）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" start

# base branch: 引数 → このブランチを作ったときの reflog（統合ブランチから切ったなら統合ブランチ）→
# default branch の順で決める（正本: scripts/lib/base-branch.sh / GitHub issue #274）
BASE_ARG="<引数で指定された base branch。指定が無ければ空のまま>"
# GitHub issue #313。シングルクォートで埋める（値の検査はシェルの展開の後なので、`$(…)` を評価させない。値に `'` があれば渡さない）
SINCE_ARG='<引数の --since= の値。無ければ空のまま>'
PRIOR_ARG='<引数の --prior-findings= の値。無ければ空のまま>'
BASE_OUT=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/lib/base-branch.sh" ${BASE_ARG:+"$BASE_ARG"})
printf '%s\n' "$BASE_OUT"
BASE=$(printf '%s\n' "$BASE_OUT" | sed -n 's/^base_branch=//p')

if [ -n "$BASE" ]; then
  # diff を $DIFF_FILE に保存し、シグナルダイジェストのみ stdout に出す
  # （`--staged` 指定時はこのコマンドの最後（継続行の後ろ）に --staged を足す。`--staged` の回は --since-tree を渡しても無視される）
  # 条件付きの引数は 1 語ずつ書く（zsh は展開を語に分けないので、`${X:+--flag "$X"}` は 1 語になる）
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh" --base "$BASE" \
    ${SINCE_ARG:+--since-tree} ${SINCE_ARG:+"$SINCE_ARG"} ${PRIOR_ARG:+--prior-findings} ${PRIOR_ARG:+"$PRIOR_ARG"}

  # Markdown 推敲の起動判定の材料（`## md-polish`。md の散文の追加・変更行数と writing-polish の有無）。
  # `--staged` 指定時は `--base "$BASE"` を `--staged` に置き換える
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/md-prose-lines.sh" --base "$BASE" --count

  # Step 1.4 の重複検出。**`--embed` のときはこの行を落とす**。triage-signals.sh が書いた
  # diff ファイルを読むので**この順序である必要がある**（パス引数は要らない / 自力導出する）
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-recent-review.sh" --skill code-review:self-review

  # 同じファイルを触った過去の merged PR のレビューコメント（GitHub issue #286）。triage-signals.sh が
  # 書いた core の一覧を読むのでこの順序。コメントがあったときだけパスを 1 行出す
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/fetch-past-reviews.sh" --base "$BASE" --save

  # 前回の self-review で修正を選んだ指摘のうち、今回の diff に入った分（GitHub issue #298）。
  # `--prior-findings` の分も合わせて出す（#313）。triage-signals.sh が書いた diff を読むのでこの順序。
  # 該当が無ければ何も出さない
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/prior-fixes.sh" match ${PRIOR_ARG:+--extra} ${PRIOR_ARG:+"$PRIOR_ARG"}
else
  echo "FATAL: base branch を特定できない（後続 5 本はスキップした）"
fi
```

**`fetch-past-reviews.sh` がパスを出したら、Step 4 の共通ブロックに `past_reviews_file=<そのパス>` として入れる**（読み方の規約は reviewer-common.md「過去 PR の指摘」）。何も出さない回（コメント 0 件・GitHub に届かない repo）は入れない。`skip:` の 1 行は欠損観点ではないので `missing_coverage` に記録しない

**`## prior-fixes` が出たら（前回の指摘への修正 / GitHub issue #298）** → Read `${CLAUDE_PLUGIN_ROOT}/references/prior-fixes-guide.md` の 1 節。範囲を絞った回でもこの行は検証済みにせず、その観点の reviewer に割り当て、**reviewer と specialist のプロンプトにだけ** `prior_fixes:` としてインラインで渡す（共通ブロックに入れない。共通ブロックは skeptic にも届く / #313）。`--prior-findings` の分もこの節に合流している（出なければ読まない）

**`set -e` を張らないこと**、そして**分岐を `[ 条件 ] && コマンド` で書かないこと**（どちらも CLAUDE.md Gotchas の ERR trap family）。base が決まらないとき `base-branch.sh` は exit 2 を返すので、`set -e` 下では `BASE_OUT=$(...)` の行でシェルごと落ち、**以降の 5 本を実行せずに終わる**。`if` なら BASE が空でも 0 で終わり、`FATAL:` の 1 行が出力に残る。

`base_source=` が `reflog` なら、このブランチを作った起点（統合ブランチ等）を base にしている。`default` なら起点が分からず default branch に倒した — 統合ブランチから切ったブランチでは、統合ブランチの他の変更まで対象に混ざるので、Phase 0 の出力にこの 1 行を載せる。

`FATAL:` が出たら base branch を特定できていない（後続 5 本は走っていない）。ユーザーに base branch を確認してから呼び直す。

**diff 全文をメインコンテキストに載せない。** `triage-signals.sh` が diff（コミット済み + 未コミット）をファイルへ保存し、Phase 0 に必要な**事実だけ**を compact に出力する。diff は reviewer / explorer へ**パスで渡す**（本文を転記しない。orchestration-guide.md `## 3.5`）。

出力セクション（`## meta` / `## size` / `## files` / `## hunks` / `## focus-signals` / `## red-flags` / `## surface` / `## explorer-signals` / `## agents-md` / `## issue-ids`）の意味と使い道の正本 → review SKILL.md `### 2`。self-review では `## issue-ids` はブランチ名から抽出され、`## meta` の `base` は指定した base branch になる（ローカルの base が origin より遅れていれば `origin/<base>`）。あわせて出る **`diff_base=`**（diff の起点のコミット）を、共通ブロックの base ref と base 検算に使う（`git show <diff_base>:<path>` が diff の変更前と一致する。`base` の ref の先端は、ブランチを切った後に base が進むとずれる / orchestration-guide.md `## 3.5`）。**`## md-polish`**（`md_prose_lines=` / `writing_polish=`）は self-review だけにあり、Markdown 推敲の起動判定（Step 2.1）に使う。**`## decision-docs`**（`design_doc=` と決定系 doc の一覧）は決定系 doc の design-review 委譲の起動判定（Step 2.1）に使う。**`## delta`** は `--since` の回だけに最後の節として出る（読み方は下の `--since` の節）。

- **`size_tier`** はスクリプトが triage-guide.md `## 6.2` の帯定義を機械適用した値をそのまま使う（core = lock・生成物・テスト・doc を除いた実質規模。GitHub issue #96）。Phase 0 の構成テーブル・Step 6 レポート冒頭・Step 6.4 の `size_tier` に記録する
- **シグナルは事実であって判定ではない**。観点採否・体数は triage-guide が決める。ヒット数 0 の観点は出力に現れない＝条件不成立、と読む
- **`diff_file=` と `agent_ctx_file=` の値はパス文字列そのものを控えておく**（後者は Step 4 の共通ブロック書き出し先。**slug は不透明な cksum 値なので、控え損ねると復元できない**）（シェル変数は Bash 呼び出し間で消えるため、`$DIFF_FILE` として引き回さず実パスを毎回書く）
- **判断が付かない場合のみ** `bash "${CLAUDE_PLUGIN_ROOT}/scripts/diff-slice.sh" "<diff_file の実パス>" <path>` で必要なファイルの diff だけを読む（全文 Read はしない）
- **diff の起点は base branch の先端ではなく HEAD との分岐点**で、ローカルの base と `origin/<base>` のうち HEAD に近い方から取る（正本: `scripts/lib/diff-base.sh` / GitHub issue #253）。ローカルの base が遅れていて origin 側を使った回は stderr に `WARN: ⚠️ base:` が出る。止めずに続け、Phase 0 の出力にその 1 行を載せる
- **スクリプトが失敗した場合**は `git diff "origin/${BASE}...HEAD" --name-only`（取れなければ `"${BASE}...HEAD"`）と `--stat` でファイル一覧と規模を取り、triage-guide.md `## 6.4` のフォールバック構成に落とす。**diff 全文の Read はこの経路でも行わない**

`## size` の `total_files` が 0 なら変更なしとして終了。

`--staged` 引数が指定されている場合は `triage-signals.sh --base "${BASE}" --staged` を使う（`git diff --cached` のみが対象になり、未ステージの変更とコミット済みの差分は除外される）。

**`--embed`（他 plugin からの呼び出し）:**

`--embed` 引数が指定されている場合は、本 skill が他 plugin（例: feature-dev Phase 6）からプログラム的に呼び出されたと判断する。Step 7 の修正方針確認 AskUserQuestion と Step 8 の worktree teardown 連携を skip し、Step 6 のレポートをそのまま return する。呼び出し元側で findings を集約・後処理する前提。

**return してもターンを終えない**（指摘 0 件の回も同じ）。Skill tool で呼ばれた skill は subagent ではなく呼び出し元と同じ会話の中で動くので、marker を書いてツールを呼ばずに止まると、呼び出し元の手順ごとターンが終わる（writing-polish の embed で実際に起きた）。marker の後は同じターンのまま、呼び出し元の次の手順（feature-dev なら Phase 6 の Step 3 以降）を実行する。marker は呼び出し元が戻りを確かめるためのもので、完了の合図ではない。

return 仕様（**dual format**: 人間可読 markdown ＋ 機械可読 JSON、marker の位置、後方互換）の正本 → orchestration-optional-flows.md `## 15`。AskUserQuestion は呼ばない（呼び出し元の UX を阻害しない）。

**`--rereview`（修正を確かめる再レビューの申告）:**

直前のレビューの指摘を直したあと、直ったかを確かめるために回し直す回であることを申告する（feature-dev の G-V ループが渡す / GitHub issue #296）。**レビューの手順は何も変えない**。publish が transcript からこの引数を読んで payload の `invocation.rereview` に載せるので、SKILL から payload に書かない。retro は再レビューを真の空振り・報告 0 件率・歩留まりの主層から外し、反証・skeptic の `scope` スキップも初回と分けて数える — 0 件が望ましい回を初回と同じ母集団で数えると、1 回の再レビューで ⚠️ の有無が入れ替わる。

**付けるのは利用者か呼び出し元 skill の手順だけ**。利用者が手で直したあとの回し直しは、利用者が slash の引数か発話（「再レビュー」）で指定する。**利用者が「self-review 回して」としか言っていない回に、Skill を呼ぶモデルが前回の構成から推して足さない**（実測: 素の「回して」に `--rereview` を足した 3 回のうち 2 回は修正確認ではなく、主層から外れた / GitHub issue #300）。publish も、利用者の発話を挟んだ `Skill` の `--rereview` は、その発話が再レビューを明示していなければ申告として読まない

**`--since=<tree>` / `--prior-findings=<path>`（再レビューの範囲を delta に絞る / GitHub issue #313）:**

直前の修正の前（feature-dev の G-V ループ）やレビューした時点（Phase 6.9）の作業ツリーの tree を受け、その後に変えた分（delta）を主な対象にする。delta は Step 1 の triage-signals.sh が作る。対象のファイルは、diff 全体に入るファイルと、起点の tree から変わったファイル（base の状態へ戻したファイルを含む。いま未追跡のものは除く）。`--prior-findings` は前回の対象（`[{file, line, focus, title}]`。形の正本は prior-fixes-guide.md の 4 節）で、`## prior-fixes` に合流する。**付けるのは利用者か呼び出し元 skill の手順だけ**で、利用者が「self-review 回して」としか言っていない回にモデルが推して足さない（`--rereview` と同じ / #300）。

- Step 1 の `## delta` が `scope_mode=delta` なら → Read `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` の `### 6.5`（観点・体数・空の delta の扱い）。`scope_mode=full` と `fallback=` が出た回は、理由を Step 6 の **範囲** の行に書いて diff 全体で続ける（`pr` / `staged` / `bad-tree-id` / `tree-not-found` / `prior-findings-unreadable` / `delta-diff-failed`）
- `--focus` / `--exclude` と一緒に渡されたら: 読む範囲は delta、skeptic と反証は従来どおり `scope` でスキップする。`--focus` は指定した観点と前回の対象の観点だけを規模キャップの外で起動し、`--exclude` は指定した観点を外して残りを 6.5 の規則で決める

**`--focus` / `--exclude`（同一セッションでの重複レビュー回避）:**

同一セッションで既に reviewer agent を走らせた後（コミット前並列レビュー等）に self-review を再実行する場合、既検証の観点を再報告しないよう以下の引数でスコープを制御する。**付けるのは利用者か呼び出し元 skill の手順だけ**（feature-dev の G-V ループは付けない — `--since` / `--prior-findings` で絞る / #313）で、利用者が「self-review 回して」としか言っていない回に、Skill を呼ぶモデルが前回の構成から推して足さない — 絞った観点の外は誰も見ず、最小保証の reviewer も起動しない（実測: 素の「回して」に `--focus` を足した 4 回は反証がどれも `scope` でスキップされ、うち 1 セッションでは利用者が後から全観点で回し直した / GitHub issue #300）。前回の指摘が再び出るのは、観点が欠けたまま終わるより安いので、迷ったら全観点で回す:

- `--focus <観点>`: レビュー対象を特定の観点に絞る（例: `--focus "comment-accuracy"`, `--focus "type-design"`）。複数指定はカンマ区切り
- `--exclude <観点1,観点2>`: 既に他 agent でカバー済みの観点をスキップする
- **値は triage-guide.md `## 3` の観点判定表のキー（＝ `${CLAUDE_PLUGIN_ROOT}/references/prompts/focus/<key>.md` のファイル名）に限る**（例外は `--exclude md-polish` と `--exclude design-review` で、それぞれ Markdown 推敲と決定系 doc の design-review 委譲を止める。観点ではないので `--focus` には書けない）。**`md-polish` と `design-review` はスコープの絞り込みに数えない** — self-review の各 Step ファイル（1・2・4.7・4.8・4.9）と参照先で「`--focus` / `--exclude` でスコープを絞った・絞り込んでいる」と書く条件（規模キャップの除外・skeptic と反証の `scope` skip・4.7）は、この 2 つ以外の値を 1 つ以上指定した場合だけを指す。この 2 つだけを `--exclude` した回は、それを止める以外は引数なしと同じに扱う。語彙外の値（例: `migration-safety`）はその reviewer を起動せず、レポートの「⚠️ 欠損観点」に `語彙外の focus: <値>` と書く（payload の `missing_coverage` には入れない。識別子の語彙検証で publish が落ちる）。黙って捨てると、呼び出し側の名前違いが「その観点は問題なし」に見える。**`--focus` の値が語彙外だけのとき**（`md-polish` / `design-review` を除いて語彙内の観点が 1 つも残らない）も絞り込みとして扱い、全体レビューに倒さない — plan は `scope=focus` で reviewer の行を出さず（前回の対象の行だけは残る）、レポートは「⚠️ 欠損観点」の `語彙外の focus` だけになる。全体に倒すと、名前を書き違えた呼び出しが規模で絞った全体レビューになり、頼んだ観点を見ていないことが見えなくなる（GitHub issue #388）

適用先:
- **Phase 0 (Step 2)**: `--focus` 指定時は該当観点の reviewer のみ構成する（最小保証の reviewer-bugs / reviewer-claude-md も `--focus` に含まれない限り起動しない）。`--exclude` 指定時は該当観点の reviewer を構成から外す。**例外は Step 1 の `## prior-fixes` の行**（前回の指摘への修正。`--prior-findings` の分を含む）で、絞り込みの外に置く
- **reviewer 起動時 (Step 4)**: 各 reviewer プロンプトに以下を注入する

  ```
  review focus: {{ focus or "全件" }}
  already verified (do not re-report): {{ exclude or "none" }}
  ```

  （`md-polish` と `design-review` は観点ではないので `exclude` の値から外して注入する）

**`--spec <path>` / `--spec=<path>`（仕様ファイルの明示 / 他 plugin からの呼び出し向け）:**

呼び出し側が仕様ファイル（BDD `spec.md`・design doc など）のパスを渡したときは、Step 2.2 の plan に `--spec <path>` で渡し（plan が仕様ソースに数えて spec-compliance を起動する）、その reviewer にパスを渡して Read させる（本文は転記しない）。session-context / Issue / knowledge が無い repo でも、spec と実装の照合が起きる。ファイルが実在しなければ plan が `spec_missing` 行を出すので、レポートの「⚠️ 欠損観点」に `--spec のファイルが無い: <path>` と書く。`--focus` を併用する場合、`spec-compliance` が focus に含まれていなければ起動しない（呼び出し側が focus に入れる）

**コンテキスト収集（並列で実行）:**
- CLAUDE.md・規約ファイル: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`
- `.claude/session-context.md` と Issue / knowledge ファイルの探索（spec-compliance の reviewer に同梱するため）。**spec-compliance を起動するかは自分で決めない** — session-context（frontmatter の `branch` が現在のブランチと一致）と Issue ファイル（ブランチ名の Issue ID）は Step 2.2 の plan が自分で探す。knowledge は見つけたら plan に `--spec-source knowledge:<path>` で渡す
- プロジェクト特性シグナル（`package.json` の存在確認と主要依存の確認）

**次は Step 1.4**（SKILL.md に戻り、その見出しを見る）
