### 1. PR コンテキスト（PR モードのみ）

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh" "$PR_NUMBER" --save
```

出力パスの markdown を Read し、**PR 本文（body）**と既存コメント（issue コメント・レビューサマリ・行コメント）を把握する。本文は Step 4 の「主張 vs diff」に、既存コメントは「人間の判断が効く箇所」に使う。

**同一セッションに review レポートがあれば**、その `🔁 報告閾値を割った指摘` を控える（Step 4 で「人間の判断が効く箇所」に載せる）。無ければ何もしない（この取り込みは前提にしない）。

base モードではこの Step を skip し、「主張 vs diff」「人間の判断が効く箇所」を Step 5 で「対象なし（ローカル diff）」と明記する（silent skip しない）。

**完了基準**: PR モードなら本文と既存コメントを読んだ。base モードなら skip を記録した。

**次は Step 1.5**（SKILL.md に戻り、その見出しを見る）
