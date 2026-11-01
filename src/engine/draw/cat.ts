// The Casanova cat in the limo, drawn in code from the owner's reference picture.
// Design space is 720×1280 (the reference size). Every moving part is a pose parameter.
import type { SKRSContext2D } from '@napi-rs/canvas'

type Ctx = SKRSContext2D

export interface CatPose {
  lid: number // 0 = eyes wide open, 1 = closed (resting look ≈ 0.42, the smug half-lid)
  winkL: number // screen-left eye closed in a happy "^" (0..1)
  winkR: number
  brow: number // 0..1 right eyebrow raised (reference "brow")
  browL: number // 0..1 left eyebrow raised (reference "browl")
  blink: number // 0..1 both eyes closing
  look: number // -1..1 pupils left/right
  lookV: number // -1..1 pupils up/down
  smirk: number // 0..1 lifts ONLY the right mouth corner (the only allowed asymmetry)
  grin: number // 0..1 big open smile
  open: number // 0..1 mouth open from the voice
  wide: number // 0..1 mouth width from the voice
  blush: number // 0..1
  headRoll: number // degrees
  headBob: number // design px
  glass: number // 0..1 raise the champagne (toast)
  sip: number // 0..1 bring the champagne to the mouth
  bodyBob: number // design px (breathing)
  tail: number // -1..1 sway
  ear: number // 0..1 ear twitch
  hearts: { x: number; y: number; s: number; a: number }[]
  t: number // seconds (bubbles, twinkles)
}

export const REST_POSE: CatPose = {
  lid: 0.42, winkL: 0, winkR: 0, brow: 0.3, browL: 0, blink: 0, look: 0, lookV: 0, smirk: 0.7, grin: 0, open: 0, wide: 0.5,
  blush: 0.35, headRoll: 0, headBob: 0, glass: 0, sip: 0, bodyBob: 0, tail: 0, ear: 0, hearts: [], t: 0
}

const C = {
  ink: '#121016',
  fur: '#ea8a2e',
  furDark: '#c4601c',
  furLight: '#f6ad5f',
  cream: '#fde3bb',
  pinkEar: '#f2a0b0',
  nose: '#f193a6',
  blush: '242,120,135',
  eyeWhite: '#f6f1d2',
  iris: '#5fbf47',
  irisDark: '#2f8a2c',
  suit: '#1e1d26',
  suitLight: '#35333f',
  pants: '#24232d',
  gold: '#e1b13c',
  goldDark: '#a77c1d',
  pocket: '#f3a5c0',
  mouth: '#4a0d1a',
  tongue: '#e8687e'
}

function outline(ctx: Ctx, w = 5) {
  ctx.lineWidth = w
  ctx.strokeStyle = C.ink
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.stroke()
}

function fillOut(ctx: Ctx, fill: string, w = 5) {
  ctx.fillStyle = fill
  ctx.fill()
  outline(ctx, w)
}

function ellipse(ctx: Ctx, x: number, y: number, rx: number, ry: number, rot = 0) {
  ctx.beginPath()
  ctx.ellipse(x, y, rx, ry, rot, 0, Math.PI * 2)
}

/** Seeded random so the background is identical every frame. */
function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 4294967296
  }
}

// ───────────────────────── background (limo interior) ─────────────────────────

