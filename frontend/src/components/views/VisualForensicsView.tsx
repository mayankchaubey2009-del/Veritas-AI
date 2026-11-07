"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Eye,
  FileCode2,
  FileSearch,
  Filter,
  Fingerprint,
  HelpCircle,
  Image as ImageIcon,
  Info,
  Layers,
  Lock,
  Play,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Stamp,
  Type,
  UserCheck,
} from "lucide-react";
import { veritasApi } from "@/lib/api";
import {
  DocumentSummary,
  ForensicAnalysisDetail,
  ForensicArtifact,
  ForensicFinding,
  Investigation,
} from "@/types/veritas";

interface VisualForensicsViewProps {
  investigations: Investigation[];
  selectedInvestigation: Investigation | null;
  onSelectInvestigation: (inv: Investigation) => void;
  initialDocumentId?: string | null;
  onGlobalRefresh: () => void;
}

type ViewerMode = "ORIGINAL" | "ELA" | "VARIANCE" | "CROP";
type InspectorTab = "FINDINGS_AND_EVIDENCE" | "PDF_METADATA" | "MODULE_TELEMETRY";

const MODULE_SHORT_LABELS: Record<string, string> = {
  MODULE_A_IMAGE_CONSISTENCY: "Mod A: Image Consistency",
  MODULE_B_ELA: "Mod B: Error Level Analysis",
  MODULE_C_TYPOGRAPHY: "Mod C: Typography",
  MODULE_D_ALIGNMENT: "Mod D: Spatial Alignment",
  MODULE_E_PDF_METADATA: "Mod E: PDF Metadata",
  MODULE_F_SIGNATURE_STAMP: "Mod F: Signature & Stamp",
  MODULE_G_TEXT_VISUAL: "Mod G: Text-to-Visual",
};

function getSeverityBadgeStyle(severity: string): string {
  switch (severity) {
    case "HIGH":
      return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    case "MEDIUM":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    case "LOW":
      return "border-cyan-500/40 bg-cyan-500/15 text-cyan-300";
    default:
      return "border-slate-600/50 bg-slate-800/70 text-slate-300";
  }
}

function getReviewBadgeStyle(status: string): string {
  switch (status) {
    case "REVIEWED":
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    case "INCONCLUSIVE":
      return "border-purple-500/40 bg-purple-500/15 text-purple-300";
    case "CONFIRMED":
      return "border-amber-500/40 bg-amber-500/15 text-amber-200";
    case "DISMISSED":
      return "border-slate-600/50 bg-slate-800/70 text-slate-400";
    default:
      return "border-rose-500/40 bg-rose-500/10 text-rose-300";
  }
}

function getSeverityStrokeColor(severity: string): string {
  switch (severity) {
    case "HIGH":
      return "#f43f5e";
    case "MEDIUM":
      return "#f59e0b";
    case "LOW":
      return "#06b6d4";
    default:
      return "#94a3b8";
  }
}

