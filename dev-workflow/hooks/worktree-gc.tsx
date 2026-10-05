// worktree-gc-pane: worktree の棚卸しを、モデルを呼ばずにペインで行う mod
//
// worktree-gc スキルは scan（副作用なし）→ 承認 → reap の 2 段で、scan と reap は同梱スクリプトが
// 決定的に行う。モデルがやっていたのは表に整えることと承認を取ることだけなので、ここでは scan.sh の
// 出力をそのままペインに並べ、行を選んで dry-run → 削除をボタンで押す（押すことが承認）。
// reap.sh には scan が出した行を書き換えずに渡す（入力契約 / ADR-20260912142858）。
// Linear の Issue 状態で分類を補う段（スキルの Step 1.5）は MCP が要るので、ここでは行わない
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On, PluginOptions } from 'claude-code'

import type { GcView } from '../types'
import { parseScan, rowLabel, selectionKey, summaryText } from './worktree-gc-lib'

const PANE = 'worktree-gc'
const COMMAND = 'worktree-gc-pane'
/** 保持の行は多くなりがちなので、ペインでは先頭だけ出す */
const KEEP_ROWS = 30
const view = atom({ plugin: 'dev-workflow', key: 'gc' } as const, null)

type Args = { isAll: boolean; root: string | null; extra: string[] }

export function parseArgs(text: string): Args {
  const words = text.split(/\s+/).filter(w => w !== '')
  const out: Args = { isAll: false, root: null, extra: [] }
  for (let i = 0; i < words.length; i++) {
    const w = words[i] as string
    if (w === '--all') {
      out.isAll = true
      const next = words[i + 1]
      if (next !== undefined && !next.startsWith('--')) {
        out.root = next
        i++
      }
    } else if (w === '--no-lsof') {
      out.extra.push(w)
    } else if (w === '--depth' && words[i + 1] !== undefined) {
      out.extra.push(w, words[i + 1] as string)
      i++
    }
  }
  return out
}

async function sh($: EngineInterface, argv: string[], cwd: string, opts: { stdin?: string; env?: Record<string, string>; timeoutMs?: number } = {}) {
  try {
    const r = await $.process.run(argv, { cwd, timeoutMs: opts.timeoutMs ?? 300_000, ...(opts.stdin !== undefined ? { stdin: opts.stdin } : {}), ...(opts.env ? { env: opts.env } : {}) })
    return { ok: r.exitCode === 0, out: `${r.stdout}${r.stderr}`, stdout: r.stdout }
  } catch (err) {
    return { ok: false, out: String(err), stdout: '' }
  }
}

/** scan の前に remote 追跡ブランチを更新する（push 済みの判定が古い追跡ブランチで誤る / #268） */
async function fetch($: EngineInterface, repo: string): Promise<boolean> {
  return (await sh($, ['git', '-C', repo, 'fetch', '--prune', '--quiet'], repo, { timeoutMs: 120_000 })).ok
}

async function reap($: EngineInterface, dryRun: boolean) {
  const v = await read($, view)
  if (v === null) return
  const lines = v.rows.filter((r, i) => r.verdict === 'reap' && v.selected[i]).map(r => r.line)
  if (lines.length === 0) return
  const key = selectionKey(v.selected)
  await update($, view, (x): GcView | null => (x === null ? x : { ...x, phase: 'running', output: '' }))
  const cwd = await $.session.cwd()
  const argv = ['bash', `${$.plugin.root}/scripts/worktree-gc/reap.sh`, ...(dryRun ? ['--dry-run'] : [])]
  const r = await sh($, argv, cwd, { stdin: `${lines.join('\n')}\n`, timeoutMs: 600_000 })
  await update($, view, (x): GcView | null =>
    x === null ? x : { ...x, phase: dryRun ? 'dry' : 'done', dryKey: dryRun ? key : '', output: r.out.trim() || '(出力なし)' },
  )
}