/** Static set, drawn wide enough (x −1000…1720) for 16:9 framing too. */
export function drawLimo(ctx: Ctx): void {
  // Walls
  const wall = ctx.createLinearGradient(0, 0, 0, 1280)
  wall.addColorStop(0, '#140f1e')
  wall.addColorStop(0.5, '#22152a')
  wall.addColorStop(1, '#170f1d')
  ctx.fillStyle = wall
  ctx.fillRect(-1000, -300, 2720, 1900)
  ctx.strokeStyle = 'rgba(255,255,255,0.04)'
  ctx.lineWidth = 3
  for (let x = -1000; x < 1720; x += 60) {
    ctx.beginPath(); ctx.moveTo(x, 160); ctx.lineTo(x, 700); ctx.stroke()
  }
  // Sunroof strip with stars
  ctx.fillStyle = '#0d0a18'
  ctx.fillRect(-1000, -300, 2720, 455)
  const r = rng(7)
  for (let i = 0; i < 260; i++) {
    const x = -1000 + r() * 2720
    const y = -280 + r() * 420
    ctx.fillStyle = `rgba(255,255,255,${0.35 + r() * 0.6})`
    ctx.beginPath(); ctx.arc(x, y, 0.8 + r() * 1.8, 0, Math.PI * 2); ctx.fill()
  }
  // Neon line
  ctx.strokeStyle = '#ff3d7f'
  ctx.lineWidth = 4
  ctx.shadowColor = '#ff3d7f'
  ctx.shadowBlur = 18
  ctx.beginPath(); ctx.moveTo(-1000, 165); ctx.lineTo(1720, 165); ctx.stroke()
  ctx.shadowBlur = 0

  // Window: neon frame + city at dusk
  const wx = 75, wy = 178, ww = 570, wh = 510, rad = 46
  ctx.save()
  ctx.beginPath(); ctx.roundRect(wx, wy, ww, wh, rad); ctx.clip()
  const sky = ctx.createLinearGradient(0, wy, 0, wy + wh)
  sky.addColorStop(0, '#2d1650')
  sky.addColorStop(0.45, '#6c2a7c')
  sky.addColorStop(0.8, '#c4507f')
  sky.addColorStop(1, '#f08a6a')
  ctx.fillStyle = sky
  ctx.fillRect(wx, wy, ww, wh)
  const rb = rng(11)
  const bokehCols = ['255,140,170', '170,120,255', '255,190,120', '120,170,255', '255,110,140']
  for (let i = 0; i < 26; i++) {
    const col = bokehCols[Math.floor(rb() * bokehCols.length)]
    ctx.fillStyle = `rgba(${col},${0.18 + rb() * 0.25})`
    ctx.beginPath(); ctx.arc(wx + rb() * ww, wy + rb() * wh * 0.9, 12 + rb() * 34, 0, Math.PI * 2); ctx.fill()
  }
  const rc = rng(23)
  let x = wx - 10
  while (x < wx + ww) {
    const bw = 34 + rc() * 50
    const bh = 90 + rc() * 190
    const top = wy + wh - bh
    ctx.fillStyle = rc() > 0.5 ? '#251a42' : '#2e2150'
    ctx.fillRect(x, top, bw, bh)
    for (let yy = top + 10; yy < wy + wh - 8; yy += 14) {
      for (let xx = x + 6; xx < x + bw - 6; xx += 11) {
        if (rc() > 0.55) {
          ctx.fillStyle = rc() > 0.75 ? 'rgba(255,140,190,0.9)' : 'rgba(255,214,120,0.9)'
          ctx.fillRect(xx, yy, 5, 6)
        }
      }
    }
    x += bw + 3
  }
  ctx.restore()
  ctx.lineWidth = 10
  ctx.strokeStyle = '#1b1426'
  ctx.beginPath(); ctx.roundRect(wx, wy, ww, wh, rad); ctx.stroke()
  ctx.shadowBlur = 16
  ctx.shadowColor = '#b05cff'
  ctx.lineWidth = 5
  ctx.strokeStyle = '#a45cf0'
  ctx.beginPath(); ctx.roundRect(wx - 12, wy - 12, ww + 24, wh + 24, rad + 10); ctx.stroke()
  ctx.shadowColor = '#ff3d7f'
  ctx.strokeStyle = '#ff4f8b'
  ctx.lineWidth = 3
  ctx.beginPath(); ctx.roundRect(wx - 4, wy - 4, ww + 8, wh + 8, rad + 3); ctx.stroke()
  ctx.shadowBlur = 0

  // Quilted seat back
  const sx = -1000, sw = 2720
  ctx.fillStyle = '#741427'
  ctx.beginPath(); ctx.roundRect(28, 690, 664, 290, 30); ctx.fill()
  ctx.fillRect(sx, 700, 28 - sx, 280)
  ctx.fillRect(692, 700, 1720 - 692, 280)
  const seatShade = ctx.createLinearGradient(0, 690, 0, 980)
  seatShade.addColorStop(0, 'rgba(255,255,255,0.06)')
  seatShade.addColorStop(1, 'rgba(0,0,0,0.25)')
  ctx.fillStyle = seatShade
  ctx.fillRect(sx, 690, sw, 290)
  ctx.strokeStyle = '#4f0b19'
  ctx.lineWidth = 3
  for (let d = -1400; d < 1800; d += 70) {
    ctx.beginPath(); ctx.moveTo(d, 700); ctx.lineTo(d + 280, 980); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(d + 280, 700); ctx.lineTo(d, 980); ctx.stroke()
  }
  ctx.fillStyle = C.gold
  for (let d = -1400; d < 1800; d += 70) {
    for (let k = 0; k < 4; k++) {
      const yy = 700 + 70 * k
      const xx = d + 70 * k
      ctx.beginPath(); ctx.arc(xx, yy, 4.5, 0, Math.PI * 2); ctx.fill()
      ctx.beginPath(); ctx.arc(xx + 35, yy + 35, 4.5, 0, Math.PI * 2); ctx.fill()
    }
  }
  ctx.strokeStyle = C.ink
  ctx.lineWidth = 5
  ctx.beginPath(); ctx.roundRect(28, 690, 664, 290, 30); ctx.stroke()

  // Cushion and front panel
  ctx.fillStyle = '#8b1a2f'
  ctx.beginPath(); ctx.moveTo(sx, 975); ctx.lineTo(1720, 975); ctx.lineTo(1720, 1045); ctx.lineTo(sx, 1045); ctx.fill()
  ctx.fillStyle = '#6a1222'
  ctx.fillRect(sx, 1045, sw, 70)
  ctx.strokeStyle = '#4f0b19'
  ctx.lineWidth = 3
  for (let xx = sx; xx < 1720; xx += 26) {
    ctx.beginPath(); ctx.moveTo(xx, 1050); ctx.lineTo(xx, 1110); ctx.stroke()
  }
  ctx.strokeStyle = C.ink
  ctx.lineWidth = 5
  ctx.beginPath(); ctx.moveTo(sx, 1045); ctx.lineTo(1720, 1045); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(sx, 975); ctx.lineTo(1720, 975); ctx.stroke()

  // Floor planks
  const fl = ctx.createLinearGradient(0, 1110, 0, 1500)
  fl.addColorStop(0, '#2a1d3c')
  fl.addColorStop(1, '#170f22')
  ctx.fillStyle = fl
  ctx.fillRect(sx, 1110, sw, 500)
  ctx.strokeStyle = 'rgba(120,90,170,0.35)'
  ctx.lineWidth = 3
  for (let k = -30; k <= 30; k++) {
    ctx.beginPath(); ctx.moveTo(360 + k * 40, 1112); ctx.lineTo(360 + k * 120, 1600); ctx.stroke()
  }
}

