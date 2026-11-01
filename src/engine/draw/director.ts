// The Director: builds the shot list FROM timeline.json (FIX_PROMPT §2.3), porting
// reference_kit/engine_reference/cat_run.py. Nothing about timing is hard-coded:
// - the opening/reveal runs from 0 to the punch time, its keys time-warped onto THIS video's
//   talk part and pause (the reference was keyed for talk 0–6.24 s and a pause 6.24–8.24 s);
// - one take per cut from the timeline (punch take first), keys scaled to each take's length;
// - the last take is the flirty smirk; longer videos re-use takes in a different order (never a cycle);
// - hearts only at the very end; PCHIP everywhere (never per-segment smoothstep).
import { pchip } from './pchip'
import { REST_POSE, type CatPose } from './cat'

export const FPS = 30

export interface DirectorTimeline {
  punch_time: number
  cuts: number[]
  duration: number
  pause_before_punch: number
}

export interface Camera { zoom: number; fx: number; fy: number; roll: number }
export interface FrameState {
  cam: Camera
  pose: CatPose
  /** Fade from black at the start (0..1), white flash (0..1) and blur radius (px at 720 wide). */
  fade: number
  flash: number
  blur: number
  takeIndex: number
}

type Keys = [number, number][]
type Shot = Record<string, Keys>

// Reference rest values (cat_run.py D).
const D: Record<string, number> = {
  z: 1.0, cx: 360, cy: 640, roll: 0, bob: 0, hr: 0, hy: 0, ear: 0, blush: 0.35, look: 0, lookv: 0, wink: 0, blink: 0,
  lid: 0.42, brow: 0.3, browl: 0, smirk: 0.7, grin: 0, sip: 0
}

// ───────────── reference opening (0 → 8.24), keyed for talk 0–6.24 s + pause 6.24–8.24 s ─────────────
const REF_P = 8.24
const REF_PAUSE_START = 6.24
const OPEN: Shot = {
  z: [[0, 3.3], [2.4, 2.7], [4.4, 1.3], [6.2, 1.18], [7.4, 1.3], [8.23, 1.5]],
  cx: [[0, 521], [2.4, 500], [4.4, 372], [6.2, 360], [8.23, 360]],
  cy: [[0, 470], [2.4, 500], [4.4, 650], [6.2, 640], [7.4, 600], [8.23, 560]],
  roll: [[0, 3], [2.4, 2], [4.4, 0], [8.23, 0]],
  look: [[0, -0.9], [4.2, -0.9], [4.7, -0.5], [6.2, -0.5], [6.6, 0.6], [7.5, 0.6], [8.0, 0.0], [8.23, 0]],
  lid: [[0, 0.45], [6.3, 0.45], [6.8, 0.8], [7.4, 0.8], [7.9, 0.42], [8.23, 0.4]],
  sip: [[0, 0], [6.3, 0], [6.8, 1], [7.4, 1], [7.9, 0], [8.23, 0]],
  hr: [[0, -5], [4.5, -5], [5.0, -3], [6.0, -7], [7.2, -8], [8.1, 0], [8.23, 0]],
  smirk: [[0, 0.3], [6.8, 0.3], [8.2, 0.9]],
  blush: [[0, 0.1], [6, 0.2], [8.2, 0.7]],
  brow: [[0, 0.2], [6.5, 0.2], [7.6, 0.9], [8.23, 0.9]],
  hy: [[0, 0], [6.8, 0], [7.1, 3], [7.9, 0]]
}

const wig = (t0: number, t1: number, step: number, a: number, b: number): Keys => {
  const n = Math.floor((t1 - t0) / step + 1e-9)
  return Array.from({ length: n + 1 }, (_, i) => [t0 + i * step, i % 2 === 0 ? a : b] as [number, number])
}

