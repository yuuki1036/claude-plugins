---
id: 20260912195236
status: accepted
phase: current
last-validated: 2026-09-12
supersedes: [20260831120000]
superseded-by: null
append_only: true
tags: [architecture, dev-workflow, ui-verify, mcp, browser, e2e]
---

# ADR-20260912195236: ui-verify の認証あり E2E は chrome-devtools --autoConnect を第 1 基盤にし、内蔵 pane / Claude in Chrome を fallback に持つ

## ステータス

accepted（2026-09-12）。ADR-20260831120000（chrome-devtools MCP を単一基盤として維持・autoConnect は opt-in のみ・ハイブリッド却下）を supersede する。

## コンテキスト / 背景

ADR-20260831 は「ui-verify の基盤は chrome-devtools MCP 単一。`--autoConnect` は実プロファイルに繋ぐ privacy posture のため opt-in 手順に留め、pane / Claude in Chrome は保存口が無いので却下」と決めた。これは **verify モードが単一ページの console/network smoke test だった**前提での結論。

その後ユーザー要望で **verify モードを実機 E2E に再定義**した（正常・準正常・異常系を実機ブラウザで通し合否と証跡を残す）。このとき新たに確定した前提:

- **認証が必要な画面を E2E する**ことが主目的に入った。ログイン状態はログイン済みブラウザの再利用で作る（Claude はパスワード入力をしない）
- **E2E の合否は実機ブラウザでのみ決める**。Playwright / Storybook は証跡撮影係であって E2E の代替にしない（ユーザーが前提として明示）
- 開発機の Chrome は 152 で `--autoConnect`（Chrome 144+）が使える。`.mcp.json` は `command`/`args`/`env` で `${CLAUDE_PLUGIN_ROOT}` と `${user_config.KEY}` を展開する（公式 doc で確認）

ADR-20260831 の「再評価のトリガー」は「pane に保存先パスが入った時」だったが、実際に再評価を強制したのは**基盤の目的が smoke test から認証 E2E に変わったこと**だった。

## 決定

**認証あり E2E の基盤を次の優先順位にする。単一基盤は維持しつつ、証跡を持たない格下げ fallback を足す:**

```
認証不要 ─→ chrome-devtools（既定プロファイル）
認証必要 ─→ chrome-devtools --autoConnect（実 Chrome のログイン状態。userConfig browser_connect=autoConnect）
              ↓ 起動不可（Chrome 144 未満 / npx 不在 / 接続失敗）
            内蔵 Browser pane（mcp__Claude_Browser__*）
              ↓ 無い（CLI など）
            Claude in Chrome（mcp__claude-in-chrome__*）
              ↓ 未接続 / 別アカウント
            ログイン画面で停止し、ユーザーにログインを依頼して続行
```

## 理由

### autoConnect を既定の第 1（認証時）に昇格できる理由

ADR-20260831 が opt-in に留めた理由は privacy（実プロファイル接続 → snap 出力が public raw URL になりうる）。E2E 再定義で「認証状態の再利用」が要件になった以上、実プロファイル接続は**回避すべきコストではなく必要な能力**になった。privacy は別の歯止めで受ける: E2E の証跡は既定で PR 添付対象外（ローカル保持）、添付は dev アカウント画面に限りユーザー承認で opt-in。

### fallback を足す理由（単一基盤からの後退だが限定的）

ADR-20260831 は保存口の無い pane / Claude in Chrome を却下したが、それは「snap の証跡保存」を満たせないため。E2E の fallback は**合否判定が目的で証跡保存は必須でない**ので、保存口が無くても E2E は通せる。fallback に落ちた回は証跡を撮れない旨を記録し、必要なら chrome-devtools / Playwright で別途撮る。保存の鎖は第 1 基盤（chrome-devtools）が担うので、ADR-20260831 の「保存口が無いと snap が死ぬ」懸念は第 1 基盤では生じない。

### 書き込み系 E2E の歯止めを backend 軸に広げる

実プロファイル接続で E2E を回すと、認証済み状態での削除・送信が実データに届きうる。ADR-20260831 時点の歯止め（本番 URL で書き込まない）は URL 軸のみ。localhost の dev server が共有 backend を叩く構成では不十分なので、autoConnect / 実 Chrome 基盤では破壊的操作を既定 blocked にし、dev backend が隔離環境であることをユーザー確認したときだけ解禁する。

## 影響

- ui-verify の allowed-tools に 3 系統（chrome-devtools / Claude Browser / Claude in Chrome）を追加
- `.mcp.json` を起動ラッパ経由にし、`userConfig.browser_connect` で接続方式を選べるようにした（既定 `default`）
- ADR-20260831 の「単一基盤維持」は**第 1 基盤の単一性としては維持**（保存の鎖は chrome-devtools 一本）。fallback は証跡を持たない縮退経路で、tool 名ドリフトのリスクは「基盤別 tool 対応表」を 1 箇所に集約して受ける

## 却下した代替案

| 案 | 却下理由 |
|---|---|
| ADR-20260831 のまま（autoConnect opt-in・fallback なし） | 認証 E2E が主目的になり、実プロファイル接続が必要能力に変わった。opt-in 手順のままでは認証画面で止まる |
| 内蔵 pane を第 1 にする | 保存口が無く、認証不要ケースの証跡保存（snap の鎖）が死ぬ。第 1 は保存できる chrome-devtools を維持 |
| Playwright を E2E 基盤にする | E2E の合否は実機ブラウザでのみ決める（ユーザー前提）。Playwright は証跡撮影係に限定 |

## 再評価のトリガー

- 内蔵 Browser pane に保存先パス指定が入ったら、fallback ではなく証跡も撮れる基盤として格上げを検討
- `--autoConnect` の privacy 歯止め（証跡の添付 opt-in）が運用で機能しないと分かったら、autoConnect を既定から外して専用プロファイル（`--userDataDir`）方式に寄せる

## 関連

- 設計: `.claude/designs/20260912-e2e-verify-comment-polish-pr-flow.md`
- supersedes: ADR-20260831120000
