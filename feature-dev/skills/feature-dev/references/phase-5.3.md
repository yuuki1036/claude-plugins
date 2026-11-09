<!-- 正本依存（SSoT pin）。Phase 5.3 の宣言オラクルの契約は code-review の machine-layer.md が正本（プラグイン間依存禁止のため要約で持つ）。正本が変わったら Phase 5.3 を確認して pin を打ち直す -->
<!-- SSOT: code-review/references/machine-layer.md#5 @737549d4 -->
## Phase 5.3: 静的オラクルゲート（fail-closed / 決定的検証）

**Goal**: runtime smoke test（Phase 5.5）と LLM レビュー（Phase 6 = 多体 agent）に進む**手前**で、型チェック・lint・テストという**決定的オラクル**を変更範囲に絞って走らせ、機械的に落とせる欠陥をここで潰す。

**Why this phase exists**: Phase 5.5 は *runtime* smoke test、Phase 6 は *LLM* レビューで、型/テストを exit code で判定する決定的ゲートがパイプラインに無かった。型エラー・テスト赤はサーバ起動（5.5）や multi-agent レビュー（6）に投げるより先に、最も安いオラクルで落とすのが Clearwing 原則 8（外部オラクル + fail-closed）。ルート CLAUDE.md「コスト×精度パイプライン設計指針」参照。最安オラクルを先頭に置くため Phase 5.5 より前に配置し、Phase 5.5 が skip される静的変更でも必ず通す。

### Step 1: オラクル検出（無ければ graceful skip）

プロジェクトが `.claude/review-oracles.sh` でオラクルを宣言していれば、**それだけを使い、下の推測はしない**。何を安いオラクルとするかはプロジェクトの判断で、推測より宣言を優先する（契約の正本は code-review の `machine-layer.md` `## 5`: exit 0 = 緑 / 1 = 検出あり / 2 = 判定不能。実行は数分以内）。Phase 6 の self-review は `--embed` で機械層を skip するので、宣言オラクルが feature-dev の中で走るのはここだけ。

```bash
test -f "$(git rev-parse --show-toplevel 2>/dev/null)/.claude/review-oracles.sh" && echo "oracle=declared"
```

宣言が無いときだけ、次の推測で検出する:

```bash
git diff --name-only HEAD 2>/dev/null > /tmp/feature-dev-changed-files.txt
ORACLE_TC=""; ORACLE_LINT=""; ORACLE_TEST=""
if [ -f package.json ]; then
  grep -q '"typecheck"' package.json && ORACLE_TC="npm run typecheck"
  [ -z "$ORACLE_TC" ] && grep -q '"tsc"' package.json && ORACLE_TC="npm run tsc"
  grep -q '"lint"' package.json && ORACLE_LINT="npm run lint"
  grep -q '"test"' package.json && ORACLE_TEST="npm test"
  # npm init 既定のプレースホルダ（"test": "echo ... exit 1"）は実テストではないので除外（恒常赤の誤爆防止）
  grep -Eq '"test"[[:space:]]*:[[:space:]]*"echo' package.json && ORACLE_TEST=""
fi
# 他エコシステムのフォールバック（存在するもののみ採用）
[ -z "$ORACLE_TC" ] && [ -f tsconfig.json ] && command -v npx >/dev/null && ORACLE_TC="npx tsc --noEmit"
[ -z "$ORACLE_TEST" ] && [ -f Cargo.toml ] && ORACLE_TEST="cargo test"
[ -z "$ORACLE_TEST" ] && [ -f go.mod ] && ORACLE_TEST="go test ./..."
[ -z "$ORACLE_TC" ] && [ -f pyproject.toml ] && command -v mypy >/dev/null && ORACLE_TC="mypy ."
```

### Step 2: 実行（変更範囲に絞る。全ビルド/全テストは重いので避ける）

- **宣言オラクル**は範囲を絞らず、repo ルートから 1 回実行する。**Bash の `timeout` に 600000 を指定する**（既定の 120 秒では、この repo の宣言でも実測 130 秒以上かかって打ち切られる）。exit code は出力に出す（代入で終わると Bash の終了ステータスが 0 に潰れ、Step 3 が判定できない）:
  ```bash
  ( cd "$(git rev-parse --show-toplevel)" && bash .claude/review-oracles.sh ); echo "oracle_exit=$?"
  ```
