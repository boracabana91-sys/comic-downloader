import { useState } from 'react'
import type { Settings, ChannelProfile } from '@engine/settings'

type Step = 1 | 2 | 3 | 4

export default function Wizard({ settings, onDone }: { settings: Settings; onDone: (s: Partial<Settings>) => void }) {
  const [step, setStep] = useState<Step>(1)
  const [key, setKey] = useState('')
  const [keyMsg, setKeyMsg] = useState<{ ok: boolean; message: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [channels, setChannels] = useState<ChannelProfile[]>(settings.channels)
  const [active, setActive] = useState<string>(settings.activeChannelId ?? settings.channels[0]?.id ?? '')
  const [newName, setNewName] = useState('')

  const saveKey = async () => {
    setBusy(true)
    setKeyMsg(null)
    const r = await window.catty.saveKey(key)
    setKeyMsg(r)
    setBusy(false)
    if (r.ok) setKey('')
  }

  const addChannel = () => {
    const name = newName.trim()
    if (!name) return
    const id = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || `channel-${Date.now()}`
    if (channels.some((c) => c.id === id)) { setActive(id); setNewName(''); return }
    setChannels([...channels, { id, name, template: 'custom', language: 'tl', format: 'vertical' }])
    setActive(id)
    setNewName('')
  }

  return (
    <div className="wizard">
      <div className="dots">{[1, 2, 3, 4].map((n) => <span key={n} className={n === step ? 'on' : n < step ? 'done' : ''} />)}</div>

      {step === 1 && (
        <div className="panel">
          <div className="hero">🐱🎬</div>
          <h1>Welcome to Cattyfied!</h1>
          <p>
            Drop your voiceover, music and pictures. Cattyfied times the punch line to the music and makes the video for you.
          </p>
          <p className="small">This setup takes about 2 minutes. You can change everything later.</p>
          <button className="primary big" onClick={() => setStep(2)}>Let’s start →</button>
        </div>
      )}

      {step === 2 && (
        <div className="panel">
          <h1>Your Anthropic key</h1>
          <p>The chat helper uses Claude. It needs a key from your Anthropic account.</p>
          <ol className="howto">
            <li>
              Click <button className="link" onClick={() => window.catty.openLink('https://console.anthropic.com/settings/keys')}>Get my key at Anthropic ↗</button> and sign in.
            </li>
            <li>Click <b>Create Key</b>, give it any name (for example “Cattyfied”), and click <b>Copy</b>.</li>
            <li>Come back here and paste it in the box below (press ⌘ and V together).</li>
          </ol>
          <input
            className="big-input"
            type="password"
            placeholder="sk-ant-…"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            autoFocus
          />
          <div className="row">
            <button className="primary" disabled={!key.trim() || busy} onClick={saveKey}>
              {busy ? 'Checking…' : 'Check and save my key'}
            </button>
          </div>
          {keyMsg && <div className={`banner ${keyMsg.ok ? 'ok' : 'error'}`}>{keyMsg.ok ? '✅ ' : '⚠️ '}{keyMsg.message}</div>}
          <p className="small">
            🔒 Your key is stored in your Mac’s Keychain, never in your project files. Only text is sent to Claude, never your
            voice, music or videos.
          </p>
          <p className="small">
            💰 Rough cost: making a video uses only a few short messages, usually a few US cents per video. Cattyfied will show
            the real cost and let you set a monthly limit once the chat is switched on.
          </p>
          <div className="row between">
            <button className="secondary" onClick={() => setStep(1)}>← Back</button>
            <button className={keyMsg?.ok ? 'primary' : 'secondary'} onClick={() => setStep(3)}>
              {keyMsg?.ok ? 'Next →' : 'Skip for now →'}
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="panel">
          <h1>Which channel is this for?</h1>
          <p>Cattyfied remembers your characters, music and settings for each channel.</p>
          <div className="choices">
            {channels.map((c) => (
              <button key={c.id} className={`choice ${active === c.id ? 'on' : ''}`} onClick={() => setActive(c.id)}>
                <strong>{c.name}</strong>
                <small>{c.template === 'casanova' ? 'Casanova-style comedy' : c.template === 'what-if' ? 'What-if stories' : 'My own style'}</small>
              </button>
            ))}
          </div>
          <div className="row">
            <input className="big-input" placeholder="…or type a new channel name" value={newName} onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addChannel()} />
            <button className="secondary" disabled={!newName.trim()} onClick={addChannel}>Add</button>
          </div>
          <div className="row between">
            <button className="secondary" onClick={() => setStep(2)}>← Back</button>
            <button className="primary" disabled={!active} onClick={() => setStep(4)}>Next →</button>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="panel">
          <div className="hero">🎉</div>
          <h1>All set!</h1>
          <p>Your projects will be saved in <b>Documents → Cattyfied</b>.</p>
          <p>Next: drop your files in the big box and Cattyfied will label them for you.</p>
          <button
            className="primary big"
            onClick={async () => {
              await window.catty.ensureFolder()
              onDone({ channels, activeChannelId: active })
            }}
          >
            Open Cattyfied →
          </button>
        </div>
      )}
    </div>
  )
}
