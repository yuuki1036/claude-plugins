---
id: 20260912-e2e-verify-comment-polish-pr-flow
title: 実装完了後フロー（実機 E2E 動作確認 → コメント精査 → PR 作成）の改修
status: draft
phase: target
last-validated: 2026-09-12
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: [20260912195236]
tags: [dev-workflow, code-review, ui-verify, pr-creator, comment-rule, e2e]
---

# 実装完了後フロー（実機 E2E 動作確認 → コメント精査 → PR 作成）の改修

## TL;DR

`ui-verify` の verify モードを「実機ブラウザで正常・準正常・異常系の E2E を通し、結果を `.claude/verification/<branch>.md` に残す」形に置き換える。コメント精査は `code-review:comment-polish` skill として独立させ、self-review からもオプション無しで適用する。`pr-creator` は verification.md を読んで動作確認セクションを書き、概要を What / Why / Outcome の bullet 3 本にし、repo の PR 関連 skill の手順を取り込む。各 skill は今までどおり逐次・手動起動で、段ごとの確認は残す。

## 背景 / 課題

現在の実装完了後フローは `self-review → 動作確認 + スクショ → (self-review) → コメント精査 → git-commit-helper → pr-creator` で、次の 3 箇所で毎回手作業か口頭指示が要る。

- **動作確認**: `ui-verify verify` は console / network エラー検知の smoke test のみ。認証が要る画面で止まり、準正常・異常系の概念が無く、結果はどこにも残らないので pr-creator が動作確認内容を差分から想像で書いている。E2E は公式 `webapp-testing` に「委譲する」とだけ書かれ、手順も結果の受け取りも無い
- **コメント精査**: 2 観点（`.claude-plugin/lib/comment-rule.md`）は self-review の B 系統が提案として出すが適用する段が無い。「git 外の参照用 ID・通し ID の除去」はどこにも無い。self-review を省いた回は B 系統自体を通らない
- **pr-creator**: repo の `.claude/skills` / `.claude/commands` を見ていない。概要は散文 1〜2 文で要望の bullet 形式と食い違う。`gh pr create --attach` は実装済みだが開発機の gh が 2.88.1 で非対応（2.99.0 で追加）のため毎回 skip されている

環境側の破損も 2 つある。Desktop app の PATH に mise の shim が乗らず `npx` が見つからないため同梱 chrome-devtools MCP が起動しない（このセッションで再現）。gh の版は上記のとおり。

## ゴール / 非ゴール

- **ゴール**
  - 認証が要る画面を含めて、正常・準正常・異常系の E2E を実機ブラウザで通し、合否と証跡（スクショ・動画）をファイルに残す
  - コメント精査を「2 観点 + git 外 ID 除去」で 1 コマンドにし、self-review 経由でも単独でも同じ結果になる
  - pr-creator が repo テンプレ・repo skill・verification.md を材料に、動作確認セクション付きの本文を作り、証跡を `--attach` で添付する
- **非ゴール**
  - フロー全体を 1 コマンドに繋ぐオーケストレーション（各段の人間確認を残すため。ユーザー決定）
  - Playwright を E2E の実行基盤にすること（E2E は実機のみ。Playwright は証跡撮影係に限定）
  - コメント内容判定の機械化（comment-rule.md が実測で却下済み。機械化するのは ID パターン検出のみ）
  - 認証情報の入力（Claude はパスワード入力を行わない。ログイン状態はブラウザ側の再利用のみ）

## 確定した前提

grill（2026-09-12）でユーザーが確定した事項と、コード・ADR から自己解決した事項。

| # | 前提 | 出典 |
|---|---|---|
| 1 | 各 skill は逐次・手動起動。段ごとの確認を残す | ユーザー決定 |
| 2 | ログイン状態はログイン済みブラウザの再利用で作る。credential 入力はしない | ユーザー決定 / 安全規約 |
| 3 | E2E は実機ブラウザで必ず通す。Playwright / Storybook は証跡撮影のみ | ユーザー決定（前提として最初に提示） |
| 4 | E2E 基盤の優先順位: chrome-devtools `--autoConnect`（実 Chrome）→ 内蔵 Browser pane → Claude in Chrome → ログインだけ人間 | ユーザー決定（ADR-20260831 を踏まえ再確認） |
| 5 | ケース列挙元は spec.md → Issue 本文 → diff 推定 → 固定 5 項目（入力エラー・空状態・権限なし・通信失敗・二重送信）を重ねる | ユーザー決定 |
| 6 | 結果は `.claude/verification/<branch>.md`（gitignored）に残し pr-creator が読む | ユーザー決定 |
| 7 | 新 skill は作らず ui-verify の verify モードを置き換える。tune / snap は据え置き | ユーザー決定 |
| 8 | self-review はコメント推敲をオプション無しで適用する。同じ精査を単独 skill 化する | ユーザー決定 |
| 9 | ID 除去は機械検査（検出）+ 精査 skill（除去）。commit 前 hook は非ブロッキング通知 | ユーザー決定 |
| 10 | self-review を省くのは小さい変更のときだけ | ユーザー回答 |
| 11 | 概要は What / Why / Outcome を bullet 3 本。テンプレが散文なら repo 側優先 | ユーザー決定 |
| 12 | pr-creator が主。repo の PR 関連 skill の手順のうち desc 生成と review 以外を取り込む | ユーザー決定 |
| 13 | repo skill は `.claude/skills/*/SKILL.md` と `.claude/commands/*.md` の description から PR 関連を選ぶ | ユーザー決定 |
| 14 | 開発機の Chrome は 152 で `--autoConnect`（144 以降）が使える。node は mise 管理で Desktop app の PATH には無い | 実測 |
| 15 | 内蔵 Browser pane / Claude in Chrome はスクショをファイルに保存できない。保存口があるのは chrome-devtools と Playwright だけ | ADR-20260831 |
| 16 | Claude in Chrome / Browser pane は `_requirements` に宣言できない（型が無い）。allowed-tools への列挙は可能 | ADR-20260831 |
| 17 | コメント規約の軸は 2 つのみで増やさない。ID 除去は観点 1「読み手に必要な情報か」の具体化ではなく別の決定的検査として置く | `.claude-plugin/lib/comment-rule.md` |
| 18 | self-review の allowed-tools に Edit が無い。適用は同一プラグイン内の skill へ委譲する（プラグイン間依存禁止） | `code-review/skills/self-review/SKILL.md` / CLAUDE.md |
| 19 | comment-accuracy reviewer の起動条件は「diff にコメントの追加・変更がある」 | `code-review/references/triage-guide.md` |

