# worktree 3 状態マトリクス

`worktree-setup` skill が分岐する 3 状態の判定基準と挙動。

## 状態の定義

```
┌─────────────────────────┬──────────────────────────────────┬─────────────────────────┐
│ 状態                    │ 条件                             │ アクション              │
├─────────────────────────┼──────────────────────────────────┼─────────────────────────┤
│ main                    │ GIT_DIR == GIT_COMMON_DIR        │ エラー終了              │
│ worktree-ready          │ worktree かつマーカー存在        │ スキップ（--force で再）│
│ worktree-unconfigured   │ worktree かつマーカー無し        │ セットアップ実行        │
└─────────────────────────┴──────────────────────────────────┴─────────────────────────┘
```

## 判定フロー

```
       開始
        │
        ▼
   git rev-parse --git-dir / --git-common-dir
        │
        ├─ 同じ? ─── YES ──→ [main] エラー終了
        │
       NO
        │
        ▼
   envs/.backend.env.worktree が存在?
        │
        ├─ YES ──→ [worktree-ready] スキップ
        │                 └─ --force あり ──→ Step 2 へ進む
        │
       NO
        │
        ▼
   [worktree-unconfigured] Step 2 へ進む
```

## 各状態の詳細

### main

- メインの clone 上で `worktree-setup` を呼ぶと発火する状態
- ここで env / DB を作るとメインの開発環境を破壊する可能性があるため即終了
- ユーザーへの案内: `git worktree add ../<name> <branch>` で worktree を作り、その中で再実行する

### worktree-ready

- 過去に `worktree-setup` が完了し、マーカー（`envs/.backend.env.worktree`）が残っている状態
- そのまま使えるので Step 2 以降をスキップ
- 現在の DB 名・port を `cat envs/.backend.env.worktree` で表示してユーザーに状態を伝える
- `--force` 指示があれば既存 env を上書きして再生成（DB は drop しない、port のみ再割当）

### worktree-unconfigured

- worktree は作ってあるが、env / DB / port が手付かずの状態
- `worktree-setup` の本流。Step 2 以降のフローを実行する

## マーカーファイルの設計判断

`envs/.backend.env.worktree` をマーカーとして兼用している理由:

- **冪等性**: ファイル存在判定なので何度実行しても安全
- **可視性**: 中身を `cat` するだけで割当内容が確認できる
- **追加コストゼロ**: 別途 `.worktree-setup.lock` のようなファイルを増やさなくて済む

マーカーを別ファイルに分離したい場合は本 skill 全体を override する。

## dev-workflow への追加 vs 独立 plugin 化

| 項目 | dev-workflow に追加（現在の選択） | 独立 plugin 化 |
|---|---|---|
| install 手間 | 既存 install で済む | 別途 install 必要 |
| 発見性 | dev-workflow を見れば分かる | worktree 専用名で発見性◎ |
| 責務 | dev-workflow が「開発環境セットアップ」を内包 | 単一責任原則寄り |
| 推奨タイミング | 初期段階（現在） | DB/port ロジックが大きくなったら分離 |

判断指針:

- DB / port 割当ロジックが「数行の bash 関数」で済むうちは dev-workflow に同梱
- 複数 DB エンジン対応・docker-compose 連携・k8s namespace 連携など機能が膨らんだら独立 plugin 化を検討
- 独立 plugin にする場合の名前候補: `parallel-worktree` / `worktree-env`

---

> プロジェクト固有のため必要に応じて override してください。
