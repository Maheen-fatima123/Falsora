import type { Request } from "express";
import { prisma } from "../db";

export type AuthAction =
  | "LOGIN_SUCCESS"
  | "LOGIN_FAIL"
  | "LOGOUT"
  | "REGISTER"
  | "PASSWORD_RESET"
  | "FORGOT_PASSWORD";

/** Best-effort auth activity write — never throws to callers. */
export async function logAuthActivity(opts: {
  action: AuthAction;
  userId?: string | null;
  email?: string | null;
  req?: Request;
  metadata?: Record<string, unknown>;
}): Promise<void> {
  try {
    if (!(prisma as any).authActivityLog) {
      console.error(
        "Auth activity log unavailable: prisma.authActivityLog is undefined. " +
          "Restart core-api after `npx prisma generate` so the new model loads."
      );
      return;
    }

    const ip =
      (opts.req?.headers["x-forwarded-for"] as string)?.split(",")[0]?.trim() ||
      opts.req?.socket?.remoteAddress ||
      null;
    const userAgent = opts.req?.headers["user-agent"] || null;

    await prisma.authActivityLog.create({
      data: {
        action: opts.action,
        userId: opts.userId || null,
        email: opts.email || null,
        ip,
        userAgent,
        metadata: opts.metadata ?? undefined,
      },
    });
  } catch (err) {
    console.warn("Auth activity log failed:", err);
  }
}