/** Champagne bucket in the corner (foreground). */
export function drawBucket(ctx: Ctx): void {
  ctx.beginPath()
  ctx.moveTo(612, 1010); ctx.lineTo(612, 1100); ctx.lineTo(600, 1112); ctx.lineTo(600, 1160); ctx.lineTo(650, 1160); ctx.lineTo(650, 1112); ctx.lineTo(638, 1100); ctx.lineTo(638, 1010); ctx.closePath()
  fillOut(ctx, '#1f5a2a', 4)
  ctx.fillStyle = C.gold
  ctx.fillRect(613, 1008, 24, 22)
  ctx.fillStyle = '#e9e0c8'
  ctx.fillRect(606, 1120, 38, 26)
  ctx.beginPath()
  ctx.moveTo(560, 1150); ctx.lineTo(685, 1150); ctx.lineTo(672, 1270); ctx.lineTo(573, 1270); ctx.closePath()
  const g = ctx.createLinearGradient(560, 0, 685, 0)
  g.addColorStop(0, '#8e93a0'); g.addColorStop(0.4, '#e7ebf2'); g.addColorStop(1, '#9da2ae')
  ctx.fillStyle = g
  ctx.fill(); outline(ctx, 4)
  for (const [x, y] of [[575, 1150], [600, 1142], [628, 1148], [655, 1140], [675, 1150]]) {
    ctx.beginPath(); ctx.moveTo(x - 13, y); ctx.lineTo(x, y - 12); ctx.lineTo(x + 13, y); ctx.lineTo(x, y + 9); ctx.closePath()
    ctx.fillStyle = '#cfe8f5'; ctx.fill(); outline(ctx, 2.5)
  }
  ctx.strokeStyle = '#6d7280'; ctx.lineWidth = 3
  for (const y of [1190, 1235]) { ctx.beginPath(); ctx.moveTo(566, y); ctx.lineTo(679, y); ctx.stroke() }
}

// ───────────────────────── character ─────────────────────────

function drawTail(ctx: Ctx, p: CatPose) {
  const sway = p.tail * 28
  ctx.beginPath()
  ctx.moveTo(455, 935)
  ctx.bezierCurveTo(600, 975, 700 + sway * 0.5, 905, 642 + sway, 822)
  ctx.lineWidth = 42; ctx.strokeStyle = C.ink; ctx.lineCap = 'round'; ctx.stroke()
  ctx.lineWidth = 32; ctx.strokeStyle = C.fur; ctx.stroke()
  ctx.strokeStyle = C.furDark; ctx.lineWidth = 6
  for (const k of [0.35, 0.5, 0.65, 0.8]) {
    const x = bez(455, 600, 700 + sway * 0.5, 642 + sway, k)
    const y = bez(935, 975, 905, 822, k)
    ctx.beginPath(); ctx.moveTo(x - 10, y - 8); ctx.lineTo(x + 10, y + 8); ctx.stroke()
  }
  ellipse(ctx, 642 + sway, 818, 18, 16)
  fillOut(ctx, C.cream, 5)
}

