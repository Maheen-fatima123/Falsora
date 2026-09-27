"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertTriangle,
  Info,
  AlertCircle,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { fetchApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Notif = {
  id: string;
  type: string;
  message: string;
  isRead: boolean;
  createdAt: string;
};

function kindFromType(type: string): "critical" | "warning" | "info" | "success" {
  const t = (type || "").toUpperCase();
  if (t.includes("FAIL") || t.includes("HIGH") || t.includes("FLAG")) return "critical";
  if (t.includes("ASSIGN") || t.includes("WARN")) return "warning";
  if (t.includes("COMPLETE") || t.includes("VERIF")) return "success";
  return "info";
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "";
  const m = Math.floor(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  return new Date(iso).toLocaleString();
}

export default function AlertsPage() {
  const [items, setItems] = useState<Notif[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchApi("http://localhost:4000/api/notifications");
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(data.message || "Failed to load notifications");
        setItems([]);
        return;
      }
      setItems(Array.isArray(data.data) ? data.data : []);
    } catch (e: any) {
      setError(e?.message || "Failed to load notifications");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const markRead = async (id: string) => {
    try {
      await fetchApi(`http://localhost:4000/api/notifications/${id}/read`, {
        method: "POST",
      });
      setItems((prev) =>
        prev.map((n) => (n.id === id ? { ...n, isRead: true } : n))
      );
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Alerts"
        description="Pipeline and case workflow notifications (6.9)"
      >
        <Button variant="outline" size="sm" onClick={() => void load()}>
          Refresh
        </Button>
      </PageHeader>
      <Card className="bg-background/60 backdrop-blur border-border/50">
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          )}
          {!loading && error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          {!loading && !error && items.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No notifications yet. Upload a case to see pipeline events.
            </p>
          )}
          {!loading &&
            items.map((alert) => {
              const kind = kindFromType(alert.type);
              return (
                <div
                  key={alert.id}
                  className="flex gap-4 items-start relative group"
                >
                  <div className="absolute left-[19px] top-10 bottom-[-24px] w-px bg-border group-last:hidden" />
                  <div
                    className={cn(
                      "mt-1 flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center border-2 border-background shadow-sm z-10",
                      kind === "critical" && "bg-destructive/20 text-destructive",
                      kind === "warning" && "bg-orange-500/20 text-orange-500",
                      kind === "success" && "bg-emerald-500/20 text-emerald-500",
                      kind === "info" && "bg-blue-500/20 text-blue-500"
                    )}
                  >
                    {kind === "critical" ? (
                      <AlertTriangle className="h-4 w-4" />
                    ) : kind === "warning" ? (
                      <AlertCircle className="h-4 w-4" />
                    ) : kind === "success" ? (
                      <CheckCircle2 className="h-4 w-4" />
                    ) : (
                      <Info className="h-4 w-4" />
                    )}
                  </div>
                  <div
                    className={cn(
                      "flex-1 bg-card border border-border/50 rounded-lg p-4 shadow-sm group-hover:border-border transition-colors",
                      !alert.isRead && "border-primary/30"
                    )}
                  >
                    <div className="flex justify-between items-start gap-4">
                      <div>
                        <h4 className="font-semibold leading-none mb-2 font-mono text-sm">
                          {alert.type}
                          {!alert.isRead && (
                            <span className="ml-2 text-[10px] text-primary">
                              NEW
                            </span>
                          )}
                        </h4>
                        <p className="text-sm text-muted-foreground">
                          {alert.message}
                        </p>
                        {!alert.isRead && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="mt-2 h-7 text-xs px-2"
                            onClick={() => void markRead(alert.id)}
                          >
                            Mark read
                          </Button>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        {relativeTime(alert.createdAt)}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
        </CardContent>
      </Card>
    </div>
  );
}
