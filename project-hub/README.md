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
/project-hub:hub todo             # hub 自身の残作業を足す・終える・一覧する
/project-hub:hub close-sub <Issue> # done を報告した sub を閉じる（Desktop の archive）
/project-hub:hub mode <方式>      # 送る前の承認の方式を切り替える（auto / number / phrase）
/project-hub:hub tracker-write <never|with_approval> # hub がトラッカーに書いてよいか（既定は with_approval、tracker local は never。書くときは毎回 lead の承認を取る。sub の follow-up は起票の候補として出す）
/project-hub:hub sidebar-group <on|off> # 後から sub にしたセッションを、hub と一緒にサイドバーのグループにまとめる（Desktop だけ。Desktop の hub は既定で on）
/project-hub:hub living-spec <path> # PJ の living spec を結ぶ（state.md にパスが出る）
/project-hub:hub takeover         # 別のセッションを hub にする（Desktop で同じ会話を開き直しただけなら、確かめられれば自動で引き継ぐ）
/project-hub:hub close            # PJ を閉じる
```

流れ: hub で `init` → `start <Issue>` で sub を起動する（brief が最初のプロンプトになる。CLI では lead が貼る）→ sub は会話の題に Issue ID を入れて `report hello` を置き、issue-workflow の `start` などで Issue を進める（進め方の確認には lead が sub の中で答える）→ 以後、sub は節目で `report` を置き、hub は通知を受けたその場で取り込んで、質問に答える・lead の判断が要るものを lead に出す。`status` で外部の状態をまとめる。

brief を経ずに始めた sub（issue-workflow の `start` など）も、cwd の repo が active な PJ に入っていれば、SessionStart で紐付けの案内が入る。Claude は Issue の作業を始めた時点で `report hello` を置く。

## 連絡の形

- **sub → hub**: report の本文は hub の inbox にファイルで置き、SendMessage では「置いた」とだけ知らせる。通知が届かなくても、hub の次の `status` で取り込まれる。ListAgents の抜き出しが自己検査に合わなければ、何も書かずに止まる。hub に聞きたいことは `questions`、lead の判断が要ることは `needs_lead`、sub の会話で決まったことは `decisions`（節目を待たずに置く）、マージを待っている PR は `waiting_prs` に書く。ListAgents の出力はそのまま渡せば hub.py が抜き出す
- **外に出る文**: repo の docs・トラッカー・PR・コミットメッセージには hub・lead・sub の語を書かず、決定は日付で書く。relay の `[lead の言葉]` は lead の発言の引用だけにし、hub の説明は `[hub の補足]` の段に分ける
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

## living spec（設計の収束）

Issue 化する前段から実行中まで、PJ の決定を「設計収束ドキュメント」(living spec) で持つ。**未確定を抱えていることが正常状態**の文書を、採番・書式・相互参照を機械化しながら「仮 → 確定」へ収束させる。living spec は repo の `.claude/living-specs/<slug>.md` に置いて commit する（1 PJ に 1 本）。hub は使わなくてよい — 設計だけを詰める段階は living spec だけで使い、sub を起動するときに hub を init する（旧 living-spec-workflow を吸収した / ADR-20261026090521・GitHub issue #322）。

hub と併用するときは、hub の `living-spec` サブコマンド（`hub.py set-living-spec`）でその PJ の living spec を結ぶ（state.md にパスが出る）。決定と段取りの間の決まりは `hub-living-spec` skill に従う: 決定を書くのは lead が決めたときだけ、進捗（PR のマージ・sub の done・確かめた事実）は lead に聞かずに出典つきでタイムラインへ書く、確定を覆した決定の関連 Issue を仕掛中・未着手・完了に分けて lead に出す、sub の report のうち設計に関わるものを OQ の候補にする、自動の連絡の出典に使ってよいのは Decision と確定の行だけ、など。

コマンドは `/project-hub:living-spec` と `/project-hub:living-spec-maintain`（他のプラグインと名前がぶつからなければ `/living-spec` でも呼べる）。

### 使い方

```text
/living-spec init auth-redesign                    # .claude/living-specs/auth-redesign.md を scaffold
/living-spec oq セッションストアに Redis を使うか    # OQ1 として起票（採番・since は機械付与）
/living-spec spec 認証方式 方向性(仮)               # 仕様表の確度を更新（since も機械付与）
/living-spec decision 認証は OAuth 2.0 を採用       # D1 を append し、関連 OQ を close
/living-spec oq list                               # open な OQ の一覧（--all で closed 込み）
/living-spec status                                # 収束率 + open OQ 残数 + 次に決めるもの
/living-spec timeline PR #12 をマージ --source 'PR #12（merge 1a2b3c4d）'  # タイムラインに 1 行足す（日付は機械付与）
/living-spec spec --freeze D12                     # 仕様表を凍結（D12 に凍結の経緯を書いてから）
/living-spec                                       # usage
```

（スラッシュコマンドはシェルを経由しないので、引数はエスケープや引用符なしでそのまま書く）

第 1 引数は**常にサブコマンド**として解釈する（slug は `init` の後ろにしか置けない）。既定のサブコマンドは持たず、未知の第 1 引数も slug とみなさずエラーにする。サブコマンド名と slug 名を同じ名前空間に置くと、後からサブコマンドを追加するたびに、その語を slug に使っていた利用者の意味が変わるため。

`init` 以外は `--spec <slug>` で対象ファイルを明示指定できる（省略時: 1 件なら自動 / 複数なら選択 / 0 件なら init を案内）。

```text
/living-spec-maintain                  # 整合・鮮度を 8 段のファネルで検証
/living-spec-maintain --all            # .claude/living-specs/ の全件を点検
```

### 何が機械化されるか

| 手作業だとズレるもの | どう機械化したか |
|---|---|
| D# / OQ# の目視採番 | 既存 ID の**数値の最大 + 1**。HTML コメントを除去してから数えるので、記入例を実在 ID と誤認しない |
| close した OQ と Decision の相互参照 | `decision` が **1 コマンドで双方向を書き、直後に Read で検証**する。片方向ならその場で直す |
| 確度ラベルの `since` 更新漏れ | `spec` が `date` から機械付与する。確度が変わらなくても `since` は更新する（「今日この確度で確認した」の意味） |
| 「仮 → 確定」の収束の手集計 | `status` が確度ラベルを集計して収束率と open OQ 残数を出す |
| frontmatter `last_updated` の更新漏れ | 書き込むサブコマンドがすべて機械更新する（`last-validated` は人が maintain で更新するので触らない） |

### 成果物

`.claude/living-specs/<slug>.md`（**committed 前提**。Decision log を履歴として残すので gitignore しない）

```yaml
---
phase: target                  # doc-freshness 契約（収束中 = target）
last-validated: 2026-07-15     # doc-freshness 契約。人が内容を確認した日（maintain 実行時に更新）
last_updated: 2026-07-15       # 機械更新。init / oq / decision / spec が書き込みのたびに更新
notion_page_id: null           # v1 未使用（予約）
sync: null                     # v1 未使用（予約）
---
```

仕様表を凍結している間だけ、`spec_table: frozen` と `spec_table_frozen_by: D<n>` の 2 行が加わる（下の「仕様表の凍結」）。

本文は 7 セクション構成。うち機械パース対象は「仕様」「Open Questions」「Decision log」の 3 つ。

| セクション | 役割 |
|---|---|
| 現在地サマリ | 1 行目に今の phase の到達点（何を決め終えたら次の phase へ進むか）。続けて、いま何が確定していて次に何を決めるか（3 行以内） |
| 仕様 | 項目ごとの確度ラベル（`確定` / `方向性(仮)` / `未定`）・phase（`P1` … / `先送り`）・関連 Issue・`since` |
| Open Questions | OQ 台帳。`open` / `closed` と関連 D# の双方向参照 |
| Decision log | append-only の決定記録（D# 採番） |
| 進め方フェーズ / タイムライン / 参照ソース | 散文セクション（タイムラインは起きたことと期日。`timeline` が `- <日付> <起きたこと>（出典: …）` の形で足す） |

### 設計の核心: 情報を move しない

OQ を close するとき、台帳から行を消して Decision へ移す設計にはしない。効き目の範囲は次のとおり。

- **情報の消失**（close した OQ が消える / 移動の途中で失敗して片方にしか無い）→ 削除を含む操作が存在しないので**構造的に起きない**
- **参照の片側漏れ**（OQ に `関連 D#` が無い等）→ 表を書くのは LLM なので起こりうる。maintain の事後検知で担保する

