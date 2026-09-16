---
name: review-guide
description: >
  PR（または base 指定のローカル diff）を人間が後から理解するための読み順ガイドを出す。重要ファイルを精読 N 件に絞り、実装の流れ順（入口 → ロジック → 永続化 → テスト）に並べ、各ファイルに 何をした / 難点 / 見る行 / レビュー観点 を付ける。読み取り専用で投稿・修正・永続化はしない。
  トリガー: 「PR の読み方」「読み順」「この PR を解説して」「このPR何やってる」「PR を理解したい」「/review-guide」
  引数: [PR番号 | --base <ref>] [--top N]（省略時は現在ブランチの PR）
effort: medium
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
---

# review-guide

PR を**読む人間**を支援する skill。指摘を出す（review / self-review）でも付いた指摘に応える（review-triage）でもなく、**diff のどこをどの順で読めばよいか**を案内する。主用途は自分の PR を後から理解すること、副用途は他者 PR に review を回した後の学習。

正本設計: `.claude/designs/20260916-code-review-review-guide-skill.md`。

## review / self-review / review-triage との違い

- review / self-review は severity 付き findings を**出す**。本 skill は findings を出さない。「レビュー観点」は「このファイルで何を見るか」の問いであって判定ではない
- 出力は**セッション内のみ**。ファイルを書かない・コメントを投稿しない・コードを修正しない（Edit / Write / Skill を持たない）
- 全ファイルは解説しない。精読は上位 N 件（既定 5・`--top N`）に絞り、残りは 1 行で流し読み / 不要に振る

## 絶対厳守ルール

- **読み取り専用**。ファイル作成・コメント投稿・push・コード修正・Issue 起票を一切しない
- **各主張に `file:line` を添える**。「この PR で何をした」「難点」「主張 vs diff」に書く事実は、確認した `file:line` を根拠にする。確かめられないことは書かない（「難点: 特になし」を許す）。記録・コミットメッセージ・PR 本文の主張をそのまま採用せず、diff とコードで確かめる
- **精読 N で切っても core を落とさない**。上位 N の選抜で core は流し読みに落ちても「不要」には落とさない

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md の 10 原則のうち **採用: 1（ファネル = triage-signals の分類で精読を N 件に絞ってから agent を当てる）/ 3（段階予算 = `${CLAUDE_EFFORT}` で explorer 0/2/3 体）/ 4（モデルルーティング = explorer は `sonnet`・統合は `opus`＝メインコンテキスト）/ 5（暴走ガード = explorer 体数上限・精読 N の上限）/ 9（構造化受け渡し = diff はパス渡し、explorer は事実のみ返す）**。**捨てた**: 2・10（severity / confidence を付けない。判定ではなく説明）/ 6（蓄積しない。永続化なし）/ 7（反証レイヤーなし。説明文の根拠を `file:line` で強制し、無い主張は書かない）/ 8（静的な読解に機械判定オラクルが無い）。

## 実行手順

### 0. 入力確定と diff 収集

引数を解析する。**`--base <ref>` の値を `BASE_REF`、`--top N` の値を N（省略時 5）、残りの非オプション引数（PR 番号）を `PR_ARG` に入れる**。`--base` があれば base モード、無ければ PR モードに入る。

```bash
# PR モード（既定）: PR_ARG（省略時は現ブランチの PR）を解決する。--base 指定時は PR モードに入らない
if [ -z "$BASE_REF" ]; then
  META=$(gh pr view ${PR_ARG:+"$PR_ARG"} --json number,title,url,headRefName,headRefOid,baseRefName,body 2>/dev/null) \
    && PR_NUMBER=$(printf '%s' "$META" | jq -r '.number') || PR_NUMBER=""
  # PR が特定できないときは base モードへフォールバックする。BASE_REF が空なら
  # default branch を解決して埋める（空のまま --base に渡すと triage-signals が FATAL で落ちる）
  if [ -z "$PR_NUMBER" ]; then
    BASE_REF=$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p')
    [ -n "$BASE_REF" ] || { echo "対象 PR も base ref も特定できない。base branch を指定して呼び直してください"; }
  fi
fi
```

