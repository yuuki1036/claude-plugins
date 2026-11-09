## Phase 4.5: Design Doc Export (design-doc plugin handoff)

**Goal**: Phase 4 の architect 比較とユーザー採用決定（プロンプト内で揮発する）を design doc として `.claude/designs/` に永続化する。後続の同領域開発の参照元・実装後の as-built 記録（`phase: target → current`）として再利用できる。design-doc 未インストール・無効時は何もしない（後方互換）。

```bash
echo "DESIGN_DOC=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" design-doc)"
```

- `DESIGN_DOC=0` → 本 Phase を skip して Phase 4.8 へ
- `DESIGN_DOC=1` → `${CLAUDE_PLUGIN_ROOT}/references/plugin-handoffs.md` の「Phase 4.5」を読み、その手順（AskUserQuestion → `design-doc:design-doc` の export 非対話呼び出し → fallback）に従う

**Output**: `DESIGN_DOC_PATH=<path>`（生成時）。Phase 7 サマリに含め、実装完了後の `phase: target → current` 更新案内に使う。

**次は Phase 4.8**（SKILL.md に戻り、その見出しの入口の条件を見る）