つまり move をやめることで消えるのは消失であって、不整合ではない。不整合の検知器を持つのはそのため。

### 実行中も使い続ける（phase・先送り・関連 Issue）

living spec は phase ごとに到達点を持ち、実行に入ったあとも閉じずに使う（実装中に確定の項目が覆る・後の phase へ回す項目が出る / GitHub issue #320）。

- 仕様表は `| 項目 | 内容 | 確度 | phase | 関連 Issue | since |` の 6 列。旧 4 列の表もそのまま読め、`/living-spec spec --upgrade` で 6 列にする
- 今の phase は frontmatter の `current_phase: P<n>`（init は `P1`）。`spec --phase-advance D<n>` で次へ進める
- **先送り** = phase が `先送り` か今の phase より後の行。確度とは別の軸で、スコープ外（やらない）とも違う。先送りにする変更は Decision で残す（`spec <項目> --phase <値> D<n>`）
- `status` は先送りを全体の収束率から外し、phase ごとの収束率と先送りの件数を出す。maintain 段 6 は先送りの行を塩漬けとして数えない
- `decision` で確定の項目を覆したら、その項目の関連 Issue を出す（Issue を直すかの確認用。Issue の状態で分けるのはトラッカーを読む側）

### 仕様表の凍結

仕様の正本を別の文書へ移したあとも、living spec を Decision log と OQ 台帳として使い続けることがある。このとき仕様表は更新しなくなるので、表全体を凍結する。

