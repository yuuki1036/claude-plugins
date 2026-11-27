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

- tune / snap は撮影そのものが目的なので、常に chrome-devtools を使う。PR に添付するスクショは pr-creator の Step 4.5 が選ぶ: このチェックアウトが今のブランチに切り替わった後に撮った snap / verify / tune のディレクトリがあればその最新を使い、無ければ snap で撮る（判定は `scripts/pick-screenshot-dir.sh`）
- **chrome-devtools を使う回は、最初の chrome-devtools のツール呼び出しの前に**「既存のブラウザがプロファイルを掴んでいるとき」（SKILL.md の `## MCP Tool の使い方`）の status を 1 回見る
- 認証の要否は、対象 URL を開いてログイン画面（`/login` `/signin` へのリダイレクト、password 型 input）を検知して決める。事前にユーザーへ聞かない。どの基盤でもログイン画面で止まったら、ユーザーにログインを依頼して続行する（パスワードは入力しない）
- `--autoConnect` を使うには `userConfig.browser_connect` を `autoConnect` にする（既定は `default`）。ADR-20260831 の privacy posture から既定では実プロファイルに繋がない
- **Claude Browser / Claude in Chrome はスクショをファイルに保存できない**。スクショが要る回にこの 2 基盤へ落ちたら E2E の操作と合否判定だけを行い、証跡は (d) で別途撮るか「証跡なし」と記録する
- Claude in Chrome は利用者の実 Chrome プロファイルにつながる。スクショを保存しないので raw URL の懸念（ADR-20260831）は当たらないが、書き込み系は (c) の実 Chrome の歯止めの対象（ADR-20261020221214）
- **期待ユーザーの確認**（アカウント切替対策）: E2E 起動時にユーザーへ 1 回「どのアカウントでログイン中か」を確認し、`expected_user` として verification.md に記録する。最初のケースで画面の表示ユーザー名を読み取り `signed_in_as` に記録し、`expected_user` と照合する。違えば停止して報告（自動で切り替えない）。表示名が読めない場合はその旨を記録し、意図したアカウントかを起動時に確認する。確認は利用者が自分で返した回答だけ。無操作の自動続行（askUserQuestionTimeout）の回答は確認とみなさず、`expected_user` を null のまま記録する（自動続行の回答を期待ユーザーとして書かない。2 回目以降の実行に引き継がれる）。この回は照合できないので、サマリに `期待ユーザー未確認` と書く（`--caller` の回も省かない）

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

列挙したケース表はユーザーに提示して確認を取ってから実行する（削る・足す）。確認は利用者が自分で返した回答だけ。無操作の自動続行（askUserQuestionTimeout）の回答は確認とみなさず実行しない（全ケースを `blocked: ケース表の確認なし` で残す。`--caller` の回も省かない）。この回は pending flag を `verified-snap` で上書きしない（UI を変えた後なら `unverified` のまま残る。(e) の最後の行）。

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
  - `--autoConnect` / Claude in Chrome（どちらも利用者の実 Chrome プロファイル）では破壊的操作を**既定 blocked**。dev server の backend が隔離環境（テスト DB / seed データ）だとユーザーが 1 回確認したときだけ解禁し、verification.md の `backend_isolation: confirmed` に記録する。確認は利用者が自分で返した回答だけで、無操作の自動続行（askUserQuestionTimeout）の回答は確認とみなさず `unconfirmed` とする（`--caller` の回も省かない）。確認が取れなければ読み取り系のみ実行し、破壊的ケースは `blocked: 書き込み先未確認` で残す
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
- 記録後に pending flag を `verified-snap` で上書きする（SKILL.md の Step 4 参照）。ただし pass も fail も 0 件の回（全ケースが `blocked`。ケース表の確認が無かった回を含む）は上書きしない（UI を変えた後なら `unverified` のまま残る。何も確かめていないのに commit 前の gate hook を黙らせない）

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
