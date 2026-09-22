"use client";

import { useState, useEffect } from "react";
import { Fingerprint, Home, Video, Folder, Settings, ShieldAlert, BarChart3, LogOut } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { fetchApi } from "@/lib/api";

const items = [
  {
    title: "Overview",
    url: "/dashboard",
    icon: Home,
  },
  {
    title: "Cases",
    url: "/dashboard/cases",
    icon: Folder,
  },
  {
    title: "Live Streams",
    url: "/dashboard/streams",
    icon: Video,
  },
  {
    title: "Alerts",
    url: "/dashboard/alerts",
    icon: ShieldAlert,
  },
  {
    title: "Analytics",
    url: "/dashboard/analytics",
    icon: BarChart3,
  },
  {
    title: "Settings",
    url: "/dashboard/settings",
    icon: Settings,
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<{ name: string; email: string; role: string } | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("falsora_user");
      if (stored) {
        setCurrentUser(JSON.parse(stored));
      } else {
        setCurrentUser({ name: "Falsora Admin", email: "admin@falsora.ai", role: "Administrator" });
      }
    } catch (e) {
      setCurrentUser({ name: "Falsora Admin", email: "admin@falsora.ai", role: "Administrator" });
    }
  }, []);

  const handleLogout = async () => {
    try {
      await fetchApi("http://localhost:4000/api/auth/logout", { 
        method: "POST", 
        credentials: "include" 
      });
    } catch (e) {}
    localStorage.removeItem("falsora_user");
    document.cookie = "auth_session=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie = "auth_token=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    window.location.href = "/login";
  };

  // RBAC Menu Filtering per Proposal Scope (§4.1, §6.1)
  const role = currentUser?.role || "Administrator";
  const visibleItems = items.filter((item) => {
    if (role === "User") {
      // Public Verification mode: Overview & Cases only
      return item.title === "Overview" || item.title === "Cases";
    }
    if (role === "Reviewer") {
      // Reviewer mode: all except Settings
      return item.title !== "Settings";
    }
    // Administrator: full access
    return true;
  });

  return (
    <Sidebar className="border-r border-border/50">
      <SidebarHeader className="p-4 flex flex-col gap-1 text-primary border-b border-border/40">
        <div className="flex items-center gap-2">
          <Fingerprint className="h-6 w-6" />
          <span className="font-bold tracking-wider text-lg">FALSORA</span>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground mt-1">
          <span className="truncate max-w-[120px] font-medium text-foreground">{currentUser?.name || "User"}</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary border border-primary/20">
            {role}
          </span>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>
            {role === "User" ? "Public Mode" : role === "Reviewer" ? "Reviewer Portal" : "Admin Workspace"}
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {visibleItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton 
                    isActive={pathname === item.url}
                    render={<Link href={item.url} />}
                    className="hover:-translate-y-0.5 transition-transform duration-200 cursor-pointer"
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4 border-t border-border/40">
        <SidebarMenuButton 
          onClick={handleLogout}
          className="text-red-400 hover:text-red-300 hover:bg-red-500/10 cursor-pointer w-full transition-colors"
        >
          <LogOut className="h-4 w-4" />
          <span>Sign Out</span>
        </SidebarMenuButton>
      </SidebarFooter>
    </Sidebar>
  );
}
