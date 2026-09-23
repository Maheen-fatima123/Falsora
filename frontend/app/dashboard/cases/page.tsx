"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fetchApi } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useRouter } from "next/navigation";
import { Search, Filter, Plus, Loader2 } from "lucide-react";
import { NewCaseModal } from "@/components/new-case-modal";
import { Skeleton } from "@/components/ui/skeleton";

export default function CasesPage() {
  const router = useRouter();
  const [casesList, setCasesList] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchApi("http://localhost:4000/api/cases")
      .then((res) => res.json())
      .then((resData) => {
        if (resData.success && Array.isArray(resData.data)) {
          setCasesList(resData.data);
        }
      })
      .catch((err) => console.error("Error fetching cases:", err))
      .finally(() => setIsLoading(false));
  }, []);

  const handleCaseCreated = (newCase: any) => {
    setCasesList((prev) => [newCase, ...prev]);
  };

  const filteredCases = casesList.filter((c) =>
    (c.subject || c.id || "").toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col gap-6">
      <NewCaseModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onCaseCreated={handleCaseCreated} 
      />

      <Card className="bg-background/60 backdrop-blur border-border/50">
        <CardHeader className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between pb-4">
          <div className="flex items-center gap-3 w-full sm:w-auto flex-1">
            <div className="flex-1 sm:max-w-sm relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input 
                type="search" 
                placeholder="Search cases..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 bg-background/50 w-full" 
              />
            </div>
            <Button variant="outline" className="gap-2">
              <Filter className="h-4 w-4" /> Filter
            </Button>
          </div>
          <Button onClick={() => setIsModalOpen(true)} className="gap-2 cursor-pointer">
            <Plus className="h-4 w-4" /> New Case
          </Button>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border border-border/50 overflow-x-auto">
            <table className="w-full text-sm text-left border-collapse">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Case ID</th>
                  <th className="px-4 py-3 font-medium">Subject</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Date Uploaded</th>
                  <th className="px-4 py-3 font-medium">AI Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {isLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i}>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-24" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-48" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-20" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-24" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-12" /></td>
                    </tr>
                  ))
                ) : filteredCases.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      No cases found. Upload evidence to start an analysis.
                    </td>
                  </tr>
                ) : (
                  filteredCases.map((c) => (
                    <tr 
                      key={c.id} 
                      onClick={() => router.push(`/dashboard/cases/${c.id}`)}
                      className="hover:bg-muted/50 cursor-pointer transition-colors group select-none"
                    >
                      <td className="px-4 py-3 font-medium group-hover:text-primary transition-colors">
                        {c.id.startsWith("CAS-") ? c.id : `CAS-${c.id.substring(0, 6).toUpperCase()}`}
                      </td>
                      <td className="px-4 py-3">{c.subject}</td>
                      <td className="px-4 py-3">
                        <Badge 
                          variant={c.status === "Flagged" ? "destructive" : c.status === "Verified" ? "default" : "secondary"}
                          className={cn(
                            c.status === "Verified" && "bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20",
                            c.status === "Analyzing" && "animate-pulse"
                          )}
                        >
                          {c.status === "Analyzing" && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                          {c.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{c.date}</td>
                      <td className="px-4 py-3">{c.confidence}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