export default function VisualForensicsView({
  investigations,
  selectedInvestigation,
  onSelectInvestigation,
  initialDocumentId,
  onGlobalRefresh,
}: VisualForensicsViewProps) {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(
    initialDocumentId ?? null
  );
  const [analysis, setAnalysis] = useState<ForensicAnalysisDetail | null>(null);
  const [selectedFinding, setSelectedFinding] =
    useState<ForensicFinding | null>(null);

  const [loadingDocs, setLoadingDocs] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ELA Parameters
  const [elaQuality, setElaQuality] = useState<number>(90);
  const [elaScale, setElaScale] = useState<number>(18);

  // Filters
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");
  const [moduleFilter, setModuleFilter] = useState<string>("ALL");
  const [reviewFilter, setReviewFilter] = useState<string>("ALL");

  // Visual Viewer State
  const [activePage, setActivePage] = useState<number>(1);
  const [viewerMode, setViewerMode] = useState<ViewerMode>("ORIGINAL");
  const [showOverlayBoxes, setShowOverlayBoxes] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<InspectorTab>(
    "FINDINGS_AND_EVIDENCE"
  );

  // Human Review Form State
  const [reviewerName, setReviewerName] = useState<string>(
    selectedInvestigation?.lead_investigator ||
      "Dr. Elena Rostova (Principal Forensic Analyst)"
  );
  const [reviewNotes, setReviewNotes] = useState<string>("");
  const [submittingReview, setSubmittingReview] = useState<boolean>(false);
  const [reviewBanner, setReviewBanner] = useState<string | null>(null);

  // Load documents for selected investigation
  const fetchDocuments = useCallback(
    async (invId: string) => {
      setLoadingDocs(true);
      setError(null);
      try {
        const list = await veritasApi.listInvestigationDocuments(invId);
        setDocuments(list);
        if (list.length > 0) {
          setSelectedDocId((prev) => {
            if (initialDocumentId && list.some((d) => d.id === initialDocumentId)) {
              return initialDocumentId;
            }
            if (prev && list.some((d) => d.id === prev)) {
              return prev;
            }
            // Prefer inconsistent demo invoice if present so user immediately sees rich signals
            const demoInconsistent = list.find((d) =>
              d.filename.includes("inconsistent")
            );
            return demoInconsistent ? demoInconsistent.id : list[0].id;
          });
        } else {
          setSelectedDocId(null);
          setAnalysis(null);
        }
      } catch (err: unknown) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load investigation documents."
        );
      } finally {
        setLoadingDocs(false);
      }
    },
    [initialDocumentId]
  );

  useEffect(() => {
    if (selectedInvestigation?.id) {
      fetchDocuments(selectedInvestigation.id);
      if (selectedInvestigation.lead_investigator) {
        setReviewerName(selectedInvestigation.lead_investigator);
      }
    }
  }, [selectedInvestigation?.id, selectedInvestigation?.lead_investigator, fetchDocuments]);

  // Load forensic analysis for selected document
  const fetchForensics = useCallback(async (docId: string) => {
    setLoadingAnalysis(true);
    setError(null);
    setReviewBanner(null);
    try {
      const data = await veritasApi.getDocumentForensics(docId);
      setAnalysis(data);
      setActivePage(1);
      setViewerMode("ORIGINAL");
      if (data.findings.length > 0) {
        const firstActionable =
          data.findings.find((f) => f.severity !== "INFORMATIONAL") ||
          data.findings[0];
        setSelectedFinding(firstActionable);
        setActivePage(firstActionable.page_number || 1);
        setReviewNotes(firstActionable.review_notes || "");
      } else {
        setSelectedFinding(null);
      }
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load Visual Forensics analysis."
      );
    } finally {
      setLoadingAnalysis(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDocId) {
      fetchForensics(selectedDocId);
    }
  }, [selectedDocId, fetchForensics]);

  const handleRunAnalysis = async () => {
    if (!selectedDocId) return;
    setReanalyzing(true);
    setError(null);
    setReviewBanner(null);
    try {
      const updated = await veritasApi.analyzeDocumentForensics(selectedDocId, {
        actor: reviewerName,
        ela_jpeg_quality: elaQuality,
        ela_amplification_scale: elaScale,
        force_reanalyze: true,
      });
      setAnalysis(updated);
      if (updated.findings.length > 0) {
        const firstActionable =
          updated.findings.find((f) => f.severity !== "INFORMATIONAL") ||
          updated.findings[0];
        setSelectedFinding(firstActionable);
        setReviewNotes(firstActionable.review_notes || "");
      }
      onGlobalRefresh();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to execute Visual Forensics analysis."
      );
    } finally {
      setReanalyzing(false);
    }
  };

  const handleSelectFinding = (finding: ForensicFinding) => {
    setSelectedFinding(finding);
    setActivePage(finding.page_number || 1);
    setReviewNotes(finding.review_notes || "");
    setReviewBanner(null);
    if (finding.module_name === "MODULE_B_ELA") {
      setViewerMode("ELA");
    } else if (finding.module_name === "MODULE_F_SIGNATURE_STAMP" && finding.artifact_id) {
      setViewerMode("CROP");
    } else {
      setViewerMode("ORIGINAL");
    }
  };

  const handleSubmitReview = async (disposition: string) => {
    if (!selectedFinding) return;
    setSubmittingReview(true);
    setError(null);
    setReviewBanner(null);
    try {
      const updatedFinding = await veritasApi.reviewForensicFinding(
        selectedFinding.finding_id,
        {
          review_status: disposition,
          reviewer: reviewerName.trim() || "Lead Forensic Analyst",
          notes: reviewNotes.trim(),
        }
      );

      setSelectedFinding(updatedFinding);
      setAnalysis((prev) => {
        if (!prev) return prev;
        const updatedList = prev.findings.map((f) =>
          f.finding_id === updatedFinding.finding_id ? updatedFinding : f
        );
        const pendingCnt = updatedList.filter(
          (f) => f.review_status === "REQUIRES_REVIEW"
        ).length;
        return {
          ...prev,
          findings: updatedList,
          pending_review_count: pendingCnt,
          reviewed_count: updatedList.length - pendingCnt,
        };
      });
      setReviewBanner(
        `Recorded human review disposition '${disposition}' by ${updatedFinding.reviewer}. Audit trail updated.`
      );
      onGlobalRefresh();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to record human review disposition."
      );
    } finally {
      setSubmittingReview(false);
    }
  };

  const filteredFindings = useMemo(() => {
    if (!analysis) return [];
    return analysis.findings.filter((f) => {
      if (severityFilter !== "ALL" && f.severity !== severityFilter) return false;
      if (moduleFilter !== "ALL" && f.module_name !== moduleFilter) return false;
      if (reviewFilter !== "ALL" && f.review_status !== reviewFilter) return false;
      return true;
    });
  }, [analysis, severityFilter, moduleFilter, reviewFilter]);

  const pageFindingsWithBbox = useMemo(() => {
    if (!analysis) return [];
    return analysis.findings.filter(
      (f) => f.page_number === activePage && f.bounding_box != null
    );
  }, [analysis, activePage]);

  const elaArtifact: ForensicArtifact | undefined = useMemo(
    () =>
      analysis?.artifacts.find((a) => a.artifact_type === "ELA_DERIVED_IMAGE"),
    [analysis]
  );

  const varianceArtifact: ForensicArtifact | undefined = useMemo(
    () =>
      analysis?.artifacts.find(
        (a) => a.artifact_type === "LOCAL_VARIANCE_HEATMAP"
      ),
    [analysis]
  );

  const cropArtifact: ForensicArtifact | undefined = useMemo(() => {
    if (!analysis) return undefined;
    if (selectedFinding?.artifact_id) {
      const linked = analysis.artifacts.find(
        (a) => a.artifact_id === selectedFinding.artifact_id
      );
      if (
        linked &&
        (linked.artifact_type === "SIGNATURE_CROP" ||
          linked.artifact_type === "STAMP_CROP")
      ) {
        return linked;
      }
    }
    return analysis.artifacts.find(
      (a) =>
        a.artifact_type === "SIGNATURE_CROP" || a.artifact_type === "STAMP_CROP"
    );
  }, [analysis, selectedFinding]);

  const selectedDocSummary = useMemo(
    () => documents.find((d) => d.id === selectedDocId) || null,
    [documents, selectedDocId]
  );

  const currentPageDimensions = useMemo(() => {
    if (selectedFinding?.bounding_box?.page_width) {
      return {
        width: selectedFinding.bounding_box.page_width,
        height: selectedFinding.bounding_box.page_height,
      };
    }
    const metaDims = analysis?.metadata_inspection?.page_dimensions?.find(
      (d) => Number(d.page_number) === activePage
    );
    if (metaDims && Number(metaDims.width) > 0) {
      return {
        width: Number(metaDims.width),
        height: Number(metaDims.height),
      };
    }
    return { width: 595, height: 842 };
  }, [analysis, activePage, selectedFinding]);

  return (
    <div className="space-y-6">
      {/* Top Forensic Principle & Neutrality Guardrail Banner */}
      <div className="rounded-xl border border-cyan-500/30 bg-gradient-to-r from-slate-900/95 via-slate-900/90 to-cyan-950/30 p-4 shadow-lg">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-lg border border-cyan-400/30 bg-cyan-500/10 p-2 text-cyan-300">
              <Scale className="h-5 w-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold tracking-tight text-white">
                  Phase 3 — Explainable Visual Forensics & Authenticity Signal Engine
                </h2>
                <span className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2.5 py-0.5 text-[11px] font-medium text-cyan-300">
                  7 Diagnostic Modules Active
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-300">
                <strong className="text-cyan-300">Forensic Neutrality Principle:</strong>{" "}
                A detected visual, typographic, compression, or metadata signal is{" "}
                <span className="underline decoration-amber-400/60">
                  NOT proof of forgery, fraud, or manipulation
                </span>
                . Every observation includes benign explanations, methodological limitations,
                exact coordinates, and requires human analyst verification.
              </p>
            </div>
          </div>

          {/* Investigation Selector */}
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={selectedInvestigation?.id || ""}
              onChange={(e) => {
                const match = investigations.find((i) => i.id === e.target.value);
                if (match) onSelectInvestigation(match);
              }}
              className="rounded-lg border border-slate-700 bg-slate-950/90 px-3 py-2 text-xs text-slate-200 focus:border-cyan-400 focus:outline-none"
            >
              {investigations.map((inv) => (
                <option key={inv.id} value={inv.id}>
                  {inv.case_code} — {inv.title}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Document Bar & Re-Analyze Controls */}
      <div className="rounded-xl border border-slate-800/80 bg-slate-900/75 p-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          {/* Document Pills */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
              Evidence Document:
            </span>
            {loadingDocs ? (
              <span className="text-xs text-slate-400">Loading documents...</span>
            ) : documents.length === 0 ? (
              <span className="text-xs text-amber-300">
                No documents uploaded in this investigation yet.
              </span>
            ) : (
              documents.map((doc) => {
                const isSelected = doc.id === selectedDocId;
                return (
                  <button
                    key={doc.id}
                    onClick={() => setSelectedDocId(doc.id)}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                      isSelected
                        ? "border-cyan-400/60 bg-cyan-500/15 text-cyan-200 shadow-sm"
                        : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700 hover:text-white"
                    }`}
                  >
                    <FileSearch className="h-3.5 w-3.5 text-cyan-400" />
                    <span>{doc.filename}</span>
                    <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                      {doc.file_type}
                    </span>
                  </button>
                );
              })
            )}
          </div>

          {/* ELA Diagnostic Parameters & Re-Run Button */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-950/70 px-2.5 py-1 text-xs">
              <span className="text-slate-400">ELA JPEG Q:</span>
              <input
                type="number"
                min={60}
                max={98}
                value={elaQuality}
                onChange={(e) =>
                  setElaQuality(
                    Math.max(60, Math.min(98, Number(e.target.value) || 90))
                  )
                }
                className="w-12 bg-transparent text-center font-mono text-cyan-300 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-950/70 px-2.5 py-1 text-xs">
              <span className="text-slate-400">ELA Scale:</span>
              <input
                type="number"
                min={5}
                max={40}
                value={elaScale}
                onChange={(e) =>
                  setElaScale(
                    Math.max(5, Math.min(40, Number(e.target.value) || 18))
                  )
                }
                className="w-12 bg-transparent text-center font-mono text-cyan-300 focus:outline-none"
              />
              <span className="text-slate-500">x</span>
            </div>

            <button
              onClick={handleRunAnalysis}
              disabled={!selectedDocId || reanalyzing || loadingAnalysis}
              className="flex items-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3.5 py-1.5 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/30 disabled:opacity-50"
            >
              {reanalyzing ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              <span>
                {reanalyzing ? "Running 7 Modules..." : "Re-Run Forensic Analysis"}
              </span>
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-950/40 p-4 text-xs text-rose-200">
          <div className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="h-4 w-4 text-rose-400" />
            <span>Forensic Engine Alert</span>
          </div>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {loadingAnalysis ? (
        <div className="flex h-64 items-center justify-center rounded-xl border border-slate-800/80 bg-slate-900/60">
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <RefreshCw className="h-5 w-5 animate-spin text-cyan-400" />
            <span>
              Executing 7-Module Visual Forensics & Authenticity Signal Pipeline...
            </span>
          </div>
        </div>
      ) : analysis ? (
        <>
          {/* SECTION A: ANALYSIS OVERVIEW METRICS */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
            <div className="rounded-xl border border-slate-800/80 bg-slate-900/75 p-3.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Analysis Status</span>
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
              </div>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="text-lg font-bold text-emerald-300">
                  {analysis.status}
                </span>
                <span className="text-[11px] text-slate-400">
                  {analysis.modules_executed.length}/7 Modules
                </span>
              </div>
              <div className="mt-1 truncate text-[11px] text-slate-400">
                Duration: {analysis.processing_duration_ms} ms
              </div>
            </div>

            <div className="rounded-xl border border-slate-800/80 bg-slate-900/75 p-3.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Original Immutability</span>
                <Fingerprint className="h-4 w-4 text-cyan-400" />
              </div>
              <div className="mt-1.5 flex items-center gap-1.5">
                <span
                  className={`text-sm font-bold ${
                    analysis.original_file_intact
                      ? "text-cyan-300"
                      : "text-rose-400"
                  }`}
                >
                  {analysis.original_file_intact
                    ? "SHA-256 Verified Intact"
                    : "Hash Mismatch"}
                </span>
              </div>
              <div
                className="mt-1 truncate font-mono text-[10px] text-slate-400"
                title={analysis.document_sha256}
              >
                {analysis.document_sha256.slice(0, 24)}...
              </div>
            </div>

            <div className="rounded-xl border border-rose-500/30 bg-rose-950/15 p-3.5">
              <div className="flex items-center justify-between text-xs text-rose-300">
                <span>High Severity Signals</span>
                <ShieldAlert className="h-4 w-4 text-rose-400" />
              </div>
              <div className="mt-1.5 text-2xl font-bold text-rose-300">
                {analysis.high_severity_count}
              </div>
              <div className="mt-1 text-[11px] text-rose-200/70">
                Priority human verification
              </div>
            </div>

            <div className="rounded-xl border border-amber-500/30 bg-amber-950/15 p-3.5">
              <div className="flex items-center justify-between text-xs text-amber-300">
                <span>Medium / Low Signals</span>
                <AlertTriangle className="h-4 w-4 text-amber-400" />
              </div>
              <div className="mt-1.5 text-2xl font-bold text-amber-300">
                {analysis.medium_severity_count}
                <span className="ml-1.5 text-sm font-normal text-cyan-300">
                  / {analysis.low_severity_count} Low
                </span>
              </div>
              <div className="mt-1 text-[11px] text-slate-400">
                +{analysis.informational_count} Informational baselines
              </div>
            </div>

            <div className="rounded-xl border border-slate-800/80 bg-slate-900/75 p-3.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Human Review Queue</span>
                <UserCheck className="h-4 w-4 text-purple-400" />
              </div>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-white">
                  {analysis.pending_review_count}
                </span>
                <span className="text-xs text-slate-400">
                  pending ({analysis.reviewed_count} reviewed)
                </span>
              </div>
              <div className="mt-1 text-[11px] text-slate-400">
                Total observations: {analysis.findings_count}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800/80 bg-slate-900/75 p-3.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Derived Artifacts</span>
                <ImageIcon className="h-4 w-4 text-cyan-400" />
              </div>
              <div className="mt-1.5 text-2xl font-bold text-cyan-300">
                {analysis.artifacts.length}
              </div>
              <div className="mt-1 truncate text-[11px] text-slate-400">
                Analyzed:{" "}
                {analysis.completed_at
                  ? new Date(analysis.completed_at).toLocaleTimeString()
                  : "Just now"}
              </div>
            </div>
          </div>

          {/* Navigation Tabs between Findings & Evidence Workspace, PDF Metadata Inspector, and Module Telemetry */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => setActiveTab("FINDINGS_AND_EVIDENCE")}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold transition ${
                  activeTab === "FINDINGS_AND_EVIDENCE"
                    ? "bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400/50"
                    : "bg-slate-900/70 text-slate-400 hover:text-slate-200"
                }`}
              >
                <Eye className="h-4 w-4" />
                <span>
                  Forensic Findings, Visual Evidence Viewer & Human Review (
                  {analysis.findings_count})
                </span>
              </button>

              <button
                onClick={() => setActiveTab("PDF_METADATA")}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold transition ${
                  activeTab === "PDF_METADATA"
                    ? "bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400/50"
                    : "bg-slate-900/70 text-slate-400 hover:text-slate-200"
                }`}
              >
                <FileCode2 className="h-4 w-4" />
                <span>
                  Module E: PDF Metadata, Embedded Objects & Font Inspector
                </span>
              </button>

              <button
                onClick={() => setActiveTab("MODULE_TELEMETRY")}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold transition ${
                  activeTab === "MODULE_TELEMETRY"
                    ? "bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400/50"
                    : "bg-slate-900/70 text-slate-400 hover:text-slate-200"
                }`}
              >
                <Layers className="h-4 w-4" />
                <span>7-Module Methodology & Limitations</span>
              </button>
            </div>

            {selectedDocSummary && (
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span>Classification:</span>
                <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 font-medium text-cyan-300">
                  {selectedDocSummary.document_type_label} (
                  {Math.round(selectedDocSummary.classification_confidence * 100)}
                  %)
                </span>
              </div>
            )}
          </div>

          {activeTab === "FINDINGS_AND_EVIDENCE" && (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
              {/* LEFT COLUMN (5 cols): SECTION B — FORENSIC FINDINGS PANEL */}
              <div className="space-y-4 xl:col-span-5">
                <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-white">
                      Forensic Observations ({filteredFindings.length})
                    </h3>
                    <span className="text-[11px] text-slate-400">
                      Click any finding to locate on page
                    </span>
                  </div>

                  {/* Filter Bar */}
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    <select
                      value={severityFilter}
                      onChange={(e) => setSeverityFilter(e.target.value)}
                      className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 text-[11px] text-slate-200 focus:border-cyan-400 focus:outline-none"
                    >
                      <option value="ALL">All Severities</option>
                      <option value="HIGH">HIGH Only</option>
                      <option value="MEDIUM">MEDIUM Only</option>
                      <option value="LOW">LOW Only</option>
                      <option value="INFORMATIONAL">INFORMATIONAL</option>
                    </select>

                    <select
                      value={moduleFilter}
                      onChange={(e) => setModuleFilter(e.target.value)}
                      className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 text-[11px] text-slate-200 focus:border-cyan-400 focus:outline-none"
                    >
                      <option value="ALL">All 7 Modules</option>
                      {Object.entries(MODULE_SHORT_LABELS).map(([k, label]) => (
                        <option key={k} value={k}>
                          {label}
                        </option>
                      ))}
                    </select>

                    <select
                      value={reviewFilter}
                      onChange={(e) => setReviewFilter(e.target.value)}
                      className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 text-[11px] text-slate-200 focus:border-cyan-400 focus:outline-none"
                    >
                      <option value="ALL">All Review States</option>
                      <option value="REQUIRES_REVIEW">Requires Review</option>
                      <option value="REVIEWED">Reviewed</option>
                      <option value="INCONCLUSIVE">Inconclusive</option>
                      <option value="CONFIRMED">Confirmed</option>
                    </select>
                  </div>

                  {/* Findings List */}
                  <div className="mt-3 max-h-[680px] space-y-2.5 overflow-y-auto pr-1">
                    {filteredFindings.length === 0 ? (
                      <div className="rounded-lg border border-slate-800/60 bg-slate-950/50 p-6 text-center text-xs text-slate-400">
                        No forensic observations match the selected filter criteria.
                      </div>
                    ) : (
                      filteredFindings.map((fnd) => {
                        const isSelected =
                          selectedFinding?.finding_id === fnd.finding_id;
                        return (
                          <button
                            key={fnd.finding_id}
                            onClick={() => handleSelectFinding(fnd)}
                            className={`w-full rounded-xl border p-3.5 text-left transition ${
                              isSelected
                                ? "border-cyan-400/70 bg-cyan-950/25 shadow-md"
                                : "border-slate-800/80 bg-slate-950/60 hover:border-slate-700"
                            }`}
                          >
                            <div className="flex flex-wrap items-center justify-between gap-1.5">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span
                                  className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase ${getSeverityBadgeStyle(
                                    fnd.severity
                                  )}`}
                                >
                                  {fnd.severity}
                                </span>
                                <span className="rounded bg-slate-800/90 px-2 py-0.5 text-[10px] font-medium text-cyan-300">
                                  {MODULE_SHORT_LABELS[fnd.module_name] ||
                                    fnd.module_name}
                                </span>
                                <span className="rounded bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                                  Page {fnd.page_number}
                                </span>
                              </div>

                              <span
                                className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${getReviewBadgeStyle(
                                  fnd.review_status
                                )}`}
                              >
                                {fnd.review_status.replace("_", " ")}
                              </span>
                            </div>

                            <div className="mt-2 text-xs font-semibold text-white">
                              {fnd.title}
                            </div>

                            <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-slate-300">
                              {fnd.observation}
                            </p>

                            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-400">
                              <span>
                                Category:{" "}
                                <code className="text-slate-300">
                                  {fnd.finding_category}
                                </code>
                              </span>
                              <span>
                                Observation Reliability:{" "}
                                <strong className="text-cyan-300">
                                  {Math.round(fnd.confidence_score * 100)}%
                                </strong>
                              </span>
                            </div>
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>

              {/* RIGHT COLUMN (7 cols): SECTION C (VISUAL EVIDENCE VIEWER) + DETAILED EXPLANATION + SECTION E (HUMAN REVIEW) */}
              <div className="space-y-4 xl:col-span-7">
                {/* SECTION C: VISUAL EVIDENCE VIEWER */}
                <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-white">
                        Visual Evidence Viewer & Coordinate Inspector
                      </h3>
                      <p className="text-[11px] text-slate-400">
                        Toggle between original immutable document render and
                        derived diagnostic artifacts
                      </p>
                    </div>

                    {/* Evidence View Mode Toggle */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      <button
                        onClick={() => setViewerMode("ORIGINAL")}
                        className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                          viewerMode === "ORIGINAL"
                            ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                            : "border-slate-800 bg-slate-950 text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        Original Page
                      </button>

                      {elaArtifact && (
                        <button
                          onClick={() => setViewerMode("ELA")}
                          className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                            viewerMode === "ELA"
                              ? "border-amber-400 bg-amber-500/20 text-amber-200"
                              : "border-slate-800 bg-slate-950 text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          Derived ELA Map
                        </button>
                      )}

                      {varianceArtifact && (
                        <button
                          onClick={() => setViewerMode("VARIANCE")}
                          className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                            viewerMode === "VARIANCE"
                              ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                              : "border-slate-800 bg-slate-950 text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          Local Variance Map
                        </button>
                      )}

                      {cropArtifact && (
                        <button
                          onClick={() => setViewerMode("CROP")}
                          className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                            viewerMode === "CROP"
                              ? "border-purple-400 bg-purple-500/20 text-purple-200"
                              : "border-slate-800 bg-slate-950 text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          Signature/Stamp Crop
                        </button>
                      )}

                      <button
                        onClick={() => setShowOverlayBoxes((v) => !v)}
                        className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                          showOverlayBoxes
                            ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
                            : "border-slate-800 bg-slate-950 text-slate-400"
                        }`}
                      >
                        {showOverlayBoxes ? "Overlays: ON" : "Overlays: OFF"}
                      </button>
                    </div>
                  </div>

                  {/* Derived PDF Render Notice when viewing ELA on PDF */}
                  {viewerMode === "ELA" &&
                    elaArtifact?.is_derived_from_pdf_render && (
                      <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-950/25 px-3 py-2 text-[11px] text-amber-200">
                        <strong>Derived PDF Page-Render Diagnostic:</strong> This
                        document is a PDF container. ELA is computed on a derived
                        150 DPI page render (not an original camera JPEG) and
                        reflects edge contrast and embedded XObject compression.
                      </div>
                    )}

                  {/* Image Canvas with SVG Bounding Box Overlays */}
                  <div className="mt-3 flex justify-center overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-3">
                    {viewerMode === "CROP" && cropArtifact ? (
                      <div className="space-y-2 text-center">
                        <img
                          src={veritasApi.getForensicArtifactUrl(
                            cropArtifact.artifact_id
                          )}
                          alt={cropArtifact.title}
                          className="mx-auto max-h-[360px] rounded border border-slate-700 object-contain"
                        />
                        <div className="text-xs font-medium text-slate-300">
                          {cropArtifact.title}
                        </div>
                        <p className="text-[11px] text-slate-400">
                          {cropArtifact.description}
                        </p>
                      </div>
                    ) : (
                      <div className="relative inline-block max-w-full">
                        <img
                          src={
                            viewerMode === "ELA" && elaArtifact
                              ? veritasApi.getForensicArtifactUrl(
                                  elaArtifact.artifact_id
                                )
                              : viewerMode === "VARIANCE" && varianceArtifact
                              ? veritasApi.getForensicArtifactUrl(
                                  varianceArtifact.artifact_id
                                )
                              : veritasApi.getDocumentPagePreviewUrl(
                                  analysis.document_id,
                                  activePage
                                )
                          }
                          alt={`Forensic Evidence Page ${activePage}`}
                          className="block max-h-[540px] w-auto rounded"
                        />

                        {showOverlayBoxes && pageFindingsWithBbox.length > 0 && (
                          <svg
                            viewBox={`0 0 ${currentPageDimensions.width} ${currentPageDimensions.height}`}
                            className="pointer-events-auto absolute inset-0 h-full w-full"
                            preserveAspectRatio="none"
                          >
                            {pageFindingsWithBbox.map((fnd) => {
                              const bb = fnd.bounding_box;
                              if (!bb) return null;
                              const isSelected =
                                selectedFinding?.finding_id === fnd.finding_id;
                              const stroke = getSeverityStrokeColor(fnd.severity);
                              return (
                                <g
                                  key={fnd.finding_id}
                                  onClick={() => handleSelectFinding(fnd)}
                                  className="cursor-pointer"
                                >
                                  <rect
                                    x={bb.x0}
                                    y={bb.y0}
                                    width={Math.max(4, bb.x1 - bb.x0)}
                                    height={Math.max(4, bb.y1 - bb.y0)}
                                    fill={
                                      isSelected
                                        ? `${stroke}38`
                                        : `${stroke}18`
                                    }
                                    stroke={isSelected ? "#22d3ee" : stroke}
                                    strokeWidth={isSelected ? 2.6 : 1.5}
                                    strokeDasharray={isSelected ? "none" : "4,2"}
                                  />
                                </g>
                              );
                            })}
                          </svg>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Coordinate & Traceability Inspector Bar */}
                  {selectedFinding && (
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/90 px-3 py-2 font-mono text-[11px] text-slate-300">
                      <div>
                        <span className="text-slate-500">Evidence Ref: </span>
                        <span className="text-cyan-300">
                          {selectedFinding.evidence_reference}
                        </span>
                      </div>
                      {selectedFinding.bounding_box ? (
                        <div>
                          <span className="text-slate-500">BBox: </span>
                          <span>
                            [x0={selectedFinding.bounding_box.x0}, y0=
                            {selectedFinding.bounding_box.y0}, x1=
                            {selectedFinding.bounding_box.x1}, y1=
                            {selectedFinding.bounding_box.y1}] on{" "}
                            {selectedFinding.bounding_box.page_width}×
                            {selectedFinding.bounding_box.page_height}
                          </span>
                        </div>
                      ) : (
                        <div className="text-slate-400">
                          Document-level / Container Observation
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* SELECTED FINDING EXPLAINABILITY & HUMAN REVIEW PANEL */}
                {selectedFinding && (
                  <div className="space-y-4 rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-800 pb-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase ${getSeverityBadgeStyle(
                              selectedFinding.severity
                            )}`}
                          >
                            {selectedFinding.severity}
                          </span>
                          <span className="text-xs font-medium text-cyan-300">
                            {MODULE_SHORT_LABELS[selectedFinding.module_name] ||
                              selectedFinding.module_name}
                          </span>
                          <span className="font-mono text-[11px] text-slate-400">
                            ({selectedFinding.finding_category})
                          </span>
                        </div>
                        <h4 className="mt-1.5 text-sm font-bold text-white">
                          {selectedFinding.title}
                        </h4>
                      </div>

                      <div className="text-right">
                        <div className="text-xs font-semibold text-cyan-300">
                          Observation Reliability:{" "}
                          {Math.round(selectedFinding.confidence_score * 100)}%
                        </div>
                        <div className="text-[10px] text-slate-400">
                          (Not an authenticity probability)
                        </div>
                      </div>
                    </div>

                    {/* Explainable Evidence Grid */}
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-cyan-300">
                          1. Observed Technical Signal
                        </div>
                        <p className="mt-1 text-xs leading-relaxed text-slate-200">
                          {selectedFinding.observation}
                        </p>
                      </div>

                      <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-purple-300">
                          2. Technical Explanation
                        </div>
                        <p className="mt-1 text-xs leading-relaxed text-slate-200">
                          {selectedFinding.technical_explanation}
                        </p>
                      </div>

                      <div className="rounded-lg border border-emerald-500/25 bg-emerald-950/15 p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
                          3. Possible Benign Explanations
                        </div>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-slate-200">
                          {selectedFinding.possible_benign_explanations.map(
                            (b, idx) => (
                              <li key={idx}>{b}</li>
                            )
                          )}
                        </ul>
                      </div>

                      <div className="rounded-lg border border-amber-500/25 bg-amber-950/15 p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
                          4. Confidence & Methodological Limitations
                        </div>
                        <p className="mt-1 text-xs text-slate-200">
                          <strong>Confidence Interpretation:</strong>{" "}
                          {selectedFinding.confidence_interpretation}
                        </p>
                        {selectedFinding.limitations && (
                          <p className="mt-1 text-xs text-slate-300">
                            <strong>Limitations:</strong>{" "}
                            {selectedFinding.limitations}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Recommended Human Verification */}
                    <div className="rounded-lg border border-cyan-500/30 bg-cyan-950/20 p-3">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-cyan-300">
                        5. Recommended Human Verification Action
                      </div>
                      <p className="mt-1 text-xs text-slate-100">
                        {selectedFinding.recommended_human_action}
                      </p>
                    </div>

                    {/* Quantitative Evidence Metrics */}
                    {Object.keys(selectedFinding.evidence_metrics || {}).length >
                      0 && (
                      <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                          Measured Diagnostic Telemetry & Parameters
                        </div>
                        <pre className="mt-1.5 overflow-x-auto font-mono text-[11px] text-cyan-200">
                          {JSON.stringify(
                            {
                              evidence_metrics: selectedFinding.evidence_metrics,
                              analysis_parameters:
                                selectedFinding.analysis_parameters,
                            },
                            null,
                            2
                          )}
                        </pre>
                      </div>
                    )}

                    {/* SECTION E: HUMAN REVIEW PANEL */}
                    <div className="rounded-xl border border-purple-500/30 bg-slate-950/90 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <UserCheck className="h-4 w-4 text-purple-400" />
                          <h5 className="text-xs font-bold uppercase tracking-wider text-purple-200">
                            Human Analyst Oversight & Disposition Panel
                          </h5>
                        </div>
                        <span
                          className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${getReviewBadgeStyle(
                            selectedFinding.review_status
                          )}`}
                        >
                          Current Status:{" "}
                          {selectedFinding.review_status.replace("_", " ")}
                        </span>
                      </div>

                      <p className="mt-1 text-[11px] text-slate-400">
                        Automated technical observations are strictly separated
                        from human forensic conclusions. Record your verification
                        disposition and case notes below.
                      </p>

                      {reviewBanner && (
                        <div className="mt-2.5 rounded-lg border border-emerald-500/40 bg-emerald-950/30 px-3 py-2 text-xs text-emerald-200">
                          {reviewBanner}
                        </div>
                      )}

                      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <div>
                          <label className="block text-[11px] font-medium text-slate-300">
                            Reviewer Identity
                          </label>
                          <input
                            type="text"
                            value={reviewerName}
                            onChange={(e) => setReviewerName(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-white focus:border-cyan-400 focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-medium text-slate-300">
                            Last Reviewed Timestamp
                          </label>
                          <div className="mt-1 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-300">
                            {selectedFinding.reviewed_at
                              ? `${new Date(
                                  selectedFinding.reviewed_at
                                ).toLocaleString()} by ${
                                  selectedFinding.reviewer || "Analyst"
                                }`
                              : "Not yet reviewed by human analyst"}
                          </div>
                        </div>
                      </div>

                      <div className="mt-3">
                        <label className="block text-[11px] font-medium text-slate-300">
                          Reviewer Notes & Verification Justification
                        </label>
                        <textarea
                          rows={2}
                          value={reviewNotes}
                          onChange={(e) => setReviewNotes(e.target.value)}
                          placeholder="Document your human verification steps, specimen comparison, or benign explanation..."
                          className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-white focus:border-cyan-400 focus:outline-none"
                        />
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => handleSubmitReview("REVIEWED")}
                          disabled={submittingReview}
                          className="flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/20 px-3 py-1.5 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/30 disabled:opacity-50"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          <span>Mark as Reviewed</span>
                        </button>

                        <button
                          onClick={() => handleSubmitReview("INCONCLUSIVE")}
                          disabled={submittingReview}
                          className="flex items-center gap-1.5 rounded-lg border border-purple-500/40 bg-purple-500/20 px-3 py-1.5 text-xs font-semibold text-purple-200 transition hover:bg-purple-500/30 disabled:opacity-50"
                        >
                          <HelpCircle className="h-3.5 w-3.5" />
                          <span>Mark as Inconclusive</span>
                        </button>

                        <button
                          onClick={() => handleSubmitReview("CONFIRMED")}
                          disabled={submittingReview}
                          className="flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/20 px-3 py-1.5 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/30 disabled:opacity-50"
                        >
                          <ShieldAlert className="h-3.5 w-3.5" />
                          <span>Confirm Anomaly for Dossier</span>
                        </button>

                        <button
                          onClick={() => handleSubmitReview("REQUIRES_REVIEW")}
                          disabled={submittingReview}
                          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 transition hover:bg-slate-800 disabled:opacity-50"
                        >
                          Reset to Requires Review
                        </button>
                      </div>

                      {/* Review Audit History for this Finding */}
                      {selectedFinding.review_history.length > 0 && (
                        <div className="mt-3 border-t border-slate-800 pt-2.5">
                          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                            Finding Review Audit Log (
                            {selectedFinding.review_history.length})
                          </div>
                          <div className="mt-1.5 space-y-1.5">
                            {selectedFinding.review_history.map((rev) => (
                              <div
                                key={rev.review_id}
                                className="rounded border border-slate-800/80 bg-slate-900/70 px-2.5 py-1.5 text-[11px] text-slate-300"
                              >
                                <span className="font-semibold text-cyan-300">
                                  {rev.reviewer}
                                </span>{" "}
                                transitioned status{" "}
                                <code className="text-slate-400">
                                  {rev.previous_status}
                                </code>{" "}
                                →{" "}
                                <code className="text-emerald-300">
                                  {rev.new_status}
                                </code>{" "}
                                <span className="text-slate-500">
                                  ({new Date(rev.created_at).toLocaleString()})
                                </span>
                                {rev.notes && (
                                  <div className="mt-0.5 text-slate-300">
                                    Note: &ldquo;{rev.notes}&rdquo;
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* SECTION D: PDF METADATA & OBJECT INSPECTOR */}
          {activeTab === "PDF_METADATA" && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
                  <h3 className="text-sm font-semibold text-white">
                    Document Info Dictionary & Container Properties
                  </h3>
                  <div className="mt-3 space-y-2 text-xs">
                    {[
                      [
                        "Container Format",
                        analysis.metadata_inspection.source_format,
                      ],
                      [
                        "Creator Tool",
                        analysis.metadata_inspection.creator || "Not specified",
                      ],
                      [
                        "PDF Producer",
                        analysis.metadata_inspection.producer || "Not specified",
                      ],
                      [
                        "Creation Timestamp",
                        analysis.metadata_inspection.creation_date_raw ||
                          "Not specified",
                      ],
                      [
                        "Modification Timestamp",
                        analysis.metadata_inspection.modification_date_raw ||
                          "Not specified",
                      ],
                      [
                        "Title / Subject",
                        `${analysis.metadata_inspection.title || "—"} / ${
                          analysis.metadata_inspection.subject || "—"
                        }`,
                      ],
                      [
                        "Incremental Save (%%EOF) Count",
                        String(
                          analysis.metadata_inspection.incremental_Save_eof_count
                        ),
                      ],
                      [
                        "Total XRef Objects",
                        String(analysis.metadata_inspection.xref_object_count),
                      ],
                    ].map(([k, v]) => (
                      <div
                        key={k}
                        className="flex items-center justify-between border-b border-slate-800/60 pb-1.5"
                      >
                        <span className="text-slate-400">{k}</span>
                        <span className="font-mono text-slate-200">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Embedded Images & Annotations */}
                <div className="space-y-4">
                  <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
                    <h3 className="text-sm font-semibold text-white">
                      Embedded Image XObjects (
                      {analysis.metadata_inspection.embedded_images.length})
                    </h3>
                    {analysis.metadata_inspection.embedded_images.length === 0 ? (
                      <p className="mt-2 text-xs text-slate-400">
                        No embedded XObject raster streams detected in PDF
                        container.
                      </p>
                    ) : (
                      <div className="mt-2 overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="border-b border-slate-800 text-[11px] text-slate-400">
                            <tr>
                              <th className="py-1.5">Page</th>
                              <th className="py-1.5">XRef</th>
                              <th className="py-1.5">Dimensions</th>
                              <th className="py-1.5">Filter</th>
                              <th className="py-1.5">Colorspace</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                            {analysis.metadata_inspection.embedded_images.map(
                              (img, i) => (
                                <tr key={i}>
                                  <td className="py-1.5">{img.page_number}</td>
                                  <td className="py-1.5 text-cyan-300">
                                    #{img.xref}
                                  </td>
                                  <td className="py-1.5">
                                    {img.width}×{img.height}
                                  </td>
                                  <td className="py-1.5 text-amber-300">
                                    {img.compression_filter}
                                  </td>
                                  <td className="py-1.5">{img.colorspace}</td>
                                </tr>
                              )
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
                    <h3 className="text-sm font-semibold text-white">
                      PDF Annotations & Overlay Objects (
                      {analysis.metadata_inspection.annotations.length})
                    </h3>
                    {analysis.metadata_inspection.annotations.length === 0 ? (
                      <p className="mt-2 text-xs text-slate-400">
                        No PDF annotation objects present.
                      </p>
                    ) : (
                      <div className="mt-2 space-y-2">
                        {analysis.metadata_inspection.annotations.map(
                          (an, idx) => (
                            <div
                              key={idx}
                              className="rounded-lg border border-amber-500/30 bg-amber-950/15 p-2.5 text-xs"
                            >
                              <div className="font-semibold text-amber-300">
                                Page {an.page_number} — {an.annot_type} Annotation
                                at [{an.rect.join(", ")}]
                              </div>
                              <div className="mt-1 text-slate-300">
                                Author: {an.author || "Unspecified"} | Content:{" "}
                                {an.content || "None"}
                              </div>
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Font Resources Table */}
              <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
                <h3 className="text-sm font-semibold text-white">
                  Embedded PDF Font Resources (
                  {analysis.metadata_inspection.font_resources.length})
                </h3>
                {analysis.metadata_inspection.font_resources.length === 0 ? (
                  <p className="mt-2 text-xs text-slate-400">
                    No vector PDF font descriptors (Raster/Scanned document).
                  </p>
                ) : (
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-slate-800 text-[11px] text-slate-400">
                        <tr>
                          <th className="py-2">Page</th>
                          <th className="py-2">XRef ID</th>
                          <th className="py-2">Base Font Name</th>
                          <th className="py-2">Font Type</th>
                          <th className="py-2">Encoding</th>
                          <th className="py-2">Subset Embedded</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                        {analysis.metadata_inspection.font_resources.map(
                          (f, idx) => (
                            <tr key={idx}>
                              <td className="py-2">{f.page_number}</td>
                              <td className="py-2 text-cyan-300">#{f.xref}</td>
                              <td className="py-2 font-semibold text-white">
                                {f.font_name}
                              </td>
                              <td className="py-2 text-slate-300">
                                {f.font_type}
                              </td>
                              <td className="py-2 text-slate-300">
                                {f.encoding}
                              </td>
                              <td className="py-2">
                                {f.is_subset ? "Yes (Subset)" : "Standard / Full"}
                              </td>
                            </tr>
                          )
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* MODULE TELEMETRY & METHODOLOGY TAB */}
          {activeTab === "MODULE_TELEMETRY" && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {analysis.module_summaries.map((mod) => (
                <div
                  key={mod.module_name}
                  className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-cyan-300">
                      {mod.display_name}
                    </span>
                    <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                      {mod.status} ({mod.duration_ms} ms)
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-slate-200">
                    <strong>Methodology:</strong> {mod.methodology_summary}
                  </div>
                  <div className="mt-1.5 text-[11px] text-slate-400">
                    <strong>Forensic Limitation:</strong> {mod.limitations_note}
                  </div>
                  <div className="mt-2 text-[11px] font-medium text-white">
                    Observations Recorded: {mod.findings_count}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