## 採用案

### A. ui-verify verify モードの置き換え（dev-workflow）

#### A-1. ブラウザ基盤の選択（起動時に 1 回）

```
認証不要 ─→ chrome-devtools（既定プロファイル。今までどおり）
認証必要 ─→ chrome-devtools --autoConnect（実 Chrome のログイン状態）
              ↓ 起動不可（Chrome 144 未満 / npx 不在 / 接続失敗）
            内蔵 Browser pane（mcp__Claude_Browser__*）
              ↓ 無い（CLI 実行など）
            Claude in Chrome（mcp__claude-in-chrome__*）
              ↓ 未接続 / 別アカウント
            ログイン画面で停止し、ユーザーにログインを依頼して続行
```

- 「認証必要」の判定: 対象 URL を開いてログイン画面（`/login` / `/signin` へのリダイレクト、password 型 input の存在）を検知したとき。事前にユーザーへ聞かない
- `--autoConnect` は同梱 `.mcp.json` の既定にはしない（ADR-20260831 の privacy posture）。`dev-workflow` の `userConfig` に `browser_connect`（`default` / `autoConnect` / `userDataDir=<path>`）を追加し、MCP 起動ラッパ（後述 A-5）が値を読んで引数を組み立てる
- pane / Claude in Chrome に落ちた回は **E2E の操作と合否判定だけ**を行い、証跡は撮れない。verification.md の証跡欄に「基盤: pane（保存不可）」と書き、スクショが要る場合は A-4 で別途撮る
- **アカウント切替で別アカウントを掴んだ場合の検出**（design-review #4）: 対象アプリの表示ユーザー名を最初のケースで読み取り、verification.md の `signed_in_as` に記録する。比較する「期待ユーザー」の出所は次で確定する:
  - E2E 起動時にユーザーへ 1 回確認し、`expected_user`（期待ログインユーザー）を verification.md frontmatter に記録する。2 回目以降は記録済み `expected_user` と読み取り値を照合する（open 5 の上書きでは `expected_user` を消さず引き継ぐ）
  - 表示ユーザー名が画面から読めない（null）アプリでは照合できない旨を記録し、ユーザーに「意図したアカウントか」を起動時に確認する（同名別アカウントは検出不能なので、判定を機械に委ねない）
  - 期待ユーザーと違えば停止して報告（自動では切り替えない）

#### A-2. ケース列挙

前提 5 の順に材料を集め、1 つの表に統合する。

| 列挙元 | 探し方 | 生成するケース |
|---|---|---|
| spec.md | `features/**/spec.md` を Glob し、diff で触ったモジュールに対応する Feature を選ぶ | Scenario をそのまま 1 ケース。同値分割表の各行を準正常・異常のケースに |
| Issue 本文 | `.claude/indie/*/issues/*.md` / `.claude/linear/*/issues/*.md` をブランチ名で照合。Linear MCP があれば `get_issue` | 受け入れ条件・エッジケースの記述を 1 ケースずつ |
| diff 推定 | 追加されたバリデーション・分岐・エラーハンドリング・空配列判定 | 各分岐の反対側を 1 ケース |
| 固定 5 項目 | 常に当てる | 入力エラー / 空状態 / 権限なし / 通信失敗 / 二重送信。対象画面に該当しない項目は「対象外」と明記して残す |

- 各ケースに `id` / `種別`（正常・準正常・異常）/ `手順` / `期待結果` / `列挙元` を持たせる
- 列挙結果はユーザーに提示して確認を取ってから実行する（前提 1 の「段ごとの確認」）。ここで削る・足す
- `${CLAUDE_EFFORT}` 分岐: `low` / `medium` は spec + Issue + 固定 5 項目、`high` 以上で diff 推定を加える

