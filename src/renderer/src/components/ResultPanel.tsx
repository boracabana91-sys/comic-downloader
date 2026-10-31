export interface RenderOk {
  ok: true
  video: string
  videoUrl: string
  frames: { label: string; url: string }[]
  qa: { ok: boolean; text: string }[]
}

export default function ResultPanel({ result, onClose }: { result: RenderOk; onClose: () => void }) {
  const allGood = result.qa.every((q) => q.ok)
  return (
    <div className="result">
      <div className="result-video">
        <video src={result.videoUrl} controls autoPlay />
      </div>
      <div className="result-side">
        <h2>{allGood ? '🎉 Your video is ready!' : '⚠️ Your video is made, but please check below'}</h2>
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
          <button className="primary" onClick={() => window.catty.reveal(result.video)}>Show my video in Finder</button>
          <button className="secondary" onClick={onClose}>Back</button>
        </div>
      </div>
    </div>
  )
}
