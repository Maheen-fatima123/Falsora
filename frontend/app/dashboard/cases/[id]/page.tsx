"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fetchApi } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { ForensicReportModal } from "@/components/report-modal";
import { toast } from "sonner";
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
  Loader2,
  UserPlus,
  Archive,
  ArchiveRestore,
  Flame,
  Grid3x3,
  Focus,
} from "lucide-react";

/** Renders one AI Detection Breakdown row from a real 0.0-1.0 model score
 * (or an N/A state when no signal exists for that branch). */
const PIPELINE_STEPS = [
  { key: "UPLOAD", label: "Upload & validate" },
  { key: "FINGERPRINT", label: "Fingerprint" },
  { key: "INTEGRITY", label: "Source integrity" },
  { key: "FORGERY", label: "AI forgery" },
  { key: "DECISION", label: "Trust decision" },
] as const;

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
  const router = useRouter();
  const caseId = (params?.id as string) || "";

  const [caseDetails, setCaseDetails] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [awaitingResults, setAwaitingResults] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [activeViewMode, setActiveViewMode] = useState<"rgb" | "ela" | "bbox" | "gradcam" | "heatmap">("rgb");
  // Natural pixel size of the case image — the face box is in these coordinates.
  const [mediaSize, setMediaSize] = useState<{ w: number; h: number } | null>(null);
  const autoOpenedGradcam = useRef(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentFrame, setCurrentFrame] = useState(142);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [analyzingProgress, setAnalyzingProgress] = useState(8);
  const [role, setRole] = useState<string>("Administrator");
  const [reviewers, setReviewers] = useState<any[]>([]);
  const [assignId, setAssignId] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [comment, setComment] = useState("");

  useEffect(() => {
    try {
      const stored = localStorage.getItem("falsora_user");
      if (stored) setRole(JSON.parse(stored)?.role || "Administrator");
    } catch {}
  }, []);

  // Fetch + poll until analysis finishes, then keep refreshing briefly for forgery scores.
  useEffect(() => {
    if (!caseId) return;

    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | undefined;
    let postCompletePolls = 0;

    setIsLoading(true);
    setAwaitingResults(true);
    setLoadError("");
    setCaseDetails(null);
    setAnalyzingProgress(8);
    autoOpenedGradcam.current = false;
    setActiveViewMode("rgb");

    const stopPoll = () => {
      if (poll) {
        clearInterval(poll);
        poll = undefined;
      }
    };

    const fetchCase = async () => {
      try {
        const res = await fetchApi(`http://localhost:4000/api/cases/${caseId}`);
        const resData = await res.json();
        if (cancelled) return;

        if (!res.ok || !resData.success || !resData.data) {
          setLoadError(resData.message || "Failed to load case");
          setIsLoading(false);
          setAwaitingResults(false);
          stopPoll();
          return;
        }

        setCaseDetails(resData.data);
        setIsLoading(false);
        setLoadError("");

        const status = resData.data.status as string;
        const job = resData.data.verificationJob;
        if (typeof job?.progress === "number") {
          setAnalyzingProgress(Math.max(8, Math.min(99, job.progress)));
        }
        const hasForgery = !!resData.data.forgery;
        if (
          !autoOpenedGradcam.current &&
          (resData.data.forgery?.overlayUrl || resData.data.forgery?.heatmapUrl)
        ) {
          setActiveViewMode("gradcam");
          autoOpenedGradcam.current = true;
        }

        const jobBusy =
          job &&
          (job.status === "PROCESSING" || job.status === "PENDING");

        if (status === "Analyzing" || jobBusy) {
          postCompletePolls = 0;
          setAwaitingResults(true);
          if (!poll) poll = setInterval(fetchCase, 1500);
          return;
        }

        // Status done but scores not in the payload yet — keep polling briefly
        if (!hasForgery && status !== "Archived" && postCompletePolls < 12) {
          postCompletePolls += 1;
          setAwaitingResults(true);
          if (!poll) poll = setInterval(fetchCase, 1500);
          return;
        }

        setAwaitingResults(false);
        stopPoll();
      } catch (error) {
        console.error("Failed to fetch case details", error);
        if (!cancelled) {
          setLoadError("Failed to load case details");
          setIsLoading(false);
          setAwaitingResults(false);
          stopPoll();
        }
      }
    };

    void fetchCase();
    return () => {
      cancelled = true;
      stopPoll();
    };
  }, [caseId]);

  useEffect(() => {
    if (role !== "Administrator") return;
    fetchApi("http://localhost:4000/api/auth/users")
      .then((r) => r.json())
      .then((d) => {
        const list = d.users || d.data || [];
        if (Array.isArray(list)) {
          setReviewers(list.filter((u: any) => u.role === "Reviewer"));
        }
      })
      .catch(() => {});
  }, [role]);

  const analysisPending =
    isLoading || awaitingResults || caseDetails?.status === "Analyzing";

  const jobStage = caseDetails?.verificationJob?.stage as string | undefined;
  const jobStatus = caseDetails?.verificationJob?.status as string | undefined;
  const stageIndex = PIPELINE_STEPS.findIndex((s) => s.key === jobStage);

  // Soft tick only when job progress not yet available from API
  useEffect(() => {
    if (!analysisPending) {
      setAnalyzingProgress(100);
      return;
    }
    if (typeof caseDetails?.verificationJob?.progress === "number") {
      setAnalyzingProgress(
        Math.max(8, Math.min(99, caseDetails.verificationJob.progress))
      );
      return;
    }

    const interval = setInterval(() => {
      setAnalyzingProgress((prev) => {
        if (prev >= 94) return prev;
        const increment = prev < 40 ? 6 : prev < 70 ? 3 : 1;
        return Math.min(94, prev + increment);
      });
    }, 450);

    return () => clearInterval(interval);
  }, [analysisPending, caseDetails?.verificationJob?.progress]);

  const patchCase = async (body: Record<string, unknown>, okMsg: string) => {
    setActionBusy(true);
    try {
      const res = await fetchApi(`http://localhost:4000/api/cases/${caseId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        toast.error(data.message || "Action failed");
        return;
      }
      toast.success(okMsg);
      if (body.status === "Archived") {
        router.push("/dashboard/cases?status=Archived");
        return;
      }
      const refreshed = await fetchApi(`http://localhost:4000/api/cases/${caseId}`);
      const refreshedData = await refreshed.json();
      if (refreshedData.success) setCaseDetails(refreshedData.data);
    } catch (e: any) {
      toast.error(e.message || "Action failed");
    } finally {
      setActionBusy(false);
    }
  };

  const assignReviewer = async () => {
    if (!assignId) {
      toast.error("Pick a reviewer first");
      return;
    }
    setActionBusy(true);
    try {
      const res = await fetchApi(`http://localhost:4000/api/cases/${caseId}/assign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ reviewerId: assignId }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        toast.error(data.message || "Assign failed");
        return;
      }
      toast.success("Reviewer assigned");
      setCaseDetails((prev: any) =>
        prev ? { ...prev, assignedTo: assignId } : prev
      );
    } catch (e: any) {
      toast.error(e.message || "Assign failed");
    } finally {
      setActionBusy(false);
    }
  };

  const displayTitle =
    caseDetails?.title || caseDetails?.subject || "Loading case…";
  const displayStatus = analysisPending
    ? "Analyzing"
    : caseDetails?.status || "Analyzing";
  const displayHash =
    caseDetails?.sha256 ||
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  const displayDate =
    caseDetails?.date || new Date().toISOString().split("T")[0];

  if (loadError && !caseDetails) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
        <AlertTriangle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">{loadError}</p>
        <Link
          href="/dashboard/cases"
          className={cn(buttonVariants({ variant: "outline" }))}
        >
          Back to cases
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Forensic Report Modal */}
      <ForensicReportModal 
        isOpen={isReportOpen}
        onClose={() => setIsReportOpen(false)}
        caseData={{
          id: caseDetails?.id || caseId,
          subject: displayTitle,
          status: displayStatus,
          confidence: caseDetails?.confidence || (displayStatus === "Flagged" ? "98.4%" : displayStatus === "Verified" ? "99.1%" : "..."),
          date: displayDate,
          fileName: caseDetails?.mediaUrl ? caseDetails.mediaUrl.split("/").pop() : "evidence.jpg",
          hash: displayHash,
          sha256: caseDetails?.sha256 || displayHash,
          format: caseDetails?.format,
          resolution: caseDetails?.resolution,
          deviceFingerprint: caseDetails?.deviceFingerprint,
          isTampered: caseDetails?.isTampered,
          softwareFlag: caseDetails?.softwareFlag,
          trustScore: caseDetails?.trustScore,
          riskLevel: caseDetails?.riskLevel,
          accessMode: caseDetails?.accessMode,
          latestVerdict: caseDetails?.latestVerdict,
          forgery: caseDetails?.forgery,
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
                variant={displayStatus === "Flagged" ? "destructive" : displayStatus === "Verified" ? "default" : "secondary"}
                className={cn(
                  displayStatus === "Verified" && "bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20",
                  analysisPending && "animate-pulse"
                )}
              >
                {analysisPending && <Loader2 className="w-3 h-3 mr-1.5 animate-spin" />}
                {analysisPending ? "Analyzing (In Progress)" : displayStatus}
              </Badge>
            </h1>
            <div className="text-muted-foreground text-sm mt-1">
              Subject: {isLoading ? <Skeleton className="inline-block h-4 w-40 align-middle" /> : caseDetails?.subject}
            </div>
            {!isLoading && caseDetails && (
              <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-[11px] text-muted-foreground">
                {caseDetails.accessMode && (
                  <span>
                    Mode:{" "}
                    <span className="text-foreground font-medium">
                      {caseDetails.accessMode === "public" ? "Public" : "Organizational"}
                    </span>
                  </span>
                )}
                {caseDetails.reviewerName && (
                  <span>
                    Reviewer:{" "}
                    <span className="text-foreground font-medium">{caseDetails.reviewerName}</span>
                  </span>
                )}
                {caseDetails.latestVerdict && (
                  <span>
                    Verdict:{" "}
                    <span className="text-foreground font-medium font-mono">
                      {caseDetails.latestVerdict.finalVerdict}
                    </span>
                    {typeof caseDetails.latestVerdict.confidence === "number" && (
                      <> ({Math.round(caseDetails.latestVerdict.confidence * 100)}%)</>
                    )}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap justify-end">
          {role === "Administrator" &&
            !analysisPending &&
            caseDetails?.status !== "Archived" && (
            <div className="flex items-center gap-2">
              <select
                value={assignId}
                onChange={(e) => setAssignId(e.target.value)}
                className="h-8 rounded-lg border border-border bg-background px-2 text-xs max-w-[160px]"
              >
                <option value="">Assign reviewer…</option>
                {reviewers.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={actionBusy || !assignId}
                onClick={() => void assignReviewer()}
              >
                <UserPlus className="h-3.5 w-3.5" /> Assign
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={actionBusy}
                onClick={() =>
                  void patchCase({ status: "Archived" }, "Case archived")
                }
              >
                <Archive className="h-3.5 w-3.5" /> Archive
              </Button>
            </div>
          )}

          {role === "Administrator" && caseDetails?.status === "Archived" && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              disabled={actionBusy}
              onClick={() => {
                const restore =
                  caseDetails?.riskLevel === "High-Risk" ||
                  caseDetails?.riskLevel === "High" ||
                  caseDetails?.riskLevel === "Medium" ||
                  caseDetails?.riskLevel === "Uncertain"
                    ? "Flagged"
                    : "Verified";
                void patchCase(
                  { status: restore },
                  `Case restored as ${restore}`
                );
              }}
            >
              <ArchiveRestore className="h-3.5 w-3.5" /> Unarchive
            </Button>
          )}

          {(role === "Reviewer" || role === "Administrator") &&
            !analysisPending &&
            caseDetails?.status !== "Archived" && (
              <div className="flex items-center gap-2">
                <input
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Optional comment"
                  className="h-8 rounded-lg border border-border bg-background px-2 text-xs w-36 hidden sm:block"
                />
                <Button
                  size="sm"
                  className="gap-1.5 bg-emerald-600 hover:bg-emerald-600/90 text-white"
                  disabled={actionBusy}
                  onClick={() =>
                    void patchCase(
                      { status: "Verified", comment },
                      "Case approved"
                    )
                  }
                >
                  <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  className="gap-1.5"
                  disabled={actionBusy}
                  onClick={() =>
                    void patchCase(
                      { status: "Flagged", comment },
                      "Case rejected / flagged"
                    )
                  }
                >
                  <AlertTriangle className="h-3.5 w-3.5" /> Reject
                </Button>
              </div>
            )}

          <Button onClick={() => setIsReportOpen(true)} className="gap-2 text-xs cursor-pointer">
            <FileText className="h-3.5 w-3.5" />{" "}
            {role === "User" ? "Download my report" : "View / Export Report"}
          </Button>
        </div>
      </div>

      {/* Main Workspace Layout: Media Viewport (Left) + AI Analysis (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column: Media Inspector (2 Cols) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <Card className="bg-background/60 backdrop-blur border-border/50 overflow-hidden p-0 py-0 gap-0">
            {/* Viewport Control Bar — wrap so icons/labels never clip */}
            <div className="flex flex-col gap-2 px-3 py-2 border-b border-border/50 bg-muted/40 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-1">
                {(
                  [
                    {
                      id: "rgb" as const,
                      label: "RGB",
                      title: "Standard RGB",
                      icon: Eye,
                      iconClass: "text-foreground",
                      enabled: true,
                    },
                    {
                      id: "ela" as const,
                      label: "ELA",
                      title: caseDetails?.forgery?.elaUrl
                        ? "Error Level Analysis (JPEG re-save difference)"
                        : "ELA map not available for this case",
                      icon: Flame,
                      iconClass: "text-purple-400",
                      enabled: !!caseDetails?.forgery?.elaUrl,
                    },
                    {
                      id: "bbox" as const,
                      label: "Faces",
                      title: "Face detection boxes",
                      icon: Focus,
                      iconClass: "text-emerald-400",
                      enabled: true,
                    },
                    {
                      id: "gradcam" as const,
                      label: "Grad-CAM",
                      title: "Grad-CAM overlay (image + attention)",
                      icon: Layers,
                      iconClass: "text-amber-400",
                      enabled: !!(
                        caseDetails?.forgery?.overlayUrl ||
                        caseDetails?.forgery?.heatmapUrl ||
                        caseDetails?.forgery?.rawHeatmapUrl
                      ),
                    },
                    {
                      id: "heatmap" as const,
                      label: "Heatmap",
                      title: caseDetails?.forgery?.rawHeatmapUrl
                        ? "Raw Grad-CAM heatmap"
                        : "Heatmap view (from Grad-CAM overlay)",
                      icon: Grid3x3,
                      iconClass: "text-rose-400",
                      // Allow click whenever any Grad-CAM artifact exists —
                      // fall back to styled overlay if raw heatmap missing
                      enabled: !!(
                        caseDetails?.forgery?.rawHeatmapUrl ||
                        caseDetails?.forgery?.overlayUrl ||
                        caseDetails?.forgery?.heatmapUrl
                      ),
                    },
                  ] as const
                ).map((mode) => {
                  const Icon = mode.icon;
                  return (
                    <Button
                      key={mode.id}
                      size="sm"
                      variant={activeViewMode === mode.id ? "default" : "ghost"}
                      title={mode.title}
                      disabled={!mode.enabled}
                      onClick={() => setActiveViewMode(mode.id)}
                      className="h-8 gap-1.5 px-2.5 text-xs shrink-0 cursor-pointer disabled:opacity-40"
                    >
                      <Icon className={cn("h-3.5 w-3.5 shrink-0", mode.iconClass)} />
                      <span>{mode.label}</span>
                    </Button>
                  );
                })}
              </div>
              <span className="text-[10px] text-muted-foreground font-mono capitalize shrink-0">
                Mode: {activeViewMode}
              </span>
            </div>

            {/* Simulated Interactive Image/Frame Viewport */}
            <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden group">
              {/* Actual Media Image — RGB / ELA / BBox use original; Grad-CAM / heatmap use evidence */}
              {(() => {
                const mediaBase = caseDetails?.mediaUrl
                  ? `http://localhost:4000${caseDetails.mediaUrl}`
                  : null;
                const overlay = caseDetails?.forgery?.overlayUrl
                  ? `http://localhost:4000${caseDetails.forgery.overlayUrl}`
                  : caseDetails?.forgery?.heatmapUrl
                    ? `http://localhost:4000${caseDetails.forgery.heatmapUrl}`
                    : null;
                const heat = caseDetails?.forgery?.rawHeatmapUrl
                  ? `http://localhost:4000${caseDetails.forgery.rawHeatmapUrl}`
                  : null;
                const ela = caseDetails?.forgery?.elaUrl
                  ? `http://localhost:4000${caseDetails.forgery.elaUrl}`
                  : null;
                // Heatmap prefers raw CAM map; if missing, reuse overlay with heatmap styling below
                const src =
                  activeViewMode === "gradcam"
                    ? overlay || heat || mediaBase
                    : activeViewMode === "heatmap"
                      ? heat || overlay || mediaBase
                      : activeViewMode === "ela"
                        ? ela || mediaBase
                        : mediaBase;
                if (!src) return null;
                const heatmapDerived =
                  activeViewMode === "heatmap" && !heat && !!overlay;
                return (
                  <>
                    <img
                      src={src}
                      onLoad={(e) => {
                        const t = e.currentTarget;
                        if (src === mediaBase && t.naturalWidth && t.naturalHeight) {
                          setMediaSize({ w: t.naturalWidth, h: t.naturalHeight });
                        }
                      }}
                      className={cn(
                        "absolute inset-0 w-full h-full object-contain z-10 transition-all duration-300",
                        analysisPending && "opacity-60 blur-[1px]",
                        // Distinct from Grad-CAM when we only have the overlay PNG
                        heatmapDerived &&
                          "contrast-[1.6] saturate-[2.2] brightness-90 hue-rotate-[320deg]",
                        activeViewMode === "heatmap" &&
                          heat &&
                          "contrast-125 saturate-150"
                      )}
                      alt={
                        activeViewMode === "gradcam"
                          ? "Grad-CAM overlay evidence"
                          : activeViewMode === "heatmap"
                            ? heat
                              ? "Raw Grad-CAM heatmap"
                              : "Heatmap view derived from Grad-CAM"
                            : activeViewMode === "ela"
                              ? "Error level analysis map"
                              : "Case Evidence"
                      }
                    />
                    {activeViewMode === "heatmap" && !analysisPending && (
                      <div className="absolute top-2 left-2 z-20 rounded border border-rose-400/40 bg-black/70 px-2 py-1 text-[10px] font-mono text-rose-300">
                        {heat
                          ? "Raw Grad-CAM heatmap"
                          : "Heatmap view · derived from overlay"}
                      </div>
                    )}
                    {activeViewMode === "ela" && ela && !analysisPending && (
                      <div className="absolute top-2 left-2 z-20 rounded border border-purple-400/40 bg-black/70 px-2 py-1 text-[10px] font-mono text-purple-300">
                        ELA · JPEG q90 re-save difference (15× amplified)
                      </div>
                    )}
                  </>
                );
              })()}

              {/* Face box overlay — real detected box from ai-engine, drawn in image
                  pixel coordinates. The SVG's "meet" scaling matches the img's
                  object-contain, so the box stays on the face at any viewer size. */}
              {activeViewMode === "bbox" && caseDetails?.mediaUrl && !analysisPending && (() => {
                const box = caseDetails?.forgery?.faceBox as
                  | { x1: number; y1: number; x2: number; y2: number }
                  | null
                  | undefined;
                if (caseDetails?.forgery?.faceDetected === false || !box) {
                  return (
                    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/45 p-4">
                      <p className="text-xs text-muted-foreground font-mono text-center max-w-xs rounded-lg border border-border/60 bg-background/80 px-3 py-2">
                        {caseDetails?.forgery?.faceDetected === false
                          ? "No face detected for this image — face-box view unavailable."
                          : "Face position not available for this case."}
                      </p>
                    </div>
                  );
                }
                if (!mediaSize) return null;
                const label =
                  typeof caseDetails?.forgery?.deepfakeScore === "number"
                    ? `Face · ${Math.round(caseDetails.forgery.deepfakeScore * 1000) / 10}% fake`
                    : "Face";
                const fs = Math.max(mediaSize.w, mediaSize.h) * 0.024;
                const labelH = fs * 1.5;
                const labelW = label.length * fs * 0.62 + fs;
                const labelY = box.y1 - labelH >= 0 ? box.y1 - labelH : box.y1;
                const labelX = Math.max(0, Math.min(box.x1, mediaSize.w - labelW));
                return (
                  <svg
                    className="absolute inset-0 z-20 w-full h-full pointer-events-none"
                    viewBox={`0 0 ${mediaSize.w} ${mediaSize.h}`}
                    preserveAspectRatio="xMidYMid meet"
                  >
                    <rect
                      x={box.x1}
                      y={box.y1}
                      width={box.x2 - box.x1}
                      height={box.y2 - box.y1}
                      fill="rgba(16,185,129,0.10)"
                      stroke="rgb(52,211,153)"
                      strokeWidth={2}
                      vectorEffect="non-scaling-stroke"
                    />
                    <rect x={labelX} y={labelY} width={labelW} height={labelH} fill="rgb(16,185,129)" />
                    <text
                      x={labelX + fs * 0.5}
                      y={labelY + labelH * 0.72}
                      fontSize={fs}
                      fontFamily="ui-monospace, monospace"
                      fontWeight="bold"
                      fill="black"
                    >
                      {label}
                    </text>
                  </svg>
                );
              })()}

              {activeViewMode === "gradcam" &&
                !caseDetails?.forgery?.overlayUrl &&
                !caseDetails?.forgery?.heatmapUrl &&
                !analysisPending && (
                  <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/50 p-6 text-center">
                    <p className="text-xs text-muted-foreground max-w-sm">
                      No Grad-CAM overlay for this case yet. Grad-CAM runs on the
                      deepfake branch when a face is detected. Try an image with a
                      clear face, or wait for analysis to finish.
                    </p>
                  </div>
                )}

              {/* Analyzing / initial-load overlay */}
              {analysisPending && (
                <div className="absolute inset-0 z-30 flex flex-col items-center justify-center overflow-hidden">
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
                      <span className="text-sm font-medium font-mono text-primary animate-pulse tracking-wider">
                        {isLoading
                          ? "LOADING CASE…"
                          : jobStage
                            ? `STAGE: ${jobStage}`
                            : "COMPUTING VECTORS…"}
                      </span>
                    </div>
                    
                    <div className="w-full space-y-1.5">
                      <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
                        <span>Pipeline progress</span>
                        <span>{Math.floor(analyzingProgress)}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-primary transition-all duration-300 ease-out rounded-full"
                          style={{ width: `${analyzingProgress}%` }}
                        />
                      </div>
                    </div>
                    <div className="flex flex-wrap justify-center gap-1 max-w-[260px]">
                      {PIPELINE_STEPS.map((step, i) => {
                        const done =
                          jobStatus === "COMPLETED" ||
                          (stageIndex >= 0 && i < stageIndex);
                        const active =
                          analysisPending &&
                          stageIndex === i &&
                          jobStatus !== "FAILED";
                        return (
                          <span
                            key={step.key}
                            className={cn(
                              "text-[8px] font-mono px-1.5 py-0.5 rounded border",
                              done && "border-emerald-500/40 text-emerald-500",
                              active && "border-primary text-primary",
                              !done && !active && "border-border/50 text-muted-foreground"
                            )}
                          >
                            {step.label}
                          </span>
                        );
                      })}
                    </div>
                    <p className="text-[10px] text-muted-foreground text-center max-w-[240px]">
                      Orchestrator updates stages automatically — no refresh needed.
                    </p>
                  </div>
                </div>
              )}

              {/* Placeholder when no media yet */}
              <div className="absolute inset-0 bg-gradient-to-tr from-slate-950 via-slate-900 to-indigo-950 flex flex-col items-center justify-center p-6 text-center z-0">
                {!caseDetails?.mediaUrl && (
                  <>
                    <p className="text-muted-foreground/60 text-xs font-mono mb-2">
                      [ MEDIA VIEWPORT — MODE:{" "}
                      <span className="text-primary font-bold uppercase">
                        {activeViewMode}
                      </span>{" "}
                      ]
                    </p>
                    <div className="text-slate-400 text-sm max-w-sm">
                      {activeViewMode === "rgb" && "Viewing raw RGB image."}
                      {activeViewMode === "ela" &&
                        "Error-level preview (compression / resave cues)."}
                      {activeViewMode === "bbox" &&
                        "Face detection region overlay."}
                      {activeViewMode === "gradcam" &&
                        "Grad-CAM overlay — regions that drove the deepfake score."}
                      {activeViewMode === "heatmap" &&
                        "Raw Grad-CAM heatmap (no original image underneath)."}
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
              
              {analysisPending ? (
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
                      <Loader2 className="w-3 h-3 animate-spin" />{" "}
                      {isLoading ? "Loading case…" : "Models evaluating…"}
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

                  {/* Fully AI-generated face — synthetic-face branch from ai-engine */}
                  <DetectionMeter
                    label="Fully AI-Generated Face"
                    score={caseDetails?.forgery?.syntheticScore}
                    naLabel={
                      caseDetails?.forgery?.faceDetected === false
                        ? "N/A (no face detected)"
                        : "N/A"
                    }
                  />
                </>
              )}
            </CardContent>
          </Card>

          {/* 6.8 Decision Intelligence */}
          <Card className="bg-background/60 backdrop-blur border-border/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Cpu className="h-4 w-4 text-primary" /> Decision Intelligence
              </CardTitle>
              <CardDescription className="text-xs">
                Aggregated trust score · Low / Medium / High (module 6.8)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-1 text-xs">
              {analysisPending ? (
                <Skeleton className="h-20 w-full" />
              ) : (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Trust score</span>
                    <span className="font-mono font-bold">
                      {typeof caseDetails?.trustScore === "number"
                        ? `${Math.round(caseDetails.trustScore * 100)}%`
                        : caseDetails?.confidence || "—"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Risk band</span>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px]",
                        (caseDetails?.riskLevel === "High" ||
                          caseDetails?.riskLevel === "High-Risk") &&
                          "border-red-500/40 text-red-500",
                        (caseDetails?.riskLevel === "Medium" ||
                          caseDetails?.riskLevel === "Uncertain") &&
                          "border-amber-500/40 text-amber-500",
                        (caseDetails?.riskLevel === "Low" ||
                          caseDetails?.riskLevel === "Authentic") &&
                          "border-emerald-500/40 text-emerald-500"
                      )}
                    >
                      {caseDetails?.decision?.riskBand ||
                        caseDetails?.riskLevel ||
                        "Pending"}
                    </Badge>
                  </div>
                  {caseDetails?.decision?.legacyRiskLevel && (
                    <div className="flex justify-between text-[10px] text-muted-foreground">
                      <span>Legacy label</span>
                      <span className="font-mono">
                        {caseDetails.decision.legacyRiskLevel}
                      </span>
                    </div>
                  )}
                  {Array.isArray(
                    (caseDetails?.decision?.ruleTrace as any)?.rules_fired
                  ) && (
                    <div className="space-y-1">
                      <span className="text-muted-foreground">Rules fired</span>
                      <div className="flex flex-wrap gap-1">
                        {(
                          (caseDetails?.decision?.ruleTrace as any)
                            .rules_fired as string[]
                        )
                          .slice(0, 8)
                          .map((r) => (
                            <span
                              key={r}
                              className="px-1.5 py-0.5 rounded border border-border/60 font-mono text-[9px]"
                            >
                              {r}
                            </span>
                          ))}
                      </div>
                    </div>
                  )}
                  {(caseDetails?.decision?.ruleTrace as any)?.breakdown ||
                  (caseDetails?.latestVerdict?.ruleTrace as any)?.breakdown ? (
                    <div className="grid grid-cols-3 gap-2 pt-1">
                      {(["forgery_factor", "exif_factor", "fingerprint_factor"] as const).map(
                        (key) => {
                          const bd =
                            (caseDetails?.decision?.ruleTrace as any)?.breakdown ||
                            (caseDetails?.latestVerdict?.ruleTrace as any)
                              ?.breakdown ||
                            {};
                          const v = bd[key];
                          return (
                            <div
                              key={key}
                              className="rounded border border-border/40 p-1.5 text-center"
                            >
                              <div className="text-[9px] text-muted-foreground uppercase">
                                {key.replace("_factor", "")}
                              </div>
                              <div className="font-mono font-semibold">
                                {typeof v === "number"
                                  ? `${Math.round(v * 100)}%`
                                  : "—"}
                              </div>
                            </div>
                          );
                        }
                      )}
                    </div>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>

          {/* 6.9 Verification Orchestration */}
          <Card className="bg-background/60 backdrop-blur border-border/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Scan className="h-4 w-4 text-sky-500" /> Verification Pipeline
              </CardTitle>
              <CardDescription className="text-xs">
                Orchestrated stages · Upload → AI → Trust (module 6.9)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-1 text-xs">
              {isLoading && !caseDetails ? (
                <Skeleton className="h-16 w-full" />
              ) : (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Job status</span>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px]",
                        jobStatus === "COMPLETED" &&
                          "border-emerald-500/40 text-emerald-500",
                        jobStatus === "FAILED" &&
                          "border-red-500/40 text-red-500",
                        (jobStatus === "PROCESSING" || !jobStatus) &&
                          analysisPending &&
                          "border-primary/40 text-primary"
                      )}
                    >
                      {jobStatus || (analysisPending ? "PROCESSING" : "—")}
                    </Badge>
                  </div>
                  <div className="space-y-1.5">
                    {PIPELINE_STEPS.map((step, i) => {
                      const done =
                        jobStatus === "COMPLETED" ||
                        (stageIndex >= 0 && i < stageIndex) ||
                        (jobStatus === "FAILED" && stageIndex >= 0 && i < stageIndex);
                      const active =
                        stageIndex === i &&
                        jobStatus !== "COMPLETED" &&
                        jobStatus !== "FAILED";
                      const failedHere =
                        jobStatus === "FAILED" && stageIndex === i;
                      return (
                        <div
                          key={step.key}
                          className="flex items-center justify-between gap-2"
                        >
                          <span
                            className={cn(
                              "font-mono text-[10px]",
                              done && "text-emerald-500",
                              active && "text-primary",
                              failedHere && "text-red-500",
                              !done && !active && !failedHere && "text-muted-foreground"
                            )}
                          >
                            {i + 1}. {step.label}
                          </span>
                          <span className="text-[9px] font-mono text-muted-foreground">
                            {failedHere
                              ? "FAILED"
                              : done
                                ? "done"
                                : active
                                  ? "running"
                                  : "—"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  {caseDetails?.verificationJob?.errorLog && (
                    <p className="text-[10px] text-red-500/90 font-mono break-words">
                      {caseDetails.verificationJob.errorLog}
                    </p>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* 6.7 Interpretability */}
          <Card className="bg-background/60 backdrop-blur border-border/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Layers className="h-4 w-4 text-amber-500" /> AI Interpretability
              </CardTitle>
              <CardDescription className="text-xs">
                Grad-CAM evidence for the deepfake branch (module 6.7)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-1 text-xs">
              {analysisPending ? (
                <Skeleton className="h-16 w-full" />
              ) : caseDetails?.forgery?.overlayUrl || caseDetails?.forgery?.heatmapUrl ? (
                <>
                  <p className="text-muted-foreground leading-relaxed">
                    {caseDetails.forgery.explanationText ||
                      "Highlighted regions contributed most to the deepfake prediction."}
                  </p>
                  <div className="flex flex-wrap gap-2 text-[10px] font-mono text-muted-foreground">
                    {caseDetails.forgery.explanationMethod && (
                      <span className="px-1.5 py-0.5 rounded border border-border/60">
                        method: {caseDetails.forgery.explanationMethod}
                      </span>
                    )}
                    {caseDetails.forgery.targetLayer && (
                      <span className="px-1.5 py-0.5 rounded border border-border/60">
                        layer: {caseDetails.forgery.targetLayer}
                      </span>
                    )}
                    {caseDetails.forgery.faceDetected === false && (
                      <span className="px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-500">
                        no face — Grad-CAM may be empty
                      </span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs gap-1"
                      onClick={() => setActiveViewMode("gradcam")}
                    >
                      Show overlay
                    </Button>
                    {caseDetails.forgery.rawHeatmapUrl && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs gap-1"
                        onClick={() => setActiveViewMode("heatmap")}
                      >
                        Raw heatmap
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs"
                      onClick={() => setActiveViewMode("rgb")}
                    >
                      Original
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground leading-relaxed">
                  No visual explanation stored for this case. Grad-CAM is generated when the
                  deepfake model runs on a detected face. Tampering-only cases may not have
                  a heatmap.
                </p>
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
