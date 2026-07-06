"use client"

import { motion } from "framer-motion"
import { BriefcaseBusiness, GraduationCap, HeartHandshake, Users } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"

const useCases = [
  {
    icon: Users,
    title: "Public service desks",
    description: "Support reception, municipal offices, and customer-facing teams that need clarity fast.",
  },
  {
    icon: HeartHandshake,
    title: "Healthcare settings",
    description: "Designed for clinics and urgent care environments where communication quality matters.",
  },
  {
    icon: GraduationCap,
    title: "Education environments",
    description: "Useful for classrooms, student services, and campus support teams.",
  },
  {
    icon: BriefcaseBusiness,
    title: "Enterprise teams",
    description: "Add communication tools into product, ops, and support workflows without redesigning the platform.",
  },
]

export function UseCases() {
  return (
    <section id="use-cases" className="py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="Use cases"
          title="Built for environments where clarity is mission-critical"
          description="The landing page should explain where Deafference creates value before the product suite expands into separate pages."
        />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          className="mt-12 grid gap-4 md:grid-cols-2"
        >
          {useCases.map((item) => {
            const Icon = item.icon
            return (
              <Card key={item.title} className="p-6">
                <div className="flex items-center gap-4">
                  <div className="flex size-12 items-center justify-center rounded-2xl bg-brand-orange/12 text-brand-red">
                    <Icon className="size-5" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-foreground">{item.title}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
                  </div>
                </div>
              </Card>
            )
          })}
        </motion.div>
      </Container>
    </section>
  )
}
