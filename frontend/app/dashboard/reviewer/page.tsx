"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Loader2, Inbox } from "lucide-react";

export default function ReviewerHomePage() {
  const [queue, setQueue] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetchApi(
          "http://localhost:4000/api/cases?scope=assigned"
        );
        const data = await res.json();
        const cases = Array.isArray(data.data) ? data.data : [];
        // Prefer waiting / flagged first
        const riskRank = (r: string | null | undefined) =>
          r === "High" || r === "High-Risk"
            ? 0
            : r === "Medium" || r === "Uncertain"
              ? 1
              : 2;
        cases.sort(
          (a: any, b: any) =>
            riskRank(a.riskLevel) - riskRank(b.riskLevel) ||
            (a.status === "Flagged" ? -1 : 1)
        );
        setQueue(cases.filter((c: any) => c.status !== "Archived"));
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <Card className="bg-background/60 backdrop-blur border-border/50">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Inbox className="h-4 w-4" /> Cases assigned to you
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading queue…
            </div>
          ) : queue.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Nothing in your queue. An administrator will assign cases here.
            </p>
          ) : (
            <div className="divide-y divide-border/40">
              {queue.map((c) => (
                <Link
                  key={c.id}
                  href={`/dashboard/cases/${c.id}`}
                  className="flex items-center justify-between py-3 px-1 hover:bg-muted/30 rounded-md transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium">{c.subject}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.riskLevel || "Pending risk"} · {c.date}
                    </p>
                  </div>
                  <Badge
                    variant={
                      c.status === "Flagged"
                        ? "destructive"
                        : c.status === "Verified"
                          ? "default"
                          : "secondary"
                    }
                    className={cn(
                      c.status === "Verified" &&
                        "bg-emerald-500/10 text-emerald-500"
                    )}
                  >
                    {c.status === "Flagged"
                      ? "Waiting for review"
                      : c.status}
                  </Badge>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
