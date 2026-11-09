## Phase 5.5: Runtime Smoke Test と動作確認

**Goal**: 静的チェック（tsc / lint / build）で取れない runtime 初期化のバグと、画面の挙動の食い違いを、Quality Review の前に実機ブラウザで捕まえる。UI に影響する変更なら既定で動作確認を行い、行わなかった回は理由を Phase 7 に残す。

**Why this phase exists**: Past incidents (e.g. Prisma v7 adapter requirement) showed bugs that pass all static checks but fail on first request — proxy lazy-init, env var loading, middleware misconfiguration, DB client initialization. Catching these before Phase 6 prevents "review passes but deploy blocks" loops. 動作確認は以前は既定 skip で聞いていたため、画面を触る変更でもほとんど走らなかった（GitHub issue #306）。

### Step 0-1: Self-lock guard と runtime-sensitive 検出

詳細な bash は `${CLAUDE_PLUGIN_ROOT}/references/smoke-test.md` にある。本文では判定結果だけ使う:

1. **Self-lock guard**（将来 PostToolUse hook で自動トリガーする構成に備えた TTL ベースの自己再帰防止）を評価する。lock が active なら `SKIP_PHASE_5_5=1` として Step 2〜4 を skip し **Phase 6** へ進む（command 経由の手動実行では通常 active にならない）。
2. **Deterministic detection**: 作業ツリーの diff（未追跡の新規ファイルの名前と中身を含む。Phase 5 は `git add` しない）を references の pattern（DB/ORM 初期化・環境変数 wiring・middleware/proxy/lazy-init・新規 route）と照合し、1 つでも当たれば **REQUIRED**、無ければ **OPTIONAL** と判定する。当たった pattern を保持し、Step 3 の `--require` に渡す。

### Step 2: 実行するかの判定（聞かない）

実行するかは利用者に聞かない。UI に影響するかは `dev-workflow:ui-verify` が判定する（ここに複製しない）。dev-workflow が有効かだけを見る:

```bash
echo "DEV_WORKFLOW=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" dev-workflow)"
```

- `DEV_WORKFLOW=1` → REQUIRED でも OPTIONAL でも Step 3 で ui-verify を呼ぶ（UI に影響せず、OPTIONAL で smoke の target も無い回は、ui-verify が `skipped` と理由を返す）
- `DEV_WORKFLOW=0` → Step 3 の 3.（手動手順）へ

### Step 3: Execute via dev-workflow:ui-verify

1. smoke の target を決める: architect の `Runtime Smoke Test Targets`（Phase 4）を使い、無ければ Step 1 で検出した追加・変更された route を使う。ui-verify には GET の target の path だけを渡す。`none (static-only change)` なら target を渡さない（画面を確かめるかは ui-verify が決める）
2. `DEV_WORKFLOW=1` なら `Skill` tool で `dev-workflow:ui-verify` を `verify --caller=feature-dev` で呼ぶ。付ける引数:
   - `--targets=<path を , で連結>`（target があるときは REQUIRED でも OPTIONAL でも必ず渡す。ui-verify は `--targets` があれば、UI に影響しないと判定した回も早期終了せずに開く）
   - `--require=<Step 1 で当たった pattern>`（REQUIRED のときだけ。合格基準は **console error 0・network 4xx/5xx 0**）
   - `--screenshot=need`（Issue・依頼が証跡やスクショの添付を求めるときだけ。省くと ui-verify が依頼・Issue から決める）

   ui-verify 内の確認（dev server の起動許可・ケース表・既存ブラウザの停止）は ui-verify の手順のまま通す（`--caller` は確認を省かない）。応答の最後に出る `UI_VERIFY_*` の 5 行（`UI_VERIFY_RESULT=` / `UI_VERIFY_REASON=` / `UI_VERIFY_BROWSER=` / `UI_VERIFY_RECORD=` / `UI_VERIFY_UNCOVERED=`）を Step 4 で使う
3. **手動手順**（`DEV_WORKFLOW=0` / 呼び出しが失敗した / `UI_VERIFY_RESULT=` の行が無い（`--caller` を知らない旧版の dev-workflow。ui-verify のサマリから pass / fail を読めればそれを使う）/ `UI_VERIFY_RESULT=blocked` かつ `UI_VERIFY_BROWSER=none`。`unselected` は入れない）:
   - 手動確認を頼む回: `UI_VERIFY_RESULT=blocked` かつ `UI_VERIFY_BROWSER=none`（使える基盤が無かった）の回は、画面に影響する変更として頼む（ui-verify が判定済みなので判定し直さない）。それ以外は、REQUIRED の回か、diff（未追跡の新規ファイルを含む）に画面のファイルがある回。dev server の起動コマンドと target の URL を示し、手動で確かめて結果を返すよう頼む。hard fail しない。返信が無ければ "manual check pending" として記録する
   - 頼まない回: 実行せず、理由（dev-workflow が無効・UI 変更なし など）を Phase 7 に残す

   画面のファイルは、ui-verify の事前判定が画面の変更と数えるファイル: UI の拡張子（`.tsx` / `.vue` / `.css` など）に加え、`components/` `pages/` `app/` `routes/` `views/` `layouts/` `hooks/` `composables/` `store(s)/` 配下の `.ts` / `.js` / `.mts` / `.mjs`。Phase 7 の申し送りも同じ定義で見る

### Step 4: Triage Findings

`UI_VERIFY_RESULT=` の値で分岐する:

- `pass` → Phase 6 へ（`UI_VERIFY_UNCOVERED=` が `none` 以外なら Phase 7 に残す）
- `fail` → fail したケース（`UI_VERIFY_REASON=`）を示し、利用者が決めるまで Phase 6 へ進まない:
  - Fix now → Phase 5 に戻る
  - Acknowledge and proceed → known issue として記録して Phase 6 へ
- `skipped` → `UI_VERIFY_REASON=` を Phase 7 に残して Phase 6 へ
- `blocked` → `UI_VERIFY_REASON=` を Phase 7 に残して Phase 6 へ。`UI_VERIFY_BROWSER=none`（使える基盤が無かった）の回だけ、Step 3 の手動手順を通してから。`UI_VERIFY_BROWSER=unselected`（基盤を選ぶ前に止まった。dev server の起動を断られた等）の回は手動確認を頼み直さない
- 手動手順の回（manual check pending / 返ってきた結果）と実行しなかった回 → その旨と理由を Phase 7 に残して Phase 6 へ（返ってきた結果が fail なら `fail` と同じ扱い）

**次は Phase 6**（SKILL.md に戻り、その見出しの入口の条件を見る）