function bez(a: number, b: number, c: number, d: number, t: number) {
  const u = 1 - t
  return u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d
}

function limb(ctx: Ctx, pts: [number, number][], width: number, color: string) {
  ctx.beginPath()
  ctx.moveTo(pts[0][0], pts[0][1])
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1])
  ctx.lineCap = 'round'; ctx.lineJoin = 'round'
  ctx.lineWidth = width + 10; ctx.strokeStyle = C.ink; ctx.stroke()
  ctx.lineWidth = width; ctx.strokeStyle = color; ctx.stroke()
}

function drawLegs(ctx: Ctx) {
  limb(ctx, [[285, 935], [238, 1005], [245, 1078]], 64, C.pants)
  limb(ctx, [[440, 935], [482, 1005], [475, 1078]], 64, C.pants)
  ctx.strokeStyle = 'rgba(255,255,255,0.12)'; ctx.lineWidth = 3
  for (const [x1, y1, x2, y2] of [[225, 985, 255, 1010], [470, 985, 500, 1012], [255, 1030, 262, 1065], [462, 1030, 455, 1065]]) {
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
  }
  for (const [x, flip] of [[238, -1], [482, 1]] as const) {
    ctx.fillStyle = 'rgba(0,0,0,0.45)'
    ellipse(ctx, x + flip * 10, 1122, 70, 12); ctx.fill()
    ctx.fillStyle = '#f07aa6'; ctx.fillRect(x - 24, 1074, 48, 12)
    ctx.beginPath()
    ctx.moveTo(x - 30, 1084); ctx.lineTo(x + 30, 1084)
    ctx.quadraticCurveTo(x + flip * 70, 1092, x + flip * 72, 1110)
    ctx.lineTo(x - flip * 36, 1112)
    ctx.quadraticCurveTo(x - flip * 40, 1094, x - 30, 1084)
    fillOut(ctx, '#0f0e14', 4)
    ctx.strokeStyle = 'rgba(255,255,255,0.7)'; ctx.lineWidth = 3
    ctx.beginPath(); ctx.moveTo(x + flip * 18, 1092); ctx.lineTo(x + flip * 44, 1096); ctx.stroke()
  }
}

function drawTorso(ctx: Ctx) {
  ctx.beginPath()
  ctx.moveTo(232, 700); ctx.lineTo(492, 700); ctx.lineTo(478, 940); ctx.lineTo(246, 940); ctx.closePath()
  fillOut(ctx, C.suit)
  // shirt
  ctx.beginPath(); ctx.moveTo(318, 690); ctx.lineTo(406, 690); ctx.lineTo(362, 845); ctx.closePath()
  ctx.fillStyle = '#f4f2ee'; ctx.fill()
  // lapels
  ctx.beginPath(); ctx.moveTo(300, 692); ctx.lineTo(332, 692); ctx.lineTo(352, 850); ctx.lineTo(268, 770); ctx.closePath()
  fillOut(ctx, C.suitLight, 4)
  ctx.beginPath(); ctx.moveTo(424, 692); ctx.lineTo(392, 692); ctx.lineTo(372, 850); ctx.lineTo(456, 770); ctx.closePath()
  fillOut(ctx, C.suitLight, 4)
  ctx.strokeStyle = 'rgba(160,160,200,0.5)'; ctx.lineWidth = 3
  ctx.beginPath(); ctx.moveTo(262, 715); ctx.lineTo(276, 840); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(258, 880); ctx.lineTo(352, 870); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(466, 880); ctx.lineTo(372, 870); ctx.stroke()
  // chain + medallion
  ctx.strokeStyle = C.gold; ctx.lineWidth = 4
  ctx.beginPath(); ctx.moveTo(332, 692); ctx.quadraticCurveTo(362, 770, 392, 692); ctx.stroke()
  ellipse(ctx, 362, 752, 13, 13); fillOut(ctx, C.gold, 3)
  ellipse(ctx, 362, 752, 6, 6); ctx.fillStyle = C.goldDark; ctx.fill()
  // bow tie
  ctx.beginPath(); ctx.moveTo(362, 708); ctx.lineTo(326, 692); ctx.lineTo(326, 724); ctx.closePath(); fillOut(ctx, '#0d0c11', 3)
  ctx.beginPath(); ctx.moveTo(362, 708); ctx.lineTo(398, 692); ctx.lineTo(398, 724); ctx.closePath(); fillOut(ctx, '#0d0c11', 3)
  ctx.strokeStyle = '#0d0c11'; ctx.lineWidth = 6
  ctx.beginPath(); ctx.moveTo(356, 714); ctx.lineTo(338, 772); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(368, 714); ctx.lineTo(388, 772); ctx.stroke()
  ellipse(ctx, 362, 708, 9, 8); fillOut(ctx, '#0d0c11', 3)
  // pocket square
  ctx.fillStyle = '#121118'; ctx.fillRect(408, 792, 42, 22)
  ctx.beginPath(); ctx.moveTo(414, 794); ctx.lineTo(426, 772); ctx.lineTo(438, 794); ctx.closePath(); ctx.fillStyle = C.pocket; ctx.fill()
  ctx.beginPath(); ctx.moveTo(430, 794); ctx.lineTo(440, 776); ctx.lineTo(448, 794); ctx.closePath(); ctx.fillStyle = '#ffffff'; ctx.fill()
  // buttons
  for (const x of [345, 380]) { ellipse(ctx, x, 892, 7, 7); fillOut(ctx, C.gold, 2) }
}

