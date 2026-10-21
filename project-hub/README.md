# project-hub

複数の作業セッションで同時に進める PJ（Issue 十数件・作業セッション 3〜5 本など）を、1 つの hub セッションから束ねるプラグイン。PJ の状態をコンテキストではなくファイルで持つので、コンパクションや開き直しを越えて hub を続けられる。

解く問題（GitHub issue #308）:

- 状態が hub の会話にしか無く、コンパクションのたびに要約頼みになる
- 作業セッションが改名・開き直すと、名前宛ての SendMessage が届かない。別のセッションへ誤って送るおそれもある
- hub の思い込みが、裏取りなしに作業側へ伝わる
- 作業側の報告が会話に流れるだけで、取りこぼす

## 使い方

```
/project-hub:hub init <PJ>        # このセッションを PJ の hub にする（tracker と repo を設定）
/project-hub:hub brief <Issue>    # 作業セッションへの最初の指示を作る（確かめた事実だけを引く）
/project-hub:report hello         # 作業セッション側: 自己登録（brief の指示どおり --project を付ける）
/project-hub:hub status           # report を取り込み、作業セッション・Issue・PR の表と止まっている箇所を出す
/project-hub:hub relay            # lead の指示を作業セッションへ送る（送る直前に宛先を引き直す）
/project-hub:hub fact             # hub が確かめた事実を出典つきで残す
/project-hub:hub takeover         # hub のセッションを開き直したら、このセッションに引き継ぐ
/project-hub:hub close            # PJ を閉じる
```

流れ: hub で `init` → `brief` を作り、新しい作業セッションの最初のプロンプトとして lead が貼る → 作業側は会話の題に Issue ID を入れて `report hello` → 以後、作業側は節目で `report`、hub は `status` で取り込み、`relay` で指示を送る。

## 連絡の形

- **作業側 → hub**: report の本文は hub の inbox にファイルで置き、SendMessage では「置いた」とだけ知らせる。通知が届かなくても、hub の次の `status` で取り込まれる。ListAgents の抜き出しが自己検査に合わなければ、何も書かずに止まる
- **hub → 作業側**: 本文を SendMessage で送り、送った全文・宛先・送信の結果を hub の journal に残す
- **宛先**: SendMessage の宛先は名前だけで、セッション ID は使えない（2026-10-21 に実測）。送る直前に毎回 ListAgents を引き、登録名か Issue ID が 1 件に決まったときだけ送る。0 件・2 件以上・ListAgents の出力を解析できないときは送らずに lead に出す。送る前の承認の画面に、解決した宛先の名前と ref を出す
- 判断の経緯: `.claude/adr/20261021154740-worker-to-hub-report-file-inbox-and-name-lookup.md`（このリポジトリ内）

## 置き場所

```
${PROJECT_HUB_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/project-hub}/
  .gitignore                   中身は `*`（~/.claude を git 同期していても同期の対象から外す）
  <PJ>/
    config.json                tracker・repos・relay の前置きと締め・status
    hub.json                   いまの hub の session_id と名前
    journal.jsonl              起きたことの追記ログ（hub だけが書く）
    facts.jsonl                確かめた事実（出典つき・追記のみ。訂正は supersedes で）
    snapshot.json              status が集めた外部の状態（取得時刻つき。失敗した回は前回の値を残す。PR は repo ごと）
    state.md                   注入する表（report の自由文は写さず件数だけ載せる）
    presence.json              ListAgents に名前が無かった登録（hub だけが書く）
    sessions/<session_id>.json 作業側の登録（report だけが書く。宛先にする欄は持たない）
    inbox/<ts>-<session_id>.json 作業側の report（一時名で書いてから rename）
    inbox/done/                取り込み済みの report
    inbox/invalid/             取り込めなかった report（版のずれ・壊れたファイル。消さずに退避）
```

データはマシンごとに置く。マシンをまたいで 1 つの hub を共有しない。

作業側・ListAgents・トラッカー由来の文面（report の本文・fact の主張・relay の全文と宛先・取得のエラー文）は `scripts/hub.py` に JSON にして stdin で渡し、argv に載せない（シェルに展開させない）。heredoc の区切りは毎回乱数つきにする。state.md の表のセルは改行・制御文字を潰し、`<` `>` を全角にして 60 字で切る（注入した表から別の行・タグとして抜け出さない）。

relay は承認の画面に出した 4 桁の番号を lead が返したときだけ送る。作業側は、送り手の名前が hub の名前と一致するメッセージだけを hub の指示として受ける。

## 注入

hub のセッション（SessionStart / PostCompact の stdin の `session_id` が `hub.json` と一致したとき）にだけ、state.md と、その生成後に増えた journal の件数・未取り込みの report の件数を注入する。ほかのセッションでは何も出さない。

## 段階 ① の範囲

入っているもの: 状態ファイル・`hub` と `report` の skill・注入 hook。

まだ無いもの（段階 ② ③。段階 ① を 1 PJ で使ってから設計する）: マージ・判断の波及と living spec への受け渡し、hub 側で通知を受けて記録する UserPromptSubmit hook、意見の台帳、送る前の文面の検査。

## install

hub のセッションと作業セッションの両方で使うので、同じマシンの全プロジェクトから見える user スコープに入れる。

```bash
# マーケットプレイスから
claude plugin install project-hub@yuuki1036-claude-plugins

# ローカルから
claude plugin install /path/to/claude-plugins/project-hub
```

## 依存

- `python3`（必須）: 状態ファイルの読み書きと宛先の照合（`scripts/hub.py`）
- `gh`（任意）: tracker が GitHub のときの Issue と PR の取得
- Linear MCP（任意）: tracker が Linear のときの Issue の取得

## テスト

`.claude-plugin/scripts/tests/test_project_hub_scripts.py`（`hub.py` の CLI）と `test_project_hub_hooks.py`（注入 hook・依存チェック）。どちらも `PROJECT_HUB_DIR` を使い捨ての dir に向ける。
