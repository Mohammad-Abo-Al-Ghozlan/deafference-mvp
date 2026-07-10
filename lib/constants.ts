export const COMPANY_NAME = "Deafference"
export const COMPANY_TAGLINE = "AI speech-to-sign translation for real-world communication"

export const APP_ROUTES = {
  home: "/",
  translate: "/translate",
  history: "/history",
  settings: "/settings",
  about: "/about",
  contact: "/contact",
} as const

export const LANDING_NAV = [
  { label: "Why us", href: "#why-choose-us" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Features", href: "#features" },
  { label: "FAQ", href: "#faq" },
  { label: "Mock Demo", href: "/mock-testing-demo" },
  { label: "State Machine Demo", href: "/enhanced-state-machine-demo" },
  { label: "Components Demo", href: "/components-demo" },
] as const

export const LANDING_METRICS = [
  { value: "< 10s", label: "to get a usable result" },
  { value: "24/7", label: "always-on communication support" },
  { value: "Multilingual", label: "designed for global teams" },
] as const
