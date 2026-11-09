<!-- 正本依存（SSoT pin）。Phase 6 Step 4 の「範囲の行が無ければ旧版」と Phase 6.9 の `--since` / `--prior-findings` の渡し方は、code-review の self-review の Step 6（`skills/self-review/references/step-6.md`）「6. レポート出力」の範囲の行と prior-fixes-guide.md「4.」の形を要約したもの。正本が変わったら Step 4 と 6.9 を確認して pin を打ち直す -->
<!-- SSOT: code-review/skills/self-review/references/step-6.md#6 @76335b44 -->
<!-- SSOT: code-review/references/prior-fixes-guide.md#4 @f5c76a67 -->
<!-- 正本依存（SSoT pin）。`--since` / `--prior-findings` の効き方（delta を主に見る・前回の対象を戻す・`--focus` と併用したときのスキップ）と、delta が未追跡を含まないこと・観点を delta で選び直すことは、self-review の Step 1（`skills/self-review/references/step-1.md`）「1.」と triage-guide.md「6.5」が正本。正本が変わったら Step 3.2 / Step 4 / 6.9 / Phase 7 の未追跡の扱いを確認して pin を打ち直す -->
<!-- SSOT: code-review/skills/self-review/references/step-1.md#1 @18660c38 -->
<!-- SSOT: code-review/references/triage-guide.md#6.5 @82b2674b -->
<!-- 正本依存（SSoT pin）。Phase 6.9 の推奨の決め方は code-review の review-guide-format.md「回し直すかの判断」の `あり` の条件 3 を要約したもの（条件 1・2 は check / diff の出力で満たされる）。正本が変わったら Phase 6.9 を確認して pin を打ち直す -->
<!-- SSOT: code-review/references/review-guide-format.md#回し直すかの判断 @bc251143 -->
## Phase 6.9: レビュー後の変更の確認

**Goal**: Phase 6 の self-review の後に入った変更を、未レビューのまま締めない（GitHub issue #276）。G-V ループが再レビューするのは auto-fix の対象だけで、ユーザーの判断で入れた修正・Phase 6.7 のコメント適用・別のセッションで決めたことの反映は通らない。仕様書のように節をまたいで同じ規則を参照する変更では、1 か所の修正が別の節との食い違いを作りやすい。

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-snapshot.sh" check
```

- `changed_files=0` → 何もせず Phase 7 へ
- `changed_files` が 1 以上 → `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-snapshot.sh" diff` で変わった中身を読み、どれを推奨にするかを決める（GitHub issue #304）。変更がどれも実行時の挙動を変えない（名前・コメント・doc、テストの改名やアサーションの追加、中身を変えないブロックの移動。Phase 6.7 のコメント適用はこれに当たる）か、変わったファイルがすべて未追跡（`untracked_files` が `changed_files` と同じ。self-review の diff は未追跡を含まないので、回しても見る対象が無い）なら「静的オラクルだけ回す」、分岐・状態・入出力の契約（引数・戻り値・出力の形式・規約の文言）を足した・変えたものが 1 つでもあれば「self-review をもう一度回す」を推奨にする。差があるという事実だけで self-review を推奨にしない — 挙動を変えない変更に回し直しても、前回と同じ閾値未満の候補が並び直すだけになる。変わったファイルと行数（`check` の `<追加>\t<削除>\t<path>` 行）と推奨の理由 1 行を示して、`AskUserQuestion` で聞く（推奨を先頭に置き「（推奨）」を付ける）:
  - 「self-review をもう一度回す」— 先に前回の対象を書く: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gv-loop.py" prior-findings` に、Step 4 の 5. で直すと決めた指摘の FINDINGS_JSON を stdin で渡す（無ければ空）。今回の run で Step 3 が走った回だけ `--with-loop` を付ける（ループの deferred / remaining を gv-loop が足す。Step 3 が走らなかった回の状態は前の run のもの）。exit 2 は `unavailable` と同じ扱いにする。出力の `prior_findings=` で引数を決め、Phase 6 Step 2 の引数に足して回す（記録の後の変更を主に見る / GitHub issue #313）:
    - `<path>` → `--since=<check が出した snapshot>` と `--prior-findings=<path>`
    - `none`（前回の対象が無い）→ `--since=<snapshot>` だけ
    - `unavailable`（書けなかった）→ どちらも付けない（前回の対象なしに delta だけを見ると、修正が対象の行に触れなかった回に、直っていない指摘を誰も見ない）

    指摘を Step 4 と同じ扱いで提示する。終わったら `save` で記録し直し、もう一度 `check` する
  - 「静的オラクルだけ回す」— Phase 5.3 を同じ手順でもう一度回し、緑なら Phase 7 へ（緑以外なら Phase 5.3 Step 3 の扱い）。Phase 7 のサマリには未レビューとして残し、緑だった回は静的オラクルが緑だったことを添える
  - 「回さずに締める」— Phase 7 のサマリに未レビューとして残す
  - `check` の `untracked_files=` が 1 以上なら、その分は self-review の対象外（self-review の diff は未追跡ファイルを含まない）。どれを選んでも Phase 7 の「レビュー後の変更」に未追跡 N ファイルとして残す。値は最初の `check` のものを控えておく（回し直した後の `save` → `check` は未追跡も含めて記録し直すので 0 になる）
- `snapshot=missing` / `unavailable`（Phase 6 が走らなかった・git の操作に失敗した）→ 聞かずに Phase 7 へ進み、サマリに「レビュー後の変更: 確認できなかった」と出す

**次は Phase 7**（SKILL.md に戻り、その見出しの入口の条件を見る）
