import { FORMATS, type FormatId } from '@engine/formats'

export default function FormatTicker({ value, onChange }: { value: FormatId; onChange: (f: FormatId) => void }) {
  return (
    <div className="ticker" role="radiogroup" aria-label="Video shape">
      {(Object.keys(FORMATS) as FormatId[]).map((id) => {
        const f = FORMATS[id]
        return (
          <button
            key={id}
            role="radio"
            aria-checked={value === id}
            className={`tick ${value === id ? 'on' : ''}`}
            onClick={() => onChange(id)}
          >
            <span className={`shape ${id}`} />
            <span>
              <strong>{f.label}</strong>
              <small>{f.subLabel}</small>
            </span>
          </button>
        )
      })}
    </div>
  )
}
