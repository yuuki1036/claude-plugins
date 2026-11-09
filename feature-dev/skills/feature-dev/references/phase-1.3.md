## Phase 1.3: BDD Spec Creation (bdd-spec plugin handoff)

**Goal**: bdd-spec が有効なら BDD `spec.md` を生成し、Phase 4 architect が読む真実にする（曖昧な Issue から実装が暴走する失敗を構造的に潰す）。未インストール・無効時は何もしない（後方互換）。

有効判定は同梱スクリプトで行う（user / project / local の settings を優先順位どおりに読み、`true` の明示値だけを有効とする。出力は `1` / `0`。以下の Phase 4.5 / 6 と worktree-flow も同じ）:

```bash
echo "BDD_SPEC_AVAILABLE=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" bdd-spec)"
```

- `BDD_SPEC_AVAILABLE=0` → **skip して Phase 1.4 へ**（1.4 は SKILL.md の入口の条件に従う。既存の Issue 解釈フローがそのまま動く）
- 初期リクエストに `spec=<path>` があれば生成せずそれを `BDD_SPEC_PATH` に採用し Phase 4 へ渡す
- それ以外で `BDD_SPEC_AVAILABLE=1` → `${CLAUDE_PLUGIN_ROOT}/references/plugin-handoffs.md` の「Phase 1.3」を読み、その手順（自動判定 → 該当時だけ `bdd-spec:create-spec` 非対話呼び出し → fallback）に従う。**利用者には聞かない**（BDD を使う repo・変更かをここで判定し、非該当なら 1 行報告して skip する。セッションを止めない）

**Output**: `BDD_SPEC_PATH=<path>` または `""`（未生成）。Phase 4 architect の "BDD Spec Injection" と Phase 1.7 の Issue context completeness 判定に使う。

**次は Phase 1.4**（SKILL.md に戻り、その見出しの入口の条件を見る）
