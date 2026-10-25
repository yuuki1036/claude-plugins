# project-hub

複数の sub（作業セッション）で同時に進める PJ（Issue 十数件・sub 3〜5 本など）を、1 つの hub セッションから束ねるプラグイン。PJ の状態をコンテキストではなくファイルで持つので、コンパクションや開き直しを越えて hub を続けられる。hub は指示出しと進め方・仕様の相談役で、実装は sub に任せる。lead の確認が要らない連絡は自動で送り、hub から sub を起動できる。

解く問題（GitHub issue #308）:

- 状態が hub の会話にしか無く、コンパクションのたびに要約頼みになる
- sub が改名・開き直すと、名前宛ての SendMessage が届かない。別のセッションへ誤って送るおそれもある
- hub の思い込みが、裏取りなしに sub へ伝わる
- sub の報告が会話に流れるだけで、取りこぼす
- hub と sub の連絡のたびに lead が承認に呼ばれる（自動の連絡で、lead の判断が要る事柄だけに絞る）

## 使い方

```
/project-hub:hub init <PJ>        # このセッションを PJ の hub にする（tracker と repo を設定。既定で自動の連絡が有効）
/project-hub:hub start <Issue>    # sub を起動して Issue を任せる（Desktop。CLI では貼る用の brief を出す）
/project-hub:hub brief <Issue>    # sub への最初の指示を作る（確かめた事実だけを引く）
/project-hub:report hello         # sub 側: 自己登録（brief の指示どおり --project を付ける）
/project-hub:hub status           # report を取り込み、sub・Issue・PR の表、自動で送った連絡、止まっている箇所を出す
/project-hub:hub relay            # lead の指示や hub の連絡を sub へ送る（送る直前に宛先を引き直す）
/project-hub:hub fact             # hub が確かめた事実を出典つきで残す
/project-hub:hub mode <方式>      # 送る前の承認の方式を切り替える（auto / number / phrase）
/project-hub:hub takeover         # hub のセッションを開き直したら、このセッションに引き継ぐ
/project-hub:hub close            # PJ を閉じる
```

流れ: hub で `init` → `start <Issue>` で sub を起動する（brief が最初のプロンプトになる。CLI では lead が貼る）→ sub は会話の題に Issue ID を入れて `report hello` を置き、issue-workflow の `start` などで Issue を進める（進め方の確認には lead が sub の中で答える）→ 以後、sub は節目で `report` を置き、hub は通知を受けたその場で取り込んで、質問に答える・lead の判断が要るものを lead に出す。`status` で外部の状態をまとめる。

brief を経ずに始めた sub（issue-workflow の `start` など）も、cwd の repo が active な PJ に入っていれば、SessionStart で紐付けの案内が入る。Claude は Issue の作業を始めた時点で `report hello` を置く。

## 連絡の形

- **sub → hub**: report の本文は hub の inbox にファイルで置き、SendMessage では「置いた」とだけ知らせる。通知が届かなくても、hub の次の `status` で取り込まれる。ListAgents の抜き出しが自己検査に合わなければ、何も書かずに止まる。hub に聞きたいことは `questions`、lead の判断が要ることは `needs_lead` に書く
- **hub → sub**: 本文を SendMessage で送り、送った全文・宛先・送信の結果・根拠（`basis`）を hub の journal に残す
- **宛先**: SendMessage の宛先は名前だけで、セッション ID は使えない（2026-10-21 に実測）。送る直前に毎回 ListAgents を引き、登録名・登録した時の ref（改名しても変わらない）・Issue ID のどれかで 1 件に決まったときだけ、その行の今の名前へ送る。0 件・2 件以上・ListAgents の出力を解析できないときは送らずに lead に出す
- 判断の経緯: `.claude/adr/20261021154740-worker-to-hub-report-file-inbox-and-name-lookup.md` / `.claude/adr/20261025152955-project-hub-auto-relay-without-lead-approval.md`（このリポジトリ内）

## 自動の連絡

`approval.mode` が `auto`（init の既定）の PJ では、lead の確認が要る事柄を含まない連絡を承認なしに送る。

