// Next 16 ships native ESLint flat configs — spread them directly (no FlatCompat).
import coreWebVitals from "eslint-config-next/core-web-vitals"
import typescript from "eslint-config-next/typescript"

const eslintConfig = [
  ...coreWebVitals,
  ...typescript,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "artifacts/**",
      "artifacts_250/**",
      "training/**",
      "**/__pycache__/**",
      "*_backup/**",
      "server/**", // standalone Express API — type-checked via tsc, not next lint
    ],
  },
]

export default eslintConfig
