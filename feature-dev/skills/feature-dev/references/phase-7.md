<!-- 正本依存（SSoT pin）。`--since` / `--prior-findings` の効き方（delta を主に見る・前回の対象を戻す・`--focus` と併用したときのスキップ）と、delta が未追跡を含まないこと・観点を delta で選び直すことは、self-review SKILL.md「1.」と triage-guide.md「6.5」が正本。正本が変わったら Step 3.2 / Step 4 / 6.9 / Phase 7 の未追跡の扱いを確認して pin を打ち直す -->
<!-- SSOT: code-review/skills/self-review/SKILL.md#1 @77013dba -->
<!-- SSOT: code-review/references/triage-guide.md#6.5 @82b2674b -->
<!-- 正本依存（SSoT pin）。Phase 7 の 4. の変異テストの分岐（承認の取り方・回し方・結果の 4 区分・前後の git status の突き合わせ）は code-review の review-guide-format.md「変異テストの提案」を要約したもの。正本が変わったら Phase 7 の 4. を確認して pin を打ち直す -->
<!-- SSOT: code-review/references/review-guide-format.md#変異テストの提案 @3c9ee376 -->
## Phase 7: Summary

**Goal**: 人間が変更を自分で読み、コミットや PR に進めるかを判断できる状態で渡す（GitHub issue #290）。この時点で要るのは要約ではなく読み順なので、読み順と読み合わせ（精読を 1 件ずつ解説し、見つけた修正をその場で入れる）は `code-review:review-guide` に任せ（読み合わせは必須。利用者が選ぶのはガイドを表示するかだけ）、feature-dev からは review-guide が diff から知りえない申し送りだけを短く添える。読み合わせで入った修正は Phase 6 の self-review も Phase 6.9 の確認も通らないので、締めの判定で self-review にもう一度通してから終える。変更ファイルを列挙するだけの独自サマリは、どこから読むか・どこが難所かを伝えない。

**Actions**:
1. Mark all todos complete
2. **申し送り**（feature-dev だけが持つ情報。該当する項目だけ出し、無い項目は行ごと省く）:
   - **足切り** (適用範囲): 足切りした回だけ。当たった項目と、Phase 1〜4.8 を飛ばしたこと。実装中に承認した方針を変えた回は、変えた理由と承認を取り直した新しい案
   - **設計契約** (Phase 3 Step 5): ユーザーが決めたことと、未決のまま残したこと（いつ・どこで決めるか）。契約が明示的に確認されなかった回（`askUserQuestionTimeout` で自動続行）はその旨
   - **探索の欠損** (Phase 2): 失敗した explorer の `missing_coverage`
   - **静的オラクル** (Phase 5.3): 緑以外で進んだ回だけ。書く文言と、回し直した回の経路の添え方は phase-5.3.md の Step 3「緑以外で進んだ回の記録」に従う
   - **動作確認** (Phase 5.5): `UI_VERIFY_RESULT` が `pass` 以外の回（`skipped` / `blocked` は `UI_VERIFY_REASON`、fail を承知で進めた回は fail したケース、手動の回は「手動確認待ち」か返ってきた結果、実行しなかった回はその理由）、`pass` でも `UI_VERIFY_UNCOVERED` が `none` 以外の回はその値、self-lock で Phase 5.5 を飛ばした回はその旨。Phase 5.5 の後に入った変更（Phase 6 の G-V ループの auto-fix・利用者の判断で入れた修正）に画面のファイル（Phase 5.5 Step 3 の定義）があれば「Phase 5.5 の後の変更は動作確認を通していない」と添える（3. の読み合わせで入る修正は 4. で扱う）
   - **G-V ループ** (Phase 6 Step 3 が走った回): `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gv-loop.py" summary` の反復回数・終了理由・auto-fix 件数・persisting（`remaining`）・`deferred`。終了理由が `regression` / `budget` / `deferred` / `manual` なら残った対象の fingerprint を目立たせる（人間の判断が要る）。範囲外の変更（`out_of_scope`）が 1 以上なら件数と場所。self-review が失敗した・Phase 6 を skip した回はその旨
   - **コメント精査** (Phase 6.7): 適用件数 / ID 除去件数、または「精査対象のコメント変更なし」
   - **BDD spec の未解消指摘** (Phase 1.4): 再評価後も 🔴 が残った回だけ、件数と内容を出す（Phase 1.4 は聞かずに進めるため、ここで初めて利用者に見える）
   - **レビュー後の変更** (Phase 6.9): 「**N ファイル・M 行（未レビュー）**」（ファイル名も並べる。「静的オラクルだけ回す」を選んで緑だった回は「（未レビュー・静的オラクルは緑）」。緑以外で進んだ回は「（未レビュー）」とし、静的オラクルの行に書く）/「確認できなかった」/「未追跡 N ファイル（self-review の対象外）」（`check` の `untracked_files=` が 1 以上。self-review をもう一度回した回も残す / GitHub issue #313）の回だけ。「なし」「再レビュー済み」は省く。値は Phase 6.9 の時点のもので、3. の読み合わせで入れる修正は含まない（それは 4. の 2 回目の self-review が見る）
   - **worktree** (Phase 4.8 で分離した場合のみ): worktree のパスとブランチ、後片付けは teardown / worktree-gc に委ねる旨
   - **Design doc follow-up** (Phase 4.5 で `DESIGN_DOC_PATH` がある場合のみ): 実装が完了したので、doc の frontmatter を `phase: target → current` に更新するよう案内する（実装と設計が乖離した箇所があれば doc への追記 or supersede も）。更新は design-doc プラグイン側の運用（ユーザー操作）に委ねる
