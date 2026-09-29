"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Download,
  ShieldAlert,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  User,
  X,
  Loader2,
  Layers,
  ExternalLink,
} from "lucide-react";
import jsPDF from "jspdf";
import { toast } from "sonner";

if (typeof window !== "undefined") {
  const origConsoleError = console.error;
  console.error = (...args: any[]) => {
    if (
      args.length > 0 &&
      typeof args[0] === "string" &&
      (args[0].includes("unsupported color function") ||
        args[0].includes("oklab") ||
        args[0].includes("lab"))
    ) {
      return;
    }
    origConsoleError.apply(console, args);
  };
}

export type ForensicReportCaseData = {
  id: string;
  subject: string;
  status: string;
  confidence: string;
  date: string;
  fileName?: string;
  hash?: string;
  sha256?: string;
  format?: string;
  resolution?: string;
  deviceFingerprint?: string;
  isTampered?: boolean;
  softwareFlag?: string;
  trustScore?: number | null;
  riskLevel?: string | null;
  accessMode?: string | null;
  latestVerdict?: {
    finalVerdict?: string;
    confidence?: number;
  } | null;
  forgery?: {
    deepfakeScore?: number | null;
    tamperingScore?: number | null;
    syntheticScore?: number | null;
    overlayUrl?: string | null;
    heatmapUrl?: string | null;
    rawHeatmapUrl?: string | null;
    explanationText?: string | null;
    explanationMethod?: string | null;
    modelName?: string | null;
  } | null;
};

interface ForensicReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseData?: ForensicReportCaseData;
}

function pctLabel(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "N/A";
  return `${Math.round(score * 1000) / 10}%`;
}

function scoreNote(score: number | null | undefined): string {
  if (score == null) return "Unavailable";
  // Align with 6.8 bands (High / Medium / Low) for forgery probability
  if (score >= 0.7) return "High";
  if (score >= 0.4) return "Medium";
  return "Low";
}

function scoreColor(score: number | null | undefined): string {
  if (score == null) return "#64748b";
  if (score >= 0.7) return "#dc2626";
  if (score >= 0.4) return "#d97706";
  return "#16a34a";
}

async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

