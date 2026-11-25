### 4.3 writing-polish 連携（PR 本文添削・必須）

`writing-polish` が有効なら**必ず**通してからユーザーに提示する。未導入か無効のときだけ skip（プラグイン独立性のため。後方互換）。推敲は **body 本文が最終形になった時点＝Step 4.7（三要素セルフチェック）の後・Step 4.9（機械検証）の前**に必ず行う（冗長削減・曖昧語の具体化・トーン統一・AI っぽさ除去）。Step 4.5 / 4.6 / 4.7 で body を変更した場合は変更分も含めて推敲を通す（推敲を経ていない本文を Step 4.95 で提示しない）。本節（4.3）は番号の順でなく、この実行位置（4.7 の後）に置いてある。

1. 有効かの判定（同梱の `plugin-enabled.sh` が user → project → local の settings の明示値で `1` / `0` を出す。出力が空ならスクリプトを起動できていないので、`${CLAUDE_PLUGIN_ROOT}` を実パス（この文書を Read したパスの、プラグインのルート）に直して再実行する（無効と同じに扱わない））:
   ```bash
   echo "WRITING_POLISH=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" writing-polish)"
   ```
   `WRITING_POLISH=0` → 本ステップを skip。
2. `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を呼ぶ。`--embed` を必ず付け、`--tone pr` を伝え、生成した PR 本文(description)を渡す。
3. 返ってきた推敲済みテキスト（`POLISH_RESULT_START`〜`POLISH_RESULT_END` マーカー間のみ抽出。サマリ・変更点リストは含めない）を description の代わりに使う。ただし **本スキルの厳守ルール（体言止め・常体に統一、敬体禁止、AI 署名禁止、装飾絵文字禁止、ローカルパス出力禁止、PR テンプレートのセクション構造は変更しない＝文面のみ推敲）を満たすこと**。満たさない結果は破棄し元案を使う。変更があれば「何を変えたか」を一言添える。
4. fallback: 呼び出し失敗時は warning を出し、添削前の本文で従来どおり完了する。

**次は Step 4.9**（SKILL.md に戻り、その見出しを見る）
