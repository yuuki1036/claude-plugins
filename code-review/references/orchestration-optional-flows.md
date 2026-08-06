# 任意フロー（適用条件を満たしたときだけ / orchestration-guide 分冊）

**このファイルは、対応するフローの適用条件を満たしたときだけ Read する。** どれも best-effort で、未導入・非該当なら no-op（後方互換）。

| 節 | フロー | 適用条件 |
|---|---|---|
| `## 2` | Issue ファイル必読フロー | review。branch 名から Issue ID が取れ、ローカルに Issue ファイルがある（issue-workflow 併用時） |
| `## 11` | Vault 照合 | self-review Step 1.5。`kvault` / `/vault-recall` が使える |
| `## 12` | 訂正の伝播前ガード | self-review Step 7。findings を本文へ反映する段 |
| `## 15` | embed mode の構造化 findings JSON | self-review に `--embed` が指定された |

## 2. Issue ファイル必読フロー（review Step 1 の任意フロー / issue-workflow 併用時）

PR head / base branch 名から Issue ID を抽出し、ローカルの Issue ファイルがあれば agent prompt に同梱する。仕様・受入条件・設計判断を踏まえた spec-compliance 判定の精度が上がる（GitHub issue #43）。

```bash
# 1. branch 名から [A-Z]+-\d+ パターンで Issue ID を抽出
HEAD_REF=$(gh pr view <PR番号> --json headRefName -q .headRefName)
BASE_REF=$(gh pr view <PR番号> --json baseRefName -q .baseRefName)
ISSUE_IDS=$(echo "$HEAD_REF $BASE_REF" | grep -oE '[A-Z]+-[0-9]+' | sort -u)

# 2. ローカル Issue ファイル探索（local / linear 両 backend の dir を走査）
for ID in $ISSUE_IDS; do
  find .claude/linear -name "*.md" 2>/dev/null | xargs grep -l "$ID" 2>/dev/null
  find .claude/indie -name "*.md" 2>/dev/null | xargs grep -l "$ID" 2>/dev/null
done | sort -u
```

- ヒットしたファイルを Read で読み込み、内容を spec-compliance reviewer の prompt に `## Issue ファイル` セクションとして同梱する（`prompts/session-context.md` と同じ要領）
- Issue 本文内に「親 Issue: [FOO-1234](...)」「Parent: FOO-1234」のような親リンクがあれば **1 段だけ追跡** （深い再帰は禁止：トークン爆発防止）
- Issue ID が抽出できない / ファイルが存在しない場合は本フローをスキップ（best-effort）
- `.claude/linear/` と `.claude/indie/` 双方が無いリポジトリでは Glob が空配列を返すだけで no-op（後方互換）

## 11. Vault 照合手順（self-review Step 1.5 / 過去の指摘・落とし穴の retrieval）

**利用可否の検出（未導入なら skip / 後方互換）**:

```bash
# kvault コマンド または /vault-recall skill のいずれかが使えれば実行
command -v kvault >/dev/null 2>&1 && echo "kvault: available"
```

`kvault` も `/vault-recall` skill も使えない環境では本ステップ全体を skip する（vault 未導入リポジトリでは no-op）。

**照合手順**:

1. Step 1 で収集した変更ファイルのパス・主要な識別子（関数名・型名・コンポーネント名）・技術語をクエリ語にする
2. 代表的なクエリを 1〜3 個 `kvault recall "<query>"` で実行する（`/vault-recall` skill が使える場合はそちら経由でも可）。出力は `results[]`（`similarity` / `title` / `excerpt` / `path` / `tags`）の JSON
3. 各結果の `similarity` と、上位ヒットと下位ヒットの **gap**（スコア差）で関連度を判断する。上位が明確に分離して高 similarity（目安: 上位 `similarity` ≥ 50 かつ次点との gap が明確）なら関連ありとみなす。全体が低 similarity で団子状なら関連なしと判断して注入しない（ノイズ注入を避ける）
4. 関連ありと判断した知見（`title` + `excerpt` + `path`）を reviewer 起動 step（self-review Step 4）の各 reviewer プロンプトに `## Vault prior findings（過去の関連指摘・落とし穴）` セクションとして注入する

**注意**:
- `--embed` 呼び出し（feature-dev Phase 6 等）でも本ステップは動作する（呼び出し元が retrieval 基盤を共有する前提）
- vault 照合は best-effort。`kvault` 実行が失敗・タイムアウトしても `missing_coverage` には記録せず skip して続行する（レビュー本体をブロックしない）

## 12. 訂正の伝播前ガード（self-review Step 7 / over-correction 防止 / GitHub issue #71）

findings をコード/文書本文に**反映する前に**、その修正が依拠する load-bearing な事実主張を一次ソースで再確認する。修正を「探す」段だけでなく「書く」段にもツール接地を効かせる（`prompts/reviewer-common.md`「事実主張のツール接地」の対）。

