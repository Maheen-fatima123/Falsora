"use client";

import { useState, useEffect } from "react";
import {
  Fingerprint,
  Home,
  Folder,
  Settings,
  ShieldAlert,
  BarChart3,
  LogOut,
  Users,
  Bell,
} from "lucide-react";
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
import { usePathname } from "next/navigation";
import { fetchApi } from "@/lib/api";
import { navForRole, readStoredUser, sidebarLabel } from "@/lib/rbac";

const iconMap = {
  home: Home,
  folder: Folder,
  users: Users,
  alerts: ShieldAlert,
  analytics: BarChart3,
  settings: Settings,
  bell: Bell,
};

export function AppSidebar() {
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<{
    name: string;
    email: string;
    role: string;
  } | null>(null);

  useEffect(() => {
    const stored = readStoredUser();
    if (stored) {
      setCurrentUser({
        name: stored.name,
        email: stored.email,
        role: stored.role,
      });
    } else {
      setCurrentUser({
        name: "Falsora Admin",
        email: "admin@falsora.ai",
        role: "Administrator",
      });
    }
  }, []);

  const handleLogout = async () => {
    try {
      await fetchApi("http://localhost:4000/api/auth/logout", {
        method: "POST",
        credentials: "include",
      });
    } catch (e) {}
    localStorage.removeItem("falsora_user");
    document.cookie =
      "auth_session=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie =
      "auth_token=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    window.location.href = "/login";
  };

  const role = currentUser?.role || "Administrator";
  const visibleItems = navForRole(role);

  const isActive = (url: string) =>
    pathname === url || (url !== "/dashboard/admin" && pathname.startsWith(url + "/"));

  return (
    <Sidebar className="border-r border-border/50">
      <SidebarHeader className="p-4 flex flex-col gap-1 text-primary border-b border-border/40">
        <div className="flex items-center gap-2">
          <Fingerprint className="h-6 w-6" />
          <span className="font-bold tracking-wider text-lg">FALSORA</span>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground mt-1">
          <span className="truncate max-w-[120px] font-medium text-foreground">
            {currentUser?.name || "User"}
          </span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary border border-primary/20">
            {role}
          </span>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>{sidebarLabel(role)}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {visibleItems.map((item) => {
                const Icon = iconMap[item.icon] || Home;
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      isActive={isActive(item.url)}
                      render={<Link href={item.url} />}
                      className="hover:-translate-y-0.5 transition-transform duration-200 cursor-pointer"
                    >
                      <Icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
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
