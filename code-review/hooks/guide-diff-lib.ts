// guide-diff mod の純粋な部分（git の出力の整形と、テキストの組み立て）。$ に触れないので単体で試せる
import type { GuideFile, GuideGroup, GuideView } from '../types'

/**
 * Code 要素の source の上限は 10,000 文字。余白を残して切る。
 * 切るのはハンクの境目で。最初のハンクだけで上限を超えるときは行の境目で切り、見出しの行数を残した行に
 * 合わせる（見出しと行数が食い違う diff は diff として読まれず、行番号の無いただのコードとして描かれる）
 */
export const MAX_SOURCE = 9800

/** `@@ -a,b +c,d @@`。数を省いた範囲（`-a`）は 1 行 */
const HUNK_HEADER = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$/

/** 0 行の範囲は直前の行を始点にする（`git diff` と同じ書き方。新規ファイルの `-0,0`） */
function range(start: number, count: number, kept: number): string {
  if (kept > 0) return `${start},${kept}`
  return `${count === 0 ? start : start - 1},0`
}

/**
 * room 文字に収まるところまでハンクを残し、見出しの行数をその行に合わせる。
 * 本文の 1 行目すら入らないときは、その行を途中で切って 1 行だけ残す
 */
export function cutHunk(hunk: string[], room: number): string {
  const header = hunk[0] ?? ''
  const m = HUNK_HEADER.exec(header)
  if (m === null) return hunk.join('\n').slice(0, Math.max(0, room))
  // 書き直した見出しは、各側に `,0` が付くぶん（2 文字ずつ）元より長くなりうる
  const budget = room - header.length - 1 - 4
  const kept: string[] = []
  let size = 0
  for (const line of hunk.slice(1)) {
    if (line === '') continue
    if (size + line.length + 1 > budget) {
      if (kept.length === 0) kept.push(line.slice(0, Math.max(1, budget)))
      break
    }
    kept.push(line)
    size += line.length + 1
  }
  const removed = kept.filter(l => l[0] === '-' || l[0] === ' ').length
  const added = kept.filter(l => l[0] === '+' || l[0] === ' ').length
  const [, a, b, c, d, rest] = m
  const head = `@@ -${range(Number(a), b === undefined ? 1 : Number(b), removed)} +${range(Number(c), d === undefined ? 1 : Number(d), added)} @@${rest ?? ''}`
  return [head, ...kept].join('\n')
}

export const GROUP_LABEL: Record<GuideGroup, string> = {
  read: '精読',
  skim: '流し読み',
  skip: '読まなくてよい',
}

export const SOURCE_LABEL: Record<string, string> = {
  arg: '引数指定',
  reflog: 'このブランチを作った起点',
  default: 'default branch へのフォールバック',
}

/**
 * `git diff` の出力を Code（format: 'diff'）に渡せる形にする。
 * Code が受け付ける制御文字はタブと改行だけなので、それ以外（CR を含む）を落とす。
 * `diff --git` / `index` / mode の行は Code が読まないので、最初の `---` か `@@` から始める
 */
export function trimDiff(raw: string): { diff: string; isTruncated: boolean } {
  const clean = raw.replace(/\r/g, '').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '')
  const lines = clean.split('\n')
  const start = lines.findIndex(l => l.startsWith('--- ') || l.startsWith('@@'))
  if (start < 0) {
    // ハンクの無い差分（バイナリ・mode だけの変更）。そのまま見せる
    const text = clean.trim()
    return { diff: text.slice(0, MAX_SOURCE), isTruncated: text.length > MAX_SOURCE }
  }
  const body = lines.slice(start)
  const out: string[] = []
  let size = 0
  let i = 0
  while (i < body.length && !(body[i] ?? '').startsWith('@@')) {
    out.push(body[i] ?? '')
    size += (body[i] ?? '').length + 1
    i++
  }
  let isTruncated = false
  let hunks = 0
  while (i < body.length) {
    const hunk = [body[i] ?? '']
    i++
    while (i < body.length && !(body[i] ?? '').startsWith('@@')) {
      hunk.push(body[i] ?? '')
      i++
    }
    const text = hunk.join('\n')
    if (size + text.length + 1 > MAX_SOURCE) {
      isTruncated = true
      if (hunks === 0) out.push(cutHunk(hunk, MAX_SOURCE - size))
      break
    }
    out.push(text)
    size += text.length + 1
    hunks++
  }
  return { diff: out.join('\n').replace(/\n+$/, ''), isTruncated }
}