- `PR_NUMBER` が空でも `BASE_REF` が空なら、上の案内を出して終了する（PR も base も無い）
- **PR モード**（`PR_NUMBER` あり）: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh" --pr "$PR_NUMBER"` で diff 収集とシグナル出力を得る
- **base モード**（`BASE_REF` あり）: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh" --base "$BASE_REF"`。この場合 Step 1 の PR コンテキストは無い
- **diff 全文をメインコンテキストに載せない**。`triage-signals.sh` が diff をファイルへ保存し、`## meta` の `diff_file=` にパスが出る。**このパスの実値を控える**（シェル変数は Bash 呼び出し間で消える）

出力の各セクション（`## files` = 分類 + 行数 / `## red-flags` `## surface` = リスク信号 / `## hunks` = core の関数コンテキスト / `## focus-signals` = 観点判定ヒット）を読む。**diff 全文の Read はしない**。

**完了基準**: `diff_file` の実パス・`size_tier`・`## files` の分類済みファイル一覧・PR/base モードの別が確定している。`## size` の `total_files` が 0 なら「変更なし」で終了。

### 1. PR コンテキスト（PR モードのみ）

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh" "$PR_NUMBER" --save
```

出力パスの markdown を Read し、**PR 本文（body）**と既存コメント（issue コメント・レビューサマリ・行コメント）を把握する。本文は Step 4 の「主張 vs diff」に、既存コメントは「人間の判断が効く箇所」に使う。

**同一セッションに review レポートがあれば**、その `🔁 報告閾値を割った指摘` を控える（Step 4 で「人間の判断が効く箇所」に載せる）。無ければ何もしない（この取り込みは前提にしない）。

base モードではこの Step を skip し、「主張 vs diff」「人間の判断が効く箇所」を Step 5 で「対象なし（ローカル diff）」と明記する（silent skip しない）。

**完了基準**: PR モードなら本文と既存コメントを読んだ。base モードなら skip を記録した。

### 2. 重要度スコアと 3 段振り分け（メインコンテキスト・agent なし）

`## files` の各ファイルに score を付ける（`## files` は 80 件で打ち切られる。超える大規模 PR では `diff-slice.sh "<diff_file>" --list` で全件を引いてから振り分ける）:

```
score = 分類（core=3 / test=2 / doc=1 / gen=0）
      + red-flags・surface の代表ファイルに +2
```

`## files` の 1 列目のラベルは core / test / doc / gen の 4 種（lockfile・生成物はすべて `gen` に畳まれる）。

- **red-flags / surface の加点は「代表ファイル」にのみ**。`triage-signals.sh` の digest は 1 signal につき代表 1 ファイル（`<key>\t<hit数>\t<代表根拠ファイル>`）しか出さないため、全該当ファイルへは配れない。代表ファイル以外は分類スコアのみ（設計判断 F2）
- **fan-in（被参照数）や行数帯は初版では使わない**。分類だけで core・test・doc の順が確定し、精読 N の選抜には足りる。独自 Grep で被参照を数えると `triage-signals.sh ## explorer-signals` が持つ誤カウント対策（3 文字未満 basename 除外・`-lwF` 固定文字列 word 一致・自己除外）を捨てて過大カウントする（設計判断 F1）。将来足すときは独自 Grep を新設せず `## explorer-signals` 出力を再利用する

3 段に振り分ける（**同点は core 優先**でタイブレークし、core を上位 N から落とさない）:

- **精読**: score 上位 N 件（既定 5）
- **流し読み**: 残りの core・test・doc
- **不要**: gen（生成物・lock）・rename のみ・機械的置換（import 差し替え等）。**各 1 行の理由を付ける**

**完了基準**: 全変更ファイルが精読 / 流し読み / 不要のいずれかに入り、不要には理由が付いている。精読は N 件以下で、core が「不要」に落ちていない。

### 3. 流れの把握（`${CLAUDE_EFFORT}` 分岐 / 実行時値: `${CLAUDE_EFFORT}`）

