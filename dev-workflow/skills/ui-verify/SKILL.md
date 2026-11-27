---
name: ui-verify
description: |
  Web UI の動作確認（実機 E2E）・スタイル調整・スクリーンショット取得を自動化する。
  verify は正常・準正常・異常系を実機ブラウザで通し、合否と証跡を .claude/verification/ に残す。
  認証あり画面はログイン済みブラウザの状態を再利用する（パスワード入力はしない）。
  トリガー: 「動作確認」「UIチェック」「E2E」「スクリーンショット」「スタイル調整」「見た目確認」「レスポンシブ確認」「/ui-verify」「visual check」「screenshot」「UI verification」「responsive check」
  引数: [verify|tune|snap] [target-url-or-path] [--screenshot=need|none] [--caller=<feature-dev|lightweight-flow>]
effort: medium
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

# ui-verify

Web UI の動作確認（実機 E2E）・スタイル調整・スクリーンショット取得を自動化するスキル。

> **Step 3 のモードごとの本文は、モードごとのファイルにある**（`skills/ui-verify/references/modes/<モード>.md`）。この SKILL.md に残すのは、Step 3 の外の節（事前判定（`verify --caller` のときだけ）・Step 0〜2・Step 4・MCP Tool の使い方・絶対厳守ルール）と、Step 3 の各モードの見出しと Read の行だけ。Step 3 で呼ばれたモードの見出しに来たら、Read の行が指すファイルを最初に読む。見出しだけを見て、本文を読まずに進めない（1 本のままだと Read 1 回で読み切れず、後ろの節を読まないまま進めうる / GitHub issue #447）。本文で (a)〜(f) と書いた箇所は verify モードのファイル（`references/modes/verify.md`）の節を指す。Step 3 より前にそれを使う回（`--caller` で Step 1・2 から (f) を返して終える回など）も、先にそのファイルのその節を読んでから従う。モードのファイルの中の `${CLAUDE_PLUGIN_ROOT}` は、この SKILL.md を Read したパスのプラグインのルートに読み替える

## 3つのモード

| モード | 用途 | 出力 |
|--------|------|------|
| `verify` | 実機ブラウザで正常・準正常・異常系を通し、合否と証跡を残す | `.claude/verification/<branch>.md` + 証跡 |
| `tune`   | スタイル調整ループ（撮影→編集→リロード→再撮影） | 調整前後の screenshot |
| `snap`   | スクリーンショット収集（複数 viewport × 状態） | `.claude/screenshots/{timestamp}/*.png` |

引数が無ければ対話的にモードを確認する。URL/path 省略時は後述の自動検出ロジックで決める。

### 呼び出し元のワークフローから呼ぶとき（`verify --caller=<…>`）

feature-dev の Phase 5.5 と issue-workflow の軽量フロー（Step 3）は、`verify --caller=<feature-dev|lightweight-flow>` でこのスキルを呼ぶ。UI に影響する変更かの判定はこのスキル（`scripts/ui-impact.sh`）だけが持ち、呼び出し元には複製しない（GitHub issue #306）。

| 引数 | 意味 |
|---|---|
| `--caller=<feature-dev\|lightweight-flow>` | 別のスキルから呼ばれた。モードを聞き返さず、Step 0 の前に「事前判定」を行い、応答の最後に (f) の 5 行を出す。**確認は省かない**（dev server の起動許可・ケース表の確認・期待ユーザー・backend の隔離の確認・既存ブラウザの停止確認。他スキルの `--embed` のように確認 UI を止める意味は持たない）。verify 以外のモードでは無視する |
| `--require=<理由>` | 事前判定が `no` でも smoke を走らせる（feature-dev の runtime-sensitive 判定が REQUIRED の回） |
| `--targets=<path>[,<path>...]` | 必ず開く URL / path（事前判定が `no` でも開く）。各 target を smoke ケース 1 件として (b) に足す |
| `--screenshot=need\|none` | (a) のスクショの要否。省くと依頼から決める |

