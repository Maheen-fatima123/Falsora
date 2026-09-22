import React from "react";
import { Fingerprint, Loader2 } from "lucide-react";

export default function DashboardLoading() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-[70vh] gap-4 animate-in fade-in duration-300">
      <div className="relative flex items-center justify-center">
        {/* Glowing aura */}
        <div className="absolute inset-0 rounded-full bg-primary/20 blur-xl animate-pulse" />
        
        {/* Spinning Outer Ring */}
        <div className="h-20 w-20 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
        
        {/* Central Logo */}
        <Fingerprint className="h-9 w-9 text-primary absolute animate-pulse" />
      </div>

      <div className="flex flex-col items-center gap-1.5 text-center">
        <h3 className="text-lg font-semibold font-heading tracking-wide">Titli Forensics Platform</h3>
        <p className="text-xs text-muted-foreground font-mono flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> Loading workspace data...
        </p>
      </div>
    </div>
  );
}
