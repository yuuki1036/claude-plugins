### 1.7 機械層の先行実行（原則 8 / `.claude/review-oracles.sh` を置いたプロジェクトのみ・`--embed` では skip）

**agent の担当は「機械が決められないもの」に限る。** `bash "${CLAUDE_PLUGIN_ROOT}/scripts/run-oracles.sh"` を実行し、プロジェクトが宣言した機械層（lint / 型 / テスト等）を Phase 0 の**前に**通す。**出力が空なら宣言なし＝何も報告せず Phase 0 へ**（no-op を報告しない）。`status=green` は Step 6 レポート冒頭に `機械層: green (<elapsed>s)` を出すだけ。**`red` / `timeout` / `error` のときだけ** → Read `${CLAUDE_PLUGIN_ROOT}/references/machine-layer.md`（続行可否の確認・reviewer への「既知」の渡し方・計測規約の正本。設計判断は ADR-20260817170000）。`--embed` では呼び出し元が自分の品質ゲートを持つため skip する。

**この呼び出しを Step 1 にまとめないこと**（#147 で検討して見送った）。1.4 の重複検出には「中止する」＝ agent を 1 体も起動せず終える経路があり、機械層（lint / 型 / テスト）を前倒しすると**中止しても払い戻せない実行時間**を先に払うことになる。往復 1 回ぶんの `cache_read` より、中止経路の意味を保つほうが大きい。

**次は Step 2**（SKILL.md に戻り、その見出しを見る）
