# Markdown 推敲（self-review 限定 / GitHub issue #243）

diff で追加・変更した Markdown の散文を writing-polish（別プラグイン・未導入なら skip）に通し、before → after の提案を severity マトリクスの外の別枠に出す。**起動条件・結果の扱い・レポート・適用の正本**。agent 側の手順は `prompts/md-polish.md`、payload の定義は `orchestration-measurement.md ## 16` の `md_polish` の節が正本。

**読むタイミング**: Step 2 で起動すると決まったとき（下の 1 節）。skip と決まった回は読まない（skip の記録は SKILL.md 本文の 1 行で足りる）。

- **なぜ要るか**: 語句・トーン・冗長は writing-polish の領分と triage-guide が境界を引いている（`## 3` の doc-substance の境界）が、diff 内の md 散文をそこへ渡す経路が無かった。コメント推敲（B 系統）の対象はコード内コメントだけ、doc-substance は語句の指摘を低 confidence で申告して好みクランプに落とすので、md の文面はどの担当からも漏れていた
- **なぜ別枠か**: B 系統と同じ理由。推敲は severity を持たず、報告マトリクス（MINOR は 95+）と好みクランプ 40 の 2 段を構造的に通らない
- **なぜ self-review だけか**: 他人の PR に文面の推敲を投稿するのは越権になりやすい（B 系統を self-review 限定にした判断と同じ）
- **なぜ独立の 1 体か**: reviewer に連結すると、writing-polish の手順と規約（tone-guide）が reviewer のコンテキストに入り本務を圧迫する。reviewer wave に相乗りさせるので壁時計は増えない

## 1. 起動条件と skip の理由

Step 1 のダイジェストの `## md-polish`（`md-prose-lines.sh --count` の出力）を読み、**上から順に**当てはめる。最初に当たった行の理由を payload の `md_polish.skip_reason` に入れる:

| 条件 | 起動 | `skip_reason` |
|---|---|---|
| `md_prose_lines=0`（推敲してよい md の追加・変更行が無い） | しない | `no-md-prose` |
| `--embed`（適用する Step 7 が無く、呼び出し元にも受け手が無い） | しない | `embed` |
| `--focus` を指定した / `--exclude` に `md-polish` を含む | しない | `scope` |
| `writing_polish=0`（writing-polish が有効でない） | しない | `not-installed` |
| 上のどれでもない | **する（effort を問わない）** | `null` |

- **`## md-polish` が出ていない（スクリプトが失敗した）回**: `--embed` か scope に当たるならその理由で skip する（表の 2・3 行目は `## md-polish` を使わずに決まる）。当たらなければ**起動せず**、`missing_coverage` に `md-polish` を記録し、`skip_reason` は空のままにする（判定できていないので `no-md-prose` にしない。publish が `payload:md_polish.skip_reason` を立てて可視化する）
- `--exclude md-polish` 単独は他の層にとってスコープの絞り込みではない（SKILL.md の `--focus` / `--exclude` の節）

- **体数の上限（effort 上限・規模キャップ）の外**。reviewer 枠にも specialist 枠にも数えず、最小保証の 2 体にも含めない。core が 0 行の doc だけの変更は small 帯になるが、そこでも起動する
- Phase 0 の構成テーブルに `md-polish` の行を 1 行足す（起動するなら「reviewer wave に相乗り」、しないなら理由）。直列 wave の本数は増えない
- 対象行の数え方（フェンス内・frontmatter・HTML コメント・見出し・表の区切り・リンクだけの行・未追跡のファイルを外す）の正本は `scripts/md-prose-lines.sh` の冒頭

## 2. 起動（Step 4 の reviewer 一括発行に相乗り）

- **発行直前チェックポイントの列挙に含め**、reviewer と**同じメッセージで**発行する。`run_in_background: false` を明示する（後から別メッセージで出すと `wave-split` が立つ）
- `model: opus`、`effort: high`（**実行時 effort に連動させない**。推敲の厚みを effort で揺らさないため。agent 側でも writing-polish の effort 分岐を high として扱わせる）
- プロンプトは 3 行だけ: 「まず `<agent_ctx_file>` を Read せよ」「`prompts/md-polish.md` を Read して従え」、`--staged` の回は「`--staged` の回である」。**確定事実・findings・Vault・AGENTS.md の注入は渡さない**（推敲に使わない）
- **`agents` の内訳に数えない**。publish は `md_polish.fired` を申告体数に足して transcript と突合する（`agents.reviewer` に含めると二重に数えて `agents-mismatch` が立つ）

## 3. 結果の扱い（reviewer の回収後・Step 5 の手前）

