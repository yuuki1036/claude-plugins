# writing-polish 連携手順

writing-polish 連携（本文添削）のインストール判定・呼び出し・結果反映・fallback の詳細手順。

1. インストール判定（check-deps.sh と同方式）:
   ```bash
   if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then
     WRITING_POLISH=1
   else
     WRITING_POLISH=0
   fi
   ```
   `WRITING_POLISH=0` → writing-polish 連携を skip。
2. `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を `--embed --tone issue` で呼び、Issue 本文 + 切り出した knowledge ページの散文部分を渡す。
3. 返ってきた推敲済みテキスト（`POLISH_RESULT_START`〜`POLISH_RESULT_END` マーカー間のみ抽出。サマリ・変更点リストは本文に含めない）を本文の代わりに使う。ただし **frontmatter・`[[ ]]` wikilink・相対パスリンク・見出し階層は変更しない（構造を壊す結果は破棄し元案を使う）**。変更があれば何を変えたか一言添える。
4. fallback: 呼び出し失敗時は warning を出し、添削前の本文で完了する。
