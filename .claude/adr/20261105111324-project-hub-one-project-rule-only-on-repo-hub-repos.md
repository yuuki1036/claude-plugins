---
id: 20261105111324
status: accepted
phase: current
last-validated: 2026-11-05
supersedes: []
superseded-by: null
append_only: true
tags: [project-hub, repo-hub, routing]
---

# ADR-20261105111324: project-hub の 1 セッション 1 PJ の登録と二重登録の禁止は、active な repo hub のある repo にだけ掛ける

## ステータス

accepted（2026-11-05。決定は 2026-11-04）

## コンテキスト / 背景

- ADR-20261102144903 の決定 1 は「1 つのセッションは、同じ git の共通ディレクトリを持つ active な PJ のうち 1 つにだけ登録する」、決定 3 は「別の active な PJ に同じ session_id の登録があれば `registered_elsewhere` で止める」と、repo hub の有無を条件にせずに書いている。一方、同じ ADR の決定 2 は「repo hub の無い repo では、今の `detect_project` のまま決める」としている
- 設計書 `.claude/designs/20261102-project-hub-repo-hub.md` のゴールは「repo hub の無い repo では、今の挙動を変えない」
- repo hub の無い repo で、通常の PJ が 2 つ以上同じ repo を含むと、`--project` の無い report は PJ が決まらず exit 1 になる（`detect_project`）。そのため sub は `--project` を付けて置き、1 つのセッションが `--project` を切り替えて 2 つの PJ に置く運用がありうる
- 二重登録の検査は、登録の固定（登録があればその PJ に置く）と組になって初めて「正しく動いていれば当たらない」検査になる。固定を掛けない repo hub の無い repo で検査だけを掛けると、`--project` の切り替えがすべて止まる
- GitHub issue #357 の実装（2026-11-04）で、この食い違いを利用者が決めた

## 決定

1. 登録の固定・`registered_elsewhere`・`needs_branch`・status の後ろ盾（`cross` の `double_registered`）は、report を置く cwd の repo に active な repo hub があるときだけ掛ける。ADR-20261102144903 の決定 1・3 は、この範囲で読む
2. repo hub の無い repo（repo hub が closed の repo を含む）では、宛先の決め方も report を止める判定も今までどおり（`--project` か、PJ が 1 つならそれ）。1 つのセッションが `--project` を切り替えて 2 つの PJ に置くことを止めない
3. 次の 2 つは repo hub の有無によらず、どの repo にも効かせる:
   - 紐付けの案内（`worker_hint`）は、同じ repo のどれかの active な PJ に登録済みなら、どの PJ の案内も出さない（ADR-20261102144903 の決定 4）
   - 宛先の照合（`foreign_names`）は、引いているセッションがこの PJ にも登録を持つなら、ほかの PJ でのそのセッションの名前を候補から外さない（同 決定 5）
4. status の後ろ盾が数える単位は route と同じにする: 登録の worktree の repo に active な repo hub があるもの。repo hub でない PJ どうしの組も数える。worktree を消した登録は、PJ が共有する repo で見る

## 影響 (Consequences)

- **良い影響**: repo hub を置かない repo の運用（`--project` で PJ を切り替える sub・hub の brief が渡す `--project`）が変わらない。二重登録の検査が、登録の固定と同じ範囲に揃う。当たるのは版のずれと、repo hub の無かった repo で 2 つの PJ に登録した後に repo hub を作った回だけで、どちらも `--project` で登録済みの 1 つを選べば置ける（route が warning を付けて置く）
- **悪い影響**: repo hub の無い repo では、1 つのセッションが 2 つの PJ に登録されうる状態が残る（ADR-20261102144903 の背景にある、宛先の照合が自分の sub の名前を外す・cross が自分自身との重なりを出す、は repo hub の無い repo では解消しない。照合のほうは決定 3 の `foreign_names` の例外で一部緩和する）。ADR-20261102144903 の決定 1・3 を単独で読むと、全 repo に掛かると誤読しうる
- **トレードオフ**: 二重登録を全 repo で禁じる一貫性と、repo hub を使わない repo の挙動を変えない互換性を比べ、互換性を取った

## 適用方法 (Enforcement)

- 機械強制できる。`project-hub/scripts/hub.py` の `route` は、cwd の repo に active な repo hub が無ければ `detect_project` の式をそのまま返し、登録の固定と二重登録の検査に入らない。`branch_check` は宛先が repo hub のときだけ呼ばれる。`cmd_cross` の `double_registered` は、登録の worktree の repo が active な repo hub を持つときだけ数える
- CLI テストで固定する（`.claude-plugin/scripts/tests/test_project_hub_scripts.py`）: `RouteWithoutRepoHubTest`（2 つの PJ への登録を止めない・base のブランチの上でも止めない・後ろ盾にも出さない）、`RepoHubRouteTest` の `test_cross_counts_two_plain_projects_on_a_repo_hub_repo`（repo hub を close すると数えない）と `test_cross_follows_the_repo_the_session_registered_in`
- 決定 3 の黙る条件は hook テスト（`test_project_hub_hooks.py` の `test_a_session_registered_in_any_project_of_the_repo_is_quiet`。repo hub の有無の両方）で固定する

## 検討した代替案

- **二重登録の禁止をすべての repo に掛ける（ADR-20261102144903 の決定 1・3 を文字どおりに読む）**: 一貫するが、repo hub の無い repo で `--project` を切り替えて 2 つの PJ に置く sub がすべて `registered_elsewhere` で止まる。登録の固定を掛けないまま検査だけを掛けることになり、設計書のゴール「今の挙動を変えない」に反する
- **登録の固定も含めて、すべての repo に掛ける**: 二重登録は当たらなくなるが、repo hub の無い repo で `--project` の無い report の宛先が、今の exit 1 から「登録済みの PJ」に変わる。挙動を変える範囲が広く、repo hub を使わない利用者が恩恵を受けない
- **`worker_hint` の黙る条件も repo hub のある repo だけにする**: 案内を出し続けると、登録済みのセッションが 2 つ目の PJ にも hello を置く誘導になる。案内を黙らせても `--project` の切り替えは止まらないので、全 repo に効かせた

## 関連

- 関連 ADR: ADR-20261102144903（1 セッション 1 PJ の登録と Issue の範囲での振り分け。この ADR は決定 1・3 の適用範囲を絞る）、ADR-20261102144843（repo hub は閉じない PJ で、上位の hub の代わりにしない）
- 関連 Issue: GitHub issue #357
- 関連 design doc: `.claude/designs/20261102-project-hub-repo-hub.md`（「実装で決めたこと（Issue 1b・2026-11-04）」）
- 関連 knowledge: なし