/** `git diff --numstat` の出力を path ごとの行数にする。バイナリ（`-`）は null */
export function parseNumstat(stdout: string): Map<string, { added: number | null; deleted: number | null }> {
  const map = new Map<string, { added: number | null; deleted: number | null }>()
  for (const line of stdout.split('\n')) {
    const parts = line.split('\t')
    if (parts.length < 3) continue
    const [a, d, ...rest] = parts
    const num = (s: string | undefined) => (s === undefined || s === '-' ? null : Number(s))
    map.set(rest.join('\t'), { added: num(a), deleted: num(d) })
  }
  return map
}

export type GuideRecord = {
  schema: number
  base_branch: string
  base_source: string
  diff_base: string
  head: string
  files: { path: string; group: GuideGroup }[]
}

/** guide-order.sh が書いた JSON を読む。形が違えば理由を返す（読める形だけを通す） */
export function parseRecord(text: string): GuideRecord | string {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return '読み順の記録が JSON として読めない'
  }
  const r = data as Partial<GuideRecord>
  if (r.schema !== 1) return `読み順の記録の版が違う（schema ${String(r.schema)}）`
  if (typeof r.diff_base !== 'string' || !/^[0-9a-f]{7,64}$/.test(r.diff_base)) return '比較先のコミットが記録に無い'
  if (!Array.isArray(r.files) || r.files.length === 0) return '読み順の記録にファイルが無い'
  const files = r.files.filter(
    (f): f is { path: string; group: GuideGroup } =>
      typeof f?.path === 'string' && f.path !== '' && (f.group === 'read' || f.group === 'skim' || f.group === 'skip'),
  )
  if (files.length === 0) return '読み順の記録にファイルが無い'
  return {
    schema: 1,
    base_branch: typeof r.base_branch === 'string' ? r.base_branch : '?',
    base_source: typeof r.base_source === 'string' ? r.base_source : 'unknown',
    diff_base: r.diff_base,
    head: typeof r.head === 'string' ? r.head : '',
    files,
  }
}

/** 1 行の「base」行。review-guide のレポート冒頭の行と同じ情報 */
export function baseLine(v: Pick<GuideView, 'baseBranch' | 'baseSource' | 'diffBase'>): string {
  const how = SOURCE_LABEL[v.baseSource] ?? v.baseSource
  return `base: ${v.baseBranch}（${how}）・比較先: ${v.diffBase.slice(0, 7)}`
}

function counts(f: GuideFile): string {
  if (f.added === null || f.deleted === null) return ''
  return ` +${f.added} −${f.deleted}`
}

/**
 * ペインが描けない場所（VS Code・-p）でも読める、コマンドの答えのテキスト。
 * waiting はペインが開いたまま描かれていない理由（engine の言葉のまま。狭い端末なら広げると置かれる）
 */
export function summaryText(v: GuideView, waiting?: string): string {
  const lines = [baseLine(v), `editor の比較先をこの commit にすると、タスクの diff だけが見える: git diff ${v.diffBase}`]
  if (v.isHeadMoved) lines.push('⚠️ 読み順ガイドを作った後にコミットが進んでいる（diff は今の作業ツリーと比較先の差）')
  for (const [i, f] of v.files.entries()) {
    lines.push(`${i + 1}. [${GROUP_LABEL[f.group]}] ${f.path}${counts(f)}`)
  }
  if (waiting !== undefined) lines.push(`（ペインはまだ描かれていない: ${waiting}。広い端末か Desktop なら 1 ファイルずつ送れる）`)
  return lines.join('\n')
}

export function fileLine(f: GuideFile, isCurrent: boolean, n: number): string {
  return `${isCurrent ? '▶' : ' '} ${n}. [${GROUP_LABEL[f.group]}] ${f.path}${counts(f)}`
}
