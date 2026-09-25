# plugin eval（出力品質の回帰）の運用

CLAUDE.md「品質チェック」から、ケースを書く・足す・結果を読むときにだけ要る部分を移したもの。CLAUDE.md には起動口と鮮度ゲートだけを残している。

`evals/runner.py`（スキル選択の回帰）が「正しいスキルが選ばれるか」を測るのに対し、こちらは「スキルが効いて回答が良くなったか」を**プラグインあり / なしの 2 アーム**で測る（Δ = with − without。judge は LLM 3 票の多数決）。ケースは `<plugin>/evals/<case>/prompt.md` + `graders/*.md`（`cd <plugin> && claude plugin eval init --bare <case>` で雛形。プロンプトは**自然言語で書く** — スラッシュコマンドは headless で落ちる）。実行は必ず起動口を通す:

```bash
bash .claude-plugin/scripts/plugin-eval.sh <plugin>            # 既定: --no-publish --trust-plugin --threshold 0.8、runs は tool 既定の 3
bash .claude-plugin/scripts/plugin-eval.sh <plugin> --runs 1   # 追加引数はそのまま渡る
```

- **pre-commit が鮮度を強制する**: ケースを持つプラグインで `skills/ commands/ agents/ references/ evals/` に staged 変更があると、起動口が残した `.last-eval` の指紋（入力ファイル内容の cksum）と現在の指紋が一致し、かつ exit 0 でなければ commit を止める。**pre-commit 自身は eval を回さない**（paid。1 ケース 2 アーム × 3 runs で実測 $1 前後 / 2〜3 分）。迂回は `PLUGIN_EVAL_SKIP=1 git commit ...`
- **結果はスコアより evidence を読む**。with が 1.00 に張り付くのは「壊れていない」の意味しかなく、改善点はケースが落ちたときの judge 向け本文にしか出ない。grader は **1 基準 1 ファイル**に分ける（どの基準で落ちたかが見えないと直せない）。スキル固有の作法（採否フロー等）を基準に入れると baseline が構造的に負けて Δ が質の差を隠すので、質を測りたいケースからは外す
- **ケースを書くときの実測済みの落とし穴**（bdd-spec / claude-meta のケース作成で約 $19 使って分かった分）:
  - **fixture はプロンプトに埋め込む**。`case.yaml` の `context.add_dirs` で渡したディレクトリは、サンドボックスの cwd の外に置かれ Read / Glob とも Permission denied になった（両アームとも「ファイルに到達できない」で全 grader FAIL）。cwd 内の状態（`.claude/indie/` 等）を前提にするスキル（issue-workflow の大半）は `scaffold_script` 無しでは測れない — 今はケースを置いていない
  - **閾値は起動口が 0.8 に下げている**。tool 既定の 1.0 は全 run・全 grader の通過を要求するが、judge は同じ基準で票が割れる（PASS PASS PASS の次の run が FAIL PASS FAIL）。0.8 は weight 1 の grader が 3 run 中 1 回落ちるのを通し、weight 2 の grader が全 run で落ちる退行を止める水準
  - **「〜を捏造していない」型の grader は、fixture に正当な指摘の余地があると機能しない**。bdd-spec では judge がテンプレ書式への正当な指摘（アンカー不一致）を「無い欠陥の報告」と読み、基準の文面を 5 回書き換えても全 run で 3 票とも FAIL だった（同じ基準・同じ回答を手元の haiku に渡すと PASS）。**judge の判定理由は `--json` にも出ない**ので、落ち続ける grader は文面を直すより外す。claude-meta の同型 grader が機能しているのは、fixture が 3 ファイルで「存在するもの」が閉じているため
  - **Δ が 0 でもケースは無駄ではない**が、意味は「壊れていない」に限られる。bdd-spec に置いたケースは baseline も仕込んだ欠陥を全部拾い（with 1.00 / without 1.00）、利用頻度の低さもあって削除した。プラグインの効果を見たいなら、baseline が落とす基準（claude-meta の「既存拡張を第一推奨にする」は without が 3 回中 1 回落とす）を含める
- **ケースを足す前に、そのプラグインの利用頻度と見込みコストを並べる**。ケースを持つプラグインは以後、入力を変える commit のたびに約 1.5〜3 USD / ケースを払う。ほぼ使っていないプラグインには置かない（bdd-spec に置いて外した実例）。起動口は実行前に概算を stderr へ出す
- **定期実行しない**。回帰テストなので走らせる意味があるのは入力を変えたときだけで、それは pre-commit が捕まえる。CI にも載せない（子 claude が自分の認証で走る）。`results/` は gitignore なので**別マシンでは記録が無い** — そのマシンで初めて入力を変えたときに 1 回回す（typo 修正なら迂回でよい）
- 実測の効用: 初回のケース 1 本で「サンドボックスでは `references/` を Glob で探せず、正本を読まずに推敲していた」を検出した（writing-polish 0.10.1）。スコアではなく evidence 冒頭の自己申告に出ていた
