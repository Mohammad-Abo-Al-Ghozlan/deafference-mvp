export type CategoryId =
  | "Restaurant"
  | "Healthcare"
  | "Reception"
  | "Education"
  | "General"

export type Status =
  | "idle"
  | "listening"
  | "understanding"
  | "preparing"
  | "signing"
  | "complete"

export const PIPELINE_STEPS = [
  "Listening",
  "Understanding",
  "Preparing Sign",
  "Showing Animation",
  "Complete",
] as const

/** Human-friendly badge label for each status. */
export const STATUS_LABEL: Record<Status, string> = {
  idle: "Ready",
  listening: "Listening",
  understanding: "Understanding",
  preparing: "Preparing sign",
  signing: "Signing",
  complete: "Complete",
}

/** Index into PIPELINE_STEPS for a given status (-1 when idle). */
export const STATUS_STEP: Record<Status, number> = {
  idle: -1,
  listening: 0,
  understanding: 1,
  preparing: 2,
  signing: 3,
  complete: 4,
}

export type TranslationResult = {
  original: string
  simplified: string
  matchedSign: string
  confidence: number
  category: CategoryId
  animationStatus: string
}

export type PhraseGroup = {
  id: CategoryId
  label: string
  phrases: string[]
}

export const CATEGORIES: { id: CategoryId; label: string }[] = [
  { id: "Restaurant", label: "Restaurant" },
  { id: "Healthcare", label: "Healthcare" },
  { id: "Reception", label: "Reception" },
  { id: "Education", label: "Education" },
  { id: "General", label: "General" },
]

export const QUICK_PHRASES: PhraseGroup[] = [
  {
    id: "Restaurant",
    label: "Restaurant",
    phrases: [
      "Hello",
      "I need water",
      "I want to order",
      "Please repeat",
      "Thank you",
      "Yes",
      "No",
      "I need help",
      "Where is the bathroom?",
      "How much does this cost?",
      "I am allergic",
      "Please call someone",
    ],
  },
  {
    id: "Healthcare",
    label: "Healthcare",
    phrases: [
      "Hello",
      "I need a doctor",
      "I am in pain",
      "Please repeat",
      "I need help",
      "Yes",
      "No",
      "I feel dizzy",
      "Where is the restroom?",
      "I take medication",
      "I am allergic",
      "Please call my family",
    ],
  },
  {
    id: "Reception",
    label: "Reception",
    phrases: [
      "Hello",
      "I have an appointment",
      "I am here to check in",
      "Please repeat",
      "Thank you",
      "Yes",
      "No",
      "I need help",
      "Where do I wait?",
      "Can you write it down?",
      "I need a form",
      "Please call someone",
    ],
  },
  {
    id: "Education",
    label: "Education",
    phrases: [
      "Hello",
      "I have a question",
      "Please repeat",
      "I do not understand",
      "Thank you",
      "Yes",
      "No",
      "I need help",
      "Can you slow down?",
      "Where is my classroom?",
      "Please write it down",
      "May I leave?",
    ],
  },
  {
    id: "General",
    label: "General",
    phrases: [
      "Hello",
      "Thank you",
      "Please repeat",
      "Yes",
      "No",
      "I need help",
      "I do not understand",
      "Where is the bathroom?",
      "How much does this cost?",
      "Please wait",
      "Nice to meet you",
      "Goodbye",
    ],
  },
]

/** Known high-confidence phrase matches, keyed by a normalized string. */
const KNOWN: Record<
  string,
  { simplified: string; matchedSign: string; confidence: number; category: CategoryId }
> = {
  "i need water": {
    simplified: "I need water",
    matchedSign: "I need water",
    confidence: 96,
    category: "Restaurant",
  },
  "i need a doctor": {
    simplified: "I need doctor",
    matchedSign: "I need a doctor",
    confidence: 94,
    category: "Healthcare",
  },
  "please repeat": {
    simplified: "Please repeat",
    matchedSign: "Please repeat",
    confidence: 98,
    category: "General",
  },
  hello: {
    simplified: "Hello",
    matchedSign: "Hello",
    confidence: 99,
    category: "General",
  },
  "thank you": {
    simplified: "Thank you",
    matchedSign: "Thank you",
    confidence: 99,
    category: "General",
  },
  yes: { simplified: "Yes", matchedSign: "Yes", confidence: 99, category: "General" },
  no: { simplified: "No", matchedSign: "No", confidence: 99, category: "General" },
  "i need help": {
    simplified: "I need help",
    matchedSign: "I need help",
    confidence: 97,
    category: "General",
  },
  "where is the bathroom?": {
    simplified: "Where bathroom?",
    matchedSign: "Where is the bathroom",
    confidence: 95,
    category: "General",
  },
  "how much does this cost?": {
    simplified: "How much cost?",
    matchedSign: "How much does this cost",
    confidence: 93,
    category: "Restaurant",
  },
  "i am allergic": {
    simplified: "I allergic",
    matchedSign: "I am allergic",
    confidence: 95,
    category: "Healthcare",
  },
  "please call someone": {
    simplified: "Please call someone",
    matchedSign: "Please call someone",
    confidence: 96,
    category: "General",
  },
}

const FILLER_WORDS = new Set(["a", "an", "the", "to", "of", "please", "just", "really"])

function normalize(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, " ")
}

function simplify(text: string): string {
  const cleaned = text.trim().replace(/\s+/g, " ")
  if (!cleaned) return ""
  const words = cleaned.split(" ")
  const kept = words.filter((w, i) => {
    // keep leading "please" for politeness, drop other filler mid-sentence
    if (i === 0) return true
    return !FILLER_WORDS.has(w.toLowerCase().replace(/[.,!?]/g, ""))
  })
  const result = kept.join(" ")
  return result.charAt(0).toUpperCase() + result.slice(1)
}

/**
 * Fake/mocked translation. Returns a plausible result with no real ML.
 */
export function translate(input: string, activeCategory: CategoryId): TranslationResult {
  const trimmed = input.trim()
  const key = normalize(trimmed)
  const known = KNOWN[key]

  if (known) {
    return {
      original: trimmed,
      simplified: known.simplified,
      matchedSign: known.matchedSign,
      confidence: known.confidence,
      category: activeCategory === "General" ? known.category : activeCategory,
      animationStatus: "Ready to replay",
    }
  }

  const simplified = simplify(trimmed)
  // Deterministic pseudo-confidence based on length so it feels stable per phrase.
  const base = 88
  const variance = (trimmed.length * 7) % 9
  const confidence = Math.min(97, base + variance)

  return {
    original: trimmed,
    simplified,
    matchedSign: simplified,
    confidence,
    category: activeCategory,
    animationStatus: "Ready to replay",
  }
}
