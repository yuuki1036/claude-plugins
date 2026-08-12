# Reviewer プロンプト索引

reviewer / specialist / meta-reviewer / 反証 / skeptic の各プロンプト本体は `references/prompts/` 配下に **1 観点 1 ファイル**で置く。

**オーケストレーター（メインコンテキスト）はこのファイルも `prompts/` の中身も Read しない。** agent プロンプトには**ファイルパスだけ**を渡し、agent 自身に Read させる（orchestration-guide.md `## 3.5`）。本文をプロンプトへ転記すると同一テキストを起動体数ぶん書き出すことになり、出力トークンが `(N-1) × 本文長` 膨らむ。共通指示だけで約 7.3k tokens あるため、6 体構成では約 44k tokens の複製になっていた。

## 索引

| 節（旧番号） | ファイル | 用途 |
|---|---|---|
| `## 1` 共通指示 | `prompts/reviewer-common.md` | 全 reviewer / specialist 共通。**最初に Read する** |
| `## 2` セッションコンテキスト | `prompts/session-context.md` | session-context.md が有効なときの注入規約 |
| `## 2.5` PR コンテキスト | `prompts/pr-context-rules.md` | review のみ。`$PR_CTX_FILE` の検出ルール（re-flag / resolved / scope:out / D1-High） |
| `## 3` Focus テンプレート | `prompts/focus/<focus>.md` | 観点ごと。`bug-detection` / `security` / `spec-compliance` ほか 17 種 |
| `## 3` バンドル起動 | `prompts/bundle-rules.md` | 1 体に複数観点を束ねるときの追加指示（reviewer / specialist 共通） |
| `## 4` Angle | `prompts/angles.md` | 冗長ペア（xhigh / max のみ）の切り口 |
| `## 5` Specialist | `prompts/specialist/<key>.md` | `injection` / `destructive-op` / `secret-handling` / `input-validation` / `guardrail-bypass` |
| `## 6` Meta-reviewer | `prompts/meta-reviewer.md` | Phase 5.6 / 4.6 |
| `## 7` Adversarial-verify | `prompts/adversarial-verify.md` | Phase 5.9 / 4.9（反証レイヤー） |
| `## 8` 冷や読み skeptic | `prompts/recall-skeptic.md` | Phase 5.8 / 4.8（recall 補強） |

- focus キーの語彙は triage-guide.md `## 3` の観点判定表と一致する（`prompts/focus/<focus キー>.md` で一意に引ける）
- **`focus/comment-polish.md` は Focus テンプレートではない** — `comment-accuracy` reviewer に self-review のときだけ連結する追加ブロック
- **specialist** は triage-guide.md `## 3`「Red-flag pattern による specialist 自動起動」で起動される別カテゴリ。**指摘の大半が BLOCKER / CRITICAL になる前提**で動作する（人間判断を促すのが目的なので、低 confidence でも報告マトリクスで届く）。specialist agent も `reviewer-common.md` を最初に Read する

## プロンプトの組み立て方（オーケストレーター向け）

agent に渡すのは以下だけ。本文は書かない。

```
あなたは reviewer-<focus> です。まず次の 2 ファイルを Read し、その指示に従ってレビューしてください。
1. ${CLAUDE_PLUGIN_ROOT}/references/prompts/reviewer-common.md
2. ${CLAUDE_PLUGIN_ROOT}/references/prompts/focus/<focus>.md

<可変部: PR 番号 / 期待 HEAD SHA / diff ファイルのパスと担当ファイル /
 PR コンテキストのパス / AGENTS.md のパス / explorer 結果 / angle 指定>
```

- `{{PR_NUMBER}}` / `{{HEAD_REF}}` / `{{HEAD_SHA}}` のプレースホルダは `reviewer-common.md` 側にあるため、**実値を可変部に明記**して「テンプレート中のプレースホルダをこの値で読み替えよ」と指示する
- 複数観点を束ねるときは `prompts/bundle-rules.md` を Read 対象に追加し、focus ファイルを複数指定する

### 可変部の予算（v2.60.0 / パス渡しの効果を可変部で打ち消さないため）

**可変部は 1 体あたり 40 行以内・スロットを埋めるだけにする。** 本文をパス渡しにしても、オーケストレーターが可変部に**散文で観点の解説を書けば同じコストが戻る**（`main.output` は単価が最も高い。orchestration-measurement.md `## 17`）。実測（review・reviewer 3 体構成）で fleet の 46% がメイン側の時間だった内訳には、この散文の執筆が入っている。

**スロット以外を書かない。** 以下が可変部の全項目で、これ以外は**テンプレート側に書くべき内容**（＝ `prompts/` を直すサインであって、可変部で補うものではない）:

| スロット | 形 |
|---|---|
| プレースホルダ実値 | `{{PLUGIN_ROOT}}` / `{{PR_NUMBER}}` / `{{HEAD_REF}}` / `{{HEAD_SHA}}` / `{{MAIN_ROOT}}` / `{{SEVERITY_THRESHOLD}}` を **1 行 1 個の箇条書き**で列挙 |
| Read させるパス | ファイルパスの**列挙のみ**（各パスの中身を要約しない） |
| 担当範囲 | focus キー / 担当ファイル名 / angle 名。**1〜3 行** |
| explorer 結果 | 該当 explorer の出力を `## Explorer 結果` に貼る（選択的注入なので複製係数 ≒ 1） |

- **禁止**: focus の観点解説・チェックリストの再掲・severity 判定基準の再説明・「doc なので〜と読み替えよ」のような長い読み替え指示。**読み替えが毎回必要なら `prompts/focus/<focus>.md` 側に mode 別の節を作る**（1 回書けば全レビューで効く。可変部に書くと毎レビュー × 体数ぶん払う）
- **例外**: `doc-review-mode` 等でテンプレートに無い一時的な読み替えが要る場合は書いてよいが、**2 回目に同じ読み替えを書いたらテンプレート側へ移す**
- agent が Read を怠った場合は出力形式検証（orchestration-guide.md `## 5`）で `### レビュー結果` 見出し・`[confidence:]` タグ・`HEAD 検証:` 行の欠落として検出され、1 回だけ auto-retry される
