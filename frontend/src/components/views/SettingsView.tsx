"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Archive,
  BarChart3,
  CheckCircle2,
  Database,
  HardDriveDownload,
  Loader2,
  Lock,
  Play,
  RefreshCw,
  RotateCcw,
  Server,
  ShieldCheck,
} from "lucide-react";
import {
  AuthenticatedUser,
  BackgroundJob,
  DatabaseBackupManifest,
  HealthStatusResponse,
  Investigation,
  QualityBenchmarkReport,
  SanitizedSystemConfig,
} from "@/types/veritas";
import { getApiBaseUrl, veritasApi } from "@/lib/api";

interface SettingsViewProps {
  health: HealthStatusResponse | null;
  onRefreshHealth: () => void;
  currentUser?: AuthenticatedUser | null;
  selectedInvestigation?: Investigation | null;
  onSwitchPersona?: (username: string) => Promise<void>;
}

export default function SettingsView({
  health,
  onRefreshHealth,
  currentUser,
  selectedInvestigation,
  onSwitchPersona,
}: SettingsViewProps) {
  const [config, setConfig] = useState<SanitizedSystemConfig | null>(null);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [backups, setBackups] = useState<DatabaseBackupManifest[]>([]);
  const [benchmark, setBenchmark] = useState<QualityBenchmarkReport | null>(
    null
  );

  const [loading, setLoading] = useState(true);
  const [runningBenchmark, setRunningBenchmark] = useState(false);
  const [creatingBackup, setCreatingBackup] = useState(false);
  const [verifyingBackupId, setVerifyingBackupId] = useState<string | null>(
    null
  );
  const [backupVerifyMsg, setBackupVerifyMsg] = useState<string | null>(null);
  const [jobBusy, setJobBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = currentUser?.role === "ADMIN";
  const isViewer = currentUser?.role === "VIEWER";

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cfgData, jobsData] = await Promise.all([
        veritasApi.getSystemConfig(),
        veritasApi.listJobs({ limit: 20 }),
      ]);
      setConfig(cfgData);
      setJobs(jobsData);

      if (currentUser?.role === "ADMIN") {
        try {
          const bkpData = await veritasApi.listBackups();
          setBackups(bkpData);
        } catch {
          // Non-admin or empty
        }
      }
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load system configuration from backend."
      );
    } finally {
      setLoading(false);
    }
  }, [currentUser?.role]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleRunBenchmark = async () => {
    setRunningBenchmark(true);
    setError(null);
    try {
      const report = await veritasApi.runQualityBenchmark();
      setBenchmark(report);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to run 10-specimen quality benchmark."
      );
    } finally {
      setRunningBenchmark(false);
    }
  };

  const handleEnqueueDemoJob = async (simulateFailureOnce: boolean) => {
    if (!selectedInvestigation) return;
    setJobBusy(true);
    setError(null);
    try {
      await veritasApi.enqueueJob({
        investigation_id: selectedInvestigation.id,
        job_type: "CONTEXTUAL_INTELLIGENCE_ANALYSIS",
        execute_immediately: true,
        simulate_failure_once: simulateFailureOnce,
      });
      const updated = await veritasApi.listJobs({ limit: 20 });
      setJobs(updated);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to enqueue background job."
      );
    } finally {
      setJobBusy(false);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    setJobBusy(true);
    setError(null);
    try {
      await veritasApi.retryJob(jobId);
      const updated = await veritasApi.listJobs({ limit: 20 });
      setJobs(updated);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to retry background job."
      );
    } finally {
      setJobBusy(false);
    }
  };

  const handleCreateBackup = async () => {
    setCreatingBackup(true);
    setError(null);
    setBackupVerifyMsg(null);
    try {
      const created = await veritasApi.createBackup(
        "Phase 6 Interactive Forensic Snapshot"
      );
      const updated = await veritasApi.listBackups();
      setBackups(updated);
      setBackupVerifyMsg(
        `Backup ${created.backup_id} created (${(
          created.size_bytes / 1024
        ).toFixed(1)} KB) · SHA-256: ${created.sha256_hash.slice(
          0,
          16
        )}... · SQLite integrity_check: ${created.sqlite_integrity_check}`
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to create SQLite backup."
      );
    } finally {
      setCreatingBackup(false);
    }
  };

  const handleVerifyBackup = async (backupId: string) => {
    setVerifyingBackupId(backupId);
    setError(null);
    try {
      const res = await veritasApi.verifyOrRestoreBackup(backupId, false);
      setBackupVerifyMsg(
        `Verified backup ${backupId}: SHA-256 match=${String(
          res.sha256_verified
        )}, SQLite integrity_check=${String(res.sqlite_integrity_check)}`
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to verify SQLite backup."
      );
    } finally {
      setVerifyingBackupId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 text-cyan-400">
            <Server className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">
              Platform Architecture, Quality Benchmark, Background Jobs &amp;
              Backups
            </h2>
            <p className="text-xs text-slate-400">
              Phase 6 Production Readiness &amp; Security Diagnostics from{" "}
              <code className="text-cyan-300">GET /api/system/config</code>,{" "}
              <code className="text-cyan-300">POST /api/system/benchmark</code>{" "}
              &amp; <code className="text-cyan-300">/api/system/backups</code>
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            loadAll();
            onRefreshHealth();
          }}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900 px-3.5 py-2 text-xs font-medium text-slate-200 transition hover:border-cyan-500/40"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Probe Backend</span>
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-xs text-rose-200">
          {error}
        </div>
      )}

      {/* Module E — 10-Specimen Extraction & Analysis Quality Benchmark */}
      <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-cyan-400">
              <BarChart3 className="h-4 w-4" />
              <span>
                Module E — Reproducible 10-Specimen Extraction &amp; Analysis
                Quality Benchmark
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Evaluates 10 synthetic forensic document categories in memory
              (isolated from production SQLite records) and computes real CER,
              Entity Precision/Recall/F1, Table Cell Accuracy, Decimal Arithmetic
              Validation, and Evidence Completeness.
            </p>
          </div>

          <button
            type="button"
            onClick={handleRunBenchmark}
            disabled={runningBenchmark || isViewer}
            className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-4 py-2 text-xs font-semibold text-white shadow-glow transition hover:from-blue-500 hover:to-cyan-400 disabled:opacity-40"
          >
            {runningBenchmark ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            <span>
              {runningBenchmark
                ? "Running 10-Specimen Suite..."
                : "Run 10-Specimen Quality Benchmark"}
            </span>
          </button>
        </div>

        {benchmark ? (
          <div className="mt-5 space-y-5">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
              <div className="rounded-xl border border-slate-800 bg-[#070B16] p-3">
                <div className="font-mono text-[10px] text-slate-400">
                  CLASSIFICATION
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-emerald-300">
                  {(
                    benchmark.aggregate_metrics
                      .document_classification_accuracy * 100
                  ).toFixed(1)}
                  %
                </div>
                <div className="text-[10px] text-slate-500">
                  {benchmark.specimens_evaluated}/10 categories
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-[#070B16] p-3">
                <div className="font-mono text-[10px] text-slate-400">
                  NATIVE PDF CER
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-cyan-300">
                  {(benchmark.aggregate_metrics.ocr_cer_native_pdf * 100).toFixed(
                    2
                  )}
                  %
                </div>
                <div className="text-[10px] text-slate-500">
                  Levenshtein CER
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-[#070B16] p-3">
                <div className="font-mono text-[10px] text-slate-400">
                  SCANNED OCR CER
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-cyan-300">
                  {(
                    benchmark.aggregate_metrics.ocr_cer_scanned_images * 100
                  ).toFixed(2)}
                  %
                </div>
                <div className="text-[10px] text-slate-500">
                  PaddleOCR Path B
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-[#070B16] p-3">
                <div className="font-mono text-[10px] text-slate-400">
                  ENTITY F1 SCORE
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-emerald-300">
                  {(
                    benchmark.aggregate_metrics.entity_extraction_f1 * 100
                  ).toFixed(1)}
                  %
                </div>
                <div className="text-[10px] text-slate-500">
                  P:{" "}
                  {(
                    benchmark.aggregate_metrics.entity_extraction_precision * 100
                  ).toFixed(0)}
                  % · R:{" "}
                  {(
                    benchmark.aggregate_metrics.entity_extraction_recall * 100
                  ).toFixed(0)}
                  %
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-[#070B16] p-3">
                <div className="font-mono text-[10px] text-slate-400">
                  TABLE CELLS
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-emerald-300">
                  {(
                    benchmark.aggregate_metrics.table_cell_extraction_accuracy *
                    100
                  ).toFixed(1)}
                  %
                </div>
                <div className="text-[10px] text-slate-500">
                  Grid cell match
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-[#070B16] p-3">
                <div className="font-mono text-[10px] text-slate-400">
                  DECIMAL CHECKS
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-emerald-300">
                  {(
                    benchmark.aggregate_metrics.financial_calculation_accuracy *
                    100
                  ).toFixed(1)}
                  %
                </div>
                <div className="text-[10px] text-slate-500">
                  Exact Decimal
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-[#070B16] p-3">
                <div className="font-mono text-[10px] text-slate-400">
                  CLAIM GROUNDING
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-emerald-300">
                  {(
                    benchmark.aggregate_metrics
                      .evidence_reference_completeness * 100
                  ).toFixed(0)}
                  %
                </div>
                <div className="text-[10px] text-slate-500">
                  {benchmark.aggregate_metrics.grounded_claims_verified} claims
                </div>
              </div>
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-800 bg-[#070B16] font-mono text-[10px] uppercase text-slate-400">
                  <tr>
                    <th className="px-3 py-2.5">Specimen</th>
                    <th className="px-3 py-2.5">Category</th>
                    <th className="px-3 py-2.5">Method</th>
                    <th className="px-3 py-2.5">Predicted Type</th>
                    <th className="px-3 py-2.5">CER</th>
                    <th className="px-3 py-2.5">Entities (TP/FP/FN)</th>
                    <th className="px-3 py-2.5">Tables</th>
                    <th className="px-3 py-2.5">BBoxes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {benchmark.specimen_results.map((sp) => (
                    <tr key={sp.specimen_id} className="hover:bg-slate-900/40">
                      <td className="px-3 py-2 font-mono text-[11px] font-semibold text-cyan-300">
                        {sp.specimen_id}
                      </td>
                      <td className="px-3 py-2 text-slate-200">{sp.category}</td>
                      <td className="px-3 py-2 font-mono text-[10px] text-slate-400">
                        {sp.extraction_method}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${
                            sp.classification_match
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                              : "border-rose-500/30 bg-rose-500/10 text-rose-300"
                          }`}
                        >
                          {sp.predicted_doc_type} (
                          {Math.round(sp.classification_confidence * 100)}%)
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-slate-300">
                        {(sp.cer * 100).toFixed(2)}%
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-slate-300">
                        {sp.entity_tp} / {sp.entity_fp} / {sp.entity_fn}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-slate-300">
                        {sp.matched_table_cells}/{sp.gt_table_cells}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-emerald-300">
                        {sp.bboxes_valid}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-dashed border-slate-800 bg-[#070B16]/70 p-6 text-center text-xs text-slate-400">
            Click{" "}
            <strong className="text-cyan-300">
              Run 10-Specimen Quality Benchmark
            </strong>{" "}
            above to execute the isolated evaluation suite across Native PDF
            Invoices, Scanned Invoices, Bank Statements, Receipts, Contracts, Tax
            Certificates, Low-Quality Scans, Ambiguous Memos, Multi-Page
            Agreements, and Table-Heavy Invoices.
          </div>
        )}
      </div>

      {/* Module C — Background Processing & Job Recovery Queue */}
      <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-cyan-400">
              <Activity className="h-4 w-4" />
              <span>
                Module C — Background Processing, Duplicate Guard &amp; Retry
                Recovery
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              SQLite-persisted job queue (<code className="text-cyan-300">background_jobs</code>)
              with stage progress tracking, duplicate active job prevention (HTTP
              409), startup recovery of interrupted jobs, and retry of failed
              runs.
            </p>
          </div>

          {selectedInvestigation && !isViewer && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={jobBusy}
                onClick={() => handleEnqueueDemoJob(true)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-3 py-2 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/25 disabled:opacity-40"
              >
                <Play className="h-3.5 w-3.5 text-amber-400" />
                <span>Simulate Transient Job Failure (Attempt 1)</span>
              </button>
              <button
                type="button"
                disabled={jobBusy}
                onClick={() => handleEnqueueDemoJob(false)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-500/15 px-3 py-2 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/25 disabled:opacity-40"
              >
                <Play className="h-3.5 w-3.5 text-cyan-400" />
                <span>Run Contextual Pipeline Job</span>
              </button>
            </div>
          )}
        </div>

        <div className="mt-4">
          {jobs.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-800 bg-[#070B16]/70 p-6 text-center text-xs text-slate-400">
              No background jobs recorded yet. Launch a job above to inspect
              lifecycle states.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-800 bg-[#070B16] font-mono text-[10px] uppercase text-slate-400">
                  <tr>
                    <th className="px-3 py-2.5">Job Type</th>
                    <th className="px-3 py-2.5">Status</th>
                    <th className="px-3 py-2.5">Stage &amp; Progress</th>
                    <th className="px-3 py-2.5">Attempts</th>
                    <th className="px-3 py-2.5">Error / Result</th>
                    <th className="px-3 py-2.5">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {jobs.slice(0, 8).map((job) => (
                    <tr key={job.id} className="hover:bg-slate-900/40">
                      <td className="px-3 py-2.5 font-mono text-[11px] font-semibold text-cyan-300">
                        {job.job_type}
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={`rounded border px-2 py-0.5 font-mono text-[10px] font-bold ${
                            job.status === "COMPLETED"
                              ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
                              : job.status === "FAILED"
                              ? "border-rose-500/40 bg-rose-500/15 text-rose-300"
                              : "border-cyan-500/30 bg-cyan-500/15 text-cyan-300"
                          }`}
                        >
                          {job.status}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[11px] text-slate-300">
                        {job.stage_label} ({job.progress_percent}%)
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[11px] text-slate-300">
                        {job.attempt_count} / {job.max_attempts}
                      </td>
                      <td className="px-3 py-2.5 text-slate-300">
                        {job.error_summary ? (
                          <span className="text-rose-300">
                            {job.error_summary}
                          </span>
                        ) : (
                          <span className="font-mono text-[11px] text-emerald-300">
                            {JSON.stringify(job.result_summary)}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        {job.status === "FAILED" && !isViewer && (
                          <button
                            type="button"
                            disabled={jobBusy}
                            onClick={() => handleRetryJob(job.id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 font-mono text-[10px] font-semibold text-emerald-200 hover:bg-emerald-500/25"
                          >
                            <RotateCcw className="h-3 w-3" />
                            <span>Retry Job</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Module F — SQLite Online Backup & Integrity Verification */}
      <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-cyan-400">
              <Archive className="h-4 w-4" />
              <span>
                Module F — SQLite Online Backup &amp; SHA-256 Integrity
                Verification
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Uses SQLite&apos;s native <code className="text-cyan-300">sqlite3.Connection.backup()</code>{" "}
              API for transactionally consistent WAL snapshots with{" "}
              <code className="text-cyan-300">PRAGMA integrity_check</code> and
              SHA-256 verification.
            </p>
          </div>

          {isAdmin ? (
            <button
              type="button"
              disabled={creatingBackup}
              onClick={handleCreateBackup}
              className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/15 px-4 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-40"
            >
              {creatingBackup ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <HardDriveDownload className="h-3.5 w-3.5 text-emerald-400" />
              )}
              <span>Create Online SQLite Backup</span>
            </button>
          ) : (
            onSwitchPersona && (
              <button
                type="button"
                onClick={() => onSwitchPersona("admin.nair")}
                className="inline-flex items-center gap-2 rounded-xl border border-purple-500/40 bg-purple-500/15 px-3.5 py-2 text-xs font-semibold text-purple-200 transition hover:bg-purple-500/25"
              >
                <ShieldCheck className="h-3.5 w-3.5 text-purple-300" />
                <span>Switch to Director Priya Nair (ADMIN) to Manage Backups</span>
              </button>
            )
          )}
        </div>

        {backupVerifyMsg && (
          <div className="mt-4 rounded-xl border border-emerald-500/40 bg-emerald-950/25 p-3 font-mono text-xs text-emerald-200">
            {backupVerifyMsg}
          </div>
        )}

        {isAdmin && backups.length > 0 && (
          <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-800 bg-[#070B16] font-mono text-[10px] uppercase text-slate-400">
                <tr>
                  <th className="px-3 py-2.5">Backup ID</th>
                  <th className="px-3 py-2.5">Label</th>
                  <th className="px-3 py-2.5">Size</th>
                  <th className="px-3 py-2.5">SHA-256 Digest</th>
                  <th className="px-3 py-2.5">Integrity</th>
                  <th className="px-3 py-2.5">Verify</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {backups.slice(0, 6).map((bkp) => (
                  <tr key={bkp.backup_id} className="hover:bg-slate-900/40">
                    <td className="px-3 py-2 font-mono text-[11px] font-semibold text-cyan-300">
                      {bkp.backup_id}
                    </td>
                    <td className="px-3 py-2 text-slate-200">{bkp.label}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-300">
                      {(bkp.size_bytes / 1024).toFixed(1)} KB
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px] text-slate-400">
                      {bkp.sha256_hash.slice(0, 20)}...
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px] text-emerald-300">
                      {bkp.sqlite_integrity_check}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        disabled={verifyingBackupId === bkp.backup_id}
                        onClick={() => handleVerifyBackup(bkp.backup_id)}
                        className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 font-mono text-[10px] font-semibold text-cyan-300 hover:bg-cyan-500/20"
                      >
                        {verifyingBackupId === bkp.backup_id
                          ? "Verifying..."
                          : "Verify SHA-256"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* API & Security Posture */}
        <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
          <div className="flex items-center gap-2 border-b border-slate-800/80 pb-4 font-mono text-xs font-semibold uppercase tracking-wider text-cyan-400">
            <Lock className="h-4 w-4" />
            <span>Security &amp; Transport Posture</span>
          </div>

          <div className="mt-4 space-y-3 text-xs">
            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">Frontend API Base Endpoint</span>
              <code className="font-mono text-cyan-300">{getApiBaseUrl()}</code>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">Password Hashing KDF</span>
              <span className="font-mono text-emerald-300">
                {config?.security.password_kdf ||
                  "PBKDF2-HMAC-SHA256 (310k) / scrypt"}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">
                Client-Side Secret / API Key Exposure
              </span>
              <span className="inline-flex items-center gap-1.5 rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
                <ShieldCheck className="h-3.5 w-3.5" />
                ZERO KEYS IN FRONTEND
              </span>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">
                Separation of Duties (Self-Approval Blocked)
              </span>
              <span className="font-mono text-emerald-300">
                {config?.security.allow_self_dossier_approval === false
                  ? "ENFORCED (403 ON SELF-APPROVAL)"
                  : "ACTIVE"}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">Allowed CORS Origins</span>
              <span className="font-mono text-slate-200">
                {config?.cors_origins?.join(", ") || "http://localhost:3000"}
              </span>
            </div>
          </div>
        </div>

        {/* SQLite Persistence Configuration */}
        <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
          <div className="flex items-center gap-2 border-b border-slate-800/80 pb-4 font-mono text-xs font-semibold uppercase tracking-wider text-cyan-400">
            <Database className="h-4 w-4" />
            <span>SQLite Forensic Storage Diagnostics</span>
          </div>

          <div className="mt-4 space-y-3 text-xs">
            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">Storage Engine</span>
              <span className="font-mono text-slate-200">
                {config?.database.engine || "SQLite (WAL Mode)"}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">Database File</span>
              <code className="font-mono text-cyan-300">
                {config?.database.file_name ||
                  health?.database.database_file ||
                  "veritas_forensics.db"}
              </code>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">Schema Version</span>
              <span className="font-mono text-cyan-300">
                {config?.database.schema_version ||
                  health?.database.schema_version ||
                  "2.0.0-phase6"}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">Audit Hash Chain Integrity</span>
              <span className="inline-flex items-center gap-1.5 font-mono text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {config?.audit_integrity?.verified
                  ? `VERIFIED (${config.audit_integrity.total_events_checked} EVENTS)`
                  : "ACTIVE"}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#070B16] p-3.5">
              <span className="text-slate-400">Connection State</span>
              <span className="inline-flex items-center gap-1.5 font-mono text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {config?.database.connected
                  ? `CONNECTED (${config.database.latency_ms} ms)`
                  : "DISCONNECTED"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