### verify は実機 E2E（役割分担）

`verify` は**実機ブラウザで E2E を通す**。console/network のエラー検知に留めず、ケースごとに操作して期待結果を確認し、合否（pass/fail/blocked）と証跡を `.claude/verification/<branch>.md` に残す。結果は `pr-creator` が動作確認セクションの材料に読む。

役割は 3 つに分ける（前提: E2E の合否は実機ブラウザでしか決めない）:

| 目的 | 手段 |
|---|---|
| E2E の実行と合否判定 | 実機ブラウザ（chrome-devtools / Claude Browser / Claude in Chrome。verify モードの (a) の優先順位） |
| スクショ（添付用証跡） | Storybook があればそれ、なければ chrome-devtools / Playwright |
| 動画（添付用証跡） | Playwright の recordVideo（webm） |

**Playwright / Storybook は証跡撮影係であって E2E の代替にしない**。複数ステップの Playwright script が要る撮影は公式 skill `webapp-testing`（`~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/`）に委譲する。repo に Playwright が入っていればそれを使う。

`snap` モードは追加引数 `--viewports=...` を受け付ける（デフォルトは desktop 1 枚）。詳細は Step 3 の snap モード（`references/modes/snap.md`）。

## 実行手順

### 事前判定: UI に影響する変更か（`verify --caller` のときだけ）

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ui-impact.sh"
```

command 本文の早期終了で実行済みなら、その結果を使う（引き直さない）。見る範囲は未コミットの変更（HEAD と作業ツリー・index の差）と未追跡のファイル。拡張子の式は ui-change-reminder.sh（hook）と共通で、画面の層のディレクトリ配下の `.ts` / `.js` / `.mts` / `.mjs` は ui-impact.sh だけが数える（式の中身は `scripts/lib/ui-paths.sh`。ここに書き写さない）。

| `UI_IMPACT` | `--require` / `--targets` | 対応 |
|---|---|---|
| `yes` / `unknown` | どれでも | Step 0 へ（`unknown` は確かめる側に倒す） |
| `no` | どちらも無い | ブラウザも dev server も起こさず、(f) を `skipped`（`UI_VERIFY_REASON` は出力の `REASON`）で返して終える。command 本文の早期終了と同じ判定 |
| `no` | どちらかがある | Step 0 へ進み、(b) のケース表は呼び出し元のケースだけにする |

### Step 0: 実行対象の checkout 判定（main か worktree か）

**最初に**（`--caller` のときは事前判定の後に）、いま居る checkout が main の clone か git worktree かを判定し、dev server の port と「その port で LISTEN している process がこの checkout のものか」を確定する。判定は同梱スクリプトが行う（記憶や `lsof` の目視で決めない）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-checkout.sh" [--port N]
```

出力は `KEY=VALUE`（`CHECKOUT` / `WORKTREE_STATE` / `TOPLEVEL` / `BRANCH` / `DEV_PORT` / `PORT_SOURCE` / `SERVER_PID` / `SERVER_CWD` / `SERVER_MATCH`）。`DEV_PORT` は引数 → worktree-setup の `envs/.frontend.env.worktree`（`FRONTEND_PORT`）→ `package.json` の `scripts.dev` → 3000 の順で決まる。**`SERVER_MATCH` が判定の要**: port が生きているだけでは「自分の server」と言えない。worktree で起動すると main（や別 worktree）が立てた server も同じ port に見え、それを流用すると**別のコードを検証して pass を書く**。

