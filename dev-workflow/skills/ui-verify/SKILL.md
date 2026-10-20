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
| `--caller=<feature-dev\|lightweight-flow>` | 別のスキルから呼ばれた。モードを聞き返さず、Step 0 の前に「事前判定」を行い、応答の最後に (f) の 5 行を出す。**確認は省かない**（dev server の起動許可・ケース表の確認・期待ユーザー・既存ブラウザの停止確認。他スキルの `--embed` のように確認 UI を止める意味は持たない）。verify 以外のモードでは無視する |
| `--require=<理由>` | 事前判定が `no` でも smoke を走らせる（feature-dev の runtime-sensitive 判定が REQUIRED の回） |
| `--targets=<path>[,<path>...]` | 必ず開く URL / path（事前判定が `no` でも開く）。各 target を smoke ケース 1 件として (b) に足す |
| `--screenshot=need\|none` | (a) のスクショの要否。省くと依頼から決める |

### verify は実機 E2E（役割分担）

`verify` は**実機ブラウザで E2E を通す**。console/network のエラー検知に留めず、ケースごとに操作して期待結果を確認し、合否（pass/fail/blocked）と証跡を `.claude/verification/<branch>.md` に残す。結果は `pr-creator` が動作確認セクションの材料に読む。

役割は 3 つに分ける（前提: E2E の合否は実機ブラウザでしか決めない）:

| 目的 | 手段 |
|---|---|
| E2E の実行と合否判定 | 実機ブラウザ（chrome-devtools / Claude Browser / Claude in Chrome。後述 Step 3 の優先順位） |
| スクショ（添付用証跡） | Storybook があればそれ、なければ chrome-devtools / Playwright |
| 動画（添付用証跡） | Playwright の recordVideo（webm） |

**Playwright / Storybook は証跡撮影係であって E2E の代替にしない**。複数ステップの Playwright script が要る撮影は公式 skill `webapp-testing`（`~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/`）に委譲する。repo に Playwright が入っていればそれを使う。

`snap` モードは追加引数 `--viewports=...` を受け付ける（デフォルトは desktop 1 枚）。詳細は後述「snap モード」参照。

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

判定結果（`CHECKOUT` / `TOPLEVEL` / `DEV_PORT` / `SERVER_MATCH`）は Step 3 (e) の verification.md frontmatter に書く。pr-creator は同じ checkout の `.claude/verification/<branch>.md` を読むので、worktree で検証した記録は worktree 側に残る（main 側には残らない）。

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
3. **ユーザーに起動許可を確認**（勝手に port を占有しない）
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

- `SERVER_MATCH=none`: 未起動 → 起動許可をユーザーに確認してから background 起動
- `SERVER_MATCH=ours`: 起動中 → そのまま使う（kill / restart 禁止）
- `SERVER_MATCH=foreign`: 別 checkout の server → 使わない・止めない。別 port で起動する（Step 0 の表）

E2E への昇格（`webapp-testing` / Playwright）時も、Playwright の `webServer.reuseExistingServer: true` 相当で起動中 server を再利用する方針に揃える。

### Step 3: モード別の実行

#### verify モード（実機 E2E）

正常・準正常・異常系を実機ブラウザで通し、合否と証跡を `.claude/verification/<branch>.md` に残す。手順は「基盤選択 → ケース列挙 → 実行と判定 → 証跡 → 記録」（`--caller` のときは最後に → 呼び出し元への結果）。

##### (a) ブラウザ基盤の選択

**スクショが要るかを先に決める**（上から順に、最初に当たったものを採る）:

1. 引数 `--screenshot=need|none` があればその値
2. 依頼（呼び出し元の引数・ユーザーの発話・Issue 本文）に証跡・スクショ・PR 添付・動画の指定があれば「要る」
3. それ以外は「要らない」

```
スクショが要る ───→ chrome-devtools（認証不要は既定プロファイル／認証必要は --autoConnect）
                     ↓ 起動不可（Chrome 144 未満 / npx 不在 / 接続失敗 / 既存のブラウザを止めなかった）
                   下の「要らない」側の基盤（chrome-devtools を除く）で続け、証跡は「なし（理由）」と記録する
スクショが要らない ─→ Claude Browser（mcp__Claude_Browser__*。デスクトップアプリのブラウザ pane）
                     ↓ 無い（CLI など）
                   Claude in Chrome（mcp__claude-in-chrome__*）
                     ↓ 未接続 / 別アカウント
                   chrome-devtools（認証の扱いは上と同じ）
                     ↓ どれも使えない
                   blocked（基盤なし）
```