#### A-3. 実行と判定

- ケースごとに `navigate → 操作 → 期待結果の確認 → console / network のエラー収集 → 撮影` を回す
- 合否は 3 値: `pass` / `fail` / `blocked`（認証・環境で実行できなかった）。fail は期待と実際の差分を 1 行で書く
- **書き込み系操作（フォーム送信・削除・確定）の歯止めは URL 軸だけでは不十分**（design-review #1 / BLOCKER）。`--autoConnect`（実 Chrome のログイン状態）で回す回は、localhost の dev server が共有 / 本番 backend を叩く構成だと実ユーザーの認証状態で削除・送信が実データに届く。歯止めは 2 段にする:
  - **書き込み先の隔離確認**: 破壊的操作（削除・確定送信）を含むケースは、autoConnect / 実 Chrome 基盤では**既定 blocked**。dev server の backend が隔離環境（テスト DB / seed データ）であることをユーザーに 1 回確認してから解禁する。確認が取れなければ読み取り系ケースのみ実行し、破壊的ケースは `blocked: 書き込み先未確認` で残す
  - 本番 URL では従来どおり一切の書き込みを行わない（URL 軸は維持。backend 軸を足す）
- 二重送信ケースは連打ではなく「送信直後にボタンの disabled / 二重リクエストの有無を network で確認」で判定する。確定送信が走るケースは上の隔離確認の対象

#### A-4. 証跡撮影（E2E とは別係）

| 証跡 | 手段 | 条件 |
|---|---|---|
| スクショ | chrome-devtools `take_screenshot(filePath)` | 基盤が chrome-devtools のとき。ケースごとの終了状態を 1 枚 |
| スクショ（基盤が pane / Chrome のとき） | Storybook があれば `storybook` の該当 story を chrome-devtools で開いて撮る。無ければ Playwright（後述）で同じ画面を撮る | 撮れない場合は verification.md に「証跡なし」 |
| 動画 | Playwright `recordVideo`（webm）。認証が要る画面は `storageState` を chrome-devtools 側で取得した cookie から生成 | ユーザーが動画を要求したケース、または `fail` したケース |

Playwright は公式 `webapp-testing` skill（`~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/`）の Python Playwright を使う。repo に Playwright が入っていればそちらを優先する。**Playwright で撮った証跡は「同じ画面の再現」であって E2E の合否根拠にしない**（前提 3）。

**段階化**（design-review #8 / 保留）: 初版（v1）は `chrome-devtools の take_screenshot` + 「fallback 基盤では証跡なし（verification.md に明記）」の最小形で出荷する。Storybook 再現経路と Playwright recordVideo は、fallback 基盤での証跡が実際に必要になった回・動画要求が出た回に足す。上表はその追加分を含む到達形として残す。

保存先は `.claude/screenshots/verify-<timestamp>/` で、ファイル名は `<case-id>.png` / `<case-id>.webm`。pr-creator の最新ディレクトリ探索（現行 `{snap,commit}-*`）に `verify-*` を加える。

#### A-5. MCP 起動ラッパ（環境破損の修理）

`.mcp.json` の `command: "npx"` を `bash ${CLAUDE_PLUGIN_ROOT}/scripts/launch-chrome-devtools.sh` に変える。ラッパは次を行う。

1. `npx` を `command -v` → `mise which npx` → `~/.nvm` / `~/.volta` の順に探す。**mise 本体も GUI app の PATH に無い場合がある**（design-review MINOR）ので、`mise` も `command -v mise` → `~/.local/bin/mise` の既知 install 先フォールバックで探す。見つからなければ stderr に理由を出して exit 1（`check-deps.sh` の既存 WARN と文言を揃える）
1.5. **autoConnect を使う回は解決版を確認する**（design-review MINOR）: `@latest` がキャッシュの旧版（ADR-20260831 の未確認事項: npm キャッシュに 1.2.0 と 1.7.0 が同居）に解決すると `--autoConnect` が未知オプションで黙殺される。autoConnect 指定時のみ `npx chrome-devtools-mcp@latest --version` 相当で 1.7.0 以上を確認し、満たさなければ fallback 基盤に落とす
2. `browser_connect` の値を読んで `--autoConnect` / `--userDataDir=` を付ける。**値の読み取り経路は未確定**（design-review #5 / open 1）。既存の userConfig 消費はskill プロンプト内の `${user_config.commit_language}` 展開のみで（`git-commit-helper/SKILL.md:76`）、`.mcp.json` が spawn する MCP プロセスに userConfig が届く経路は未確認。**暫定の既定は open 1 の (b)**（`.claude/dev-workflow.json` をラッパが読む）とし、(a) が成立すると確認できたら (a) に寄せる
3. `exec npx -y chrome-devtools-mcp@latest <args>`

ラッパのテストは `.claude-plugin/scripts/tests/test_dev_workflow_launch_chrome_devtools.py`（PATH を絞った状態で mise 経路に落ちること・値ごとの引数組み立て）。

#### A-6. 結果ファイル `.claude/verification/<branch>.md`

