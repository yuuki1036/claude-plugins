// issue-workflow の issue-band mod（hooks/issue-band.tsx）のテスト。`claude plugin test` で走る
import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'

import { frontmatter, issueSummary } from '../hooks/issue-band-lib'

const ROOT = '/w/app'
const SURFACES = ['terminal', 'desktop'] as const

function ctx(branch: string, id: string) {
  return `---\nshared_state_type: session\nproducer: issue-workflow\nbranch: ${branch}\nissue_id: ${id}\n---\n# セッションコンテキスト\n`
}

function issue(id: string, opts: { scope?: string; progress?: string[]; done?: string[] } = {}) {
  const fm = `---\nstatus: in-progress          # 必須\nid: ${id}\ntype: feature\nscope_size: ${opts.scope ?? 'medium'}\n---\n# ${id}: 帯を出す\n\n## 概要\nx\n`
  const p = opts.progress ? `\n## 進捗\n${opts.progress.join('\n')}\n` : ''
  const d = opts.done ? `\n## 完了条件\n${opts.done.join('\n')}\n` : ''
  return fm + p + d + '\n## メモ\n- [ ] 数えない\n'
}

type World = { branch: string; files: Record<string, string>; slugs: Record<string, string[]>; reads: string[] }

function newWorld(over: Partial<World> = {}): World {
  return {
    branch: 'feat/band',
    files: {
      [`${ROOT}/.claude/session-context.md`]: ctx('feat/band', 'MYAPP-3'),
      [`${ROOT}/.claude/indie/myapp/issues/MYAPP-3.md`]: issue('MYAPP-3', { progress: ['- [x] a', '- [X] b', '- [ ] c', '  - [ ] d', '- [ ] e'] }),
    },
    slugs: { indie: ['other', 'myapp'] },
    reads: [],
    ...over,
  }
}

function out(stdout: string, exitCode = 0) {
  return { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
}

function stub(on: On, w: World) {
  on('session.cwd', () => ({ value: `${ROOT}/src` }))
  on('process.run', (_$, e) => {
    const a = e.argv.join(' ')
    if (a === 'git rev-parse --show-toplevel') return { value: out(`${ROOT}\n`) }
    if (a === 'git rev-parse --abbrev-ref HEAD') return { value: out(`${w.branch}\n`) }
    return { value: out('', 2) }
  })
  on('fs.read', (_$, e) => {
    w.reads.push(e.path)
    const t = w.files[e.path]
    return t === undefined ? { deny: `ENOENT ${e.path}` } : { value: t }
  })
  on('fs.list', (_$, e) => {
    const backend = e.path.split('/').pop() ?? ''
    const names = w.slugs[backend]
    return names ? { value: names.map(name => ({ name, isDirectory: true })) as never } : { deny: 'ENOENT' }
  })
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false } as never, text: '' }))
  on('prompt.submit', (_$, e) => ({ text: e.text }))
  on('ui.render', { component: 'AbovePrompt' }, () => ({ type: 'Text', props: {}, children: ['BELOW'] }) as never)
}

async function submit($: Engine) {
  await $.prompt.submit({ text: 'hi' } as never)
}

async function band($: Engine, surface: (typeof SURFACES)[number] = 'terminal') {
  const ui = await $.ui.mount({ plugin: 'issue-workflow', surface, component: 'AbovePrompt', props: { hasSurvey: false, isWorking: false, maxRows: 10 } as never })
  const line = (await ui.find({ type: 'Text', text: /feat\/|MYAPP|OTHER/ }))?.text
  const over = (await ui.find({ type: 'Text', text: /scope_size=/ }))?.text
  const below = (await ui.find({ type: 'Text', text: 'BELOW' }))?.text
  return { ui, line, over, below }
}

test('作業中の Issue をタイトル・状態・タスクの進み・ブランチで出し、下の帯も残す', async ($, on) => {
  stub(on, newWorld())
  await submit($)
  for (const s of SURFACES) {
    const b = await band($, s)
    expect(b.line).toBe('MYAPP-3 帯を出す · in-progress · feature · タスク 2/5 · feat/band')
    expect(b.over).toBeUndefined()
    expect(b.below).toBe('BELOW')
    await b.ui.unmount()
  }
})

