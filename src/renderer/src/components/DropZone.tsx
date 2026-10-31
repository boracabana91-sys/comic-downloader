import { useState } from 'react'
import { KIND_LABELS, type AssetKind, type Guess } from '@engine/classify'

export interface AssetCard {
  path: string
  name: string
  size: number
  kind: AssetKind
  allowed: AssetKind[]
  reason: string
  needsAnswer: boolean
}

const ICON: Record<AssetKind, string> = {
  voice: '🎙️', music: '🎵', character: '🐱', background: '🏙️', video: '🎬', notes: '📝', unknown: '❓'
}

function prettySize(n: number): string {
  if (n > 1e9) return `${(n / 1e9).toFixed(1)} GB`
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`
  return `${Math.max(1, Math.round(n / 1e3))} KB`
}

export default function DropZone({ cards, setCards }: { cards: AssetCard[]; setCards: (c: AssetCard[]) => void }) {
  const [over, setOver] = useState(false)

  const addPaths = async (paths: string[]) => {
    const described: { path: string; name: string; size: number; guess: Guess; allowed: AssetKind[] }[] =
      await window.catty.describeFiles(paths)
    const known = new Set(cards.map((c) => c.path))
    const fresh = described
      .filter((d) => !known.has(d.path))
      .map((d) => ({
        path: d.path, name: d.name, size: d.size, kind: d.guess.kind, allowed: d.allowed,
        reason: d.guess.reason, needsAnswer: d.guess.ambiguous
      }))
    setCards([...cards, ...fresh])
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setOver(false)
    const paths = Array.from(e.dataTransfer.files).map((f) => window.catty.pathForFile(f)).filter(Boolean)
    addPaths(paths)
  }

  const setKind = (path: string, kind: AssetKind) =>
    setCards(cards.map((c) => (c.path === path ? { ...c, kind, needsAnswer: false, reason: 'You chose this label.' } : c)))

  const remove = (path: string) => setCards(cards.filter((c) => c.path !== path))

  return (
    <div
      className={`dropzone ${over ? 'over' : ''} ${cards.length ? 'has' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      {cards.length === 0 ? (
        <div className="drop-empty">
          <div className="drop-icon">📥</div>
          <h1>Drop everything here</h1>
          <p>Voice, music, pictures, video clips, notes — all at once is fine.</p>
          <button className="secondary" onClick={async () => addPaths(await window.catty.pickFiles())}>
            …or click to choose files
          </button>
          <p className="small">Your original files are never changed.</p>
        </div>
      ) : (
        <>
          <div className="cards">
            {cards.map((c) => (
              <div key={c.path} className={`card ${c.needsAnswer ? 'ask' : ''}`}>
                <div className="card-head">
                  <span className="card-icon">{c.needsAnswer ? '❓' : ICON[c.kind]}</span>
                  <span className="card-name" title={c.path}>{c.name}</span>
                  <button className="x" aria-label="Remove" onClick={() => remove(c.path)}>✕</button>
                </div>
                <div className="card-size">{prettySize(c.size)}</div>
                <div className="card-reason">{c.needsAnswer ? '🤔 ' : ''}{c.reason}</div>
                {c.allowed.length > 1 && (
                  <div className="card-labels">
                    {c.allowed.map((k) => (
                      <button
                        key={k}
                        className={`chip ${c.kind === k && !c.needsAnswer ? 'on' : ''}`}
                        onClick={() => setKind(c.path, k)}
                      >
                        {ICON[k]} {KIND_LABELS[k]}
                      </button>
                    ))}
                  </div>
                )}
                {c.allowed.length <= 1 && <div className="card-kind">{KIND_LABELS[c.kind]}</div>}
              </div>
            ))}
          </div>
          <div className="drop-more">Drop more files anywhere here.</div>
        </>
      )}
    </div>
  )
}