| `CHECKOUT` / `WORKTREE_STATE` | `SERVER_MATCH` | 対応 |
|---|---|---|
| `main` | `none` | Step 2 の通常経路（起動許可を取って `DEV_PORT` で起動） |
| `main` | `ours` | 起動中の server をそのまま使う |
| `worktree-ready` | `none` | `DEV_PORT`（worktree-setup が割り当てた port）で起動。起動コマンドは env を読む形にする（`envs/.frontend.env.worktree` を経由。読み込み方は worktree-setup の `references/env-templates.md`） |
| `worktree-ready` | `ours` | そのまま使う |
| `worktree-unconfigured` | `none` | `DEV_PORT` は main と共有の値なので**衝突しうる**。`worktree-setup` の実行を 1 回提案し、断られたら `DEV_PORT` が空いていることを確認したうえで起動する |
| どれでも | `foreign` | **流用も kill もしない**。`SERVER_CWD` を示して「別 checkout の server が port を占有している」と報告し、worktree なら `DEV_PORT + 10` から空きを探して（worktree-setup の `allocate_port` と同じ刻み）その port で起動する許可を取る。main なら占有側の停止か別 port での起動かをユーザーに選んでもらう |
| どれでも | `unknown` | cwd が取れない（`lsof` / procfs 不在）。`ours` と見なさず、ユーザーに「`SERVER_PID` はこの checkout の server か」を確認してから進む |

この表で取る許可・確認（`none` / `foreign` の起動の許可と占有側の停止の選択、`worktree-unconfigured` の worktree-setup の提案、`unknown` の確認）は、利用者が自分で選んだ回答だけを有効とする。無操作の自動続行（askUserQuestionTimeout）の回答は許可・確認とみなさず、起動しない・占有側を止めない・worktree-setup を走らせない・`ours` と見なさない側に読む（既存ブラウザの停止確認と同じ規則。`--caller` の回も省かない）。

判定結果（`CHECKOUT` / `TOPLEVEL` / `DEV_PORT` / `SERVER_MATCH`）は Step 3 の verify モードの (e) の verification.md frontmatter に書く。pr-creator は同じ checkout の `.claude/verification/<branch>.md` を読むので、worktree で検証した記録は worktree 側に残る（main 側には残らない）。

### Step 1: 対象プロジェクトの Web 判定

プロジェクトが Web フロントエンドを持つか判定する。該当しないプロジェクトで起動された場合は中止し、理由をユーザーに伝える。

```bash
# package.json に Web フレームワーク依存があるか
jq -r '(.dependencies // {}) + (.devDependencies // {}) | keys | .[]' package.json 2>/dev/null | \
  grep -E '^(next|react|vue|svelte|@angular/core|nuxt|astro|solid-js|remix)$' | head -3
```

マッチが無い場合は「Web プロジェクトとして検出できません。対象 URL を明示してください」と確認する。`--caller` では聞き返さない: `--targets` があればそれで続け、`--require` だけなら `http://localhost:${DEV_PORT}/` を smoke のケース 1 件にして続ける（(b) の「呼び出し元」の行と同じ）。どちらも無ければ (f) を `skipped`（`UI_VERIFY_REASON=Web フロントエンドを検出できない`）で返して終える。

### Step 2: dev server の確保

port と起動中判定は Step 0 の `DEV_PORT` / `SERVER_MATCH` を使う（ここで `lsof` を引き直さない）。`ours` ならそのまま使い、`none` なら立ち上げる。`foreign` / `unknown` は Step 0 の表に従う。

**起動してない場合の対応:**

1. `package.json` の `scripts.dev` (または `start`, `preview`) を読む
2. パッケージマネージャを推定（`pnpm-lock.yaml`→pnpm / `yarn.lock`→yarn / `bun.lockb`→bun / else npm）
3. **ユーザーに起動許可を確認**（勝手に port を占有しない）。許可は利用者が自分で選んだ回答だけ。無操作の自動続行（askUserQuestionTimeout）の回答は許可とみなさず、起動しない（`--caller` の回も同じで、(f) は `blocked` / `UI_VERIFY_BROWSER=unselected`）
4. 許可されたら background で起動: `pnpm dev &` 相当を Bash の `run_in_background: true` で実行
5. HTTP が応答するまで Bash で待機する（`wait_for` は**ページ上のテキスト出現待ち**であって
   疎通待ちではないので使えない）:
   ```bash
   for _ in $(seq 30); do
     curl -sSf -o /dev/null "http://localhost:${DEV_PORT}/" && break
     sleep 1
   done
   ```
   疎通後、ページ描画の完了は `wait_for(text: ["..."])` で待つ

