import { GraduationCap, HeartPulse, Landmark, UtensilsCrossed } from "lucide-react"

const CASES = [
  {
    icon: UtensilsCrossed,
    title: "Restaurants",
    desc: "Help staff and deaf customers understand each other quickly.",
  },
  {
    icon: HeartPulse,
    title: "Hospitals & Clinics",
    desc: "Support basic communication at reception and triage.",
  },
  {
    icon: GraduationCap,
    title: "Schools",
    desc: "Make classroom instructions easier to access.",
  },
  {
    icon: Landmark,
    title: "Public Services",
    desc: "Improve accessibility at desks, counters, and offices.",
  },
]

export function UseCases() {
  return (
    <section aria-labelledby="use-cases-title">
      <div className="mb-5 text-center">
        <h2
          id="use-cases-title"
          className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl"
        >
          Built for everyday places
        </h2>
        <p className="mx-auto mt-2 max-w-lg text-pretty text-muted-foreground">
          Wherever people need to connect, Deafference makes the first step simple.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CASES.map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="rounded-2xl border border-border bg-card p-5 shadow-sm transition-shadow hover:shadow-md"
          >
            <span className="brand-gradient flex size-11 items-center justify-center rounded-xl text-white shadow-sm">
              <Icon className="size-5" />
            </span>
            <h3 className="mt-4 text-lg font-semibold text-foreground">{title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-pretty text-muted-foreground">
              {desc}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}