3. **読み合わせの案内**（必須）: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" code-review` が `1` なら、読み合わせは**飛ばさない**（精読を選び、レビュー観点に答え、直せるものを直す工程がコードの質を上げるため）。利用者に選ばせるのは**ガイドを表示するかだけ**で、`AskUserQuestion` で聞く:
   - question: "読み順ガイドと精読の解説を表示する？（どちらでも読み合わせの工程は同じに通し、見つけた修正はその場で入れる）"
   - header: "ガイド表示"
   - options: "表示する (Recommended)"（読み順の概要を出した後、精読を 1 件ずつ解説する。難点がなぜ難点になったかとレビュー観点の答えを添え、見つけた修正はその場で入れる。入った修正は最後に self-review へもう一度通す）/ "表示しない"（同じ工程を表示せずに通し、結果は締めで受け取る。入った修正は同じく self-review へもう一度通す）

   どちらでも `Skill` tool で `code-review:review-guide` を `--base <BASE>` 付きで呼ぶ（読み合わせとして `--walkthrough` も付け、「表示しない」なら `--hide-guide` も付ける）。PR がまだ無い段階なので base モードで呼び、未コミットの変更まで読み順に入れる（PR モードは PR に push 済みのコミットしか見ない）。`<BASE>` は Phase 6 の self-review が冒頭で出した `base_branch=` の値を使う（同じ base から読ませる）。Phase 6 が走らなかった・値が分からないときは `--base` を付けずに `--walkthrough`（「表示しない」なら `--hide-guide` も）で呼ぶ（PR が無ければ review-guide が同じ順で base を決める）。**呼ぶ直前に** `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-snapshot.sh" save` を実行する（4. で読み合わせの間に入った変更だけを数えるため。Phase 6 の記録を上書きするが、その確認は Phase 6.9 で済んでいる）。

   **読み合わせは何ターンも続く**: review-guide は概要を出してターンを終え、利用者の「次」ごとに精読を 1 件ずつ解説し（1 精読 1 ターン）、最後に締め（精読の外で気になるところ → `変異テスト:` / `self-review 以降の変更:` / `次の一手:` の行）を出す。`--hide-guide` の回は概要と解説を出さずに全精読を 1 ターンで通し、締めから始まる（締めでは持ち越した確認と、精読の外の点の対応可否を 1 問ずつ聞くので、そこからも続く）。進め方は review-guide の手順に任せ、feature-dev は途中で次の一手やサマリを挟まない。4. 以降は締めが出てから進める