**認証や環境変数が必要な場合:**
- `.env` / `.env.local` が存在するか確認
- 必要な環境変数が未設定なら起動せず、ユーザーに状況を伝える
- ログイン画面が出る場合は認証済みセッションの使い回しをユーザーに相談

#### dev server ライフサイクル（セッション中は保持する）

dev server はセッション開始時に **1 回だけ** 起動し、以後は **保持** する。タスク完了ごとに停止・再起動しない。再起動を繰り返すと HMR WebSocket 断（`ERR_CONNECTION_REFUSED`）、認証セッションの再ハンドシェイク、ユーザーが並行で開いている server との二重起動衝突、port 競合解消ループ（1 サイクル ~10s）が発生する。1 セッション内で 4 回の再起動が観測された実例あり。

- セッション開始時に **1 回だけ** 起動。以後は **保持** する
- 保持して使い回すのは `SERVER_MATCH=ours` の server だけ。`foreign`（別 checkout の server）は使わず、止めもしない
- コード変更は **HMR** で反映 / chrome-devtools `navigate_page reload` で手動 reload
- `TaskStop`（server 停止）するのは下記のみ:
  1. ユーザーが明示的に「dev server 止めて」と言ったとき
  2. セッション終了時（PR 作成完了などの最終出口）
- ターン途中で再検証が必要なときは、起動中の server を **そのまま使う**（再起動しない）
- Tailwind v4 + Turbopack で「新規 utility class の初出で HMR に乗らない」等の特殊事情があるときだけ例外的に restart

##### 検出ロジック

Step 0 の `detect-checkout.sh` が正本（port の占有ではなく LISTEN process の cwd で判定する）:

- `SERVER_MATCH=none`: 未起動 → 起動許可をユーザーに確認してから background 起動（無操作の自動続行の回答は許可ではない。上の 3）
- `SERVER_MATCH=ours`: 起動中 → そのまま使う（kill / restart 禁止）
- `SERVER_MATCH=foreign`: 別 checkout の server → 使わない・止めない。別 port で起動する（Step 0 の表）

E2E への昇格（`webapp-testing` / Playwright）時も、Playwright の `webServer.reuseExistingServer: true` 相当で起動中 server を再利用する方針に揃える。

### Step 3: モード別の実行

#### verify モード（実機 E2E）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/ui-verify/references/modes/verify.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

#### tune モード

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/ui-verify/references/modes/tune.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

#### snap モード

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/ui-verify/references/modes/snap.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

### Step 4: 撮影結果の後処理

- `.claude/screenshots/` が存在しなければ作成（`mkdir -p`）
- `.claude/screenshots/.gitignore` に `*` を書いて git 追跡を防ぐ（初回のみ）
- 結果を報告する際は保存パスを file_path:line_number 形式ではなくプレーンパスで提示
- **pending flag の更新**: PostToolUse hook が UI 変更検知時に作成する `.claude/.ui-verify-pending` を `verified-snap` ステータスで上書きする（verify / tune / snap のいずれも実行完了時点。verify で pass も fail も 0 件の回は上書きしない — (e)）。これにより commit 前の gate hook が黙る。
  ```bash
  mkdir -p .claude
  printf 'verified-snap\n%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .claude/.ui-verify-pending
  ```
  pending flag は 3 値仕様（正本はここ）:

  | 値 | 意味 | 書き込む主体 |
  |----|------|------------|
  | `unverified` | 未確認。gate hook が `git commit` 直前に reminder を出す | `ui-change-reminder.sh`（UI ファイル変更検知時） |
  | `verified-local` | ローカル目視済み。gate hook は黙る | 手動（撮影せず黙らせたいとき） |
  | `verified-snap` | snap 撮影済み。gate hook は黙る | ui-verify（verify / tune / snap の完了時。verify は pass か fail が 1 件以上の回だけ） |

  撮影せず黙らせる場合は次を実行する:
  ```bash
  printf 'verified-local\n%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .claude/.ui-verify-pending
  ```

