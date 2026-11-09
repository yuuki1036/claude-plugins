<!-- SSOT: feature-dev/references/grill-protocol.md @f90e4324 -->
## Phase 3: Clarifying Questions (Grill)

**Goal**: Fill in gaps and resolve all ambiguities before designing — by **grilling**, not by dumping a flat question list

**CRITICAL**: This is one of the most important phases. DO NOT SKIP.

**Why grill instead of a list**: A flat list forces the user to answer everything at once — including questions the codebase already answers — and hides the dependency order between decisions. The grill protocol resolves the design tree one branch at a time, self-answering facts the code can answer and recommending an answer for the rest. Full protocol: `${CLAUDE_PLUGIN_ROOT}/references/grill-protocol.md`.

### Step 1: Enumerate candidate ambiguities

Review the Phase 2 codebase findings + original request. List every underspecified aspect: edge cases, error handling, integration points, scope boundaries, design preferences, backward compatibility, performance needs.

Always add these **premise checks** as candidates too (full rules: grill-protocol.md「採用する決定の前提を問う」):

- **設計システムとの対応**（UI を含むタスク）: 各 UI 要素が設計システム / `REQUIRED_DOCS` のどのコンポーネントに当たり、設計がそれに一致するか
- **引き継いだ決定の前提**: Issue / spec / living spec の既存決定（決定番号つきのもの等）が置いた前提が、今回の実装コンテキスト（コンテナ・画面種別・呼び出し経路など）でまだ成り立つか
- **標準規約との衝突**: 引き継いだ決定が `REQUIRED_DOCS` やプロジェクト規約とぶつからないか
- **説明とコードの食い違い**: ユーザーの説明が Phase 2 の調査結果と食い違っていたら、該当箇所（file:line）を示してどちらが正しいか聞く
- **既存 ADR との矛盾**: 採ろうとしている決定が `.claude/adr/` の ADR とぶつかるなら、ADR の id を挙げて明示し、従うか見直すかを聞く（黙って上書きしない）
- **用語の別名**: bdd-spec の用語集 `features/all_spec.md`（`featuresDir` を変えていればその下）があれば読み、要求や決定に「別名禁止リスト」の語が使われていたら正規の語を示して指摘する（無ければ黙る）

### Step 2: Self-resolve facts, not decisions (grill principle ①)

Split each candidate into a **fact** (how things are now) or a **decision** (how things should be).

- **Facts**: if Phase 2 explorer findings or a quick `Grep` / `Glob` answer it, **resolve it yourself, drop it from the list, and record it as a 確定した前提** to surface in Step 5. Do NOT ask the user something the code already answers.
- **Decisions**: self-resolve only when an **explicit decision record** answers the question directly — the BDD spec (Phase 1.3), the decisions in the Issue context (Phase 1.5), an ADR, or a knowledge decision. A precedent in the code is not a decision record: use it as the basis for your recommendation in Step 4, and still ask.

**Exception — conflicts are not self-resolvable**: when a premise check finds that an inherited decision's premise no longer holds, or that it conflicts with `REQUIRED_DOCS`, do not pick a side yourself. Keep it as a question for Step 4 (recommend the option that follows the standard convention unless the decision explicitly overrides it for a stated reason).

### Step 3: Order by design-tree dependency

Sort the remaining questions so that **upstream decisions come first** — those that constrain or eliminate downstream questions (e.g. "replace vs augment existing auth?" gates a dozen follow-ups).

### Step 4: Grill one at a time (grill principles ②③)

For each remaining question, in dependency order:

1. Ask it with `AskUserQuestion` — **one question per call** — with a **recommended answer as the first option suffixed `(Recommended)`** plus a one-line rationale.
2. After the answer, re-evaluate the remaining questions: a prior answer may resolve, reshape, or reveal a downstream branch. Collapse resolved ones; insert newly-revealed ones.
3. If the user says "whatever you think is best", take the recommended option and continue. An answer that auto-continued on idle (`askUserQuestionTimeout`) is **not** that — keep the question open instead of settling it.
4. If the user says they don't know or someone else decides, do not fill it with your recommendation. Keep it open and record when / where / by whom it gets settled; list it in Step 5 as an open decision the architects must not assume.

Stop when no open branch remains. **Proportionality**: if only 1-2 questions remain and the direction is obvious, batch them into a single `AskUserQuestion` rather than grilling serially (avoid over-questioning).

### Step 5: Confirm the design contract

Summarize before Phase 4: (a) the **確定した前提** auto-resolved in Step 2, (b) every user decision from Step 4 (and any question left open, with when / where it gets settled), (c) each inherited decision with its premise-check result (成立 / 衝突を解消した結果). This is the implicit contract the Phase 4 architects must honor. An inherited decision enters the contract only after its premise check — it is not an unconditional contract just because the Issue states it.

If `bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" adr-keeper` prints `1`, also list as **ADR 候補** the user decisions in (b) that meet all three of adr-keeper's conditions (hard to reverse / puzzling without context / the result of a real trade-off). Zero is the normal case — list nothing then. Only list them; recording one is the user's call (`/adr new <title>`). Print nothing about ADRs when adr-keeper is not enabled.

Then confirm it with **one** `AskUserQuestion` before launching the architects (they are opus agents, up to 3, and a misunderstanding baked in here propagates into every blueprint): question "この設計契約で Phase 4（設計）に進みますか？", options "進む (Recommended)" / "直す" (the user states what to change via the free-text option). On "直す", update the contract, show the changed lines, and continue — do not re-ask unless the correction itself opened a new decision (grill that one per Step 4).

- **Skip the question** when (b) and (c) contain nothing the user decided or left open — a contract made only of auto-resolved facts has nothing for the user to confirm. Still show the summary.
- An answer that auto-continued on idle (`askUserQuestionTimeout`) counts as "進む", but note in the Phase 7 summary that the contract was not explicitly confirmed.

**次は Phase 4**（SKILL.md に戻り、その見出しの入口の条件を見る）
