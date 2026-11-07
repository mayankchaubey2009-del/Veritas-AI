"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Clock,
  FileText,
  FolderOpen,
  Loader2,
  MessageSquarePlus,
  Send,
  ShieldAlert,
  Tag,
  Trash2,
  UserCheck,
} from "lucide-react";
import {
  Investigation,
  InvestigationDetail,
  InvestigationStatus,
  NavigationSectionId,
} from "@/types/veritas";
import { veritasApi } from "@/lib/api";

interface InvestigationWorkspaceProps {
  selectedInvestigation: Investigation | null;
  onInvestigationUpdated: () => void;
  onNavigateSection: (section: NavigationSectionId) => void;
}

const STATUS_OPTIONS: InvestigationStatus[] = [
  "OPEN",
  "IN_PROGRESS",
  "UNDER_REVIEW",
  "COMPLETED",
  "ARCHIVED",
];

export function getStatusBadgeStyle(status: InvestigationStatus | string) {
  switch (status) {
    case "OPEN":
      return "border-cyan-500/40 bg-cyan-500/10 text-cyan-300";
    case "IN_PROGRESS":
      return "border-blue-500/40 bg-blue-500/15 text-blue-300";
    case "UNDER_REVIEW":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    case "COMPLETED":
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    case "ARCHIVED":
      return "border-slate-700 bg-slate-800/80 text-slate-400";
    default:
      return "border-slate-700 bg-slate-800 text-slate-300";
  }
}

export function getPriorityBadgeStyle(priority: string) {
  switch (priority) {
    case "CRITICAL":
      return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    case "HIGH":
      return "border-orange-500/40 bg-orange-500/15 text-orange-300";
    case "MEDIUM":
      return "border-cyan-500/40 bg-cyan-500/10 text-cyan-300";
    default:
      return "border-slate-700 bg-slate-800 text-slate-400";
  }
}

