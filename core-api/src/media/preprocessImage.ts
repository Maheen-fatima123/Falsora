import path from "node:path";
import fs from "node:fs";
import sharp from "sharp";
import {
  MAX_EDGE,
  MIN_DIMENSION,
  type ValidationResult,
  validateImageBuffer,
} from "./validateUpload";

export type PreprocessResult = {
  /** Absolute path of the file used for analysis (may equal original). */
  processedPath: string;
  /** Public URL path under /uploads/ */
  storageUrl: string;
  /** Bytes fed to AI after preprocess */
  buffer: Buffer;
  /** Original upload bytes (for SHA-256 / EXIF) */
  originalBuffer: Buffer;
  mime: string;
  width: number;
  height: number;
  /** True when we re-encoded / resized */
  changed: boolean;
  originalBytes: number;
  processedBytes: number;
};

/**
 * Full 6.2 pipeline: magic-byte validate → dimension gate → preprocess for analysis.
 */
export async function validateAndPreprocessImage(opts: {
  absolutePath: string;
  originalName: string;
  declaredMime?: string;
  uploadDir: string;
}): Promise<
  | { ok: true; validation: Extract<ValidationResult, { ok: true }>; preprocess: PreprocessResult }
  | { ok: false; validation: Extract<ValidationResult, { ok: false }> }
> {
  const originalBytes = fs.readFileSync(opts.absolutePath);
  const base = validateImageBuffer(originalBytes, {
    originalName: opts.originalName,
    declaredMime: opts.declaredMime,
  });

  if (!base.ok) {
    return { ok: false, validation: base };
  }

  let meta: sharp.Metadata;
  try {
    meta = await sharp(originalBytes, { failOn: "none" }).metadata();
  } catch {
    return {
      ok: false,
      validation: {
        ok: false,
        status: "REJECTED",
        reason: "Image could not be decoded (corrupt or unsupported).",
        code: "UNREADABLE",
        detectedFormat: base.detectedFormat,
      },
    };
  }

  const width = meta.width || 0;
  const height = meta.height || 0;
  if (width < MIN_DIMENSION || height < MIN_DIMENSION) {
    return {
      ok: false,
      validation: {
        ok: false,
        status: "REJECTED",
        reason: `Image too small (${width}×${height}). Minimum ${MIN_DIMENSION}×${MIN_DIMENSION}px.`,
        code: "TOO_SMALL",
        detectedFormat: base.detectedFormat,
      },
    };
  }

  const validation: Extract<ValidationResult, { ok: true }> = {
    ...base,
    width,
    height,
  };

  const needsResize = Math.max(width, height) > MAX_EDGE;
  // Normalize to JPEG for analysis stability (except keep PNG if already small PNG with alpha needs — use JPEG always for AI path simplicity)
  const outName = `processed-${Date.now()}-${Math.round(Math.random() * 1e9)}.jpg`;
  const processedPath = path.join(opts.uploadDir, outName);

  let pipeline = sharp(originalBytes, { failOn: "none" }).rotate(); // honour EXIF orientation
  if (needsResize) {
    pipeline = pipeline.resize({
      width: MAX_EDGE,
      height: MAX_EDGE,
      fit: "inside",
      withoutEnlargement: true,
    });
  }

  const outBuffer = await pipeline
    .jpeg({ quality: 92, mozjpeg: true })
    .toBuffer();

  fs.writeFileSync(processedPath, outBuffer);

  const outMeta = await sharp(outBuffer).metadata();

  return {
    ok: true,
    validation,
    preprocess: {
      processedPath,
      storageUrl: `/uploads/${outName}`,
      buffer: outBuffer,
      originalBuffer: originalBytes,
      mime: "image/jpeg",
      width: outMeta.width || width,
      height: outMeta.height || height,
      changed: true,
      originalBytes: originalBytes.length,
      processedBytes: outBuffer.length,
    },
  };
}