4. **読み合わせで入った修正を self-review に通す**（3. で読み合わせた回）: review-guide は判断の材料を出すだけで self-review を起動しないので、回すのは feature-dev。まず `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-snapshot.sh" check` で 3. の直前に `save` した時点との差を取り、`changed_files` が 1 以上なら下の `あり`、0 なら `なし` として扱う（読み合わせの間に入った変更だけを数える。Phase 6.7 のコメント適用と、Phase 6.9 で self-review を回さなかった変更は数えない — そちらは 6.9 で利用者が決めた）。`snapshot=missing` / `unavailable` のときだけ、締めの `self-review 以降の変更:` の行で分岐する（この行は直近の self-review の publish 以降の全変更を数えるので、6.7 / 6.9 の変更も `あり` に入る）:
   - `あり` → 締めの `次の一手:` が `決定的な検証` で始まるなら、self-review は回さずに Phase 5.3（静的オラクル）を同じ手順でもう一度回し、緑なら `次の一手:` の理由を 1 行添えて次の一手へ進む（緑以外なら Phase 5.3 Step 3 の扱い。review-guide が、読み合わせの変更は挙動を変えず解説で確かめ済みと判断した回 / GitHub issue #304）。それ以外（`self-review をもう一度` / 行が無い）なら `Skill` tool で `code-review:self-review` を呼ぶ。**引数は base だけ**（3. と同じ `<BASE>`。分からなければ引数なし）。例外は Phase 6 で `--spec=<BDD_SPEC_PATH>` を渡した回で、それも渡す（渡さないと spec-compliance reviewer が BDD spec を読まない）。Phase 6 Step 2 と違い `--embed` を付けない — 読み合わせの後は feature-dev が findings を集約しないので、self-review の Step 7（修正方針の確認と、修正した指摘の prior-fixes への記録）と 1.4 の重複検出をそのまま通す。`--focus` / `--rereview` / `--since` / `--prior-findings` も付けない（前回の指摘が直ったかを確かめる回ではなく、読み合わせで入った修正を含めて diff 全体を見直す回 / GitHub issue #300）。呼ぶ前に、1.4 で重複レビュー（header「重複レビュー」）の続行可否を聞かれたら（読み合わせで直した回し直しでは出ない。出るのは別の skill の記録と一致したときなど）、読み合わせの後の回し直しなので「続行する」でよい旨を 1 行添える。Step 6 の定型レポートと 6.4 の publish は Phase 6 Step 2 と同じく省かない・1 行に畳まない（GitHub issue #232 / #250）
   - `なし` → 回さずに次の一手へ
   - `不明（…）` → 読み合わせで修正を入れた（締めの「入れた修正」が 1 件以上）なら `あり` と同じ、入れていなければ `なし` と同じ
   - 締めにこの行が無い（`--walkthrough` を知らない旧版の code-review でガイドだけが出た。`--hide-guide` を知らない版は表示して進む見込みだが、未知の引数の扱いは旧版に定めが無い。締めの行が出ればこの分岐には入らない）→ ガイドの後に修正を入れたかで `不明` と同じ分岐

   **締めの `変異テスト:` の行で、次の一手の前に変異テストを提案するかを決める**（GitHub issue #307。`review-snapshot.sh check` の結果によらず、3. で読み合わせた回はすべて通る。上の分岐で 2 回目の self-review や Phase 5.3 を回した回はその後に 1 回だけ）:
   - 先頭が `提案する` → 行の理由・回し方・所要の目安をそのまま示し、回すかを通常のメッセージで聞いてターンを終える。`AskUserQuestion` にしない（無操作の自動続行（`askUserQuestionTimeout`）を承認と取り違えないため）。回しているあいだは作業ツリーを編集しないことも添える（道具によっては、変異体を作業ツリーのファイルへ直接書き込みながら回る）。**承認の返信が無ければ回さない**。承認されたら、`git status --porcelain` の出力を控えてから、回し方のコマンドをリポジトリのルートで Bash の `run_in_background: true` で起動し、終わるまで次の一手へ進まない（所要は前景の上限 600 秒を超えうる）。終わったら、exit code と出力（stdout と stderr）から結果を次の 4 区分のどれかで報告する（推測した道具の回は、道具の出力の集計で同じ区分に当てる）: `生存 N 件`（exit 1 で生存した変異の行がある。ファイル・行・変異の内容を出力どおりに並べ、未実行が残っていればその数も添える。exit 0 で全件を実行して生存が無ければ `生存 0 件`）/ `一部未実行`（exit 0 だが、集計に「上限で未実行 N」か「タイムアウト N」がある。生存が無くても「生存 0」と書かず、実行した数と未実行の数を書く）/ `未計測`（exit 0 で、対象行・変異が 0 個）/ `判定不能`（コマンドが失敗した・exit 2・途中で止まった。exit 1 で stderr に中断の FATAL があるものを含み、生存の行があってもこちら）。途中で止まった回は、stderr の「変異が当たったまま」の箇所（ファイル・行・元の内容）を利用者に示し、元に戻したと返されるまで次の一手へ進まない（変異が残ったツリーをコミットしない）。回す前と後の `git status --porcelain` を突き合わせ、増えたファイル（道具の出力）を報告に並べ、コミットに混ぜない（消すか gitignore するかは利用者が決める）。テストを足すかは利用者が決め、足した回は足したテストを走らせて緑を確かめてから次の一手へ（テストの追加は実行時の挙動を変えないので self-review は回し直さない。Phase 5.3 の宣言オラクルはテストを含まないことがある）。回さないと返されたら次の一手へ
   - 先頭が `不要` / `道具なし` → 聞かずに、行の理由を 1 行添えて次の一手へ
   - 行が無い（`変異テスト:` を出さない旧版の code-review / 締めが出なかった）→ 何もしない

   **読み合わせ以降の画面の変更を残す**（GitHub issue #306。3. で読み合わせて修正を入れた回はすべて。上の分岐で 2 回目の self-review を回した回も、`決定的な検証` で Phase 5.3 だけを回した回も同じ）: 3. の読み合わせ以降に入った変更（読み合わせでの修正・2 回目の self-review での修正）に画面のファイル（Phase 5.5 Step 3 の定義）があれば、次の一手に「読み合わせ後の変更は動作確認を通していない」と添える（Phase 5.5 はもう一度回さない）。変わったファイルは 4. の冒頭の `review-snapshot.sh check` が出す `<追加>\t<削除>\t<path>` の行（`snapshot=missing` / `unavailable` の回は締めの「入れた修正」）と、2 回目の self-review で直したファイルで見る

   **コミットの前に文書整合を通す**（2026-11-07 決定。3. で読み合わせた回も、5. の従来のサマリの回も同じ。上の分岐と変異テストを済ませてから 1 回だけ）: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" issue-workflow` が `1` なら、`Skill` tool で `issue-workflow:doc-sync` を `--base <BASE>`（3. と同じ。分からなければ付けない）で起動する。doc-sync は、コードの変更で更新が要る文書とコメントを承認を取らずに直し、残った指摘を一覧にする。応答の最後の行で分岐する:
   - 直した（`DOC_SYNC_FIXED=` が 1 以上）→ Phase 5.3（静的オラクル）をもう一度回す（文書とコメントだけの変更なので self-review は回し直さない）。次の一手に「doc-sync の文書修正は self-review を通していない」と添え、直した文書はコミットに含める
   - 残った（`DOC_SYNC_RESULT=findings`）→ 残った指摘（「実装を直す」・doc-checks の検出）を利用者に示し、直すかを聞く。実装を直すと決まったら Phase 5 に戻る
   - 指摘なし（`clean` / `skipped`。`0` で issue-workflow が無い回も）→ 結果を 1 行添えて次の一手へ
   - git-commit-helper は呼び出し元のフローから起動されたときに doc-sync を回さないので、feature-dev の回はここで回す（二重に回さない）
   - Phase 1.5 で Issue ファイルを読んだ回は、その更新履歴に `doc-sync: <DOC_SYNC_RESULT の値>` と 1 行足す（issue-workflow の issue-maintain は、この行があれば completed にするときに doc-sync を回し直さない）

   - 2 回目の self-review の後は、読み合わせも self-review も繰り返さない。最後に次の一手（コミット → PR）を 1 行添える
   - **コミット・PR は dev-workflow の skill で行う**: 利用者が次の一手どおりに進めるよう返したら、`bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" dev-workflow` が `1` なら、コミットは `Skill` tool で `dev-workflow:git-commit-helper`、PR は `dev-workflow:pr-creator` を起動する（command の `dev-workflow:commit` / `dev-workflow:pr` を経由せず、skill を直接呼ぶ）。`git commit` / `gh pr create` を直接打たない。`0` なら Conventional Commits 形式で論理単位に分けてコミットする。5. の従来のサマリの回も同じ