function paw(ctx: Ctx, x: number, y: number, r: number) {
  ellipse(ctx, x, y, r, r * 0.95)
  fillOut(ctx, C.cream, 5)
  ctx.save()
  ellipse(ctx, x, y, r, r * 0.95); ctx.clip()
  ctx.fillStyle = C.fur; ctx.fillRect(x - r, y - r, 2 * r, r * 0.8)
  ctx.restore()
  ellipse(ctx, x, y, r, r * 0.95); outline(ctx, 5)
  ctx.strokeStyle = C.ink; ctx.lineWidth = 4
  for (const dx of [-r * 0.35, 0, r * 0.35]) { ctx.beginPath(); ctx.moveTo(x + dx, y + r * 0.1); ctx.lineTo(x + dx, y + r * 0.6); ctx.stroke() }
}

function drawLeftArm(ctx: Ctx) {
  limb(ctx, [[262, 722], [180, 690], [112, 690]], 50, C.suit)
  ctx.fillStyle = C.gold; ctx.fillRect(104, 670, 12, 40)
  paw(ctx, 80, 700, 30)
}

function drawRightArm(ctx: Ctx, p: CatPose) {
  const lift = p.glass * 75
  const px = 528 - 14 * p.sip, py = 640 - lift - 18 * p.sip
  limb(ctx, [[468, 718], [565, 800 - lift * 0.4 - 10 * p.sip], [px + 8, py + 30]], 50, C.suit)
  ctx.fillStyle = C.gold; ctx.fillRect(px - 6, py + 14, 34, 12)
  // champagne flute (behind the paw); a sip tilts it 58° so the rim reaches the mouth
  const gx = px - 2, top = py - 205, bottom = py - 15
  ctx.save()
  ctx.translate(px + 10, py)
  ctx.rotate((-58 * p.sip * Math.PI) / 180)
  ctx.translate(-(px + 10), -py)
  ctx.save()
  ctx.beginPath()
  ctx.moveTo(gx - 20, top); ctx.lineTo(gx + 20, top); ctx.lineTo(gx + 8, bottom); ctx.lineTo(gx - 8, bottom); ctx.closePath()
  ctx.fillStyle = 'rgba(255,255,255,0.12)'; ctx.fill()
  ctx.clip()
  ctx.fillStyle = 'rgba(242,197,75,0.9)'
  ctx.fillRect(gx - 25, top + 75, 50, bottom - top)
  for (let i = 0; i < 6; i++) {
    const ph = (p.t * 0.8 + i / 6) % 1
    ctx.fillStyle = 'rgba(255,255,255,0.85)'
    ctx.beginPath(); ctx.arc(gx - 6 + ((i * 7) % 13), bottom - 10 - ph * (bottom - top - 85), 2.4, 0, Math.PI * 2); ctx.fill()
  }
  ctx.restore()
  ctx.strokeStyle = 'rgba(255,255,255,0.95)'; ctx.lineWidth = 3
  ctx.beginPath(); ctx.moveTo(gx - 20, top); ctx.lineTo(gx - 8, bottom); ctx.lineTo(gx + 8, bottom); ctx.lineTo(gx + 20, top); ctx.closePath(); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(gx, bottom); ctx.lineTo(gx, bottom + 30); ctx.stroke()
  ctx.restore()
  paw(ctx, px + 10, py + 2, 26)
  ellipse(ctx, px + 32, py - 14, 11, 11); fillOut(ctx, C.fur, 4)
}

