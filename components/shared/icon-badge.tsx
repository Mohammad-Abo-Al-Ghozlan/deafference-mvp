import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface IconBadgeProps {
  icon: LucideIcon
  /** "tint" = brand-tinted chip (default), "solid" = theme-inverted chip for emphasis */
  variant?: "tint" | "solid"
  /** "default" = 44px container / 20px icon, "compact" = 40px container / 16px icon for nested/secondary cards */
  size?: "default" | "compact"
  className?: string
}

/**
 * Shared icon container used across every landing page section. Standardizes
 * dimensions, radius, and background so icon chips read as one consistent
 * design system instead of each section hand-rolling its own variant.
 */
export function IconBadge({ icon: Icon, variant = "tint", size = "default", className }: IconBadgeProps) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center",
        size === "default" ? "size-11 rounded-2xl" : "size-10 rounded-xl",
        variant === "tint" ? "bg-brand-orange/12 text-brand-red" : "bg-foreground text-background",
        className,
      )}
    >
      <Icon className={size === "default" ? "size-5" : "size-4"} />
    </div>
  )
}