export function registerWorktreeGc(on: On, options: PluginOptions) {
  const root = typeof options.worktree_gc_root === 'string' ? options.worktree_gc_root : ''

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: 'worktree を棚卸しし、ペインで選んで dry-run → 削除する（worktree-gc をモデルを呼ばずに）',
      argumentHint: '[--all [root]] [--no-lsof]',
    })
    return next(e)
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    const args = parseArgs(e.args)
    const cwd = await $.session.cwd()
    const scanArgv = ['bash', `${$.plugin.root}/scripts/worktree-gc/scan.sh`, ...(args.isAll ? ['--all', ...(args.root ? [args.root] : [])] : []), ...args.extra]
    const env = root !== '' ? { DEV_WORKFLOW_WORKTREE_GC_ROOT: root } : undefined
    $.ui.status('worktree-gc: scan 中')
    const failed: string[] = []
    if (!args.isAll && !(await fetch($, cwd))) failed.push('このリポ')
    let scan = await sh($, scanArgv, cwd, env ? { env } : {})
    if (args.isAll && scan.ok) {
      // 横断では、見つかったリポごとに fetch してから scan し直す
      for (const repo of new Set(parseScan(scan.stdout).map(r => r.repo).filter(r => r !== ''))) {
        if (!(await fetch($, repo))) failed.push(repo)
      }
      scan = await sh($, scanArgv, cwd, env ? { env } : {})
    }
    $.ui.status(undefined)
    if (!scan.ok) return { text: `worktree-gc: scan に失敗した\n${scan.out.trim()}` }
    const rows = parseScan(scan.stdout)
    const note = failed.length > 0 ? `（fetch できなかった: ${failed.join(', ')}。push 済みの判定が古い追跡ブランチに拠る）` : ''
    await update($, view, () => ({ rows, selected: rows.map(r => r.verdict === 'reap'), phase: 'list', dryKey: '', output: '', note }))
    const opened = await $.ui.open({ id: PANE, title: 'worktree-gc' })
    const text = summaryText(rows, note)
    // 描く面が無い（`-p`）と isPlaced は true のまま返るので、面の有無でも見る
    const isDrawn = opened.isPlaced && (await $.session.surface()) !== null
    return { text: isDrawn ? (text.split('\n')[0] ?? text) : text }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    if (v === null) return <Text dimColor>/{COMMAND} で worktree を棚卸しする</Text>
    const reapIdx = v.rows.map((r, i) => (r.verdict === 'reap' ? i : -1)).filter(i => i >= 0)
    const keep = v.rows.filter(r => r.verdict === 'keep')
    const n = reapIdx.filter(i => v.selected[i]).length
    const isLocked = v.phase === 'running' || v.phase === 'done'
    return (
      <Box flexDirection="column">
        <Text bold>
          削除候補 {reapIdx.length} 件（選択 {n}）/ 保持 {keep.length} 件{v.note}
        </Text>
        <Box flexDirection="column" marginTop={1}>
          {reapIdx.length === 0 && <Text dimColor>削除候補は無い</Text>}
          {reapIdx.map(i => {
            const r = v.rows[i]
            if (!r) return null
            return (
              <Button
                key={`t-${i}`}
                label={`${v.selected[i] ? '☑' : '☐'} ${rowLabel(r)}`}
                onPress={() =>
                  isLocked
                    ? undefined
                    : update($, view, x => {
                        if (x === null) return x
                        const selected = x.selected.map((s, j) => (j === i ? !s : s))
                        return { ...x, selected, phase: selectionKey(selected) === x.dryKey ? x.phase : 'list' }
                      })
                }
              />
            )
          })}
        </Box>
        <Box gap={1} marginTop={1}>
          {v.phase === 'list' && n > 0 && <Button key="dry" label={`dry-run で確認（${n} 件）`} onPress={() => reap($, true)} />}
          {v.phase === 'dry' && n > 0 && (
            <Button key="reap" label={`削除する（${n} 件）`} variant="primary" onPress={() => reap($, false)} />
          )}
          <Button key="close" label="閉じる" role="dismiss" onPress={() => $.ui.close({ id: PANE })} />
        </Box>
        {v.phase === 'running' && <Text dimColor>実行中…</Text>}
        {v.output !== '' && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>{v.phase === 'done' ? '削除の結果' : 'dry-run の結果（まだ消していない）'}</Text>
            <Text>{v.output}</Text>
            {v.phase === 'done' && <Text dimColor>もう一度棚卸しするときは /{COMMAND}</Text>}
          </Box>
        )}
        {keep.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>保持</Text>
            {keep.slice(0, KEEP_ROWS).map(r => (
              <Text dimColor wrap="truncate-end">
                {rowLabel(r)} [{r.reasons.join(', ')}]
              </Text>
            ))}
            {keep.length > KEEP_ROWS && <Text dimColor>ほか {keep.length - KEEP_ROWS} 件</Text>}
          </Box>
        )}
      </Box>
    )
  })
}
