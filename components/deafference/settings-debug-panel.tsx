"use client"

import { useState } from "react"
import { Gauge, ListChecks, ScanEye, Search, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

const VOCABULARY = ["Hello", "Thank You", "Yes", "No", "Help", "Water", "Hospital"]

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

export function SettingsDebugPanel({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const [confidence, setConfidence] = useState(80)
  const [landmarkOverlay, setLandmarkOverlay] = useState(false)

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
        id="settings-debug"
        role="dialog"
        aria-modal="true"
        aria-label="Settings and debug panel"
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-card shadow-2xl transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">Settings &amp; Debug</h2>
            <p className="text-xs text-muted-foreground">
              Preview panel for recognition tuning
            </p>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close settings" onClick={onClose}>
            <X />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-2">
          <div className="divide-y divide-border">
            {/* Confidence Threshold */}
            <section className="py-5">
              <div className="flex items-center gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                  <Gauge className="size-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-foreground">Confidence Threshold</p>
                  <p className="text-xs text-muted-foreground">
                    Minimum confidence to accept a prediction
                  </p>
                </div>
              </div>

              <div className="mt-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">0%</span>
                  <span className="text-sm font-semibold text-foreground">{confidence}%</span>
                  <span className="text-xs text-muted-foreground">100%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={confidence}
                  onChange={(e) => setConfidence(Number(e.target.value))}
                  aria-label="Confidence threshold"
                  className="mt-2 h-2 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
                />
              </div>
            </section>

            {/* Vocabulary List */}
            <section className="py-5">
              <div className="flex items-center gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                  <ListChecks className="size-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-foreground">Vocabulary List</p>
                  <p className="text-xs text-muted-foreground">Signs currently supported</p>
                </div>
              </div>

              <div className="relative mt-3">
                <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search vocabulary..."
                  aria-label="Search vocabulary"
                  className="pl-9"
                />
              </div>

              <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto rounded-2xl border border-border bg-background/60 p-2">
                {VOCABULARY.map((word) => (
                  <li
                    key={word}
                    className="rounded-xl px-3 py-2 text-sm text-foreground hover:bg-muted"
                  >
                    {word}
                  </li>
                ))}
              </ul>
            </section>

            {/* Landmark Overlay */}
            <section className="py-5">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                    <ScanEye className="size-4" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-foreground">Show Landmark Overlay</p>
                    <p className="text-xs text-muted-foreground">
                      Preview hand landmark points on the camera feed
                    </p>
                  </div>
                </div>
                <Switch
                  label="Show Landmark Overlay"
                  checked={landmarkOverlay}
                  onChange={setLandmarkOverlay}
                />
              </div>
            </section>
          </div>
        </div>
      </aside>
    </>
  )
}
