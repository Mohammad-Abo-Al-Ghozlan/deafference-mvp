// server/index.ts
import 'dotenv/config';
import express, { Express, Request, Response, NextFunction } from 'express';
import cors, { CorsOptions } from 'cors';
import rateLimit from 'express-rate-limit';
import cameraPermissionRoutes from './routes/cameraPermissionRoutes';
import userRoutes from './routes/userRoutes';
import { prisma } from './lib/prisma';

// ── Fail fast on missing required config ────────────────────────────────────
// Previously the server booted without DATABASE_URL and only 500'd on the first
// DB request. Refuse to start instead, so misconfiguration is obvious.
if (!process.env.DATABASE_URL) {
  console.error('[startup] DATABASE_URL is not set — refusing to start.');
  process.exit(1);
}

const app: Express = express();
// Default to 4000 so the API does not collide with the Next.js dev server (3000).
const PORT = process.env.PORT || 4000;

// ── CORS: allowlist instead of wide-open ────────────────────────────────────
// `cors()` with no options reflected any Origin, which (combined with the API
// being writable) let any site call these endpoints from a victim's browser.
// Set ALLOWED_ORIGINS="https://app.example.com,https://www.example.com" in prod.
const allowedOrigins = (process.env.ALLOWED_ORIGINS || '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

const corsOptions: CorsOptions = {
  origin(origin, callback) {
    // Non-browser clients / same-origin requests have no Origin header.
    if (!origin) return callback(null, true);
    // No allowlist configured (dev): permit, but this must be set in prod.
    if (allowedOrigins.length === 0) return callback(null, true);
    if (allowedOrigins.includes(origin)) return callback(null, true);
    return callback(new Error('Not allowed by CORS'));
  },
  credentials: true,
};

// ── Middleware ──────────────────────────────────────────────────────────────
app.use(express.json({ limit: '100kb' }));
app.use(express.urlencoded({ extended: true, limit: '100kb' }));
app.use(cors(corsOptions));

// Basic rate limiting on the API surface — prevents unbounded row creation and
// brute-forcing. Tune per-route later (e.g. stricter on writes / AI endpoints).
const apiLimiter = rateLimit({
  windowMs: 60_000,
  max: 60,
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    success: false,
    error: { code: 'RATE_LIMITED', message: 'Too many requests, please slow down.' },
  },
});
app.use('/api', apiLimiter);

// Request logging middleware
app.use((req: Request, res: Response, next: NextFunction) => {
  console.log(`${req.method} ${req.path}`);
  next();
});

// ── Routes ──────────────────────────────────────────────────────────────────
app.use('/api/users', userRoutes);
app.use('/api/users', cameraPermissionRoutes);

// Health check endpoint
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// 404 handler
app.use((req: Request, res: Response) => {
  res.status(404).json({
    success: false,
    error: { code: 'NOT_FOUND', message: 'Route not found' },
  });
});

// Error handling middleware
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  if (err && err.message === 'Not allowed by CORS') {
    res.status(403).json({
      success: false,
      error: { code: 'CORS_FORBIDDEN', message: 'Origin not allowed.' },
    });
    return;
  }
  console.error('Unhandled error:', err);
  res.status(500).json({
    success: false,
    error: { code: 'INTERNAL_SERVER_ERROR', message: 'An unexpected error occurred' },
  });
});

// ── Start server + lifecycle ────────────────────────────────────────────────
const server = app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});

server.on('error', (err) => {
  console.error('[startup] failed to bind server:', err);
  process.exit(1);
});

async function shutdown(signal: string): Promise<void> {
  console.log(`${signal} received — shutting down gracefully.`);
  server.close(async () => {
    await prisma.$disconnect();
    process.exit(0);
  });
  // Force-exit if connections don't drain in time.
  setTimeout(() => process.exit(1), 10_000).unref();
}
(['SIGTERM', 'SIGINT'] as const).forEach((sig) =>
  process.on(sig, () => void shutdown(sig))
);

export default app;
