"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fetchApi } from "@/lib/api";
import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useRouter, useSearchParams } from "next/navigation";
import { Search, Filter, Plus, Loader2, Trash2, X, ArchiveRestore } from "lucide-react";
import { NewCaseModal } from "@/components/new-case-modal";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { canDeleteCases, readStoredUser } from "@/lib/rbac";

export default function CasesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [casesList, setCasesList] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [canDelete, setCanDelete] = useState(false);
  const [role, setRole] = useState<string>("Administrator");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [unarchivingId, setUnarchivingId] = useState<string | null>(null);

  useEffect(() => {
    const fromUrl = searchParams.get("status");
    if (
      fromUrl === "Archived" ||
      fromUrl === "everything" ||
      fromUrl === "Analyzing" ||
      fromUrl === "Flagged" ||
      fromUrl === "Verified"
    ) {
      setStatusFilter(fromUrl);
    }
  }, [searchParams]);

  useEffect(() => {
    const user = readStoredUser();
    const r = user?.role || "Administrator";
    setRole(r);
    setCanDelete(canDeleteCases(r));
  }, []);

  const fetchCases = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const res = await fetchApi("http://localhost:4000/api/cases");
      const resData = await res.json();
      if (resData.success && Array.isArray(resData.data)) {
        setCasesList(resData.data);
      }
    } catch (err) {
      console.error("Error fetching cases:", err);
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchCases(false);
  }, [fetchCases]);

  // Poll while any case is still Analyzing so status updates without a manual refresh.
  const hasAnalyzing = casesList.some((c) => c.status === "Analyzing");
  useEffect(() => {
    if (!hasAnalyzing) return;
    const id = setInterval(() => {
      void fetchCases(true);
    }, 2000);
    return () => clearInterval(id);
  }, [hasAnalyzing, fetchCases]);

  const handleCaseCreated = (newCase: any) => {
    setCasesList((prev) => [newCase, ...prev]);
  };

  const filteredCases = useMemo(
    () =>
      casesList.filter((c) => {
        const matchesSearch = (c.subject || c.id || "")
          .toLowerCase()
          .includes(searchQuery.toLowerCase());
        const matchesStatus =
          statusFilter === "everything" ||
          (statusFilter === "all" && (c.status || "") !== "Archived") ||
          (statusFilter !== "all" &&
            statusFilter !== "everything" &&
            ((c.status || "").toLowerCase() === statusFilter.toLowerCase() ||
              (statusFilter === "High-Risk" &&
                (c.riskLevel === "High-Risk" || c.riskLevel === "High"))));
        return matchesSearch && matchesStatus;
      }),
    [casesList, searchQuery, statusFilter]
  );

  const selectableIds = useMemo(
    () => filteredCases.map((c) => c.id as string),
    [filteredCases]
  );

  const allFilteredSelected =
    selectableIds.length > 0 && selectableIds.every((id) => selectedIds.has(id));

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allFilteredSelected) {
        selectableIds.forEach((id) => next.delete(id));
      } else {
        selectableIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const toggleSelectOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const clearSelection = () => setSelectedIds(new Set());

  const unarchiveCase = async (c: any, e: React.MouseEvent) => {
    e.stopPropagation();
    if (role !== "Administrator" || c.status !== "Archived") return;
    const restore =
      c.riskLevel === "High-Risk" ||
      c.riskLevel === "High" ||
      c.riskLevel === "Medium" ||
      c.riskLevel === "Uncertain"
        ? "Flagged"
        : "Verified";
    setUnarchivingId(c.id);
    try {
      const res = await fetchApi(`http://localhost:4000/api/cases/${c.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ status: restore }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        toast.error(data.message || "Unarchive failed");
        return;
      }
      setCasesList((prev) =>
        prev.map((row) =>
          row.id === c.id ? { ...row, status: restore, closedAt: null } : row
        )
      );
      toast.success(`Case restored as ${restore}`);
    } catch (err: any) {
      toast.error(err.message || "Unarchive failed");
    } finally {
      setUnarchivingId(null);
    }
  };

  const confirmDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    setIsDeleting(true);
    try {
      const res = await fetchApi("http://localhost:4000/api/cases/bulk-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ ids }),
      });
      const data = await res.json();
      if (!res.ok && !data.success) {
        toast.error(data.message || data.error || "Failed to delete cases");
        return;
      }

      const deleted: string[] = data.data?.deleted || [];
      const failed = data.data?.failed || [];

      if (deleted.length > 0) {
        setCasesList((prev) => prev.filter((c) => !deleted.includes(c.id)));
        setSelectedIds((prev) => {
          const next = new Set(prev);
          deleted.forEach((id) => next.delete(id));
          return next;
        });
        toast.success(
          deleted.length === 1 ? "Case deleted" : `${deleted.length} cases deleted`
        );
      }
      if (failed.length > 0) {
        toast.error(
          `${failed.length} case(s) could not be deleted (demo/fallback rows or missing).`
        );
      }
      setConfirmOpen(false);
    } catch (err: any) {
      toast.error(err.message || "Failed to delete cases");
    } finally {
      setIsDeleting(false);
    }
  };

  const showActions = role === "Administrator";
  const colCount = (canDelete ? 7 : 6) + (showActions ? 1 : 0);
  const pageTitle =
    role === "User"
      ? "My Submissions"
      : role === "Reviewer"
        ? "My Cases"
        : "All Cases";

  return (
    <div className="flex flex-col gap-6">
      <NewCaseModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCaseCreated={handleCaseCreated}
      />

      {canDelete && selectedIds.size > 0 && (
        <div className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/60 bg-background/95 px-4 py-3 shadow-sm backdrop-blur">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-medium">{selectedIds.size} selected</span>
            <Button variant="ghost" size="sm" onClick={clearSelection} className="gap-1.5">
              <X className="h-3.5 w-3.5" />
              Clear
            </Button>
          </div>
          <Button
            variant="destructive"
            size="sm"
            className="gap-1.5"
            onClick={() => setConfirmOpen(true)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete {selectedIds.size === 1 ? "case" : "cases"}
          </Button>
        </div>
      )}

      <Card className="bg-background/60 backdrop-blur border-border/50">
        <CardHeader className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between pb-4">
          <div className="flex flex-col gap-1 w-full sm:w-auto flex-1">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
              {pageTitle}
            </p>
            <div className="flex items-center gap-3 w-full flex-wrap">
              <div className="flex-1 sm:max-w-sm relative min-w-[180px]">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  type="search"
                  placeholder="Search cases..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 bg-background/50 w-full"
                />
              </div>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="h-8 rounded-lg border border-border bg-background px-2 text-xs"
              >
                <option value="all">All (active)</option>
                <option value="Analyzing">Checking</option>
                <option value="Flagged">Flagged / High risk</option>
                <option value="Verified">Verified / Done</option>
                <option value="Archived">Archived only</option>
                <option value="everything">Everything</option>
              </select>
              <Button variant="outline" className="gap-2 hidden sm:inline-flex">
                <Filter className="h-4 w-4" /> Filter
              </Button>
            </div>
          </div>
          {(role === "Administrator" || role === "User") && (
            <Button onClick={() => setIsModalOpen(true)} className="gap-2 cursor-pointer">
              <Plus className="h-4 w-4" />{" "}
              {role === "User" ? "Check Image" : "New Case"}
            </Button>
          )}
        </CardHeader>
        <CardContent>
          <div className="rounded-md border border-border/50 overflow-x-auto">
            <table className="w-full text-sm text-left border-collapse">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  {canDelete && (
                    <th className="px-4 py-3 w-10">
                      <input
                        type="checkbox"
                        aria-label="Select all cases"
                        checked={allFilteredSelected}
                        onChange={toggleSelectAll}
                        disabled={selectableIds.length === 0}
                        className="size-4 accent-primary cursor-pointer"
                      />
                    </th>
                  )}
                  <th className="px-4 py-3 font-medium">Case ID</th>
                  <th className="px-4 py-3 font-medium">Subject</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Risk</th>
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Trust</th>
                  {showActions && (
                    <th className="px-4 py-3 font-medium text-right">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {isLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: colCount }).map((__, j) => (
                        <td key={j} className="px-4 py-3">
                          <Skeleton className="h-5 w-20" />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : filteredCases.length === 0 ? (
                  <tr>
                    <td
                      colSpan={colCount}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      No cases found.
                      {role === "User" && " Upload an image to start a check."}
                    </td>
                  </tr>
                ) : (
                  filteredCases.map((c) => {
                    const selected = selectedIds.has(c.id);
                    return (
                      <tr
                        key={c.id}
                        onClick={() => router.push(`/dashboard/cases/${c.id}`)}
                        className={cn(
                          "hover:bg-muted/50 cursor-pointer transition-colors group select-none",
                          selected && "bg-primary/5"
                        )}
                      >
                        {canDelete && (
                          <td
                            className="px-4 py-3"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <input
                              type="checkbox"
                              aria-label={`Select case ${c.id}`}
                              checked={selected}
                              onChange={() => toggleSelectOne(c.id)}
                              className="size-4 accent-primary cursor-pointer"
                            />
                          </td>
                        )}
                        <td className="px-4 py-3 font-medium group-hover:text-primary transition-colors">
                          {c.id.startsWith("CAS-")
                            ? c.id
                            : `CAS-${c.id.substring(0, 6).toUpperCase()}`}
                        </td>
                        <td className="px-4 py-3">{c.subject}</td>
                        <td className="px-4 py-3">
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
                                "bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20",
                              c.status === "Analyzing" && "animate-pulse"
                            )}
                          >
                            {c.status === "Analyzing" && (
                              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                            )}
                            {c.status === "Analyzing"
                              ? role === "User"
                                ? "Checking"
                                : "Analyzing"
                              : c.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {c.riskLevel || (c.status === "Analyzing" ? "Pending" : "—")}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{c.date}</td>
                        <td className="px-4 py-3">{c.confidence}</td>
                        {showActions && (
                          <td
                            className="px-4 py-3 text-right"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {c.status === "Archived" ? (
                              <Button
                                variant="outline"
                                size="sm"
                                className="gap-1.5 h-7 text-xs"
                                disabled={unarchivingId === c.id}
                                onClick={(e) => void unarchiveCase(c, e)}
                              >
                                {unarchivingId === c.id ? (
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                ) : (
                                  <ArchiveRestore className="h-3 w-3" />
                                )}
                                Unarchive
                              </Button>
                            ) : (
                              <span className="text-muted-foreground text-xs">—</span>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          {hasAnalyzing && (
            <p className="mt-3 text-xs text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-3 w-3 animate-spin" />
              Analysis in progress — this list updates automatically.
            </p>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogMedia className="bg-destructive/10 text-destructive">
              <Trash2 />
            </AlertDialogMedia>
            <AlertDialogTitle>
              Delete {selectedIds.size === 1 ? "this case" : `${selectedIds.size} cases`}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the selected case
              {selectedIds.size === 1 ? "" : "s"}, media, audit logs, and related
              records. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={isDeleting}
              onClick={() => void confirmDelete()}
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Deleting…
                </>
              ) : (
                "Delete"
              )}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
