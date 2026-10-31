import { useEffect, useRef, useState } from 'react'
import type { Settings } from '@engine/settings'
import type { FormatId } from '@engine/formats'
import { versionLabel } from '@engine/version'
import Wizard from './components/Wizard'
import DropZone, { type AssetCard } from './components/DropZone'
import FormatTicker from './components/FormatTicker'
import ChatPanel from './components/ChatPanel'
import TimingPanel, { type CheckResult } from './components/TimingPanel'
import ResultPanel, { type RenderOk } from './components/ResultPanel'
import TimelineEditor, { type EditorView, type ManualClip } from './components/TimelineEditor'

type Failure = { ok: false; message: string; detail?: string }

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [cards, setCards] = useState<AssetCard[]>([])
  const [toolsMsg, setToolsMsg] = useState<string>('')
  const [busy, setBusy] = useState<{ step: string; fraction: number | null } | null>(null)
  const [check, setCheck] = useState<CheckResult | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [result, setResult] = useState<RenderOk | null>(null)
  const [error, setError] = useState<Failure | null>(null)
  const params = useRef<{ punchIndex: number | null; hitIndex: number; pauseSec: number | null; look: 'drawn' | 'clip' | 'picture'; manual?: ManualClip[] }>({ punchIndex: null, hitIndex: 0, pauseSec: null, look: 'drawn' })
  const keepTiming = useRef(false)

  useEffect(() => {
    window.catty.getSettings().then(setSettings)
    window.catty.checkTools().then((r: { ok: boolean; message?: string }) =>
      setToolsMsg(r.ok ? '' : r.message ?? 'Video tools are not working.')
    )
    return window.catty.onProgress((p) => setBusy(p))
  }, [])

  // New or changed files mean the old timing no longer applies.
  const cardKey = cards.map((c) => `${c.path}|${c.kind}|${c.musicRole}|${c.needsAnswer}|${c.roleKnown}`).join(';')
  useEffect(() => {
    if (keepTiming.current) { keepTiming.current = false; return }
    setCheck(null)
    setConfirmed(false)
    setResult(null)
    params.current = { punchIndex: null, hitIndex: 0, pauseSec: null, look: params.current.look }
  }, [cardKey])

  const update = async (patch: Partial<Settings>) => {
    if (!settings) return
    setSettings(await window.catty.setSettings({ ...settings, ...patch }))
  }

  const label = versionLabel(__APP_NAME__, __APP_VERSION__)
  if (!settings) return <div className="loading">Loading…</div>

  const unanswered = cards.filter((c) => c.needsAnswer || (c.kind === 'music' && !c.roleKnown))
  const hasVoice = cards.some((c) => c.kind === 'voice' && !c.needsAnswer)
  const channel = settings.channels.find((c) => c.id === settings.activeChannelId)?.name ?? 'My video'
  const pauseSec = params.current.pauseSec ?? settings.punchPauseSec

  const runCheck = async (format: FormatId = settings.format, cardList: AssetCard[] = cards) => {
    setError(null)
    setResult(null)
    setBusy({ step: 'Starting…', fraction: null })
    const r = await window.catty.checkTiming({
      cards: cardList.map((c) => ({ path: c.path, kind: c.kind, musicRole: c.musicRole })),
      manualMusic: params.current.manual,
      format,
      pauseSec,
      punchIndex: params.current.punchIndex,
      hitIndex: params.current.hitIndex,
      channelName: channel,
      look: params.current.look
    })
    setBusy(null)
    if (r.ok) setCheck(r as CheckResult)
    else setError(r as Failure)
  }

  const makeVideo = async () => {
    setError(null)
    setBusy({ step: 'Making your video…', fraction: 0 })
    const r = await window.catty.makeVideo()
    setBusy(null)
    if (r.ok) setResult(r as RenderOk)
    else setError(r as Failure)
  }

  let hint = ''
  if (!hasVoice) hint = 'Drop your voiceover to start.'
  else if (unanswered.length) hint = `Please answer the ${unanswered.length} yellow card${unanswered.length > 1 ? 's' : ''} first.`
  else if (!check) hint = 'Click “Check timing” to line up the punch line with the music.'
  else if (!confirmed) hint = 'Please confirm which part is the punch line.'
  else hint = 'All set! Click “Make my video”.'

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
              {result ? (
                <ResultPanel result={result} onClose={() => setResult(null)} />
              ) : (
                <>
                  <FormatTicker
                    value={settings.format}
                    onChange={(f: FormatId) => {
                      void update({ format: f })
                      if (check) void runCheck(f)
                    }}
                  />
                  <DropZone cards={cards} setCards={setCards} compact={!!check} />
                  {error && (
                    <div className="banner error">
                      ⚠️ {error.message}{' '}
                      {error.detail && <button className="link" onClick={() => window.catty.copyText(error.detail!)}>Copy details</button>}
                    </div>
                  )}
                  {check && (
                    <TimingPanel
                      result={check}
                      confirmed={confirmed}
                      pauseSec={pauseSec}
                      onConfirm={() => setConfirmed(true)}
                      onPickPunch={(i) => {
                        params.current.punchIndex = i
                        setConfirmed(false)
                        void runCheck()
                      }}
                      onPickHit={(i) => {
                        params.current.hitIndex = i
                        void runCheck()
                      }}
                      onPause={(s) => {
                        params.current.pauseSec = s
                        void runCheck()
                      }}
                      hasClip={cards.some((c) => c.kind === 'video')}
                      hasPicture={cards.some((c) => c.kind === 'character' || c.kind === 'background')}
                      onLook={(l) => {
                        params.current.look = l
                        void runCheck()
                      }}
                    />
                  )}
                  {check && (check.plan as unknown as { editor?: EditorView }).editor && (
                    <details className="tl-wrap" open={!!params.current.manual}>
                      <summary>🎚️ Fix the timing by hand <small>(only if the automatic sync doesn’t sound right)</small></summary>
                      <TimelineEditor
                        data={(check.plan as unknown as { editor: EditorView }).editor}
                        punchAtSec={check.plan.punchAtSec}
                        durationSec={check.plan.durationSec}
                        onApply={(clips) => {
                          params.current.manual = clips
                          void runCheck()
                        }}
                        onAuto={() => {
                          params.current.manual = undefined
                          void runCheck()
                        }}
                        onDropFile={async (path, atSec) => {
                          const ed = (check.plan as unknown as { editor: EditorView }).editor
                          const [d] = await window.catty.describeFiles([path])
                          if (!d) return
                          const existing = params.current.manual ?? ed.clips.map((c) => ({ cardPath: c.cardPath, dstFromPunchSec: c.dstSec - check.plan.punchAtSec, inSec: c.inSec, outSec: c.outSec }))
                          params.current.manual = [...existing, { cardPath: d.path, dstFromPunchSec: atSec - check.plan.punchAtSec, inSec: 0, outSec: null }]
                          let next = cards
                          if (!cards.some((c) => c.path === d.path)) {
                            next = [...cards, { path: d.path, name: d.name, size: d.size, kind: 'music', allowed: d.allowed, reason: 'Dropped on the timeline as music.', needsAnswer: false, musicRole: 'main', roleKnown: true }]
                            keepTiming.current = true
                            setCards(next)
                          }
                          void runCheck(settings.format, next)
                        }}
                      />
                    </details>
                  )}
                </>
              )}
            </section>
            <ChatPanel />
          </main>
          <footer className="bottombar">
            <button className="secondary big" disabled={!hasVoice || unanswered.length > 0 || !!busy} onClick={() => runCheck()}>
              {check ? 'Check timing again' : 'Check timing'}
            </button>
            <button className="primary big" disabled={!check || !confirmed || !!busy} onClick={makeVideo}>
              Make my video
            </button>
            {busy ? (
              <div className="progress">
                <div className="progress-label">{busy.step}</div>
                <div className="progress-bar">
                  <div className={`progress-fill ${busy.fraction === null ? 'indeterminate' : ''}`} style={{ width: `${Math.round((busy.fraction ?? 0.3) * 100)}%` }} />
                </div>
              </div>
            ) : (
              <span className="hint">{hint}</span>
            )}
          </footer>
        </>
      )}
    </div>
  )
}
