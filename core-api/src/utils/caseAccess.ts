import type { AuthenticatedRequest } from "../middleware/auth";

export type CaseAccessRow = {
  id: string;
  createdBy: string | null;
  assignedTo: string | null;
  status?: string;
};

/**
 * Module 6.3 access rules:
 * - Administrator: all cases
 * - Reviewer: assigned to them, or unassigned Flagged (queue pickup)
 * - User (public): only cases they created
 */
export function canAccessCase(
  user: AuthenticatedRequest["user"] | undefined,
  c: CaseAccessRow
): boolean {
  if (!user) return false;
  if (user.role === "Administrator") return true;
  if (user.role === "User") {
    return !!user.userId && c.createdBy === user.userId;
  }
  if (user.role === "Reviewer") {
    if (c.assignedTo === user.userId) return true;
    if (c.status === "Flagged" && !c.assignedTo) return true;
    return false;
  }
  return false;
}

export function canDeleteCase(
  user: AuthenticatedRequest["user"] | undefined,
  c: Pick<CaseAccessRow, "createdBy">
): boolean {
  if (!user) return false;
  if (user.role === "Administrator") return true;
  if (user.role === "User") {
    return !!user.userId && c.createdBy === user.userId;
  }
  return false;
}

export function canReviewCase(user: AuthenticatedRequest["user"] | undefined): boolean {
  return user?.role === "Administrator" || user?.role === "Reviewer";
}

export function accessModeForAuthorRole(
  roleName: string | null | undefined
): "public" | "organizational" {
  return roleName === "User" ? "public" : "organizational";
}
