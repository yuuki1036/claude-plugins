// issue-band mod の純粋な部分（frontmatter とチェックリストの読み取り、帯の文の組み立て）
import type { IssueBand } from '../types'

/** `---` で囲まれた先頭の frontmatter を key → 値にする（行末の ` # 注釈` と囲みの引用符は外す） */
export function frontmatter(text: string): Record<string, string> {
  const lines = text.split('\n')
  if (lines[0]?.trim() !== '---') return {}
  const out: Record<string, string> = {}
  for (const line of lines.slice(1)) {
    if (line.trim() === '---') break
    const m = /^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$/.exec(line)
    if (!m) continue
    const raw = (m[2] ?? '').trim()
    // 引用符で囲まれた値は中の ` # ` を注釈と見なさない
    const quoted = /^(["'])(.*?)\1(\s+#.*)?$/.exec(raw)
    out[m[1] as string] = quoted ? (quoted[2] ?? '') : raw.replace(/\s+#(\s.*)?$/, '').trim()
  }
  return out
}

/** `.claude/session-context.md`（issue-workflow:start が書く）のブランチと Issue ID */
export function sessionContext(text: string): { branch: string; issueId: string } | null {
  const fm = frontmatter(text)
  const branch = fm.branch ?? ''
  const issueId = fm.issue_id ?? ''
  // ID はファイル名に入るので、英数字・`-`・`_` 以外を含む値は採らない
  if (branch === '' || !/^[A-Za-z0-9_-]+$/.test(issueId)) return null
  return { branch, issueId }
}

/** scope_size ごとのタスク数の上限（hooks/scripts/check-scope-size.sh と同じ値） */
export const SCOPE_LIMIT: Record<string, number> = { small: 3, medium: 7, large: 15 }

/**
 * Issue ファイルの要約。チェックリストは `## 進捗` を優先し、無ければ `## 完了条件` を数える
 * （check-scope-size.sh と同じ規則 / GitHub issue #179。両方を足すと移行途中のファイルで二重に数える）
 */
export function issueSummary(text: string, issueId: string, branch: string): IssueBand {
  const fm = frontmatter(text)
  const heading = text.split('\n').find(l => l.startsWith('# '))
  const title = heading ? heading.slice(2).replace(new RegExp(`^${issueId}:\\s*`), '').trim() : ''
  const count = { p: { done: 0, total: 0 }, d: { done: 0, total: 0 } }
  let sec: 'p' | 'd' | null = null
  for (const line of text.split('\n')) {
    if (/^## 進捗\s*$/.test(line)) sec = 'p'
    else if (/^## 完了条件\s*$/.test(line)) sec = 'd'
    else if (line.startsWith('## ')) sec = null
    else if (sec) {
      const m = /^\s*-\s*\[([ xX])\]/.exec(line)
      if (m) {
        count[sec].total++
        if (m[1] !== ' ') count[sec].done++
      }
    }
  }
  const tasks = count.p.total > 0 ? count.p : count.d
  const scopeSize = fm.scope_size ?? ''
  return {
    issueId,
    title,
    status: fm.status ?? '',
    type: fm.type ?? '',
    branch,
    scopeSize,
    done: tasks.done,
    total: tasks.total,
    limit: SCOPE_LIMIT[scopeSize] ?? null,
  }
}

export function bandLine(b: IssueBand): string {
  const parts = [b.title ? `${b.issueId} ${b.title}` : b.issueId, b.status, b.type]
  if (b.total > 0) parts.push(`タスク ${b.done}/${b.total}`)
  parts.push(b.branch)
  return parts.filter(p => p !== '').join(' · ')
}

/** scope_size の上限を超えたときの 1 行。超えていなければ null */
export function overLine(b: IssueBand): string | null {
  if (b.limit === null || b.total <= b.limit) return null
  return `⚠️ タスク ${b.total} 件が scope_size=${b.scopeSize} の上限 ${b.limit} を超えている（別 Issue に切り出すか scope_size を上げる / /issue-maintain）`
}
