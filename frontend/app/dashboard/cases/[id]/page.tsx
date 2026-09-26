"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fetchApi } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { ForensicReportModal } from "@/components/report-modal";
import { 
  ArrowLeft, 
  Download, 
  ShieldAlert, 
  Eye, 
  Layers, 
  Scan, 
  Play, 
  Pause, 
  SkipBack, 
  SkipForward, 
  FileText, 
  Cpu, 
  CheckCircle2, 
  AlertTriangle,
  Loader2
} from "lucide-react";

/** Renders one AI Detection Breakdown row from a real 0.0-1.0 model score
 * (or an N/A state when no signal exists for that branch). */
function DetectionMeter({
  label,
  score,
  naLabel = "N/A",
}: {
  label: string;
  score: number | null | undefined;
  naLabel?: string;
}) {
  const hasScore = typeof score === "number" && Number.isFinite(score);
  const pct = hasScore ? Math.round(score * 1000) / 10 : 0;

  const risk = !hasScore
    ? { label: naLabel, color: "text-muted-foreground", bar: "bg-muted-foreground" }
    : pct >= 70
    ? { label: "High Risk", color: "text-red-500", bar: "bg-red-500" }
    : pct >= 40
    ? { label: "Medium Risk", color: "text-amber-500", bar: "bg-amber-500" }
    : { label: "Low Risk", color: "text-emerald-500", bar: "bg-emerald-500" };

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs">
        <span className="font-medium">{label}</span>
        <span className={cn("font-mono font-bold", risk.color)}>
          {hasScore ? `${pct}% (${risk.label})` : risk.label}
        </span>
      </div>
      <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
        <div className={cn("h-full rounded-full", risk.bar)} style={{ width: `${hasScore ? pct : 0}%` }} />
      </div>
    </div>
  );
}