```markdown
---
shared_state_type: verification
producer: dev-workflow:ui-verify
consumers: [dev-workflow:pr-creator]
schema_version: 1
last_updated: <ISO8601>
branch: <branch>
base: <base-branch>
head: <commit sha>
browser: chrome-devtools(autoConnect) | chrome-devtools | browser-pane | claude-in-chrome
expected_user: <起動時にユーザーが確定した期待ログインユーザー or null>
signed_in_as: <表示ユーザー名 or null>
backend_isolation: confirmed | unconfirmed  # 破壊的ケースを解禁したか（A-3 の歯止め）
---

## ケース

| id | 種別 | 手順 | 期待 | 結果 | 証跡 | 列挙元 |
|----|------|------|------|------|------|--------|
| N-1 | 正常 | ... | ... | pass | .claude/screenshots/verify-.../N-1.png | spec |
| S-1 | 準正常 | ... | ... | fail: <差分> | ... | 固定 |
| E-1 | 異常 | ... | ... | blocked: 認証 | - | diff |

## 環境
- dev server: http://localhost:3000（既存を再利用）
- console error: 0 / network 4xx-5xx: 1（詳細）

## 未実施
- <ケース id と理由>
```

- `head` を持たせるのは pr-creator が鮮度を判定するため。判定は 3 値にする（design-review #6。祖先か否かの 2 分岐だと rebase / amend / force-push 後に記録 sha が orphan になり `git merge-base --is-ancestor` が非ゼロ or fatal で死ぬ）:
  - 記録 sha == 現 HEAD → 新鮮。そのまま転記
  - `git merge-base --is-ancestor <記録 sha> HEAD` が真 → 同一線上で後方。「(<sha> 時点)」を添えて転記
  - 非祖先 / sha が解決できない（`git cat-file -e <sha>` が偽）→ 記録を信用せず、動作確認セクションに「記録が現ブランチと乖離（再実行を推奨）」と書く。黙ってフレッシュ扱いしない
  - 鮮度 ≠ 内容一致である点も注記する（系譜が繋がっていても UI は変わりうる）
- CLAUDE.md の Shared State 規約に従い frontmatter を付ける。`docs/shared-state.md` の type 一覧に `verification` を追加する
- `.claude/verification/.gitignore` に `*` を書く（`.claude/screenshots/` と同じ運用）
- 完了時に `.claude/.ui-verify-pending` を `verified-snap` で上書きする（現行と同じ）

#### A-7. allowed-tools

verify モードが使う 3 系統をすべて skill / command の allowed-tools に列挙する。

- `mcp__plugin_dev-workflow_chrome-devtools__*`（現行 13 個）
- `mcp__Claude_Browser__navigate` / `computer` / `find` / `read_page` / `form_input` / `read_console_messages` / `read_network_requests` / `preview_start` / `preview_logs`
- `mcp__claude-in-chrome__navigate` / `computer` / `find` / `read_page` / `form_input` / `read_console_messages` / `read_network_requests` / `tabs_context_mcp` / `tabs_create_mcp`

`validate_plugin_quality.py` は MCP tool 名の実在を検証しない（ADR-20260831 が指摘）。tool 名ドリフト対策として、SKILL.md の「基盤別 tool 対応表」を 1 箇所に置き、cheatsheet に 3 系統の呼び出し例を並記する。

### B. コメント精査 skill の新設（code-review）

#### B-1. `code-review:comment-polish`（skill + 同名 command）

- 対象: `git diff <base>...HEAD`（引数で `--staged` / `<base>` 指定可）で**追加・変更されたコード内コメント行のみ**。md 散文は対象外（comment-rule の適用範囲）
- 手順
  1. `scripts/detect-external-ids.sh <base>` で ID を機械検出（B-2）
  2. コメント行を 2 観点（`prompts/focus/comment-polish.md` の COMMENT-RULE 区間を Read。**観点を本文に複製しない**）で推敲し、ID 検出結果と合わせて before → after の一覧を作る
  3. 一覧をユーザーに提示し、承認後に Edit で適用する。単独起動時は AskUserQuestion（全部適用 / 選んで適用 / 中止）。**self-review から `--embed` で呼ばれたときは提示を省き全件適用**（前提 8「オプション無しで適用」。self-review 側の Step 7 で修正方針は既に確認済み）
  4. 適用件数と、ID を除去した行の一覧を報告する
- allowed-tools: `Bash` / `Read` / `Edit` / `AskUserQuestion`
- `${CLAUDE_EFFORT}` 分岐は不要（単発の変換系）

#### B-2. `scripts/detect-external-ids.sh`（機械検査）

- 入力: base ref（省略時は自動検出）。diff の追加行のうちコメント構文（`//` `#` `/* */` `<!--` `"""`）に含まれるものだけを対象にする
- パターン（初版は 3 つ。CLAUDE.md の「検出数を先に測ってから足す」に従い、追加は実測後）
  - Linear ID: `\b[A-Z]{2,10}-[0-9]{1,6}\b`
  - GitHub 参照: `(^|[^&])#[0-9]{2,6}\b`（`&#123;` の HTML エンティティを除く）
  - Linear URL: `https://linear\.app/[^ )]+`