## MCP Tool の使い方

chrome-devtools MCP のツール一覧と典型的な呼び出しパターンは `references/chrome-devtools-cheatsheet.md` を参照。

**ページを操作するツールはすべて `pageId` が必須**（`new_page` / `list_pages` 以外。chrome-devtools-mcp 1.8.0 で既定になった）。ID は `new_page` / `navigate_page` の応答に出るページ一覧から取る。既に開いているタブを使うときや ID を見失ったときは `list_pages` で引き直す。本文の呼び出し例で `pageId` を省いているものも、実際の呼び出しでは付ける。

### 既存のブラウザがプロファイルを掴んでいるとき（全モード共通）

chrome-devtools-mcp のプロファイル（既定は `~/.cache/chrome-devtools-mcp/chrome-profile`）は同時に 1 つのブラウザしか使えず、別セッションの MCP が開いたブラウザが残っていると、こちらの呼び出しが `The browser is already running for <dir>` で失敗する。検知と停止は同梱スクリプトで行う:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/chrome-profile-lock.sh" status [--dir '<dir>']
```

- **いつ見るか**: verify / tune / snap で chrome-devtools を使う回に、最初の chrome-devtools のツール呼び出しの**前に** 1 回（`--dir` は省く）。ツール呼び出しが `The browser is already running for <dir>` で失敗した回も、`--dir '<エラーに出た dir>'`（文末の `.` は含めない。エラー文から取った dir はシングルクォートで囲み、中の `'` は `'\''` に置き換える）で同じ分岐を通る
- **`--dir` を省いたときに見る dir**: Bash から読める接続方式は `.claude/dev-workflow.json` の `browser_connect` だけ（userConfig の値は `.mcp.json` の env で MCP プロセスにだけ渡り、Bash の環境には無い）。userConfig だけで `autoConnect` / `userDataDir=<path>` にした環境では、MCP が使う dir ではなく既定の dir を見る（`DIR_SOURCE=default`）。同じ値を `.claude/dev-workflow.json` にも書けば、起動前の status が MCP と同じ dir を見る。`userDataDir=<path>` の path は絶対パスで書く（相対・`~` は MCP の cwd を起点に解決されるので照合できず、`LOCK=unknown` になる）
- **分岐はキー名つきで読む**（`LOCK=unknown` と `HOLDER_SESSION=unknown` は別のキー）:

| status の出力 | 対応 |
|---|---|
| `LOCK=none` / `LOCK=stale` | そのまま進む（失敗した後の回なら、失敗した呼び出しを 1 回だけやり直す。同じエラーなら「止めない」と同じ扱い） |
| `LOCK=held` かつ `HOLDER_SESSION=self` | そのまま進む（このセッションの MCP のブラウザ。止めない）。失敗した後の回なら、そのウィンドウをユーザーに閉じてもらってから 1 回だけやり直す |
| `LOCK=held` かつ `HOLDER_SESSION=other` / `HOLDER_SESSION=orphan` | 下の確認を出す |
| `LOCK=held` かつ `HOLDER_SESSION=unknown` / `LOCK=foreign-host` / `LOCK=unknown` | 止めずに報告し（`LOCK=unknown` は `REASON` も添える）、chrome-devtools を基盤から外す（(a) の次の基盤へ。スクショが要る回は「証跡なし（理由）」を記録。tune / snap は中止して報告） |

**確認**（AskUserQuestion を 1 問）:
- question: 既存ブラウザの pid（`HOLDER_PID`）と起動時刻（`HOLDER_STARTED`）、起動元の MCP の pid と起動時刻（`HOLDER_MCP_PID` / `HOLDER_MCP_STARTED`。orphan なら「見当たらない」）を含める。`DIR_SOURCE=default` なら「userConfig の browser_connect を autoConnect / userDataDir にしているなら、このブラウザは今回使わないので止める必要はない」と添える
- header: 「既存ブラウザ」
- options（この順。どちらにも (Recommended) を付けない）:
  1. 「止めない」 / description: 「chrome-devtools を使わずに次の基盤で続ける（tune / snap は中止して報告）」
  2. 「止めて続行」 / description: `other` なら「別セッションの chrome-devtools は、そのセッションがブラウザを開き直すまで使えなくなる」、`orphan` なら「起動元の chrome-devtools-mcp が見当たらない（MCP の終了後に残ったか、手動で起動したブラウザ）」
- `stop` を呼ぶのは、利用者が自分で「止めて続行」を選んだ回答のときだけ。無操作の自動続行（askUserQuestionTimeout）の回答は「止めない」扱い

「止めて続行」のとき:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/chrome-profile-lock.sh" stop --pid <HOLDER_PID> [--dir '<dir>']
```

