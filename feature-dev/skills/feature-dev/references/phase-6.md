<!-- 正本依存（SSoT pin）。Phase 6 Step 4 の「範囲の行が無ければ旧版」と Phase 6.9 の `--since` / `--prior-findings` の渡し方は、code-review の self-review の Step 6（`skills/self-review/references/step-6.md`）「6. レポート出力」の範囲の行と prior-fixes-guide.md「4.」の形を要約したもの。正本が変わったら Step 4 と 6.9 を確認して pin を打ち直す -->
<!-- SSOT: code-review/skills/self-review/references/step-6.md#6 @76335b44 -->
<!-- SSOT: code-review/references/prior-fixes-guide.md#4 @f5c76a67 -->
<!-- 正本依存（SSoT pin）。`--since` / `--prior-findings` の効き方（delta を主に見る・前回の対象を戻す・`--focus` と併用したときのスキップ）と、delta が未追跡を含まないこと・観点を delta で選び直すことは、self-review の Step 1（`skills/self-review/references/step-1.md`）「1.」と triage-guide.md「6.5」が正本。正本が変わったら Step 3.2 / Step 4 / 6.9 / Phase 7 の未追跡の扱いを確認して pin を打ち直す -->
<!-- SSOT: code-review/skills/self-review/references/step-1.md#1 @18660c38 -->
<!-- SSOT: code-review/references/triage-guide.md#6.5 @82b2674b -->
## Phase 6: Quality Review

**Goal**: `code-review:self-review` skill に委譲して品質ゲートを通し、致命指摘を Generator-Verifier ループで自動 fix する

**モデル切り替えの停止点（Step 0 の前）**: 実行中のメインモデルが**現行世代の Opus より前の世代**（例: Opus 4.8 で実装した）なら、Phase 6 に入る前にここで止まり、次のメッセージを出してターンを終える。ユーザーの返信を待ってから Step 0 へ進む。現行世代（またはそれより上位）で動いているなら止まらず、何も出さずに Step 0 へ進む:

> 🔀 **モデル切り替えポイント**: これから Phase 6（self-review）に入ります。self-review 内の `opus` 指定の reviewer・検証役はメインモデルの世代に解決されるため、前の世代のままだと見落としが増えます。**現行世代の Opus へ切り替えてから**「続けて」と返信してください。このまま進める場合もそのまま返信で構いません。

選択 UI（`AskUserQuestion`）ではなく通常メッセージで止めるのは、ユーザーがモデル選択を操作してから返信する必要があるため。

**設計判断**: v2.0.0 で feature-dev 内蔵の `code-reviewer` agent を廃止し、`code-review` plugin の `self-review` skill に品質基準を一本化した。理由は (a) 同リポジトリ内で reviewer ロジックが二重化していた DRY 違反、(b) `code-review` の 2 軸スコアリング × 15 観点 × specialist × meta-reviewer 構造の方が遥かに堅牢だから。`code-review` plugin は `_requirements` で `required: false` 宣言（claude-plugins 規約で plugin 間の強制依存を避ける）だが、Phase 6 では fail-fast する。

### Step 0: Existence Check (code-review plugin)

Phase 6 は `code-review:self-review` skill に依存する。冒頭で plugin が有効かを確認し、未インストール・無効時は **fail-fast** する:

```bash
if [ "$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" code-review)" != 1 ]; then
  echo "❌ Phase 6 は code-review plugin に依存します（未インストールか無効）。インストール・有効化:"
  echo "   claude plugin install code-review@yuuki1036-claude-plugins"
  echo ""
  echo "Phase 5 までの成果物は維持されています。インストール後、Phase 6 から再開してください。"
  exit 1
fi
```

ユーザーに「インストールして再開 / Phase 6 を skip して Phase 6.7 へ（6.7 と 6.9 はそれぞれの入口の条件・本文の分岐に従う）/ abandon」を `AskUserQuestion` で確認するのも可。SessionStart hook (`hooks/scripts/check-deps.sh`) が事前に warning を出しているはずだが、ここで再確認することでセッション中盤のインストールにも対応する。

### Step 1: Capture the implementation diff

```bash
# Phase 5.5 でも同じファイルを使う前提
git diff HEAD 2>/dev/null > /tmp/feature-dev-final-diff.txt
git diff --name-only HEAD 2>/dev/null > /tmp/feature-dev-final-files.txt
```