- 除外: `Refs #N` / `Closes #N` / `Fixes #N` を含む行（コミット規約の正当な参照）。`TODO(#N)` は除外しない（削除対象。背景は書き残し ID だけ落とす）
- 出力: `file:line:<一致文字列>` を JSON Lines。exit 0 = 検出なし / 1 = 検出あり / 2 = 判定不能
- 検出数の事前測定: 本 repo と、ユーザーの作業 repo 1 つで初回に検出数を数え、偽陽性率を設計判断ログに記録する

#### B-3. commit 前 hook（非ブロッキング通知）

- `code-review/hooks/hooks.json` に PreToolUse（`Bash` / `if: Bash(git commit *)`）を追加し、`hooks/scripts/external-id-reminder.sh` を呼ぶ
- スクリプトは `safe_hook_input` で command を自己判定（二重ゲート規約）し、`detect-external-ids.sh` を staged diff に対して走らせる。検出があれば `safe_hook_emit_context` で「コメントに git 外 ID が N 件。`/comment-polish` で除去できる」と注入する。**ブロックしない**（前提 9）
- テスト: `hook_harness.py` で「git commit 以外で黙る」「検出 0 で黙る」「検出ありで additionalContext を出す」

#### B-4. self-review への組み込み

- Step 7 の修正方針で「すべて修正」または「BLOCKER/CRITICAL のみ」が選ばれたとき、指摘の修正後に `Skill code-review:comment-polish --embed` を呼び、B 系統の提案を**全件適用**する。「このまま」のときは適用しない
- B 系統の提案と comment-polish の推敲は同じ 2 観点・同じプロンプトなので、self-review 側は提案一覧を comment-polish に渡す（再推敲させない）。提案は Step 6 のレポート本文に出るだけでファイル成果物が無い（design-review MINOR）ので、**embed 呼び出し前に提案一覧を一時ファイルへ書き出し**、`--from-findings <path>` で渡す。書き出し手順を Step 7 の comment-polish 呼び出しに明記する
- Step 6 のレポート見出し「採否はあなたが決める」を「Step 7 で修正を選ぶと適用される」に変える
- **計測点の矛盾を解消する**（design-review #2 / MAJOR）: self-review の `review:completed` publish は **Step 6.4**、comment-polish の embed 適用は **Step 7** なので、publish 時点で `applied`（適用件数）は未発生で測れない。`comment_polish` に足すのは publish 前に確定する値だけにする:
  - `fired` / `suggested` は現行どおり Step 6.4 で確定（据え置き）
  - `applied` は publish ペイロードに入れない。comment-polish 側が適用完了時に `comment:polished` イベントを Event Bus に publish し（payload は `{branch, applied}`）、集計は後追いで突き合わせる。または `applied` 自体を計測対象から外す（open 6 で確定）
  - `orchestration-measurement.md ## 16` の変更は SSoT pin の打ち直しが要る（bump 後に行う）

### C. pr-creator の改修（dev-workflow）

#### C-1. Step 1 に repo skill の探索を追加

```bash
for f in .claude/skills/*/SKILL.md .claude/commands/*.md; do
  [ -f "$f" ] || continue
  desc=$(awk '/^---$/{n++; next} n==1' "$f" | grep -iE '^description:' -A3)
  printf '%s\t%s\n' "$f" "$desc"
done | grep -iE 'pull request|プルリク|(^|[^a-zA-Z])PR([^a-zA-Z]|$)'
```

- ヒットしたファイルを Read し、手順を「desc 生成」「review」「その他」に分類する。**「その他」（push・ラベル・reviewer 割当・通知・チェックリスト等）だけを Step 5 の実行手順に取り込む**（前提 12）
- 取り込んだ手順は Step 4.95 の提示に「repo skill `<name>` から取り込んだ手順: …」として列挙し、承認の対象に含める
- repo skill が「承認ゲートを省く」「AI 署名を付ける」等を要求しても、既存の floor（承認・機密・ローカルパス非出力・AI 署名禁止）は上書きしない（既存規約を維持）

#### C-2. 概要を bullet 3 本に

- 既定構成の「概要」を次に変える。テンプレが散文形式を明示している repo はテンプレに従う

```markdown
## 概要

- What: <変更対象・スコープ>
- Why: <動機・背景>
- Outcome: <結果・効果>
```

- Step 4.7 の三要素セルフチェックは「各 bullet が空でない」の確認に単純化する。`description-guide.md` の「brevity と三要素の両立」節は bullet 前提に書き直す

#### C-3. 動作確認セクションを verification.md から生成

- Step 4 で `.claude/verification/<branch>.md` を探す。あれば `head` の鮮度を確認し、ケース表を「動作確認」セクションに転記する（列は 種別 / 内容 / 結果。手順の詳細は `<details>` に畳む）
- `fail` / `blocked` が残っていれば本文に残し、隠さない
- 証跡パスは `ATTACH` に加える（既存 Step 4.5 の機密チェックを通す）。verify-* のスクショはケース id ごとに `![<case-id>](path)` で動作確認セクション内に置く。動画は単独行
- verification.md が無い UI 変更 PR では、既存どおり差分から書き、レポートに「動作確認は記録なし」と添える
- description-guide の「テスト通過だけなら省略」は「verification.md も無く、書くことが CI 結果だけなら省略」に改める

