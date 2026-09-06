---
description: "厄介なバグ・性能劣化を feedback loop 駆動の 6 Phase 診断規律で原因特定・修正する トリガー: 「バグ診断」「デバッグして」「原因を調べて」「再現しない」「直したはずが直らない」「なぜか動かない」「性能が劣化した」「遅くなった原因」「/diagnose」「debug this」 引数: [症状・再現手順・対象箇所]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/diagnose/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `dev-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

diagnose スキルを使用して、バグ・性能劣化の診断を実行してください。

引数が渡されていればバグの症状・再現手順・対象箇所として扱ってください。
引数がなければ、まずユーザーに症状（何が・いつから・どう壊れているか）を確認してください。