5. **従来のサマリ**（code-review が無効 / review-guide の呼び出しが失敗した回。review-guide を持たない旧版の code-review も含む）: What was built / Key decisions made / Files modified / Suggested next steps を出す。2. の申し送りはそのまま残す
6. **Event Bus publish (`feature:implemented`)**:
   - 完了直前に `feature:implemented` イベントを `.claude/events.jsonl` へ追記する。subscriber がいなくても無害（fire-and-forget）
   - **読み合わせ（3.）と 2 回目の self-review（4.）が終わってから**、Phase 7 の最後に 1 回だけ追記する。読み合わせは何ターンも続くので、review-guide を呼んだターンで先に publish しない（`files_changed` にも読み合わせの修正を入れる）
   - feature-dev は `hooks/lib/safe-hook.sh` を同梱しているため、`event_bus_publish` 経由で追記する（規約どおり 1 行 1 イベント）。`SAFE_HOOK_NAME` を `feature-dev` に上書きして publisher を識別する
   - payload は最小限の JSON: `{"feature":"<short description>","files_changed":<count>,"phases_completed":[...]}`
   - `feature` は 80 文字以内・ダブルクオート/バックスラッシュ/改行は除去。`files_changed` は今セッションで触ったファイル数（git diff の `--name-only` を `wc -l`）。`phases_completed` は実際に走った phase 番号の JSON 配列
   - **worktree 内で実行している場合は書き込み先をメインリポジトリのルートに固定する**（`event_bus_publish` は `CLAUDE_PROJECT_DIR` 未設定時に cwd 相対で書くため、worktree 相対に書くと teardown で worktree ごと消える。`--git-common-dir` は linked worktree からもメインの `.git` を返すので、その親がメインルート）
   - 実行コマンド例（`<...>` を Phase 7 のサマリ情報で埋めてから走らせる）:
     ```bash
     GCD=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
     MAIN_ROOT=${GCD:+$(dirname "$GCD")}
     source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null && \
       CLAUDE_PROJECT_DIR="${MAIN_ROOT:-$PWD}" SAFE_HOOK_NAME="feature-dev" \
       event_bus_publish "feature:implemented" \
       '{"feature":"<sanitized desc>","files_changed":<n>,"phases_completed":["1","2","..."]}'
     ```
   - 失敗しても Phase 7 全体は成功扱い（イベント送信は best-effort）

**ここで終わり**