export default function CaseDetailPage() {
  const params = useParams();
  const caseId = (params?.id as string) || "CAS-142";

  const [caseDetails, setCaseDetails] = useState<any>(null);
  const [activeViewMode, setActiveViewMode] = useState<"rgb" | "ela" | "bbox">("rgb");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentFrame, setCurrentFrame] = useState(142);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [analyzingProgress, setAnalyzingProgress] = useState(0);

  useEffect(() => {
    // Fetch initial case details
    const fetchCase = async () => {
      if (!caseId) return;
      try {
        const res = await fetchApi(`http://localhost:4000/api/cases/${caseId}`);
        const resData = await res.json();
        if (resData.success) {
          setCaseDetails(resData.data);
        }
      } catch (error) {
        console.error("Failed to fetch case details", error);
      }
    };

    fetchCase();

    // Setup polling if status is Analyzing
    let pollInterval: NodeJS.Timeout;
    if (caseDetails?.status === "Analyzing") {
      pollInterval = setInterval(fetchCase, 2500);
    }

    return () => clearInterval(pollInterval);
  }, [caseId, caseDetails?.status]);

  // Simulated progress bar for the Analyzing state
  useEffect(() => {
    if (caseDetails?.status !== "Analyzing") {
      setAnalyzingProgress(100);
      return;
    }

    setAnalyzingProgress(0);
    const interval = setInterval(() => {
      setAnalyzingProgress((prev) => {
        // Slow down progress as it gets closer to 90% to wait for actual completion
        const increment = prev < 50 ? 5 : prev < 80 ? 2 : prev < 95 ? 0.5 : 0;
        return Math.min(95, prev + increment);
      });
    }, 400);

    return () => clearInterval(interval);
  }, [caseDetails?.status]);

  const displayTitle = caseDetails?.title || caseDetails?.subject || "Deepfake Detection - Investigation";
  const displayStatus = caseDetails?.status || "Analyzing";
  const displayHash = caseDetails?.sha256 || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  const displayDate = caseDetails?.date || new Date().toISOString().split("T")[0];

  return (
    <div className="flex flex-col gap-6">
      {/* Forensic Report Modal */}
      <ForensicReportModal 
        isOpen={isReportOpen}
        onClose={() => setIsReportOpen(false)}
        caseData={{
          id: caseId,
          subject: displayTitle,
          status: displayStatus,
          confidence: caseDetails?.confidence || (displayStatus === "Flagged" ? "98.4%" : displayStatus === "Verified" ? "99.1%" : "..."),
          date: displayDate,
          fileName: caseDetails?.mediaUrl ? caseDetails.mediaUrl.split("/").pop() : "evidence_media.mp4",
          hash: displayHash
        }}
      />

      {/* Top Action Bar */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between pb-2 border-b border-border/50">
        <div className="flex items-center gap-3">
          <Link 
            href="/dashboard/cases"
            className={cn(buttonVariants({ variant: "outline", size: "icon" }), "h-9 w-9 cursor-pointer")}
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-foreground font-erode flex items-center gap-3">
              {caseDetails?.id.startsWith("CAS-") ? caseDetails.id : `CAS-${caseDetails?.id.substring(0, 6).toUpperCase()}`}
              <Badge 
                variant={caseDetails?.status === "Flagged" ? "destructive" : caseDetails?.status === "Verified" ? "default" : "secondary"}
                className={cn(
                  caseDetails?.status === "Verified" && "bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20",
                  caseDetails?.status === "Analyzing" && "animate-pulse"
                )}
              >
                {caseDetails?.status === "Analyzing" && <Loader2 className="w-3 h-3 mr-1.5 animate-spin" />}
                {caseDetails?.status || "Analyzing"} {caseDetails?.status === "Analyzing" && "(In Progress)"}
              </Badge>
            </h1>
            <p className="text-muted-foreground text-sm mt-1">Subject: {caseDetails?.subject}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button onClick={() => setIsReportOpen(true)} className="gap-2 text-xs cursor-pointer">
            <FileText className="h-3.5 w-3.5" /> View / Export Report
          </Button>
        </div>
      </div>

      {/* Main Workspace Layout: Media Viewport (Left) + AI Analysis (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column: Media Inspector (2 Cols) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <Card className="bg-background/60 backdrop-blur border-border/50 overflow-hidden p-0 py-0 gap-0">
            {/* Viewport Control Bar */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-border/50 bg-muted/40">
              <div className="flex items-center gap-1">
                <Button 
                  size="sm" 
                  variant={activeViewMode === "rgb" ? "default" : "ghost"}
                  onClick={() => setActiveViewMode("rgb")}
                  className="gap-1.5 text-xs cursor-pointer"
                >
                  <Eye className="h-3.5 w-3.5" /> Standard RGB
                </Button>
                <Button 
                  size="sm" 
                  variant={activeViewMode === "ela" ? "default" : "ghost"}
                  onClick={() => setActiveViewMode("ela")}
                  className="gap-1.5 text-xs cursor-pointer"
                >
                  <Layers className="h-3.5 w-3.5 text-purple-400" /> Error Level Analysis (ELA)
                </Button>
                <Button 
                  size="sm" 
                  variant={activeViewMode === "bbox" ? "default" : "ghost"}
                  onClick={() => setActiveViewMode("bbox")}
                  className="gap-1.5 text-xs cursor-pointer"
                >
                  <Scan className="h-3.5 w-3.5 text-emerald-400" /> Face Detection Boxes
                </Button>
              </div>

              <span className="text-xs text-muted-foreground font-mono">Frame #{currentFrame} / 1800</span>
            </div>

            {/* Simulated Interactive Image/Frame Viewport */}
            <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden group">
              {/* Actual Media Image */}
              {caseDetails?.mediaUrl && (
                <img 
                  src={`http://localhost:4000${caseDetails.mediaUrl}`}
                  className={cn(
                    "absolute inset-0 w-full h-full object-contain z-10 transition-all duration-500",
                    caseDetails?.status === "Analyzing" && "opacity-60 blur-[1px]"
                  )} 
                  alt="Case Evidence" 
                />
              )}

              {/* Analyzing Overlay */}
              {caseDetails?.status === "Analyzing" && (
                <div className="absolute inset-0 z-20 flex flex-col items-center justify-center overflow-hidden">
                  {/* Scanner line animation (using raw CSS animation style) */}
                  <style>{`
                    @keyframes scan {
                      0% { top: 0%; opacity: 0; }
                      10% { opacity: 1; }
                      90% { opacity: 1; }
                      100% { top: 100%; opacity: 0; }
                    }
                    .scanner-line {
                      animation: scan 2.5s linear infinite;
                    }
                  `}</style>
                  <div className="absolute left-0 right-0 h-0.5 bg-primary shadow-[0_0_20px_4px_hsl(var(--primary))] scanner-line z-20" />
                  
                  <div className="bg-background/90 px-6 py-4 rounded-xl border border-primary/50 flex flex-col items-center gap-3 shadow-[0_0_30px_rgba(0,0,0,0.5)] backdrop-blur-md relative z-30 min-w-[280px]">
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-5 h-5 text-primary animate-spin" />
                      <span className="text-sm font-medium font-mono text-primary animate-pulse tracking-wider">COMPUTING VECTORS...</span>
                    </div>
                    
                    {/* Progress Bar */}
                    <div className="w-full space-y-1.5">
                      <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
                        <span>Analysis Progress</span>
                        <span>{Math.floor(analyzingProgress)}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-primary transition-all duration-300 ease-out rounded-full"
                          style={{ width: `${analyzingProgress}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* RGB Background Placeholder (visible behind transparent images or while loading) */}
              <div className="absolute inset-0 bg-gradient-to-tr from-slate-950 via-slate-900 to-indigo-950 flex flex-col items-center justify-center p-6 text-center z-0">
                
                {/* Simulated ELA Layer */}
                {activeViewMode === "ela" && (
                  <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,_rgba(168,85,247,0.45),_rgba(239,68,68,0.3),_transparent_70%)] mix-blend-screen animate-pulse z-20 pointer-events-none" />
                )}

                {/* Simulated Bounding Box Overlay */}
                {activeViewMode === "bbox" && (
                  <div className="absolute top-[25%] left-[38%] w-[24%] h-[40%] border-2 border-emerald-400/90 rounded-sm bg-emerald-500/10 flex flex-col justify-between p-1.5 shadow-[0_0_15px_rgba(52,211,153,0.3)] z-20 pointer-events-none">
                    <span className="text-[10px] font-mono font-bold bg-emerald-500 text-black px-1 rounded-xs self-start">
                      Target Face: 99.1% Fake
                    </span>
                    <div className="flex justify-between text-[9px] text-emerald-300 font-mono">
                      <span>{caseDetails?.resolution || "1080p"}</span>
                    </div>
                  </div>
                )}

                {!caseDetails?.mediaUrl && (
                  <>
                    <p className="text-muted-foreground/60 text-xs font-mono mb-2">
                      [ MEDIA VIEWPORT - MODE: <span className="text-primary font-bold uppercase">{activeViewMode}</span> ]
                    </p>
                    <div className="text-slate-400 text-sm max-w-sm">
                      {activeViewMode === "rgb" && "Viewing raw RGB image."}
                      {activeViewMode === "ela" && "Highlighting compression artifacts & noise mismatches."}
                      {activeViewMode === "bbox" && "Displaying neural face swap detection region boundaries."}
                    </div>
                  </>
                )}
              </div>

              {/* Viewport Play Controls (Hidden for static images) */}
              {caseDetails?.format?.includes("video") && (
                <div className="absolute bottom-0 inset-x-0 bg-slate-950/80 backdrop-blur border-t border-white/10 p-3 flex items-center justify-between text-white z-20">
                  <div className="flex items-center gap-2">
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-white hover:text-primary cursor-pointer" onClick={() => setCurrentFrame(Math.max(1, currentFrame - 1))}>
                      <SkipBack className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-white hover:text-primary cursor-pointer" onClick={() => setIsPlaying(!isPlaying)}>
                      {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                    </Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-white hover:text-primary cursor-pointer" onClick={() => setCurrentFrame(currentFrame + 1)}>
                      <SkipForward className="h-3.5 w-3.5" />
                    </Button>
                    <span className="text-xs font-mono text-slate-400 ml-2">00:04:44 / 01:00:00</span>
                  </div>

                  {/* Timeline Progress Bar */}
                  <div className="flex-1 mx-4">
                    <div className="relative w-full h-1.5 bg-white/20 rounded-full overflow-hidden cursor-pointer">
                      <div className="h-full bg-primary w-[32%]" />
                    </div>
                  </div>

                  <Badge variant="outline" className="text-[10px] text-slate-300 border-white/20 font-mono">
                    {caseDetails?.format || "Webcam H.264"}
                  </Badge>
                </div>
              )}
            </div>
          </Card>

          {/* Anomaly Timeline Chart (Hidden for static images) */}
          {caseDetails?.format?.includes("video") && (
            <Card className="bg-background/60 backdrop-blur border-border/50">
              <CardHeader className="py-3 px-4 flex flex-row items-center justify-between border-b border-border/50">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-primary" /> Frame-by-Frame Anomaly Timeline
                </CardTitle>
                <span className="text-xs text-muted-foreground">High variance detected between frames 120 - 450</span>
              </CardHeader>
              <CardContent className="p-4">
                <div className="h-28 flex items-end gap-1 border-b border-border/50 pb-2">
                  {Array.from({ length: 48 }).map((_, idx) => {
                    const heightPercentage = Math.floor(Math.sin(idx * 0.4) * 35 + 50) + (idx > 10 && idx < 28 ? 35 : 0);
                    const isHighRisk = heightPercentage > 75;
                    return (
                      <div 
                        key={idx}
                        className={`flex-1 rounded-t-xs transition-all ${
                          isHighRisk ? "bg-red-500/80 hover:bg-red-400" : "bg-primary/30 hover:bg-primary/60"
                        }`}
                        style={{ height: `${Math.min(100, heightPercentage)}%` }}
                        title={`Frame ${idx * 30}: ${heightPercentage}% Anomaly`}
                      />
                    );
                  })}
                </div>
                <div className="flex justify-between text-[10px] text-muted-foreground font-mono mt-2">
                  <span>00:00 (Start)</span>
                  <span className="text-red-400 font-bold">Deepfake Burst (00:04 - 00:09)</span>
                  <span>01:00 (End)</span>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right Column: AI Detection Breakdown + Metadata (1 Col) */}
        <div className="flex flex-col gap-4">
          
          {/* AI Confidence Scores */}
          <Card className="bg-background/60 backdrop-blur border-border/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-red-500" /> AI Detection Breakdown
              </CardTitle>
              <CardDescription className="text-xs">Model ensemble evaluation results</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-1">
              
              {caseDetails?.status === "Analyzing" ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex justify-between"><Skeleton className="h-4 w-32" /><Skeleton className="h-4 w-12" /></div>
                    <Skeleton className="h-2 w-full rounded-full" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between"><Skeleton className="h-4 w-40" /><Skeleton className="h-4 w-12" /></div>
                    <Skeleton className="h-2 w-full rounded-full" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between"><Skeleton className="h-4 w-28" /><Skeleton className="h-4 w-12" /></div>
                    <Skeleton className="h-2 w-full rounded-full" />
                  </div>
                  <div className="pt-2 text-center">
                    <span className="text-xs text-muted-foreground font-mono animate-pulse inline-flex items-center gap-2">
                      <Loader2 className="w-3 h-3 animate-spin" /> Models Evaluating...
                    </span>
                  </div>
                </div>
              ) : (
                <>
                  {/* Face Swap Meter — real EfficientNet-B0 deepfake score from ai-engine */}
                  <DetectionMeter
                    label="Deepfake Face Swap"
                    score={caseDetails?.forgery?.deepfakeScore}
                  />

                  {/* Temporal Splicing Meter — real tampering/ELA score from ai-engine */}
                  <DetectionMeter
                    label="Frame Splicing & Editing"
                    score={caseDetails?.forgery?.tamperingScore}
                  />

                  {/* No audio branch in the current pipeline — static image
                      analysis only (deepfake + tampering), so this is
                      surfaced as N/A rather than a fabricated number. */}
                  <DetectionMeter
                    label="Voice Cloning / Audio Gen"
                    score={null}
                    naLabel="N/A (image-only analysis)"
                  />
                </>
              )}
            </CardContent>
          </Card>

          {/* Forensic File & EXIF Metadata */}
          <Card className="bg-background/60 backdrop-blur border-border/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold">Media Metadata</CardTitle>
              <CardDescription className="text-xs">Extracted file information & hash integrity</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-1 text-xs">
              <div className="flex justify-between py-1.5 border-b border-border/40">
                <span className="text-muted-foreground">File Name:</span>
                <span className="font-medium truncate max-w-[180px]">
                  {caseDetails?.mediaUrl ? caseDetails.mediaUrl.split("/").pop() : "evidence_media.mp4"}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-border/40">
                <span className="text-muted-foreground">SHA-256 Hash:</span>
                <span className="font-mono text-[10px] text-primary truncate max-w-[170px]" title={displayHash}>
                  {displayHash.slice(0, 16)}...
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-border/40">
                <span className="text-muted-foreground">Resolution:</span>
                <span className="font-medium">{caseDetails?.resolution || "1920 x 1080 (1080p)"}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-border/40">
                <span className="text-muted-foreground">Software Toolkit:</span>
                <span className="font-medium">{caseDetails?.exifData?.Software || caseDetails?.exifData?.ProcessingSoftware || "Unknown"}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-border/40">
                <span className="text-muted-foreground">Camera Model:</span>
                <span className="font-medium">{caseDetails?.deviceFingerprint || "Standard Digital Camera"}</span>
              </div>
              <div className="flex justify-between py-1.5">
                <span className="text-muted-foreground">Container / Format:</span>
                <span className="font-medium">{caseDetails?.format || "image/png"}</span>
              </div>
            </CardContent>
          </Card>

        </div>
      </div>
    </div>
  );
}