export function ForensicReportModal({
  isOpen,
  onClose,
  caseData,
}: ForensicReportModalProps) {
  const printRef = useRef<HTMLDivElement>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [savedReports, setSavedReports] = useState<any[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);

  const cId = caseData?.id || "CAS-UNKNOWN";
  const subject = caseData?.subject || "Untitled case";
  const confidence = caseData?.confidence || "…";
  const status = caseData?.status || "Analyzing";
  const date =
    caseData?.date ||
    new Date().toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  const fileName = caseData?.fileName || "evidence.jpg";
  const hash =
    caseData?.sha256 ||
    caseData?.hash ||
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  const deepfake = caseData?.forgery?.deepfakeScore ?? null;
  const tampering = caseData?.forgery?.tamperingScore ?? null;
  const synthetic = caseData?.forgery?.syntheticScore ?? null;
  const overlayPath =
    caseData?.forgery?.overlayUrl || caseData?.forgery?.heatmapUrl || null;
  const verdictLabel =
    caseData?.latestVerdict?.finalVerdict ||
    (status === "Verified"
      ? "GENUINE"
      : status === "Flagged"
        ? "MANIPULATED"
        : "PENDING");

  const loadReports = async () => {
    if (!caseData?.id) return;
    setLoadingReports(true);
    try {
      const res = await fetch(
        `http://localhost:4000/api/cases/${caseData.id}/reports`,
        { credentials: "include" }
      );
      const data = await res.json();
      if (data.success && Array.isArray(data.data)) {
        setSavedReports(data.data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingReports(false);
    }
  };

  useEffect(() => {
    if (isOpen && caseData?.id) {
      void loadReports();
    }
  }, [isOpen, caseData?.id]);

  const buildSummary = () => {
    const parts: string[] = [];
    parts.push(
      `Falsora automated analysis was run on media item "${fileName}" (case ${cId}).`
    );
    if (deepfake != null) {
      parts.push(
        `Deepfake face-swap probability: ${pctLabel(deepfake)} (${scoreNote(deepfake)}).`
      );
    } else {
      parts.push("Deepfake branch did not return a score (no face or model unavailable).");
    }
    if (tampering != null) {
      parts.push(
        `Tampering / splice probability: ${pctLabel(tampering)} (${scoreNote(tampering)}).`
      );
    }
    if (synthetic != null) {
      parts.push(
        `Fully AI-generated face probability: ${pctLabel(synthetic)} (${scoreNote(synthetic)}).`
      );
    }
    if (caseData?.riskLevel) {
      parts.push(`Decision engine risk level: ${caseData.riskLevel}.`);
    }
    if (caseData?.latestVerdict?.finalVerdict) {
      parts.push(`Recorded verdict: ${caseData.latestVerdict.finalVerdict}.`);
    }
    if (overlayPath) {
      parts.push(
        "Grad-CAM visual evidence is attached when available (module 6.7)."
      );
    }
    return parts.join(" ");
  };

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      const pdf = new jsPDF("p", "mm", "a4");
      const W = 210;
      const margin = 14;
      const col = W - margin * 2;
      let y = 14;

      const hex = (color: string) => {
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        return [r, g, b] as [number, number, number];
      };
      const setColor = (c: string) => {
        pdf.setTextColor(...hex(c));
      };
      const setFill = (c: string) => {
        pdf.setFillColor(...hex(c));
      };
      const setDraw = (c: string) => {
        pdf.setDrawColor(...hex(c));
      };

      setColor("#0f172a");
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(18);
      pdf.text("FALSORA", margin, y);

      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(8);
      setColor("#64748b");
      y += 5;
      pdf.text(
        "Digital Media Forensics & Deepfake Verification Platform",
        margin,
        y
      );
      y += 4;
      pdf.text("Module 6.10 — Forensic Report Generation", margin, y);

      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(9);
      setColor("#0f172a");
      pdf.text(`REF: ${cId}`, W - margin, 14, { align: "right" });
      pdf.setFont("helvetica", "normal");
      setColor("#64748b");
      pdf.text(`Issued: ${date}`, W - margin, 19, { align: "right" });

      const flagColor = status === "Flagged" ? "#b91c1c" : status === "Verified" ? "#15803d" : "#475569";
      const flagBg = status === "Flagged" ? "#fee2e2" : status === "Verified" ? "#dcfce7" : "#f1f5f9";
      setFill(flagBg);
      setDraw(flagColor);
      pdf.setLineWidth(0.3);
      pdf.roundedRect(W - margin - 62, 22, 62, 6, 1, 1, "FD");
      pdf.setFontSize(7.5);
      pdf.setFont("helvetica", "bold");
      setColor(flagColor);
      pdf.text(
        `${verdictLabel} · ${status} (${confidence})`,
        W - margin - 2,
        26,
        { align: "right" }
      );

      y = 32;
      setDraw("#e2e8f0");
      pdf.setLineWidth(0.5);
      pdf.line(margin, y, W - margin, y);
      y += 6;

      setFill("#f8fafc");
      setDraw("#e2e8f0");
      pdf.roundedRect(margin, y, col, 24, 2, 2, "FD");
      pdf.setFontSize(7.5);
      setColor("#64748b");
      pdf.setFont("helvetica", "bold");
      pdf.text("Investigation Subject:", margin + 4, y + 5);
      pdf.text("Access Mode:", margin + col / 2 + 2, y + 5);
      pdf.text("Evidence File:", margin + 4, y + 13);
      pdf.text("SHA-256:", margin + col / 2 + 2, y + 13);
      pdf.setFont("helvetica", "normal");
      setColor("#0f172a");
      pdf.text(subject.substring(0, 40), margin + 4, y + 9);
      pdf.text(
        caseData?.accessMode === "public" ? "Public verification" : "Organizational",
        margin + col / 2 + 2,
        y + 9
      );
      pdf.text(fileName.substring(0, 36), margin + 4, y + 17);
      setColor("#1e40af");
      pdf.text(hash.substring(0, 28) + "…", margin + col / 2 + 2, y + 17);
      y += 30;

      const sectionTitle = (title: string) => {
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(8);
        setColor("#475569");
        pdf.text(title, margin, y);
        y += 5;
      };

      sectionTitle("1. EXECUTIVE SUMMARY & VERDICT");
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(8.5);
      setColor("#475569");
      const summaryLines = pdf.splitTextToSize(buildSummary(), col);
      pdf.text(summaryLines, margin, y);
      y += summaryLines.length * 4.5 + 6;

      sectionTitle("2. MODEL EVALUATION METRICS");
      const metrics = [
        {
          label: `Deepfake detector (${caseData?.forgery?.modelName || "EfficientNet"})`,
          score: deepfake,
        },
        {
          label: "Tampering / splice detector",
          score: tampering,
        },
        ...(synthetic != null
          ? [{ label: "AI-generated face detector (ViT)", score: synthetic }]
          : []),
      ];
      metrics.forEach(({ label, score }) => {
        const color = scoreColor(score);
        const pct = score == null ? 0 : Math.min(1, Math.max(0, score));
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(8);
        setColor("#0f172a");
        pdf.text(label, margin, y);
        setColor(color);
        pdf.text(
          `${pctLabel(score)} (${scoreNote(score)})`,
          W - margin,
          y,
          { align: "right" }
        );
        y += 3;
        setFill("#f1f5f9");
        pdf.roundedRect(margin, y, col, 3, 1, 1, "F");
        if (score != null) {
          setFill(color);
          pdf.roundedRect(margin, y, Math.max(2, col * pct), 3, 1, 1, "F");
        }
        y += 8;
      });
      y += 2;

      sectionTitle("3. EXTRACTED FILE METADATA");
      const metaRows: [string, string, string, string][] = [
        [
          "Format",
          caseData?.format || "image/*",
          "Accepted",
          "#16a34a",
        ],
        [
          "Resolution",
          caseData?.resolution || "Unknown",
          "Recorded",
          "#16a34a",
        ],
        [
          "SHA-256",
          hash.substring(0, 36) + "…",
          "Stored",
          "#16a34a",
        ],
        [
          "Device / EXIF",
          (caseData?.deviceFingerprint || "Unknown").substring(0, 32),
          caseData?.isTampered ? "Software flag" : "Inconclusive OK",
          caseData?.isTampered ? "#d97706" : "#16a34a",
        ],
      ];
      metaRows.forEach(([attr, val, st, stColor]) => {
        pdf.setFont("helvetica", "normal");
        pdf.setFontSize(7.5);
        setColor("#64748b");
        pdf.text(attr, margin, y);
        setColor("#0f172a");
        pdf.text(val, margin + 36, y);
        pdf.setFont("helvetica", "bold");
        setColor(stColor);
        pdf.text(st, W - margin, y, { align: "right" });
        y += 5;
      });
      y += 4;

      sectionTitle("4. AI INTERPRETABILITY (GRAD-CAM)");
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(8);
      setColor("#475569");
      if (overlayPath) {
        const explain =
          caseData?.forgery?.explanationText ||
          "Grad-CAM overlay highlights regions that most influenced the deepfake score.";
        const lines = pdf.splitTextToSize(explain, col);
        pdf.text(lines, margin, y);
        y += lines.length * 4 + 3;
        try {
          const imgRes = await fetch(`http://localhost:4000${overlayPath}`, {
            credentials: "include",
          });
          if (imgRes.ok) {
            const blob = await imgRes.blob();
            const dataUrl = await blobToDataUrl(blob);
            const imgH = 55;
            if (y + imgH > 280) {
              pdf.addPage();
              y = 16;
            }
            pdf.addImage(dataUrl, "PNG", margin, y, col, imgH);
            y += imgH + 6;
          }
        } catch (e) {
          pdf.text("(Grad-CAM image could not be embedded; see case detail UI.)", margin, y);
          y += 6;
        }
      } else {
        pdf.text(
          "No Grad-CAM artifact for this case (face not detected or explain skipped).",
          margin,
          y
        );
        y += 8;
      }

      if (y > 250) {
        pdf.addPage();
        y = 16;
      }
      setDraw("#e2e8f0");
      pdf.line(margin, y, W - margin, y);
      y += 6;
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(8);
      setColor("#0f172a");
      pdf.text("Falsora Forensic Assurance", margin, y);
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(7);
      setColor("#94a3b8");
      pdf.text(
        "Linked to case audit trail. Scoped for FYP demonstration — not a legal certification.",
        margin,
        y + 4
      );

      const filename = `Falsora_Forensic_Report_${cId.slice(0, 8)}.pdf`;
      const pdfBlob = pdf.output("blob");
      pdf.save(filename);

      // Persist to core-api Report table
      try {
        const form = new FormData();
        form.append("pdf", pdfBlob, filename);
        const saveRes = await fetch(
          `http://localhost:4000/api/cases/${cId}/reports`,
          { method: "POST", credentials: "include", body: form }
        );
        const saveData = await saveRes.json();
        if (saveRes.ok && saveData.success) {
          toast.success("Report downloaded and saved to case records");
          void loadReports();
        } else {
          toast.success("Report downloaded (cloud save skipped: " + (saveData.message || "error") + ")");
        }
      } catch {
        toast.success("Report downloaded (could not reach API to save copy)");
      }
    } catch (err) {
      console.error("PDF generation failed:", err);
      toast.error("Failed to generate PDF");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent
        showCloseButton={false}
        className="sm:max-w-4xl max-h-[90vh] overflow-hidden p-0 bg-background border-border/60 shadow-2xl flex flex-col"
      >
        <DialogHeader className="p-4 px-6 border-b border-border/50 bg-muted/30 flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            <div>
              <DialogTitle className="text-lg font-bold font-heading">
                Digital Forensic Report
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Falsora evidence verification record (module 6.10)
              </DialogDescription>
            </div>
          </div>
          <div className="flex items-center gap-2 print:hidden">
            <Button
              size="sm"
              onClick={() => void handleDownload()}
              disabled={isDownloading}
              className="gap-2 text-xs cursor-pointer"
            >
              {isDownloading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              {isDownloading ? "Generating PDF…" : "Download & Save"}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              className="h-8 w-8 text-muted-foreground hover:text-foreground cursor-pointer rounded-md"
              title="Close Modal"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </DialogHeader>

        <div className="p-8 overflow-y-auto flex-1 bg-card text-card-foreground print:p-0">
          <div
            ref={printRef}
            id="forensic-report-printable"
            className="max-w-3xl mx-auto space-y-6 text-sm"
          >
            <div className="flex justify-between items-start border-b-2 border-primary/20 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-black tracking-wider font-heading text-foreground">
                    FALSORA
                  </span>
                  <Badge
                    variant="outline"
                    className="text-[10px] font-mono border-primary/40 text-primary"
                  >
                    OFFICIAL REPORT
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Digital Media Forensics & Deepfake Verification Platform
                </p>
              </div>
              <div className="text-right space-y-1">
                <div className="text-xs font-mono font-bold">REF: {cId}</div>
                <div className="text-xs text-muted-foreground">Issued: {date}</div>
                <Badge
                  className={
                    status === "Flagged"
                      ? "bg-red-500/10 text-red-500 border-red-500/30"
                      : status === "Verified"
                        ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/30"
                        : "bg-muted text-muted-foreground"
                  }
                >
                  {status === "Flagged" ? (
                    <AlertTriangle className="h-3 w-3 mr-1" />
                  ) : (
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                  )}
                  {verdictLabel} · {status} ({confidence})
                </Badge>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 p-4 rounded-lg bg-muted/40">
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground font-medium">
                  Investigation Subject
                </span>
                <p className="font-semibold">{subject}</p>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground font-medium">
                  Access Mode
                </span>
                <p className="font-semibold flex items-center gap-1.5">
                  <User className="h-3.5 w-3.5 text-primary" />
                  {caseData?.accessMode === "public"
                    ? "Public verification"
                    : "Organizational workflow"}
                </p>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground font-medium">
                  Evidence File
                </span>
                <p className="font-mono text-xs font-semibold">{fileName}</p>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground font-medium">
                  SHA-256
                </span>
                <p className="font-mono text-[11px] text-primary truncate" title={hash}>
                  {hash.substring(0, 28)}…
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <ShieldAlert className="h-4 w-4 text-primary" /> 1. Executive Summary
              </h4>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {buildSummary()}
              </p>
            </div>

            <div className="space-y-3">
              <h4 className="font-bold text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Cpu className="h-4 w-4 text-primary" /> 2. Model Metrics
              </h4>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span>Deepfake face-swap</span>
                  <span
                    className="font-mono font-bold"
                    style={{ color: scoreColor(deepfake) }}
                  >
                    {pctLabel(deepfake)} ({scoreNote(deepfake)})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Tampering / splice</span>
                  <span
                    className="font-mono font-bold"
                    style={{ color: scoreColor(tampering) }}
                  >
                    {pctLabel(tampering)} ({scoreNote(tampering)})
                  </span>
                </div>
                {synthetic != null && (
                  <div className="flex justify-between">
                    <span>Fully AI-generated face</span>
                    <span
                      className="font-mono font-bold"
                      style={{ color: scoreColor(synthetic) }}
                    >
                      {pctLabel(synthetic)} ({scoreNote(synthetic)})
                    </span>
                  </div>
                )}
                {caseData?.riskLevel && (
                  <div className="flex justify-between">
                    <span>Decision risk level</span>
                    <span className="font-mono font-bold">{caseData.riskLevel}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Layers className="h-4 w-4 text-amber-500" /> 3. Grad-CAM Evidence
              </h4>
              {overlayPath ? (
                <div className="rounded-lg border border-border/50 overflow-hidden bg-black/80">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`http://localhost:4000${overlayPath}`}
                    alt="Grad-CAM overlay"
                    className="w-full max-h-56 object-contain"
                  />
                  <p className="text-[11px] text-muted-foreground p-2">
                    {caseData?.forgery?.explanationText ||
                      "Regions that most influenced the deepfake prediction."}
                  </p>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No Grad-CAM artifact stored for this case.
                </p>
              )}
            </div>

            <div className="space-y-2 border-t border-border/40 pt-4">
              <h4 className="font-bold text-xs uppercase tracking-wider text-muted-foreground">
                Saved case reports
              </h4>
              {loadingReports ? (
                <p className="text-xs text-muted-foreground">Loading…</p>
              ) : savedReports.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No PDF saved yet — click Download &amp; Save to link a report to this case.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {savedReports.map((r) => (
                    <li key={r.id} className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">
                        {r.generatedAt
                          ? new Date(r.generatedAt).toLocaleString()
                          : r.id.slice(0, 8)}
                      </span>
                      <a
                        href={`http://localhost:4000${r.pdfUrl}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        Open PDF <ExternalLink className="h-3 w-3" />
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