test('session-context のブランチが今と違う・無い・ID が不正なら出さない', async ($, on) => {
  const w = newWorld({ branch: 'main' })
  stub(on, w)
  await submit($)
  let b = await band($)
  expect(b.line).toBeUndefined()
  expect(b.below).toBe('BELOW')
  await b.ui.unmount()

  w.branch = 'feat/band'
  w.files[`${ROOT}/.claude/session-context.md`] = ctx('feat/band', '../x')
  await submit($)
  b = await band($)
  expect(b.line).toBeUndefined()
  await b.ui.unmount()

  delete w.files[`${ROOT}/.claude/session-context.md`]
  await submit($)
  b = await band($)
  expect(b.line).toBeUndefined()
})

test('Issue ファイルが見つからなくても ID とブランチは出す / linear の側も探す', async ($, on) => {
  const w = newWorld({ slugs: { indie: ['myapp'], linear: ['team'] } })
  w.files[`${ROOT}/.claude/session-context.md`] = ctx('feat/band', 'TEAM-9')
  stub(on, w)
  await submit($)
  let b = await band($)
  expect(b.line).toBe('TEAM-9 · feat/band')
  await b.ui.unmount()
  w.files[`${ROOT}/.claude/linear/team/issues/TEAM-9.md`] = issue('TEAM-9', { done: ['- [ ] x'] })
  await submit($)
  b = await band($)
  expect(b.line).toBe('TEAM-9 帯を出す · in-progress · feature · タスク 0/1 · feat/band')
})

test('scope_size の上限を超えたら知らせる（check-scope-size.sh と同じ上限）', async ($, on) => {
  const w = newWorld()
  w.files[`${ROOT}/.claude/indie/myapp/issues/MYAPP-3.md`] = issue('MYAPP-3', { scope: 'small', progress: ['- [ ] 1', '- [ ] 2', '- [ ] 3'] })
  stub(on, w)
  await submit($)
  expect((await band($)).over).toBeUndefined()
  w.files[`${ROOT}/.claude/indie/myapp/issues/MYAPP-3.md`] = issue('MYAPP-3', { scope: 'small', progress: ['- [ ] 1', '- [ ] 2', '- [ ] 3', '- [x] 4'] })
  await submit($)
  expect((await band($)).over).toContain('タスク 4 件が scope_size=small の上限 3')
})

test('Issue / session-context の編集とブランチの切り替えで読み直す（subagent・他のファイルでは読まない）', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  await submit($)
  const issuePath = `${ROOT}/.claude/indie/myapp/issues/MYAPP-3.md`
  w.files[issuePath] = issue('MYAPP-3', { progress: ['- [x] a'] })

  w.reads = []
  await $.tool.call({ tool: 'Edit', file_path: `${ROOT}/src/x.ts`, old_string: 'a', new_string: 'b' })
  await $.tool.call({ tool: 'Edit', file_path: issuePath, old_string: 'a', new_string: 'b', agentId: 'sub-1' } as never)
  await $.tool.call({ tool: 'Bash', command: 'git status' })
  expect(w.reads).toEqual([])

  await $.tool.call({ tool: 'Write', file_path: issuePath, content: 'x' })
  expect((await band($)).line).toContain('タスク 1/1')

  w.branch = 'main'
  await $.tool.call({ tool: 'Bash', command: 'git switch main' })
  expect((await band($)).line).toBeUndefined()
})

test('隠すと消え、別の Issue に移るとまた出る', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  await submit($)
  const b = await band($)
  await b.ui.press({ key: 'hide-issue' })
  await b.ui.unmount()
  await submit($)
  expect((await band($)).line).toBeUndefined()

  w.files[`${ROOT}/.claude/session-context.md`] = ctx('feat/band', 'MYAPP-4')
  w.files[`${ROOT}/.claude/indie/myapp/issues/MYAPP-4.md`] = issue('MYAPP-4')
  await submit($)
  expect((await band($)).line).toContain('MYAPP-4')
})

test('frontmatter / issueSummary', () => {
  expect(frontmatter('---\na: 1  # c\nb: "x # y"\n---\nc: 3\n')).toEqual({ a: '1', b: 'x # y' })
  expect(frontmatter('no\n---\n')).toEqual({})
  const s = issueSummary(issue('X-1', { progress: ['- [x] a'], done: ['- [ ] b', '- [ ] c'] }), 'X-1', 'br')
  expect([s.done, s.total, s.limit, s.title]).toEqual([1, 1, 7, '帯を出す'])
  const d = issueSummary(issue('X-1', { done: ['- [ ] b', '- [x] c'] }), 'X-1', 'br')
  expect([d.done, d.total]).toEqual([1, 2])
  expect(issueSummary(issue('X-1', { scope: 'huge' }), 'X-1', 'br').limit).toBeNull()
})