```text
/living-spec decision 仕様の正本を docs/product-specs/ に移した   # 経緯を D12 として残す
/living-spec spec --freeze D12                                # 仕様表を凍結
/living-spec spec --unfreeze D15                              # 解除（D15 に再開の経緯を書いてから）
```

- 凍結中は `/living-spec-maintain` の段 6 が塩漬けを判定しない（skip した理由をレポートに出す）。凍結後に表を手で触った行（`since` が凍結の Decision より新しい）だけを Warning にする
- `spec` は凍結中の追加・更新を拒否し、凍結を宣言した Decision を案内する
- `status` は収束率を数えず「凍結済み」と出す（表の内訳は参考として出す）。「次に決めるもの」には open な OQ だけを挙げる
- 凍結の 2 行が壊れている（書式違反・Decision log に無い D# を指す）ときは、`--unfreeze` を D# なしで実行すると消せる（書き損じの修正なので Decision は要らない）
- 凍結の Decision は表の最後の更新以降に書いたもの、解除の Decision は凍結の Decision より後のものに限る。行単位では凍結しない。確度ラベルに 4 つ目の値を足す案は、3 値の契約と段 1 の正規表現を変えることになるので採らなかった

### 点検（/living-spec-maintain）

整合と鮮度を 8 段のファネルで検証する。**安い機械判定を先頭に置き、LLM 判断は通過分にだけ当てる**。

| 段 | 何を見るか | severity |
|---|---|---|
| 1 | 表スキーマ違反 | Critical |
| 2 | 採番の重複・欠番 | Critical |
| 3 | OQ ⇔ Decision の双方向参照 | Critical |
| 4 | 「参照ソース」の外部 URL の死リンク | Warning |
| 5 | OQ の `status` と `関連 D#` の行内整合 | Warning |
| 6 | 確度ラベルの塩漬け（仕様表が凍結済みなら、凍結後の更新だけを見る） | Warning |
| 7 | frontmatter `last_updated` の整合 | Info |
| 8 | 現在地サマリと実態のズレ（LLM 判断・`high` 以上） | Info |

段 1-3 で Critical が出たらファイルが壊れているので、段 8 には進まない。**検証を通過したときだけ** `last-validated` の更新を提案する（「内容を確認し問題ないと判断した日」なので、契約違反が残った状態で更新するのは意味に反する）。

**直すのは人**。機械的に直すのは `last-validated`（承認つき）だけで、他は修正方針を示すに留める。特に段 2 の欠番は**番号を詰めて直さない** — Critical が指しているのは「欠番という状態」ではなく「行が消えた事実」で、詰めるとその事実が見えなくなる。

### 隣接プラグインとの棲み分け

| やりたいこと | 使うもの |
|---|---|
| Issue 化前に、未確定を抱えたまま設計を収束させる | **living spec**（このプラグイン） |
| 代替案を比較して採用案を確定し、スナップショットとして残す | `design-doc` |
| 単一の設計判断（WHY）を点で記録する | `adr-keeper` |
| Issue 1 件の作業設計（9 セクション） | `issue-workflow` の issue-design |
| 設計から実装まで一気通貫 | `feature-dev` |

使い分けの軸は「何セッションかかるか」。未確定が 1 セッションの grill で片付くなら `design-doc` / `feature-dev` で足り、複数セッションに跨って決めていくときに living spec を使う。

living spec で確度が `確定` に寄った塊ができたら Issue 化する。living spec 側からプラグインは呼ばない（疎結合）。ユーザーが `/issue-create`（issue-workflow）に手で渡す。

### doc-freshness との住み分け

| 責務 | 担当 |
|---|---|
| ファイル単位の鮮度（`last-validated` / `phase` stale）の**検出** | doc-freshness |
| frontmatter スキーマ検証 / 内部相対リンクの実在検証 | doc-freshness |
| 表スキーマ・採番・相互参照・確度ラベルの `since` stale | living spec（このプラグイン） |
| `last-validated` の**更新**（点検を通過したときに承認つきで） | living spec（`/living-spec-maintain` の完了処理） |

