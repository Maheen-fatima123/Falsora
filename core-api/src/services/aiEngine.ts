/**
 * AI Engine Client — core-api → ai-engine (port 8000)
 *
 * Wraps the M9 static-analysis endpoint (`/ai/forgery/analyze`) that runs
 * the real deepfake + tampering models and, optionally, Grad-CAM
 * interpretability. Mirrors the same fail-soft pattern as
 * decisionEngine.ts: on any error/timeout the caller gets `null` back and
 * the upload pipeline falls back to its pre-AI defaults rather than
 * failing the whole request.
 */

const AI_ENGINE_URL = process.env.AI_ENGINE_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types (mirror falsora_ai.contracts — ForgeryResult / Explanation)
// ---------------------------------------------------------------------------

export interface DeepfakeSignal {
  probability_fake: number;
  authenticity: number;
  model_name: string;
  model_version: string;
  input_size: number;
  quantized: boolean;
}

export interface TamperingSignal {
  probability_tampered: number;
  ela_score: number | null;
  residual_score: number | null;
  model_name: string;
  model_version: string;
}

export interface ForgeryResultPayload {
  result_id: string;
  case_id: string | null;
  mode: string;
  face_detected: boolean;
  deepfake: DeepfakeSignal | null;
  tampering: TamperingSignal | null;
  latency_ms: number;
  warnings: string[];
}

export interface ExplanationPayload {
  explanation_id: string;
  result_id: string;
  method: string;
  target_layer: string;
  overlay_path: string;
  heatmap_path: string | null;
}

export interface ForgeryAnalysis {
  forgery_result: ForgeryResultPayload;
  explanation: ExplanationPayload | null;
}

/**
 * Send an uploaded image to the AI engine for deepfake + tampering
 * analysis. Called from the case upload pipeline once the file is on disk.
 */
export async function analyzeForgery(
  fileBuffer: Buffer,
  filename: string,
  mimeType: string,
  caseId?: string
): Promise<ForgeryAnalysis | null> {
  try {
    const form = new FormData();
    const arrayBuffer = fileBuffer.buffer.slice(
      fileBuffer.byteOffset,
      fileBuffer.byteOffset + fileBuffer.byteLength
    ) as ArrayBuffer;
    form.append("file", new Blob([arrayBuffer], { type: mimeType || "image/png" }), filename);
    if (caseId) form.append("case_id", caseId);
    form.append("explain", "true");

    const res = await fetch(`${AI_ENGINE_URL}/ai/forgery/analyze`, {
      method: "POST",
      body: form,
      // Model inference is slower than the decision-engine's rule lookups.
      signal: AbortSignal.timeout(30000),
    });
    if (!res.ok) {
      console.warn(`[ai-engine] /ai/forgery/analyze returned ${res.status}`);
      return null;
    }
    return (await res.json()) as ForgeryAnalysis;
  } catch (err) {
    console.warn("[ai-engine] /ai/forgery/analyze unreachable — degrading gracefully:", err);
    return null;
  }
}
