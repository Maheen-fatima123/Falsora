"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { NewCaseModal } from "@/components/new-case-modal";
import { fetchApi } from "@/lib/api";
import { Upload, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export default function UserHomePage() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [recent, setRecent] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const loadMine = async () => {
    try {
      const res = await fetchApi("http://localhost:4000/api/cases?scope=mine");
      const data = await res.json();
      if (data.success && Array.isArray(data.data)) {
        setRecent(data.data.slice(0, 5));
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadMine();
  }, []);

  // Auto-refresh while something is still checking
  useEffect(() => {
    if (!recent.some((c) => c.status === "Analyzing")) return;
    const id = setInterval(() => void loadMine(), 2000);
    return () => clearInterval(id);
  }, [recent]);

  const plainStatus = (status: string) => {
    if (status === "Analyzing") return "Checking";
    if (status === "Flagged") return "Needs human review";
    if (status === "Verified") return "Done";
    return status;
  };

  return (
    <div className="flex flex-col gap-8 max-w-3xl mx-auto w-full">
      <NewCaseModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCaseCreated={(c) => {
          setRecent((prev) => [c, ...prev].slice(0, 5));
          setIsModalOpen(false);
        }}
      />

      <Card className="bg-background/60 backdrop-blur border-border/50 border-dashed">
        <CardContent className="flex flex-col items-center text-center gap-4 py-12">
          <div className="h-14 w-14 rounded-full bg-primary/10 flex items-center justify-center">
            <Upload className="h-7 w-7 text-primary" />
          </div>
          <div>
            <h2 className="text-xl font-semibold font-heading">Check an image</h2>
            <p className="text-sm text-muted-foreground mt-1 max-w-md">
              Upload → Wait for AI → See a plain-language result. Only your own
              submissions are shown here.
            </p>
          </div>
          <ol className="text-xs text-muted-foreground flex flex-wrap justify-center gap-3">
            <li>1. Upload</li>
            <li>2. Wait</li>
            <li>3. See result</li>
          </ol>
          <Button size="lg" className="gap-2" onClick={() => setIsModalOpen(true)}>
            <Upload className="h-4 w-4" /> Upload / Check an image
          </Button>
        </CardContent>
      </Card>

      <Card className="bg-background/60 backdrop-blur border-border/50">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Your recent submissions</CardTitle>
          <Link
            href="/dashboard/cases"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
          >
            My Submissions
          </Link>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-6 text-muted-foreground text-sm gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : recent.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              No submissions yet. Upload an image to get started.
            </p>
          ) : (
            <div className="divide-y divide-border/40">
              {recent.map((c) => (
                <Link
                  key={c.id}
                  href={`/dashboard/cases/${c.id}`}
                  className="flex items-center justify-between py-3 hover:bg-muted/30 px-1 rounded-md"
                >
                  <div>
                    <p className="text-sm font-medium">{c.subject}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.riskLevel || "Pending"} · {c.date}
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
                    className={cn(c.status === "Analyzing" && "animate-pulse")}
                  >
                    {c.status === "Analyzing" && (
                      <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                    )}
                    {plainStatus(c.status)}
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
