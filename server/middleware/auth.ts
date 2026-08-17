// server/middleware/auth.ts
import { Request, Response, NextFunction } from 'express';
import { timingSafeEqual } from 'crypto';

/**
 * Minimal bearer-token guard. Before this, EVERY route was public — anyone could
 * read or overwrite any user's data (IDOR). This closes that hole until a real
 * identity provider (login + session/JWT) is wired up.
 *
 * Behavior:
 *   - `API_ACCESS_TOKEN` set  -> require `Authorization: Bearer <token>`.
 *   - not set, production      -> refuse all requests (500) so it can't ship open.
 *   - not set, development     -> warn and allow (local convenience only).
 *
 * SECURITY TODO (BE-14): this is a shared service-to-service secret, NOT per-user
 * auth. Once users log in, `userId` for camera-permission reads/writes MUST come
 * from the authenticated identity — never trust the userId in the body/params, or
 * the IDOR returns.
 */
function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}

export function requireAuth(req: Request, res: Response, next: NextFunction): void {
  const expected = process.env.API_ACCESS_TOKEN;

  if (!expected) {
    if (process.env.NODE_ENV === 'production') {
      res.status(500).json({
        success: false,
        error: {
          code: 'AUTH_NOT_CONFIGURED',
          message: 'Server authentication is not configured.',
        },
      });
      return;
    }
    console.warn('[auth] API_ACCESS_TOKEN not set — auth is DISABLED (dev only).');
    next();
    return;
  }

  const header = req.header('authorization') || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';

  if (token && safeEqual(token, expected)) {
    next();
    return;
  }

  res.status(401).json({
    success: false,
    error: { code: 'UNAUTHORIZED', message: 'Missing or invalid access token.' },
  });
}
