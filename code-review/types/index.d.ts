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

declare module 'claude-code' {
  interface PluginState {
    'code-review': { guideDiff: GuideView | null }
  }
}
