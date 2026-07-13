"use client"

import { motion } from "framer-motion"
import { ArrowRight, Sparkles } from "lucide-react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { APP_ROUTES, LANDING_METRICS } from "@/lib/constants"

const stats = [
  "Real-time translation pipeline",
  "Marketing and product surfaces stay separate",
  "Built to scale into dashboard, pricing, and auth",
]

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden pt-16 sm:pt-24">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[36rem] bg-[radial-gradient(circle_at_top,_rgba(240,165,28,0.18),_transparent_45%),linear-gradient(to_bottom,_rgba(255,255,255,0.92),_rgba(255,255,255,0))]" />
      <Container>
        <div className="grid items-center gap-12 lg:grid-cols-[1.15fr_0.85fr] lg:gap-16">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          >
            <Badge className="border-brand-orange/30 bg-background/90 px-3 py-1.5 text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
              <Sparkles className="mr-2 size-3.5 text-brand-orange" />
              AI communication infrastructure
            </Badge>

            <h1 className="mt-6 max-w-3xl text-5xl font-semibold tracking-tight text-balance text-foreground sm:text-6xl lg:text-7xl">
              Deafference turns spoken words into fluid, accessible sign language.
            </h1>

            <p className="mt-6 max-w-2xl text-lg leading-8 text-pretty text-muted-foreground sm:text-xl">
              We listen to speech, understand what&apos;s being said, and translate it into clear,
              sign-ready visuals in real time — breaking communication barriers as the conversation happens.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                href={APP_ROUTES.translate}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-foreground px-6 text-base font-semibold text-background transition-transform hover:scale-[1.02]"
              >
                <ArrowRight className="size-4" />
                Get Started
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex h-12 items-center justify-center rounded-full border border-border bg-background px-6 text-base font-medium text-foreground shadow-sm transition-colors hover:bg-muted"
              >
                See the workflow
              </a>
            </div>

            <div className="mt-10 grid gap-3 sm:grid-cols-3">
              {LANDING_METRICS.map((metric) => (
                <Card key={metric.label} className="p-4">
                  <p className="text-2xl font-semibold tracking-tight text-foreground">
                    {metric.value}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">{metric.label}</p>
                </Card>
              ))}
            </div>

            <div className="mt-8 flex flex-wrap gap-3 text-sm text-muted-foreground">
              {stats.map((item) => (
                <span key={item} className="rounded-full border border-border bg-background px-3 py-2">
                  {item}
                </span>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, ease: "easeOut", delay: 0.08 }}
          >
            <Card className="relative overflow-hidden border-border/80 bg-card/90 p-6 shadow-[0_30px_80px_-28px_rgba(0,0,0,0.24)] sm:p-8">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(224,120,60,0.18),_transparent_40%),radial-gradient(circle_at_bottom_left,_rgba(216,70,30,0.16),_transparent_42%)]" />
              <div className="relative space-y-5">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-muted-foreground">Live product preview</p>
                  <span className="rounded-full bg-foreground px-3 py-1 text-xs font-semibold text-background">
                    Pipeline ready
                  </span>
                </div>
                <div className="rounded-3xl border border-border bg-background p-5">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-xs font-medium tracking-[0.24em] text-muted-foreground uppercase">
                        Input
                      </p>
                      <p className="mt-2 text-lg font-medium text-foreground">I need help at reception.</p>
                    </div>
                    <span className="rounded-full bg-brand-orange/15 px-3 py-1 text-xs font-semibold text-brand-red">
                      Translate
                    </span>
                  </div>
                  <div className="mt-5 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl bg-muted p-4">
                      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                        Output
                      </p>
                      <p className="mt-2 text-sm leading-6 text-foreground">
                        Simplified language, sign-ready phrasing, and accessible animation cues.
                      </p>
                    </div>
                    <div className="rounded-2xl bg-muted p-4">
                      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                        Delivery
                      </p>
                      <p className="mt-2 text-sm leading-6 text-foreground">
                        Independent landing, workflow, and future product pages.
                      </p>
                    </div>
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {[
                    "Landing",
                    "Translation app",
                    "Future products",
                  ].map((item) => (
                    <div key={item} className="rounded-2xl border border-border bg-background px-4 py-3 text-sm font-medium text-foreground">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>
        </div>
      </Container>
    </section>
  )
}
