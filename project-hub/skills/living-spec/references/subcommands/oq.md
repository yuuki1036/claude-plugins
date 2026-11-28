<!-- 正本依存（SSoT pin）。本ファイルは format-spec.md の、続く pin の節を言い換えている。正本の節が変わったら、その節を言い換えている箇所を確認して pin を打ち直す（`--update-ssot-pins` は repo 全体を一括で打ち直す） -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#3 @d620c24e -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#8 @bec4708d -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#9 @3d83e7f4 -->

## Phase 4: oq — OQ 台帳への追加 / 一覧

### 4a. `oq <text>` — 追加

1. 対象ファイルを Read する
2. W2 で `OQ<max+1>` を採番する
3. OQ 台帳の表に 1 行 append する（W5）:
   ```
   | OQ<n> | <text> | open | - | <TODAY> |
   ```
   - `関連 D#` は `-`（8 節: 空セルは半角ハイフン 1 文字）
   - `<text>` に `|` が含まれる場合は **`\|` にエスケープする**（8 節。9 節の正規表現はエスケープを許容する。生の `|` はセルを分割して段 1 の Critical になる）
4. W4 で `last_updated` を更新する
5. 報告:
   ```
   ✅ OQ<n> を追加しました（.claude/living-specs/<slug>.md）
     <text>

   open な OQ: <残数> 件
   ```

### 4b. `oq list` — 一覧

1. 対象ファイルを Read し、コメント除去後に OQ 行をパースする（9 節の正規表現）
2. **既定は `open` のみ**表示する。`--all` 指定時は `closed` も含める（closed 行は台帳に残っているので、フィルタは表示だけの話）
3. 0 件なら「open な OQ はありません」と報告する
4. 表で出す:
   ```
   ## Open Questions（open <n> 件 / 全 <m> 件）

   | OQ# | 問い | since | 経過 |
   |-----|------|-------|------|
   | OQ1 | ... | 2026-07-10 | 5 日 |
   ```
   `--all` のときは `status` と `関連 D#` の列を足す

> `oq list` は**読むだけ**。W1-W5 の書き込み規律は適用しない（`last_updated` も更新しない）。
