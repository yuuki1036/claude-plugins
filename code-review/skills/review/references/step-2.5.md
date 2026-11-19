<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @22cde26f -->
### 2.5. PR コンテキストの扱い

Step 1 が保存した `$PR_CTX_FILE` を PR コンテキストの**唯一の原本**として扱う（LLM による再構築・要約・編集は **禁止**：再現性と取りこぼし防止のため）。

- **Phase 0 のタイプ判定**: メインコンテキストが Step 1 で Read した内容を使う
- **reviewer への引き渡し**: 本文を転記せず**パスのみ**注入し、agent 自身に Read させる（バイト同一が保証され、転記リスクがゼロになる。orchestration-guide.md `## 3.5`）

スクリプト出力の構造（参考）: → design-notes/pr-context-format.md `## 3`

**次は Step 2.6**（SKILL.md に戻り、その見出しを見る）