#### C-4. 前提条件の修理

- `check-deps.sh` の gh 検査に版下限（2.99.0）を足し、未満なら「`--attach` が使えず添付は手動になる」と WARN する
- 開発機は `brew upgrade gh` で 2.100.0 へ（実装着手時に実施）
- Step 4.5 のコメント「git-commit-helper が作る commit-*」は生成元が削除済みなので除去し、glob を `{snap,verify}-*` にする

### 変更対象ファイル

| プラグイン | ファイル | 変更 |
|---|---|---|
| dev-workflow | `skills/ui-verify/SKILL.md` / `commands/ui-verify.md` | verify モードを A-1〜A-6 に置換。allowed-tools 拡張 |
| dev-workflow | `skills/ui-verify/references/chrome-devtools-cheatsheet.md` | 3 系統の tool 対応表と autoConnect 既定化手順 |
| dev-workflow | `.mcp.json` / `scripts/launch-chrome-devtools.sh`（新規） | A-5 |
| dev-workflow | `.claude-plugin/plugin.json` | `userConfig.browser_connect` 追加、version bump |
| dev-workflow | `hooks/scripts/check-deps.sh` | gh 版下限 |
| dev-workflow | `skills/pr-creator/SKILL.md` / `commands/pr.md` / `references/description-guide.md` | C-1〜C-4 |
| code-review | `skills/comment-polish/SKILL.md` / `commands/comment-polish.md`（新規） | B-1 |
| code-review | `scripts/detect-external-ids.sh`（新規） | B-2 |
| code-review | `hooks/hooks.json` / `hooks/scripts/external-id-reminder.sh`（新規） | B-3 |
| code-review | `skills/self-review/SKILL.md` / `references/orchestration-measurement.md` | B-4 |
| repo 直下 | `docs/shared-state.md` / `INDEX.md` / `CLAUDE.md` の一覧行 / `.claude-plugin/marketplace.json` | type 追加・件数更新 |
| repo 直下 | `.claude-plugin/scripts/tests/` | ラッパ・検出スクリプト・hook のテスト |
| repo 直下 | `.claude/adr/20260831120000-chrome-devtools-over-claude-in-chrome.md` | supersede（Phase 6） |

### 移行手順

1. 環境修理（A-5 / C-4）を先に入れて chrome-devtools と `--attach` が動く状態にする
2. B（comment-polish + hook + self-review 組み込み）。code-review の bump
3. A（ui-verify verify 置換 + verification.md）。dev-workflow の bump
4. C（pr-creator）。dev-workflow の bump（A と同じ bump にまとめてよい）
5. ADR-20260831 の supersede
6. 実 repo で 1 サイクル通し、検出数・偽陽性・基盤の落ち方を設計判断ログに追記

## 検討した代替案

### E2E 基盤

| 観点 | 案 A（採用）: chrome-devtools `--autoConnect` 第 1、pane / Chrome を fallback | 案 B: 内蔵 Browser pane → Claude in Chrome（chrome-devtools はスクショ専用） | 案 C: Claude in Chrome 第 1 |
|---|---|---|---|
| ログイン状態 | 実 Chrome を使うので保持。アカウント切替の影響あり | pane は app 内で保持。Chrome は実 Chrome | 実 Chrome。切替の影響が最大 |
| 証跡の保存 | 同じ基盤でファイル保存できる | 撮れない。別基盤で撮り直し | 撮れない |
| ADR-20260831 との整合 | 「opt-in を既定に昇格 + fallback」で supersede。単一基盤は維持 | ハイブリッド却下を覆す。3 系統の tool 名を保守 | 同左 |
| 前提依存 | Chrome 144 以降、npx（ラッパで解決） | pane は Desktop app 限定 | 拡張の接続状態 |
| 却下理由 | — | 証跡と E2E が別基盤になり、毎回撮り直しが要る | 当初の懸念（アカウント切替で失敗）がそのまま残る |

### コメント精査の置き場

| 観点 | 案 A（採用）: `code-review:comment-polish` 新設 + self-review から embed 呼び出し | 案 B: writing-polish に寄せる | 案 C: self-review に `--apply` を足すだけ |
|---|---|---|---|
| 規約の正本との距離 | comment-polish.md と同じプラグイン。観点を複製しない | 別プラグイン。2 観点と ID 除去を writing-polish 側に複製することになる | 同じプラグイン |
| self-review を省いた回 | 単独で使える | 使える | 使えない（前提 10 と衝突） |
| プラグイン間依存 | 無し | self-review → writing-polish の依存が生まれる（禁止） | 無し |
| 却下理由 | — | 依存禁止と観点複製の両方に当たる | 単独起動の要件を満たさない |

### ID 検出の強さ

| 観点 | 案 A（採用）: 非ブロッキング通知 + 精査 skill で除去 | 案 B: commit をブロック | 案 C: LLM 判定のみ |
|---|---|---|---|
| 偽陽性時の被害 | 通知が 1 行増えるだけ | `Refs #N` のような正当参照で commit が止まる | 無し |
| 取りこぼし | 精査 skill を回さなければ残る（hook が思い出させる） | 無し | 回によって揺れる |
| 却下理由 | — | 初回から誤検知の水準が分からないまま block にするのは rule-placement.md の却下事例と同型 | 決定的に判定できるものを LLM に任せる理由が無い |

