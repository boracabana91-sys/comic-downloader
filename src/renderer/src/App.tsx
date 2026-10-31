import { useEffect, useState } from 'react'
import type { Settings } from '@engine/settings'
import type { FormatId } from '@engine/formats'
import { versionLabel } from '@engine/version'
import Wizard from './components/Wizard'
import DropZone, { type AssetCard } from './components/DropZone'
import FormatTicker from './components/FormatTicker'
import ChatPanel from './components/ChatPanel'

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [cards, setCards] = useState<AssetCard[]>([])
  const [toolsMsg, setToolsMsg] = useState<string>('')

  useEffect(() => {
    window.catty.getSettings().then(setSettings)
    window.catty.checkTools().then((r: { ok: boolean; message?: string }) =>
      setToolsMsg(r.ok ? '' : r.message ?? 'Video tools are not working.')
    )
  }, [])

  const update = async (patch: Partial<Settings>) => {
    if (!settings) return
    setSettings(await window.catty.setSettings({ ...settings, ...patch }))
  }

  const label = versionLabel(__APP_NAME__, __APP_VERSION__)

  if (!settings) return <div className="loading">Loading…</div>

  return (
    <div className={`app ${settings.largeText ? 'large' : ''}`}>
      <header className="topbar">
        <div className="brand">🐱 Cattyfied</div>
        <div className="top-actions">
          <button className="link" onClick={() => update({ largeText: !settings.largeText })}>
            {settings.largeText ? 'Normal text' : 'Bigger text'}
          </button>
          <button className="link" onClick={() => window.catty.openFolder()}>Open my projects folder</button>
        </div>
        <div className="version" title="The version of Cattyfied you are using">{label}</div>
      </header>

      {!settings.firstRunDone ? (
        <Wizard settings={settings} onDone={(s) => update({ ...s, firstRunDone: true })} />
      ) : (
        <>
          {toolsMsg && <div className="banner error">⚠️ {toolsMsg} Please reinstall Cattyfied. If it keeps happening, tell Claude.</div>}
          <main className="main">
            <section className="center">
              <FormatTicker value={settings.format} onChange={(f: FormatId) => update({ format: f })} />
              <DropZone cards={cards} setCards={setCards} />
            </section>
            <ChatPanel />
          </main>
          <footer className="bottombar">
            <button className="secondary" disabled title="Coming in Phase 2">Preview</button>
            <button className="primary big" disabled title="Coming in Phase 2–3">Make my video</button>
            <button className="secondary" disabled title="Coming in Phase 3">Export</button>
            <span className="hint">Making videos arrives in the next update. Right now you can drop files and check the labels.</span>
          </footer>
        </>
      )}
    </div>
  )
}
