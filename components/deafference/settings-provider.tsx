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

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)

  const update = useCallback<SettingsContextValue["update"]>((key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }, [])

  const toggleTheme = useCallback(() => {
    setSettings((prev) => ({ ...prev, theme: prev.theme === "light" ? "dark" : "light" }))
  }, [])

  const reset = useCallback(() => setSettings(DEFAULT_SETTINGS), [])

  // Reflect settings onto the document root so global CSS can respond.
  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", settings.theme === "dark")
    root.classList.toggle("light", settings.theme === "light")
    root.classList.toggle("hc", settings.highContrast)
    root.classList.toggle("reduce-motion", settings.reduceMotion)
    root.dataset.textSize = settings.textSize
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
