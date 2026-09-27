/**
 * Canonical permission names for module 6.1.
 * Seeded into Permission / RolePermission; also used as offline fallback.
 */

export const PERMISSIONS = [
  "cases:read",
  "cases:write",
  "cases:delete",
  "cases:assign",
  "cases:review",
  "users:manage",
  "analytics:read",
  "auth:activity:read",
] as const;

export type PermissionName = (typeof PERMISSIONS)[number];

/** Default grants when DB RolePermission rows are missing. */
export const ROLE_PERMISSIONS: Record<string, PermissionName[]> = {
  User: ["cases:read", "cases:write", "cases:delete"],
  Reviewer: ["cases:read", "cases:review", "analytics:read"],
  Administrator: [...PERMISSIONS],
};

export function permissionsForRole(role: string | undefined | null): PermissionName[] {
  if (!role) return [];
  return ROLE_PERMISSIONS[role] || [];
}