精読ファイルの呼び出し関係を辿り、「入口（API / CLI / UI）→ ロジック → 永続化 → テスト」のスレッド（変更が貫く 1 本の流れ）を組む。1 PR に 2〜3 本のスレッドが典型。

- **`low` / `medium`**: agent を起動しない。`bash "${CLAUDE_PLUGIN_ROOT}/scripts/diff-slice.sh" "<diff_file 実パス>" '<精読ファイル>'` で精読ファイルの hunk を切り出して読み、import / 呼び出しの字面からスレッドを組む。**担当ファイル名は必ずシングルクォートで囲む**（diff 由来 = 信頼できない入力。`references/prompts/explorer-common.md`）
- **`high`**: explorer **上限 2 体**（`sonnet`）を**同一メッセージで一括発行**（各 Agent call に `run_in_background: false` を明示）。①function-flow（精読ファイルの変更関数の分岐・データ変更・呼び出し先）②dependency-trace（精読ファイルの呼び出し元）
- **`xhigh` / `max`**: explorer **上限 3 体**（`sonnet`）。上の 2 つ + value-flow-trace（入口から永続化までの値の流れ）

explorer 起動の共通詳細（プロンプト組み立て・2 ファイル Read 方式・diff のパス渡し・HEAD 検証）は `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` を Read して従う。explorer には **`diff_file` のパスと担当ファイルだけ渡す**（diff 本文を転記しない）。explorer は事実収集に徹し判定しないので、返る「コードフロー」「依存関係」をスレッド構成の材料にする。

**完了基準**: 精読ファイルがスレッドに割り当てられ、各スレッドが入口から永続化・テストへ向かう順に並んでいる。

### 4. 統合・執筆（メインコンテキスト）

`${CLAUDE_PLUGIN_ROOT}/references/review-guide-format.md` を Read し、その形式で各項目を書く:

1. **まず全体**: PR 本文 + diff から「この PR がやったこと」を 2〜3 行。スレッド一覧
2. **精読ファイル（実装の流れ順）**: 各ファイルに 4 項目（この PR で何をした / 難点 / 見る行 `file:line` / レビュー観点）。レビュー観点は `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md ## 3` の観点判定表を `## focus-signals` のヒットで引いて添える（表は複製しない）
3. **主張 vs diff**（PR モードのみ）: 本文の主張が diff にあるか / diff にあるが本文に無いか
4. **テスト対応**: 変更した振る舞いごとに対応するテストの有無と場所
5. **人間の判断が効く箇所**: 既存の行コメント（PR モード。`fetch-pr-context.sh` は解決状態を取得しないので「未解決」と断定せず、返信チェーンで著者が閉じていないものを緩く拾い「解決状態は不明」と留保する）と、同一セッションの review レポートの `🔁` 付録（あれば）

**各主張の根拠 `file:line` を必須にする**（絶対厳守ルール）。確かめられない主張は書かない。

**完了基準**: 全精読ファイルに 4 項目が埋まり、事実主張すべてに `file:line` が付いている。主張 vs diff・テスト対応・人間の判断が効く箇所の各セクションが（該当なしなら「特になし」を含めて）埋まっている。

### 5. レポート出力

`review-guide-format.md` のテンプレートで出力する。**ファイルは書かない**（セッション出力のみ）。base モードでは「主張 vs diff」「人間の判断が効く箇所」を「対象なし（ローカル diff）」と明記する。

**完了基準**: レポートを出力した。ファイルへの書き込み・コメント投稿・コード修正を一切していない。

## Additional Resources

- `${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh` — diff 収集と分類・リスク信号（`--pr` / `--base`）
- `${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh` — PR 本文・コメントの取得（`--save`）
- `${CLAUDE_PLUGIN_ROOT}/scripts/diff-slice.sh` — 精読ファイルの hunk 切り出し
- `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` — explorer 起動の共通詳細（Step 3 の high 以上で Read）
- `${CLAUDE_PLUGIN_ROOT}/references/review-guide-format.md` — レポート形式と 4 項目の書き方（Step 4 で Read）
- `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 3` — レビュー観点判定表（正本・複製しない）
