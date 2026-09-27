"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { fetchApi } from "@/lib/api";
import {
  FolderOpen,
  AlertTriangle,
  Users,
  Clock,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function AdminHomePage() {
  const [stats, setStats] = useState({
    total: 0,
    flagged: 0,
    analyzing: 0,
    verified: 0,
  });
  const [recent, setRecent] = useState<any[]>([]);
  const [userCount, setUserCount] = useState(0);

  useEffect(() => {
    const load = async () => {
      try {
        const [casesRes, usersRes] = await Promise.all([
          fetchApi("http://localhost:4000/api/cases?scope=all"),
          fetchApi("http://localhost:4000/api/auth/users"),
        ]);
        const casesData = await casesRes.json();
        const usersData = await usersRes.json();
        const cases = Array.isArray(casesData.data) ? casesData.data : [];
        setStats({
          total: cases.length,
          flagged: cases.filter((c: any) => c.status === "Flagged").length,
          analyzing: cases.filter((c: any) => c.status === "Analyzing").length,
          verified: cases.filter((c: any) => c.status === "Verified").length,
        });
        setRecent(cases.slice(0, 5));
        if (usersData.success) {
          const list = usersData.users || usersData.data || [];
          if (Array.isArray(list)) setUserCount(list.length);
        }
      } catch (e) {
        console.error(e);
      }
    };
    void load();
  }, []);

  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Cases</CardTitle>
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
            <p className="text-xs text-muted-foreground">All investigations</p>
          </CardContent>
        </Card>
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Waiting / Analyzing</CardTitle>
            <Clock className="h-4 w-4 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.analyzing}</div>
            <p className="text-xs text-muted-foreground">Still in AI pipeline</p>
          </CardContent>
        </Card>
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">High Risk / Flagged</CardTitle>
            <AlertTriangle className="h-4 w-4 text-destructive" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.flagged}</div>
            <p className="text-xs text-muted-foreground">Need reviewer attention</p>
          </CardContent>
        </Card>
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Users</CardTitle>
            <Users className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{userCount}</div>
            <p className="text-xs text-muted-foreground">Accounts in system</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Recent cases</h2>
        <Link
          href="/dashboard/cases"
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "inline-flex items-center gap-1")}
        >
          All Cases <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      <Card className="bg-background/60 backdrop-blur border-border/50">
        <CardContent className="pt-4 divide-y divide-border/40">
          {recent.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No cases yet.
            </p>
          ) : (
            recent.map((c) => (
              <Link
                key={c.id}
                href={`/dashboard/cases/${c.id}`}
                className="flex items-center justify-between py-3 hover:bg-muted/30 px-2 rounded-md transition-colors"
              >
                <div>
                  <p className="text-sm font-medium">{c.subject}</p>
                  <p className="text-xs text-muted-foreground">
                    {c.id.startsWith("CAS-")
                      ? c.id
                      : `CAS-${c.id.substring(0, 6).toUpperCase()}`}{" "}
                    · {c.date}
                  </p>
                </div>
                <span className="text-xs font-medium">{c.status}</span>
              </Link>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
