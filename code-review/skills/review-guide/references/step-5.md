<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/prompts/explorer-common.md#diff @6e10af97 -->
<!-- SSOT: code-review/references/review-guide-format.md @d04866a2 -->
### 5. レポート出力

`review-guide-format.md` のテンプレートで出力する。**ファイルは書かない**（セッション出力のみ）。base モードでは「主張 vs diff」「人間の判断が効く箇所」を「対象なし（ローカル diff）」と明記する。

**base モードのみ、出力の前に読み順を記録する**。editor に移らず、タスクの diff（分岐点から）を読み順どおりにペインで送れるようにするため（`/guide-diff` / GitHub issue #274 の続き）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/guide-order.sh" --diff-base <## meta の diff_base> \
  --base <base_branch> --source <base_source> \
  --read '<精読 1>' '<精読 2>' … --skim '<流し読み>' … --skip '<読まなくてよい>' …
```

- `--read` は**レポートの精読と同じ順**（実装の流れ順）、`--skim` / `--skip` もレポートの並びのまま渡す。群が空ならそのオプションごと省く
- **パスは 1 つずつシングルクォートで囲む**（diff 由来 = 信頼できない入力。Step 3 の diff-slice と同じ）
- `guide_order=` が出たら、レポートの末尾に `/guide-diff` の 1 行を添える（`review-guide-format.md`）。exit 2（`FATAL:`）ならその 1 行を出さず、レポートはそのまま出す（記録は付随物で、ガイド本体を止めない）

**`WALKTHROUGH=1` のときは（`HIDE_GUIDE=1` の回を除く。下の段落）、レポートの末尾に読み合わせの案内を 1 行出してターンを終える**（`review-guide-format.md` のテンプレート末尾）。利用者はまず概要を確かめるので、同じターンで精読 1 の解説に入らない。

**`HIDE_GUIDE=1` のときは、レポートを書き上げたうえで出力しない**（Step 4 の完了基準はそのまま満たす。レポートは Step 6 の読解の入力になる）。代わりに `review-guide-format.md` の「ガイド非表示の開始行」だけを出し、ターンを終えずに Step 6 へ進む。レポートの冒頭と末尾にしか置き場の無い注記（N を寄せた・`FIX_OK=0` の理由・`/guide-diff` の 1 行）と、PR モードの「人間の判断が効く箇所」は開始行に添えて出す（省くのは解説の読み物で、判断に要る情報ではない）。読み順の記録（base モード）は表示する回と同じく行う。

**完了基準**: レポートを出力した（`HIDE_GUIDE=1` の回は、書き上げたうえで開始行だけを出した）。base モードでは読み順を記録したか、記録できなかった理由が分かっている。読み順の記録の他に、ファイルへの書き込み・コメント投稿・コード修正を一切していない（修正は Step 6 から）。

**次は Step 6**（`HIDE_GUIDE=1` の回は同じターンで、`WALKTHROUGH=1` だけの回と利用者が精読の解説を頼んだ回は利用者の返信の後に入る。それ以外はここで終わり。SKILL.md に戻り、その見出しを見る）