// ───────────── reference takes (start, end, keys) — re-timed onto the real cuts ─────────────
const TAKES: { s: number; e: number; k: Shot }[] = [
  { s: 8.24, e: 9.24, k: { z: [[8.24, 2.05], [9.24, 2.35]], cx: [[8.24, 360], [9.24, 366]], cy: [[8.24, 520], [9.24, 515]], roll: [[8.24, -3], [9.24, -1]],
    wink: [[8.24, 0], [8.40, 0], [8.50, 1], [9.0, 1], [9.22, 0.4]], smirk: [[8.24, 0.7], [9.24, 0.9]], blush: [[8.24, 0.7]], lid: [[8.24, 0.4]],
    brow: [[8.24, 0.8], [9.24, 0.6]], hr: [[8.24, -3], [9.24, -5]] } },
  { s: 9.24, e: 10.24, k: { z: [[9.24, 1.9], [10.24, 2.15]], cx: [[9.24, 372], [10.24, 360]], cy: [[9.24, 535], [10.24, 525]], roll: [[9.24, 4], [10.24, 2]],
    grin: [[9.24, 0.2], [9.5, 1], [10.24, 1]], blush: [[9.24, 0.9]], lid: [[9.24, 0.3]], brow: [[9.24, 0.4]], hr: [[9.24, -4], [10.24, 2]] } },
  { s: 10.24, e: 11.24, k: { z: [[10.24, 2.2], [11.24, 2.4]], cx: [[10.24, 345], [11.24, 352]], cy: [[10.24, 520], [11.24, 510]], roll: [[10.24, -5], [11.24, -3]],
    smirk: [[10.24, 0.5], [10.5, 1.0], [11.24, 1.0]], lid: [[10.24, 0.5]], brow: [[10.24, 1.0]], look: [[10.24, -0.4], [11.24, 0.3]], hr: [[10.24, 5], [11.24, 3]], blush: [[10.24, 0.8]] } },
  { s: 11.24, e: 12.44, k: { z: [[11.24, 2.7], [12.44, 3.0]], cx: [[11.24, 360]], cy: [[11.24, 478], [12.44, 470]], roll: [[11.24, 2], [12.44, -1]],
    lid: [[11.24, 0.6], [11.8, 0.55], [12.44, 0.35]], look: [[11.24, -1], [11.6, -1], [11.95, 1], [12.2, 1], [12.44, 0]],
    brow: [[11.24, 0.2], [11.8, 1], [12.2, 0.2], [12.44, 0.9]], browl: [[11.24, 0], [11.8, 0], [12.2, 1], [12.44, 0]],
    blink: [[11.24, 0], [11.9, 0], [11.97, 1], [12.1, 0]], smirk: [[11.24, 0.7]], hr: [[11.24, -3], [12.44, 3]], blush: [[11.24, 0.9]] } },
  { s: 12.44, e: 13.44, k: { z: [[12.44, 1.65], [13.44, 1.95]], cx: [[12.44, 385], [13.44, 372]], cy: [[12.44, 570], [13.44, 550]], roll: [[12.44, -4], [13.44, 0]],
    wink: [[12.44, 0], [12.62, 0], [12.72, 1], [13.2, 1], [13.44, 0.3]], smirk: [[12.44, 0.9]], grin: [[12.44, 0], [12.7, 0.7], [13.44, 0.7]],
    blush: [[12.44, 0.8]], hr: [[12.44, 4], [13.44, -2]], brow: [[12.44, 0.9]] } },
  { s: 13.44, e: 14.54, k: { z: [[13.44, 2.4], [14.54, 2.6]], cx: [[13.44, 360]], cy: [[13.44, 495], [14.54, 490]], roll: [[13.44, 3], [14.54, -2]],
    lid: [[13.44, 0.45]], brow: wig(13.44, 14.54, 0.16, 1.0, 0.1), browl: wig(13.44, 14.54, 0.16, 0.1, 1.0), grin: [[13.44, 0.5]],
    hr: [[13.44, -4], [14.54, 4]], look: [[13.44, 0.5], [14.54, -0.5]], blush: [[13.44, 0.9]] } },
  { s: 14.54, e: 15.64, k: { z: [[14.54, 2.0], [15.64, 2.3]], cx: [[14.54, 350], [15.64, 358]], cy: [[14.54, 540], [15.64, 530]], roll: [[14.54, 5], [15.64, 2]],
    grin: [[14.54, 0.3], [14.8, 1], [15.64, 1]], blush: [[14.54, 1.0]], lid: [[14.54, 0.3]], brow: [[14.54, 0.5]], hr: [[14.54, 3], [15.64, -3]],
    ear: [[14.54, 0], [14.7, 1], [14.85, 0], [15.1, 1], [15.25, 0]] } },
  // the last take: flirty smirk (+ a late wink)
  { s: 15.64, e: 18.0, k: { z: [[15.64, 1.95], [18.0, 2.5]], cx: [[15.64, 360]], cy: [[15.64, 535], [18.0, 520]], roll: [[15.64, -3], [18.0, 0]],
    smirk: [[15.64, 0.6], [16.0, 1.0], [18, 1.0]], lid: [[15.64, 0.45], [18, 0.4]], brow: [[15.64, 0.6], [16.5, 1], [18, 1]],
    wink: [[15.64, 0], [16.85, 0], [16.95, 1], [17.3, 1], [17.4, 0]], hr: [[15.64, 2], [18.0, -2]], blush: [[15.64, 0.6], [17, 1.0]] } }
]
const FINAL = TAKES.length - 1
// Extra takes for longer videos: re-use middle takes in an order that never repeats as a cycle.
const EXTRA_ORDER = [2, 5, 1, 4, 6, 3, 5, 2, 6, 1, 3, 4]

