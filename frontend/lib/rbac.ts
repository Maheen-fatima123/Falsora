/** Role-based access helpers for the Falsora dashboard. */

export type FalsoraRole = "Administrator" | "Reviewer" | "User";

export type NavItem = {
  title: string;
  url: string;
  icon: "home" | "folder" | "users" | "alerts" | "analytics" | "settings" | "bell";
};

export function roleHome(role: string | undefined | null): string {
  switch (role) {
    case "Reviewer":
      return "/dashboard/reviewer";
    case "User":
      return "/dashboard/user";
    case "Administrator":
    default:
      return "/dashboard/admin";
  }
}

/** Nav items shown in the sidebar for each role. */
export function navForRole(role: string | undefined | null): NavItem[] {
  switch (role) {
    case "Reviewer":
      return [
        { title: "My Queue", url: "/dashboard/reviewer", icon: "home" },
        { title: "My Cases", url: "/dashboard/cases", icon: "folder" },
        { title: "Alerts", url: "/dashboard/alerts", icon: "alerts" },
        { title: "Analytics", url: "/dashboard/analytics", icon: "analytics" },
      ];
    case "User":
      return [
        { title: "Check Image", url: "/dashboard/user", icon: "home" },
        { title: "My Submissions", url: "/dashboard/cases", icon: "folder" },
        { title: "My Notifications", url: "/dashboard/alerts", icon: "bell" },
      ];
    case "Administrator":
    default:
      return [
        { title: "Overview", url: "/dashboard/admin", icon: "home" },
        { title: "All Cases", url: "/dashboard/cases", icon: "folder" },
        { title: "Users", url: "/dashboard/settings", icon: "users" },
        { title: "Analytics", url: "/dashboard/analytics", icon: "analytics" },
        { title: "Alerts", url: "/dashboard/alerts", icon: "alerts" },
        { title: "Settings", url: "/dashboard/settings", icon: "settings" },
      ];
  }
}

export function sidebarLabel(role: string | undefined | null): string {
  switch (role) {
    case "Reviewer":
      return "Reviewer Portal";
    case "User":
      return "Simple Check";
    default:
      return "Control Center";
  }
}

/**
 * Paths each role may open. Anything under an allowed prefix is OK
 * (e.g. /dashboard/cases/:id). Role homes are always allowed.
 */
export function canAccessPath(role: string | undefined | null, pathname: string): boolean {
  const home = roleHome(role);
  if (pathname === home || pathname === "/dashboard") return true;

  const allowedPrefixes: string[] = (() => {
    switch (role) {
      case "Reviewer":
        return ["/dashboard/reviewer", "/dashboard/cases", "/dashboard/alerts", "/dashboard/analytics"];
      case "User":
        return ["/dashboard/user", "/dashboard/cases", "/dashboard/alerts"];
      case "Administrator":
      default:
        return [
          "/dashboard/admin",
          "/dashboard/cases",
          "/dashboard/settings",
          "/dashboard/analytics",
          "/dashboard/alerts",
          "/dashboard/streams",
        ];
    }
  })();

  return allowedPrefixes.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
}

export function canDeleteCases(role: string | undefined | null): boolean {
  return role === "Administrator" || role === "User";
}

export function canAssignReviewer(role: string | undefined | null): boolean {
  return role === "Administrator";
}

export function canReviewCase(role: string | undefined | null): boolean {
  return role === "Reviewer" || role === "Administrator";
}

/** Permission check using JWT/localStorage `permissions` array when present. */
export function hasPermission(
  user: { role?: string; permissions?: string[] } | null | undefined,
  permission: string
): boolean {
  if (!user) return false;
  if (Array.isArray(user.permissions) && user.permissions.length > 0) {
    return user.permissions.includes(permission);
  }
  // Fallback by role when older sessions lack permissions[]
  switch (user.role) {
    case "Administrator":
      return true;
    case "Reviewer":
      return ["cases:read", "cases:review", "analytics:read"].includes(permission);
    case "User":
      return ["cases:read", "cases:write", "cases:delete"].includes(permission);
    default:
      return false;
  }
}

export function accessMode(role: string | undefined | null): "public" | "organizational" {
  return role === "User" ? "public" : "organizational";
}

export function readStoredUser(): {
  id?: string;
  name: string;
  email: string;
  role: FalsoraRole | string;
  permissions?: string[];
  mode?: string;
} | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("falsora_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
