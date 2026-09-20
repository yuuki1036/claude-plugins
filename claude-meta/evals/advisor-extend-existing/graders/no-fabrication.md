---
type: llm
weight: 1
---

demo-plugin に存在しないものを存在すると述べていない。demo-plugin が持つのは `commands/commit.md` と `skills/git-commit-helper/SKILL.md` と `plugin.json` だけで、agents / hooks / references / 他の skill は無い。

存在しない skill・agent・hook・ファイルを「既にある」と述べていなければ PASS。1 つでも捏造していれば FAIL（「将来こういう hook を足せる」のような提案は捏造に数えない）。
