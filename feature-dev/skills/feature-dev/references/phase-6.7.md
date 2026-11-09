## Phase 6.7: コードコメント精査（comment-polish 委譲）

**Goal**: diff で追加・変更したコード内コメントを 2 観点（読み手に必要な情報か / 冗長表現の排除）で精査し、git 外の参照 ID を除去する。

**Why this phase exists**: Phase 6 は self-review を `--embed` で呼ぶため、self-review Step 7 のコメント推敲（B 系統）適用が skip され、標準フローの精査が feature-dev 経由では丸ごと落ちていた（GitHub issue #227）。Phase 6 の G-V ループ（Fix Mode）が**新しいコメントを追加しうる**ので、本 phase は Phase 6 の完了後に置く。

`code-review` 未インストールの回は SKILL.md の入口の条件で skip 済み。それ以外は必ず実行する — diff にコメント変更が無ければ comment-polish 側が「精査対象のコメント変更なし」を返して no-op で終わる。

**手順**: `Skill` tool で `code-review:comment-polish` を呼ぶ。入力は Phase 6 の self-review レポートで分岐する（今回の run で Step 3 が走り、G-V ループの再レビューが 1 回でも走った回 — `gv-loop.py summary` の `iterations` が 1 以上 — は下の 2 つ目に倒す。Step 3 が走らなかった回の summary は前の run の状態なので読まない。再レビューのレポートは delta 中心で、コメント推敲の提案も delta の分しか無い / GitHub issue #313）:

- `## コメント推敲提案` ブロックがある → そのブロックを一時ファイル（例: `.claude/.comment-polish-findings.txt`）へ書き出し、`--embed --from-findings <path>` で起動（comment-polish は再推敲せず全件適用）
- ブロックが無い（self-review の triage が `comment-accuracy` を起動しなかった / Fix Mode でコメントが増えた） → `--embed` 単独で起動（diff から精査して全件適用）

どちらも `--embed` を付ける（一気通貫フローなので適用の是非を個別に聞き返さない。結果は Phase 7 summary と最終 diff で可視化される）。

**結果の確認**: 適用件数と ID を除去した行（file:line）を受け取る。`git diff --stat` で**コメント以外のコード行が変わっていたら scope 逸脱として報告**し、その場合のみ Phase 5.3 を再走させ、緑なら Phase 6.9 へ（緑以外なら Phase 5.3 Step 3 の扱い。コメントのみなら再走不要）。呼び出しが失敗したら warning を出して Phase 6.9 へ進む。

**次は Phase 6.9**（SKILL.md に戻り、その見出しの入口の条件を見る）