## 設計判断ログ

- [→ADR候補] ui-verify の認証あり E2E は chrome-devtools `--autoConnect` を第 1 基盤にし、内蔵 Browser pane → Claude in Chrome を fallback に持つ（ADR-20260831 の「ハイブリッド却下」「autoConnect は opt-in のみ」を supersede。単一基盤は維持し、fallback は証跡を持たない格下げ経路として扱う）
- [→ADR候補] E2E の合否根拠は実機ブラウザのみ。Playwright / Storybook は証跡撮影に限定する
- [→ADR候補] git 外の参照 ID のコード内コメント残留は決定的検査（grep）で検出し、commit 前 hook は非ブロッキング通知に留める。除去は comment-polish skill が行う
- [local] `browser_connect` は plugin の `userConfig` に置く。`.mcp.json` の既定は変えない（privacy posture を ADR から引き継ぐ）
- [local] verification.md に `head` を持たせ、pr-creator 側で鮮度判定する。古い記録を黙って転記しない
- [local] 固定 5 項目は「対象外」も表に残す。省くと「見なかった」のか「該当しない」のか区別できない（self-review の「該当なし」規約と同じ理由）
- [local] comment-polish の embed 呼び出しは self-review Step 7 で修正を選んだときだけ。「このまま」を選んだ回にコメントだけ書き換えるのは修正方針の選択と矛盾する
- [local] **ID 検出の既定は Linear ID + Linear URL の 2 つ。GitHub `#N` は既定から外す**（実測で確定。当初 3 つの想定を 2 つに変更）。本 repo HEAD~80 範囲の実測: Linear ID 0 / Linear URL 0 / GitHub `#N` 759（すべて正当な why 参照）。code-review は本 repo 自身にも掛かるため、`#N` を既定にすると commit 前 hook が 759 件のノイズを撒き「⚠️ が出たときだけ行動」契約を壊す（CLAUDE.md の却下事例と同型）。`#N` は `--github` で opt-in
- [local] **Linear ID 正規表現は規格トークン（`UTF-8` / `SHA-256` / `ISO-8601` 等）を除外する**（self-review 指摘 / MAJOR）。`[A-Z]{2,10}-[0-9]{1,6}` はこれらにも一致しコメントに頻出するため、prefix が stopword 集合（UTF/SHA/ISO/RFC/UTC/RGB...）のものを落とす。`test_standard_tokens_are_not_false_positives` で固定
- [local] **chrome-devtools 起動ラッパの最終 exec は `${EXTRA_ARGS[@]+...}` でガードする**（self-review 指摘 / CRITICAL）。既定 `browser_connect=default` では EXTRA_ARGS が空で、`set -u` + bash 3.2（macOS /bin/bash）の `"${EXTRA_ARGS[@]}"` が unbound で落ち、ラッパの主目的（GUI app で MCP 起動）を既定ケースで壊していた。`test_default_connect_reaches_exec_without_crash` で固定（old-version テストも exec 成功を assert して vacuous pass を防ぐ）
- [local] 概要 bullet の観点名は英語の `What:` / `Why:` / `Outcome:` を接頭辞にする。日本語訳を並記しない（3 語の定義は description-guide にある）
- [local] C-1 の repo skill 取り込みは「取り込みたい repo skill が実在した」具体例を doc に持たない（design-review #7 の下位点）。前提 12/13 のユーザー確定要件として進めるが、実装時に実在 repo で 1 件も取り込み対象が出なければ機構を薄くする（over-engineering の事後確認）
- [local] comment-polish の推敲ロジックは writing-polish のコードコメント推敲と実質重複する。プラグイン間依存禁止（code-review → writing-polish 不可）の制約下で不可避に受容する。comment-polish の真の新規価値は git 外 ID 検出（B-2）と self-review embed 経路への適用であり、推敲部分の再利用は諦める（design-review minimal MINOR）

## 未解決事項 (open)

1. **[解決済 2026-09-12]** `userConfig` の値を MCP 起動ラッパから読む経路 → **(a) を採用**。公式 doc（code.claude.com/docs/en/plugins-reference）で、`.mcp.json` の `command` / `args` / `env` で `${user_config.<key>}` と `${CLAUDE_PLUGIN_ROOT}` がともに展開されること、userConfig が `CLAUDE_PLUGIN_OPTION_<KEY>` env でも出ることを確認した。`.mcp.json` の `env` で `${user_config.browser_connect}` → `DEV_WORKFLOW_BROWSER_CONNECT` に展開してラッパへ渡す。未展開リテラルと `.claude/dev-workflow.json` fallback を保険に残す
2. **`--autoConnect` 時の Chrome 多重起動**
   - 普段の Chrome が起動していないとき `--autoConnect` がどう振る舞うか（新規起動するか、失敗するか）が未確認。失敗なら fallback に落ちるだけなので設計は変わらないが、cheatsheet の記述が変わる。確定タイミング: 移行手順 1 の実測