function drawNeck(ctx: Ctx) {
  ctx.beginPath(); ctx.moveTo(326, 585); ctx.lineTo(398, 585); ctx.lineTo(404, 700); ctx.lineTo(320, 700); ctx.closePath()
  fillOut(ctx, C.fur)
  ctx.beginPath(); ctx.moveTo(342, 600); ctx.lineTo(382, 600); ctx.lineTo(386, 700); ctx.lineTo(338, 700); ctx.closePath()
  ctx.fillStyle = C.cream; ctx.fill()
  ellipse(ctx, 362, 650, 33, 9); ctx.fillStyle = 'rgba(214,110,40,0.9)'; ctx.fill()
}

function brows(ctx: Ctx, p: CatPose) {
  ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = C.furDark; ctx.lineWidth = 11
  // right brow (reference "brow"): arches up when raised
  const rx = 427, ry = 472, br = p.brow
  ctx.beginPath(); ctx.moveTo(rx - 34, ry - 70 + 9.6 * (1 - br)); ctx.lineTo(rx + 5, ry - 86 - 12 * br); ctx.lineTo(rx + 36, ry - 70 - 7 * br); ctx.stroke()
  // left brow (reference "browl"): a flatter slope that lifts when raised
  const lx = 297, ly = 472, bl = p.browL
  ctx.beginPath(); ctx.moveTo(lx - 36, ly - 53 - 10 * bl); ctx.lineTo(lx + 34, ly - 60 - 19 * bl); ctx.stroke()
}

function eye(ctx: Ctx, cx: number, cy: number, p: CatPose, wink: number, side: -1 | 1) {
  const w = 46, h = 30
  const cl = Math.max(p.blink, wink)
  if (cl > 0.88) {
    // closed eye: a happy "^" for a wink, a soft line for a blink
    ctx.beginPath()
    ctx.moveTo(cx - w * 0.9, cy + 6); ctx.quadraticCurveTo(cx, cy - (wink > p.blink ? 22 : 8) + 4 * (1 - cl), cx + w * 0.9, cy + 6)
    outline(ctx, 7)
    return
  }
  const lid = Math.min(1, p.lid + (1 - p.lid) * cl)
  const almond = () => {
    ctx.beginPath()
    ctx.moveTo(cx - w, cy)
    ctx.quadraticCurveTo(cx - w * 0.2, cy - h * 1.35, cx + w, cy - 2)
    ctx.quadraticCurveTo(cx + w * 0.2, cy + h * 1.25, cx - w, cy)
    ctx.closePath()
  }
  almond(); ctx.fillStyle = C.eyeWhite; ctx.fill()
  ctx.save(); almond(); ctx.clip()
  const ix = cx + 7 * (1 - Math.abs(p.look) * 0.3) * side * 0 + p.look * 13 + side * 2
  const iy = cy + 3 + p.lookV * 5
  ellipse(ctx, ix, iy, 20, 21); ctx.fillStyle = C.iris; ctx.fill()
  ellipse(ctx, ix, iy + 5, 20, 14); ctx.fillStyle = 'rgba(47,138,44,0.35)'; ctx.fill()
  ellipse(ctx, ix, iy, 5 + 2.4 * Math.max(0, p.lid - 0.4), 17); ctx.fillStyle = C.ink; ctx.fill()
  ellipse(ctx, ix + 7, iy - 10, 4.5, 4.5); ctx.fillStyle = '#ffffff'; ctx.fill()
  // upper lid
  const top = cy - h * 1.05
  const lidY = top + lid * (h * 2.1)
  ctx.fillStyle = C.fur
  ctx.fillRect(cx - w - 5, top - 30, 2 * w + 10, lidY - top + 30)
  ctx.restore()
  // lid line (thick, flat = smug) + lower line
  ctx.beginPath()
  ctx.moveTo(cx - w - 2, Math.max(cy - 2, lidY + 2) - (lidY > cy ? 0 : 0))
  ctx.quadraticCurveTo(cx, lidY - 6 + lid * 4, cx + w + 4, Math.min(lidY + 2, cy))
  outline(ctx, 8)
  ctx.beginPath()
  ctx.moveTo(cx - w, cy); ctx.quadraticCurveTo(cx + w * 0.2, cy + h * 1.25, cx + w, cy - 2)
  outline(ctx, 4)
}

