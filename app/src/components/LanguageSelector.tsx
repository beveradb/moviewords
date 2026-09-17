// app/src/components/LanguageSelector.tsx
import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'
import { LOCALES, localeByCode } from '../i18n/locales'

export default function LanguageSelector() {
  const { locale, setLocale, t } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const current = localeByCode(locale) ?? LOCALES[0]

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={t('languageSwitcher.label')}
        aria-expanded={open}
        title={t('languageSwitcher.current')}
        className="flex h-8 items-center gap-1.5 border-2 border-ink px-2 font-script text-sm font-bold hover:bg-mark"
      >
        <span aria-hidden="true">{current.flag}</span>
        <span className="hidden sm:inline">{current.native}</span>
      </button>
      {open && (
        <div className="absolute top-full end-0 z-50 mt-1 max-h-80 w-64 overflow-y-auto border-2 border-ink bg-card">
          {LOCALES.map((l) => (
            <button
              key={l.code}
              onClick={() => {
                setOpen(false)
                setLocale(l.code)
              }}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-start text-sm hover:bg-mark ${
                l.code === locale ? 'bg-ink text-paper' : ''
              }`}
            >
              <span aria-hidden="true">{l.flag}</span>
              <span className="font-script font-bold">{l.native}</span>
              <span className="ms-auto text-xs text-ink-2">{l.english}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
