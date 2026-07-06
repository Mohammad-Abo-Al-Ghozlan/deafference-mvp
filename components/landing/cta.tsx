"use client"

import { motion } from "framer-motion"
import { ArrowRight, Mail } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"

export function CTA() {
  return (
    <section id="cta" className="py-24 sm:py-28">
      <Container>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
        >
          <Card className="relative overflow-hidden border-foreground/10 bg-foreground p-8 text-background sm:p-10 lg:p-12">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(255,188,77,0.2),_transparent_35%),radial-gradient(circle_at_bottom_left,_rgba(255,92,61,0.18),_transparent_42%)]" />
            <div className="relative grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
              <div>
                <p className="text-sm font-medium tracking-[0.24em] text-background/70 uppercase">
                  Start here
                </p>
                <h2 className="mt-4 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
                  Ship the landing page now and keep the product surface ready for what comes next.
                </h2>
                <p className="mt-4 max-w-2xl text-base leading-8 text-background/75">
                  Deafference can grow into dashboard, pricing, auth, and documentation pages without
                  a redesign. The structure is already in place.
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row lg:justify-end">
                <a
                  href="mailto:hello@deafference.ai"
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-background px-6 text-base font-semibold text-foreground transition-colors hover:bg-background/90"
                >
                  <Mail className="size-4" />
                  Contact us
                </a>
                <a
                  href="#top"
                  className="inline-flex h-12 items-center justify-center rounded-full border border-background/20 px-6 text-base font-semibold text-background transition-colors hover:bg-background/10"
                >
                  Back to top
                  <ArrowRight className="ml-2 size-4" />
                </a>
              </div>
            </div>
          </Card>
        </motion.div>
      </Container>
    </section>
  )
}
