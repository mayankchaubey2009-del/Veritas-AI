"use client";

import React from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  FileSearch,
  FolderKanban,
  FolderPlus,
  HardDrive,
  Layers,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import {
  CommandCentreSummary,
  HealthStatusResponse,
  Investigation,
  NavigationSectionId,
} from "@/types/veritas";
import InvestigationWorkspace, {
  getPriorityBadgeStyle,
  getStatusBadgeStyle,
} from "@/components/InvestigationWorkspace";

interface CommandCentreViewProps {
  summary: CommandCentreSummary | null;
  health: HealthStatusResponse | null;
  loading: boolean;
  error: string | null;
  selectedInvestigation: Investigation | null;
  onSelectInvestigation: (inv: Investigation) => void;
  onOpenNewInvestigation: () => void;
  onRefresh: () => void;
  onNavigateSection: (section: NavigationSectionId) => void;
}

export default function CommandCentreView({
  summary,
  health,
  loading,
  error,
  selectedInvestigation,
  onSelectInvestigation,
  onOpenNewInvestigation,
  onRefresh,
  onNavigateSection,
}: CommandCentreViewProps) {
  const metrics = summary?.metrics;
  const recentInvestigations = summary?.recent_investigations ?? [];
  const processingActivity = summary?.processing_activity ?? [];

  return (
    <div className="space-y-6">
      {/* 1. Welcome Header Banner */}
      <section className="relative overflow-hidden rounded-2xl border border-cyan-500/25 bg-gradient-to-r from-[#0A1328] via-[#0B162C] to-[#081020] p-6 shadow-[0_0_40px_-15px_rgba(37,99,235,0.35)]">
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 left-1/3 h-64 w-64 rounded-full bg-blue-600/10 blur-3xl" />

        <div className="relative flex flex-col justify-between gap-6 lg:flex-row lg:items-center">
          <div className="max-w-2xl space-y-2">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-widest text-cyan-300">
              <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
              <span>VERITAS AI · Forensic Command Centre</span>
            </div>
            <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Multi-Document Forensics &amp; Contextual Intelligence
            </h2>
            <p className="text-sm leading-relaxed text-slate-300">
              Initiate evidentiary investigations, track forensic workflows backed
              by SQLite persistence, and monitor subsystem readiness across
              optical extraction, visual tampering detection, and cross-document
              reasoning.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onOpenNewInvestigation}
              className="inline-flex items-center gap-2.5 rounded-xl border border-cyan-400/50 bg-gradient-to-r from-blue-600 to-cyan-500 px-5 py-3 text-sm font-semibold text-white shadow-glow transition hover:from-blue-500 hover:to-cyan-400"
            >
              <Plus className="h-4 w-4 stroke-[2.5]" />
              <span>New Investigation</span>
            </button>

            <button
              type="button"
              onClick={() => onNavigateSection("investigations")}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900/80 px-4 py-3 text-sm font-medium text-slate-200 transition hover:border-cyan-500/40 hover:text-cyan-300"
            >
              <span>Case Registry</span>
              <ArrowUpRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </section>

      {/* Backend Error Banner */}
      {error && (
        <div className="flex flex-col justify-between gap-4 rounded-2xl border border-rose-500/40 bg-rose-950/30 p-4 sm:flex-row sm:items-center">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
            <div>
              <h3 className="text-sm font-semibold text-rose-200">
                Backend Telemetry Connection Issue
              </h3>
              <p className="mt-0.5 text-xs text-rose-300/90">{error}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="inline-flex items-center gap-2 self-start rounded-xl border border-rose-400/40 bg-rose-500/20 px-3.5 py-2 text-xs font-semibold text-rose-200 transition hover:bg-rose-500/30 sm:self-auto"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Retry Connection</span>
          </button>
        </div>
      )}

      {/* 2. Genuine Database-Backed KPI Metric Cards */}
      <section
        aria-label="Key Forensic Metrics"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        {/* Total Investigations */}
        <div className="group relative overflow-hidden rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 transition hover:border-cyan-500/40">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
              Total Investigations
            </span>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-blue-500/30 bg-blue-500/10 text-blue-400">
              <FolderKanban className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-3">
            <span className="font-mono text-3xl font-bold text-white">
              {loading && !metrics ? "—" : metrics?.total_investigations ?? 0}
            </span>
            <span className="font-mono text-xs text-cyan-400">
              {metrics?.active_investigations ?? 0} active cases
            </span>
          </div>
          <p className="mt-2 font-mono text-[11px] text-slate-500">
            SQLite table: <code className="text-slate-400">investigations</code>
          </p>
        </div>

        {/* Documents Processed */}
        <div className="group relative overflow-hidden rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 transition hover:border-cyan-500/40">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
              Documents Processed
            </span>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 text-cyan-400">
              <FileSearch className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-3">
            <span className="font-mono text-3xl font-bold text-white">
              {loading && !metrics ? "—" : metrics?.documents_processed ?? 0}
            </span>
            <span className="font-mono text-xs text-slate-400">
              Ingested files
            </span>
          </div>
          <p className="mt-2 font-mono text-[11px] text-slate-500">
            SQLite table: <code className="text-slate-400">documents</code>
          </p>
        </div>

        {/* Findings Requiring Review */}
        <div className="group relative overflow-hidden rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 transition hover:border-cyan-500/40">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
              Findings Requiring Review
            </span>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-400">
              <AlertTriangle className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-3">
            <span className="font-mono text-3xl font-bold text-white">
              {loading && !metrics
                ? "—"
                : metrics?.findings_requiring_review ?? 0}
            </span>
            <span className="font-mono text-xs text-slate-400">
              of {metrics?.total_findings ?? 0} total findings
            </span>
          </div>
          <p className="mt-2 font-mono text-[11px] text-slate-500">
            SQLite table: <code className="text-slate-400">findings</code>
          </p>
        </div>

        {/* Processing Activity */}
        <div className="group relative overflow-hidden rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 transition hover:border-cyan-500/40">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
              Processing Activity
            </span>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
              <Activity className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-3">
            <span className="font-mono text-3xl font-bold text-white">
              {loading && !metrics
                ? "—"
                : metrics?.processing_events_count ?? 0}
            </span>
            <span className="font-mono text-xs text-emerald-400">
              Logged audit events
            </span>
          </div>
          <p className="mt-2 font-mono text-[11px] text-slate-500">
            SQLite table: <code className="text-slate-400">audit_logs</code>
          </p>
        </div>
      </section>

      {/* 3. Main Workspace Grid: Recent Investigations (Left 7 cols) + Quick-Access Workspace (Right 5 cols) */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        {/* Recent Investigations Panel */}
        <section className="flex flex-col rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 xl:col-span-7">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold text-white">
                  Recent Investigations
                </h3>
                <span className="rounded-md border border-slate-700 bg-slate-900 px-2 py-0.5 font-mono text-xs text-cyan-300">
                  {recentInvestigations.length}
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Live records retrieved from SQLite forensic store. Select a case
                to open its workspace.
              </p>
            </div>

            <button
              type="button"
              onClick={onOpenNewInvestigation}
              className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/35 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/20"
            >
              <FolderPlus className="h-3.5 w-3.5" />
              <span>Create Case</span>
            </button>
          </div>

          {loading && recentInvestigations.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center py-16 text-slate-400">
              <RefreshCw className="mb-2 h-6 w-6 animate-spin text-cyan-400" />
              <p className="text-xs">Querying SQLite investigations table...</p>
            </div>
          ) : recentInvestigations.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-[#070B16]/60 px-6 py-14 text-center mt-4">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-500/30 bg-cyan-500/10 text-cyan-400">
                <FolderKanban className="h-6 w-6" />
              </div>
              <h4 className="text-sm font-semibold text-white">
                No Forensic Investigations Recorded Yet
              </h4>
              <p className="mt-1 max-w-md text-xs leading-relaxed text-slate-400">
                The SQLite database is initialized and ready. Create your first
                investigation to generate a forensic case code, initialize an
                audit trail, and open the Quick-Access Workspace.
              </p>
              <button
                type="button"
                onClick={onOpenNewInvestigation}
                className="mt-4 inline-flex items-center gap-2 rounded-xl border border-cyan-400/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-4 py-2 text-xs font-semibold text-white shadow-glow"
              >
                <Plus className="h-4 w-4" />
                <span>Create First Investigation</span>
              </button>
            </div>
          ) : (
            <div className="mt-4 space-y-2.5">
              {recentInvestigations.map((inv) => {
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
                    className={`group cursor-pointer rounded-xl border p-4 transition-all ${
                      isSelected
                        ? "border-cyan-500/50 bg-gradient-to-r from-blue-950/40 via-cyan-950/25 to-slate-900/60 shadow-[0_0_24px_-8px_rgba(6,182,212,0.35)]"
                        : "border-slate-800/80 bg-[#070B16]/80 hover:border-slate-700 hover:bg-slate-900/70"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
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
                        {new Date(inv.updated_at).toLocaleString([], {
                          month: "short",
                          day: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>

                    <h4 className="mt-2 text-sm font-semibold text-white group-hover:text-cyan-300">
                      {inv.title}
                    </h4>

                    {inv.description && (
                      <p className="mt-1 line-clamp-2 text-xs text-slate-400">
                        {inv.description}
                      </p>
                    )}

                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/70 pt-2.5 text-xs text-slate-400">
                      <span>
                        Lead:{" "}
                        <strong className="font-medium text-slate-200">
                          {inv.lead_investigator}
                        </strong>
                      </span>
                      <div className="flex items-center gap-3 font-mono text-[11px]">
                        <span>{inv.document_count} docs</span>
                        <span>·</span>
                        <span>{inv.findings_count} findings</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Quick-Access Investigation Workspace */}
        <section className="xl:col-span-5">
          <InvestigationWorkspace
            selectedInvestigation={selectedInvestigation}
            onInvestigationUpdated={onRefresh}
            onNavigateSection={onNavigateSection}
          />
        </section>
      </div>

      {/* 4. Bottom Grid: Processing Activity Stream + Live System Status */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        {/* Processing Activity (SQLite Audit Ledger) */}
        <section className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 xl:col-span-6">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10 text-cyan-400">
                <Activity className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">
                  Processing Activity &amp; Audit Stream
                </h3>
                <p className="text-xs text-slate-400">
                  Real-time database events recorded in{" "}
                  <code className="font-mono text-slate-300">audit_logs</code>
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => onNavigateSection("audit-history")}
              className="font-mono text-xs text-cyan-400 hover:text-cyan-300"
            >
              View Full Ledger →
            </button>
          </div>

          {processingActivity.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">
              No processing events recorded yet. Create or update an
              investigation to generate live audit telemetry.
            </div>
          ) : (
            <div className="mt-4 max-h-80 space-y-2.5 overflow-y-auto pr-1">
              {processingActivity.map((item) => (
                <div
                  key={item.id}
                  className="flex items-start justify-between gap-3 rounded-xl border border-slate-800/80 bg-[#070B16]/80 p-3 text-xs"
                >
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded border border-blue-500/30 bg-blue-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-blue-300">
                        {item.action}
                      </span>
                      {item.case_code && (
                        <span className="font-mono text-[11px] font-semibold text-cyan-300">
                          {item.case_code}
                        </span>
                      )}
                      <span className="text-slate-400">by {item.actor}</span>
                    </div>
                    <p className="text-slate-200">{item.summary}</p>
                  </div>
                  <span className="shrink-0 font-mono text-[10px] text-slate-400">
                    {new Date(item.created_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* System Status & Subsystem Readiness (Live from GET /api/health) */}
        <section className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 xl:col-span-6">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
                <Server className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">
                  System Status &amp; Architecture Telemetry
                </h3>
                <p className="text-xs text-slate-400">
                  Live probe from{" "}
                  <code className="font-mono text-cyan-300">GET /api/health</code>
                </p>
              </div>
            </div>

            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold ${
                health?.status === "healthy"
                  ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border border-rose-500/30 bg-rose-500/10 text-rose-300"
              }`}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              {health ? health.status.toUpperCase() : "PROBING"}
            </span>
          </div>

          {!health ? (
            <div className="py-12 text-center text-xs text-slate-400">
              Awaiting telemetry response from FastAPI backend...
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              {/* Database & Runtime Metrics */}
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                <div className="rounded-xl border border-slate-800/80 bg-[#070B16] p-3">
                  <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-slate-400">
                    <Database className="h-3.5 w-3.5 text-cyan-400" />
                    <span>SQLite Engine</span>
                  </div>
                  <p className="mt-1 font-mono text-sm font-bold text-white">
                    v{health.database.sqlite_version || "3.x"}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-800/80 bg-[#070B16] p-3">
                  <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-slate-400">
                    <Cpu className="h-3.5 w-3.5 text-blue-400" />
                    <span>DB Latency</span>
                  </div>
                  <p className="mt-1 font-mono text-sm font-bold text-emerald-300">
                    {health.database.latency_ms} ms
                  </p>
                </div>

                <div className="rounded-xl border border-slate-800/80 bg-[#070B16] p-3">
                  <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-slate-400">
                    <Layers className="h-3.5 w-3.5 text-cyan-400" />
                    <span>Tables Active</span>
                  </div>
                  <p className="mt-1 font-mono text-sm font-bold text-white">
                    {health.database.tables_initialized ?? 4} tables
                  </p>
                </div>

                <div className="rounded-xl border border-slate-800/80 bg-[#070B16] p-3">
                  <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-slate-400">
                    <Clock className="h-3.5 w-3.5 text-emerald-400" />
                    <span>API Uptime</span>
                  </div>
                  <p className="mt-1 font-mono text-sm font-bold text-white">
                    {Math.round(health.uptime_seconds)}s
                  </p>
                </div>
              </div>

              {/* Subsystem Status List */}
              <div className="space-y-2">
                {health.subsystems.map((sub) => {
                  const isOp = sub.status === "OPERATIONAL";
                  return (
                    <div
                      key={sub.name}
                      className="flex items-center justify-between gap-3 rounded-xl border border-slate-800/80 bg-[#070B16]/80 px-3.5 py-2.5 text-xs"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <ShieldCheck
                            className={`h-3.5 w-3.5 shrink-0 ${
                              isOp ? "text-emerald-400" : "text-slate-500"
                            }`}
                          />
                          <span className="font-medium text-slate-200">
                            {sub.name}
                          </span>
                          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                            {sub.phase}
                          </span>
                        </div>
                        <p className="mt-0.5 truncate pl-5 text-[11px] text-slate-400">
                          {sub.description}
                        </p>
                      </div>

                      <span
                        className={`shrink-0 rounded-md border px-2 py-0.5 font-mono text-[10px] font-semibold ${
                          isOp
                            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                            : "border-slate-700 bg-slate-800/80 text-slate-400"
                        }`}
                      >
                        {sub.status}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
