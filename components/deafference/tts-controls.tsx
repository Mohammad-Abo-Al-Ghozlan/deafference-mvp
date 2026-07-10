"use client"

import { useState, useSyncExternalStore } from "react"
import { motion } from "framer-motion"
import { Square, Volume2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { getServerSnapshot, getSnapshot, setVoice, speak, stop, subscribe } from "@/lib/speech"

export function TTSControls() {
  const state = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  const [notice, setNotice] = useState<string | null>(null)
  // Manual entry for now — once the AI pipeline produces real translations,
  // feed its output in here (e.g. via a `useEffect` calling `setTranslationText`,
  // or by lifting this state up and passing it in as a prop).
  const [translationText, setTranslationText] = useState("")

  const hasText = translationText.trim().length > 0
  const isBusy = state.speaking || state.queue.length > 0

  function handleSpeak() {
    const result = speak(translationText)
    setNotice(
      result.ok
        ? null
        : result.reason === "unsupported"
          ? "Speech synthesis isn't supported in this browser."
          : "There's no translation text to speak yet.",
    )
  }

  function handleStop() {
    stop()
    setNotice(null)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut", delay: 0.14 }}
    >
      <Card className="p-5 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-semibold tracking-[0.22em] text-muted-foreground uppercase">
            Listen
          </p>
          <span className="inline-flex items-center gap-2 rounded-full bg-brand-orange/12 px-3 py-1 text-xs font-semibold text-brand-red">
            <Volume2 className="size-3.5" />
            Text-to-Speech
          </span>
        </div>

        {!state.supported ? (
          <p className="mt-4 rounded-2xl border border-dashed border-border bg-background/60 px-4 py-4 text-sm text-muted-foreground">
            Speech synthesis isn&apos;t supported in this browser. Try a recent version of
            Chrome, Edge, or Safari.
          </p>
        ) : (
          <>
            <div className="mt-4">
              <label
                htmlFor="tts-text"
                className="mb-1.5 block text-xs font-semibold tracking-[0.18em] text-muted-foreground uppercase"
              >
                Translation
              </label>
              <Textarea
                id="tts-text"
                value={translationText}
                onChange={(e) => setTranslationText(e.target.value)}
                placeholder="Type text to speak..."
                rows={3}
              />
            </div>

            <div className="mt-4">
              <label
                htmlFor="tts-voice"
                className="mb-1.5 block text-xs font-semibold tracking-[0.18em] text-muted-foreground uppercase"
              >
                Voice
              </label>
              {state.voices.length === 0 ? (
                <p className="text-sm text-muted-foreground">No voices available yet.</p>
              ) : (
                <div className="relative inline-flex w-full items-center">
                  <select
                    id="tts-voice"
                    aria-label="Select voice"
                    value={state.voiceURI ?? ""}
                    onChange={(e) => setVoice(e.target.value || null)}
                    className="h-10 w-full cursor-pointer appearance-none rounded-xl border border-border bg-background px-3 pr-8 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  >
                    {state.voices.map((voice) => (
                      <option key={voice.voiceURI} value={voice.voiceURI}>
                        {voice.name} ({voice.lang})
                      </option>
                    ))}
                  </select>
                  <svg
                    className="pointer-events-none absolute right-3 size-3.5 text-muted-foreground"
                    viewBox="0 0 12 12"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 4.5 6 7.5 9 4.5"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
              )}
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <Button className="h-11 rounded-full" onClick={handleSpeak} disabled={!hasText}>
                <Volume2 className="size-4" />
                Speak Translation
              </Button>
              <Button
                variant="outline"
                className="h-11 rounded-full"
                onClick={handleStop}
                disabled={!isBusy}
              >
                <Square className="size-4" />
                Stop
              </Button>
            </div>

            {notice && <p className="mt-3 text-xs text-muted-foreground">{notice}</p>}

            {(state.current || state.queue.length > 0) && (
              <div className="mt-4 space-y-2">
                {state.current && (
                  <p className="text-xs text-muted-foreground">
                    <span className="font-semibold text-foreground">Speaking now:</span>{" "}
                    {state.current.text}
                  </p>
                )}
                {state.queue.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold tracking-[0.18em] text-muted-foreground uppercase">
                      Queued ({state.queue.length})
                    </p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {state.queue.map((item) => (
                        <Badge key={item.id} className="max-w-[12rem] truncate">
                          {item.text}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </Card>
    </motion.div>
  )
}
