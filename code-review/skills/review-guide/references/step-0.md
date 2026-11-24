<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @22cde26f -->
<!-- SSOT: code-review/references/review-guide-format.md#変異テストの提案 @7be3a9e1 -->
### 0. 入力確定と diff 収集

引数を解析する。**`--base <ref>` の値を `BASE_REF`、`--top N` の値を精読の上限 N（省略時 5）、`--walkthrough` の有無を `WALKTHROUGH`、`--hide-guide` の有無を `HIDE_GUIDE`（1 なら `WALKTHROUGH` も 1 にする）、残りの非オプション引数（PR 番号）を `PR_ARG` に入れる**。`--base` があれば base モード、無ければ PR モードに入る。N は 1〜5 に収める（範囲の外なら近い方の端に寄せ、数でなければ 5 に戻す。寄せたときはレポート冒頭に 1 行で書く）。

```bash
# PR モード（既定）: PR_ARG（省略時は現ブランチの PR）を解決する。--base 指定時は PR モードに入らない
if [ -z "$BASE_REF" ]; then
  META=$(gh pr view ${PR_ARG:+"$PR_ARG"} --json number,title,url,headRefName,headRefOid,baseRefName,body 2>/dev/null) \
    && PR_NUMBER=$(printf '%s' "$META" | jq -r '.number') || PR_NUMBER=""
fi
# base モード（--base 指定 / PR が特定できない）: base branch を決め、origin から取り直す。
# 決め方は 引数 → このブランチを作ったときの reflog（統合ブランチから切ったなら統合ブランチ）→ default branch
# （正本: scripts/lib/base-branch.sh / GitHub issue #274）。ローカルの base は早送りできるときだけ進める
if [ -z "$PR_NUMBER" ]; then
  BASE_OUT=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/lib/base-branch.sh" --refresh ${BASE_REF:+"$BASE_REF"})
  printf '%s\n' "$BASE_OUT"
  BASE_REF=$(printf '%s\n' "$BASE_OUT" | sed -n 's/^base_branch=//p')
fi
```

- `FATAL:` が出たら（PR も base も決まらない）、base branch を指定して呼び直すよう案内して終了する
- 出力の `base_branch=` / `base_source=`（`arg` 引数指定 / `reflog` このブランチを作った起点 / `default` default branch へのフォールバック）/ `base_refresh=` は Step 5 のレポート冒頭の「base」行と読み順の記録にそのまま使う

- **PR モード**（`PR_NUMBER` あり）: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh" --pr "$PR_NUMBER"` で diff 収集とシグナル出力を得る
- **base モード**（`BASE_REF` あり）: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh" --base "$BASE_REF"`。この場合 Step 1 の PR コンテキストは無い。`## meta` の `diff_base=`（分岐点のコミット）と、stderr の `WARN: ⚠️ base:` をレポート冒頭の「base」行に使う
- **diff 全文をメインコンテキストに載せない**。`triage-signals.sh` が diff をファイルへ保存し、`## meta` の `diff_file=` にパスが出る。**このパスの実値を控える**（シェル変数は Bash 呼び出し間で消える）

出力の各セクション（`## files` = 分類 + 行数 / `## red-flags` `## surface` = リスク信号 / `## hunks` = core の関数コンテキスト / `## focus-signals` = 観点判定ヒット）を読む。**diff 全文の Read はしない**。

**読み合わせで直してよいか（`FIX_OK`）を決める**。Step 6・7 で修正を入れてよいのは、diff の対象が今の作業ツリーそのものの回だけ:

- base モード → `FIX_OK=1`（diff は分岐点から今の作業ツリーまで）
- PR モード → 今の `HEAD`（`git rev-parse HEAD`）が `META` の `headRefOid` と一致するときだけ `FIX_OK=1`。diff は PR head のものなので、ブランチ名が同じでも手元が head と違えば（別のマシンから push して手元が古い・未 push のコミットがある・fork の同名ブランチ）、解説したコードと Edit する作業ツリーが食い違う。一致しない回は `FIX_OK=0` で修正は提案に留め、理由（HEAD が PR head と違う）をレポート冒頭に 1 行で書く

**ガイド非表示（`HIDE_GUIDE=1`）**: Step 1〜7 の工程は `WALKTHROUGH=1` の回と同じで、省くのは**表示とターンの区切りだけ**。精読の選抜・スレッドの組み立て・4 項目の執筆・読み順の記録（Step 5）・精読ごとの読解とレビュー観点への答え・修正（Step 6）・締めの判定（Step 7）を 1 つも飛ばさない。表示しない分、利用者が解説で見るはずだったもの（入れた修正の確かめ方と副作用・何で確かめたか・答えの出なかった問い）は締めに集めて出す。各 Step の差分はその Step に書く。

**完了基準**: `diff_file` の実パス・`size_tier`・見出しに使う `## size` の値（`total_files` / `total_added` / `total_deleted` / `core_files` / `core_lines`）・`## files` の分類済みファイル一覧・PR/base モードの別・`WALKTHROUGH` と `HIDE_GUIDE` と `FIX_OK` が確定している。PR モードでは `META` の `baseRefName` と `headRefOid` の実値を控えている（Step 7 の 4. で変異テストの `<ref>` を手元の `HEAD` ではなく PR head から求める。シェル変数は Bash 呼び出し間で消える）。`## size` の `total_files` が 0 なら「変更なし」で終了。

**次は Step 1**（SKILL.md に戻り、その見出しを見る）
