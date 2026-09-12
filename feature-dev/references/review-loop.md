# Quality Review — Generator-Verifier Loop（Phase 6 の詳細手順）

SKILL.md 本文の Phase 6 は「self-review へ委譲 → 致命指摘を auto-fix ループで潰す」の骨格だけを持つ。本ファイルは (1) self-review 出力の構造化 findings 消費契約（dual format）と、(2) Generator-Verifier ループの初期化・実行・終了ログの手順を持つ。Phase 6 Step 2 / Step 3 から参照される。

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

If `max_iterations == 0`, skip Step 3 and proceed to Step 4. Otherwise initialize the loop state file:

```bash
cat > /tmp/feature-dev-loop-state.json <<EOF
{
  "run_id": "$(uuidgen 2>/dev/null || date +%s)",
  "max_iterations": <N>,
  "current_iteration": 0,
  "iterations": []
}
EOF
```

### Step 3.2: Loop

Repeat the following until a termination condition fires:

1. **Filter**: self-review 出力から auto-fix 対象を抽出。**まず構造化 findings JSON ブロック（`<!-- FINDINGS_JSON_START -->` 〜 END）を決定的にパースし `findings[]` を得る**。JSON が無ければ markdown を正規表現フォールバックでパース（dual format、Step 2 参照）。得た findings に上記マッピング（BLOCKER any / CRITICAL ≥90）を適用。0 件なら **terminate with success** → Step 4。
2. **Fingerprint**: 各 issue から `fingerprint = "{file}:{line}:{focus}"` を算出し、current iteration の `fingerprints` 配列に append。`file` / `line` / `focus` は JSON findings の同名フィールドを使う（focus は安定 focus キー。markdown フォールバック時は `ファイル: path:line` と `[カテゴリ]` から抽出）。
3. **Regression check**: 現 iteration の `fingerprints` と前 iteration の `fingerprints` が 1 件以上 overlap したら **terminate with "regression detected"** → Step 4。
4. **Budget check**: `current_iteration >= max_iterations` なら **terminate with "budget exhausted"** → Step 4。
5. **Notify user**: 1 行 update — `🔄 Iteration {N+1}/{max}: auto-fixing {K} critical issues...`
6. **Fix** (Phase 5 Fix Mode):
   - 各 issue について flagged file:line を読み、JSON findings の `suggested_fix`（無ければ markdown の影響説明から推定）を Edit で適用
   - 設計レベル変更が必要なら `code-architect` を `delta-proposal` focus で起動（1 iteration 消費）
7. **Re-review**: `Skill code-review:self-review` を再呼び出し。引数:
   - `--focus <persisting issue の focus 集合>`
   - `--exclude <既に解決した focus 集合>` で重複検査をスキップ可
   - `--embed`（loop 中も AskUserQuestion を skip させる）
8. **Update loop state**: `current_iteration` をインクリメントし、新 iteration エントリを append。
9. Return to step 1。

### Step 3.3: Loop termination logging

ループ終了時に loop state file へ集約を append:

```json
{
  "terminated_at": "<timestamp>",
  "termination_reason": "success | regression | budget | manual",
  "remaining_critical": <count>,
  "auto_fixed_count": <count>
}
```

このファイルは Phase 7 summary で参照される。

