export default function ChatPanel() {
  return (
    <aside className="chat">
      <h2>💬 Talk to Cattyfied</h2>
      <div className="chat-body">
        <div className="bubble app">
          Hi! Soon you’ll be able to tell me things like “more pause before the punch line” or “make the
          background a rooftop at night”. I’ll show you a picture before making anything.
        </div>
        <div className="bubble note">The chat is switched on in a later update (Phase 4).</div>
      </div>
      <input className="chat-input" placeholder="Chat arrives in a later update" disabled />
    </aside>
  )
}
