# writing-polish 連携手順

writing-polish 連携（本文添削）の有効かの判定・呼び出し・結果反映・fallback の詳細手順。

1. 有効かの判定（有効なものだけを見る判定。`${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh` が user → project → local の settings の明示値で `1` / `0` を出す）:
   ```bash
   echo "WRITING_POLISH=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" writing-polish)"
   ```
   `WRITING_POLISH=0` → writing-polish 連携を skip。
2. `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を `--embed --tone issue` で呼び、Issue 本文 + 切り出した knowledge ページの散文部分を渡す。
3. 返ってきた推敲済みテキスト（`POLISH_RESULT_START`〜`POLISH_RESULT_END` マーカー間のみ抽出。サマリ・変更点リストは本文に含めない）を本文の代わりに使う。ただし **frontmatter・`[[ ]]` wikilink・相対パスリンク・見出し階層は変更しない（構造を壊す結果は破棄し元案を使う）**。変更があれば何を変えたか一言添える。
4. fallback: 呼び出し失敗時は warning を出し、添削前の本文で完了する。