- 以下は推測で検出したときの出し分け
- 型チェック・lint は常時実行（安い）。テストは effort に応じて出し分ける（`triage-guide.md` の effort 予算に接続）:
  - `low` / `medium`: 型チェック（+ lint）のみ。テストは Phase 5.5 と Phase 6 に委ねる
  - `high` 以上: 型チェック + lint + テスト。テストは可能なら**変更ファイルに関連するもののみ**（例: jest なら `npx jest --findRelatedTests $(cat /tmp/feature-dev-changed-files.txt)`、他は最小スコープ）
- 各コマンドの exit code を記録する。

### Step 3: 判定（fail-closed）

**緑以外で進んだ回の記録**（下の判定不能・打ち切り・オラクル不在・暴走ガードで赤のまま進んだ回・`low` effort の skip のすべて。記録の書き方はここだけが持つ）: その旨（「静的オラクル判定不能」（exit 2・126・127）「静的オラクル打ち切り」（timeout）「静的オラクル無し（型/テスト未検証）」「静的オラクル赤のまま進行」「静的オラクル skip（low）」のどれか）を、初回（Phase 5 の実装の後）は Phase 7 の申し送りに書く。Phase 6.7・6.9 から回し直した回も申し送りに書き、「（Phase 6.9 の回し直し）」のように経路を添える。Phase 7 の 4. 以降から回し直した回は、申し送りを出した後なので次の一手に添える。どれも「静的オラクルは緑」とは書かない

- **全て緑（exit 0）**: 5.3 に入った経路の次へ進む。通常（Phase 5 の実装の後）は Phase 5.5 へ。Phase 6.7・6.9・7 から 5.3 を回し直した回は、その phase の手順の次へ戻る（緑の行き先はここが持つ。Fix Mode から戻った回と、下の「承知の上で進む」出口も同じ）。この結果は Phase 6 の focus 判定でも「静的検証済み」として扱ってよい。
- **いずれか赤（exit≠0。下の exit 2・126・127 と打ち切りを除く）**: Phase 5.5 / Phase 6 へ**進まず**、エラー出力を Phase 5 Fix Mode に渡して決定的に修正 → 本ゲートを再実行。Phase 6.7・6.9・7 から回し直した回に Fix Mode で入れた修正は、self-review も動作確認も通っていないので、緑以外の記録と同じ書き先に「Fix Mode の修正 N ファイル（未レビュー）」と残す。
- **宣言オラクルが exit 2（判定不能）/ 126・127（実行不能）/ Bash の timeout で打ち切り**: 緑として扱わない。前提の欠落（依存ライブラリが無い等）はコードの修正では直らないので Fix Mode には渡さず、出力を添えて `AskUserQuestion` で「前提を整えて再実行 / 承知の上で進む」を委ねる（進む先は緑の行き先と同じ）。進んだ場合は上の「緑以外で進んだ回の記録」に従う。
- **オラクル不在（検出ゼロ）**: gate できないので緑の行き先へ進むが、上の「緑以外で進んだ回の記録」に従う（fail-open は「検証手段が無い」ときだけ許容。曖昧・実行エラー時は赤扱いで保留に倒す）。

**暴走ガード**: 本ゲート ↔ Fix Mode の往復は**最大 2 回**まで。2 回修正しても赤が残る場合はループを止め、`AskUserQuestion` で「手動修正して再開 / 承知の上で進む（進む先は緑の行き先と同じ） / abandon」をユーザーに委ねる（同一エラーの無限往復を防ぐ）。赤のまま進んだ回は上の「緑以外で進んだ回の記録」に従う。`low` effort では初回（Phase 5 の実装の後）に限り本ゲート自体を skip 可（速度優先。Phase 6.7・6.9・7 から回し直す回は skip しない）。skip した回は上の「緑以外で進んだ回の記録」に従う。

**次は Phase 5.5**（SKILL.md に戻り、その見出しの入口の条件を見る。Phase 6.7・6.9・7 から回し直した回は Step 3 の緑の行き先に従う）
