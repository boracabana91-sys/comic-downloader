// The "director": a shot list timed to the audio, matching the reference video's rhythm —
// one continuous push-in until the punch line, then a hard cut every 1 s (flash + blur + shake)
// to close-ups with different expressions. Camera keys are interpolated with PCHIP.
import { pchip } from './pchip'
import { REST_POSE, type CatPose } from './cat'

export interface Camera { zoom: number; fx: number; fy: number; roll: number }
export interface FrameState {
  cam: Camera
  pose: CatPose
  /** Screen-space shake in output pixels (at 1080 wide) and degrees. */
  shake: { x: number; y: number; rot: number }
  takeIndex: number
}

export interface DirectorInput {
  durationSec: number
  punchSec: number
  /** Timeline phrases (seconds), to look away during the pause and back at the punch line. */
  phrases: { start: number; end: number }[]
  takeSec?: number
}

type Expr = Partial<Omit<CatPose, 'hearts' | 't'>> & { winkLAt?: [number, number]; winkRAt?: [number, number]; heartsAt?: number }

interface Template {
  zoom: [number, number]
  fx: number
  fy: number
  roll: [number, number]
  expr: Expr
}

// Post-punch takes, cycled. Mirrors the reference: wink + laugh, brow over the shades, eye close-up,
// a toast with the glass, the other wink + hearts.
const TAKES: Template[] = [
  { zoom: [2.55, 2.75], fx: 362, fy: 492, roll: [4, 5.5], expr: { grin: 0.95, blush: 1, lid: 0.25, winkRAt: [0.08, 0.8], heartsAt: 0.05 } },
  { zoom: [2.3, 2.45], fx: 346, fy: 480, roll: [-4.5, -6], expr: { brow: 1, lid: 0.12, look: 0.55, smirk: 1, grin: 0.3, blush: 0.6 } },
  { zoom: [3.3, 3.5], fx: 362, fy: 476, roll: [1.5, 0.5], expr: { lid: 0.5, look: -0.5, grin: 0.55, blush: 0.8 } },
  { zoom: [1.75, 1.92], fx: 430, fy: 560, roll: [-2, -3.5], expr: { glass: 1, grin: 0.85, blush: 0.8, lid: 0.25, heartsAt: 0.2 } },
  { zoom: [2.6, 2.8], fx: 362, fy: 494, roll: [6, 7], expr: { grin: 1, blush: 1, lid: 0.2, winkLAt: [0.1, 0.85], heartsAt: 0.1 } }
]

export function cutTimes(punchSec: number, durationSec: number, takeSec = 1.0): number[] {
  const cuts: number[] = []
  for (let c = punchSec; c < durationSec - 0.45; c += takeSec) cuts.push(c)
  return cuts
}

const smooth = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x))
function ramp(t: number, a: number, b: number, edge = 0.1) {
  return smooth((t - a) / edge) * (1 - smooth((t - b) / edge))
}

