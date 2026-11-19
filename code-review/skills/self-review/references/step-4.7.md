<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#8b @e63ec2b7 -->
### 4.7 観点カバレッジ・事後突合（メインコンテキスト / 常時実行・agent 追加起動なし）

Step 5 の直前に、**メインコンテキストで**（Agent は使わない・低コスト）Step 2.3 の起動前検算で確定した構成テーブルと実際に起動・完走した focus を突合し、差分を `missing_coverage` に追記する（orchestration-guide `### 8b`）。観点漏れの検出は Step 2.3 の起動前検算（`### 8a`）へ前倒し済みのため、**本フェーズで agent は追加起動しない**（v2.39.0。issue #69 の常時検査の意図は 8a で維持）。

**スキップ条件**: `--focus` / `--exclude` 指定時は意図的にスコープを絞り込んでいるため、その範囲外の観点は missing_coverage に記録するのみ。

**次は Step 5**（SKILL.md に戻り、その見出しを見る）
