// A small video-editor style timeline: see the voice and music as waveforms, drag music clips,
// trim where they start/end, drop new music files where they should start, and hear it instantly.
import { useEffect, useMemo, useRef, useState } from 'react'

export interface EditorView {
  pps: number
  voicePeaks: number[]
  voiceUrl: string
  manual: boolean
  files: { cardPath: string; name: string; durSec: number; peaks: number[]; hitsSec: number[]; url: string }[]
  clips: { cardPath: string; dstSec: number; inSec: number; outSec: number }[]
}

export interface ManualClip {
  cardPath: string
  dstFromPunchSec: number
  inSec: number
  outSec: number | null
}

interface Clip { id: number; cardPath: string; dst: number; in: number; out: number }

const PRE = 1.5 // seconds shown before the video starts
const RULER_H = 26
const VOICE_H = 54
const ROW_H = 56
const FRAME = 1 / 30
const SNAP_PX = 10

function drawWave(c: HTMLCanvasElement | null, peaks: number[], pps: number, from: number, to: number, zoom: number, color: string) {
  if (!c) return
  const w = Math.max(1, Math.round((to - from) * zoom))
  const h = c.height
  if (c.width !== w) c.width = w
  const ctx = c.getContext('2d')!
  ctx.clearRect(0, 0, w, h)
  ctx.fillStyle = color
  for (let x = 0; x < w; x++) {
    const a = Math.floor((from + x / zoom) * pps)
    const b = Math.max(a + 1, Math.floor((from + (x + 1) / zoom) * pps))
    let m = 0
    for (let k = a; k < b && k < peaks.length; k++) if (k >= 0) m = Math.max(m, peaks[k])
    const bh = Math.max(1, m * (h - 4))
    ctx.fillRect(x, (h - bh) / 2, 1, bh)
  }
}

