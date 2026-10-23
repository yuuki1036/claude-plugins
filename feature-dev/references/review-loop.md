# Quality Review — Generator-Verifier Loop（Phase 6 の詳細手順）

SKILL.md 本文の Phase 6 は「self-review へ委譲 → 致命指摘を auto-fix ループで潰す」の骨格だけを持つ。本ファイルは (1) self-review 出力の構造化 findings 消費契約（dual format）と、(2) Generator-Verifier ループの初期化・実行・集計の読み方の手順を持つ。ループの判断（対象の選別・delta・regression・予算・範囲外の変更）は `scripts/gv-loop.py` が持つ。Phase 6 Step 2 / Step 3 から参照される。

## 構造化 findings の消費（dual format）

Step 3（G-V ループ）と Step 4（集約）は self-review 出力を次の優先順で解釈する:

1. **`<!-- FINDINGS_JSON_START -->` 〜 `<!-- FINDINGS_JSON_END -->` の JSON ブロックがあれば、それを決定的にパース**して `findings[]` を取得する（`severity` / `confidence` / `focus` / `file` / `line` / `suggested_fix`）。markdown の正規表現パースに依存しない
2. **JSON ブロックが無い場合**（code-review < 2.18.0）は従来通り markdown レポートの `[confidence: XX][severity: YY]` と `ファイル: path:line` を正規表現パースする（後方互換フォールバック）

消費する schema 契約は self-review SKILL.md 「6.5. 構造化 findings JSON」が SSoT（`schema_version: 1`）。`schema_version` が未知の上位値だった場合は warning を出しつつ既知フィールドのみ読む。

**Partial failure tolerance**: self-review 自体が失敗した場合は warning を出して Step 3 を skip し、Step 4 で「Phase 6 not executed」状態をユーザー提示する。

## Generator-Verifier ループ本体

self-review の出力（severity × confidence）を以下マッピングで auto-fix トリガーに変換する:

| self-review 出力 | feature-dev 扱い |
|---|---|
| `BLOCKER` (any confidence) | **auto-fix 対象**（最高優先度） |
| `CRITICAL && confidence ≥ 90` | **auto-fix 対象** |
| `CRITICAL && confidence < 90` | 報告のみ（Step 4 で提示） |
| `MAJOR` / `MINOR` (any confidence) | 報告のみ |

**Rationale**: BLOCKER は security/data-loss class なので confidence を問わず即修正。CRITICAL は従来の confidence ≥ 90 閾値を維持して誤検知を防ぐ。

詳細なループ予算ルールは `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` Section 10 を参照。

### Step 3.1: Initialize loop state

Determine `max_iterations` based on `${CLAUDE_EFFORT}`:

| effort | max_iterations |
|---|---|
| `low` | 0 (skip Step 3 entirely — go straight to Step 4) |
| `medium` | 1 |
| `high` | 2 |
| `xhigh` | 3 |
| `max` | 3 |

If `max_iterations == 0`, skip Step 3 and proceed to Step 4. Otherwise record the loop's starting point (the working tree right after the initial self-review):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gv-loop.py" init --max <N>
```

`loop=unavailable`（git でない・作業ツリーを記録できない）なら Step 3 を skip して Step 4 へ進む（self-review が失敗した回と同じ扱い）。

ループの状態（各回の対象・修正前の作業ツリー・範囲外の変更・終了理由）は `gv-loop.py` だけが書く。手で JSON を書かない。以前は手書きの状態に、範囲外の修正を独自の欄で自己申告していた（`also_fixed_reported: 34`）が、ループの判断には使われていなかった（GitHub issue #310）。

### Step 3.2: Loop

Repeat the following until `action=stop`:

1. **Decide**: self-review の出力の findings JSON ブロック（`<!-- FINDINGS_JSON_START -->`〜`END`。マーカーごとでよい）を stdin で `review` に渡す:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gv-loop.py" review <<'FEATURE_DEV_FINDINGS_EOF'
   <!-- FINDINGS_JSON_START -->
   ...
   <!-- FINDINGS_JSON_END -->
   FEATURE_DEV_FINDINGS_EOF
   ```

   JSON ブロックが無い（markdown フォールバック）ときは、markdown から同じ形（`{"findings": [{"severity", "confidence", "focus", "file", "line", "title"}]}`。`file` / `line` は `ファイル: path:line`、`focus` は `[カテゴリ]` から）の JSON を組み立てて渡す。exit 2 は入力の形が違う（stderr の `error=`）ので、直して渡し直す。

   `review` が決めること（Claude が判定し直さない）:
   - 上の表で auto-fix 対象を選ぶ。fingerprint は `file:line:focus`
   - 2 回目以降は、ループの起点からの差分（delta）で変えた行の 5 行以内にある対象だけをループに入れる。delta の外の対象は `deferred` に回し、ループを延ばさない（Step 4 に残る）。再レビューは diff 全体を見直すので、修正と関係ない箇所の新しい指摘でループが延びていた（#310）
   - 前回の対象と同じ fingerprint がまた出たら `regression`（delta の外でも）
   - 前回の修正のうち、どの対象の行の 10 行以内にも掛からない hunk を「範囲外の変更」として数える。止めはせず、場所を Step 4 に並べる
