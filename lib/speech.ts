/**
 * Text-to-speech service wrapping the browser's Web Speech API
 * (window.speechSynthesis / SpeechSynthesisUtterance).
 *
 * This module owns a single module-level store so any part of the app —
 * UI controls today, an AI translation pipeline later — can call speak()
 * with new text and it will queue/play correctly regardless of caller.
 */

export type SpeechQueueItem = {
  id: string
  text: string
}

export type SpeechState = {
  supported: boolean
  voices: SpeechSynthesisVoice[]
  voiceURI: string | null
  speaking: boolean
  current: SpeechQueueItem | null
  queue: SpeechQueueItem[]
}

export type SpeakResult = { ok: true } | { ok: false; reason: "unsupported" | "empty" }

const initialState: SpeechState = {
  supported: false,
  voices: [],
  voiceURI: null,
  speaking: false,
  current: null,
  queue: [],
}

let state: SpeechState = initialState
let initialized = false
let idCounter = 0

const listeners = new Set<() => void>()

function nextId(): string {
  idCounter += 1
  return `speech-${idCounter}`
}

function isSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window
}

function setState(patch: Partial<SpeechState>) {
  state = { ...state, ...patch }
  listeners.forEach((listener) => listener())
}

function refreshVoices() {
  const voices = window.speechSynthesis.getVoices()
  const voiceURI =
    state.voiceURI && voices.some((v) => v.voiceURI === state.voiceURI)
      ? state.voiceURI
      : voices[0]?.voiceURI ?? null
  setState({ voices, voiceURI })
}

/** Lazily wires up the browser API the first time anything subscribes. */
function ensureInitialized() {
  if (initialized || !isSupported()) return
  initialized = true
  setState({ supported: true })
  refreshVoices()
  window.speechSynthesis.addEventListener("voiceschanged", refreshVoices)
}

function playNext() {
  if (!isSupported()) return
  const [next, ...rest] = state.queue

  if (!next) {
    setState({ current: null, speaking: false })
    return
  }

  setState({ queue: rest, current: next, speaking: true })

  const utterance = new SpeechSynthesisUtterance(next.text)
  const voice = state.voices.find((v) => v.voiceURI === state.voiceURI)
  if (voice) utterance.voice = voice

  utterance.onend = playNext
  utterance.onerror = playNext

  window.speechSynthesis.speak(utterance)
}

/**
 * Speaks `text`. If something is already playing, the text is appended to
 * the queue and played automatically once earlier items finish.
 */
export function speak(text: string): SpeakResult {
  ensureInitialized()
  if (!isSupported()) return { ok: false, reason: "unsupported" }

  const trimmed = text.trim()
  if (!trimmed) return { ok: false, reason: "empty" }

  const item: SpeechQueueItem = { id: nextId(), text: trimmed }
  setState({ queue: [...state.queue, item] })

  if (!state.current) {
    playNext()
  }

  return { ok: true }
}

/** Immediately cancels the current utterance and clears the queue. */
export function stop() {
  if (!isSupported()) return
  setState({ queue: [], current: null, speaking: false })
  window.speechSynthesis.cancel()
}

/** Selects which voice future speak() calls should use. */
export function setVoice(voiceURI: string | null) {
  setState({ voiceURI })
}

export function subscribe(onChange: () => void): () => void {
  ensureInitialized()
  listeners.add(onChange)
  return () => listeners.delete(onChange)
}

export function getSnapshot(): SpeechState {
  return state
}

/** Safe, browser-free snapshot used for the server-rendered pass. */
export function getServerSnapshot(): SpeechState {
  return initialState
}
