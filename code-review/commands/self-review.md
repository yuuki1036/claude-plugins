---
description: "コミット前のセルフレビューを実行する（2フェーズ構成・PR不要・ローカル完結） トリガー: 「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」 引数: [base branch] [--staged] [--focus <観点>] [--exclude <観点1,観点2>] [--embed] (省略時は自動検出)"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Agent
  - AskUserQuestion
  - Skill
argument-hint: "[--staged | base branch] [--focus <観点>] [--exclude <観点1,観点2>] [--spec <path>] [--embed] [--rereview] [--since=<tree>] [--prior-findings=<path>] (省略時はデフォルトブランチとの差分)"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/self-review/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `code-review@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。**SKILL.md が持つのは、全 Step に効く節（review との違い・前提など）と、Step の並び・Read の行だけで、各 Step の手順は `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-<番号>.md` にある。Step に入るたびに、その見出しの下の Read の行が指すファイルを読んでから進む** — Step 6 の定型を読まないまま締めた回は 3/3 で定型を出さなかった（GitHub issue #250 / #426）。

self-review スキルを使用して、現在の変更のセルフレビューを実行してください。

引数に `--staged` が指定されている場合は、ステージ済みの変更のみを対象にしてください。
引数にブランチ名が指定されている場合は、それをbase branchとして使用してください。
引数に `--focus <観点>` / `--exclude <観点1,観点2>` が指定されている場合は、レビュー対象観点を絞り込み・除外してください（同一セッションで既検証の観点を再報告しないため）。
引数に `--since=<tree>` / `--prior-findings=<path>` が指定されている場合は、その tree の後に変えた分（delta）を主な対象にし、前回の対象を確認対象に戻してください（feature-dev の G-V ループと Phase 6.9 が渡す / GitHub issue #313）。
`--focus` / `--exclude` / `--rereview` / `--since` / `--prior-findings` は利用者か呼び出し元 skill の手順が付ける引数です。利用者が「self-review 回して」としか言っていない回に、前回の構成から推して足さないでください（絞った観点の外は誰も見ず、計測では修正確認の再レビューに入る / GitHub issue #300）。
`--exclude md-polish` は観点ではなく、Markdown 推敲（diff の md の散文を writing-polish に通す別枠）を止めます。
`--exclude design-review` も観点ではなく、決定系 doc（RFC / ADR / design doc）の決定の質を design-review に見させる別枠を止めます。
引数に `--spec <path>`（または `--spec=<path>`）が指定されている場合は、その仕様ファイルを spec-compliance の照合元にしてください（パスを base branch と読み違えない）。
引数に `--embed` が指定されている場合は、他 plugin からの呼び出しと判断し、終端の修正方針確認 AskUserQuestion を skip してください（呼び出し元側で findings を集約する想定）。**marker を書いた後もターンを終えず**、同じターンのまま呼び出し元の次の手順へ戻ってください（このスキルは呼び出し元と同じ会話の中で動くので、ツールを呼ばずに止まると呼び出し元の手順ごと終わる）。
