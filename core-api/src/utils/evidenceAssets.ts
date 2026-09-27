import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const evidenceDir = path.join(process.cwd(), "uploads", "evidence");

function ensureEvidenceDir(): void {
  if (!fs.existsSync(evidenceDir)) {
    fs.mkdirSync(evidenceDir, { recursive: true });
  }
}

/**
 * Copy a Grad-CAM PNG from the AI engine's local path into core-api static
 * storage so the browser can load it via http://localhost:4000/uploads/...
 */
export function publishEvidenceFile(
  sourcePath: string | null | undefined,
  kind: "overlay" | "heatmap",
  caseId?: string
): string | null {
  if (!sourcePath) return null;
  try {
    const resolved = path.resolve(sourcePath);
    if (!fs.existsSync(resolved)) {
      console.warn(`publishEvidenceFile: missing source ${resolved}`);
      return null;
    }
    ensureEvidenceDir();
    const stem = `${(caseId || "case").slice(0, 8)}-${kind}-${crypto
      .randomBytes(4)
      .toString("hex")}.png`;
    const dest = path.join(evidenceDir, stem);
    fs.copyFileSync(resolved, dest);
    return `/uploads/evidence/${stem}`;
  } catch (err) {
    console.warn("publishEvidenceFile failed:", err);
    return null;
  }
}

export type PublishedExplanation = {
  overlayUrl: string | null;
  heatmapUrl: string | null;
  method: string;
  targetLayer: string;
  summary: string;
};

export function publishExplanationArtifacts(
  explanation: {
    overlay_path?: string;
    heatmap_path?: string | null;
    method?: string;
    target_layer?: string;
  } | null,
  caseId?: string
): PublishedExplanation | null {
  if (!explanation) return null;
  const overlayUrl = publishEvidenceFile(explanation.overlay_path, "overlay", caseId);
  const heatmapUrl = publishEvidenceFile(
    explanation.heatmap_path || undefined,
    "heatmap",
    caseId
  );
  const method = explanation.method || "gradcam";
  const targetLayer = explanation.target_layer || "unknown";
  return {
    overlayUrl,
    heatmapUrl,
    method,
    targetLayer,
    summary: `Grad-CAM (${method}) highlighting regions that most influenced the deepfake score. Target layer: ${targetLayer}.`,
  };
}

/**
 * If DB still holds an absolute filesystem path (pre-6.7), try to publish it
 * once so the UI can render.
 */
export function ensurePublicMediaUrl(
  stored: string | null | undefined,
  caseId?: string
): string | null {
  if (!stored) return null;
  if (stored.startsWith("/uploads/")) return stored;
  if (stored.startsWith("http://") || stored.startsWith("https://")) return stored;
  // Absolute local path from AI engine
  if (path.isAbsolute(stored) || stored.includes("gradcam") || stored.includes("\\")) {
    return publishEvidenceFile(stored, "overlay", caseId);
  }
  return stored;
}

export function parseExplanationMeta(explanationText: string | null | undefined): {
  overlayUrl?: string;
  heatmapUrl?: string;
  method?: string;
  targetLayer?: string;
  summary?: string;
} | null {
  if (!explanationText) return null;
  try {
    const parsed = JSON.parse(explanationText);
    if (parsed && typeof parsed === "object") return parsed;
  } catch {
    /* plain text legacy */
  }
  return { summary: explanationText };
}
