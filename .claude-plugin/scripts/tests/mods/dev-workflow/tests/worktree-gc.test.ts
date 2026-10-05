// dev-workflow の worktree-gc-pane mod（hooks/worktree-gc.tsx）のテスト。`claude plugin test` で走る
//
// scan の行は実物（使い捨てリポジトリで scan.sh を回した出力。パスだけ /w に置き換えた）
import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'

import { parseScan, selectionKey } from '../hooks/worktree-gc-lib'
import { parseArgs } from '../hooks/worktree-gc'

const SCAN = [
  "{\"repo\":\"/w/repo\",\"path\":\"/w/repo\",\"branch\":\"main\",\"head\":\"fcd12398b0f9288d661ea115a875a82b8a7e97b6\",\"kind\":\"other\",\"nested_parent\":null,\"self\":true,\"primary\":true,\"dirty\":false,\"untracked\":false,\"ahead_of_main\":0,\"pr\":null,\"merged_into_main\":true,\"issue\":null,\"live_pids\":[728,730,795,796,797,798,799],\"live_unknown\":false,\"marker\":null,\"db_guess\":[],\"unpushed\":0,\"remote_branches\":[\"origin/done\",\"origin/main\"],\"local_branches\":[],\"last_commit\":\"2026-10-04\",\"verdict\":\"keep\",\"reasons\":[\"self\",\"primary-worktree\",\"live-or-unknown-process\"]}",
  "{\"repo\":\"/w/repo\",\"path\":\"/w/wt-dirty\",\"branch\":\"dirty\",\"head\":\"fcd12398b0f9288d661ea115a875a82b8a7e97b6\",\"kind\":\"other\",\"nested_parent\":null,\"self\":false,\"primary\":false,\"dirty\":true,\"untracked\":true,\"ahead_of_main\":0,\"pr\":null,\"merged_into_main\":true,\"issue\":null,\"live_pids\":[],\"live_unknown\":false,\"marker\":null,\"db_guess\":[],\"unpushed\":0,\"remote_branches\":[\"origin/done\",\"origin/main\"],\"local_branches\":[],\"last_commit\":\"2026-10-04\",\"verdict\":\"keep\",\"reasons\":[\"dirty\"]}",
  "{\"repo\":\"/w/repo\",\"path\":\"/w/wt-done\",\"branch\":\"done\",\"head\":\"783aa18e6653cb535597997b5c1726e6cf70bae0\",\"kind\":\"other\",\"nested_parent\":null,\"self\":false,\"primary\":false,\"dirty\":false,\"untracked\":false,\"ahead_of_main\":1,\"pr\":null,\"merged_into_main\":false,\"issue\":null,\"live_pids\":[],\"live_unknown\":false,\"marker\":null,\"db_guess\":[],\"unpushed\":0,\"remote_branches\":[\"origin/done\"],\"local_branches\":[],\"last_commit\":\"2026-10-04\",\"verdict\":\"reap\",\"reasons\":[\"reapable\",\"pushed-clean\"]}",
]
const SURFACES = ['terminal', 'desktop'] as const
const DONE = SCAN[2] as string

type World = {
  runs: { argv: string[]; stdin?: string; env?: Record<string, string> }[]
  scan: string[]
  scanFails: boolean
  fetchFails: Set<string>
  surface: string | null
  placed: boolean
  opened: number
  closed: number
}

function newWorld(over: Partial<World> = {}): World {
  return { runs: [], scan: SCAN, scanFails: false, fetchFails: new Set(), surface: 'terminal', placed: true, opened: 0, closed: 0, ...over }
}

