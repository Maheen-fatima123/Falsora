import path from "node:path";
import fs from "node:fs";

/** Supported image formats for module 6.2 (static verification path). */
export const ALLOWED_MIME = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
]);

export const ALLOWED_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
]);

/** Minimum edge length (px) — reject tiny / empty-ish images. */
export const MIN_DIMENSION = 64;

/** Maximum edge before preprocess downscale (px). */
export const MAX_EDGE = 2048;

/** Multer / API file size limit (bytes). */
export const MAX_FILE_BYTES = 10 * 1024 * 1024;

export type DetectedImageFormat = "jpeg" | "png" | "webp" | "unknown";

/**
 * Detect image type from magic bytes (not from the client MIME or extension).
 */
export function detectImageFormat(buffer: Buffer): DetectedImageFormat {
  if (buffer.length < 12) return "unknown";

  // JPEG: FF D8 FF
  if (buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) {
    return "jpeg";
  }

  // PNG: 89 50 4E 47 0D 0A 1A 0A
  if (
    buffer[0] === 0x89 &&
    buffer[1] === 0x50 &&
    buffer[2] === 0x4e &&
    buffer[3] === 0x47 &&
    buffer[4] === 0x0d &&
    buffer[5] === 0x0a &&
    buffer[6] === 0x1a &&
    buffer[7] === 0x0a
  ) {
    return "png";
  }

  // WEBP: RIFF....WEBP
  if (
    buffer[0] === 0x52 &&
    buffer[1] === 0x49 &&
    buffer[2] === 0x46 &&
    buffer[3] === 0x46 &&
    buffer[8] === 0x57 &&
    buffer[9] === 0x45 &&
    buffer[10] === 0x42 &&
    buffer[11] === 0x50
  ) {
    return "webp";
  }

  return "unknown";
}

export function formatToMime(format: DetectedImageFormat): string | null {
  switch (format) {
    case "jpeg":
      return "image/jpeg";
    case "png":
      return "image/png";
    case "webp":
      return "image/webp";
    default:
      return null;
  }
}

export type ValidationResult =
  | {
      ok: true;
      status: "VALIDATED";
      detectedFormat: DetectedImageFormat;
      mime: string;
      width: number;
      height: number;
      bytes: number;
    }
  | {
      ok: false;
      status: "REJECTED";
      reason: string;
      code:
        | "EMPTY"
        | "TOO_LARGE"
        | "BAD_MAGIC"
        | "MIME_MISMATCH"
        | "EXT_MISMATCH"
        | "TOO_SMALL"
        | "UNREADABLE";
      detectedFormat?: DetectedImageFormat;
    };

/**
 * Validate an uploaded image buffer against format + quality rules (6.2).
 */
export function validateImageBuffer(
  buffer: Buffer,
  opts: {
    originalName?: string;
    declaredMime?: string;
  } = {}
): ValidationResult {
  if (!buffer || buffer.length === 0) {
    return { ok: false, status: "REJECTED", reason: "Empty file.", code: "EMPTY" };
  }

  if (buffer.length > MAX_FILE_BYTES) {
    return {
      ok: false,
      status: "REJECTED",
      reason: `File exceeds ${MAX_FILE_BYTES / (1024 * 1024)}MB limit.`,
      code: "TOO_LARGE",
    };
  }

  const detectedFormat = detectImageFormat(buffer);
  const mime = formatToMime(detectedFormat);
  if (!mime || detectedFormat === "unknown") {
    return {
      ok: false,
      status: "REJECTED",
      reason:
        "File content is not a supported image (JPEG, PNG, or WEBP). Extension alone is not enough.",
      code: "BAD_MAGIC",
      detectedFormat,
    };
  }

  const ext = path.extname(opts.originalName || "").toLowerCase();
  if (ext && !ALLOWED_EXTENSIONS.has(ext)) {
    return {
      ok: false,
      status: "REJECTED",
      reason: `Extension ${ext} is not allowed. Use .jpg, .jpeg, .png, or .webp.`,
      code: "EXT_MISMATCH",
      detectedFormat,
    };
  }

  // Extension should agree with magic bytes when present
  if (ext) {
    const extOk =
      (detectedFormat === "jpeg" && (ext === ".jpg" || ext === ".jpeg")) ||
      (detectedFormat === "png" && ext === ".png") ||
      (detectedFormat === "webp" && ext === ".webp");
    if (!extOk) {
      return {
        ok: false,
        status: "REJECTED",
        reason: `File extension (${ext}) does not match actual image type (${detectedFormat}).`,
        code: "EXT_MISMATCH",
        detectedFormat,
      };
    }
  }

  const declared = (opts.declaredMime || "").toLowerCase();
  if (declared && declared !== "application/octet-stream" && !ALLOWED_MIME.has(declared)) {
    return {
      ok: false,
      status: "REJECTED",
      reason: `Declared MIME ${declared} is not an allowed image type.`,
      code: "MIME_MISMATCH",
      detectedFormat,
    };
  }

  // Dimensions checked via sharp in the async wrapper (see validateUploadedImage)
  return {
    ok: true,
    status: "VALIDATED",
    detectedFormat,
    mime,
    width: 0,
    height: 0,
    bytes: buffer.length,
  };
}

export function safeUnlink(filePath: string | undefined | null): void {
  if (!filePath) return;
  try {
    if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
  } catch {
    /* ignore */
  }
}