/** Which reference take plays in each of the video's takes (index 0 = the punch take, last = final smirk). */
export function takePlan(nTakes: number): number[] {
  if (nTakes <= 0) return []
  if (nTakes === 1) return [FINAL]
  const middle = TAKES.length - 2 // takes 1..6
  const out = [0]
  for (let i = 1; i < nTakes - 1; i++) out.push(i <= middle ? i : EXTRA_ORDER[(i - middle - 1) % EXTRA_ORDER.length])
  out.push(FINAL)
  return out
}

function remap(keys: Keys, f: (t: number) => number): Keys {
  return keys.map(([t, v]) => [f(t), v])
}

function shotFns(shot: Shot): Record<string, (t: number) => number> {
  const out: Record<string, (t: number) => number> = {}
  for (const [k, pts] of Object.entries(shot)) {
    const xs = pts.map((p) => p[0])
    const ys = pts.map((p) => p[1])
    out[k] = pts.length === 1 ? () => ys[0] : pchip(xs, ys)
  }
  return out
}

export function makeDirector(tl: DirectorTimeline) {
  const P = tl.punch_time
  const Dur = tl.duration
  const pauseStart = Math.max(0.5, P - tl.pause_before_punch)
  // Opening time-warp: reference talk part 0–6.24 → 0–pauseStart, reference pause 6.24–8.24 → pauseStart–P.
  const warp = (t: number) =>
    t <= REF_PAUSE_START ? (t * pauseStart) / REF_PAUSE_START : pauseStart + ((t - REF_PAUSE_START) * (P - pauseStart)) / (REF_P - REF_PAUSE_START)
  const opening = shotFns(Object.fromEntries(Object.entries(OPEN).map(([k, v]) => [k, remap(v, (t) => Math.min(warp(t), P - 0.01))])))

  const starts = [P, ...tl.cuts.filter((c) => c > P + 0.05 && c < Dur)]
  const plan = takePlan(starts.length)
  const takes = starts.map((s, i) => {
    const e = i + 1 < starts.length ? starts[i + 1] : Dur
    const ref = TAKES[plan[i]]
    const scale = (t: number) => s + ((t - ref.s) * (e - s)) / (ref.e - ref.s)
    return { s, e, ref: plan[i], fns: shotFns(Object.fromEntries(Object.entries(ref.k).map(([k, v]) => [k, remap(v, scale)]))) }
  })
  const cutFrames = starts.map((c) => Math.round(c * FPS))
  const heartsFrom = Dur - 1.9 // reference: hearts from 16.1 s of an 18 s video

  function takeAt(t: number): number {
    let k = -1
    for (let i = 0; i < takes.length; i++) if (t >= takes[i].s - 1e-9) k = i
    return k
  }

  function state(f: number, talk: number, wide: number): FrameState {
    const t = f / FPS
    const k = takeAt(t)
    const fns = k < 0 ? opening : takes[k].fns
    const P_: Record<string, number> = { ...D }
    for (const [key, fn] of Object.entries(fns)) P_[key] = fn(t)
    // natural blink unless the take controls it
    if (!('blink' in fns)) P_.blink = t % 3.3 < 0.11 && P_.wink < 0.5 ? 1 : 0
    P_.bob = Math.sin(t * 2.4) * 1.4
    // handheld camera; the shake jumps after each cut and decays
    const last = cutFrames.filter((c) => f >= c).pop()
    const amp = last !== undefined ? 3.0 + 11.0 * Math.exp(-((f - last) / FPS) * 9) : 1.4
    const dx = amp * (Math.sin(f * 1.9) + 0.6 * Math.sin(f * 4.3))
    const dy = amp * (Math.sin(f * 2.3 + 1) + 0.5 * Math.sin(f * 5.1))
    P_.cx += dx / P_.z
    P_.cy += dy / P_.z
    P_.roll += ((0.5 * amp) / 10) * Math.sin(f * 3.1)
    const fx = cutEffects(f, cutFrames)

    const pose: CatPose = {
      ...REST_POSE,
      t,
      lid: P_.lid, blink: P_.blink, winkR: P_.wink, winkL: 0, brow: P_.brow, browL: P_.browl,
      look: P_.look, lookV: P_.lookv, smirk: P_.smirk, grin: P_.grin, blush: P_.blush,
      headRoll: P_.hr, headBob: P_.hy * 1.2, bodyBob: P_.bob, sip: P_.sip, ear: P_.ear,
      open: talk, wide, tail: Math.sin(t * 2.2), hearts: hearts(t - heartsFrom)
    }
    return {
      cam: { zoom: P_.z, fx: P_.cx, fy: P_.cy, roll: P_.roll },
      pose,
      fade: t < 0.9 ? Math.pow(Math.min(1, Math.max(0, t / 0.9)), 1.5) : 1,
      flash: fx.flash,
      blur: fx.blur,
      takeIndex: k
    }
  }

  return { state, takeAt, cutFrames, takes: takes.map((t) => ({ start: t.s, end: t.e, ref: t.ref })), heartsFrom }
}

