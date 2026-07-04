"use client"

import { Navbar } from "./navbar"
import { Hero } from "./hero"
import { WhyChooseUs } from "./why-choose-us"
import { HowItWorks } from "./how-it-works"
import { Features } from "./features"
import { Technology } from "./technology"
import { Performance } from "./performance"
import { UseCases } from "./use-cases"
import { BestConditions } from "./best-conditions"
import { SupportedLanguages } from "./supported-languages"
import { Mission } from "./mission"
import { FAQ } from "./faq"
import { CTA } from "./cta"
import { Footer } from "./footer"

export function LandingPage() {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <Navbar />
      <main>
        <Hero />
        <WhyChooseUs />
        <HowItWorks />
        <Features />
        <Technology />
        <Performance />
        <UseCases />
        <BestConditions />
        <SupportedLanguages />
        <Mission />
        <FAQ />
        <CTA />
      </main>
      <Footer />
    </div>
  )
}
