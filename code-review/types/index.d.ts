// code-review の mod（hooks/guide-diff.tsx）が $.state に置く値の型の契約
// `claude plugin validate` が、モジュールの書く $.state のキーをこの宣言と突き合わせる

/** 読み順の群: 精読 / 流し読み / 読まなくてよい（review-guide のレポートの 3 区分） */
export type GuideGroup = 'read' | 'skim' | 'skip'

export type GuideFile = {
  path: string
  group: GuideGroup
  /** 比較先からの追加・削除行数。未追跡の新規ファイル・バイナリは null */
  added: number | null
  deleted: number | null
}

export type GuideView = {
  /** 作業ツリーのルート（git diff をここで走らせる） */
  root: string
  baseBranch: string
  /** base branch の決め方: arg / reflog / default（scripts/lib/base-branch.sh） */
  baseSource: string
  /** 比較先: base branch との分岐点のコミット */
  diffBase: string
  /** ガイドを作った後に HEAD が進んだ（コミットした）か */
  isHeadMoved: boolean
  files: GuideFile[]
  index: number
  /** 今のファイルの diff（Code に渡す形に整えた後） */
  diff: string
  isTruncated: boolean
}

/** review / self-review の進み具合（hooks/review-progress.tsx が帯に出す） */
export type ReviewProgress = {
  /** start に `--pr` が付いていれば review */
  kind: 'review' | 'self-review'
  startedAt: number
  /** 経過時間の表示に使う今の時刻（1 分ごとに進める） */
  now: number
  /** 最後に何かが起きた時刻。長く何も起きなければ帯を消す */
  lastEventAt: number
  /** main が起動した agent の数と、そのうち終わった数 */
  spawned: number
  done: number
  /** run_in_background で起動した agent の数 */
  background: number
  /** 初回レポートを出した（`mark t2`） */
  isReported: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'code-review': { guideDiff: GuideView | null; progress: ReviewProgress | null; progressHidden: boolean }
  }
}
