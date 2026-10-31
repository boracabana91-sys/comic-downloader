import { useRef, useState } from 'react'

export interface CheckResult {
  ok: true
  projectDir: string
  visual: 'picture' | 'clip' | 'none'
  stillUrl: string | null
  plan: {
    phrases: { index: number; startSec: number; endSec: number; url: string }[]
    punchIndex: number
    punchGuessed: boolean
    hits: { atSec: number; strength: number }[]
    hitIndex: number
    musicSummary: string
    punchAtSec: number
    durationSec: number
    mixUrl: string
    loudnessText: string
    voiceOverMusicDb: number | null
    syncErrorMs: number | null
    notes: string[]
    warnings: string[]
  }
}

function PlayButton({ url, label }: { url: string; label: string }) {
  const ref = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  return (
    <>
      <audio ref={ref} src={url} onEnded={() => setPlaying(false)} onPause={() => setPlaying(false)} />
      <button
        className="play"
        aria-label={label}
        onClick={() => {
          const a = ref.current
          if (!a) return
          if (playing) { a.pause(); a.currentTime = 0 } else { a.currentTime = 0; void a.play(); setPlaying(true) }
        }}
      >
        {playing ? '⏹' : '▶'}
      </button>
    </>
  )
}

export default function TimingPanel(props: {
  result: CheckResult
  confirmed: boolean
  pauseSec: number
  onConfirm: () => void
  onPickPunch: (i: number) => void
  onPickHit: (i: number) => void
  onPause: (s: number) => void
}) {
  const { plan } = props.result
  const [pause, setPause] = useState(props.pauseSec)
  const sync = plan.syncErrorMs
  return (
    <div className="timing">
      <div className="timing-col">
        <h2>1. Which part is the punch line?</h2>
        <p className="small">
          I found {plan.phrases.length} part{plan.phrases.length === 1 ? '' : 's'} in your voice. Press ▶ to listen.
          {plan.punchGuessed && !props.confirmed && ' I guessed the last one — please check.'}
        </p>
        <div className="phrases">
          {plan.phrases.map((p) => (
            <div key={p.index} className={`phrase ${p.index === plan.punchIndex ? 'on' : ''}`}>
              <PlayButton url={p.url} label={`Play part ${p.index + 1}`} />
              <button className="phrase-pick" onClick={() => props.onPickPunch(p.index)}>
                Part {p.index + 1} <small>{(p.endSec - p.startSec).toFixed(1)} s</small>
                {p.index === plan.punchIndex && <span className="tag">🥁 Punch line</span>}
              </button>
            </div>
          ))}
        </div>
        {props.confirmed ? (
          <div className="banner ok">✅ Part {plan.punchIndex + 1} is the punch line.</div>
        ) : (
          <button className="primary" onClick={props.onConfirm}>Yes, part {plan.punchIndex + 1} is the punch line</button>
        )}

        <h2>2. Pause before the punch line</h2>
        <div className="row">
          <input
            type="range" min={0.5} max={4} step={0.1} value={pause}
            onChange={(e) => setPause(Number(e.target.value))}
            onMouseUp={() => props.onPause(pause)}
            onKeyUp={() => props.onPause(pause)}
            aria-label="Pause before the punch line"
          />
          <b>{pause.toFixed(1)} s</b>
        </div>
        <p className="small">The music keeps playing during the pause.</p>

        {plan.hits.length > 1 && (
          <>
            <h2>3. Music hit</h2>
            <p className="small">{plan.musicSummary} Doesn’t sound right? Try another hit:</p>
            <div className="card-labels">
              {plan.hits.slice(0, 4).map((h, i) => (
                <button key={i} className={`chip ${i === plan.hitIndex ? 'on' : ''}`} onClick={() => props.onPickHit(i)}>
                  {i === 0 ? '⭐ ' : ''}{h.atSec.toFixed(2)} s
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="timing-col">
        <h2>Listen to the timing</h2>
        <audio className="mix" controls src={plan.mixUrl} />
        <ul className="facts">
          <li>🥁 The punch line lands at <b>{plan.punchAtSec.toFixed(2)} s</b> of a {plan.durationSec.toFixed(1)} s video.</li>
          {sync !== null && (
            <li className={Math.abs(sync) <= 33 ? 'good' : 'bad'}>
              {Math.abs(sync) <= 33 ? '✅' : '⚠️'} Punch line and music hit are {Math.abs(sync)} ms apart
              {Math.abs(sync) <= 33 ? ' (perfect: less than one frame).' : '.'}
            </li>
          )}
          {plan.voiceOverMusicDb !== null && <li>🎙️ Your voice is {plan.voiceOverMusicDb.toFixed(1)} dB above the music.</li>}
          <li>🔊 {plan.loudnessText}</li>
          {plan.notes.map((n, i) => <li key={`n${i}`}>ℹ️ {n}</li>)}
          {plan.warnings.map((w, i) => <li key={`w${i}`} className="bad">⚠️ {w}</li>)}
        </ul>
        {props.result.stillUrl && (
          <div className="still">
            <img src={props.result.stillUrl} alt="How the video will look" />
            <small>How the video will be framed</small>
          </div>
        )}
      </div>
    </div>
  )
}
