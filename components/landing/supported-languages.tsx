"use client"

import { motion } from "framer-motion"
import { Globe2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"
import { IconBadge } from "@/components/shared/icon-badge"

const languages = [
  "English",
  "Spanish",
  "French",
  "German",
  "Portuguese",
  "Italian",
  "Japanese",
  "Korean",
  "Mandarin",
  "Arabic",
  "Hindi",
  "ASL-ready phrasing",
]

export function SupportedLanguages() {
  return (
    <section id="supported-languages" className="py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="Supported languages"
          title="Built to expand across languages and regions"
          description="The system starts with a focused core and can grow into a broader multilingual communication platform."
        />

        <div className="mt-12 grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
          >
            <Card className="h-full p-6">
              <IconBadge icon={Globe2} variant="solid" />
              <h3 className="mt-5 text-xl font-semibold text-foreground">
                Localized where it matters, adaptable where it counts.
              </h3>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">
                Future language pages can fit into the same architecture without changing the
                underlying product structure.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Badge>Regional readiness</Badge>
                <Badge>Scalable content</Badge>
                <Badge>Inclusive UX</Badge>
              </div>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut", delay: 0.05 }}
            className="grid grid-cols-2 gap-3 sm:grid-cols-3"
          >
            {languages.map((language) => (
              <Card key={language} className="flex items-center justify-center px-4 py-5 text-center">
                <p className="text-sm font-medium text-foreground">{language}</p>
              </Card>
            ))}
          </motion.div>
        </div>
      </Container>
    </section>
  )
}
