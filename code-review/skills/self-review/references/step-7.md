### 7. 修正方針の確認

**publish 済みかのガード（`--embed` / 指摘 0 件でも必ず実行する / GitHub issue #133）**: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" publish-pending` で 6.4 の脱落を捕まえる。**下の skip 条件はこのガードには掛からない** — 本ステップの他の判定（embed / 指摘件数）より前に、レポート出力後 1 回だけ無条件で実行する。**警告が出たら他を中断して 6.4 を先に完了させる**（計測ファイルはまだ残っているので、この時点なら損失なく復旧できる。修正作業に入ってから気づいた回は `duration_min` が欠測に倒れる）。**embed 経路こそ落ちやすい**（publish の後に呼び出し元の作業が続くため）ので、ここを条件分岐の内側に入れない。

**embed mode skip**: 引数で `--embed` が指定されている場合は、上のガードを実行したうえで本ステップの残りを skip する。Step 6 の markdown レポート → **Step 6.5 の構造化 JSON ブロック** → `[embed-mode: findings-only, no-prompt]` の 1 行 marker、の順で出力し、**ターンを終えずに呼び出し元の次の手順へ戻る**（Step 1 の `--embed` の節）。AskUserQuestion を呼ばないことで呼び出し元 plugin の UX を阻害しない。

**以下の修正方針フローは**、指摘事項（A 系統）・`## コメント推敲提案`（B 系統）・Markdown 推敲の提案のいずれかが 1 件以上ある場合に実行する。B 系統と Markdown 推敲は severity マトリクスを通らない別枠であり、**適用トリガーを A 系統の件数に従属させない**（A 系統 0 件でも別枠に提案があれば下の確認へ進む / GitHub issue #236）。すべて 0 件なら（上のガードを実行したうえで）「問題なし」で完了。

レポート全文を出力し終えた直後に **AskUserQuestion** で対応方針を確認する。該当する質問だけを含めて **1 回の呼び出し**にまとめる（別呼び出しに分けない）。**どの質問を入れるかは、publish（6.4）が出す `Step 7 の AskUserQuestion に入れる質問:` の行に従う** — payload の件数から機械的に決めたもので、自分の記憶で選び直さない（指摘の修正方針だけを聞き、Markdown 推敲の採否を落とした実例がある / GitHub issue #279）:
- 質問 1（A 系統の指摘が 1 件以上ある場合のみ）:
  - question: "指摘事項への対応方針を選択してください（コミット前の作業優先度を整理します）"
  - header: "修正方針"
  - options:
    1. label: "すべて修正" / description: "指摘事項をすべて今すぐ修正する"
    2. label: "BLOCKER/CRITICAL のみ" / description: "severity BLOCKER または CRITICAL の指摘だけ修正する"
    3. label: "このまま" / description: "修正はせず、このまま進む（コミットは git-commit-helper で行う）"
- 質問 2（`## コメント推敲提案` が 1 件以上ある場合のみ）:
  - question: "コメント推敲提案（N 件）を適用しますか？"
  - header: "コメント推敲"
  - options:
    1. label: "適用する (Recommended)" / description: "提案どおり comment-polish で全件適用する"
    2. label: "適用しない" / description: "コメントは現状のまま残す"
- 質問 3（Markdown 推敲の提案が 1 件以上ある場合のみ）: 文面と選択肢の正本は `md-polish-guide.md` の 6 節（確実のみ / 全件 / 適用しない）

各選択肢の後処理:
- **すべて修正**: 全指摘を一覧化し、ファイルごとにまとめて修正を実施する
- **BLOCKER/CRITICAL のみ**: 該当 severity の指摘のみ再表示し、ファイルごとにまとめて修正を実施する
- **このまま**: 完了（BLOCKER 指摘が 1 件以上残っている場合は「BLOCKER 指摘を残したままコミットしますか？」と AskUserQuestion で再確認する）