**reviewer の観点はここで選ばない。** 観点の選定・体数・束ね方は self-review の Phase 0 triage に任せる（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` Section 6 / GitHub issue #283）。初回のレビューに `--focus` を付けると、反証レイヤーと skeptic が `scope` でスキップされ、triage が出す観点（`layer-responsibility` など）も範囲外になる。

### Step 2: Invoke code-review:self-review

`Skill` tool で `code-review:self-review` を呼ぶ。引数:

- **`--focus` は付けない**（Step 1）。Phase 6 のどの呼び出しでも付けない — Step 3 の G-V ループの再レビューは `--since` / `--prior-findings` で範囲を delta に絞る（GitHub issue #313）
- `--embed`（**必須**: feature-dev は自前で findings を集約するため、self-review 終端の修正方針確認 AskUserQuestion を skip させる）
- `--spec=<BDD_SPEC_PATH>`（`BDD_SPEC_PATH` があるときだけ）: spec-compliance reviewer に BDD spec を読ませる。self-review の spec-compliance は session-context / Issue / knowledge しか読まないので、渡さないと Phase 1.3 の spec と実装の照合が起きない。`=` でつないで 1 語にする（`--spec` を知らない旧版の self-review がパスを base branch と読み違えないため）
- base branch は省略（self-review が `git remote show origin | grep "HEAD branch"` で自動検出）
- 未コミット diff は self-review 側で `git diff` / `git diff --cached` を併用して取得

self-review 内部の動き（詳細は `code-review:self-review` skill の SKILL.md 参照）:

- Phase 0 triage で reviewer 体数を `${CLAUDE_EFFORT}` 連動で決定（feature-dev の effort をそのまま継承）
- Phase 3/4 で explorer + reviewer 並列起動
- Phase 4.5 adaptive deepening（reviewer が unmet_information を申告した場合、追加 explorer 最大 3 体 + 再起動 reviewer 最大 3 体）
- Phase 4.6 meta-reviewer ラウンド（BLOCKER/CRITICAL 検出時、`${CLAUDE_EFFORT}` が xhigh/max のとき動作）
- Phase 5 で **2 軸スコアリング** (confidence 0-100 × severity BLOCKER/CRITICAL/MAJOR/MINOR)
- Phase 6 でレポート出力（severity 別グループ、欠損観点、総括）
- Phase 6.5（**code-review ≥ 2.18.0**）で `--embed` 時に **構造化 findings JSON ブロック**を markdown レポート直後に出力（`<!-- FINDINGS_JSON_START -->` / `<!-- FINDINGS_JSON_END -->` で囲む）
- Phase 7 は `--embed` 指定により skip（末尾 marker `[embed-mode: findings-only, no-prompt]` を確認）

**self-review の Step 6 定型レポートと Step 6.4 publish は feature-dev が省かない**（GitHub issue #232）: self-review の手順をこのコンテキストで回すので、実行主体が曖昧になると定型を独自要約に置き換えたり、publish を踏まずに Step 3 へ進んだりしやすい。`--embed` を外して呼んだ場合も含め、self-review の定型レポート → `mark t2` → publish を済ませてから Step 3 に進む。feature-dev の集約（Step 4）は定型レポートの後に足し、置き換えない。publish 前に Edit / Skill 等を呼ぶと code-review の publish-guard hook が鳴る。

**`--embed` が落とすもの（構造的な穴の埋め戻し）**: self-review の Step 7 には**コメント推敲（B 系統）の適用**が入っているため、`--embed` ではコードコメント精査が実行されない。feature-dev 側は **Phase 6.7** で独立ステップとして必ず通す（GitHub issue #227）。B 系統の提案自体は `--embed` でも Step 6 のレポートに `## コメント推敲提案` ブロックとして出るので、Phase 6.7 でそれを材料にする。

**embed mode の利点**: ユーザー操作が 1 回減り、findings をそのまま Step 3 の G-V loop と Step 4 の集約処理に流せる。`--embed` 未対応の旧 code-review (< 2.17.0) では Step 7 の AskUserQuestion がそのまま出るが、Step 0 は **存在チェックのみ**で version は確認していない。旧版が混在しうる前提で、JSON ブロック不在時は markdown フォールバックへ、AskUserQuestion 出力時はそれを findings 提示として吸収する（version ゲートは張らない）。

**構造化 findings の消費（dual format）**: Step 3 / Step 4 は self-review 出力を、`<!-- FINDINGS_JSON_START -->`〜`END` の JSON ブロックがあれば決定的にパースし、無ければ markdown を正規表現でフォールバックパースする。schema 契約と詳細は `${CLAUDE_PLUGIN_ROOT}/references/review-loop.md` を参照。

