"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Moon, Sun } from "lucide-react";

const routeTitleMap: Record<string, { title: string; subtitle: string }> = {
  "/dashboard": { title: "Overview", subtitle: "System health and recent forensic activity." },
  "/dashboard/cases": { title: "Cases", subtitle: "Manage and review all forensic investigations." },
  "/dashboard/streams": { title: "Live Streams", subtitle: "Real-time deepfake and manipulation monitoring." },
  "/dashboard/alerts": { title: "System Alerts", subtitle: "Notifications and critical system events." },
  "/dashboard/analytics": { title: "Analytics", subtitle: "Platform usage, accuracy metrics, and detection trends." },
  "/dashboard/settings": { title: "Settings", subtitle: "Configure your forensic platform preferences." },
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { setTheme, theme } = useTheme();
  const pathname = usePathname();

  const getPageInfo = () => {
    if (routeTitleMap[pathname]) return routeTitleMap[pathname];
    if (pathname.startsWith("/dashboard/cases/")) {
      return { title: "Case Details", subtitle: "Forensic analysis and deepfake inspection." };
    }
    return { title: "Titli Forensics Platform", subtitle: "Advanced Deepfake Detection" };
  };

  const currentPage = getPageInfo();

  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full bg-background overflow-hidden relative">
        {/* Subtle background gradient */}
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/5 via-background to-background" />

        <AppSidebar />
        
        <main className="flex-1 flex flex-col min-w-0">
          <header className="flex h-14 items-center gap-4 border-b border-border/50 bg-background/80 px-6 backdrop-blur z-10 sticky top-0">
            <SidebarTrigger />
            <div className="h-6 w-px bg-border/60 mx-2" />
            <div className="flex-1 flex flex-col justify-center">
              <h1 className="text-sm font-semibold font-heading leading-tight">{currentPage.title}</h1>
              <p className="text-[11px] text-muted-foreground leading-tight">{currentPage.subtitle}</p>
            </div>
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              >
                <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
                <span className="sr-only">Toggle theme</span>
              </Button>
            </div>
          </header>
          
          <div className="flex-1 p-6 overflow-auto">
            <div className="mx-auto max-w-7xl w-full">
              {children}
            </div>
          </div>
        </main>
      </div>
    </SidebarProvider>
  );
}
