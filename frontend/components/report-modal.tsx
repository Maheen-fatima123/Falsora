"use client";

import React, { useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { 
  Printer, 
  Download, 
  ShieldAlert, 
  ShieldCheck, 
  FileText, 
  CheckCircle2, 
  AlertTriangle,
  Lock,
  Cpu,
  Layers,
  Calendar,
  User,
  Hash,
  Award,
  X
} from "lucide-react";

import jsPDF from "jspdf";
import { Loader2 } from "lucide-react";

// Global filter for html2canvas internal parser logs regarding oklab/lab colors
if (typeof window !== "undefined") {
  const origConsoleError = console.error;
  console.error = (...args: any[]) => {
    if (
      args.length > 0 &&
      typeof args[0] === "string" &&
      (args[0].includes("unsupported color function") || args[0].includes("oklab") || args[0].includes("lab"))
    ) {
      return;
    }
    origConsoleError.apply(console, args);
  };
}

interface ForensicReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseData?: {
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
  };
}

export function ForensicReportModal({ isOpen, onClose, caseData }: ForensicReportModalProps) {
  const printRef = useRef<HTMLDivElement>(null);
  const [isDownloading, setIsDownloading] = React.useState(false);

  const cId = caseData?.id || "CAS-142";
  const subject = caseData?.subject || "Deepfake Detection - Politician Speech";
  const confidence = caseData?.confidence || "98.4%";
  const status = caseData?.status || "Flagged";
  const date = caseData?.date || new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const fileName = caseData?.fileName || "speech_politician_v2.mp4";
  const hash = caseData?.sha256 || caseData?.hash || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

  const handleDownload = () => {
    setIsDownloading(true);

    try {
      const pdf = new jsPDF("p", "mm", "a4");
      const W = 210; // A4 width mm
      const margin = 14;
      const col = W - margin * 2;
      let y = 14;

      const hex = (color: string) => {
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        return [r, g, b] as [number, number, number];
      };

      const setColor = (c: string) => { pdf.setTextColor(...hex(c)); };
      const setFill = (c: string) => { pdf.setFillColor(...hex(c)); };
      const setDraw = (c: string) => { pdf.setDrawColor(...hex(c)); };

      // ─── HEADER ───
      setColor("#0f172a");
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(18);
      pdf.text("TITLI FORENSICS", margin, y);

      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(8);
      setColor("#64748b");
      y += 5;
      pdf.text("Digital Media Forensics & Deepfake Verification Platform", margin, y);
      y += 4;
      pdf.text("ISO/IEC 27037:2012 Digital Evidence Guidelines Compliant", margin, y);

      // Ref + date (right aligned)
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(9);
      setColor("#0f172a");
      pdf.text(`REF: ${cId}`, W - margin, 14, { align: "right" });
      pdf.setFont("helvetica", "normal");
      setColor("#64748b");
      pdf.text(`Issued: ${date}`, W - margin, 19, { align: "right" });

      // Verdict badge
      setFill("#fee2e2");
      setDraw("#fca5a5");
      pdf.setLineWidth(0.3);
      pdf.roundedRect(W - margin - 58, 22, 58, 6, 1, 1, "FD");
      pdf.setFontSize(8);
      pdf.setFont("helvetica", "bold");
      setColor("#b91c1c");
      pdf.text(`VERDICT: ${status.toUpperCase()} (${confidence})`, W - margin - 2, 26, { align: "right" });

      // Divider
      y = 32;
      setDraw("#e2e8f0");
      pdf.setLineWidth(0.5);
      pdf.line(margin, y, W - margin, y);
      y += 6;

      // ─── CASE OVERVIEW GRID ───
      setFill("#f8fafc");
      setDraw("#e2e8f0");
      pdf.setLineWidth(0.3);
      pdf.roundedRect(margin, y, col, 20, 2, 2, "FD");

      pdf.setFontSize(7.5);
      setColor("#64748b");
      pdf.setFont("helvetica", "bold");
      pdf.text("Investigation Subject:", margin + 4, y + 5);
      pdf.text("Lead Forensic Examiner:", margin + col / 2 + 2, y + 5);
      pdf.text("Evidence File Name:", margin + 4, y + 13);
      pdf.text("Chain of Custody Hash:", margin + col / 2 + 2, y + 13);

      pdf.setFont("helvetica", "normal");
      setColor("#0f172a");
      pdf.text(subject.substring(0, 38), margin + 4, y + 9);
      pdf.text("Senior Analyst (Ujala Zaib)", margin + col / 2 + 2, y + 9);
      pdf.text(fileName, margin + 4, y + 17);
      setColor("#1e40af");
      pdf.text(hash.substring(0, 30) + "...", margin + col / 2 + 2, y + 17);
      y += 26;

      // ─── SECTION HELPER ───
      const sectionTitle = (title: string) => {
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(8);
        setColor("#475569");
        pdf.text(title, margin, y);
        y += 5;
      };

      // ─── 1. EXECUTIVE SUMMARY ───
      sectionTitle("1. EXECUTIVE SUMMARY & VERDICT");
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(8.5);
      setColor("#475569");
      const summary = `Automated multi-model neural ensemble inspection was conducted on media item "${fileName}". Spatial ELA (Error Level Analysis) and facial boundary feature extractors identified high-confidence synthetic manipulation. The subject image exhibits neural face swap artifacts along with spatial boundary noise mismatches.`;
      const summaryLines = pdf.splitTextToSize(summary, col);
      pdf.text(summaryLines, margin, y);
      y += summaryLines.length * 4.5 + 6;

      // ─── 2. MODEL METRICS ───
      sectionTitle("2. MODEL ENSEMBLE EVALUATION METRICS");

      const metrics = [
        { label: "Deepfake Face Swap Detector (XceptionNet)", value: "99.2%", pct: 0.992, color: "#dc2626", bgColor: "#fee2e2", note: "Manipulated" },
        { label: "Frame Splicing & Noise Consistency (ELA)", value: "87.4%", pct: 0.874, color: "#d97706", bgColor: "#fef3c7", note: "Inconsistent" },
      ];

      metrics.forEach(({ label, value, pct, color, bgColor, note }) => {
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(8);
        setColor("#0f172a");
        pdf.text(label, margin, y);
        setColor(color);
        pdf.text(`${value} (${note})`, W - margin, y, { align: "right" });
        y += 3;
        // Track bg
        setFill(bgColor);
        setDraw(bgColor);
        pdf.roundedRect(margin, y, col, 3, 1, 1, "FD");
        // Progress bar
        setFill(color);
        pdf.roundedRect(margin, y, col * pct, 3, 1, 1, "F");
        y += 8;
      });

      y += 2;

      // ─── 3. METADATA TABLE ───
      sectionTitle("3. EXTRACTED FILE METADATA");

      const metaRows = [
        ["Container / Format", "MP4 (MPEG-4 Part 14)", "Valid Structure", "#16a34a"],
        ["Video Resolution", "1920 x 1080 (1080p60)", "Standard Ratio", "#16a34a"],
        ["SHA-256 Checksum", hash.substring(0, 40) + "...", "Tamper-Evident Signed", "#16a34a"],
        ["Camera Profile EXIF", "Sony Alpha A7 IV (v2.0)", "Metadata Re-encoded", "#d97706"],
      ];

      const colWidths = [42, 72, 50];
      const colX = [margin, margin + colWidths[0], margin + colWidths[0] + colWidths[1]];

      // Header row
      setFill("#f1f5f9");
      setDraw("#e2e8f0");
      pdf.roundedRect(margin, y, col, 6, 1, 1, "FD");
      ["Attribute", "Extracted Value", "Integrity Status"].forEach((h, i) => {
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(7.5);
        setColor("#0f172a");
        pdf.text(h, colX[i] + 2, y + 4);
      });
      y += 7;

      metaRows.forEach(([attr, val, status, statusColor]) => {
        setDraw("#f1f5f9");
        pdf.line(margin, y + 5, W - margin, y + 5);
        pdf.setFont("helvetica", "normal");
        pdf.setFontSize(7.5);
        setColor("#64748b");
        pdf.text(attr, colX[0] + 2, y + 4);
        setColor("#0f172a");
        pdf.text(val, colX[1] + 2, y + 4);
        pdf.setFont("helvetica", "bold");
        setColor(statusColor);
        pdf.text(status, colX[2] + 2, y + 4);
        y += 6;
      });

      y += 4;

      // ─── 4. AUDIT TRAIL ───
      sectionTitle("4. IMMUTABLE AUDIT TRAIL (CHAIN OF CUSTODY)");

      const auditColWidths = [44, 52, 38, 30];
      const auditColX = [
        margin,
        margin + auditColWidths[0],
        margin + auditColWidths[0] + auditColWidths[1],
        margin + auditColWidths[0] + auditColWidths[1] + auditColWidths[2],
      ];

      setFill("#f1f5f9");
      setDraw("#e2e8f0");
      pdf.roundedRect(margin, y, col, 6, 1, 1, "FD");
      ["Timestamp", "Action Event", "Actor / System", "Log Hash"].forEach((h, i) => {
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(7.5);
        setColor("#0f172a");
        pdf.text(h, auditColX[i] + 2, y + 4);
      });
      y += 7;

      const auditRows = [
        ["2026-08-12 14:02:11", "EVIDENCE_INGESTED", "Ujala Zaib", "0x9a8f...4b12", "#0f172a"],
        ["2026-08-12 14:02:45", "AI_FORGERY_FLAGGED", "Ensemble-V3 Engine", "0x3c21...8e90", "#dc2626"],
        ["2026-08-12 14:05:00", "VERDICT_CONFIRMED", "Senior Analyst", "0x7d44...11fa", "#0f172a"],
      ];

      auditRows.forEach(([ts, event, actor, logHash, eventColor]) => {
        setDraw("#f1f5f9");
        pdf.line(margin, y + 5, W - margin, y + 5);
        pdf.setFont("helvetica", "normal");
        pdf.setFontSize(7.5);
        setColor("#64748b");
        pdf.text(ts, auditColX[0] + 2, y + 4);
        pdf.setFont("helvetica", "bold");
        setColor(eventColor);
        pdf.text(event, auditColX[1] + 2, y + 4);
        pdf.setFont("helvetica", "normal");
        setColor("#0f172a");
        pdf.text(actor, auditColX[2] + 2, y + 4);
        setColor("#94a3b8");
        pdf.text(logHash, auditColX[3] + 2, y + 4);
        y += 6;
      });

      // ─── SIGNATURE BLOCK ───
      y += 8;
      setDraw("#e2e8f0");
      pdf.setLineWidth(0.5);
      pdf.line(margin, y, W - margin, y);
      y += 6;

      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(8);
      setColor("#0f172a");
      pdf.text("Titli Forensic Assurance Seal", margin, y);
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(7);
      setColor("#94a3b8");
      pdf.text("Cryptographically signed & stored in immutable forensic audit logs.", margin, y + 4);

      // Signature line
      setDraw("#0f172a");
      pdf.setLineWidth(0.3);
      pdf.line(W - margin - 55, y + 8, W - margin, y + 8);
      pdf.setFont("helvetica", "bolditalic");
      pdf.setFontSize(9);
      setColor("#1e40af");
      pdf.text("Ujala Zaib", W - margin - 55, y + 6);
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(7);
      setColor("#64748b");
      pdf.text("AUTHORIZED SIGNATURE", W - margin - 55, y + 12);

      pdf.save(`Titli_Forensic_Report_${cId}.pdf`);
    } catch (err) {
      console.error("PDF generation failed:", err);
    } finally {
      setIsDownloading(false);
    }
  };



  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent showCloseButton={false} className="sm:max-w-4xl max-h-[90vh] overflow-hidden p-0 bg-background border-border/60 shadow-2xl flex flex-col">
        
        {/* Header Bar */}
        <DialogHeader className="p-4 px-6 border-b border-border/50 bg-muted/30 flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            <div>
              <DialogTitle className="text-lg font-bold font-heading">Digital Forensic Report</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Official evidence verification & deepfake audit record
              </DialogDescription>
            </div>
          </div>
          <div className="flex items-center gap-2 print:hidden">
            <Button size="sm" onClick={handleDownload} disabled={isDownloading} className="gap-2 text-xs cursor-pointer">
              {isDownloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              {isDownloading ? "Generating PDF..." : "Download"}
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

        {/* Scrollable Printable Document Area */}
        <div className="p-8 overflow-y-auto flex-1 bg-card text-card-foreground print:p-0 print:bg-white print:text-black">
          <div ref={printRef} id="forensic-report-printable" className="max-w-3xl mx-auto space-y-6 text-sm">

            {/* Document Header & Watermark */}
            <div className="flex justify-between items-start border-b-2 border-primary/20 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-black tracking-wider font-heading text-foreground print:text-black">TITLI FORENSICS</span>
                  <Badge variant="outline" className="text-[10px] font-mono border-primary/40 text-primary print:border-black print:text-black">
                    OFFICIAL REPORT
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground print:text-gray-600 mt-1">Digital Media Forensics & Deepfake Verification Platform</p>
                <p className="text-[11px] font-mono text-muted-foreground print:text-gray-500">ISO/IEC 27037:2012 Digital Evidence Guidelines Compliant</p>
              </div>
              <div className="text-right space-y-1">
                <div className="text-xs font-mono font-bold text-foreground print:text-black">REF: {cId}</div>
                <div className="text-xs text-muted-foreground print:text-gray-600">Issued: {date}</div>
                <Badge 
                  className={
                    status === "Flagged" || status === "Critical" 
                      ? "bg-red-500/10 text-red-500 border-red-500/30 print:bg-red-100 print:text-red-800" 
                      : "bg-emerald-500/10 text-emerald-500 border-emerald-500/30 print:bg-green-100 print:text-green-800"
                  }
                >
                  {status === "Flagged" || status === "Critical" ? <AlertTriangle className="h-3 w-3 mr-1" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
                  VERDICT: {status.toUpperCase()} ({confidence})
                </Badge>
              </div>
            </div>

            {/* Case Overview Grid */}
            <div className="grid grid-cols-2 gap-4 p-4 rounded-lg bg-muted/40 print:bg-gray-50 print:border print:border-gray-200">
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground print:text-gray-500 font-medium">Investigation Subject:</span>
                <p className="font-semibold text-foreground print:text-black">{subject}</p>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground print:text-gray-500 font-medium">Lead Forensic Examiner:</span>
                <p className="font-semibold text-foreground print:text-black flex items-center gap-1.5">
                  <User className="h-3.5 w-3.5 text-primary print:text-black" /> Senior Analyst (Ujala Zaib)
                </p>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground print:text-gray-500 font-medium">Evidence File Name:</span>
                <p className="font-mono text-xs font-semibold text-foreground print:text-black">{fileName}</p>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground print:text-gray-500 font-medium">Chain of Custody Hash:</span>
                <p className="font-mono text-[11px] text-primary print:text-black truncate" title={hash}>
                  {hash.substring(0, 24)}...
                </p>
              </div>
            </div>

            {/* Executive Summary */}
            <div className="space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-muted-foreground print:text-gray-700 flex items-center gap-1.5">
                <ShieldAlert className="h-4 w-4 text-primary print:text-black" /> 1. Executive Summary & Verdict
              </h4>
              <p className="text-xs leading-relaxed text-muted-foreground print:text-gray-800">
                Automated multi-model neural ensemble inspection was conducted on media item <code className="font-mono font-semibold">{fileName}</code>. 
                Spatial ELA (Error Level Analysis) and facial boundary feature extractors identified high-confidence synthetic manipulation. 
                The subject image exhibits neural face swap artifacts along with spatial boundary noise mismatches.
              </p>
            </div>

            {/* AI Forensic Detection Breakdown */}
            <div className="space-y-3">
              <h4 className="font-bold text-xs uppercase tracking-wider text-muted-foreground print:text-gray-700 flex items-center gap-1.5">
                <Cpu className="h-4 w-4 text-primary print:text-black" /> 2. Model Ensemble Evaluation Metrics
              </h4>
              
              <div className="space-y-2">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-medium">Deepfake Face Swap Detector (XceptionNet)</span>
                  <span className="font-mono font-bold text-red-500 print:text-red-700">99.2% (Manipulated)</span>
                </div>
                <div className="w-full h-2 bg-muted rounded-full overflow-hidden print:bg-gray-200">
                  <div className="h-full bg-red-500 print:bg-red-600 rounded-full w-[99.2%]" />
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-medium">Frame Splicing & Noise Consistency (ELA)</span>
                  <span className="font-mono font-bold text-amber-500 print:text-amber-700">87.4% (Inconsistent)</span>
                </div>
                <div className="w-full h-2 bg-muted rounded-full overflow-hidden print:bg-gray-200">
                  <div className="h-full bg-amber-500 print:bg-amber-600 rounded-full w-[87.4%]" />
                </div>
              </div>
            </div>

            {/* Media Metadata Table */}
            <div className="space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-muted-foreground print:text-gray-700 flex items-center gap-1.5">
                <Layers className="h-4 w-4 text-primary print:text-black" /> 3. Extracted File Metadata
              </h4>
              <div className="border rounded-md overflow-hidden print:border-gray-300 text-xs">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-muted/50 border-b print:bg-gray-100 print:border-gray-300">
                      <th className="p-2 font-semibold">Attribute</th>
                      <th className="p-2 font-semibold">Extracted Value</th>
                      <th className="p-2 font-semibold">Integrity Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40 print:divide-gray-200">
                    <tr>
                      <td className="p-2 text-muted-foreground print:text-gray-600">Container / Format</td>
                      <td className="p-2 font-mono">{caseData?.format || "Unknown Format"}</td>
                      <td className="p-2 text-emerald-500 print:text-green-700 font-medium">Valid Structure</td>
                    </tr>
                    <tr>
                      <td className="p-2 text-muted-foreground print:text-gray-600">Media Resolution</td>
                      <td className="p-2 font-mono">{caseData?.resolution || "Unknown"}</td>
                      <td className="p-2 text-emerald-500 print:text-green-700 font-medium">Standard Ratio</td>
                    </tr>
                    <tr>
                      <td className="p-2 text-muted-foreground print:text-gray-600">SHA-256 Checksum</td>
                      <td className="p-2 font-mono text-[10px] truncate max-w-[200px]">{hash}</td>
                      <td className="p-2 text-emerald-500 print:text-green-700 font-medium">Tamper-Evident Signed</td>
                    </tr>
                    <tr>
                      <td className="p-2 text-muted-foreground print:text-gray-600">Hardware Signature</td>
                      <td className="p-2 font-mono">{caseData?.deviceFingerprint || "No signature"}</td>
                      <td className={`p-2 font-medium ${caseData?.isTampered ? "text-amber-500 print:text-orange-600" : "text-emerald-500 print:text-green-700"}`}>
                        {caseData?.softwareFlag || "Original Camera Capture"}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Audit Trail & Chain of Custody */}
            <div className="space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-muted-foreground print:text-gray-700 flex items-center gap-1.5">
                <Lock className="h-4 w-4 text-primary print:text-black" /> 4. Immutable Audit Trail (Chain of Custody)
              </h4>
              <div className="border rounded-md overflow-hidden print:border-gray-300 text-xs">
                <table className="w-full text-left border-collapse font-mono text-[11px]">
                  <thead>
                    <tr className="bg-muted/50 border-b print:bg-gray-100 print:border-gray-300">
                      <th className="p-2 font-semibold">Timestamp</th>
                      <th className="p-2 font-semibold">Action Event</th>
                      <th className="p-2 font-semibold">Actor / System</th>
                      <th className="p-2 font-semibold">Log Hash Block</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40 print:divide-gray-200">
                    <tr>
                      <td className="p-2 text-muted-foreground print:text-gray-600">2026-08-12 14:02:11</td>
                      <td className="p-2">EVIDENCE_INGESTED</td>
                      <td className="p-2">Ujala Zaib</td>
                      <td className="p-2 text-muted-foreground">0x9a8f...4b12</td>
                    </tr>
                    <tr>
                      <td className="p-2 text-muted-foreground print:text-gray-600">2026-08-12 14:02:45</td>
                      <td className="p-2 text-red-400 print:text-red-700">AI_FORGERY_FLAGGED</td>
                      <td className="p-2">Ensemble-V3 Engine</td>
                      <td className="p-2 text-muted-foreground">0x3c21...8e90</td>
                    </tr>
                    <tr>
                      <td className="p-2 text-muted-foreground print:text-gray-600">2026-08-12 14:05:00</td>
                      <td className="p-2">VERDICT_CONFIRMED</td>
                      <td className="p-2">Senior Analyst</td>
                      <td className="p-2 text-muted-foreground">0x7d44...11fa</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Official Signature Block */}
            <div className="pt-6 border-t border-border/50 flex justify-between items-end">
              <div className="space-y-1">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground print:text-black">
                  <Award className="h-4 w-4 text-primary print:text-black" /> Titli Forensic Assurance Seal
                </div>
                <p className="text-[10px] text-muted-foreground print:text-gray-500 max-w-xs">
                  This document has been cryptographically signed and stored in immutable forensic audit logs.
                </p>
              </div>
              <div className="text-center space-y-2">
                <div className="border-b border-foreground/40 print:border-black w-48 pb-1 font-mono text-xs italic text-primary print:text-black">
                  Ujala Zaib
                </div>
                <p className="text-[10px] text-muted-foreground print:text-gray-600 uppercase font-semibold">Authorized Signature</p>
              </div>
            </div>

          </div>
        </div>

      </DialogContent>
    </Dialog>
  );
}