- tune / snap は撮影そのものが目的なので、常に chrome-devtools を使う。PR に添付するスクショは従来どおり pr-creator の Step 4.5 が snap で撮る
- **chrome-devtools を使う回は、最初の chrome-devtools のツール呼び出しの前に**「既存のブラウザがプロファイルを掴んでいるとき」（`## MCP Tool の使い方`）の status を 1 回見る
- 認証の要否は、対象 URL を開いてログイン画面（`/login` `/signin` へのリダイレクト、password 型 input）を検知して決める。事前にユーザーへ聞かない。どの基盤でもログイン画面で止まったら、ユーザーにログインを依頼して続行する（パスワードは入力しない）
- `--autoConnect` を使うには `userConfig.browser_connect` を `autoConnect` にする（既定は `default`）。ADR-20260831 の privacy posture から既定では実プロファイルに繋がない
- **Claude Browser / Claude in Chrome はスクショをファイルに保存できない**。スクショが要る回にこの 2 基盤へ落ちたら E2E の操作と合否判定だけを行い、証跡は (d) で別途撮るか「証跡なし」と記録する
- Claude in Chrome は利用者の実 Chrome プロファイルにつながる。スクショを保存しないので raw URL の懸念（ADR-20260831）は当たらないが、書き込み系は (c) の実 Chrome の歯止めの対象（ADR-20261020221214）
- **期待ユーザーの確認**（アカウント切替対策）: E2E 起動時にユーザーへ 1 回「どのアカウントでログイン中か」を確認し、`expected_user` として verification.md に記録する。最初のケースで画面の表示ユーザー名を読み取り `signed_in_as` に記録し、`expected_user` と照合する。違えば停止して報告（自動で切り替えない）。表示名が読めない場合はその旨を記録し、意図したアカウントかを起動時に確認する

##### (b) ケース列挙

次の順に材料を集めて 1 つのケース表に統合する。各ケースは `id` / `種別`（正常/準正常/異常）/ `手順` / `期待結果` / `列挙元` を持つ。

| 列挙元 | 探し方 |
|---|---|
| spec.md | `features/**/spec.md` を Glob。diff で触ったモジュールの Feature / Scenario / 同値分割表の各行 |
| Issue 本文 | `.claude/indie/*/issues/*.md` / `.claude/linear/*/issues/*.md` をブランチ名で照合。受け入れ条件・エッジケース |
| diff 推定 | 追加されたバリデーション・分岐・エラーハンドリング・空配列判定の反対側 |
| 固定 5 項目 | 入力エラー / 空状態 / 権限なし / 通信失敗 / 二重送信。該当しない項目は「対象外」と明記して残す |
| 呼び出し元 | `--targets` の各 path を 1 ケース（種別 正常・期待「表示され、console error 0・network 4xx/5xx 0」）。`--require` があって `--targets` が無ければ `http://localhost:${DEV_PORT}/` を 1 ケースにする |

事前判定が `no` で `--require` か `--targets` がある回は、ケース表を列挙元「呼び出し元」のケースだけにし、準正常 / 異常が 0 件の理由は「UI 変更なし（runtime smoke のみ）」と書く。

**`${CLAUDE_EFFORT}` 分岐**: `low` / `medium` は spec + Issue + 固定 5 項目。`high` 以上で diff 推定も加える。「呼び出し元」の行は effort に関わらず入れる。

列挙したケース表はユーザーに提示して確認を取ってから実行する（削る・足す）。

**coverage 宣言（列挙時に必須）**: ケース表と一緒に次の 2 表を出す。正常系だけのケース表を黙って確定させないためのゲートで、準正常 / 異常が 0 件なら件数ではなく**理由**を書く（「該当なし」では通さない。どの入力・どの失敗経路を候補として見て落としたかを 1 行）。

