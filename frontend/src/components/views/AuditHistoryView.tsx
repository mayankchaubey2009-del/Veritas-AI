"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Hash,
  History,
  Info,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { AuditLogEntry, AuditVerificationResult } from "@/types/veritas";
import { veritasApi } from "@/lib/api";

export default function AuditHistoryView() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [verification, setVerification] =
    useState<AuditVerificationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLogsAndVerify = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [logsData, verifyData] = await Promise.all([
        veritasApi.listAuditLogs({ limit: 100 }),
        veritasApi.verifyAuditLogs(),
      ]);
      setLogs(logsData);
      setVerification(verifyData);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load audit trail from SQLite."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRunVerificationOnly = async () => {
    setVerifying(true);
    try {
      const verifyData = await veritasApi.verifyAuditLogs();
      setVerification(verifyData);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to verify SHA-256 audit hash chain."
      );
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    loadLogsAndVerify();
  }, [loadLogsAndVerify]);

  const originBadge = (origin?: string) => {
    switch (origin) {
      case "AUTHENTICATED_HUMAN":
        return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
      case "BACKGROUND_WORKER":
        return "border-purple-500/40 bg-purple-500/15 text-purple-300";
      case "HISTORICAL_SEED_SIMULATION":
        return "border-amber-500/40 bg-amber-500/15 text-amber-300";
      default:
        return "border-slate-700 bg-slate-800/80 text-slate-300";
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 text-cyan-400">
            <History className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">
              Cryptographic SHA-256 Hash-Chained Audit Ledger
            </h2>
            <p className="text-xs text-slate-400">
              Append-only chain-of-custody ledger in SQLite table{" "}
              <code className="text-cyan-300">audit_logs</code> with{" "}
              <code className="text-cyan-300">prev_hash</code> &rarr;{" "}
              <code className="text-cyan-300">event_hash</code> sealing
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={handleRunVerificationOnly}
            disabled={verifying || loading}
            className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/15 px-3.5 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-50"
          >
            <ShieldCheck
              className={`h-3.5 w-3.5 text-emerald-400 ${
                verifying ? "animate-pulse" : ""
              }`}
            />
            <span>
              {verifying ? "Verifying Chain..." : "Verify SHA-256 Hash Chain"}
            </span>
          </button>

          <button
            type="button"
            onClick={loadLogsAndVerify}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900 px-3.5 py-2 text-xs font-medium text-slate-200 transition hover:border-cyan-500/40"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${
                loading ? "animate-spin text-cyan-400" : ""
              }`}
            />
            <span>Refresh Ledger</span>
          </button>
        </div>
      </div>

      {/* Cryptographic Hash-Chain Verification Status Card */}
      {verification && (
        <div
          className={`rounded-2xl border p-5 ${
            verification.verified
              ? "border-emerald-500/35 bg-emerald-950/15"
              : "border-rose-500/50 bg-rose-950/25"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              {verification.verified ? (
                <CheckCircle2 className="h-6 w-6 text-emerald-400" />
              ) : (
                <ShieldAlert className="h-6 w-6 text-rose-400" />
              )}
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-white">
                    {verification.verified
                      ? "AUDIT HASH CHAIN VERIFIED — ZERO TAMPERING OR SEQUENCE GAPS DETECTED"
                      : `TAMPERING OR CORRUPTION DETECTED (${verification.corrupted_events_count} DISCREPANCIES)`}
                  </h3>
                  <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] text-cyan-300">
                    {verification.total_events_checked} EVENTS SEALED
                  </span>
                </div>
                <p className="mt-0.5 font-mono text-[11px] text-slate-300">
                  Head Event Hash:{" "}
                  <span className="text-cyan-300">
                    {verification.latest_event_hash}
                  </span>{" "}
                  · Genesis:{" "}
                  <span className="text-slate-400">
                    {verification.genesis_hash}
                  </span>
                </p>
              </div>
            </div>

            {/* Origin Breakdown Pills */}
            <div className="flex flex-wrap items-center gap-2">
              {Object.entries(verification.origin_breakdown || {}).map(
                ([origin, count]) => (
                  <span
                    key={origin}
                    className={`rounded-lg border px-2.5 py-1 font-mono text-[10px] font-semibold ${originBadge(
                      origin
                    )}`}
                  >
                    {origin}: {count}
                  </span>
                )
              )}
            </div>
          </div>

          {!verification.verified &&
            verification.corrupted_events.length > 0 && (
              <div className="mt-4 space-y-2 rounded-xl border border-rose-500/40 bg-rose-950/40 p-3.5 text-xs text-rose-200">
                <div className="flex items-center gap-2 font-semibold">
                  <AlertTriangle className="h-4 w-4 text-rose-400" />
                  <span>Detected Hash-Chain Discrepancies:</span>
                </div>
                {verification.corrupted_events.slice(0, 5).map((item, idx) => (
                  <div key={idx} className="font-mono text-[11px]">
                    • [{item.reason || item.issue_type}] {item.description}
                  </div>
                ))}
              </div>
            )}

          {verification.architectural_limitations &&
            verification.architectural_limitations.length > 0 && (
              <div className="mt-3.5 flex items-start gap-2 rounded-xl border border-slate-800/90 bg-[#070B16]/90 p-3 text-[11px] text-slate-400">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-400" />
                <div>
                  <span className="font-semibold text-slate-300">
                    Cryptographic Audit Ledger Scope &amp; Limitations:{" "}
                  </span>
                  {verification.architectural_limitations.join(" ")}
                </div>
              </div>
            )}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-xs text-rose-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center rounded-2xl border border-slate-800/80 bg-[#0A1020]/90 py-16 text-slate-400">
          <Loader2 className="mr-2 h-5 w-5 animate-spin text-cyan-400" />
          <span className="text-xs">Reading SQLite audit_logs table...</span>
        </div>
      ) : logs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-800 bg-[#0A1020]/80 p-12 text-center text-xs text-slate-400">
          No audit events recorded yet. Create or update an investigation to
          populate the forensic ledger.
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-800/90 bg-[#0A1020]/90">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-800 bg-[#070B16] font-mono text-[11px] uppercase tracking-wider text-slate-400">
                <tr>
                  <th className="px-3.5 py-3.5">Seq #</th>
                  <th className="px-3.5 py-3.5">Timestamp (UTC)</th>
                  <th className="px-3.5 py-3.5">Action</th>
                  <th className="px-3.5 py-3.5">Origin &amp; Role</th>
                  <th className="px-3.5 py-3.5">Case</th>
                  <th className="px-3.5 py-3.5">Actor</th>
                  <th className="px-3.5 py-3.5">Event Summary</th>
                  <th className="px-3.5 py-3.5">SHA-256 Chain</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {logs.map((entry) => (
                  <tr
                    key={entry.id}
                    className="transition hover:bg-slate-900/50"
                  >
                    <td className="whitespace-nowrap px-3.5 py-3 font-mono text-[11px] font-bold text-cyan-400">
                      #{entry.sequence_number ?? "—"}
                    </td>
                    <td className="whitespace-nowrap px-3.5 py-3 font-mono text-[11px] text-slate-400">
                      {new Date(entry.created_at).toLocaleString()}
                    </td>
                    <td className="whitespace-nowrap px-3.5 py-3">
                      <span className="inline-flex items-center gap-1.5 rounded border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-blue-300">
                        <ShieldCheck className="h-3 w-3 text-cyan-400" />
                        {entry.action}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3.5 py-3">
                      <div className="flex flex-col gap-1">
                        <span
                          className={`inline-block w-fit rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold ${originBadge(
                            entry.event_origin
                          )}`}
                        >
                          {entry.event_origin || "SYSTEM"}
                        </span>
                        {entry.actor_role && (
                          <span className="font-mono text-[9px] text-slate-400">
                            Role: {entry.actor_role}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3.5 py-3 font-mono text-xs font-semibold text-cyan-300">
                      {entry.case_code || "—"}
                    </td>
                    <td className="whitespace-nowrap px-3.5 py-3 text-slate-300">
                      {entry.actor}
                    </td>
                    <td className="px-3.5 py-3 text-slate-200">
                      {entry.summary}
                    </td>
                    <td className="whitespace-nowrap px-3.5 py-3 font-mono text-[10px] text-slate-400">
                      <div className="flex items-center gap-1 text-emerald-300">
                        <Hash className="h-3 w-3" />
                        <span title={entry.event_hash}>
                          {entry.event_hash
                            ? `${entry.event_hash.slice(0, 12)}...`
                            : "—"}
                        </span>
                      </div>
                      <div
                        className="text-[9px] text-slate-500"
                        title={entry.prev_hash}
                      >
                        prev:{" "}
                        {entry.prev_hash === "GENESIS"
                          ? "GENESIS"
                          : entry.prev_hash
                          ? `${entry.prev_hash.slice(0, 10)}...`
                          : "—"}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
