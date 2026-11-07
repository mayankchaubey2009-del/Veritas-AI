"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Filter,
  FolderKanban,
  FolderPlus,
  Loader2,
  Search,
} from "lucide-react";
import {
  Investigation,
  InvestigationPriority,
  InvestigationStatus,
  NavigationSectionId,
} from "@/types/veritas";
import { veritasApi } from "@/lib/api";
import InvestigationWorkspace, {
  getPriorityBadgeStyle,
  getStatusBadgeStyle,
} from "@/components/InvestigationWorkspace";

interface InvestigationsViewProps {
  selectedInvestigation: Investigation | null;
  onSelectInvestigation: (inv: Investigation) => void;
  onOpenNewInvestigation: () => void;
  onGlobalRefresh: () => void;
  onNavigateSection: (section: NavigationSectionId) => void;
}

export default function InvestigationsView({
  selectedInvestigation,
  onSelectInvestigation,
  onOpenNewInvestigation,
  onGlobalRefresh,
  onNavigateSection,
}: InvestigationsViewProps) {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [priorityFilter, setPriorityFilter] = useState<string>("");

  const loadInvestigations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await veritasApi.listInvestigations({
        status: statusFilter || undefined,
        priority: priorityFilter || undefined,
        search: search.trim() || undefined,
        limit: 100,
      });
      setInvestigations(list);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load investigations from SQLite."
      );
    } finally {
      setLoading(false);
    }
  }, [statusFilter, priorityFilter, search]);

  useEffect(() => {
    loadInvestigations();
  }, [loadInvestigations]);

  const handleUpdated = () => {
    loadInvestigations();
    onGlobalRefresh();
  };

  return (
    <div className="space-y-6">
      {/* Filter & Search Bar */}
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 lg:flex-row lg:items-center">
        <div className="flex flex-1 flex-wrap items-center gap-3">
          <div className="relative min-w-[240px] flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search case code, title, description, or lead analyst..."
              className="w-full rounded-xl border border-slate-800 bg-[#060A14] py-2.5 pl-10 pr-4 text-xs text-white placeholder-slate-500 outline-none focus:border-cyan-400"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-slate-400" />
            <select
              aria-label="Filter by investigation status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-xl border border-slate-800 bg-[#060A14] px-3 py-2.5 text-xs text-slate-200 outline-none focus:border-cyan-400"
            >
              <option value="">All Statuses</option>
              {(
                [
                  "OPEN",
                  "IN_PROGRESS",
                  "UNDER_REVIEW",
                  "COMPLETED",
                  "ARCHIVED",
                ] as InvestigationStatus[]
              ).map((st) => (
                <option key={st} value={st}>
                  {st.replace("_", " ")}
                </option>
              ))}
            </select>

            <select
              aria-label="Filter by investigation priority"
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="rounded-xl border border-slate-800 bg-[#060A14] px-3 py-2.5 text-xs text-slate-200 outline-none focus:border-cyan-400"
            >
              <option value="">All Priorities</option>
              {(
                [
                  "CRITICAL",
                  "HIGH",
                  "MEDIUM",
                  "LOW",
                ] as InvestigationPriority[]
              ).map((pr) => (
                <option key={pr} value={pr}>
                  {pr}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="button"
          onClick={onOpenNewInvestigation}
          className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-4 py-2.5 text-xs font-semibold text-white shadow-glow"
        >
          <FolderPlus className="h-4 w-4" />
          <span>New Investigation</span>
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-xs text-rose-200">
          {error}
        </div>
      )}

      {/* Registry + Workspace Grid */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="space-y-3 xl:col-span-7">
          {loading ? (
            <div className="flex items-center justify-center rounded-2xl border border-slate-800/80 bg-[#0A1020]/90 py-16 text-slate-400">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-cyan-400" />
              <span className="text-xs">Loading SQLite case registry...</span>
            </div>
          ) : investigations.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-[#0A1020]/80 p-12 text-center">
              <FolderKanban className="mb-3 h-8 w-8 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">
                No Matching Investigations Found
              </h3>
              <p className="mt-1 max-w-sm text-xs text-slate-400">
                Adjust your search filters or initialize a new investigation
                record in the SQLite database.
              </p>
            </div>
          ) : (
            investigations.map((inv) => {
              const isSelected = selectedInvestigation?.id === inv.id;
              return (
                <div
                  key={inv.id}
                  onClick={() => onSelectInvestigation(inv)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      onSelectInvestigation(inv);
                    }
                  }}
                  className={`cursor-pointer rounded-2xl border p-4 transition ${
                    isSelected
                      ? "border-cyan-500/50 bg-gradient-to-r from-blue-950/40 via-cyan-950/25 to-slate-900/60 shadow-glow"
                      : "border-slate-800/80 bg-[#0A1020]/90 hover:border-slate-700"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-xs font-semibold text-cyan-300">
                        {inv.case_code}
                      </span>
                      <span
                        className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getStatusBadgeStyle(
                          inv.status
                        )}`}
                      >
                        {inv.status.replace("_", " ")}
                      </span>
                      <span
                        className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getPriorityBadgeStyle(
                          inv.priority
                        )}`}
                      >
                        {inv.priority}
                      </span>
                    </div>
                    <span className="font-mono text-[11px] text-slate-400">
                      {inv.classification.replace(/_/g, " ")}
                    </span>
                  </div>

                  <h4 className="mt-2.5 text-sm font-semibold text-white">
                    {inv.title}
                  </h4>
                  {inv.description && (
                    <p className="mt-1 text-xs text-slate-400">
                      {inv.description}
                    </p>
                  )}

                  <div className="mt-3 flex items-center justify-between border-t border-slate-800/70 pt-2.5 text-xs text-slate-400">
                    <span>Lead: {inv.lead_investigator}</span>
                    <span className="font-mono text-[11px]">
                      {inv.document_count} docs · {inv.findings_count} findings
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="xl:col-span-5">
          <InvestigationWorkspace
            selectedInvestigation={selectedInvestigation}
            onInvestigationUpdated={handleUpdated}
            onNavigateSection={onNavigateSection}
          />
        </div>
      </div>
    </div>
  );
}