`--dir` は status に付けた回だけ同じ値（同じクォート）を付ける。exit 0（`STOPPED=yes`）なら続行する（失敗した後の回なら、失敗した呼び出しを 1 回だけやり直す）。exit 1（SIGTERM で終わらない）/ exit 3（`REFUSED=…`。`signal-failed` は SIGTERM を送れなかった（権限など）、ほかは確認の後に lock が変わった）は結果を報告し、「止めない」と同じ扱いにする。status / stop の exit 2（引数の誤り・同梱の lib を読めない）も止めずに stderr を報告し、「止めない」と同じ扱いにする。

## 絶対厳守ルール

- dev server の勝手な起動禁止。必ずユーザー確認を取る
- dev server の起動許可・期待ユーザーの確認・ケース表の確認・backend の隔離の確認・既存ブラウザの停止確認は、利用者が自分で選んだ回答だけを有効とする。無操作の自動続行（askUserQuestionTimeout）の回答は許可・確認とみなさない（起動しない・期待ユーザーとして記録しない・実行しない・破壊的操作を解禁しない・止めない）。`--caller` で呼ばれた回もこれらの確認を省かない
- `verify` は列挙した全ケースに verdict（pass / fail / blocked）を付けるまで完了にしない。準正常 / 異常が 0 件または未実施なら、verification.md とサマリに `未カバー` を理由つきで明記する（正常系だけの完了を黙って通さない）
- 一度起動した dev server をタスク完了ごとに停止・再起動しない。セッション中は保持する（詳細は Step 2「dev server ライフサイクル」）
- 別 checkout（main / 他 worktree）の dev server を流用しない・kill しない。`SERVER_MATCH=ours` 以外の server で E2E を回さない（Step 0）
- chrome-devtools のプロファイルを掴む既存のブラウザは、利用者が選択 UI で自分で「止めて続行」を選んだときだけ `chrome-profile-lock.sh stop` で止める（無操作の自動続行は確認ではない）。`HOLDER_SESSION=self` は止めない。`kill` / `pkill` を直接打たない
- 認証情報やシークレットを screenshot に含めないよう、撮影前にログアウト状態 or masked 状態を確認
- 本番環境 URL に対する `verify` 実行時は書き込み系操作（フォーム送信等）を行わない
- `.claude/screenshots/` 以外への screenshot 保存禁止（プロジェクトに不要ファイルを残さない）
- Web プロジェクトでない場合はスキップ（このプラグイン自体のような marketplace リポでは実行しない）

## Additional Resources

### Reference Files

- **`references/chrome-devtools-cheatsheet.md`** - MCP tool の呼び出しパターンと典型的なフロー
