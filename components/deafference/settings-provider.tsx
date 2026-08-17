"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

export type TextSize = "normal" | "large" | "xlarge"
export type Theme = "light" | "dark"

export type Settings = {
  theme: Theme
  textSize: TextSize
  highContrast: boolean
  reduceMotion: boolean
  alwaysCaptions: boolean
  textOnly: boolean
  largeButtons: boolean
  sound: boolean
  language: string
}

const DEFAULT_SETTINGS: Settings = {
  theme: "light",
  textSize: "normal",
  highContrast: false,
  reduceMotion: false,
  alwaysCaptions: true,
  textOnly: false,
  largeButtons: false,
  sound: true,
  language: "English",
}

type SettingsContextValue = {
  settings: Settings
  update: <K extends keyof Settings>(key: K, value: Settings[K]) => void
  toggleTheme: () => void
  reset: () => void
}

const SettingsContext = createContext<SettingsContextValue | null>(null)

const STORAGE_KEY = "deafference.settings"

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)

  // Hydrate persisted settings on mount (client-only, so SSR markup stays stable
  // and there's no hydration mismatch). Falls back to the OS colour scheme for
  // theme when the user hasn't chosen one yet.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const saved = JSON.parse(raw) as Partial<Settings>
        setSettings((prev) => ({ ...prev, ...saved }))
      } else if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
        setSettings((prev) => ({ ...prev, theme: "dark" }))
      }
    } catch {
      /* ignore malformed storage */
    }
  }, [])

  const update = useCallback<SettingsContextValue["update"]>((key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }, [])

  const toggleTheme = useCallback(() => {
    setSettings((prev) => ({ ...prev, theme: prev.theme === "light" ? "dark" : "light" }))
  }, [])

  const reset = useCallback(() => setSettings(DEFAULT_SETTINGS), [])

  // Reflect settings onto the document root so global CSS can respond, and
  // persist them so preferences survive reloads / navigation.
  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", settings.theme === "dark")
    root.classList.toggle("light", settings.theme === "light")
    root.classList.toggle("hc", settings.highContrast)
    root.classList.toggle("reduce-motion", settings.reduceMotion)
    root.classList.toggle("large-buttons", settings.largeButtons)
    root.classList.toggle("text-only", settings.textOnly)
    root.classList.toggle("captions-on", settings.alwaysCaptions)
    root.dataset.textSize = settings.textSize
    root.dataset.sound = settings.sound ? "on" : "off"
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    } catch {
      /* storage may be unavailable (private mode) — non-fatal */
    }
  }, [settings])

  const value = useMemo(
    () => ({ settings, update, toggleTheme, reset }),
    [settings, update, toggleTheme, reset],
  )

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettings() {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error("useSettings must be used within a SettingsProvider")
  return ctx
}
