"use client"

import { motion } from "framer-motion"
import { Gauge, ShieldCheck, Zap } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"
import { IconBadge } from "@/components/shared/icon-badge"

const metrics = [
  { value: "< 300ms", label: "to animate core UI transitions" },
  { value: "100%", label: "responsive layouts across breakpoints" },
  { value: "Zero coupling", label: "between landing and translation features" },
]

export function Performance() {
  return (
    <section id="performance" className="py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="Performance"
          title="Fast to scan, fast to extend"
          description="The visual system aims for clarity first, while the architecture keeps runtime concerns simple and separated."
        />

        <div className="mt-12 grid gap-4 lg:grid-cols-[1fr_1.1fr]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
            className="grid gap-4 sm:grid-cols-3 lg:grid-cols-1"
          >
            {metrics.map((metric) => (
              <Card key={metric.label} className="p-6">
                <p className="text-3xl font-semibold tracking-tight text-foreground">{metric.value}</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">{metric.label}</p>
              </Card>
            ))}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut", delay: 0.05 }}
          >
            <Card className="h-full p-6">
              <div className="grid gap-4 sm:grid-cols-3">
                {[
                  { icon: Gauge, title: "Lightweight", text: "Minimal overhead and deliberate surface area." },
                  { icon: Zap, title: "Responsive", text: "Layouts adapt cleanly from mobile to desktop." },
                  { icon: ShieldCheck, title: "Predictable", text: "Reusable primitives reduce visual drift." },
                ].map((item) => {
                  const Icon = item.icon
                  return (
                    <div key={item.title} className="rounded-2xl border border-border bg-muted/30 p-4">
                      <IconBadge icon={Icon} variant="solid" size="compact" />
                      <h3 className="mt-4 text-sm font-semibold text-foreground">{item.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.text}</p>
                    </div>
                  )
                })}
              </div>
            </Card>
          </motion.div>
        </div>
      </Container>
    </section>
  )
}
