import { prisma } from "../db";
import crypto from "node:crypto";

export async function appendAuditLog({
  caseId,
  userId,
  action,
  metadataJson,
}: {
  caseId: string;
  userId: string;
  action: string;
  metadataJson?: any;
}) {
  try {
    // 1. Fetch the most recent audit log to get its hash
    const lastLog = await prisma.auditLog.findFirst({
      orderBy: { timestamp: "desc" },
      select: { hash: true },
    });

    const previousHash = lastLog?.hash || "0000000000000000000000000000000000000000000000000000000000000000"; // Genesis hash
    const timestamp = new Date();

    // 2. Compute the new hash for tamper-evidence
    // Format: SHA256(previousHash + caseId + userId + action + timestamp.toISOString())
    const dataToHash = `${previousHash}${caseId}${userId}${action}${timestamp.toISOString()}`;
    const newHash = crypto.createHash("sha256").update(dataToHash).digest("hex");

    // 3. Insert the new log entry
    const logEntry = await prisma.auditLog.create({
      data: {
        caseId,
        userId,
        action,
        metadataJson: metadataJson || {},
        previousHash,
        hash: newHash,
        timestamp,
      },
    });

    return logEntry;
  } catch (error) {
    console.error("Failed to append audit log:", error);
    // Depending on strictness, we might want to throw here, but for now we just log it
    // so we don't break the main flow if audit logging fails.
    return null;
  }
}
