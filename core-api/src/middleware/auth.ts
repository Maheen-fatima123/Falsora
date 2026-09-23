import type { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET || 'super-secret-key-change-in-prod';

export interface AuthenticatedRequest extends Request {
  user?: {
    userId: string;
    email: string;
    role: string;
  };
}

/**
 * Middleware: verify JWT on every protected route.
 * Reads from the HttpOnly cookie set at login, or an Authorization header
 * (Bearer token) as a fallback for API clients.
 */
export function requireAuth(
  req: AuthenticatedRequest,
  res: Response,
  next: NextFunction
) {
  const token =
    req.cookies?.auth_token ||
    req.headers.authorization?.replace('Bearer ', '');

  if (!token) {
    return res.status(401).json({ success: false, error: 'Unauthenticated' });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET) as {
      userId: string;
      email: string;
      role: string;
    };
    req.user = decoded;
    return next();
  } catch {
    return res.status(401).json({ success: false, error: 'Invalid or expired token' });
  }
}

/**
 * Middleware factory: require a specific role (or one of several roles).
 * Usage: requireRole('Administrator') or requireRole(['Administrator', 'Reviewer'])
 */
export function requireRole(roles: string | string[]) {
  const allowed = Array.isArray(roles) ? roles : [roles];
  return (req: AuthenticatedRequest, res: Response, next: NextFunction) => {
    if (!req.user) {
      return res.status(401).json({ success: false, error: 'Unauthenticated' });
    }
    if (!allowed.includes(req.user.role)) {
      return res.status(403).json({
        success: false,
        error: `Access denied. Required role: ${allowed.join(' or ')}`,
      });
    }
    return next();
  };
}
