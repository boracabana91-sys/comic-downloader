// Acceptance tests on the owner's GOLDEN inputs (FIX_PROMPT §3). Runs when the files are present:
//   CATTY_GOLDEN_DIR (default /tmp/golden_inputs) containing Sol_Street_71.m4a, money_mode_wil_intro.mp3,
//   money_mode_wil_chorus_2.mp3 — and the UVR model at CATTY_MDX_MODEL (default /tmp/models/UVR-MDX-NET-Voc_FT.onnx).
// Prints PASS/FAIL with the measured number, and the differences from golden/casanova_cat_v1.mp4.
import { describe, it, expect, beforeAll } from 'vitest'
import { createRequire } from 'node:module'
import { existsSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { buildAudio, renderDraft, inProcessIsolator, type AudioPlan } from '@engine/project'
import { FORMATS } from '@engine/formats'
import { grayFrames, flashFrames, loopScore, loudnessCurve } from '@engine/preflight'

const require = createRequire(import.meta.url)
const ff: string = require('ffmpeg-static')
const G = process.env.CATTY_GOLDEN_DIR ?? '/tmp/golden_inputs'
const MODEL = process.env.CATTY_MDX_MODEL ?? '/tmp/models/UVR-MDX-NET-Voc_FT.onnx'
const VOICE = join(G, 'Sol_Street_71.m4a')
const INTRO = join(G, 'money_mode_wil_intro.mp3')
const CHORUS = join(G, 'money_mode_wil_chorus_2.mp3')
const GOLDEN_MP4 = join(__dirname, '..', 'reference_kit', 'golden', 'casanova_cat_v1.mp4')
const have = [VOICE, INTRO, CHORUS, MODEL].every(existsSync)
const OUT = '/tmp/catty-golden'

const report: string[] = []
const check = (name: string, ok: boolean, measured: string) => {
  report.push(`${ok ? 'PASS' : 'FAIL'}  ${name} — measured ${measured}`)
  return ok
}

describe.skipIf(!have)('golden case: Sol_Street_71 + intro + chorus_2, punch units 2,3', () => {
  let plan: AudioPlan
  let qa: { ok: boolean; text: string }[] = []
  beforeAll(async () => {
    mkdirSync(join(OUT, 'work'), { recursive: true })
    plan = await buildAudio({
      ffmpeg: ff, workDir: join(OUT, 'work'), voice: VOICE,
      music: [{ path: INTRO, role: 'intro' }, { path: CHORUS, role: 'punchline' }],
      pauseSec: 2, punchUnits: [2, 3], mdx: inProcessIsolator(ff, require('onnxruntime-node'), MODEL), style: 'draw', duration: 18
    })
    const r = await renderDraft({ ffmpeg: ff, workDir: join(OUT, 'work'), outFile: join(OUT, 'golden-mine.mp4'), plan, visual: { type: 'drawn' }, fmt: FORMATS.vertical })
    qa = r.qa
  }, 3_600_000)

  it('units found: (1.35–2.93) (4.08–5.33) (6.37–6.87) (7.98–8.68) ±0.05 s', () => {
    const want = [[1.35, 2.93], [4.08, 5.33], [6.37, 6.87], [7.98, 8.68]]
    const got = plan.phrases.map((p) => [p.startSec, p.endSec])
    const ok = got.length === 4 && want.every((w, i) => Math.abs(w[0] - got[i][0]) <= 0.05 && Math.abs(w[1] - got[i][1]) <= 0.05)
    expect(check('units', ok, JSON.stringify(got.map((u) => u.map((x) => +x.toFixed(2)))))).toBe(true)
  })
  it('chorus downbeat on 8.24 ±0.02; intro offset 1.18 ±0.03', () => {
    const tl = plan.timeline
    expect(check('chorus downbeat on punch', Math.abs(plan.syncErrorMs!) <= 20, `${plan.syncErrorMs} ms`)).toBe(true)
    expect(check('intro offset', Math.abs(tl.intro_offset! - 1.18) <= 0.03, `${tl.intro_offset}`)).toBe(true)
  })
  it('punch unit starts at 8.24 ±0.04; pause 2.00 ±0.05', () => {
    const tl = plan.timeline
    const start = Math.min(...tl.placed.filter((p) => tl.punch_units.includes(p.unit)).map((p) => p.dest[0]))
    expect(check('punch unit start', Math.abs(start - 8.24) <= 0.04, start.toFixed(3))).toBe(true)
    expect(check('pause before punch', Math.abs(tl.pause_before_punch - 2) <= 0.05, `${tl.pause_before_punch}`)).toBe(true)
  })
  it('cuts exactly 9.24 10.24 11.24 12.44 13.44 14.54 15.64', () => {
    expect(check('cuts', JSON.stringify(plan.timeline.cuts) === JSON.stringify([9.24, 10.24, 11.24, 12.44, 13.44, 14.54, 15.64]), JSON.stringify(plan.timeline.cuts))).toBe(true)
  })
  it('voice ≥ 8 dB over music; −14…−16.5 LUFS; peak ≤ −1; 18.0 s; flashes; no loop; mouth closed (preflight on the mp4)', () => {
    for (const q of qa) check(q.text, q.ok, '')
    expect(qa.filter((q) => !q.ok).map((q) => q.text)).toEqual([])
  })
  it('compare with golden/casanova_cat_v1.mp4 (cut times + per-second loudness)', async () => {
    const mine = join(OUT, 'golden-mine.mp4')
    const [fm, fg] = [await grayFrames(ff, mine), await grayFrames(ff, GOLDEN_MP4)]
    const [cm, cg] = [flashFrames(fm).map((f) => +(f / 30).toFixed(2)), flashFrames(fg).map((f) => +(f / 30).toFixed(2))]
    const [lm, lg] = [await loudnessCurve(ff, mine), await loudnessCurve(ff, GOLDEN_MP4)]
    report.push(`flash/cut times  mine:   ${cm.join(' ')}`, `flash/cut times  golden: ${cg.join(' ')}`)
    report.push(`loudness per second (dB) mine/golden/diff:`)
    for (let s = 0; s < Math.min(lm.length, lg.length, 18); s++) report.push(`  ${String(s).padStart(2)}s  ${lm[s].toFixed(1).padStart(6)}  ${lg[s].toFixed(1).padStart(6)}  ${(lm[s] - lg[s]).toFixed(1).padStart(5)}`)
    report.push(`loop score mine ${loopScore(fm).toFixed(2)} golden ${loopScore(fg).toFixed(2)}`)
    console.log('\n' + report.join('\n'))
    expect(cm.length).toBe(cg.length)
  }, 600_000)
})
