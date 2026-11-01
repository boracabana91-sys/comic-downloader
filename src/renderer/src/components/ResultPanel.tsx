import { useState } from 'react'
export interface RenderOk {
  ok: true
  video: string
  videoUrl: string
  frames: { label: string; url: string }[]
  qa: { ok: boolean; text: string }[]
  allOk?: boolean
}

export default function ResultPanel({ result, onClose }: { result: RenderOk; onClose: () => void }) {
  const allGood = result.allOk ?? result.qa.every((q) => q.ok)
  const [override, setOverride] = useState(false)
  return (
    <div className="result">
      <div className="result-video">
        <video src={result.videoUrl} controls autoPlay />
      </div>
      <div className="result-side">
        <h2>{allGood ? '🎉 Your video is ready! All checks passed.' : '⚠️ Not ready yet: some checks failed (in red below)'}</h2>
        <p className="small">These checks were measured on the finished video file itself.</p>
        <ul className="facts">
          {result.qa.map((q, i) => (
            <li key={i} className={q.ok ? 'good' : 'bad'}>{q.ok ? '✅' : '❌'} {q.text}</li>
          ))}
        </ul>
        <div className="frames">
          {result.frames.map((f) => (
            <figure key={f.label}>
              <img src={f.url} alt={f.label} />
              <figcaption>{f.label}</figcaption>
            </figure>
          ))}
        </div>
        <div className="row">
          {allGood || override ? (
            <button className="primary" onClick={() => window.catty.reveal(result.video)}>Show my video in Finder</button>
          ) : (
            <button className="secondary" onClick={() => setOverride(true)}>I understand the red checks, let me use it anyway</button>
          )}
          <button className="secondary" onClick={onClose}>Back</button>
        </div>
      </div>
    </div>
  )
}
