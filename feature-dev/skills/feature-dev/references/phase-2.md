## Phase 2: Codebase Exploration

**Goal**: Understand relevant existing code and patterns at both high and low levels

**Actions**:
1. Launch the N code-explorer agents specified by the Phase 1.7 configuration table in parallel (single message, multiple Agent tool calls). Agents always start in the background (CC 2.1.302+) and each result arrives later as a completion notification — **do not move on until every explorer's result has arrived**. Each agent receives:
   - Its assigned `focus` (similar-features / architecture-mapping / shared-modules / history-context / dependency-trace / layer-mapping)
   - Its target scope (specific directory / module / abstraction layer)
   - A request to return 5-10 key files to read

   **Focus templates**:
   - `similar-features`: "Find features similar to [feature] and trace through their implementation"
   - `architecture-mapping`: "Map the architecture and abstractions for [feature area], tracing through the code"
   - `shared-modules`: "Identify shared modules (`utils/`, `lib/`, `helpers/`) that this feature will touch and document their consumers"
   - `history-context`: "Use git log to understand how [area] evolved and surface prior decisions / abandoned approaches"
   - `dependency-trace`: "Trace upstream/downstream dependencies of [target module] across the codebase"
   - `layer-mapping`: "Map the UI / API / data layer separately for [feature area]"

2. Once the agents return, read all files identified by agents to build deep understanding
3. **結果をファイルに書く**（GitHub issue #427）: explorer の結果を作業ファイルに Write で書き、その絶対パスを `EXPLORATION_PATH` として Phase 4 へ渡す（Phase 4 の architect がこのファイルを読む。オーケストレーターの要約を prompt に入れるかどうかで、architect が explorer の辿った経路を使えるかが回ごとに揺れていた）。パスは次で決める（出力の `EXPLORATION_PATH=` の値。前の run の残りもここで消える — Write は読んでいない既存のファイルを上書きできず、立て直しで読むと古い結果が混ざる）:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/exploration-file.sh" path
   ```

   作業ツリーの中に置き、Phase 4 の architect が読み終えたら消す（phase-4.md の「探索結果の作業ファイルを消す」）。Phase 3 で止めた run のように Phase 4 に届かなかった残りは、次の run の Phase 2・Phase 4 か、Phase 5 Normal Mode の 2.（書き始める前）が消す。パスの正本は `scripts/exploration-file.sh` で、消す側も同じスクリプトの `clear` を呼ぶ。作業ツリーの外（`/tmp` など）に置かないのは、作業ディレクトリの外への Write が承認待ちで止まりうるうえ、background で走る architect の Read が拒否されると、探索結果が渡らないまま黙って進むため。消すのは、残すと未追跡ファイルとして Phase 5.5 の判定（未追跡ファイルの中身まで grep する）に要点の行が当たり、Phase 7 のコミットにも混ざりうるため。形は次のとおり:

   ```markdown
   # Exploration results

   ## <focus>（<対象の範囲>）
   - `<path>` — <要点（役割・見つかったパターン・この機能との関わり）>
   - ...

   ## missing_coverage
   - <失敗した explorer の focus と対象の範囲>（無ければ「なし」）
   ```

   - focus ごとに 1 節。explorer が返した重要なファイルを全件、パスと要点の 1 行で並べる（2. で読んで分かったことを要点に足してよい）
   - 本文はパスと要点に留め、ファイルの中身を写さない（architect は要るファイルを自分で Read する）
4. Present a summary of findings and patterns discovered

**Partial failure tolerance**: If individual explorers fail, continue with the remaining results. Record failed explorers in a `missing_coverage` list to surface in Phase 7, and write the same list into the `## missing_coverage` section of the exploration file (so the architect explores those areas itself).

**次は Phase 3**（SKILL.md に戻り、その見出しの入口の条件を見る）
