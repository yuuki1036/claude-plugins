---
id: 20261102144903
status: accepted
phase: current
last-validated: 2026-11-02
supersedes: []
superseded-by: null
append_only: true
tags: [project-hub, repo-hub, routing]
---

# ADR-20261102144903: project-hub では 1 つのセッションを同じ repo の active な PJ のうち 1 つにだけ登録し、Issue の範囲で振り分ける

## ステータス

accepted（2026-11-02）

## コンテキスト / 背景

- repo hub（ADR-20261102144843）を足すと、1 つの repo を含む active な PJ が 2 つ以上ある状態が常態になる
- 紐付けの案内（`project-hub/scripts/hub.py:2731` `worker_hint`）は、SessionStart と PostCompact の hook からだけ呼ばれ、受け取るのは session_id と cwd だけ（`hub.py:2785`）。この時点では Issue が決まっていない。未登録かは PJ ごとに判定する（`hub.py:2743`）ので、ある PJ に登録済みのセッションにも、同じ repo の別の PJ の案内が出続け、両方に登録されうる
- 同じセッションが 2 つの PJ に登録されると、次のことが起きる:
  - 宛先の照合は、active かどうかを問わず別の PJ の登録名を候補から外す（`hub.py:2330` `foreign_names`）ので、自分の sub の名前も外れる
  - 別の PJ の hub から見ると自分の sub なので、「別の PJ の sub には送らない」決まりをすり抜けて自動の連絡が届く
  - cross は session_id で突き合わせないので、自分自身との重なりを出す
  - report は 1 回に 1 つの PJ にしか置かれず、もう片方では hello のまま残る
- 登録（`sessions/<sid>.json`）は report のたびに書かれ（`hub.py:2573-2581`）、消す処理は無い
- `--project` を付けない report は、候補の PJ が 1 件のときだけ決まる（`hub.py:2506` `detect_project`）。候補が 2 件以上だと毎回利用者に PJ を聞く
- report の issue の検査は形だけで（`hub.py:589`）、tracker に実在するかは見ない。`hub.py` は gh を呼ばない

## 決定

1. 1 つのセッションは、同じ git の共通ディレクトリを持つ active な PJ のうち 1 つにだけ登録する
2. 宛先の PJ は report の中で決める（`route` は report の内部の関数）。紐付けの案内は宛先を決めない:
   - repo hub の無い repo（active な repo hub が無い）では、今の `detect_project` のまま決める
   - 同じ repo の active な PJ にこのセッションの登録が既にあれば、その PJ に固定する。作業の途中で範囲が変わっても付け替えず、食い違いは `warnings` に出すだけにする
   - `--project` があればそれを使う。ただし repo hub を指していて、Issue が active な通常の PJ の範囲に入ると判定できたら `out_of_scope` で止める
   - 初めての登録で `--project` が無ければ、通常の PJ ごとに Issue の範囲を判定する（local は Issue ファイルの slug、github は milestone、linear は project。milestone と project は呼ぶ側が渡す）。材料が足りないとき（milestone の指定が無い・tracker が別の repo の PJ がある）は「不明」とし、範囲外と同じには扱わない
   - 範囲に入る PJ が 1 件で不明が無ければその PJ、0 件で不明が無く repo hub の tracker の範囲にあれば repo hub、それ以外は `needs_project` で利用者に聞く
3. 二重登録の検査は書き込む側の report に置く。別の active な PJ に同じ session_id の登録があれば `registered_elsewhere` で止める
4. 紐付けの案内は、同じ repo の active な PJ のどれかに登録済みなら、どの PJ の案内も出さない。未登録なら今と同じく PJ を並べ、active な repo hub がある repo では「`--project` を付けずに report を置けば宛先は report が決める」を足す
5. `foreign_names` は、自分の PJ にも登録のある session_id の名前を外さない
6. 弾く理由は stdout の `status`（`needs_project` / `out_of_scope` / `registered_elsewhere`）と 0 以外の exit で返し、SKILL はその `status` で分岐する

## 影響 (Consequences)

- **良い影響**: 宛先の照合・cross・自動の連絡の回数の上限が、session_id 単位で正しく働く。PJ hub がある repo でも、hello のたびに PJ を聞かれない。判定できない Issue を黙って repo hub に入れない。repo hub の無い repo では今の挙動が変わらない
- **悪い影響**: GitHub の Issue は、初めての登録のたびに milestone を取る gh の呼び出しが 1 回増える。1 つのセッションで 2 つの PJ の Issue を続けて進めることはできない（Issue ごとにセッションを分ける）。tracker が別の repo の PJ がある repo では、`--project` が無ければ毎回聞かれる。sub の project-hub が古いと検査が掛からない（status の後ろ盾で拾う）
- **トレードオフ**: 振り分けの正確さ（Issue の範囲で判定する）と単純さ（PJ hub が渡した分だけ PJ にする・毎回聞く）を比べ、正確さを取った。範囲の判定より登録の固定を優先し、作業の途中で行き先が変わることを避けた

## 適用方法 (Enforcement)

- report の宛先の決め方（今の挙動の維持・登録の固定・範囲の判定・不明の扱い）と二重登録の検査は `project-hub/scripts/hub.py` に置き、CLI テスト（`.claude-plugin/scripts/tests/test_project_hub_scripts.py`）で固定する
- 「登録済みのセッションにはどの PJ の案内も出さない」は hook テスト（`test_project_hub_hooks.py`）で、黙る条件を厚く書いて固定する
- Claude が `--project` に範囲外の通常の PJ を渡す経路は、GitHub と Linear では範囲の判定に呼ぶ側の情報が要るため、`hub.py` だけでは判定しきれない。report の SKILL.md の手順（`--project` を付けるのは brief や利用者が指定したときだけ）で守る
- 版のずれで report の検査が掛からなかった回は、hub の status が、同じ session_id が同じ repo の別の active な PJ にも登録されていないかを見て lead に出す

## 検討した代替案

- **PJ hub の start / brief が渡した `--project` の分だけ PJ にし、それ以外は repo hub にする**: PJ の Issue を直接開いたセッション（issue-workflow の start）で始めると repo hub に入り、GitHub issue #315 で直した「hub を経ずに始めた sub も PJ に紐付く」流れが崩れる
- **候補が 2 件以上なら毎回聞く（今の挙動）**: 実装は要らないが、repo hub がある repo では hello のたびに聞かれる
- **紐付けの案内の時点で宛先を決める**: hook の時点では Issue が決まっておらず、gh も呼べない
- **report のたびに範囲で引き直す（登録を固定しない）**: 作業の途中で Issue に milestone が付くと行き先が変わり、二重登録の検査に当たって抜けられなくなる
- **判定できないときは repo hub に入れる**: milestone の渡し忘れや別の repo の Issue が、黙って repo hub の sub になる
- **二重登録を許し、cross・resolve の側で session_id の重複を除く**: 直す箇所が report・resolve・cross・自動の連絡の回数・close-sub に散り、漏れが出やすい

## 関連

- 関連 ADR: ADR-20261102144843（repo hub は閉じない PJ で、上位の hub の代わりにしない）、ADR-20261021154740（report のファイル inbox と名前の照合）、ADR-20261029233229（PJ 横断は読むだけ）
- 関連 Issue: GitHub issue #315（issue-workflow の start で始めたセッションが hub に紐付かない）
- 関連 design doc: `.claude/designs/20261102-project-hub-repo-hub.md`
- 関連 knowledge: なし