| 種別 | 件数 | ケース id |
|---|---|---|
| 正常 | n | … |
| 準正常 | n | …（0 件なら理由） |
| 異常 | n | …（0 件なら理由） |

| 固定 5 項目 | 該当 | ケース id / 対象外の理由 |
|---|---|---|
| 入力エラー | yes/no | … |
| 空状態 | yes/no | … |
| 権限なし | yes/no | … |
| 通信失敗 | yes/no | … |
| 二重送信 | yes/no | … |

##### (c) 実行と判定

- ケースごとに `navigate → 操作 → 期待結果の確認 → console/network のエラー収集 → 撮影` を回す
- 合否は 3 値: `pass` / `fail`（期待と実際の差分を 1 行）/ `blocked`（認証・環境で実行できなかった）
- 列挙元が「呼び出し元」のケースは、console error か network 4xx/5xx が 1 件でもあれば `fail`
- **列挙した全ケースに verdict を付けてから完了する（必須）**。実行しなかったケースは空欄ではなく `blocked` + 理由 1 行で残す。正常系だけ通して打ち切る場合も、残りの準正常 / 異常を `blocked` として表に残す（省略すると「通した」と区別できない）
- 完了時に種別ごとの verdict 集計（例: 正常 3 pass / 準正常 1 pass 1 blocked / 異常 0 件）を出す。**種別単位で「0 件 または 1 件も pass していない」ものを判定し、該当する種別だけを `未カバー: <種別>（理由）` としてサマリと verification.md の両方に明記する**（例: 異常=0 件で準正常は pass なら `未カバー: 異常（…理由）`）。全種別がカバー済みなら `未カバー: なし`。pr-creator がこの行を PR 本文へ転記する
- **書き込み系（フォーム送信・削除・確定）の歯止めは 2 段**:
  - 本番 URL では一切書き込まない（従来どおり）
  - `--autoConnect` / Claude in Chrome（どちらも利用者の実 Chrome プロファイル）では破壊的操作を**既定 blocked**。dev server の backend が隔離環境（テスト DB / seed データ）だとユーザーが 1 回確認したときだけ解禁し、verification.md の `backend_isolation: confirmed` に記録する。確認が取れなければ読み取り系のみ実行し、破壊的ケースは `blocked: 書き込み先未確認` で残す
- 二重送信は連打せず「送信直後にボタンの disabled / 二重リクエストの有無を network で確認」

##### (d) 証跡撮影（E2E とは別係）

- スクショは (a) で「要る」と決めた回だけ撮る。要らない回は撮らず、ケース表の証跡列は `-`。要る回は、基盤が chrome-devtools なら `take_screenshot(filePath=.claude/screenshots/verify-<timestamp>/<case-id>.png)`。pane / Claude in Chrome に落ちたときは Storybook があればその story を chrome-devtools で開いて撮る。ただし chrome-devtools を基盤から外した回（既存ブラウザを止めなかった・`HOLDER_SESSION=unknown`・`LOCK=foreign-host` / `LOCK=unknown`）は Storybook でも撮らない。撮れなければ「証跡なし（理由）」
- 動画: ユーザーが要求したケース、または `fail` したケースで Playwright recordVideo（webm）。認証画面は chrome-devtools 側 cookie から storageState を生成
- **最小形は「スクショが要る回は chrome-devtools で撮る。要らない回と、要る回に pane 系へ落ちた回は証跡なし」**。Storybook 再現・Playwright 動画は必要になった回に足す
- **autoConnect / 実 Chrome の証跡は実ユーザー情報を含みやすい**ので、既定で PR 添付対象外（ローカル保持）とし、PR 添付は dev アカウント画面に限りユーザー承認で opt-in する（pr-creator の機密チェックと重ねる）

##### (e) verification.md への記録

`.claude/verification/<branch>.md` に次を書く（Shared State 規約の frontmatter 必須）:

