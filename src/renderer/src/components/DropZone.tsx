import { useState, type Dispatch, type SetStateAction } from 'react'
import { KIND_LABELS, type AssetKind, type Guess, type MusicRole } from '@engine/classify'

export interface AssetCard {
  path: string
  name: string
  size: number
  kind: AssetKind
  allowed: AssetKind[]
  reason: string
  needsAnswer: boolean
  musicRole: MusicRole | null
  roleKnown: boolean
  thumb?: string | null
}

const ICON: Record<AssetKind, string> = {
  voice: '🎙️', music: '🎵', character: '🐱', background: '🏙️', video: '🎬', notes: '📝', unknown: '❓'
}

const ROLE_LABEL: Record<MusicRole, string> = { intro: 'Intro', chorus: 'Chorus', main: 'Single track' }

function prettySize(n: number): string {
  if (n > 1e9) return `${(n / 1e9).toFixed(1)} GB`
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`
  return `${Math.max(1, Math.round(n / 1e3))} KB`
}

export default function DropZone({ cards, setCards }: { cards: AssetCard[]; setCards: Dispatch<SetStateAction<AssetCard[]>> }) {
  const [over, setOver] = useState(false)

  const addPaths = async (paths: string[]) => {
    const described: {
      path: string; name: string; size: number; guess: Guess; allowed: AssetKind[]; musicRole: { role: MusicRole; ambiguous: boolean } | null
    }[] = await window.catty.describeFiles(paths)
    const known = new Set(cards.map((c) => c.path))
    const fresh: AssetCard[] = described
      .filter((d) => !known.has(d.path))
      .map((d) => ({
        path: d.path, name: d.name, size: d.size, kind: d.guess.kind, allowed: d.allowed,
        reason: d.guess.reason, needsAnswer: d.guess.ambiguous,
        musicRole: d.musicRole?.role ?? null, roleKnown: d.musicRole ? !d.musicRole.ambiguous : true
      }))
    setCards([...cards, ...fresh])

    // Thumbnails load in after the cards appear, so dropping a big batch still feels instant.
    for (const d of fresh) {
      const thumbKind = d.kind === 'video' ? 'video' : d.allowed.includes('character') || d.allowed.includes('background') ? 'image' : null
      if (!thumbKind) continue
      window.catty.thumbnail(d.path, thumbKind).then((thumb: string | null) => {
        setCards((prev) => prev.map((c) => (c.path === d.path ? { ...c, thumb } : c)))
      })
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setOver(false)
    const paths = Array.from(e.dataTransfer.files).map((f) => window.catty.pathForFile(f)).filter(Boolean)
    addPaths(paths)
  }

  const setKind = (path: string, kind: AssetKind) =>
    setCards(cards.map((c) => (c.path === path ? { ...c, kind, needsAnswer: false, reason: 'You chose this label.' } : c)))

  const setRole = (path: string, musicRole: MusicRole) =>
    setCards(cards.map((c) => (c.path === path ? { ...c, musicRole, roleKnown: true } : c)))

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
            {cards.map((c) => {
              const needsRole = c.kind === 'music' && !c.roleKnown
              return (
                <div key={c.path} className={`card ${c.needsAnswer || needsRole ? 'ask' : ''}`}>
                  <div className="card-head">
                    {c.thumb ? (
                      <img className="card-thumb" src={c.thumb} alt="" />
                    ) : (
                      <span className="card-icon">{c.needsAnswer ? '❓' : ICON[c.kind]}</span>
                    )}
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

                  {c.kind === 'music' && (
                    <>
                      {needsRole && <div className="card-reason">🤔 Does this play first (intro) or is it the main part (chorus)?</div>}
                      <div className="card-labels">
                        {(['intro', 'chorus', 'main'] as MusicRole[]).map((r) => (
                          <button
                            key={r}
                            className={`chip ${c.musicRole === r && c.roleKnown ? 'on' : ''}`}
                            onClick={() => setRole(c.path, r)}
                          >
                            {ROLE_LABEL[r]}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )
            })}
          </div>
          <div className="drop-more">Drop more files anywhere here.</div>
        </>
      )}
    </div>
  )
}