**コミットはこの skill でしない**（設計原則: コミットは Generator 側の `dev-workflow:git-commit-helper` が行う）。どの選択肢の後でも、コミットへ進むとき（「このまま」を選んだ・修正を終えた・利用者がコミットを指示した）は、呼び出し元のフロー（issue-workflow の軽量フロー等）があればその次の手順へ戻る。単独で起動した回は、使える skill に `dev-workflow:git-commit-helper` があれば `Skill` tool で起動する（`git commit` を直接打たない。protected branch へ直接コミットする運用のリポジトリでは `--no-protect` を渡す）。無ければ Conventional Commits 形式で論理単位に分けてコミットする

**修正した指摘を記録する（GitHub issue #298）**: 「すべて修正」「BLOCKER/CRITICAL のみ」で修正を終えたら、修正した指摘を次の self-review に渡す（`file` は repo のルート相対、`focus` は観点判定表のキー、`title` は指摘の要旨。扱いの詳細は `${CLAUDE_PLUGIN_ROOT}/references/prior-fixes-guide.md` の 2・3 節）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/prior-fixes.sh" record <<'JSON'
[{"file": "src/a.ts", "line": 42, "focus": "bug-detection", "title": "結果の種類 X のときだけ確認表示を下げる"}]
JSON
```

「このまま」の回と `--embed` の回は記録しない。

**コメント推敲（B 系統）の適用**: 質問 2 で「適用する」を選んだときは、（A 系統の指摘修正がある場合はそれを終えた後に）`## コメント推敲提案` ブロック（Step 6 で出力済み）を適用する。**質問 1 の回答（「このまま」を含む）とは独立に、質問 2 の回答だけで決める**。`code-review` がインストールされているので `Skill` tool で `code-review:comment-polish` を呼ぶ:
- 提案を一時ファイル（例: `.claude/.comment-polish-findings.txt`）に書き出してから、`comment-polish --embed --from-findings <path>`（+ 現在の base / `--staged` があれば同値）で起動する
- comment-polish 側は再推敲せず、渡した提案を**全件 Edit で適用**する（オプションなしで適用。提案が 0 件 or「該当なし」なら no-op）
- `comment-accuracy` が構成に無く `## コメント推敲提案` が出ていない回は本処理を skip する（質問 2 自体を出さない）

**Markdown 推敲の適用**: 質問 3 の回答だけで決める（質問 1・2 とは独立）。A 系統の修正とコメント推敲の適用を終えた後に、**メインが Edit で当てる**（writing-polish を呼び直さない — 呼び直すと推敲がやり直されてレポートと食い違う）。行が変わっていて当たらない提案の扱いと報告の書式は `md-polish-guide.md` の 6 節

**訂正の伝播前ガード（over-correction 防止 / GitHub issue #71）**: findings をコード/文書本文に**反映する前に**、その修正が依拠する load-bearing な事実主張を一次ソースで再確認する。**反証レイヤーが覆っていない指摘**（`反証: 未実施` の回の全件 / `⚠️ 反証未実施（対象帯外）` 付き）では、**load-bearing かの判定より先に一次ソースを引く** — 絞り込みの判定自体が指摘を書いた同じ 1 体の推論に乗っているため（#196）。判定ルール（repo で確認できる/できない主張の扱い・暫定入力の非伝播・1 箇所先行確認・複数観点の独立一致）の詳細: → orchestration-optional-flows.md `## 12`

**修正の指針（Fix the code, not the reviewer）**: 「分かりにくい」「誤解を招く」「意図が読めない」系の指摘に対しては、説明コメントを足して取り繕うのではなく、**コード・命名・型・構造そのものを直して解消する**ことを優先する。将来の読み手（半年後の自分・別コンテキストの Claude）も同じ箇所でつまずくため（Google eng-practices "Handling reviewer comments: fix the code, not the reviewer"）。

**次は Step 8**（SKILL.md に戻り、その見出しを見る）