function out(stdout: string, exitCode = 0) {
  return { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
}

function stub(on: On, w: World) {
  on('session.cwd', () => ({ value: '/w/repo' }))
  on('session.surface', () => ({ value: w.surface as never }))
  on('process.run', (_$, e) => {
    const argv = [...e.argv]
    w.runs.push({ argv, ...(e.init?.stdin !== undefined ? { stdin: e.init.stdin } : {}), ...(e.init?.env ? { env: { ...e.init.env } } : {}) })
    if (argv[0] === 'git' && argv.includes('fetch')) return { value: out('', w.fetchFails.has(argv[2] ?? '') ? 1 : 0) }
    const script = argv[1] ?? ''
    if (script.endsWith('/scan.sh')) return { value: w.scanFails ? out('FATAL: x', 2) : out(`${w.scan.join('\n')}\n`) }
    if (script.endsWith('/reap.sh')) return { value: out(argv.includes('--dry-run') ? 'would remove /w/wt-done' : 'removed /w/wt-done') }
    return { value: out('', 127) }
  })
  on('ui.open', () => {
    w.opened++
    return { value: w.placed ? { isPlaced: true } : { isPlaced: false, reason: 'narrow' } }
  })
  on('ui.close', () => {
    w.closed++
    return { value: undefined }
  })
  on('ui.status', () => ({ value: undefined }))
  on('command.register', (_$, e) => ({ value: { command: e.name } }))
}

async function run($: Engine, args = '') {
  return $.command.run({ command: 'worktree-gc-pane', args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } })
}

function pane(surface: (typeof SURFACES)[number]) {
  return {
    plugin: 'dev-workflow',
    surface,
    component: 'Pane' as const,
    requestId: 'worktree-gc',
    props: { title: 'worktree-gc', isFocused: true, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} } as never,
  }
}

function reaps(w: World) {
  return w.runs.filter(r => (r.argv[1] ?? '').endsWith('/reap.sh'))
}

test('fetch してから scan し、候補と保持を出す（ペインがあれば答えは 1 行）', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  const r = await run($)
  expect(r.text).toBe('worktree-gc: 削除候補 1 件 / 保持 2 件')
  expect(w.runs[0]?.argv).toEqual(['git', '-C', '/w/repo', 'fetch', '--prune', '--quiet'])
  expect(w.runs[1]?.argv[1]).toMatch(/\/scripts\/worktree-gc\/scan\.sh$/)
  expect(w.opened).toBe(1)
  for (const surface of SURFACES) {
    const ui = await $.ui.mount(pane(surface))
    expect((await ui.find({ key: 't-2' }))?.text).toContain('☑ /w/wt-done')
    expect(await ui.find({ type: 'Text', text: /wt-dirty.*\[dirty\]/ })).toBeDefined()
    expect(await ui.find({ key: 't-1' })).toBeUndefined()
    expect(await ui.find({ key: 'reap' })).toBeUndefined()
    await ui.unmount()
  }
})

test('描く面が無い・ペインが置かれないときは表をテキストで返す', async ($, on) => {
  const w = newWorld({ surface: null })
  stub(on, w)
  const r = await run($)
  expect(r.text).toContain('削除候補:\n- /w/wt-done')
  expect(r.text).toContain('[dirty]')
  expect(r.text).toContain('worktree-gc スキル')
  w.surface = 'terminal'
  w.placed = false
  expect((await run($)).text).toContain('保持:')
})

test('dry-run → 削除。reap には scan の行を書き換えずに渡す', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  await run($)
  for (const surface of SURFACES) {
    w.runs = []
    await run($)
    const ui = await $.ui.mount(pane(surface))
    await ui.press({ key: 'dry' })
    expect(reaps(w).map(r => r.argv.includes('--dry-run'))).toEqual([true])
    expect(reaps(w)[0]?.stdin).toBe(`${DONE}\n`)
    expect(await ui.find({ type: 'Text', text: /would remove/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /まだ消していない/ })).toBeDefined()
    await ui.press({ key: 'reap' })
    expect(reaps(w).map(r => r.argv.includes('--dry-run'))).toEqual([true, false])
    expect(reaps(w)[1]?.stdin).toBe(`${DONE}\n`)
    expect(await ui.find({ type: 'Text', text: /削除の結果/ })).toBeDefined()
    await ui.press({ key: 't-2' })
    expect((await ui.find({ key: 't-2' }))?.text).toContain('☑')
    expect(await ui.find({ key: 'reap' })).toBeUndefined()
    await ui.unmount()
  }
})

