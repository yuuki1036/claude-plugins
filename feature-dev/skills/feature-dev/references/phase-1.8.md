## Phase 1.8: プロジェクト宣言の必読 doc（fail-closed / explorer 0 体でも skip しない）

**Goal**: プロジェクトが「タスク種別 → 必読 doc」を宣言していれば、該当する doc を**全部**読み、Phase 3 grill と Phase 4 architect の入力にする。一部の doc だけを選んで渡すと、読まなかった doc の規約（例: 警告は設計システムの `<Alert>` を使う）を設計が破り、人間レビューまで見つからない（GitHub issue #233）。Phase 2 は explorer 0 体で丸ごと skip されるので、ここは独立 phase に置く。

1. 宣言を探す。`AGENTS.md` / `CLAUDE.md` をリポジトリ直下と、変更対象ディレクトリから直下までの各階層で探し、「必読」「must read」「required reading」や、タスク種別と doc パスを対応させた表・箇条書きを拾う:

   ```bash
   for f in AGENTS.md CLAUDE.md .claude/CLAUDE.md; do [ -f "$f" ] && grep -n -iE '必読|must read|required reading|読むこと' "$f"; done
   ```

   変更対象ディレクトリ配下の `AGENTS.md` / `CLAUDE.md` も同じ grep に掛ける（Phase 1 で分かっている範囲だけでよい）
2. ヒットした節を Read し、今回のタスクに**当てはまる行をすべて**選ぶ。1 つのタスクが複数の種別に当たる（UI 実装かつエラー表示など）ときは全行を採る。当てはまるか迷う行は採る側に倒す
3. 選んだ行が指す doc を全部 Read する。節の指定があればその節を読む

**Output**: `REQUIRED_DOCS=<doc パス / 節 / 当てはまった種別の一覧>` または `""`（宣言なし）。宣言が無ければ「必読 doc の宣言なし」と 1 行 notify して Phase 2 へ。宣言はあるが当てはまる行が無い場合も、その旨と見た種別を 1 行残す（黙って空にしない）。

`REQUIRED_DOCS` は Phase 3（grill の分岐）と Phase 4（architect 注入）に**全件**渡す。要約して一部だけ渡さない。

**次は Phase 2**（SKILL.md に戻り、その見出しの入口の条件を見る）