doc-freshness 未導入でも動作する。失われるのはファイル単位の stale 検出だけで、OQ / Decision / 収束の可視化は単体で成立する。

### 既知の制約

- **doc-freshness は 0.4.0 以降が必要**。`.claude/living-specs/` の走査対象への追加は doc-freshness 0.4.0 で入った。それ未満のバージョンでは鮮度 lint の委譲が成立しない（living spec が走査されず、stale が検出されない）
- **`.claude/doc-freshness.json` に `hookTargets` を設定済みのプロジェクトは注意**。`hookTargets` を指定すると hook の対象がその配列で**置き換わる**（部分追加ではない）ため、既定への追加が効かない。利用者側で `.claude/living-specs/` を配列に追記する必要がある

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
    todos.jsonl                hub 自身の残作業（add / done の追記のみ）
    last_resolve.json          直前の ok の resolve の宛先（record --from-resolve が使って消す）
  bin/hub.py                   版に左右されない呼び口（hub のセッションの hook が、動いている版へ向けて書き直す）
```

データはマシンごとに置く。マシンをまたいで 1 つの hub を共有しない。

sub・ListAgents・トラッカー由来の文面（report の本文・fact の主張・relay の全文と宛先・取得のエラー文）は `scripts/hub.py` に JSON にして stdin で渡し、argv に載せない（シェルに展開させない）。heredoc の区切りは毎回乱数つきにする。state.md の表のセルは改行・制御文字を潰し、`<` `>` を全角にして 60 字で切る（注入した表から別の行・タグとして抜け出さない）。


## 注入

- **hub のセッション**（SessionStart / PostCompact の stdin の `session_id` が `hub.json` と一致したとき）: state.md と、その生成後に増えた journal の件数・未取り込みの report の件数
- **hub のセッションの発言ごと**（UserPromptSubmit）: inbox に未取り込みの report があるときだけ、取り込みのコマンドを注入する。sub の通知でも lead の発言でも発火するので、通知が届かなかった回も次の発言で拾う。hook は件数を見るだけで、report の文面は読まない
- **sub**（SessionStart / PostCompact）: cwd の repo が active な PJ に入っていて、このセッションがまだ登録されていないときだけ、Issue の作業を始めたら `report hello` を置くよう案内する

ほかのセッションでは何も出さない。

## 入っている範囲

入っているもの: 状態ファイル・`hub` と `report` と `hub-living-spec` の skill・living spec（`living-spec` と `living-spec-maintain` の skill。旧 living-spec-workflow）・注入 hook・未取り込みの知らせ（UserPromptSubmit）・sub への紐付けの案内（段階 ①）、自動の連絡・`start`・`mode`・report の `questions`（段階 ②a）、report の `decisions` と `waiting_prs`・待っている PR のマージの知らせ・hub の残作業（`todo`）・sub を閉じる（`close-sub`）・トラッカーへの承認つきの書き込み（`tracker-write`）・ListAgents の生の出力の受け取り・後から sub にしたセッションのサイドバーのグループ（`sidebar-group`）。

まだ無いもの（段階 ② の残りと ③。使ってから設計する）: マージの連鎖（待っている PR の知らせを除く）、判断の波及と living spec への受け渡しの機械化（いまは `hub-living-spec` の決まりに沿って hub が手で行う）、status への living spec の数字の機械表示（いまは status の手順で hub が `/project-hub:living-spec status` を見る）、決定と経緯（journal・facts）の ID による機械的な紐付け、意見の台帳、送る前の文面の検査。

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
- `gh`（任意）: tracker が GitHub のときの Issue と PR の取得。`tracker_write: with_approval` の PJ では Issue の起票・本文の直しにも使う
- Linear MCP（任意）: tracker が Linear のときの Issue の取得。`tracker_write: with_approval` の PJ では Issue の保存（`save_issue`）にも使う
- issue-workflow の local backend（任意）: tracker が local のときの Issue ファイル（`hub.py` が直接読む。プラグインとしての依存は無い）

- doc-freshness（任意・0.4.0 以降）: living spec のファイル単位の鮮度 lint を委譲する。未導入でも living spec は動く
## テスト

`.claude-plugin/scripts/tests/test_project_hub_scripts.py`（`hub.py` の CLI）と `test_project_hub_hooks.py`（注入 hook・未取り込みの知らせ・依存チェック）。どちらも `PROJECT_HUB_DIR` を使い捨ての dir に向ける。
