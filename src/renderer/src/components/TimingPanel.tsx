import { useEffect, useRef, useState } from 'react'

export interface CheckResult {
  ok: true
  projectDir: string
  visual: 'picture' | 'clip' | 'none' | 'drawn'
  look: 'drawn' | 'clip' | 'picture'
  stillUrl: string | null
  plan: {
    phrases: { index: number; startSec: number; endSec: number; url: string }[]
    punchUnits: number[]
    punchGuessed: boolean
    unitsFromPhrases: boolean
    isolated: boolean
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
  onPickPunch: (units: number[]) => void
  onPause: (s: number) => void
  hasClip: boolean
  hasPicture: boolean
  onLook: (l: 'drawn' | 'clip' | 'picture') => void
}) {
  const { plan } = props.result
  const [pause, setPause] = useState(props.pauseSec)
  const [picked, setPicked] = useState<number[]>(plan.punchUnits)
  useEffect(() => setPicked(plan.punchUnits), [plan.punchUnits.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps
  const changed = picked.join(',') !== plan.punchUnits.join(',')
  const label = (u: number[]) => (u.length === 1 ? `part ${u[0] + 1}` : `parts ${u.map((x) => x + 1).join(' + ')}`)
  const sync = plan.syncErrorMs
  return (
    <div className="timing">
      <div className="timing-col">
        <h2>1. Which part is the punch line?</h2>
        <p className="small">
          I found {plan.phrases.length} part{plan.phrases.length === 1 ? '' : 's'} in your voice{plan.isolated ? ' (after removing any music from it)' : ''}.
          Press ▶ to listen, then tick the part{plan.phrases.length > 1 ? '(s)' : ''} that are the punch line. It can be more than one.
          {plan.punchGuessed && !props.confirmed && ' I ticked the last one as a guess. Please check.'}
        </p>
        <div className="phrases">
          {plan.phrases.map((p) => {
            const on = picked.includes(p.index)
            return (
              <div key={p.index} className={`phrase ${on ? 'on' : ''}`}>
                <PlayButton url={p.url} label={`Play part ${p.index + 1}`} />
                <button
                  className="phrase-pick"
                  onClick={() => setPicked(on ? picked.filter((x) => x !== p.index) : [...picked, p.index].sort((a, b) => a - b))}
                  aria-pressed={on}
                >
                  <span className="tick">{on ? '☑' : '☐'}</span> Part {p.index + 1} <small>{(p.endSec - p.startSec).toFixed(1)} s</small>
                  {on && <span className="tag">🥁 Punch line</span>}
                </button>
              </div>
            )
          })}
        </div>
        {changed ? (
          <button className="primary" disabled={!picked.length || picked[0] === 0} onClick={() => props.onPickPunch(picked)}>
            {picked[0] === 0 ? 'Part 1 can’t be the punch line (something must come before it)' : 'Use these parts as the punch line'}
          </button>
        ) : props.confirmed ? (
          <div className="banner ok">✅ {label(plan.punchUnits)} {plan.punchUnits.length > 1 ? 'are' : 'is'} the punch line.</div>
        ) : (
          <button className="primary" onClick={props.onConfirm}>Yes, {label(plan.punchUnits)} {plan.punchUnits.length > 1 ? 'are' : 'is'} the punch line</button>
        )}
        <p className="small">The word-by-word check (Whisper) isn’t in the app yet, and it’s often wrong on Tagalog anyway. Please confirm by listening.</p>

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
      </div>

      <div className="timing-col">
        <h2>What should the video show?</h2>
        <div className="card-labels">
          <button className={`chip ${props.result.look === 'drawn' ? 'on' : ''}`} onClick={() => props.onLook('drawn')}>🐱 Animated Casanova cat</button>
          {props.hasClip && <button className={`chip ${props.result.look === 'clip' ? 'on' : ''}`} onClick={() => props.onLook('clip')}>🎬 My video clip</button>}
          {props.hasPicture && <button className={`chip ${props.result.look === 'picture' ? 'on' : ''}`} onClick={() => props.onLook('picture')}>🖼️ My picture</button>}
        </div>
        {props.result.look === 'drawn' && (
          <p className="small">The cat talks with your voice, then the camera cuts every second after the punch line (wink, laugh, hearts, toast). Drawn by code, so it is a bit stiffer than hand animation.</p>
        )}
        <h2>Listen to the timing</h2>
        <audio className="mix" controls src={plan.mixUrl} />
        <ul className="facts">
          <li>🥁 The punch line lands at <b>{plan.punchAtSec.toFixed(2)} s</b> of a {plan.durationSec.toFixed(1)} s video.</li>
          {sync !== null && (
            <li className={Math.abs(sync) <= 20 ? 'good' : 'bad'}>
              {Math.abs(sync) <= 20 ? '✅' : '⚠️'} The music’s beat is {Math.abs(sync)} ms from the punch line
              {Math.abs(sync) <= 20 ? ' (on the beat).' : '. If it sounds wrong, fix it by hand below.'}
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
            <small>{props.result.look === 'drawn' ? 'The punch-line moment' : 'How the video will be framed'}</small>
          </div>
        )}
      </div>
    </div>
  )
}
