---
description: "Web UI の動作確認（実機 E2E）・スタイル調整・スクリーンショット取得を自動化する。verify は正常・準正常・異常系を実機ブラウザで通し合否と証跡を残す トリガー: 「動作確認」「UIチェック」「E2E」「スクリーンショット」「スタイル調整」「見た目確認」「レスポンシブ確認」「/ui-verify」「visual check」「screenshot」「UI verification」「responsive check」 引数: [verify|tune|snap] [target-url-or-path] [--screenshot=need|none] [--caller=<feature-dev|lightweight-flow>]"
allowed-tools:
  - Bash
  - Read
  - Edit
  - AskUserQuestion
  - Skill
  - mcp__plugin_dev-workflow_chrome-devtools__navigate_page
  - mcp__plugin_dev-workflow_chrome-devtools__new_page
  - mcp__plugin_dev-workflow_chrome-devtools__list_pages
  - mcp__plugin_dev-workflow_chrome-devtools__take_screenshot
  - mcp__plugin_dev-workflow_chrome-devtools__take_snapshot
  - mcp__plugin_dev-workflow_chrome-devtools__get_css_styles
  - mcp__plugin_dev-workflow_chrome-devtools__list_console_messages
  - mcp__plugin_dev-workflow_chrome-devtools__list_network_requests
  - mcp__plugin_dev-workflow_chrome-devtools__resize_page
  - mcp__plugin_dev-workflow_chrome-devtools__emulate
  - mcp__plugin_dev-workflow_chrome-devtools__click
  - mcp__plugin_dev-workflow_chrome-devtools__hover
  - mcp__plugin_dev-workflow_chrome-devtools__fill
  - mcp__plugin_dev-workflow_chrome-devtools__press_key
  - mcp__plugin_dev-workflow_chrome-devtools__wait_for
  - mcp__Claude_Browser__navigate
  - mcp__Claude_Browser__computer
  - mcp__Claude_Browser__find
  - mcp__Claude_Browser__read_page
  - mcp__Claude_Browser__form_input
  - mcp__Claude_Browser__read_console_messages
  - mcp__Claude_Browser__read_network_requests
  - mcp__Claude_Browser__preview_start
  - mcp__Claude_Browser__preview_logs
  - mcp__claude-in-chrome__navigate
  - mcp__claude-in-chrome__computer
  - mcp__claude-in-chrome__find
  - mcp__claude-in-chrome__read_page
  - mcp__claude-in-chrome__form_input
  - mcp__claude-in-chrome__read_console_messages
  - mcp__claude-in-chrome__read_network_requests
  - mcp__claude-in-chrome__tabs_context_mcp
  - mcp__claude-in-chrome__tabs_create_mcp
---

**モードが `verify` で引数に `--caller=` もあるときは、SKILL.md を Read する前に下の「呼び出し元からの早期終了」を先に見る**（verify 以外のモードの `--caller` は SKILL.md の定義どおり無視し、早期終了しない）。それ以外は（早期終了しなかった回も）**まず `${CLAUDE_PLUGIN_ROOT}/skills/ui-verify/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `dev-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

ui-verify スキルを使用して、Web UI の動作確認・スタイル調整・スクリーンショット取得を実行してください。

引数が渡されていればそれも考慮してください（例: `verify`, `tune`, `snap`, 対象 URL やパス、`--screenshot=need|none`、呼び出し元のワークフローからの `--caller=<feature-dev|lightweight-flow>`。`--caller` は確認を省く意味を持たない — 他スキルの `--embed` と違う）。
引数がなければユーザーに使用モードを確認してください。

## 呼び出し元からの早期終了（`verify --caller` のときだけ）

feature-dev / 軽量フローは UI に影響しない変更でも毎回この口を呼ぶので、SKILL.md を読む前に事前判定だけを済ませる（判定の正本は `scripts/ui-impact.sh`。SKILL.md の「事前判定」と同じ判定を先に行うだけ）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ui-impact.sh"
```

モードが `verify` で `UI_IMPACT=no`、引数に `--require` も `--targets` も無ければ、SKILL.md を読まずに次の 5 行を応答の最後に出して終える（ブラウザも dev server も起こさない。verification.md も pending flag も書かない）:

```
UI_VERIFY_RESULT=skipped
UI_VERIFY_REASON=<ui-impact.sh の REASON の値>
UI_VERIFY_BROWSER=none
UI_VERIFY_RECORD=none
UI_VERIFY_UNCOVERED=none
```

それ以外（`UI_IMPACT=yes` / `UI_IMPACT=unknown` / `--require` か `--targets` あり）は SKILL.md を Read して続ける（事前判定はこの結果をそのまま使い、引き直さない）。