**Partial failure tolerance**: self-review 自体が失敗した場合は warning を出して Step 3 を skip し、Step 4 で「Phase 6 not executed」状態をユーザー提示する。

### Step 3: Generator-Verifier Loop (automatic critical-issue fix)

self-review の出力を severity × confidence で auto-fix トリガーに変換し、致命指摘を Phase 5 Fix Mode で自動修正して再レビューするループ。

| self-review 出力 | feature-dev 扱い |
|---|---|
| `BLOCKER` (any confidence) | **auto-fix 対象**（最高優先度） |
| `CRITICAL && confidence ≥ 90` | **auto-fix 対象** |
| `CRITICAL && confidence < 90` | 報告のみ（Step 4 で提示） |
| `MAJOR` / `MINOR` (any confidence) | 報告のみ |

**Rationale**: BLOCKER は security/data-loss class なので confidence を問わず即修正。CRITICAL は confidence ≥ 90 閾値を維持して誤検知を防ぐ。

ループの初期化（`${CLAUDE_EFFORT}` → `max_iterations`）・実行・集計の読み方は `${CLAUDE_PLUGIN_ROOT}/references/review-loop.md` に従う。対象の選別・regression / budget の判定・2 回目以降に delta の外の対象を `deferred` に回すこと・範囲外の変更の集計は `scripts/gv-loop.py review` が持ち、Claude はその `action=` に従って Fix と再レビューを回す（GitHub issue #310）。再レビューには `review` が出す `since=` / `prior_findings=` を渡し、self-review は直前の修正からの delta を主に見る（GitHub issue #313）。2 回目以降で上限の回は、続けるかを利用者に聞く。`low` effort は `max_iterations=0` で Step 3 を skip し Step 4 へ直行する。

### Step 4: Consolidate and present

0. **レビューした時点を記録する**（GitHub issue #276）: Step 3 のループが終わった直後（skip した回は Step 2 の直後）に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-snapshot.sh" save` を実行する。この後に入る変更（下の 5. のユーザー判断の修正・Phase 6.7・別の決定の反映）は self-review を通らないので、Phase 6.9 で差を取る
1. **集約**: Step 2 の初回のレポートと Step 3 の**各回の**再レビューのレポート、`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gv-loop.py" summary`（Step 3 が走った回）を読み、全ての BLOCKER / CRITICAL / MAJOR / MINOR を列挙する。同じ fingerprint（`file:line:focus`）は後の回の判定を使う。再レビューは delta を主に見るので、最後の回だけを読むと初回や途中の回で出た delta の外の指摘が落ちる（GitHub issue #313）。`--since` を渡したのに再レビューのレポート冒頭に `**範囲**:` の行が無かった回は、code-review が旧版で diff 全体を見直した旨を 1 行添える（`since=unavailable` で渡さなかった回は、新版でも行が出ない）
2. **タグ付け**: Step 3 で解決したものは `[auto-fixed]`、ループ後も残ったもの（summary の `remaining`）は `[persisting]`、delta の外にあってループに入れなかったもの（`deferred`）は `[deferred]`。範囲外の変更（`out_of_scope`）が 1 以上なら「範囲外の変更 N か所」と場所を添える（ループの再レビューは通っているが、auto-fix の対象ではない変更）
3. **Recommend**: 手動修正を推奨する高 severity issue を identify
4. **Present findings and ask**（`reason=` で分岐）:
   - `success`: 確認のみで Phase 6.7 へ
   - `regression` / `budget` / `manual`: persisting critical issues を提示し、ユーザーに（手動修正 / 受け入れて続行 / abandon）を聞く
   - `deferred`: deferred の対象（BLOCKER / CRITICAL ≥ 90 で、ループの修正と関係ない箇所にあった。前の回の分は最後に報告された時点の状態で、delta を主に見る再レビューは確かめ直していない）を提示し、同じ 3 択を聞く
   - Step 3 が skip（`low` effort / `loop=unavailable`）: 全 critical を提示してユーザー判断
   - self-review が失敗: warning を提示し、ユーザー判断（リトライ / skip / abandon）
5. ユーザー判断に従って対応。直すと決めた指摘は、Phase 6.9 で前回の対象として渡すので、FINDINGS_JSON の形（`{"findings": [...]}`。self-review の出力の該当行をそのまま）で控える

**次は Phase 6.7**（SKILL.md に戻り、その見出しの入口の条件を見る）