```markdown
---
shared_state_type: verification
producer: dev-workflow:ui-verify
consumers: [dev-workflow:pr-creator]
schema_version: 2
last_updated: <ISO8601>
branch: <branch>
base: <base-branch>
head: <commit sha>
checkout: main | worktree
toplevel: <Step 0 の TOPLEVEL>
dev_port: <Step 0 の DEV_PORT>
server_match: ours | none（自分で起動した）
browser: chrome-devtools(autoConnect) | chrome-devtools | browser-pane | claude-in-chrome
expected_user: <起動時に確定した期待ユーザー or null>
signed_in_as: <表示ユーザー名 or null>
backend_isolation: confirmed | unconfirmed
---

## ケース
| id | 種別 | 手順 | 期待 | 結果 | 証跡 | 列挙元 |
|----|------|------|------|------|------|--------|

## カバレッジ
| 種別 | 件数 | pass | fail | blocked |
|------|------|------|------|---------|
| 正常 | | | | |
| 準正常 | | | | |
| 異常 | | | | |

固定 5 項目: 入力エラー <ケース id or 対象外の理由> / 空状態 … / 権限なし … / 通信失敗 … / 二重送信 …
未カバー: <なし | 準正常・異常 等。0 件の種別はここに理由つきで残す>

## 環境
- dev server / console error / network 4xx-5xx

## 未実施
- <ケース id と理由>
```

- 2 回目実行は上書きする（最新の head が正）。ただし `expected_user` は消さず引き継ぐ
- 出力先を作る: `mkdir -p .claude/verification` し、`.claude/verification/.gitignore` に `*` を書く（初回のみ）
- 記録後に pending flag を `verified-snap` で上書きする（Step 4 参照）

##### (f) 呼び出し元への結果（`--caller` のときだけ）

応答の**最後に**、この順で 5 行を出す（呼び出し元はこの行だけを読み、verification.md は読まない）:

```
UI_VERIFY_RESULT=pass|fail|blocked|skipped
UI_VERIFY_REASON=<1 行。skipped / blocked の理由、fail なら fail したケース id。pass なら空>
UI_VERIFY_BROWSER=chrome-devtools(autoConnect)|chrome-devtools|browser-pane|claude-in-chrome|none|unselected
UI_VERIFY_RECORD=.claude/verification/<branch>.md|none
UI_VERIFY_UNCOVERED=<verification.md の「未カバー:」の値。なしは none>
```

| `UI_VERIFY_RESULT` | 条件 |
|---|---|
| `skipped` | ブラウザを開かなかった（事前判定が `no` で `--require` も `--targets` も無い／Web フロントエンドを検出できず `--targets` も `--require` も無い） |
| `blocked` | fail 0 件かつ pass 0 件（基盤なし・dev server の起動不許可・ログイン待ちなど） |
| `fail` | fail が 1 件以上 |
| `pass` | fail 0 件かつ pass 1 件以上 |

- `skipped` の回は verification.md も pending flag も書かない（`UI_VERIFY_RECORD=none`）
- `UI_VERIFY_BROWSER` は `skipped` なら `none`。`blocked` で基盤を選ぶ前に止まった回（dev server の起動を断られた等）は `unselected` で、verification.md を書かない（`UI_VERIFY_RECORD=none`）。`blocked` の `none` は「基盤を選ぼうとして使えるものが無かった」に限る（呼び出し元はこの回だけを手動の確認に回す）

#### tune モード

スタイル調整の対話ループ。

1. 初回の `take_screenshot` を `.claude/screenshots/tune-{timestamp}/before.png` に保存
2. ユーザーに調整内容を確認（例: 「ヘッダーの余白を広げたい」「ボタンの色を primary に」）
3. 直す場所を `get_css_styles` で特定してから Edit で修正する。`take_snapshot` で対象要素の uid を取り、`get_css_styles(pageId, uid)` で**効いているルールと定義位置（ファイル:行）・上書きされたプロパティ**を読む（source map が効くので dev server ではソースのファイル名が出る）。grep でクラス名を探して当たりを付けない — 上書きされて効いていないルールを直す手戻りになる
4. dev server の HMR 反映を待つ（`wait_for` + 短い sleep）
5. `take_screenshot` で after.png を保存
6. 差分をユーザーに提示し、OK なら終了、NG ならループ

**HMR が効かない場合:**
- `navigate_page` で再読み込み
- ビルドエラーなら `list_console_messages` で原因特定

#### snap モード