- **repo で確認できる主張**(コード挙動・型・呼び出し関係）→ Read/Grep で現物を確認してから書き換える。記憶や推測で本文を直さない
- **repo で確認できない主張**（DB/本番の現状態・外部数値・運用設定・「本番では解消済み」等）→ 「事実」として断定的に書かない。正本（spec / PR / Issue / ADR / コミットメッセージ）で裏が取れない限り **「要確認（典拠=X）」マーカーを残す**。reviewer 指摘が `[unverified: ...]` 付きなら、その不確実性を修正後の本文にも引き継ぐ
- **暫定入力を確定として伝播しない**: ユーザーや reviewer の推測的な言及（「〜かも」「たぶん」「〜のはず」）を、確定した事実として複数箇所に展開しない。確定させるには一次ソースを引くこと
- **1 箇所先行確認 → 確証後に展開**: 同じ訂正を複数箇所に広げる場合、まず 1 箇所で正本確認し、確証が取れてから他箇所へ展開する（未検証の訂正を一括で 5 箇所に広げて全部誤り、という失敗を防ぐ）
- **複数観点の独立一致は高信頼**: 同一箇所を複数の独立した reviewer 観点が指している場合は、相互の誤検出が打ち消されるため高信頼として扱ってよい

## 15. embed mode の構造化 findings JSON（self-review Step 6.5 のみ）

**`--embed` が指定されている場合のみ**、Step 6 の markdown レポート直後に機械可読な findings ブロックを出力する（非 embed 実行では出力しない）。呼び出し元（feature-dev Phase 6 等）はこの JSON を決定的にパースし、markdown の正規表現パースに依存しない。

出力フォーマット（マーカーで厳密に囲む。前後に余計な文字を入れない）:

~~~
<!-- FINDINGS_JSON_START -->
```json
{
  "schema_version": 1,
  "summary": {"score": 7, "blocker": 1, "critical": 2, "major": 1, "minor": 0},
  "findings": [
    {
      "id": 1,
      "severity": "BLOCKER",
      "confidence": 70,
      "focus": "security",
      "file": "src/config.ts",
      "line": 15,
      "title": "Hardcoded secret の疑い",
      "impact": "コミット時にシークレット漏洩",
      "suggested_fix": "process.env.X 経由に置換する"
    }
  ],
  "missing_coverage": ["reviewer-security: timeout で未検査"]
}
```
<!-- FINDINGS_JSON_END -->
~~~

フィールド契約（**schema_version: 1**。変更時は bump して consumer に通知）:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `schema_version` | int | yes | 契約バージョン。フィールド追加/変更時に bump |
| `summary.score` | int | yes | 総合評価 (0-10) |
| `summary.{blocker,critical,major,minor}` | int | yes | severity 別件数（Step 6 報告マトリクス通過後の件数） |
| `findings[].id` | int | yes | Step 6 の連番と一致させる |
| `findings[].severity` | enum | yes | `BLOCKER` \| `CRITICAL` \| `MAJOR` \| `MINOR`（Step 5 でスコアリング後の最終値） |
| `findings[].confidence` | int | yes | 0-100（Step 5 で加減算後の最終値） |
| `findings[].focus` | string | yes | **発生元 reviewer の安定 focus キー**（`bug-detection` / `security` / `claude-md-compliance` / `error-handling` / `spec-compliance` / `performance` 等。triage-guide の focus 語彙）。表示用の日本語カテゴリ（`[セキュリティ]` 等）ではなく、**この英語キーを使う**。呼び出し元の fingerprint (`file:line:focus`) と `--focus` / `--exclude` の語彙に揃える |
| `findings[].file` | string | yes | リポジトリ相対パス |
| `findings[].line` | int | yes | 主たる行番号（範囲なら開始行） |
| `findings[].title` | string | yes | 1 行要約 |
| `findings[].impact` | string | no | 影響説明 |
| `findings[].suggested_fix` | string | no | 修正方針（呼び出し元の auto-fix が利用。不明なら省略可） |
| `missing_coverage` | string[] | yes | 欠損観点（空配列可） |

- **findings は Step 6 で報告された指摘と 1:1**（報告マトリクスで skip されたものは含めない）。`id` は Step 6 のレポート連番に一致させる
- **「✏️ コメント推敲」（B 系統）は findings に含めない**（v2.45.0）。severity / confidence を持たない別枠出力であり、呼び出し元（feature-dev Phase 6 等）の auto-fix は severity 駆動で動くため。推敲は人間が採否を決める性質のもので、自動適用の対象にしない
- **反証レイヤー（Phase 4.9）の効果は `severity` / `confidence` に反映済み**（Step 5 で verdict 反映を適用してから報告するため、JSON には最終値が入る）。`refuted` で取り下げた MAJOR/MINOR は findings に含まれない。**係争中の BLOCKER/CRITICAL は通常通り findings に残り、`title` または `impact` に `⚠️ 反証メモ:` を含める**（schema_version は据え置き 1。新フィールドは追加しない＝consumer 後方互換）
- JSON として valid であること（末尾カンマ禁止、ダブルクオート、改行は文字列内で `\n`）
- このブロックの**後**に `[embed-mode: findings-only, no-prompt]` marker を置く

