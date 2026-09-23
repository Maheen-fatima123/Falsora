import { Router, type Request, type Response } from "express";
import { prisma } from "../db";

const router = Router();

/**
 * GET /api/analytics/dashboard
 * Returns real aggregate metrics computed via Prisma from the cases table.
 * Replaces the old analytics.py DB-querying code that lived in decision-engine.
 */
router.get("/dashboard", async (req: Request, res: Response) => {
  try {
    // --- Total case count ---
    const total = await prisma.case.count();

    // --- Count by status ---
    const byStatusRaw = await prisma.case.groupBy({
      by: ["status"],
      _count: { status: true },
    });
    const byStatus: Record<string, number> = {};
    for (const row of byStatusRaw) {
      byStatus[row.status] = row._count.status;
    }

    // --- Count by risk level (riskLevel may be null) ---
    const byRiskRaw = await prisma.case.groupBy({
      by: ["riskLevel"],
      _count: { riskLevel: true },
    });
    const byRiskLevel: Record<string, number> = {};
    for (const row of byRiskRaw) {
      byRiskLevel[row.riskLevel ?? "Pending"] = row._count.riskLevel;
    }

    // --- 7-day daily trend ---
    const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const recentCases = await prisma.case.findMany({
      where: { createdAt: { gte: sevenDaysAgo } },
      select: { createdAt: true },
      orderBy: { createdAt: "asc" },
    });

    const dailyMap: Record<string, number> = {};
    for (const c of recentCases) {
      const day = c.createdAt.toISOString().split("T")[0]!;
      dailyMap[day] = (dailyMap[day] || 0) + 1;
    }
    const dailyTrend = Object.entries(dailyMap).map(([date, count]) => ({ date, count }));

    // --- Average trust score (computed in JS to avoid Prisma aggregate field issues) ---
    const allScores = await prisma.case.findMany({
      where: { trustScore: { not: null } },
      select: { trustScore: true },
    });
    const avgTrustScore =
      allScores.length > 0
        ? allScores.reduce((sum, c) => sum + (c.trustScore ?? 0), 0) / allScores.length
        : null;

    return res.json({
      success: true,
      data: {
        total_cases: total,
        by_status: byStatus,
        by_risk_level: byRiskLevel,
        daily_trend: dailyTrend,
        avg_trust_score: avgTrustScore !== null ? Math.round(avgTrustScore * 1000) / 1000 : null,
        scored_cases: allScores.length,
      },
    });
  } catch (error) {
    console.error("Error in GET /api/analytics/dashboard:", error);
    return res.status(500).json({ success: false, message: "Failed to fetch analytics." });
  }
});

/**
 * GET /api/analytics/reviewer/:reviewerId/cases
 * Cases assigned to a specific reviewer — replaces get_cases_for_reviewer()
 * that was removed from decision-engine.
 */
router.get("/reviewer/:reviewerId/cases", async (req: Request, res: Response) => {
  try {
    const reviewerId = req.params.reviewerId as string;
    const cases = await prisma.case.findMany({
      where: { assignedTo: reviewerId },
      orderBy: { createdAt: "desc" },
      select: {
        id: true,
        title: true,
        status: true,
        riskLevel: true,
        trustScore: true,
        createdAt: true,
      },
    });
    return res.json({ success: true, data: cases });
  } catch (error) {
    console.error("Error in GET /api/analytics/reviewer/:reviewerId/cases:", error);
    return res.status(500).json({ success: false, message: "Failed to fetch reviewer cases." });
  }
});

export default router;