export default function TimelineEditor(props: {
  data: EditorView
  punchAtSec: number
  durationSec: number
  onApply: (clips: ManualClip[]) => void
  onAuto: () => void
  onDropFile: (path: string, atSec: number) => void
}) {
  const { data, punchAtSec: P, durationSec: D } = props
  const files = useMemo(() => new Map(data.files.map((f) => [f.cardPath, f])), [data.files])
  const initial = useMemo(() => data.clips.map((c, i) => ({ id: i + 1, cardPath: c.cardPath, dst: c.dstSec, in: c.inSec, out: c.outSec })), [data.clips])
  const [clips, setClips] = useState<Clip[]>(initial)
  const [dirty, setDirty] = useState(false)
  const [sel, setSel] = useState<number | null>(initial[0]?.id ?? null)
  const [zoom, setZoom] = useState(90) // px per second
  const [snap, setSnap] = useState(true)
  const [together, setTogether] = useState(true)
  const dragOrig = useRef<Clip[]>([])
  const [head, setHead] = useState(Math.max(0, P - 2))
  const [playing, setPlaying] = useState(false)
  const [playErr, setPlayErr] = useState('')
  const scroller = useRef<HTMLDivElement>(null)
  const drag = useRef<{ id: number; mode: 'move' | 'left' | 'right'; x0: number; orig: Clip } | null>(null)

  useEffect(() => { setClips(initial); setDirty(false) }, [initial])

  const X = (t: number) => (t + PRE) * zoom
  const T = (x: number) => x / zoom - PRE
  const width = X(Math.max(D, ...clips.map((c) => c.dst + c.out - c.in)) + 1.5)

  // Keep the punch line in view when opening / zooming.
  useEffect(() => {
    const el = scroller.current
    if (el) el.scrollLeft = Math.max(0, X(P) - el.clientWidth / 2)
  }, [zoom]) // eslint-disable-line react-hooks/exhaustive-deps

  // ───────── live preview playback (Web Audio) ─────────
  const audio = useRef<{ ctx: AudioContext; nodes: AudioBufferSourceNode[]; t0: number; h0: number; raf: number } | null>(null)
  const buffers = useRef(new Map<string, AudioBuffer>())
  async function buf(ctx: AudioContext, url: string) {
    let b = buffers.current.get(url)
    if (!b) {
      const res = await fetch(url)
      b = await ctx.decodeAudioData(await res.arrayBuffer())
      buffers.current.set(url, b)
    }
    return b
  }
  function stop() {
    const a = audio.current
    if (!a) return
    a.nodes.forEach((n) => { try { n.stop() } catch { /* already stopped */ } })
    cancelAnimationFrame(a.raf)
    void a.ctx.close()
    audio.current = null
    setPlaying(false)
  }
  async function play() {
    stop()
    const ctx = new AudioContext()
    const nodes: AudioBufferSourceNode[] = []
    const start = ctx.currentTime + 0.15
    const h0 = Math.max(0, head)
    const voice = await buf(ctx, data.voiceUrl)
    const vs = ctx.createBufferSource()
    vs.buffer = voice
    vs.connect(ctx.destination)
    if (h0 < voice.duration) { vs.start(start, h0); nodes.push(vs) }
    const mg = ctx.createGain()
    mg.gain.value = 0.5
    mg.connect(ctx.destination)
    for (const c of clips) {
      const f = files.get(c.cardPath)
      if (!f) continue
      const b = await buf(ctx, f.url)
      const skip = Math.max(0, h0 - c.dst)
      const dur = c.out - c.in - skip
      if (dur <= 0) continue
      const s = ctx.createBufferSource()
      s.buffer = b
      s.connect(mg)
      s.start(start + Math.max(0, c.dst - h0), c.in + skip, dur)
      nodes.push(s)
    }
    const tick = () => {
      const a = audio.current
      if (!a) return
      const t = a.h0 + Math.max(0, a.ctx.currentTime - a.t0)
      setHead(t)
      if (t > Math.max(D, 1) + 0.2) { stop(); return }
      a.raf = requestAnimationFrame(tick)
    }
    audio.current = { ctx, nodes, t0: start, h0, raf: requestAnimationFrame(tick) }
    setPlaying(true)
  }
  useEffect(() => () => stop(), []) // eslint-disable-line react-hooks/exhaustive-deps

  // ───────── editing ─────────
  /** Move the selected clip in time (and the others too, when "together" is on). */
  function shift(id: number, delta: number) {
    setClips((cs) => cs.map((c) => (together || c.id === id ? { ...c, dst: c.dst + delta } : c)))
    setDirty(true)
  }
  function update(id: number, patch: Partial<Clip>) {
    setClips((cs) => cs.map((c) => (c.id === id ? { ...c, ...patch } : c)))
    setDirty(true)
  }
  function hitsOn(c: Clip): number[] {
    const f = files.get(c.cardPath)
    return (f?.hitsSec ?? []).filter((h) => h >= c.in && h <= c.out).map((h) => c.dst + (h - c.in))
  }
  function nearestHitDelta(c: Clip): number | null {
    const hs = hitsOn(c)
    if (!hs.length) return null
    return hs.reduce((b, h) => (Math.abs(h - P) < Math.abs(b - P) ? h : b)) - P
  }
  function snapMove(c: Clip): Clip {
    if (!snap) return c
    let best: number | null = null
    const consider = (delta: number) => {
      if (Math.abs(delta) * zoom < SNAP_PX && (best === null || Math.abs(delta) < Math.abs(best))) best = delta
    }
    for (const h of hitsOn(c)) consider(P - h) // a music hit onto the punch line
    consider(P - c.dst) // clip start onto the punch line
    consider(0 - c.dst) // clip start onto the video start
    for (const o of together ? [] : clips) if (o.id !== c.id) {
      consider(o.dst + (o.out - o.in) - c.dst) // start right where another clip ends
      consider(o.dst - (c.dst + c.out - c.in)) // end right where another clip starts
    }
    return best === null ? c : { ...c, dst: c.dst + best }
  }
  function onPointerDown(e: React.PointerEvent, c: Clip, mode: 'move' | 'left' | 'right') {
    e.stopPropagation()
    stop()
    setSel(c.id)
    drag.current = { id: c.id, mode, x0: e.clientX, orig: { ...c } }
    dragOrig.current = clips.map((k) => ({ ...k }))
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }
  function onPointerMove(e: React.PointerEvent) {
    const d = drag.current
    if (!d) return
    const dt = (e.clientX - d.x0) / zoom
    const f = files.get(d.orig.cardPath)
    const o = d.orig
    if (d.mode === 'move') {
      const moved = snapMove({ ...o, dst: o.dst + dt })
      const delta = moved.dst - o.dst
      if (together) {
        setClips(dragOrig.current.map((k) => ({ ...k, dst: k.dst + delta })))
        setDirty(true)
      } else update(o.id, { dst: moved.dst })
    } else if (d.mode === 'left') {
      let ni = Math.min(Math.max(0, o.in + dt), o.out - 0.05)
      let nd = o.dst + (ni - o.in)
      if (snap && Math.abs(nd - P) * zoom < SNAP_PX) { ni += P - nd; nd = P }
      update(o.id, { in: ni, dst: nd })
    } else {
      const no = Math.max(o.in + 0.05, Math.min(f?.durSec ?? o.out, o.out + dt))
      update(o.id, { out: no })
    }
  }
  function onPointerUp() { drag.current = null }

  function apply() {
    stop()
    props.onApply(clips.map((c) => ({ cardPath: c.cardPath, dstFromPunchSec: c.dst - P, inSec: c.in, outSec: c.out })))
  }

  const selected = clips.find((c) => c.id === sel) ?? null
  const selDelta = selected ? nearestHitDelta(selected) : null
  const rows = clips.length
  const height = RULER_H + VOICE_H + Math.max(1, rows) * ROW_H + 8

  const ticks: number[] = []
  const step = zoom > 160 ? 0.5 : zoom > 60 ? 1 : 2
  for (let t = -1; t < (width / zoom) - PRE; t += step) ticks.push(Math.round(t * 10) / 10)

  const num = (v: number, set: (x: number) => void, label: string) => (
    <label className="tl-num">
      <span>{label}</span>
      <input type="number" step={0.001} value={v.toFixed(3)} onChange={(e) => { const x = Number(e.target.value); if (!Number.isNaN(x)) set(x) }} />
      <span>s</span>
    </label>
  )

  return (
    <div className="tl" onPointerMove={onPointerMove} onPointerUp={onPointerUp}>
      <div className="tl-bar">
        <button
          className="play"
          onClick={() => {
            if (playing) { stop(); return }
            setPlayErr('')
            play().catch(() => { stop(); setPlayErr('The preview couldn’t play. “Use this timing” still works; then use the player above.') })
          }}
          aria-label={playing ? 'Stop' : 'Play'}
        >{playing ? '⏹' : '▶'}</button>
        <span className="tl-time">{head.toFixed(2)} s</span>
        <label className="tl-zoom">🔍 <input type="range" min={30} max={600} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} aria-label="Zoom" /></label>
        <label className="tl-check"><input type="checkbox" checked={snap} onChange={(e) => setSnap(e.target.checked)} /> Snap to the punch line</label>
        <label className="tl-check"><input type="checkbox" checked={together} onChange={(e) => setTogether(e.target.checked)} /> Move all music together</label>
        <span className="tl-spacer" />
        {(data.manual || dirty) && <button className="secondary" onClick={() => { stop(); props.onAuto() }}>↺ Back to automatic</button>}
        <button className="primary" disabled={!dirty} onClick={apply}>✅ Use this timing</button>
      </div>

      <div className="tl-body">
        <div className="tl-labels" style={{ height }}>
          <div style={{ height: RULER_H }} />
          <div className="tl-label" style={{ height: VOICE_H }}>🎙️ Voice</div>
          {clips.map((c) => (
            <div key={c.id} className="tl-label" style={{ height: ROW_H }} title={files.get(c.cardPath)?.name}>🎵 {files.get(c.cardPath)?.name ?? 'Music'}</div>
          ))}
        </div>
        <div className="tl-scroll" ref={scroller}>
          <div
            className="tl-canvas"
            style={{ width, height }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              const file = e.dataTransfer.files[0]
              if (!file) return
              const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
              const at = T(e.clientX - rect.left)
              props.onDropFile(window.catty.pathForFile(file), Math.round(at * 1000) / 1000)
            }}
          >
            <div className="tl-ruler" style={{ height: RULER_H }} onPointerDown={(e) => {
              const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
              setHead(Math.max(0, T(e.clientX - rect.left)))
              stop()
            }}>
              {ticks.map((t) => (
                <div key={t} className="tl-tick" style={{ left: X(t) }}>{Number.isInteger(t) ? `${t}s` : ''}</div>
              ))}
            </div>
            <div className="tl-before" style={{ width: X(0), top: RULER_H, height: height - RULER_H }} title="Before the video starts" />
            <div className="tl-after" style={{ left: X(D), top: RULER_H, height: height - RULER_H }} title="After the video ends" />

            <div className="tl-lane" style={{ top: RULER_H, height: VOICE_H }}>
              <canvas
                style={{ left: X(0), position: 'absolute', top: 4 }}
                height={VOICE_H - 8}
                ref={(c) => drawWave(c, data.voicePeaks, data.pps, 0, data.voicePeaks.length / data.pps, zoom, '#ff6b8b')}
              />
            </div>

            {clips.map((c, row) => {
              const f = files.get(c.cardPath)
              const top = RULER_H + VOICE_H + row * ROW_H
              return (
                <div
                  key={c.id}
                  className={`tl-clip ${sel === c.id ? 'on' : ''}`}
                  style={{ left: X(c.dst), top: top + 4, width: Math.max(4, (c.out - c.in) * zoom), height: ROW_H - 8 }}
                  onPointerDown={(e) => onPointerDown(e, c, 'move')}
                  title="Drag to move. Drag the edges to change where the music starts and ends."
                >
                  <canvas height={ROW_H - 12} ref={(el) => f && drawWave(el, f.peaks, data.pps, c.in, c.out, zoom, '#6c4bd6')} />
                  {hitsOn(c).map((h, i) => (
                    <div key={i} className="tl-hit" style={{ left: (h - c.dst) * zoom }} title="Music hit" />
                  ))}
                  <div className="tl-edge left" onPointerDown={(e) => onPointerDown(e, c, 'left')} />
                  <div className="tl-edge right" onPointerDown={(e) => onPointerDown(e, c, 'right')} />
                </div>
              )
            })}

            <div className="tl-punch" style={{ left: X(P), top: 0, height }}><span>🥁 Punch line {P.toFixed(2)} s</span></div>
            <div className="tl-head" style={{ left: X(head), top: 0, height }} />
          </div>
        </div>
      </div>

      {playErr && <div className="banner error">⚠️ {playErr}</div>}
      <p className="small tl-hint">⬇ Drop any music or video file (mp3, m4a, wav, mp4…) onto the timeline, right at the spot where it should start. Drag a clip to move it, drag its edges to choose where the music starts and ends.</p>
      {selected && (
        <div className="tl-detail">
          <div className="tl-detail-row">
            <b>🎵 {files.get(selected.cardPath)?.name}</b>
            {selDelta !== null && (
              <span className={Math.abs(selDelta) <= FRAME ? 'good' : 'bad'}>
                {Math.abs(selDelta) <= 0.0005 ? '✅ Its hit is exactly on the punch line' : `${Math.abs(selDelta) <= FRAME ? '✅' : '⚠️'} Its nearest hit is ${Math.round(Math.abs(selDelta) * 1000)} ms ${selDelta > 0 ? 'after' : 'before'} the punch line`}
              </span>
            )}
          </div>
          <div className="tl-detail-row">
            {num(selected.dst, (x) => shift(selected.id, x - selected.dst), 'Starts on the video at')}
            <div className="tl-nudge">
              <button onClick={() => shift(selected.id, -FRAME)}>−1 frame</button>
              <button onClick={() => shift(selected.id, -0.01)}>−10 ms</button>
              <button onClick={() => shift(selected.id, 0.01)}>+10 ms</button>
              <button onClick={() => shift(selected.id, FRAME)}>+1 frame</button>
            </div>
          </div>
          <div className="tl-detail-row">
            {num(selected.in, (x) => {
              const ni = Math.max(0, Math.min(x, selected.out - 0.05))
              update(selected.id, { in: ni, dst: selected.dst + (ni - selected.in) })
            }, 'Song plays from')}
            {num(selected.out, (x) => update(selected.id, { out: Math.max(selected.in + 0.05, Math.min(x, files.get(selected.cardPath)?.durSec ?? x)) }), 'to')}
            {selDelta !== null && <button className="secondary" onClick={() => shift(selected.id, -selDelta)}>🎯 Put its hit on the punch line</button>}
            <button className="secondary" onClick={() => { setClips((cs) => cs.filter((c) => c.id !== selected.id)); setDirty(true); setSel(null) }}>🗑 Remove</button>
          </div>
          <p className="small">▶ plays a quick preview while you edit. “Use this timing” then makes the real mix and checks it.</p>
        </div>
      )}
    </div>
  )
}
