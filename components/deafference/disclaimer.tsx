import { Info } from "lucide-react"

export function Disclaimer() {
  return (
    <div className="flex items-start gap-3.5 rounded-2xl border border-brand-orange/30 bg-accent/40 p-4 sm:p-5">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-orange/15 text-brand-red">
        <Info className="size-5" />
      </span>
      <p className="text-sm leading-relaxed text-pretty text-muted-foreground">
        <span className="font-semibold text-foreground">Demo prototype. </span>
        This experience uses fake data and mocked translation/animation logic. It does not
        provide certified sign-language interpretation, medical, or accessibility services.
      </p>
    </div>
  )
}