function mouth(ctx: Ctx, p: CatPose) {
  const cx = 362
  const baseY = 556
  const talking = p.open > 0.08
  const lift = p.grin * 7
  const smirkLift = p.smirk * 16
  if (!talking && p.grin <= 0.5) {
    // closed "w" smile with the smirk on the right corner only
    ctx.beginPath()
    ctx.moveTo(cx - 52, baseY - 4 - lift)
    ctx.quadraticCurveTo(cx - 28, baseY + 16, cx, baseY - 4)
    ctx.quadraticCurveTo(cx + 28, baseY + 16, cx + 54, baseY - 6 - lift - smirkLift)
    outline(ctx, 5.5)
    fang(ctx, cx + 32, baseY + 8)
    return
  }
  const oo = Math.max(talking ? p.open : 0, p.grin * 0.35)
  const hw = 40 * (1 + 0.16 * p.grin) * (1 + 0.1 * (talking ? p.wide : 0))
  const h = 6 + 46 * oo + 12 * p.grin
  const lY = baseY - lift
  const rY = baseY - lift - smirkLift * 0.6
  const shape = () => {
    ctx.beginPath()
    ctx.moveTo(cx - hw, lY)
    ctx.quadraticCurveTo(cx, baseY - 6, cx + hw, rY)
    ctx.quadraticCurveTo(cx + hw * 0.7, baseY + h, cx, baseY + h)
    ctx.quadraticCurveTo(cx - hw * 0.7, baseY + h, cx - hw, lY)
    ctx.closePath()
  }
  shape(); ctx.fillStyle = C.mouth; ctx.fill()
  ctx.save(); shape(); ctx.clip()
  ellipse(ctx, cx, baseY + h + 4, hw * 0.65, h * 0.55); ctx.fillStyle = C.tongue; ctx.fill()
  if (p.grin > 0.4) { ctx.fillStyle = '#ffffff'; ctx.fillRect(cx - hw, baseY - 12, hw * 2, 9 + p.grin * 3) }
  ctx.restore()
  shape(); outline(ctx, 5.5)
  fang(ctx, cx + hw * 0.55, (baseY + rY) / 2 + 2)
}

function fang(ctx: Ctx, x: number, y: number) {
  ctx.beginPath(); ctx.moveTo(x - 5, y); ctx.lineTo(x + 5, y); ctx.lineTo(x + 1, y + 16); ctx.closePath()
  fillOut(ctx, '#ffffff', 2.5)
}

