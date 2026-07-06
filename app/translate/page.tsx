import { SettingsProvider } from "@/components/deafference/settings-provider"
import { DeafferenceApp } from "@/components/deafference/deafference-app"

export default function TranslatePage() {
  return (
    <SettingsProvider>
      <DeafferenceApp />
    </SettingsProvider>
  )
}
