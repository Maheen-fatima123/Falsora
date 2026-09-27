"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { readStoredUser, roleHome } from "@/lib/rbac";

/** Legacy /dashboard — bounce to the role-specific home. */
export default function DashboardIndexRedirect() {
  const router = useRouter();

  useEffect(() => {
    const user = readStoredUser();
    router.replace(roleHome(user?.role));
  }, [router]);

  return (
    <div className="text-sm text-muted-foreground py-8 text-center">
      Redirecting to your workspace…
    </div>
  );
}