test('dry-run の後に選び直したら、もう一度 dry-run するまで削除ボタンを出さない', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  await run($)
  const ui = await $.ui.mount(pane('terminal'))
  await ui.press({ key: 'dry' })
  expect(await ui.find({ key: 'reap' })).toBeDefined()
  await ui.press({ key: 't-2' })
  expect(await ui.find({ key: 'reap' })).toBeUndefined()
  expect(await ui.find({ key: 'dry' })).toBeUndefined()
  await ui.press({ key: 't-2' })
  expect(await ui.find({ key: 'reap' })).toBeUndefined()
  expect(await ui.find({ key: 'dry' })).toBeDefined()
  expect(reaps(w).filter(r => !r.argv.includes('--dry-run'))).toEqual([])
  await ui.press({ key: 'close' })
  expect(w.closed).toBe(1)
})

test('fetch に失敗したら、push 済みの判定が古いかもしれないと添える', async ($, on) => {
  const w = newWorld({ fetchFails: new Set(['/w/repo']), surface: null })
  stub(on, w)
  expect((await run($)).text).toContain('fetch できなかった: このリポ')
})

test('scan に失敗したらペインを開かずに理由を返す', async ($, on) => {
  const w = newWorld({ scanFails: true })
  stub(on, w)
  expect((await run($)).text).toContain('scan に失敗した')
  expect(w.opened).toBe(0)
})

test('--all はリポごとに fetch して scan し直し、root と userConfig の root を渡す', { options: { worktree_gc_root: '/projects' } }, async ($, on) => {
  const w = newWorld({ fetchFails: new Set(['/w/repo']) })
  stub(on, w)
  const r = await run($, '--all /src --no-lsof')
  const scans = w.runs.filter(x => (x.argv[1] ?? '').endsWith('/scan.sh'))
  expect(scans).toHaveLength(2)
  expect(scans[0]?.argv.slice(2)).toEqual(['--all', '/src', '--no-lsof'])
  expect(scans[0]?.env).toEqual({ DEV_WORKFLOW_WORKTREE_GC_ROOT: '/projects' })
  expect(w.runs.filter(x => x.argv[0] === 'git').map(x => x.argv[2])).toEqual(['/w/repo'])
  expect(r.text).toContain('fetch できなかった: /w/repo')
})

test('保持が多ければ先頭だけ出す', async ($, on) => {
  const keep = JSON.parse(SCAN[1] as string) as Record<string, unknown>
  const many = Array.from({ length: 33 }, (_, i) => JSON.stringify({ ...keep, path: `/w/k${i}` }))
  const w = newWorld({ scan: many })
  stub(on, w)
  await run($)
  const ui = await $.ui.mount(pane('terminal'))
  expect(await ui.find({ type: 'Text', text: /ほか 3 件/ })).toBeDefined()
  expect(await ui.findAll({ type: 'Text', text: /\[dirty\]/ })).toHaveLength(30)
  expect(await ui.find({ key: 'dry' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /削除候補は無い/ })).toBeDefined()
})

test('parseArgs / parseScan / selectionKey', () => {
  expect(parseArgs('')).toEqual({ isAll: false, root: null, extra: [] })
  expect(parseArgs('--all')).toEqual({ isAll: true, root: null, extra: [] })
  expect(parseArgs('--all --no-lsof --depth 6')).toEqual({ isAll: true, root: null, extra: ['--no-lsof', '--depth', '6'] })
  expect(parseArgs('--all ~/src')).toEqual({ isAll: true, root: '~/src', extra: [] })
  const rows = parseScan(`${SCAN.join('\n')}\nnot json\n{"path":"/x","verdict":"maybe"}\n`)
  expect(rows.map(r => r.verdict)).toEqual(['keep', 'keep', 'reap'])
  expect(rows[2]?.line).toBe(DONE)
  expect(selectionKey([true, false, true])).toBe('0,2')
})
