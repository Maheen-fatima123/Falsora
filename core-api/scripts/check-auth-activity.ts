import dotenv from "dotenv";
dotenv.config();
import { prisma } from "../src/db";

async function main() {
  console.log("has authActivityLog?", typeof (prisma as any).authActivityLog);
  try {
    const count = await (prisma as any).authActivityLog.count();
    const rows = await (prisma as any).authActivityLog.findMany({
      orderBy: { createdAt: "desc" },
      take: 10,
    });
    console.log("count", count);
    console.log(JSON.stringify(rows, null, 2));
  } catch (e: any) {
    console.error("QUERY_FAIL", e?.message || e);
  } finally {
    await prisma.$disconnect();
  }
}

main();