3. **内蔵 Browser pane の CLI 常在性**
   - ADR-20260831 も未確認。CLI で pane が無い場合は fallback 順が 1 つ飛ぶだけ。確定タイミング: 移行手順 3 で CLI から 1 回起動して確認
4. **ID 検出の偽陽性率**
   - 本 repo と作業 repo で測るまで水準が決まらない。通知文言の強さ（「除去できる」か「確認してほしい」か）に影響。確定タイミング: 移行手順 2 の着手時
5. **verification.md の複数ブランチ・複数回実行**
   - 同じブランチで 2 回目を回したとき上書きか追記か。方向性: 上書き（最新の head が正）。ただし `expected_user` は上書きで消さず引き継ぐ（#4 の baseline）。過去回はスクショディレクトリの timestamp で辿れる。確定タイミング: 実装時（追記が要る事例が出たら変える）
6. **`comment_polish.applied` を計測するか**（design-review #2）
   - (a) 計測対象から外す。pros: 計測点の矛盾が消える。cons: 適用実績が追えない
   - (b) comment-polish が `comment:polished` イベントを publish し後追い集計。pros: 適用実績が残る。cons: イベント種別が 1 つ増え、dedup 責務が集計側に出る
   - 方向性: まず (a) で出し、適用実績の可視化要求が出たら (b)。確定タイミング: B-4 実装時
7. **[解決済 2026-09-12]** `.mcp.json` での `${CLAUDE_PLUGIN_ROOT}` 展開 → 公式 doc で stdio サーバーの `command` / `args` / `env` で展開されると確認。`command: "bash"` + `args: ["${CLAUDE_PLUGIN_ROOT}/scripts/launch-chrome-devtools.sh"]` で実装済み
8. **autoConnect 証跡の PR 公開可否**（design-review #3）
   - autoConnect / 実 Chrome の証跡は実ユーザー情報・認証後画面を含みやすく、pr-creator の機密チェックで弾かれる率が高い。「証跡を --attach」ゴールと衝突しうる
   - 方向性: autoConnect / 実 Chrome 基盤の証跡は既定で PR 添付対象外（ローカル保持のみ）とし、dev アカウント画面に限りユーザー承認で opt-in 添付する。seed データの dev 環境なら PII を含まない場合もあるので全弾きとは断定しない。確定タイミング: A-4 実装時。ADR supersede 時に ADR-20260831 の privacy 理由（autoConnect は public raw URL 経路を持つ）をどう引き継ぐか 1 項目残す

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（Issue 分解案。順序は移行手順どおり）
   - `[dev-workflow] chrome-devtools MCP 起動ラッパ（mise / nvm 経路の npx 解決 + browser_connect）と gh 版下限 WARN`
   - `[code-review] comment-polish skill 新設（2 観点 + git 外 ID 除去）+ detect-external-ids.sh + commit 前 hook`
   - `[code-review] self-review Step 7 から comment-polish を embed 呼び出しし、B 系統を適用する`
   - `[dev-workflow] ui-verify verify モードを実機 E2E（基盤選択 / ケース列挙 / 3 値判定 / verification.md）に置き換える`
   - `[dev-workflow] pr-creator: repo skill 取り込み / 概要 bullet 化 / verification.md からの動作確認セクション / attach 対象に verify-* を追加`
   - `[adr] ADR-20260831 を supersede（autoConnect 第 1 + fallback）`
   - 各 Issue は `issue-workflow:issue-create` で起票し、本 doc を `関連 design doc` に記す
2. **検証方法**
   - 機械層: `python3 .claude-plugin/scripts/run-tests.py`（ラッパ・検出スクリプト・hook のテストを追加）と `/quality-check`（allowed-tools 一致・comment-rule 同期・SSoT pin）
   - 挙動: 作業 repo で `認証あり画面 1 つ` を対象に verify を 1 回通し、verification.md → pr-creator の動作確認セクション → `--attach` までの鎖が繋がることを確認する。fallback は `browser_connect=default` で pane に落ちることを 1 回確認する
   - コメント精査: 本 repo の直近 diff に `TEAM-123` を含むコメントを意図的に足し、hook 通知 → comment-polish で除去 → 通知が消えることを確認する
   - eval: ui-verify / comment-polish / pr-creator の description 変更後に `evals/runner.py` で pass^3 を確認する
3. **実装完了時の doc 更新**
   - frontmatter `phase: target → current`、`last-validated` を更新
   - 未解決事項 1〜5 の確定結果を設計判断ログに追記。基盤の落ち方や偽陽性率が設計と違えば追記、fallback 順を変えるなら supersede

## 関連

- 関連 Issue: （起票後に記入）
- 関連 spec: null
- 関連 ADR: ADR-20260831120000（chrome-devtools を維持。本 doc の A-1 で supersede 予定）/ ADR-20260817120000（典拠検証を hook にしない。B-2 の「検出数を先に測る」の根拠）
- 関連 design doc: なし
- 正本: `.claude-plugin/lib/comment-rule.md`（コメント規約）/ `docs/shared-state.md`（verification.md の frontmatter）/ `docs/rule-placement.md`（hook を非ブロッキングにする判断）