function drawHead(ctx: Ctx, p: CatPose) {
  // ears (behind head)
  const tw = p.ear * 10
  ctx.beginPath(); ctx.moveTo(214, 405); ctx.lineTo(206, 300); ctx.lineTo(292, 360); ctx.closePath(); fillOut(ctx, C.fur)
  ctx.beginPath(); ctx.moveTo(228, 388); ctx.lineTo(222, 322); ctx.lineTo(272, 362); ctx.closePath(); ctx.fillStyle = C.pinkEar; ctx.fill()
  ctx.beginPath(); ctx.moveTo(432, 360); ctx.lineTo(516 + tw, 300 - tw * 0.5); ctx.lineTo(510, 405); ctx.closePath(); fillOut(ctx, C.fur)
  ctx.beginPath(); ctx.moveTo(452, 362); ctx.lineTo(502 + tw, 322 - tw * 0.5); ctx.lineTo(496, 388); ctx.closePath(); ctx.fillStyle = C.pinkEar; ctx.fill()
  // cheek tufts
  ctx.beginPath(); ctx.moveTo(206, 462); ctx.lineTo(176, 478); ctx.lineTo(202, 488); ctx.lineTo(178, 508); ctx.lineTo(206, 512); ctx.closePath(); fillOut(ctx, C.fur, 4)
  // head
  ctx.beginPath()
  ctx.moveTo(225, 382)
  ctx.bezierCurveTo(270, 346, 318, 338, 362, 338)
  ctx.bezierCurveTo(406, 338, 455, 346, 500, 382)
  ctx.bezierCurveTo(526, 412, 528, 468, 522, 505)
  ctx.bezierCurveTo(514, 562, 452, 600, 362, 602)
  ctx.bezierCurveTo(274, 600, 210, 562, 203, 505)
  ctx.bezierCurveTo(198, 466, 200, 412, 225, 382)
  ctx.closePath()
  fillOut(ctx, C.fur)
  // forehead stripes
  ctx.strokeStyle = C.furDark; ctx.lineWidth = 9; ctx.lineCap = 'round'; ctx.lineJoin = 'round'
  for (const s of [[[262, 412], [328, 405], [330, 392]], [[360, 372], [360, 416]], [[386, 386], [390, 404]], [[398, 388], [426, 376], [458, 396]]]) {
    ctx.beginPath(); ctx.moveTo(s[0][0], s[0][1]); for (const q of s.slice(1)) ctx.lineTo(q[0], q[1]); ctx.stroke()
  }
  // hair curl
  ctx.beginPath()
  ctx.moveTo(312, 374)
  ctx.bezierCurveTo(298, 318, 332, 280, 402, 282)
  ctx.bezierCurveTo(452, 284, 492, 296, 484, 320)
  ctx.bezierCurveTo(470, 310, 430, 302, 396, 313)
  ctx.bezierCurveTo(362, 326, 352, 350, 352, 376)
  ctx.closePath()
  fillOut(ctx, C.fur)
  ctx.beginPath(); ctx.moveTo(334, 336); ctx.quadraticCurveTo(372, 296, 448, 300)
  ctx.lineWidth = 7; ctx.strokeStyle = C.furLight; ctx.stroke()
  // blush
  ctx.fillStyle = `rgba(${C.blush},${0.25 + 0.45 * p.blush})`
  ellipse(ctx, 254, 512, 28, 14); ctx.fill()
  ellipse(ctx, 470, 512, 28, 14); ctx.fill()
  // muzzle
  ctx.fillStyle = C.cream
  ellipse(ctx, 330, 555, 54, 38); ctx.fill()
  ellipse(ctx, 396, 555, 54, 38); ctx.fill()
  ellipse(ctx, 362, 582, 58, 20); ctx.fill()
  // eyes
  eye(ctx, 297, 472, p, p.winkL, -1)
  eye(ctx, 427, 472, p, p.winkR, 1)
  brows(ctx, p)
  // nose
  ctx.beginPath(); ctx.moveTo(347, 521); ctx.lineTo(377, 521); ctx.lineTo(362, 538); ctx.closePath(); fillOut(ctx, C.nose, 3)
  // mouth
  mouth(ctx, p)
  // beauty mark
  ellipse(ctx, 368, 590, 4, 4); ctx.fillStyle = C.gold; ctx.fill()
  // whiskers
  for (const sgn of [-1, 1]) {
    for (const [dy, ex, ey] of [[-6, 158, 520], [2, 150, 552], [10, 165, 586]]) {
      const x0 = 362 + sgn * 60
      const x1 = 362 + sgn * (362 - ex)
      ctx.beginPath(); ctx.moveTo(x0, 548 + dy); ctx.lineTo(x1, ey)
      ctx.lineWidth = 5; ctx.strokeStyle = 'rgba(18,16,22,0.8)'; ctx.stroke()
      ctx.lineWidth = 2.6; ctx.strokeStyle = '#fbf6ea'; ctx.stroke()
    }
  }
  // earring
  ctx.beginPath(); ctx.arc(213, 432, 11, 0, Math.PI * 2); ctx.lineWidth = 5; ctx.strokeStyle = C.gold; ctx.stroke()
}

function heart(ctx: Ctx, x: number, y: number, s: number, a: number) {
  ctx.save()
  ctx.translate(x, y); ctx.scale(s, s)
  ctx.beginPath()
  ctx.moveTo(0, 10)
  ctx.bezierCurveTo(-26, -8, -12, -30, 0, -14)
  ctx.bezierCurveTo(12, -30, 26, -8, 0, 10)
  ctx.closePath()
  ctx.globalAlpha = a
  ctx.fillStyle = '#ff4d7d'; ctx.fill()
  ctx.lineWidth = 3; ctx.strokeStyle = '#7a0f2a'; ctx.stroke()
  ctx.globalAlpha = 1
  ctx.restore()
}

/** Draws the whole character (everything in front of the limo set). */
export function drawCat(ctx: Ctx, p: CatPose): void {
  const breathe = p.bodyBob * 1.2
  ctx.save()
  ctx.translate(0, breathe * 0.5)
  drawTail(ctx, p)
  drawLegs(ctx)
  drawLeftArm(ctx)
  drawTorso(ctx)
  drawNeck(ctx)
  ctx.save()
  ctx.translate(362, 640 + p.headBob + breathe)
  ctx.rotate((p.headRoll * Math.PI) / 180)
  ctx.translate(-362, -640)
  drawHead(ctx, p)
  ctx.restore()
  drawRightArm(ctx, p)
  ctx.restore()
  for (const h of p.hearts) heart(ctx, h.x, h.y, h.s, h.a)
}