スクリーンショット一括収集。**デフォルトは desktop 1 枚のみ**。複数 viewport が必要な PR タイプの場合のみ opt-in する。

**デフォルト viewport:** desktop 1440×900 のみ（1 枚）

**opt-in 引数:**

| 引数 | 撮影対象 |
|------|---------|
| なし（デフォルト） | desktop のみ |
| `--viewports=mobile,desktop` | 指定した viewport |
| `--viewports=mobile,tablet,desktop` | 3 viewport 全部 |
| `--viewports=light,dark` | テーマ切り替え（後述「テーマ撮影」参照） |

**プリセット viewport サイズ:**
- mobile: 375×812（iPhone 13 相当）
- tablet: 768×1024
- desktop: 1440×900

**PR タイプ別ガイドライン:**

`pr-creator` / `git-commit-helper` から呼ばれた時、PR の性質に応じて以下を目安に viewport を選択する。撮影目的は「証跡」「レビュー補助」「レスポンシブ検証」のいずれかに分類できる。

| PR タイプ | 推奨枚数 | viewport |
|-----------|---------|---------|
| 検証 PR (probe / spike / stage1 / compat) | 0–1 | desktop のみ、または省略 |
| リファクタ（UI 変更なし） | 0 | — |
| UI 新機能 | 1–3 | desktop + 必要なら mobile |
| レイアウト / レスポンシブ変更 | 2–3 | desktop + mobile (+ tablet if breakpoint) |
| Theme / Token 変更 | 2 | light + dark |
| バグ修正（UI レンダリング） | 1–2 | 修正対象の viewport |

PR タイプ判定はブランチ名・コミットメッセージ・差分から推定する。判別不能な場合はユーザーに確認。

**手順:**
1. 出力ディレクトリ作成: `.claude/screenshots/snap-{timestamp}/`
2. 引数で指定された viewport（無ければ desktop のみ）について `resize_page` → `take_screenshot` → 保存
3. ユーザーが特定の state (hover, focus, open-modal等) を指定した場合、`hover` / `click` 後に追加撮影
4. 最後に保存済みファイル一覧を報告

**テーマ撮影:**

`--viewports=light,dark` 指定時は viewport を desktop 固定にし、テーマを切り替えて 2 枚撮影する。

既定は `emulate` による `prefers-color-scheme` のエミュレート（プロジェクト非依存で決定的）:

```
mcp__plugin_dev-workflow_chrome-devtools__emulate(pageId: 1, colorScheme: "light")  # → light.png
mcp__plugin_dev-workflow_chrome-devtools__emulate(pageId: 1, colorScheme: "dark")   # → dark.png
mcp__plugin_dev-workflow_chrome-devtools__emulate(pageId: 1, colorScheme: "auto")   # 撮影後に解除
```

アプリが `prefers-color-scheme` ではなく自前のトグル（class / localStorage 等）でテーマを持つ場合は emulate が効かないため、その場合のみ UI 上のトグル操作に切り替える（どちらを使うかをユーザーに確認する）。

### Step 4: 撮影結果の後処理

- `.claude/screenshots/` が存在しなければ作成（`mkdir -p`）
- `.claude/screenshots/.gitignore` に `*` を書いて git 追跡を防ぐ（初回のみ）
- 結果を報告する際は保存パスを file_path:line_number 形式ではなくプレーンパスで提示
- **pending flag の更新**: PostToolUse hook が UI 変更検知時に作成する `.claude/.ui-verify-pending` を `verified-snap` ステータスで上書きする（verify / tune / snap のいずれも実行完了時点）。これにより commit 前の gate hook が黙る。
  ```bash
  mkdir -p .claude
  printf 'verified-snap\n%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .claude/.ui-verify-pending
  ```
  pending flag は 3 値仕様（正本はここ）:

  | 値 | 意味 | 書き込む主体 |
  |----|------|------------|
  | `unverified` | 未確認。gate hook が `git commit` 直前に reminder を出す | `ui-change-reminder.sh`（UI ファイル変更検知時） |
  | `verified-local` | ローカル目視済み。gate hook は黙る | 手動（撮影せず黙らせたいとき） |
  | `verified-snap` | snap 撮影済み。gate hook は黙る | ui-verify（verify / tune / snap の完了時） |

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
