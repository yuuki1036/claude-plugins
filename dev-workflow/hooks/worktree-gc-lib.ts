// worktree-gc-pane mod の純粋な部分（scan.sh の出力の読み取りと、表示の組み立て）。
// 分類の正本は skills/worktree-gc/references/classification.md（ここでは判定し直さない）
import type { GcRow } from '../types'

/** scan.sh の出力（1 行 1 JSON）。行の文字列は reap にそのまま渡すので書き換えずに持つ */
export function parseScan(stdout: string): GcRow[] {
  const rows: GcRow[] = []
  for (const line of stdout.split('\n')) {
    if (line.trim() === '') continue
    let d: Record<string, unknown>
    try {
      d = JSON.parse(line) as Record<string, unknown>
    } catch {
      continue
    }
    if (typeof d.path !== 'string' || (d.verdict !== 'reap' && d.verdict !== 'keep')) continue
    const pr = d.pr as { number?: unknown; state?: unknown } | null
    rows.push({
      line,
      repo: typeof d.repo === 'string' ? d.repo : '',
      path: d.path,
      branch: typeof d.branch === 'string' ? d.branch : null,
      head: typeof d.head === 'string' ? d.head : null,
      kind: typeof d.kind === 'string' ? d.kind : 'other',
      verdict: d.verdict,
      reasons: Array.isArray(d.reasons) ? d.reasons.filter((r): r is string => typeof r === 'string') : [],
      pr: pr && typeof pr.number === 'number' && typeof pr.state === 'string' ? `#${pr.number} ${pr.state}` : null,
      lastCommit: typeof d.last_commit === 'string' ? d.last_commit : null,
    })
  }
  return rows
}

/** 1 行の表示。ブランチが無ければ HEAD の短縮 sha */
export function rowLabel(r: GcRow): string {
  const ref = r.branch ?? (r.head ? `(detached ${r.head.slice(0, 7)})` : '(?)')
  const extra = [r.kind, r.pr, r.lastCommit].filter(Boolean).join(' · ')
  return `${r.path}  ${ref}  ${extra}`
}

/** ペインを描けない場所で返すテキスト。削除はここからはしない */
export function summaryText(rows: GcRow[], note: string): string {
  const reap = rows.filter(r => r.verdict === 'reap')
  const keep = rows.filter(r => r.verdict === 'keep')
  const lines = [`worktree-gc: 削除候補 ${reap.length} 件 / 保持 ${keep.length} 件${note}`]
  if (reap.length > 0) lines.push('', '削除候補:', ...reap.map(r => `- ${rowLabel(r)}  [${r.reasons.join(', ')}]`))
  if (keep.length > 0) lines.push('', '保持:', ...keep.map(r => `- ${rowLabel(r)}  [${r.reasons.join(', ')}]`))
  lines.push(
    '',
    '削除は、ペインで行を選んで dry-run → 削除の順に押す。ペインが無い場所では worktree-gc スキル（「worktree 棚卸し」）で承認して消す',
  )
  return lines.join('\n')
}

/** 選んだ行の組の鍵。dry-run の後に選び直したら、削除ボタンを出し直さない */
export function selectionKey(selected: readonly boolean[]): string {
  return selected.map((s, i) => (s ? i : '')).filter(x => x !== '').join(',')
}
