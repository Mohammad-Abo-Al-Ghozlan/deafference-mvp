"use client"

import { useEffect } from "react"
import {
  Captions,
  Contrast,
  Moon,
  MousePointerClick,
  RotateCcw,
  Type,
  Volume2,
  Waves,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { LanguageSelector } from "./language-selector"
import { useSettings, type TextSize } from "./settings-provider"

function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card focus-visible:outline-none",
        checked ? "brand-gradient" : "bg-muted",
      )}
    >
      <span
        className={cn(
          "inline-block size-5 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-6" : "translate-x-1",
        )}
      />
    </button>
  )
}

function Row({
  icon,
  title,
  desc,
  children,
}: {
  icon: React.ReactNode
  title: string
  desc: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3.5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
          {icon}
        </span>
        <div>
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="text-xs text-muted-foreground">{desc}</p>
        </div>
      </div>
      {children}
    </div>
  )
}

const TEXT_SIZES: { id: TextSize; label: string }[] = [
  { id: "normal", label: "Normal" },
  { id: "large", label: "Large" },
  { id: "xlarge", label: "Extra Large" },
]

export function AccessibilityPanel({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const { settings, update, reset } = useSettings()

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    if (open) document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-50 bg-foreground/40 backdrop-blur-sm transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        id="accessibility"
        role="dialog"
        aria-modal="true"
        aria-label="Accessibility settings"
        aria-hidden={!open}
        inert={!open}
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-card shadow-2xl transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">Accessibility</h2>
            <p className="text-xs text-muted-foreground">
              Adjust the interface to your needs
            </p>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close settings" onClick={onClose}>
            <X />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-2">
          {/* Text size */}
          <div className="py-3.5">
            <div className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                <Type className="size-4" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">Text size</p>
                <p className="text-xs text-muted-foreground">Make text easier to read</p>
              </div>
            </div>
            <div
              role="radiogroup"
              aria-label="Text size"
              className="mt-3 grid grid-cols-3 gap-1 rounded-xl bg-muted p-1"
            >
              {TEXT_SIZES.map((s) => (
                <button
                  key={s.id}
                  role="radio"
                  aria-checked={settings.textSize === s.id}
                  onClick={() => update("textSize", s.id)}
                  className={cn(
                    "rounded-lg px-2 py-2 text-sm font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                    settings.textSize === s.id
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="divide-y divide-border">
            <Row
              icon={<Moon className="size-4" />}
              title="Dark mode"
              desc="Switch to a dark colour theme"
            >
              <Switch
                label="Dark mode"
                checked={settings.theme === "dark"}
                onChange={(v) => update("theme", v ? "dark" : "light")}
              />
            </Row>
            <Row
              icon={<Contrast className="size-4" />}
              title="High contrast mode"
              desc="Stronger borders and darker text"
            >
              <Switch
                label="High contrast mode"
                checked={settings.highContrast}
                onChange={(v) => update("highContrast", v)}
              />
            </Row>
            <Row
              icon={<Waves className="size-4" />}
              title="Reduce motion"
              desc="Minimize animations"
            >
              <Switch
                label="Reduce motion"
                checked={settings.reduceMotion}
                onChange={(v) => update("reduceMotion", v)}
              />
            </Row>
            <Row
              icon={<Captions className="size-4" />}
              title="Always show captions"
              desc="Keep text captions on screen"
            >
              <Switch
                label="Always show captions"
                checked={settings.alwaysCaptions}
                onChange={(v) => update("alwaysCaptions", v)}
              />
            </Row>
            <Row
              icon={<Type className="size-4" />}
              title="Text-only fallback"
              desc="Prefer large text cards over animation"
            >
              <Switch
                label="Text-only fallback"
                checked={settings.textOnly}
                onChange={(v) => update("textOnly", v)}
              />
            </Row>
            <Row
              icon={<MousePointerClick className="size-4" />}
              title="Large button mode"
              desc="Bigger, easier-to-tap controls"
            >
              <Switch
                label="Large button mode"
                checked={settings.largeButtons}
                onChange={(v) => update("largeButtons", v)}
              />
            </Row>
            <Row
              icon={<Volume2 className="size-4" />}
              title="Sound"
              desc="Play subtle audio cues"
            >
              <Switch
                label="Sound"
                checked={settings.sound}
                onChange={(v) => update("sound", v)}
              />
            </Row>
          </div>

          {/* Language */}
          <div className="py-4">
            <label
              htmlFor="panel-language"
              className="mb-2 block text-sm font-semibold text-foreground"
            >
              Language
            </label>
            <LanguageSelector id="panel-language" />
          </div>
        </div>

        <div className="border-t border-border px-5 py-4">
          <Button variant="outline" onClick={reset} className="w-full">
            <RotateCcw className="size-4" />
            Reset to defaults
          </Button>
        </div>
      </aside>
    </>
  )
}
