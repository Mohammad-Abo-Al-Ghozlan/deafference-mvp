"use client"

import { Globe } from "lucide-react"
import { useSettings } from "./settings-provider"

export const LANGUAGES = [
  "English",
  "Español",
  "Français",
  "Deutsch",
  "العربية",
  "中文",
]

export function LanguageSelector({ id }: { id?: string }) {
  const { settings, update } = useSettings()

  return (
    <div className="relative inline-flex items-center">
      <Globe className="pointer-events-none absolute left-2.5 size-4 text-muted-foreground" />
      <select
        id={id}
        aria-label="Select language"
        value={settings.language}
        onChange={(e) => update("language", e.target.value)}
        className="h-9 cursor-pointer appearance-none rounded-lg border border-border bg-background py-0 pr-7 pl-8 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        {LANGUAGES.map((lang) => (
          <option key={lang} value={lang}>
            {lang}
          </option>
        ))}
      </select>
      <svg
        className="pointer-events-none absolute right-2.5 size-3.5 text-muted-foreground"
        viewBox="0 0 12 12"
        fill="none"
        aria-hidden="true"
      >
        <path d="M3 4.5 6 7.5 9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}
