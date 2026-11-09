## Phase 1.4: BDD Spec Evaluation (bdd-spec:evaluate-spec handoff)

**Goal**: Phase 1.3 で spec.md を生成した場合、architect の入力にする前に品質ゲート（網羅性・トレーサビリティ）を通す。穴のある spec を真実として渡すと穴が実装に伝播するため、安いオラクルを実装前に挟む。

- `BDD_SPEC_PATH` がセット済み → `${CLAUDE_PLUGIN_ROOT}/references/plugin-handoffs.md` の「Phase 1.4」を読み、その手順（`bdd-spec:evaluate-spec --embed` 呼び出し → 🔴 critical があれば spec を自分で直して 1 回だけ再評価し、残っても止めずに Phase 7 のサマリへ回す。🟡 以下は情報提示のみ → fallback）。**利用者には聞かない**に従う

**次は Phase 1.5**（SKILL.md に戻り、その見出しの入口の条件を見る）
