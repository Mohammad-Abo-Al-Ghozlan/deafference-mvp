import { Keyboard, LifeBuoy, Mic, MousePointerClick } from "lucide-react"
import { Logo } from "./logo"

const STEPS = [
  { icon: Mic, title: "Choose Speak or Type", desc: "Pick how you want to enter your phrase." },
  { icon: Keyboard, title: "Say or type it", desc: "Use a quick phrase or your own words." },
  {
    icon: MousePointerClick,
    title: "Show the sign",
    desc: "Watch the avatar sign it, then replay anytime.",
  },
]

export function SiteFooter() {
  return (
    <footer id="help" className="scroll-mt-20 border-t border-border bg-card/50">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="mx-auto mb-10 max-w-2xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-xs font-medium text-muted-foreground">
            <LifeBuoy className="size-3.5 text-brand-orange" />
            Need help?
          </span>
          <h2 className="mt-4 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
            How Deafference works
          </h2>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, desc }, i) => (
            <div key={title} className="rounded-2xl border border-border bg-card p-5">
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg bg-muted text-foreground">
                  <Icon className="size-4" />
                </span>
                <span className="text-sm font-bold text-brand-red">Step {i + 1}</span>
              </div>
              <h3 className="mt-3 font-semibold text-foreground">{title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{desc}</p>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-col items-center justify-between gap-4 border-t border-border pt-6 sm:flex-row">
          <Logo />
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} Deafference · Demo prototype for accessible
            communication
          </p>
        </div>
      </div>
    </footer>
  )
}
