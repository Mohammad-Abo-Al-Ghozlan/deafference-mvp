# Deafference: Speech-to-Sign MVP

Deafference is a modern, responsive web application MVP designed to bridge the communication gap between hearing individuals and the Deaf/Hard-of-Hearing (DHH) community. The application translates spoken speech or typed text into simplified, high-confidence sign language phrases with interactive visual support.

---

## 🚀 Key Features

- **Dual Input Modes**: Use voice recognition (Speech-to-Text) or manual typing to draft messages.
- **Interactive Sign Language Avatar**: A simulated signing avatar interface that showcases visual translations, with support for replay and detailed text view.
- **Speech-to-Sign Pipeline**: A real-time visual step indicator displaying the translation lifecycle:
  `Listening` ➔ `Understanding` ➔ `Preparing Sign` ➔ `Showing Animation` ➔ `Complete`.
- **Pre-Categorized Quick Phrases**: Instant access to context-specific, high-frequency phrases tailored for:
  - 🍽️ **Restaurant**: Ordering, requesting water, allergen warnings.
  - 🏥 **Healthcare**: Patient-doctor interactions, reporting pain, requesting help.
  - 🛎️ **Reception**: Checking in, asking for directions, waiting room guidance.
  - 🎓 **Education**: Classroom questions, requesting clarifications.
  - 🌐 **General**: Everyday greetings, polite requests.
- **Accessibility Customization**:
  - Adjustable font sizes (Normal, Large, Extra Large).
  - Configurable speech-to-text response rates.
  - Toggleable high contrast and dark mode.
  - Sound effects for state transitions.

---

## 🛠️ Technology Stack

- **Framework**: [Next.js](https://nextjs.org/) (v16) with App Router
- **Core Library**: [React 19](https://react.dev/) & [TypeScript](https://www.typescriptlang.org/)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/) & [PostCSS](https://postcss.org/)
- **Animations**: [Framer Motion](https://www.framer.com/motion/) (for smooth, fluid transitions and UI alerts)
- **UI Components**: [Base UI](https://base-ui.com/) & custom tailwind-designed components
- **Icons**: [Lucide React](https://lucide.dev/)

---

## 📁 Project Structure

```text
├── app/                  # Next.js App Router (Layouts, pages, styles)
│   ├── globals.css       # Core design system and CSS classes
│   ├── layout.tsx        # Base root layout
│   └── page.tsx          # Main entry page calling DeafferenceApp
├── components/           # Reusable UI components
│   ├── deafference/      # Core logic and sub-components for the translation flow
│   │   ├── accessibility-panel.tsx # Custom accessibility control interface
│   │   ├── avatar-preview.tsx     # Sign language avatar visualization wrapper
│   │   ├── data.ts                # Mock dictionaries, categorization, translation engine
│   │   ├── deafference-app.tsx    # Primary controller component orchestrating the MVP
│   │   ├── input-panel.tsx        # Voice & manual input controller
│   │   ├── pipeline.tsx           # Progress and status step indicator
│   │   ├── quick-phrases.tsx      # Multi-category quick-selection panel
│   │   └── ...                    # Header, Footer, Hero, Disclaimer, and auxiliary files
│   └── ui/               # Standard UI block components (buttons, badges, dialogs)
├── public/               # Static assets (images, icons)
├── package.json          # Dependency definition
└── tsconfig.json         # TypeScript configuration
```

---

## ⚙️ Setup and Installation

### Prerequisites

Make sure you have [Node.js](https://nodejs.org/) installed (v18+ recommended).

### Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/ghozlan-mo/deafference-speech-to-sign-mvp.git
   cd deafference-speech-to-sign-mvp
   ```

2. **Install Dependencies**
   ```bash
   npm install
   ```

3. **Run the Development Server**
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) in your browser to see the application.

4. **Build for Production**
   ```bash
   npm run build
   npm run start
   ```

---

## 🔌 Backend API

A small Express + Prisma (PostgreSQL) API lives in [`server/`](server/) and is
separate from the Next.js frontend.

- **Frontend (Next.js):** port **3000** (`npm run dev`)
- **API (Express):** port **4000** (`npm run server:dev`)

They use different ports so both can run at the same time.

### Database setup

1. Copy the environment template and adjust the connection string for your
   local Postgres:
   ```bash
   cp .env.example .env
   # then edit DATABASE_URL in .env if your Postgres user/password/db differ
   ```
   `.env.example` documents the format:
   `postgresql://USER:PASSWORD@HOST:PORT/DATABASE?schema=SCHEMA`.

2. Create the tables and generate the Prisma client:
   ```bash
   npx prisma migrate dev --name init
   npx prisma generate
   ```
   This creates the `User` and `CameraPermission` tables.

3. Start the API:
   ```bash
   npm run server:dev
   ```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness check |
| `POST` | `/api/users` | Create a user (`email` required, `name` optional) → **201** |
| `POST` | `/api/users/camera-permission` | Create **or** update a user's camera permission (upsert) → **200** |
| `GET`  | `/api/users/camera-permission/:userId` | Read a user's camera permission |

`CameraPermission.userId` is a foreign key to `User.id` (both integers), so a
user must exist before a permission can be set.

### Full flow: zero → create user → set camera permission → read it back

```bash
API=http://localhost:4000

# 1. Create a user and capture the generated integer id
USER_ID=$(curl -s -X POST "$API/api/users" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","name":"Alice"}' \
  | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)

# 2. Set that user's camera permission
curl -X POST "$API/api/users/camera-permission" \
  -H "Content-Type: application/json" \
  -d "{\"userId\":$USER_ID,\"status\":\"granted\"}"

# 3. Read the permission back
curl "$API/api/users/camera-permission/$USER_ID"
```

See [`CURL_EXAMPLES.md`](CURL_EXAMPLES.md) for every endpoint and error case,
and run [`test-api.sh`](test-api.sh) to exercise the whole suite end-to-end.

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to open an issue or submit a pull request.

## 📄 License

This project is private and proprietary. All rights reserved.