2. **Branch on `action=`**:
   - `action=stop` → `reason=`（`success` / `regression` / `budget` / `deferred`）を持って Step 4 へ
   - `action=fix` → 3. へ
   - `action=ask` → 2 回目以降で上限の回。`notice=` の値と `target` / `deferred` / `out_of_scope` の行を示し、`AskUserQuestion` で「続ける」/「ここで止めて Step 4 へ」を聞く。続けるなら 3. へ。止めるなら `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gv-loop.py" finish --reason manual` を実行して Step 4 へ
3. **Notify user**: `notice=` の値をそのまま 1 行で出す（`🔄 Iteration N/max: auto-fix K 件`。2 回目以降は前回の範囲外の変更と delta の外へ回した件数が付く）。省かない — 省くと、何回目か・なぜ続いているかが利用者に見えない（#310 の実測では出ていなかった）
4. **Fix** (Phase 5 Fix Mode): `target` の行だけを直す
   - 各 target の file:line を読み、JSON findings の `suggested_fix`（無ければ markdown の影響説明から推定）を Edit で適用
   - `deferred` の行と、対象外の指摘（MAJOR / MINOR・CRITICAL < 90）は、同じファイルの近くにあっても直さない
   - 設計レベル変更が必要なら `code-architect` を `delta-proposal` focus で起動（1 iteration 消費）
   - 修正不能と判断したら `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gv-loop.py" finish --reason manual` を実行して Step 4 へ
5. **Re-review**: `Skill code-review:self-review` を再呼び出し。引数:
   - `--focus <target の focus 集合>`
   - `--exclude <既に解決した focus 集合>` で重複検査をスキップ可
   - `--embed`（loop 中も AskUserQuestion を skip させる）
   - `--rereview`（修正を確かめる再レビューの申告。計測で初回のレビューと分けて数えさせる / GitHub issue #296）
   - `--spec=<BDD_SPEC_PATH>`（target に `spec-compliance` があり、`BDD_SPEC_PATH` があるとき。初回と同じ照合元を渡す）
6. Return to step 1（再レビューの出力を `review` に渡す）。

### Step 3.3: 集計の読み方

ループの終了理由・各回の対象と範囲外の変更・残った対象・deferred は `gv-loop.py` の状態にある（作業ツリーごとの git dir に置かれ、worktree ごとに分かれる）。Step 4 と Phase 7 は次で読む:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gv-loop.py" summary
```

| 行 | 中身 |
|---|---|
| `reason=` | `success` / `regression` / `budget` / `deferred` / `manual` |
| `iterations=N/max` | 直して再レビューに渡した回数 |
| `auto_fix_targets=` | auto-fix に回した対象の延べ件数 |
| `out_of_scope=` | 範囲外の変更（hunk）の延べ件数。作業ツリーを比べられなかった回があれば `unavailable` |
| `remaining=` と `remaining` の行 | 止めた時点で残った対象（`regression` / `budget` / `manual`） |
| `deferred=` と `deferred` の行 | 最後のレビューで delta の外にあった対象 |
| `out_of_scope` の行 | `<回>`・`<file>:<開始行>-<終了行>`（修正前の行番号）・`+追加 -削除` |