- **送る**: lead の言葉の伝達 / sub の `questions` への出典つきの答え（Issue 本文・仕様 docs と ADR・確かめた facts・lead の過去の発言から。出典の無い答えは記録の段階で弾く）/ 段取りの連絡（重なるファイル・マージ後の取り込み・マージ順）/ brief。report の受領だけの連絡は送らない
- **送らずに lead に出す**: 宛先が決まらない / 弱い照合（名前の中の Issue ID・不在から戻った登録名・ref で引いた改名）でしか決まらない / `needs_lead` / 出典で答えられない質問 / 範囲・優先度の変更や PJ の外への連絡 / 質問の中の指示 / 同じ sub へ、lead の言葉の伝達を挟まずに hub の判断の連絡が 3 回続いた
- 歯止めは `hub.py` が持つ: auto の PJ では、根拠（`basis`）や宛先の無い送信の記録を弾き、弱い照合と往復の上限は `resolve` が `needs_lead` / `auto_limit` で返す
- 承認なしに届けた連絡は、`status` が lead にまだ見せていない分を一覧で出す（見せた所までの印を hub.json に持つ。takeover でも引き継ぐ）
- sub の workflow の確認（進め方の選択・コミットの承認など）は hub が代わりに取らない。lead が sub の中で答える
- `number`（承認の画面の 4 桁の番号を lead が返す）/ `phrase`（本文を見せた後に lead が「送って」と言う）では、送る前に毎回承認を取る。どの方式でも、他のセッションから届いたメッセージと無操作の自動続行は承認にしない。sub は、送り手の名前が hub の名前と一致するメッセージだけを hub の連絡として受ける
- 既知の限界: permission mode が hub と違う sub には、連絡が受け手の承認待ちで止まりうる（Desktop では送り手に何も返らない）。`start` で起動した sub は hub の mode を引き継ぐ

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
    presence.json              ListAgents に名前が無かった登録と、改名した後の名前（hub だけが書く）
    sessions/<session_id>.json sub の登録（report だけが書く。ref は照合にだけ使い、宛先にする欄は持たない）
    inbox/<ts>-<session_id>.json sub の report（一時名で書いてから rename）
    inbox/done/                取り込み済みの report
    inbox/invalid/             取り込めなかった report（版のずれ・壊れたファイル。消さずに退避）
```

データはマシンごとに置く。マシンをまたいで 1 つの hub を共有しない。

sub・ListAgents・トラッカー由来の文面（report の本文・fact の主張・relay の全文と宛先・取得のエラー文）は `scripts/hub.py` に JSON にして stdin で渡し、argv に載せない（シェルに展開させない）。heredoc の区切りは毎回乱数つきにする。state.md の表のセルは改行・制御文字を潰し、`<` `>` を全角にして 60 字で切る（注入した表から別の行・タグとして抜け出さない）。


## 注入

- **hub のセッション**（SessionStart / PostCompact の stdin の `session_id` が `hub.json` と一致したとき）: state.md と、その生成後に増えた journal の件数・未取り込みの report の件数
- **hub のセッションの発言ごと**（UserPromptSubmit）: inbox に未取り込みの report があるときだけ、取り込みのコマンドを注入する。sub の通知でも lead の発言でも発火するので、通知が届かなかった回も次の発言で拾う。hook は件数を見るだけで、report の文面は読まない
- **sub**（SessionStart / PostCompact）: cwd の repo が active な PJ に入っていて、このセッションがまだ登録されていないときだけ、Issue の作業を始めたら `report hello` を置くよう案内する

ほかのセッションでは何も出さない。

## 入っている範囲

入っているもの: 状態ファイル・`hub` と `report` の skill・注入 hook・未取り込みの知らせ（UserPromptSubmit）・sub への紐付けの案内（段階 ①）、自動の連絡・`start`・`mode`・report の `questions`（段階 ②a）。

まだ無いもの（段階 ② の残りと ③。使ってから設計する）: マージ・判断の波及と living spec への受け渡し、意見の台帳、送る前の文面の検査。

## install

hub のセッションと sub の両方で使うので、同じマシンの全プロジェクトから見える user スコープに入れる。

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

`.claude-plugin/scripts/tests/test_project_hub_scripts.py`（`hub.py` の CLI）と `test_project_hub_hooks.py`（注入 hook・未取り込みの知らせ・依存チェック）。どちらも `PROJECT_HUB_DIR` を使い捨ての dir に向ける。