export default function InvestigationWorkspace({
  selectedInvestigation,
  onInvestigationUpdated,
  onNavigateSection,
}: InvestigationWorkspaceProps) {
  const [detail, setDetail] = useState<InvestigationDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [noteSubmitting, setNoteSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await veritasApi.getInvestigationDetail(id);
      setDetail(data);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load investigation workspace."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedInvestigation?.id) {
      fetchDetail(selectedInvestigation.id);
    } else {
      setDetail(null);
    }
  }, [selectedInvestigation?.id, selectedInvestigation?.updated_at, fetchDetail]);

  const handleStatusChange = async (newStatus: InvestigationStatus) => {
    if (!detail || detail.status === newStatus) return;
    setStatusUpdating(true);
    setError(null);
    try {
      await veritasApi.updateInvestigation(detail.id, { status: newStatus });
      await fetchDetail(detail.id);
      onInvestigationUpdated();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to update case status."
      );
    } finally {
      setStatusUpdating(false);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!detail || noteText.trim().length < 2) return;
    setNoteSubmitting(true);
    setError(null);
    try {
      await veritasApi.addCaseNote(detail.id, {
        actor: detail.lead_investigator,
        note: noteText.trim(),
      });
      setNoteText("");
      await fetchDetail(detail.id);
      onInvestigationUpdated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to log case note.");
    } finally {
      setNoteSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!detail) return;
    setStatusUpdating(true);
    try {
      await veritasApi.deleteInvestigation(detail.id);
      setDetail(null);
      onInvestigationUpdated();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to delete investigation."
      );
    } finally {
      setStatusUpdating(false);
    }
  };

  if (!selectedInvestigation) {
    return (
      <div className="flex h-full min-h-[380px] flex-col items-center justify-center rounded-2xl border border-slate-800/80 bg-[#0A1020]/90 p-6 text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/90 text-cyan-400">
          <FolderOpen className="h-6 w-6" />
        </div>
        <h3 className="text-sm font-semibold text-white">
          Quick-Access Investigation Workspace
        </h3>
        <p className="mt-1.5 max-w-xs text-xs leading-relaxed text-slate-400">
          Select an active investigation from the registry or create a new
          forensic case to inspect its parameters, transition workflow status,
          and append audit log notes.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col rounded-2xl border border-cyan-500/25 bg-[#0A1020]/95 p-5 shadow-[0_0_30px_-15px_rgba(6,182,212,0.25)]">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-xs font-semibold text-cyan-300">
              {detail?.case_code || selectedInvestigation.case_code}
            </span>
            <span
              className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getPriorityBadgeStyle(
                detail?.priority || selectedInvestigation.priority
              )}`}
            >
              {detail?.priority || selectedInvestigation.priority}
            </span>
            <span className="font-mono text-[11px] text-slate-500">
              QUICK-ACCESS WORKSPACE
            </span>
          </div>
          <h3 className="mt-2 text-base font-semibold text-white">
            {detail?.title || selectedInvestigation.title}
          </h3>
        </div>

        <button
          type="button"
          onClick={handleDelete}
          disabled={statusUpdating}
          title="Delete Investigation"
          className="rounded-lg border border-slate-800 bg-slate-900/80 p-2 text-slate-400 transition hover:border-rose-500/40 hover:bg-rose-950/30 hover:text-rose-300"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-xl border border-rose-500/40 bg-rose-950/30 px-3 py-2 text-xs text-rose-200">
          {error}
        </div>
      )}

      {loading && !detail ? (
        <div className="flex items-center justify-center py-12 text-slate-400">
          <Loader2 className="mr-2 h-5 w-5 animate-spin text-cyan-400" />
          <span className="text-xs font-medium">
            Loading investigation telemetry...
          </span>
        </div>
      ) : (
        detail && (
          <div className="mt-4 space-y-4">
            {/* Description */}
            <p className="rounded-xl border border-slate-800/80 bg-[#060A14] p-3 text-xs leading-relaxed text-slate-300">
              {detail.description ||
                "No hypothesis briefing entered for this case."}
            </p>

            {/* Metadata Grid */}
            <div className="grid grid-cols-2 gap-2.5 text-xs">
              <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-2.5">
                <div className="flex items-center gap-1.5 text-slate-400">
                  <UserCheck className="h-3.5 w-3.5 text-cyan-400" />
                  <span>Lead Analyst</span>
                </div>
                <p className="mt-1 truncate font-medium text-slate-200">
                  {detail.lead_investigator}
                </p>
              </div>

              <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-2.5">
                <div className="flex items-center gap-1.5 text-slate-400">
                  <Tag className="h-3.5 w-3.5 text-blue-400" />
                  <span>Classification</span>
                </div>
                <p className="mt-1 truncate font-mono text-[11px] text-slate-200">
                  {detail.classification.replace(/_/g, " ")}
                </p>
              </div>
            </div>

            {/* Database Linked Counters */}
            <div className="grid grid-cols-3 gap-2 text-center">
              <button
                type="button"
                onClick={() => onNavigateSection("document-intelligence")}
                className="rounded-xl border border-slate-800/90 bg-slate-900/60 p-2.5 transition hover:border-cyan-500/40"
              >
                <div className="flex items-center justify-center gap-1 text-slate-400">
                  <FileText className="h-3.5 w-3.5 text-cyan-400" />
                  <span className="font-mono text-[10px] uppercase">Docs</span>
                </div>
                <div className="mt-1 font-mono text-base font-bold text-white">
                  {detail.document_count}
                </div>
              </button>

              <button
                type="button"
                onClick={() => onNavigateSection("evidence-explorer")}
                className="rounded-xl border border-slate-800/90 bg-slate-900/60 p-2.5 transition hover:border-cyan-500/40"
              >
                <div className="flex items-center justify-center gap-1 text-slate-400">
                  <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
                  <span className="font-mono text-[10px] uppercase">
                    Findings
                  </span>
                </div>
                <div className="mt-1 font-mono text-base font-bold text-white">
                  {detail.findings_count}
                </div>
              </button>

              <button
                type="button"
                onClick={() => onNavigateSection("audit-history")}
                className="rounded-xl border border-slate-800/90 bg-slate-900/60 p-2.5 transition hover:border-cyan-500/40"
              >
                <div className="flex items-center justify-center gap-1 text-slate-400">
                  <Clock className="h-3.5 w-3.5 text-blue-400" />
                  <span className="font-mono text-[10px] uppercase">
                    Events
                  </span>
                </div>
                <div className="mt-1 font-mono text-base font-bold text-white">
                  {detail.audit_trail.length}
                </div>
              </button>
            </div>

            {/* Workflow Status Switcher */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Case Lifecycle Status
                </span>
                {statusUpdating && (
                  <span className="font-mono text-[10px] text-cyan-400">
                    Updating SQLite...
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {STATUS_OPTIONS.map((st) => {
                  const active = detail.status === st;
                  return (
                    <button
                      key={st}
                      type="button"
                      disabled={statusUpdating}
                      onClick={() => handleStatusChange(st)}
                      className={`rounded-lg border px-2.5 py-1 font-mono text-[10px] font-semibold transition ${
                        active
                          ? getStatusBadgeStyle(st)
                          : "border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                      }`}
                    >
                      {st.replace("_", " ")}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Append Investigator Note Form */}
            <form onSubmit={handleAddNote} className="space-y-2 pt-1">
              <label
                htmlFor="workspace-note"
                className="flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400"
              >
                <MessageSquarePlus className="h-3.5 w-3.5 text-cyan-400" />
                <span>Append Forensic Case Note</span>
              </label>
              <div className="flex gap-2">
                <input
                  id="workspace-note"
                  type="text"
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  placeholder="Log an evidentiary observation to audit ledger..."
                  className="flex-1 rounded-xl border border-slate-800 bg-[#060A14] px-3 py-2 text-xs text-white placeholder-slate-500 outline-none focus:border-cyan-400"
                />
                <button
                  type="submit"
                  disabled={noteSubmitting || noteText.trim().length < 2}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-500/15 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/25 disabled:opacity-40"
                >
                  {noteSubmitting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Send className="h-3.5 w-3.5" />
                  )}
                  <span>Log</span>
                </button>
              </div>
            </form>

            {/* Case Audit Trail Mini-Feed */}
            <div className="border-t border-slate-800/80 pt-3">
              <div className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Case Audit Trail ({detail.audit_trail.length})
              </div>
              <div className="max-h-40 space-y-2 overflow-y-auto pr-1">
                {detail.audit_trail.map((log) => (
                  <div
                    key={log.id}
                    className="rounded-lg border border-slate-800/70 bg-[#060A14]/90 p-2.5 text-xs"
                  >
                    <div className="flex items-center justify-between font-mono text-[10px] text-slate-400">
                      <span className="text-cyan-300">{log.action}</span>
                      <span>
                        {new Date(log.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                    </div>
                    <p className="mt-1 text-slate-300">{log.summary}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}