export function makeDirector(inp: DirectorInput) {
  const P = inp.punchSec
  const D = inp.durationSec
  const cuts = cutTimes(P, D, inp.takeSec ?? 1)

  // Continuous opening shot: wide → slow push-in to the face, small rolls.
  const ks = P > 1.6 ? [0, P * 0.45, P * 0.8, P - 0.02] : [0, Math.max(0.01, P - 0.02)]
  const kz = P > 1.6 ? [1.0, 1.22, 1.5, 1.85] : [1.2, 1.7]
  const kfx = P > 1.6 ? [360, 360, 362, 362] : [360, 362]
  const kfy = P > 1.6 ? [700, 660, 600, 560] : [640, 570]
  const kr = P > 1.6 ? [0, -1.2, 0.8, 1.5] : [0, 1]
  const open = { z: pchip(ks, kz), fx: pchip(ks, kfx), fy: pchip(ks, kfy), roll: pchip(ks, kr) }

  // Look away during the pause before the punch line, back to camera right before it lands.
  const before = inp.phrases.filter((p) => p.end <= P + 0.01)
  const pauseStart = before.length ? before[before.length - 1].end : Math.max(0, P - 2)
  const lookKeysT = [0, pauseStart, pauseStart + 0.4, Math.max(pauseStart + 0.45, P - 0.35), P - 0.08, P]
  const lookKeysV = [0, 0, 0.7, 0.7, 0, 0]
  const lookFn = pchip(lookKeysT, lookKeysV)

  // Takes after the punch line.
  const takes = cuts.map((c, i) => {
    const tpl = TAKES[i === 0 ? 0 : 1 + ((i - 1) % (TAKES.length - 1))]
    const end = i + 1 < cuts.length ? cuts[i + 1] : D
    const mid = (c + end) / 2
    return {
      start: c, end, tpl,
      z: pchip([c, mid, end], [tpl.zoom[0], (tpl.zoom[0] * 0.45 + tpl.zoom[1] * 0.55), tpl.zoom[1]]),
      r: pchip([c, mid, end], [tpl.roll[0], (tpl.roll[0] * 0.45 + tpl.roll[1] * 0.55), tpl.roll[1]]),
      fx: pchip([c, mid, end], [tpl.fx, tpl.fx + 4, tpl.fx + 6])
    }
  })

  const blinkTimes: number[] = []
  for (let b = 1.3; b < P - 0.4; b += 2.7) blinkTimes.push(b)

  const burstTimes = takes.filter((k) => k.tpl.expr.heartsAt !== undefined).map((k) => k.start + (k.tpl.expr.heartsAt as number))

  /** Which take a time belongs to (−1 = opening shot). Motion-blur subsamples never cross a cut. */
  function takeAt(t: number): number {
    let k = -1
    for (let i = 0; i < takes.length; i++) if (t >= takes[i].start) k = i
    return k
  }

  function state(t: number, mouth: { open: number; wide: number }): FrameState {
    const k = takeAt(t)
    const pose: CatPose = { ...REST_POSE, t, hearts: [] }
    let cam: Camera
    if (k < 0) {
      cam = { zoom: open.z(t), fx: open.fx(t), fy: open.fy(t), roll: open.roll(t) }
      pose.look = lookFn(t)
      pose.smirk = 0.6 + 0.4 * smooth((t - pauseStart) / Math.max(0.2, P - pauseStart))
      pose.glass = 0.15 + 0.15 * Math.sin(t * 1.3)
      for (const b of blinkTimes) pose.lid = Math.max(pose.lid, ramp(t, b, b + 0.1, 0.05))
    } else {
      const tk = takes[k]
      const u = t - tk.start
      cam = { zoom: tk.z(t), fx: tk.fx(t), fy: tk.tpl.fy, roll: tk.r(t) }
      const e = tk.tpl.expr
      Object.assign(pose, Object.fromEntries(Object.entries(e).filter(([key]) => !key.endsWith('At'))))
      if (e.winkLAt) pose.winkL = ramp(u, e.winkLAt[0], e.winkLAt[1], 0.08)
      if (e.winkRAt) pose.winkR = ramp(u, e.winkRAt[0], e.winkRAt[1], 0.08)
      pose.headRoll = 2.5 * Math.sin(u * 3.1 + k)
      pose.headBob = -6 * Math.sin(Math.min(1, u / 0.25) * Math.PI)
    }
    // Lip-sync on top of the expression.
    pose.open = mouth.open
    pose.wide = mouth.wide
    pose.tail = Math.sin(t * 1.7)
    pose.ear = ramp(t % 4.3, 2.0, 2.15, 0.05)
    // Hearts float up from bursts.
    for (const b of burstTimes) {
      const age = t - b
      if (age < 0 || age > 1.6) continue
      for (let i = 0; i < 6; i++) {
        const side = i % 2 === 0 ? -1 : 1
        pose.hearts.push({
          x: 362 + side * (120 + i * 14) + Math.sin(age * 5 + i) * 10,
          y: 470 - 190 * age - i * 12,
          s: (0.9 + 0.25 * Math.sin(i * 1.7)) * (0.6 + 0.4 * Math.min(1, age / 0.2)),
          a: 1 - age / 1.6
        })
      }
    }
    // Handheld camera, always moving a little; plus a decaying shake after each cut.
    cam.fx += 3 * Math.sin(1.3 * t) + 2 * Math.sin(2.9 * t + 1)
    cam.fy += 3 * Math.sin(1.1 * t + 2) + 2 * Math.sin(3.7 * t)
    cam.roll += 0.4 * Math.sin(0.9 * t)
    const shake = { x: 0, y: 0, rot: 0 }
    if (k >= 0) {
      const u = t - takes[k].start
      const a = Math.exp(-u / 0.18)
      shake.x = 16 * a * Math.sin(2 * Math.PI * 8 * u)
      shake.y = 11 * a * Math.cos(2 * Math.PI * 7 * u)
      shake.rot = 1.4 * a * Math.sin(2 * Math.PI * 6 * u)
    }
    return { cam, pose, shake, takeIndex: k }
  }

  return { state, cuts, takeAt, takes: takes.map((t) => ({ start: t.start, end: t.end })) }
}

/** Brief: 3-frame white flash after each cut; blur radius 3, 7, 11, 7, 3.5, 1.5 on frames −3…+2. */
export function cutEffects(frame: number, cutFrames: number[]): { flash: number; blur: number } {
  let flash = 0
  let blur = 0
  const BLUR: Record<number, number> = { [-3]: 3, [-2]: 7, [-1]: 11, 0: 7, 1: 3.5, 2: 1.5 }
  const FLASH: Record<number, number> = { 0: 0.85, 1: 0.5, 2: 0.2 }
  for (const c of cutFrames) {
    const d = frame - c
    if (d in BLUR) blur = Math.max(blur, BLUR[d])
    if (d in FLASH) flash = Math.max(flash, FLASH[d])
  }
  return { flash, blur }
}