- **出力の検証**: `## Markdown 推敲提案` の見出しがあり、提案が 1 件以上あるか `該当なし` と書いてあれば正常。**要約行の次の行が `推敲不能` で始まる回（writing-polish を 1 ファイルも呼べなかった）は失敗として扱う**（`該当なし` の成功に数えると、推敲して何も無かった回と区別できない）。reviewer 用の形式検証と auto-retry（orchestration-guide.md `## 5`）は**当てない**（この agent は `### レビュー結果` を出さない）
- **失敗**（agent がエラーで終わった・見出しが無い）: retry しない。`missing_coverage` に `md-polish` を記録し、`md_polish.suggested` を `-1` にし、レポートの節に「失敗」と 1 行書く。レビュー本体は続行する
- **Step 5 の手順 1〜6 と反証を通さない**。severity 欠落を CRITICAL とみなす既定も当てない。報告件数・`findings_class`・`pre_adjust_counts`・`below_threshold_counts`・🔁 付録・`appendix` のどれにも数えない（数えると publish の合計突合や `payload:appendix.exceeds-body` が壊れる）
- **二重掲載の除去**: Step 5 を通過して Step 6 に残った A 系統の指摘と**同一 file:line** の提案だけを落とす（B 系統と同じ規則）
- **掲載上限は 10 件**。超えた分は「他 N 件（Step 7 の適用対象に含む）」と添える。`md_polish.suggested` は**除去の後・切る前**の件数

## 4. レポート（Step 6 のテンプレートの節）

```
### 📝 Markdown 推敲（severity 対象外・Step 7 で「適用する」を選ぶとメインが Edit で適用する）
{起動した回は必ず出す（0 件なら「該当なし」）。`embed` / `scope` / `not-installed` で skip した回は見出しの下に理由を 1 行。`no-md-prose` の回は見出しごと省く}
<agent の要約行（対象ファイル数・行数・上限で対象外の行数・捨てた提案の件数）>

1. docs/guide.md:12 [確実][冗長]
   before: `することができます`
   after: `できます`
   理由: 意味は同じで短く読める
   行: `この設定は後から変更することができます。`

捨てた提案:
- <agent が挙げた行をそのまま>
```

1 件は agent の出力の 5 行をそのまま載せる（`行:` は Step 7 の適用の手がかり。載せておくと、見た提案と当たる箇所が同じだと読み手も確かめられる）。

`[confidence: ...]` / `[severity: ...]` / `ファイル:` の字面を書かない（指摘として集計され、feature-dev の markdown パーサにも拾われる）。

## 5. payload（Step 6.4）

`md_polish: {fired, skip_reason, suggested}` を入れる（self-review のみ。`gate_schema` は publish が注入する）。定義・語彙・計数の正本は `orchestration-measurement.md ## 16` の `md_polish` の節。**起動しなかった回も入れる**（`fired: false` と理由）。

## 6. 適用（Step 7）

提案が 1 件以上あるとき、Step 7 の AskUserQuestion（**1 回の呼び出し**）に質問を 1 つ足す。**質問 1・2 の回答とは独立に、この回答だけで決める**:

- question: 「Markdown 推敲（N 件。うち確実 M 件）を適用しますか？」
- header: 「md 推敲」
- options（writing-polish の採否 UX に合わせてリスクの低い順。存在しない群の選択肢は出さない）:
  1. 「確実のみ適用 (Recommended)」/「`[確実]` の M 件だけ適用する」（M が 0 なら出さない）
  2. 「全件適用」/「`[任意]` を含む N 件を適用する」（M と N が同じなら出さず、1 の label を「適用する (Recommended)」にする）
  3. 「適用しない」/「文面は現状のまま残す」（M が 0 ならこれを Recommended にする）

**適用の手順**（A 系統の修正とコメント推敲の適用を終えた後。publish の後なので publish-guard は鳴らない）:

1. **行番号ではなく行の全文で位置を決める**（A 系統の修正で行番号がずれる。`--staged` の回は提案の行番号が index 基準で、Edit する作業ツリーとずれうる）。agent の出力の `行:`（対象行の全文）を、そのファイルの中から探す
2. **その全文がファイルにちょうど 1 行だけあり、その行に before がちょうど 1 回現れるときだけ** Edit する（`old_string` は行全体、`new_string` は行の中の before を after に置き換えたもの）。全文が見つからない（A 系統の修正で行が変わった）・2 行以上ある・before が 1 回でない・Edit が「一意でない」で失敗した（行全体が別の行の一部でもある）なら当てずに数える
3. 同じ行に複数の提案があるときは、1 件当てるごとに `行:` を当てた後の全文に読み替えて次を探す
4. 報告: 「Markdown 推敲: 適用 X 件 / 見送り Y 件（行が変わっていた・同じ行が複数あった）」。見送った提案は file:line と before → after を列挙する（黙って落とさない）

## 7. 既知の限界

- writing-polish の有効判定は設定ファイル（ユーザー / プロジェクト / プロジェクトのローカル）の `"writing-polish@…": true` を見るだけで、`--plugin-dir` で読み込んだものは拾わない（未導入として skip する）
- 未追跡の新規 md は対象外（self-review の diff に出ないのと同じ）。`git add` すれば対象になる
- 対象行は 1 回 300 行まで（`md-prose-lines.sh` の既定）。超えた分は agent の要約行に件数が出る
- フェンスの無い 4 桁字下げのコードブロックは、箇条の続きの行と見分けられないので対象から外さない（フェンスで書いたコードは字下げ・引用の中でも外す）
- 同じ原文が対象行の複数箇所に現れ、writing-polish がそれを 1 件にまとめて返した・一部だけ直した回は、どこに当てるか決まらないので捨てる（捨てた提案は agent の出力に並ぶ）
- 正本と複製の同期を機械で検証しているリポジトリ（SSoT pin など）では、正本の節の文面を推敲で変えると検証が落ちる。Step 7 で適用した後はリポジトリの検証（pre-commit 等）を通す
