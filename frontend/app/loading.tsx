import React from "react";
import { Fingerprint, Loader2 } from "lucide-react";

export default function GlobalLoading() {
  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col items-center justify-center gap-4 animate-in fade-in duration-200">
      <div className="relative flex items-center justify-center">
        <div className="absolute inset-0 rounded-full bg-primary/25 blur-2xl animate-pulse" />
        <div className="h-24 w-24 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
        <Fingerprint className="h-10 w-10 text-primary absolute animate-pulse" />
      </div>

      <div className="flex flex-col items-center gap-1.5 text-center mt-2">
        <h2 className="text-xl font-bold font-heading tracking-wider">TITLI FORENSICS</h2>
        <p className="text-xs text-muted-foreground font-mono flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> Synchronizing forensic engine...
        </p>
      </div>
    </div>
  );
}
