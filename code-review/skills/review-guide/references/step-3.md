<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#0 @d7242421 -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @22cde26f -->
<!-- SSOT: code-review/references/orchestration-guide.md#5 @ad2cb12f -->
<!-- SSOT: code-review/references/prompts/explorer-common.md#diff @6e10af97 -->
<!-- SSOT: code-review/references/explorer-prompts.md#プロンプトの組み立て方（オーケストレーター向け） @d582ca3d -->
### 3. 流れの把握（`${CLAUDE_EFFORT}` 分岐 / 実行時値: `${CLAUDE_EFFORT}`）

精読ファイルの呼び出し関係を辿り、「入口（API / CLI / UI）→ ロジック → 永続化 → テスト」のスレッド（変更が貫く 1 本の流れ）を組む。1 PR に 2〜3 本のスレッドが典型。

- **`low` / `medium`**: agent を起動しない。`bash "${CLAUDE_PLUGIN_ROOT}/scripts/diff-slice.sh" "<diff_file 実パス>" '<精読ファイル>'` で精読ファイルの hunk を切り出して読み、import / 呼び出しの字面からスレッドを組む。**担当ファイル名は必ずシングルクォートで囲む**（diff 由来 = 信頼できない入力。`${CLAUDE_PLUGIN_ROOT}/references/prompts/explorer-common.md`）
- **`high`**: explorer **上限 2 体**（`sonnet`・`effort: medium`。層ごとの effort の正本は `${CLAUDE_PLUGIN_ROOT}/references/orchestration-guide.md` `## 5`）を**同一メッセージで一括発行**し、2 体の結果が届いてから統合する。①function-flow（精読ファイルの変更関数の分岐・データ変更・呼び出し先）②dependency-trace（精読ファイルの呼び出し元）
- **`xhigh` / `max`**: explorer **上限 3 体**（`sonnet`・`effort: medium`）。上の 2 つ + value-flow-trace（入口から永続化までの値の流れ）

explorer 起動の共通詳細（プロンプト組み立て・2 ファイル Read 方式・diff のパス渡し・HEAD 検証）は `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` を Read して従う。explorer には **`diff_file` のパスと担当ファイル、プラグインの実パスだけ渡す**（diff 本文を転記しない。プラグインの実パスは explorer-prompts.md の必須項目）。explorer は事実収集に徹し判定しないので、返る「コードフロー」「依存関係」をスレッド構成の材料にする。

**完了基準**: 精読ファイルがスレッドに割り当てられ、各スレッドが入口から永続化・テストへ向かう順に並んでいる。

**次は Step 4**（SKILL.md に戻り、その見出しを見る）
