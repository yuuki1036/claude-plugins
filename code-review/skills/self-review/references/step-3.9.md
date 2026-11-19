<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @22cde26f -->
<!-- SSOT: code-review/references/orchestration-guide.md#4 @5e6a3406 -->
### 3.9 AGENTS.md 階層動的選択（reviewer 起動前）

Step 1 のダイジェスト `## agents-md` に出ている**パス一覧**を reviewer プロンプトに渡し、agent 自身に Read させる（本文の転記はしない — 既にディスク上にあるので体数ぶんの複製がそのまま消える。orchestration-guide.md `## 3.5`）。ヒットが 0 件なら no-op（後方互換）。

注入セクション名・探索ロジックの詳細: → orchestration-guide.md `## 4`

**次は Step 4**（SKILL.md に戻り、その見出しを見る）