/** Hearts rising at the end (reference positions converted to the 720×1280 design space). */
function hearts(u0: number): CatPose['hearts'] {
  if (u0 <= 0) return []
  const out: CatPose['hearts'] = []
  const SRC: [number, number, number][] = [[130, -520, 3.0], [-150, -470, 2.4], [170, -400, 2.0], [-110, -600, 1.8], [20, -640, 2.2]]
  SRC.forEach(([hx, hy, s0], n) => {
    const u = u0 - n * 0.12
    if (u <= 0) return
    out.push({
      x: 360 + (hx + Math.sin(u * 5 + n) * 10) * 1.2,
      y: 1092 + (hy - u * 70) * 1.2,
      s: s0 * 0.74 * Math.min(1, u * 4),
      a: 1
    })
  })
  return out
}

/** Reference cut effects: blur {-1:3, 0:7, 1:11, 2:7, 3:3.5, 4:1.5} and flash {0:.9, 1:.5, 2:.2} around each cut frame. */
export function cutEffects(frame: number, cutFrames: number[]): { flash: number; blur: number } {
  const BL: Record<number, number> = { [-1]: 3.0, 0: 7.0, 1: 11.0, 2: 7.0, 3: 3.5, 4: 1.5 }
  const FL: Record<number, number> = { 0: 0.9, 1: 0.5, 2: 0.2 }
  let flash = 0
  let blur = 0
  for (const c of cutFrames) {
    const r = frame - c
    if (r in BL) blur = Math.max(blur, BL[r])
    if (r in FL) flash = Math.max(flash, FL[r])
  }
  return { flash, blur }
}
