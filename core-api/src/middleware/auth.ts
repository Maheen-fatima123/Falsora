import type { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import { prisma } from "../db";
import {
  permissionsForRole,
  type PermissionName,
} from "../rbac/permissions";

const JWT_SECRET = process.env.JWT_SECRET || "super-secret-key-change-in-prod";

export interface AuthenticatedRequest extends Request {
  user?: {
    userId: string;
    email: string;
    role: string;
    permissions?: string[];
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
    req.headers.authorization?.replace("Bearer ", "");

  if (!token) {
    return res.status(401).json({ success: false, error: "Unauthenticated" });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET) as {
      userId: string;
      email: string;
      role: string;
      permissions?: string[];
    };
    req.user = decoded;
    return next();
  } catch {
    return res.status(401).json({ success: false, error: "Invalid or expired token" });
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
      return res.status(401).json({ success: false, error: "Unauthenticated" });
    }
    if (!allowed.includes(req.user.role)) {
      return res.status(403).json({
        success: false,
        error: `Access denied. Required role: ${allowed.join(" or ")}`,
      });
    }
    return next();
  };
}

/**
 * Resolve permissions for a role from DB RolePermission, falling back to
 * the static ROLE_PERMISSIONS map when DB is empty or unreachable.
 */
export async function loadPermissionsForRole(roleName: string): Promise<string[]> {
  try {
    const role = await prisma.role.findUnique({
      where: { name: roleName },
      include: { permissions: { include: { permission: true } } },
    });
    const fromDb = role?.permissions.map((rp) => rp.permission.name) || [];
    if (fromDb.length > 0) return fromDb;
  } catch (err) {
    console.warn("Permission DB lookup failed, using static map:", err);
  }
  return permissionsForRole(roleName);
}

/**
 * Middleware factory: require one permission (or any of several).
 * Uses JWT-embedded permissions when present; otherwise loads from role.
 */
export function requirePermission(needed: PermissionName | PermissionName[]) {
  const required = Array.isArray(needed) ? needed : [needed];
  return async (req: AuthenticatedRequest, res: Response, next: NextFunction) => {
    if (!req.user) {
      return res.status(401).json({ success: false, error: "Unauthenticated" });
    }

    let perms = req.user.permissions;
    if (!perms || perms.length === 0) {
      perms = await loadPermissionsForRole(req.user.role);
      req.user.permissions = perms;
    }

    const ok = required.some((p) => perms!.includes(p));
    if (!ok) {
      return res.status(403).json({
        success: false,
        error: `Access denied. Required permission: ${required.join(" or ")}`,
      });
    }
    return next();
  };
}
