## Phase 5: Implementation

**Goal**: Build the feature (Normal Mode) or apply targeted fixes (Fix Mode)

### Mode Detection

Phase 5 has two modes — check the invocation context:

- **Normal Mode**: Triggered by Phase 4 completion. Implements the feature from scratch. 適用範囲で足切りした回は停止点の返信で入る（承認は停止点で済んでいるので Actions の 1. は通らない。2.（作業ファイルの clear を含む）以降は通る）。終えたら Phase 5.3 へ進む
- **Fix Mode**: 入口は 2 つ — Phase 6 の Generator-Verifier loop (Step 3) と、Phase 5.3 の赤（静的オラクルのエラー出力）。Applies only the flagged issues. **DO NOT START WITHOUT USER APPROVAL** is waived for Fix Mode (both loops are automatic; reaching the user-decision step happens at Phase 6 Step 4 / Phase 5.3 の暴走ガード).

### Normal Mode

**DO NOT START WITHOUT USER APPROVAL**

**Actions**:
1. Wait for explicit user approval. 承認を求めるメッセージは次の 2 つで構成する（設計と実装でメインモデルを分ける運用の切り替え点。Phase 5 に入ると承認待ちで止まる箇所はここしか無い）:
   - **設計の引き継ぎ要約**: 採用した設計案とその理由、Phase 3 Step 5 の設計契約（確定した前提 + ユーザー決定）、実装で触るファイルと build sequence を**本文として**書き出す。モデルを切り替えると、切り替え先は切り替え前のモデルの思考過程を読めない（API 仕様上、読める向きが決まっている）ため、実装に必要な判断は可視テキストに残っていないと失われる。Phase 4.5 で design doc を書き出した場合もそのパスを添えたうえで要約を省略しない
   - 末尾に次の案内を**必ずそのまま**添える:

   設計から実装へは**同じセッションで続けるのが既定**（実装は設計の推論を一次ソースのまま使える）。`/compact` は最後の手段 — 要約で決定が平らになり、新しい文脈がその決定について自信を持って誤る。

   > 🔀 **モデル切り替えポイント**: 設計（Phase 1〜4.8）と実装で別のモデルを使う場合は、**この承認に返信する前に**アプリのモデル選択で実装用モデルへ切り替えてください。切り替えた後の返信から、そのモデルで Phase 5 以降を実行します。切り替え先には上の要約（と design doc）だけが引き継がれるので、足りない判断があれば承認と一緒に書き足してください。
2. Read all relevant files identified in previous phases
   - 書き始める前に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/exploration-file.sh" clear` を実行する（Phase 2 の探索結果の作業ファイル。phase-2.md の 3.）。Phase 4 で消しているが、足切りした回は Phase 4 を通らないので、前の run が Phase 2 と Phase 4 の間で止まった残りがここまで来る。残すと未追跡ファイルとして Phase 5.5 の判定と Phase 7 のコミットに入りうる
3. Implement following chosen architecture. If the project has a test setup (a test runner and existing tests), Read `${CLAUDE_PLUGIN_ROOT}/references/testing-discipline.md` first and put tests at the **Test Seams** from the chosen blueprint
4. **承認した方針を実装中に変えるときは、書き換える前に止まる**（GitHub issue #319。承認は 1. の承認か、足切りした回の停止点の承認）: 承認した手段が効かないと分かった・別の手段に替える・承認した範囲（build sequence / 停止点の変更方針に挙げたファイルと挙動）の外まで広げる、のどれかに当たったら、承認した案が使えない理由（観測したもの: エラー・ドキュメント・コードの行）と、新しい案・触るファイルを示してターンを終え、返信を待ってから書き換える（通常のメッセージで止める。モデル切り替えの案内は繰り返さない）。承認は示した方針に対するもので、別の案には及ばない。実例では、足切りの停止点で承認された `dynamicParams = false` が全ルートの動的レンダリングで効かないと分かり、別の案（`notFound()` とデータ取得関数の戻り値）へ確かめずに切り替えた
5. Follow codebase conventions strictly
6. Write clean, well-documented code
7. Update todos as you progress
8. **実装を終えたら SKILL.md の Phase 5.3 の見出しに戻り、そこからも phase ごとにファイルを Read して進む**。Phase 6 の self-review は Phase 6 の手順（`--embed`・`review-snapshot.sh save`・G-V ループ）を通して呼び、Phase 6.7・6.9・7（読み合わせ）を飛ばさない（6.7 を self-review の Step 7 で代わりに済ませない。GitHub issue #350）

### Fix Mode

**Triggered by**:
- Phase 6 Step 3 G-V loop with the `target` rows printed by `gv-loop.py review` (`BLOCKER` any-confidence OR `CRITICAL && confidence ≥ 90` from `code-review:self-review` output; from the 2nd round on, only those inside the loop's delta)
- Phase 5.3 の赤: 静的オラクルのエラー出力。エラーが指す file:line を `target` 行として読み、エラーを解消する最小の修正を当てる（loop iteration は消費しない。往復の上限は Phase 5.3 の暴走ガード）

**Constraints**:
- **Scope is strictly limited** to the `target` rows' file:line locations
- 対象外の指摘（MAJOR / MINOR・CRITICAL < 90・`deferred` の行）は、同じファイルの近くにあっても直さない。Step 4 で利用者に出る。実測では各回で対象外まで直し（34 件・17 件）、その修正が次のレビューの新しい指摘になってループが収束しなかった（GitHub issue #310）。範囲外の変更は次の `gv-loop.py review` が hunk 単位で数え、Step 4 に場所を並べる
- The architect design chosen in Phase 4 must be preserved
- No scope expansion, no refactoring of unrelated code

**Actions**:
1. Read each flagged file at the indicated line range（Phase 5.3 から来た回はエラー出力が指す行）
2. Apply the reviewer's suggested fix (or a minimal equivalent that resolves the issue)（Phase 5.3 から来た回はエラーを解消する最小の修正）
3. If the fix requires design-level changes, escalate by launching `code-architect` with focus `delta-proposal` (wait for its result before applying) and **consume 1 loop iteration**（G-V ループから来た回だけ）. Otherwise apply directly with Edit. 適用範囲で足切りした回は architect を起動しない（基準にする設計が無い）。停止点で承認した方針と別の手段が要るなら、Normal Mode の 4. と同じく止まって確かめ直す（ループの状態はそのまま残し、返信の後に修正して 4. の戻り先へ戻る）
4. 戻り先は入口で決まる: G-V ループ（Phase 6 Step 3）から来た回は Phase 6 Step 3 へ戻る (do NOT re-run Phase 5.5 unless the fix is runtime-sensitive and effort ≥ `medium`)。ループの状態は書かない（次の `gv-loop.py review` が記録する）。Phase 5.3 の赤（静的オラクルのエラー出力）から来た回は Phase 5.3 へ戻ってゲートを再実行する（緑の行き先は phase-5.3.md の Step 3 が持つ。Phase 6 Step 3 には進まない）

**次は Phase 5.3**（SKILL.md に戻り、その見出しの入口の条件を見る。Normal Mode の終わり。Fix Mode から来た回は Fix Mode の 4. の戻り先に従う）
