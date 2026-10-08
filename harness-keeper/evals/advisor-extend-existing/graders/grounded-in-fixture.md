---
type: llm
weight: 2
---

demo-plugin の実物を根拠に使っている。次のうち 2 つ以上を、ファイルを読んだ上での事実として挙げていれば PASS:

- `git-commit-helper` の allowed-tools に既に `Bash` が含まれるので `git blame` を追加で許可する必要が無い
- 既存の Phase 1（変更の把握）または Phase 2〜4 のどこに blame 確認を差し込めるか、phase 名か番号で特定している
- `commit` command と `git-commit-helper` skill が対になっており、両方の allowed-tools を揃える必要がある
- トリガーが「コミットして」等で重なるため、別 skill にすると起動が競合しうる

demo-plugin のファイルを読まず一般論だけで答えている（ファイル名・phase 名・allowed-tools の具体に一切触れない）なら FAIL。
