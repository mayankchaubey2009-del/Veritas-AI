"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  ClipboardCheck,
  Cpu,
  Download,
  ExternalLink,
  FileCode2,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Filter,
  FolderKanban,
  GitCompareArrows,
  HelpCircle,
  History,
  Layers,
  ListChecks,
  Loader2,
  RefreshCw,
  ScanEye,
  Scale,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from "lucide-react";
import { veritasApi } from "@/lib/api";
import {
  AuthenticatedUser,
  DossierDetail,
  DossierSummary,
  EvidenceGroundedClaim,
  EvidenceManifestItem,
  Investigation,
  InvestigationReasoning,
} from "@/types/veritas";

interface InvestigationDossiersViewProps {
  investigations: Investigation[];
  selectedInvestigation: Investigation | null;
  onSelectInvestigation: (investigation: Investigation) => void;
  onGlobalRefresh: () => void;
  onOpenDocumentIntelligence: () => void;
  onOpenVisualForensics: (documentId: string) => void;
  onOpenContextualIntelligence: () => void;
  currentUser?: AuthenticatedUser | null;
  onSwitchPersona?: (username: string) => Promise<void>;
}

type ActiveDossierTab =
  | "SECTIONS"
  | "CLAIMS"
  | "COMPARISON"
  | "EVIDENCE_MANIFEST"
  | "QUESTIONS_STEPS"
  | "VERSIONS_REVIEW";

function getClaimTypeBadge(claimType: string) {
  switch (claimType) {
    case "DIRECTLY_OBSERVED_FACT":
      return {
        label: "DIRECTLY OBSERVED FACT",
        className: "border-cyan-500/40 bg-cyan-500/15 text-cyan-200",
      };
    case "DETERMINISTIC_CALCULATION_RESULT":
      return {
        label: "DETERMINISTIC CALCULATION",
        className: "border-blue-500/40 bg-blue-500/15 text-blue-200",
      };
    case "AUTOMATED_TECHNICAL_OBSERVATION":
      return {
        label: "AUTOMATED TECHNICAL OBSERVATION",
        className: "border-indigo-500/40 bg-indigo-500/15 text-indigo-200",
      };
    case "POTENTIAL_INTERPRETATION":
      return {
        label: "POTENTIAL INTERPRETATION",
        className: "border-amber-500/40 bg-amber-500/15 text-amber-200",
      };
    case "HUMAN_CONFIRMED_CONCLUSION":
      return {
        label: "HUMAN CONFIRMED CONCLUSION",
        className: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200",
      };
    case "UNKNOWN_OR_MISSING_INFORMATION":
      return {
        label: "MISSING / UNKNOWN INFO",
        className: "border-purple-500/40 bg-purple-500/15 text-purple-200",
      };
    default:
      return {
        label: claimType,
        className: "border-slate-700 bg-slate-800 text-slate-300",
      };
  }
}

function getReviewStatusBadge(status: string) {
  switch (status) {
    case "APPROVED":
      return {
        label: "HUMAN APPROVED",
        className: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
      };
    case "UNDER_REVIEW":
      return {
        label: "UNDER HUMAN REVIEW",
        className: "border-cyan-500/40 bg-cyan-500/15 text-cyan-300",
      };
    case "REQUIRES_REVISION":
      return {
        label: "REQUIRES REVISION",
        className: "border-rose-500/40 bg-rose-500/15 text-rose-300",
      };
    case "ARCHIVED":
      return {
        label: "ARCHIVED",
        className: "border-slate-600 bg-slate-800/80 text-slate-400",
      };
    case "UNAPPROVED_AI_ASSISTED":
    default:
      return {
        label: "UNAPPROVED (AI-ASSISTED)",
        className: "border-amber-500/40 bg-amber-500/15 text-amber-300",
      };
  }
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(2)} MB`;
}

export default function InvestigationDossiersView({
  investigations,
  selectedInvestigation,
  onSelectInvestigation,
  onGlobalRefresh,
  onOpenDocumentIntelligence,
  onOpenVisualForensics,
  onOpenContextualIntelligence,
  currentUser = null,
  onSwitchPersona,
}: InvestigationDossiersViewProps) {
  const [activeTab, setActiveTab] = useState<ActiveDossierTab>("SECTIONS");
  const [dossiers, setDossiers] = useState<DossierSummary[]>([]);
  const [selectedDossier, setSelectedDossier] = useState<DossierDetail | null>(
    null
  );
  const [latestReasoning, setLatestReasoning] =
    useState<InvestigationReasoning | null>(null);

  const [loading, setLoading] = useState(false);
  const [runningReasoning, setRunningReasoning] = useState(false);
  const [generatingDossier, setGeneratingDossier] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters & interactive selection
  const [selectedSectionKey, setSelectedSectionKey] = useState<string>("A");
  const [claimTypeFilter, setClaimTypeFilter] = useState<string>("ALL");
  const [claimSearchQuery, setClaimSearchQuery] = useState<string>("");
  const [manifestSearchQuery, setManifestSearchQuery] = useState<string>("");
  const [manifestTypeFilter, setManifestTypeFilter] = useState<string>("ALL");
  const [highlightedEvidenceId, setHighlightedEvidenceId] = useState<
    string | null
  >(null);

  // New dossier options
  const [customDossierTitle, setCustomDossierTitle] = useState<string>("");
  const [useGeminiSynthesis, setUseGeminiSynthesis] = useState<boolean>(false);

  // Human review form state
  const [reviewStatusInput, setReviewStatusInput] =
    useState<string>("APPROVED");
  const [reviewerNameInput, setReviewerNameInput] = useState<string>(
    selectedInvestigation?.lead_investigator || "Lead Forensic Investigator"
  );
  const [reviewNotesInput, setReviewNotesInput] = useState<string>("");
  const [submittingReview, setSubmittingReview] = useState<boolean>(false);

  const loadDossierWorkspace = useCallback(async (investigationId: string) => {
    setLoading(true);
    setError(null);
    try {
      const [dossierList, reasoningData] = await Promise.all([
        veritasApi.listInvestigationDossiers(investigationId),
        veritasApi.getInvestigationReasoning(investigationId),
      ]);
      setDossiers(dossierList);
      setLatestReasoning(reasoningData);

      if (dossierList.length > 0) {
        const latestDetail = await veritasApi.getDossierDetail(
          dossierList[0].dossier_id
        );
        setSelectedDossier(latestDetail);
        setReviewStatusInput(
          latestDetail.review_status === "UNAPPROVED_AI_ASSISTED"
            ? "APPROVED"
            : latestDetail.review_status
        );
        setReviewNotesInput(latestDetail.review_notes || "");
      } else {
        setSelectedDossier(null);
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to load Phase 5 Investigation Dossier workspace.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedInvestigation) {
      setReviewerNameInput(
        currentUser?.full_name ||
          selectedInvestigation.lead_investigator ||
          "Lead Forensic Investigator"
      );
      loadDossierWorkspace(selectedInvestigation.id);
    }
  }, [selectedInvestigation, currentUser, loadDossierWorkspace]);

  const handleSelectDossierVersion = async (dossierId: string) => {
    setLoading(true);
    setError(null);
    try {
      const detail = await veritasApi.getDossierDetail(dossierId);
      setSelectedDossier(detail);
      setLatestReasoning(detail.reasoning);
      setReviewStatusInput(
        detail.review_status === "UNAPPROVED_AI_ASSISTED"
          ? "APPROVED"
          : detail.review_status
      );
      setReviewNotesInput(detail.review_notes || "");
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load selected dossier version."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleRunReasoning = async () => {
    if (!selectedInvestigation) return;
    setRunningReasoning(true);
    setError(null);
    try {
      const reasoning = await veritasApi.generateInvestigationReasoning(
        selectedInvestigation.id,
        {
          use_ai_provider_if_available: useGeminiSynthesis,
          actor:
            selectedInvestigation.lead_investigator || "Forensic Investigator",
        }
      );
      setLatestReasoning(reasoning);
      onGlobalRefresh();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to execute evidence-grounded reasoning."
      );
    } finally {
      setRunningReasoning(false);
    }
  };

  const handleGenerateDossier = async () => {
    if (!selectedInvestigation) return;
    setGeneratingDossier(true);
    setError(null);
    try {
      const detail = await veritasApi.generateInvestigationDossier(
        selectedInvestigation.id,
        {
          title: customDossierTitle.trim() || undefined,
          actor:
            selectedInvestigation.lead_investigator || "Forensic Investigator",
          regenerate_reasoning: true,
        }
      );
      setSelectedDossier(detail);
      setLatestReasoning(detail.reasoning);
      const updatedList = await veritasApi.listInvestigationDossiers(
        selectedInvestigation.id
      );
      setDossiers(updatedList);
      setCustomDossierTitle("");
      onGlobalRefresh();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to generate immutable investigation dossier."
      );
    } finally {
      setGeneratingDossier(false);
    }
  };

  const handleReviewSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDossier) return;
    setSubmittingReview(true);
    setError(null);
    try {
      const updated = await veritasApi.reviewDossier(
        selectedDossier.dossier_id,
        {
          review_status: reviewStatusInput,
          reviewer: reviewerNameInput.trim() || "Lead Investigator",
          notes: reviewNotesInput.trim(),
        }
      );
      setSelectedDossier(updated);
      if (selectedInvestigation) {
        const updatedList = await veritasApi.listInvestigationDossiers(
          selectedInvestigation.id
        );
        setDossiers(updatedList);
      }
      onGlobalRefresh();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to record human dossier review."
      );
    } finally {
      setSubmittingReview(false);
    }
  };

  const activeReasoning: InvestigationReasoning | null =
    selectedDossier?.reasoning ?? latestReasoning;

  const evidenceManifestList = useMemo<EvidenceManifestItem[]>(() => {
    if (!activeReasoning) return [];
    return Object.values(activeReasoning.evidence_manifest || {});
  }, [activeReasoning]);

  const filteredClaims = useMemo<EvidenceGroundedClaim[]>(() => {
    if (!activeReasoning) return [];
    return activeReasoning.claims.filter((claim) => {
      if (claimTypeFilter !== "ALL" && claim.claim_type !== claimTypeFilter) {
        return false;
      }
      if (claimSearchQuery.trim()) {
        const q = claimSearchQuery.toLowerCase();
        const inText = claim.claim_text.toLowerCase().includes(q);
        const inId = claim.claim_id.toLowerCase().includes(q);
        const inEvid =
          claim.supporting_evidence_ids.some((id) =>
            id.toLowerCase().includes(q)
          ) ||
          claim.contradicting_evidence_ids.some((id) =>
            id.toLowerCase().includes(q)
          );
        return inText || inId || inEvid;
      }
      return true;
    });
  }, [activeReasoning, claimTypeFilter, claimSearchQuery]);

  const filteredManifest = useMemo<EvidenceManifestItem[]>(() => {
    return evidenceManifestList.filter((item) => {
      if (
        manifestTypeFilter !== "ALL" &&
        item.source_type !== manifestTypeFilter
      ) {
        return false;
      }
      if (manifestSearchQuery.trim()) {
        const q = manifestSearchQuery.toLowerCase();
        return (
          item.evidence_id.toLowerCase().includes(q) ||
          item.summary.toLowerCase().includes(q) ||
          item.filename.toLowerCase().includes(q) ||
          item.raw_value.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [evidenceManifestList, manifestTypeFilter, manifestSearchQuery]);

  const activeSectionObj = useMemo(() => {
    if (!activeReasoning || activeReasoning.sections.length === 0) return null;
    return (
      activeReasoning.sections.find(
        (s) => s.section_key === selectedSectionKey
      ) || activeReasoning.sections[0]
    );
  }, [activeReasoning, selectedSectionKey]);

  const handleInspectEvidenceId = (evidId: string) => {
    setHighlightedEvidenceId(evidId);
    setManifestSearchQuery(evidId);
    setManifestTypeFilter("ALL");
    setActiveTab("EVIDENCE_MANIFEST");
  };

  if (!selectedInvestigation) {
    return (
      <div className="rounded-2xl border border-slate-800/80 bg-[#0A101F]/90 p-10 text-center">
        <FileSpreadsheet className="mx-auto h-12 w-12 text-cyan-400" />
        <h2 className="mt-4 text-xl font-bold text-white">
          Select an Active Investigation
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          Choose an investigation case to run evidence-grounded reasoning and
          compile versioned PDF & JSON dossiers.
        </p>
      </div>
    );
  }

  const reviewBadge = getReviewStatusBadge(
    selectedDossier?.review_status || "UNAPPROVED_AI_ASSISTED"
  );

  return (
    <div className="space-y-6">
      {/* Top Case Selector & Phase 5 Header */}
      <div className="rounded-2xl border border-slate-800/90 bg-gradient-to-br from-[#0A1020] via-[#080D1A] to-[#050811] p-6 shadow-2xl">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-cyan-300">
                <BookOpenCheck className="h-3.5 w-3.5" />
                Phase 5 • AI Investigation Reasoning & Dossier Compiler
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[11px] font-semibold ${reviewBadge.className}`}
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                {reviewBadge.label}
              </span>
              {selectedDossier && (
                <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 font-mono text-[11px] font-semibold text-blue-300">
                  Dossier v{selectedDossier.version_number}
                </span>
              )}
            </div>

            <h1 className="mt-3 text-2xl font-bold tracking-tight text-white sm:text-3xl">
              {selectedInvestigation.case_code} — {selectedInvestigation.title}
            </h1>
            <p className="mt-1.5 max-w-3xl text-sm text-slate-400">
              Synthesizes Phase 1–4 document classifications, entities, tables,
              visual forensic signals, and cross-document financial checks into
              strictly evidence-grounded claims and immutable PDF/JSON dossiers.
            </p>
          </div>

          {/* Case Switcher & Primary Actions */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/90 px-3 py-2">
              <FolderKanban className="h-4 w-4 text-cyan-400" />
              <select
                aria-label="Select investigation case"
                value={selectedInvestigation.id}
                onChange={(e) => {
                  const found = investigations.find(
                    (inv) => inv.id === e.target.value
                  );
                  if (found) onSelectInvestigation(found);
                }}
                className="bg-transparent font-mono text-xs font-semibold text-slate-200 focus:outline-none"
              >
                {investigations.map((inv) => (
                  <option
                    key={inv.id}
                    value={inv.id}
                    className="bg-slate-950 text-slate-200"
                  >
                    {inv.case_code} — {inv.title}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={handleRunReasoning}
              disabled={runningReasoning || generatingDossier}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/90 px-4 py-2.5 text-xs font-semibold text-slate-200 transition hover:border-cyan-500/50 hover:text-white disabled:opacity-50"
            >
              {runningReasoning ? (
                <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
              ) : (
                <RefreshCw className="h-4 w-4 text-cyan-400" />
              )}
              Re-Run Reasoning
            </button>

            <button
              type="button"
              onClick={handleGenerateDossier}
              disabled={generatingDossier || runningReasoning}
              className="inline-flex items-center gap-2 rounded-xl border border-cyan-500/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-cyan-500/20 transition hover:brightness-110 disabled:opacity-50"
            >
              {generatingDossier ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              Compile Immutable Dossier{" "}
              {dossiers.length > 0 ? `(v${dossiers[0].version_number + 1})` : "(v1)"}
            </button>
          </div>
        </div>

        {/* Export & Version Bar */}
        {selectedDossier && (
          <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-slate-800/80 pt-4">
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <span className="font-mono text-slate-400">Active Version:</span>
              <div className="flex flex-wrap items-center gap-1.5">
                {dossiers.map((d) => (
                  <button
                    key={d.dossier_id}
                    type="button"
                    onClick={() => handleSelectDossierVersion(d.dossier_id)}
                    className={`rounded-lg border px-2.5 py-1 font-mono text-xs font-semibold transition ${
                      selectedDossier.dossier_id === d.dossier_id
                        ? "border-cyan-500/50 bg-cyan-500/20 text-cyan-200"
                        : "border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                    }`}
                  >
                    v{d.version_number}
                  </button>
                ))}
              </div>
              <span className="hidden text-slate-700 sm:inline">|</span>
              <span className="font-mono text-[11px] text-slate-400">
                Composite SHA-256:{" "}
                <code className="text-cyan-300">
                  {selectedDossier.dossier_sha256_hash.slice(0, 20)}...
                </code>
              </span>
            </div>

            {/* I & J: PDF Export & JSON Export */}
            <div className="flex flex-wrap items-center gap-2.5">
              <a
                href={veritasApi.getDossierPdfUrl(selectedDossier.dossier_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/15 px-3.5 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25"
              >
                <Download className="h-3.5 w-3.5 text-emerald-400" />
                Export PDF Dossier (
                {formatBytes(selectedDossier.pdf_size_bytes)})
              </a>
              <a
                href={veritasApi.getDossierJsonUrl(selectedDossier.dossier_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-xl border border-blue-500/40 bg-blue-500/15 px-3.5 py-2 text-xs font-semibold text-blue-200 transition hover:bg-blue-500/25"
              >
                <FileCode2 className="h-3.5 w-3.5 text-blue-400" />
                Export JSON Dossier (
                {formatBytes(selectedDossier.json_size_bytes)})
              </a>
            </div>
          </div>
        )}
      </div>

      {/* Explicit Epistemic & AI Governance Banner */}
      {activeReasoning && (
        <div className="flex flex-col justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 sm:flex-row sm:items-center">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div className="text-xs text-amber-100/90">
              <span className="font-bold uppercase tracking-wider text-amber-300">
                AI-Assisted & Evidence-Grounded Synthesis Notice:
              </span>{" "}
              Every analytical claim is bound to explicit{" "}
              <code className="font-mono text-amber-200">EVID-*</code> IDs and
              page coordinates. Automated observations are never treated as
              human-confirmed conclusions and never accuse any party of fraud.
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 font-mono text-[11px] text-amber-200/90">
            <Cpu className="h-3.5 w-3.5 text-amber-400" />
            <span>
              Engine: {activeReasoning.ai_provider} ({activeReasoning.ai_model})
            </span>
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertTriangle className="h-5 w-5 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* A. Investigation Intelligence Summary KPI Cards */}
      {activeReasoning && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <div className="rounded-xl border border-slate-800/90 bg-[#0A101F]/90 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
              Evidence Manifest
            </div>
            <div className="mt-1.5 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-white">
                {evidenceManifestList.length}
              </span>
              <span className="font-mono text-[11px] text-cyan-400">
                EVID-* IDs
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Indexed across {activeReasoning.source_document_hashes.length}{" "}
              docs
            </p>
          </div>

          <div className="rounded-xl border border-slate-800/90 bg-[#0A101F]/90 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
              Validated Claims
            </div>
            <div className="mt-1.5 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-emerald-400">
                {activeReasoning.claims.length}
              </span>
              <span className="font-mono text-[11px] text-emerald-300">
                100% Grounded
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Rejected unsupported: {activeReasoning.rejected_claims_count}
            </p>
          </div>

          <div className="rounded-xl border border-slate-800/90 bg-[#0A101F]/90 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
              Reasoning Sections
            </div>
            <div className="mt-1.5 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-cyan-300">
                {activeReasoning.sections.length}
              </span>
              <span className="font-mono text-[11px] text-slate-400">
                Sections A–N
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Structured dossier narrative
            </p>
          </div>

          <div className="rounded-xl border border-slate-800/90 bg-[#0A101F]/90 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
              Contradiction Claims
            </div>
            <div className="mt-1.5 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-amber-400">
                {
                  activeReasoning.claims.filter(
                    (c) => c.contradicting_evidence_ids.length > 0
                  ).length
                }
              </span>
              <span className="font-mono text-[11px] text-amber-300">
                Cross-Doc
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              With opposing evidence IDs
            </p>
          </div>

          <div className="rounded-xl border border-slate-800/90 bg-[#0A101F]/90 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
              Follow-Up Questions
            </div>
            <div className="mt-1.5 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-blue-400">
                {activeReasoning.questions.length}
              </span>
              <span className="font-mono text-[11px] text-blue-300">
                Non-Accusatory
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Evidence-linked inquiries
            </p>
          </div>

          <div className="rounded-xl border border-slate-800/90 bg-[#0A101F]/90 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
              Verification Steps
            </div>
            <div className="mt-1.5 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-purple-400">
                {activeReasoning.verification_steps.length}
              </span>
              <span className="font-mono text-[11px] text-purple-300">
                Actionable
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Human investigator protocol
            </p>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800/80 pb-3">
        {[
          {
            id: "SECTIONS" as ActiveDossierTab,
            label: "Executive Summary & 14 Sections (A–N)",
            icon: FileText,
            count: activeReasoning?.sections.length ?? 0,
          },
          {
            id: "CLAIMS" as ActiveDossierTab,
            label: "Evidence-Backed Claims & Validator",
            icon: ShieldCheck,
            count: activeReasoning?.claims.length ?? 0,
          },
          {
            id: "COMPARISON" as ActiveDossierTab,
            label: "Supporting vs Contradicting Evidence",
            icon: Scale,
            count:
              activeReasoning?.claims.filter(
                (c) => c.contradicting_evidence_ids.length > 0
              ).length ?? 0,
          },
          {
            id: "EVIDENCE_MANIFEST" as ActiveDossierTab,
            label: "Evidence Reference Viewer",
            icon: Layers,
            count: evidenceManifestList.length,
          },
          {
            id: "QUESTIONS_STEPS" as ActiveDossierTab,
            label: "Questions & Verification Steps",
            icon: ListChecks,
            count:
              (activeReasoning?.questions.length ?? 0) +
              (activeReasoning?.verification_steps.length ?? 0),
          },
          {
            id: "VERSIONS_REVIEW" as ActiveDossierTab,
            label: "Version History & Human Approval",
            icon: UserCheck,
            count: dossiers.length,
          },
        ].map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition ${
                active
                  ? "border-cyan-500/40 bg-cyan-500/15 text-white shadow-sm"
                  : "border-slate-800/80 bg-slate-900/60 text-slate-400 hover:border-slate-700 hover:text-slate-200"
              }`}
            >
              <Icon
                className={`h-3.5 w-3.5 ${
                  active ? "text-cyan-400" : "text-slate-500"
                }`}
              />
              <span>{tab.label}</span>
              <span
                className={`rounded-md px-1.5 py-0.5 font-mono text-[10px] ${
                  active
                    ? "bg-cyan-500/20 text-cyan-200"
                    : "bg-slate-800 text-slate-400"
                }`}
              >
                {tab.count}
              </span>
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="flex items-center justify-center rounded-2xl border border-slate-800/80 bg-[#0A101F]/80 p-16">
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <Loader2 className="h-5 w-5 animate-spin text-cyan-400" />
            <span>
              Loading Phase 5 Evidence-Grounded Reasoning & Dossier...
            </span>
          </div>
        </div>
      ) : !activeReasoning ? (
        <div className="rounded-2xl border border-slate-800/80 bg-[#0A101F]/90 p-12 text-center">
          <BookOpenCheck className="mx-auto h-12 w-12 text-cyan-400" />
          <h3 className="mt-4 text-lg font-bold text-white">
            No Investigation Dossier Generated Yet
          </h3>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-400">
            Click &ldquo;Compile Immutable Dossier (v1)&rdquo; above to run the
            Phase 5 Evidence-Grounded Reasoning Engine and compile the initial
            PDF and JSON dossier.
          </p>
        </div>
      ) : (
        <>
          {/* TAB 1: EXECUTIVE SUMMARY & 14 STRUCTURED SECTIONS */}
          {activeTab === "SECTIONS" && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              {/* Left Section Index (A through N) */}
              <div className="space-y-1.5 lg:col-span-4">
                <div className="mb-2 px-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  14 Structured Reasoning Sections
                </div>
                {activeReasoning.sections.map((sec) => {
                  const isSelected =
                    activeSectionObj?.section_key === sec.section_key;
                  return (
                    <button
                      key={sec.section_key}
                      type="button"
                      onClick={() => setSelectedSectionKey(sec.section_key)}
                      className={`flex w-full items-center justify-between rounded-xl border px-3.5 py-2.5 text-left transition ${
                        isSelected
                          ? "border-cyan-500/40 bg-cyan-500/15 text-white"
                          : "border-slate-800/80 bg-[#0A101F]/80 text-slate-300 hover:border-slate-700 hover:bg-slate-900"
                      }`}
                    >
                      <div className="flex items-center gap-2.5 truncate">
                        <span
                          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md font-mono text-xs font-bold ${
                            isSelected
                              ? "bg-cyan-500 text-slate-950"
                              : "bg-slate-800 text-cyan-300"
                          }`}
                        >
                          {sec.section_key}
                        </span>
                        <span className="truncate text-xs font-medium">
                          {sec.title}
                        </span>
                      </div>
                      <span className="ml-2 shrink-0 rounded bg-slate-800/90 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                        {sec.claim_ids.length} claims
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Right Active Section Detail + Claims */}
              <div className="space-y-5 lg:col-span-8">
                {activeSectionObj && (
                  <div className="rounded-2xl border border-slate-800/90 bg-[#0A101F]/95 p-6">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-4">
                      <div>
                        <span className="font-mono text-xs font-semibold uppercase tracking-wider text-cyan-400">
                          Section {activeSectionObj.section_key} •{" "}
                          {activeSectionObj.section_code}
                        </span>
                        <h2 className="mt-1 text-xl font-bold text-white">
                          {activeSectionObj.title}
                        </h2>
                      </div>
                      <div className="flex items-center gap-2 font-mono text-xs text-slate-400">
                        <span>
                          {activeSectionObj.claim_ids.length} Grounded Claims
                        </span>
                        <span>•</span>
                        <span>
                          {activeSectionObj.evidence_ids.length} Evidence Refs
                        </span>
                      </div>
                    </div>

                    {/* Section Narrative */}
                    <div className="mt-4 rounded-xl border border-slate-800/90 bg-slate-950/70 p-4 text-sm leading-relaxed text-slate-200">
                      {activeSectionObj.narrative}
                    </div>

                    {/* Referenced Evidence Badges */}
                    {activeSectionObj.evidence_ids.length > 0 && (
                      <div className="mt-4">
                        <div className="mb-2 font-mono text-[11px] uppercase tracking-wider text-slate-400">
                          Referenced Evidence Manifest IDs (Click to Inspect
                          Source)
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {activeSectionObj.evidence_ids.map((evidId) => (
                            <button
                              key={evidId}
                              type="button"
                              onClick={() => handleInspectEvidenceId(evidId)}
                              className="inline-flex items-center gap-1 rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[11px] text-cyan-300 transition hover:border-cyan-400 hover:bg-cyan-500/20"
                            >
                              <span>{evidId}</span>
                              <ExternalLink className="h-2.5 w-2.5" />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Claims belonging to this section */}
                    <div className="mt-6 space-y-3">
                      <div className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-300">
                        Evidence-Grounded Claims in Section{" "}
                        {activeSectionObj.section_key}
                      </div>
                      {activeReasoning.claims
                        .filter(
                          (c) => c.section_key === activeSectionObj.section_key
                        )
                        .map((claim) => {
                          const badge = getClaimTypeBadge(claim.claim_type);
                          return (
                            <div
                              key={claim.claim_id}
                              className="rounded-xl border border-slate-800/90 bg-slate-900/60 p-4"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-mono text-xs font-bold text-cyan-300">
                                    {claim.claim_id}
                                  </span>
                                  <span
                                    className={`rounded-md border px-2 py-0.5 font-mono text-[10px] font-semibold ${badge.className}`}
                                  >
                                    {badge.label}
                                  </span>
                                </div>
                                <span className="font-mono text-xs text-slate-400">
                                  Confidence:{" "}
                                  <strong className="text-white">
                                    {(claim.confidence_score * 100).toFixed(1)}%
                                  </strong>
                                </span>
                              </div>

                              <p className="mt-2.5 text-sm leading-relaxed text-slate-100">
                                {claim.claim_text}
                              </p>

                              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                                {claim.supporting_evidence_ids.map((id) => (
                                  <button
                                    key={id}
                                    type="button"
                                    onClick={() => handleInspectEvidenceId(id)}
                                    className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] text-emerald-300 hover:bg-emerald-500/20"
                                  >
                                    + Support: {id}
                                  </button>
                                ))}
                                {claim.contradicting_evidence_ids.map((id) => (
                                  <button
                                    key={id}
                                    type="button"
                                    onClick={() => handleInspectEvidenceId(id)}
                                    className="rounded border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 font-mono text-[10px] text-rose-300 hover:bg-rose-500/20"
                                  >
                                    ! Contradicts: {id}
                                  </button>
                                ))}
                                {claim.page_references.map((ref, idx) => (
                                  <span
                                    key={`${ref.document_id}-${ref.page_number}-${idx}`}
                                    className="rounded border border-slate-700 bg-slate-800/80 px-2 py-0.5 font-mono text-[10px] text-slate-300"
                                  >
                                    {ref.filename} (p.{ref.page_number})
                                  </span>
                                ))}
                              </div>

                              <div className="mt-2.5 border-t border-slate-800/70 pt-2 text-[11px] text-slate-400">
                                <span className="font-mono text-slate-500">
                                  Method: {claim.reasoning_method}
                                </span>{" "}
                                — {claim.confidence_interpretation}
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: EVIDENCE-BACKED CLAIMS & VALIDATOR LOG */}
          {activeTab === "CLAIMS" && (
            <div className="space-y-6">
              {/* Filter bar */}
              <div className="flex flex-col gap-3 rounded-2xl border border-slate-800/90 bg-[#0A101F]/90 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2">
                  <Search className="h-4 w-4 text-slate-500" />
                  <input
                    type="text"
                    value={claimSearchQuery}
                    onChange={(e) => setClaimSearchQuery(e.target.value)}
                    placeholder="Filter claims by text, CLAIM-ID, or EVID-ID..."
                    className="w-full bg-transparent text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <Filter className="h-4 w-4 text-cyan-400" />
                  <select
                    aria-label="Filter by claim type"
                    value={claimTypeFilter}
                    onChange={(e) => setClaimTypeFilter(e.target.value)}
                    className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-200 focus:outline-none"
                  >
                    <option value="ALL">All Claim Categories</option>
                    <option value="DIRECTLY_OBSERVED_FACT">
                      DIRECTLY_OBSERVED_FACT
                    </option>
                    <option value="DETERMINISTIC_CALCULATION_RESULT">
                      DETERMINISTIC_CALCULATION_RESULT
                    </option>
                    <option value="AUTOMATED_TECHNICAL_OBSERVATION">
                      AUTOMATED_TECHNICAL_OBSERVATION
                    </option>
                    <option value="POTENTIAL_INTERPRETATION">
                      POTENTIAL_INTERPRETATION
                    </option>
                    <option value="HUMAN_CONFIRMED_CONCLUSION">
                      HUMAN_CONFIRMED_CONCLUSION
                    </option>
                    <option value="UNKNOWN_OR_MISSING_INFORMATION">
                      UNKNOWN_OR_MISSING_INFORMATION
                    </option>
                  </select>
                </div>
              </div>

              {/* Strict Claim Grounding Validator Status */}
              <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                    <span className="text-sm font-semibold text-white">
                      Evidence-Reference Validator Active
                    </span>
                  </div>
                  <span className="font-mono text-xs text-emerald-300">
                    {activeReasoning.claims.length} Validated Claims •{" "}
                    {activeReasoning.rejected_claims_count} Unsupported Claims
                    Rejected
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  Every claim below has passed mandatory verification for
                  non-empty evidence IDs, valid manifest linkage, page
                  references, and human-confirmation guardrails.
                </p>
              </div>

              {/* Claims List */}
              <div className="space-y-3">
                {filteredClaims.map((claim) => {
                  const badge = getClaimTypeBadge(claim.claim_type);
                  return (
                    <div
                      key={claim.claim_id}
                      className="rounded-2xl border border-slate-800/90 bg-[#0A101F]/90 p-5"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded bg-cyan-500/15 px-2 py-0.5 font-mono text-xs font-bold text-cyan-300">
                            {claim.claim_id}
                          </span>
                          <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300">
                            Section {claim.section_key}
                          </span>
                          <span
                            className={`rounded-md border px-2.5 py-0.5 font-mono text-[10px] font-semibold ${badge.className}`}
                          >
                            {badge.label}
                          </span>
                        </div>
                        <span className="font-mono text-xs text-slate-400">
                          Confidence:{" "}
                          <strong className="text-white">
                            {(claim.confidence_score * 100).toFixed(1)}%
                          </strong>
                        </span>
                      </div>

                      <p className="mt-3 text-sm leading-relaxed text-white">
                        {claim.claim_text}
                      </p>

                      <div className="mt-3 grid grid-cols-1 gap-3 rounded-xl border border-slate-800/80 bg-slate-950/60 p-3 sm:grid-cols-2">
                        <div>
                          <div className="font-mono text-[10px] uppercase text-emerald-400">
                            Supporting Evidence IDs (
                            {claim.supporting_evidence_ids.length})
                          </div>
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {claim.supporting_evidence_ids.map((id) => (
                              <button
                                key={id}
                                type="button"
                                onClick={() => handleInspectEvidenceId(id)}
                                className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[11px] text-emerald-300 hover:bg-emerald-500/20"
                              >
                                {id}
                              </button>
                            ))}
                          </div>
                        </div>

                        <div>
                          <div className="font-mono text-[10px] uppercase text-rose-400">
                            Contradicting Evidence IDs (
                            {claim.contradicting_evidence_ids.length})
                          </div>
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {claim.contradicting_evidence_ids.length === 0 ? (
                              <span className="font-mono text-xs text-slate-500">
                                None
                              </span>
                            ) : (
                              claim.contradicting_evidence_ids.map((id) => (
                                <button
                                  key={id}
                                  type="button"
                                  onClick={() => handleInspectEvidenceId(id)}
                                  className="rounded border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 font-mono text-[11px] text-rose-300 hover:bg-rose-500/20"
                                >
                                  {id}
                                </button>
                              ))
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-mono text-[11px] text-slate-500">
                            Page Citations:
                          </span>
                          {claim.page_references.map((ref, idx) => (
                            <span
                              key={`${ref.document_id}-${ref.page_number}-${idx}`}
                              className="rounded border border-slate-800 bg-slate-900 px-2 py-0.5 font-mono text-[11px] text-slate-300"
                            >
                              {ref.filename} • Page {ref.page_number}
                            </span>
                          ))}
                        </div>
                        <span className="font-mono text-[11px] text-slate-500">
                          Method: {claim.reasoning_method}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 3: SUPPORTING VS CONTRADICTING EVIDENCE COMPARISON */}
          {activeTab === "COMPARISON" && (
            <div className="space-y-5">
              <div className="rounded-2xl border border-slate-800/90 bg-[#0A101F]/90 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-bold text-white">
                      Supporting vs. Contradicting Evidence Comparison
                    </h3>
                    <p className="mt-1 text-xs text-slate-400">
                      Side-by-side evidentiary matrix contrasting primary
                      supporting records against conflicting cross-document
                      observations.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={onOpenContextualIntelligence}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20"
                  >
                    <GitCompareArrows className="h-4 w-4" />
                    Open Contextual Intelligence Engine
                  </button>
                </div>
              </div>

              {activeReasoning.claims
                .filter((c) => c.contradicting_evidence_ids.length > 0)
                .map((claim) => (
                  <div
                    key={claim.claim_id}
                    className="rounded-2xl border border-amber-500/30 bg-[#0A101F]/95 p-5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-amber-500/20 px-2 py-0.5 font-mono text-xs font-bold text-amber-300">
                          {claim.claim_id}
                        </span>
                        <span className="text-sm font-semibold text-white">
                          Cross-Document Evidentiary Conflict
                        </span>
                      </div>
                      <span className="font-mono text-xs text-slate-400">
                        Confidence: {(claim.confidence_score * 100).toFixed(1)}%
                      </span>
                    </div>

                    <p className="mt-3 text-sm text-slate-200">
                      {claim.claim_text}
                    </p>

                    <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
                      {/* Left: Supporting Evidence */}
                      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
                        <div className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-300">
                          Primary / Supporting Evidence Records
                        </div>
                        <div className="mt-3 space-y-2.5">
                          {claim.supporting_evidence_ids.map((id) => {
                            const item = activeReasoning.evidence_manifest[id];
                            return (
                              <div
                                key={id}
                                className="rounded-lg border border-emerald-500/20 bg-slate-950/80 p-3 text-xs"
                              >
                                <div className="flex items-center justify-between font-mono">
                                  <button
                                    type="button"
                                    onClick={() => handleInspectEvidenceId(id)}
                                    className="font-bold text-emerald-300 underline"
                                  >
                                    {id}
                                  </button>
                                  <span className="text-slate-400">
                                    {item?.filename} (p.{item?.page_number})
                                  </span>
                                </div>
                                <p className="mt-1.5 text-slate-200">
                                  {item?.summary}
                                </p>
                                <div className="mt-1 font-mono text-[11px] text-emerald-200/80">
                                  Observed: {item?.raw_value}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Right: Contradicting Evidence */}
                      <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4">
                        <div className="font-mono text-xs font-bold uppercase tracking-wider text-rose-300">
                          Contradicting / Opposing Evidence Records
                        </div>
                        <div className="mt-3 space-y-2.5">
                          {claim.contradicting_evidence_ids.map((id) => {
                            const item = activeReasoning.evidence_manifest[id];
                            return (
                              <div
                                key={id}
                                className="rounded-lg border border-rose-500/20 bg-slate-950/80 p-3 text-xs"
                              >
                                <div className="flex items-center justify-between font-mono">
                                  <button
                                    type="button"
                                    onClick={() => handleInspectEvidenceId(id)}
                                    className="font-bold text-rose-300 underline"
                                  >
                                    {id}
                                  </button>
                                  <span className="text-slate-400">
                                    {item?.filename} (p.{item?.page_number})
                                  </span>
                                </div>
                                <p className="mt-1.5 text-slate-200">
                                  {item?.summary}
                                </p>
                                <div className="mt-1 font-mono text-[11px] text-rose-200/80">
                                  Observed: {item?.raw_value}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          )}

          {/* TAB 4: EVIDENCE REFERENCE VIEWER */}
          {activeTab === "EVIDENCE_MANIFEST" && (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 rounded-2xl border border-slate-800/90 bg-[#0A101F]/90 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2">
                  <Search className="h-4 w-4 text-slate-500" />
                  <input
                    type="text"
                    value={manifestSearchQuery}
                    onChange={(e) => setManifestSearchQuery(e.target.value)}
                    placeholder="Search Evidence Manifest by EVID-ID, filename, or value..."
                    className="w-full bg-transparent text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
                  />
                  {manifestSearchQuery && (
                    <button
                      type="button"
                      onClick={() => {
                        setManifestSearchQuery("");
                        setHighlightedEvidenceId(null);
                      }}
                      className="font-mono text-[10px] text-slate-400 hover:text-white"
                    >
                      CLEAR
                    </button>
                  )}
                </div>

                <select
                  aria-label="Filter evidence source type"
                  value={manifestTypeFilter}
                  onChange={(e) => setManifestTypeFilter(e.target.value)}
                  className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-200 focus:outline-none"
                >
                  <option value="ALL">All Evidence Source Types</option>
                  <option value="DOCUMENT">DOCUMENT (EVID-DOC-*)</option>
                  <option value="TABLE">TABLE (EVID-TBL-*)</option>
                  <option value="VISUAL_FORENSIC_FINDING">
                    VISUAL_FORENSIC_FINDING (EVID-VIS-*)
                  </option>
                  <option value="FINANCIAL_VALIDATION">
                    FINANCIAL_VALIDATION (EVID-FIN-*)
                  </option>
                  <option value="CONTEXTUAL_FINDING">
                    CONTEXTUAL_FINDING (EVID-CTX-*)
                  </option>
                  <option value="ENTITY_RESOLUTION">
                    ENTITY_RESOLUTION (EVID-ENT-*)
                  </option>
                </select>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {filteredManifest.map((item) => {
                  const isHighlighted =
                    highlightedEvidenceId === item.evidence_id;
                  return (
                    <div
                      key={item.evidence_id}
                      className={`rounded-2xl border p-4 transition ${
                        isHighlighted
                          ? "border-cyan-400 bg-cyan-500/10 shadow-lg shadow-cyan-500/10"
                          : "border-slate-800/90 bg-[#0A101F]/90"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-cyan-500/20 px-2 py-0.5 font-mono text-xs font-bold text-cyan-300">
                            {item.evidence_id}
                          </span>
                          <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                            {item.source_type}
                          </span>
                        </div>
                        <span className="font-mono text-[11px] text-slate-400">
                          Conf: {(item.confidence_score * 100).toFixed(1)}%
                        </span>
                      </div>

                      <p className="mt-2.5 text-xs font-medium text-white">
                        {item.summary}
                      </p>

                      <div className="mt-2.5 space-y-1 rounded-lg border border-slate-800/80 bg-slate-950/70 p-2.5 font-mono text-[11px]">
                        <div className="flex justify-between text-slate-400">
                          <span>Document:</span>
                          <span className="text-slate-200">
                            {item.filename} (Page {item.page_number})
                          </span>
                        </div>
                        <div className="flex justify-between text-slate-400">
                          <span>Raw Value:</span>
                          <span className="truncate pl-2 text-cyan-300">
                            {item.raw_value}
                          </span>
                        </div>
                        {item.document_sha256 && (
                          <div className="flex justify-between text-slate-400">
                            <span>SHA-256:</span>
                            <span className="text-slate-300">
                              {item.document_sha256.slice(0, 16)}...
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-[10px] text-slate-400">
                          Status: {item.review_status}
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={onOpenDocumentIntelligence}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] font-medium text-slate-200 hover:border-cyan-500/40 hover:text-cyan-300"
                          >
                            <FileSearch className="h-3 w-3" />
                            Inspect Document
                          </button>
                          {item.document_id && (
                            <button
                              type="button"
                              onClick={() =>
                                item.document_id &&
                                onOpenVisualForensics(item.document_id)
                              }
                              className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] font-medium text-slate-200 hover:border-cyan-500/40 hover:text-cyan-300"
                            >
                              <ScanEye className="h-3 w-3" />
                              Visual Forensics
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 5: INVESTIGATION QUESTIONS & RECOMMENDED VERIFICATION STEPS */}
          {activeTab === "QUESTIONS_STEPS" && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {/* F. Investigation Questions */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <HelpCircle className="h-5 w-5 text-cyan-400" />
                  <h3 className="text-lg font-bold text-white">
                    Non-Accusatory Investigation Questions (
                    {activeReasoning.questions.length})
                  </h3>
                </div>
                {activeReasoning.questions.map((q) => (
                  <div
                    key={q.question_id}
                    className="rounded-2xl border border-slate-800/90 bg-[#0A101F]/90 p-5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="rounded bg-blue-500/20 px-2.5 py-0.5 font-mono text-xs font-bold text-blue-300">
                        {q.question_id}
                      </span>
                      <span
                        className={`rounded-full px-2.5 py-0.5 font-mono text-[10px] font-semibold ${
                          q.priority === "HIGH"
                            ? "border border-amber-500/40 bg-amber-500/15 text-amber-300"
                            : "border border-slate-700 bg-slate-800 text-slate-300"
                        }`}
                      >
                        {q.priority} PRIORITY
                      </span>
                    </div>
                    <p className="mt-3 text-sm font-semibold text-white">
                      {q.question_text}
                    </p>
                    <p className="mt-2 text-xs leading-relaxed text-slate-400">
                      {q.rationale}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {q.related_evidence_ids.map((id) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => handleInspectEvidenceId(id)}
                          className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] text-cyan-300 hover:bg-cyan-500/20"
                        >
                          {id}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {/* G. Recommended Human Verification Steps */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <ClipboardCheck className="h-5 w-5 text-emerald-400" />
                  <h3 className="text-lg font-bold text-white">
                    Recommended Human Verification Steps (
                    {activeReasoning.verification_steps.length})
                  </h3>
                </div>
                {activeReasoning.verification_steps.map((step) => (
                  <div
                    key={step.step_id}
                    className="rounded-2xl border border-slate-800/90 bg-[#0A101F]/90 p-5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="rounded bg-emerald-500/20 px-2.5 py-0.5 font-mono text-xs font-bold text-emerald-300">
                        {step.step_id} • Step {step.step_number}
                      </span>
                      <span
                        className={`rounded-full px-2.5 py-0.5 font-mono text-[10px] font-semibold ${
                          step.priority === "HIGH"
                            ? "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                            : "border border-slate-700 bg-slate-800 text-slate-300"
                        }`}
                      >
                        {step.priority} PRIORITY
                      </span>
                    </div>
                    <h4 className="mt-3 text-sm font-bold text-white">
                      {step.title}
                    </h4>
                    <p className="mt-1.5 text-xs leading-relaxed text-slate-300">
                      {step.action_description}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {step.target_evidence_ids.map((id) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => handleInspectEvidenceId(id)}
                          className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] text-emerald-300 hover:bg-emerald-500/20"
                        >
                          Target: {id}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 6: DOSSIER VERSION HISTORY & HUMAN REVIEW / APPROVAL */}
          {activeTab === "VERSIONS_REVIEW" && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              {/* H. Immutable Dossier Version History */}
              <div className="space-y-4 lg:col-span-7">
                <div className="rounded-2xl border border-slate-800/90 bg-[#0A101F]/90 p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <History className="h-5 w-5 text-cyan-400" />
                      <h3 className="text-lg font-bold text-white">
                        Immutable Dossier Version History ({dossiers.length})
                      </h3>
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    Generating a new dossier creates a new versioned artifact (
                    <code className="text-cyan-300">v1, v2, ...</code>) without
                    overwriting prior versions or their SHA-256 fingerprints.
                  </p>

                  {/* Compile New Version With Optional Custom Title */}
                  <div className="mt-4 flex flex-col gap-2.5 rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 sm:flex-row sm:items-center">
                    <input
                      type="text"
                      value={customDossierTitle}
                      onChange={(e) => setCustomDossierTitle(e.target.value)}
                      placeholder="Optional custom title for next dossier version..."
                      className="flex-1 bg-transparent text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
                    />
                    <label className="flex items-center gap-1.5 font-mono text-[11px] text-slate-400">
                      <input
                        type="checkbox"
                        checked={useGeminiSynthesis}
                        onChange={(e) =>
                          setUseGeminiSynthesis(e.target.checked)
                        }
                        className="rounded border-slate-700 bg-slate-900 text-cyan-500"
                      />
                      Try Gemini Synthesis
                    </label>
                    <button
                      type="button"
                      onClick={handleGenerateDossier}
                      disabled={generatingDossier}
                      className="rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
                    >
                      Compile New Version
                    </button>
                  </div>

                  <div className="mt-4 space-y-3">
                    {dossiers.map((d) => {
                      const badge = getReviewStatusBadge(d.review_status);
                      const isCurrent =
                        selectedDossier?.dossier_id === d.dossier_id;
                      return (
                        <div
                          key={d.dossier_id}
                          className={`rounded-xl border p-4 transition ${
                            isCurrent
                              ? "border-cyan-500/50 bg-cyan-500/10"
                              : "border-slate-800 bg-slate-950/60"
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span className="rounded bg-cyan-500 px-2 py-0.5 font-mono text-xs font-bold text-slate-950">
                                v{d.version_number}
                              </span>
                              <span className="text-sm font-bold text-white">
                                {d.title}
                              </span>
                            </div>
                            <span
                              className={`rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-semibold ${badge.className}`}
                            >
                              {badge.label}
                            </span>
                          </div>

                          <div className="mt-3 grid grid-cols-1 gap-1.5 font-mono text-[11px] text-slate-400 sm:grid-cols-2">
                            <div>
                              Dossier SHA-256:{" "}
                              <span className="text-cyan-300">
                                {d.dossier_sha256_hash.slice(0, 18)}...
                              </span>
                            </div>
                            <div>
                              PDF SHA-256:{" "}
                              <span className="text-slate-300">
                                {d.pdf_sha256_hash.slice(0, 18)}...
                              </span>
                            </div>
                            <div>
                              JSON SHA-256:{" "}
                              <span className="text-slate-300">
                                {d.json_sha256_hash.slice(0, 18)}...
                              </span>
                            </div>
                            <div>
                              Created:{" "}
                              <span className="text-slate-300">
                                {new Date(d.created_at).toLocaleString()}
                              </span>
                            </div>
                          </div>

                          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/80 pt-2.5">
                            <button
                              type="button"
                              onClick={() =>
                                handleSelectDossierVersion(d.dossier_id)
                              }
                              className="text-xs font-semibold text-cyan-400 hover:underline"
                            >
                              {isCurrent
                                ? "Currently Viewing"
                                : `Switch to v${d.version_number}`}
                            </button>
                            <div className="flex items-center gap-2">
                              <a
                                href={veritasApi.getDossierPdfUrl(d.dossier_id)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] text-emerald-300 hover:bg-emerald-500/20"
                              >
                                PDF ({formatBytes(d.pdf_size_bytes)})
                              </a>
                              <a
                                href={veritasApi.getDossierJsonUrl(
                                  d.dossier_id
                                )}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="rounded border border-blue-500/30 bg-blue-500/10 px-2.5 py-1 font-mono text-[11px] text-blue-300 hover:bg-blue-500/20"
                              >
                                JSON ({formatBytes(d.json_size_bytes)})
                              </a>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* K. Human Review & Approval Workflow */}
              <div className="space-y-4 lg:col-span-5">
                {selectedDossier && (
                  <div className="rounded-2xl border border-slate-800/90 bg-[#0A101F]/90 p-5">
                    <div className="flex items-center gap-2">
                      <UserCheck className="h-5 w-5 text-emerald-400" />
                      <h3 className="text-lg font-bold text-white">
                        Human Investigator Review & Approval (v
                        {selectedDossier.version_number})
                      </h3>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">
                      AI-generated dossier content remains marked as unapproved
                      until explicitly reviewed by an authenticated Reviewer or
                      Administrator under Separation-of-Duties controls.
                    </p>

                    {currentUser &&
                      currentUser.role !== "REVIEWER" &&
                      currentUser.role !== "ADMIN" && (
                        <div className="mt-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">
                          <div className="font-bold text-amber-300">
                            Separation-of-Duties & RBAC Guard Active
                          </div>
                          <p className="mt-1 text-[11px] text-amber-100/90">
                            You are currently signed in as{" "}
                            <strong>{currentUser.full_name}</strong> (
                            <code className="font-mono">{currentUser.role}</code>
                            ). Dossier review & approval requires{" "}
                            <code className="font-mono">REVIEWER</code> or{" "}
                            <code className="font-mono">ADMIN</code> privileges,
                            and creators cannot self-approve their own dossiers.
                          </p>
                          {onSwitchPersona && (
                            <button
                              type="button"
                              onClick={() => onSwitchPersona("m.vance")}
                              className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-amber-400/50 bg-amber-500/20 px-2.5 py-1 font-mono text-[11px] font-semibold text-amber-200 hover:bg-amber-500/30"
                            >
                              <UserCheck className="h-3.5 w-3.5" />
                              Switch to Marcus Vance (REVIEWER)
                            </button>
                          )}
                        </div>
                      )}

                    <form
                      onSubmit={handleReviewSubmit}
                      className="mt-4 space-y-3.5"
                    >
                      <div>
                        <label className="block font-mono text-[11px] uppercase text-slate-400">
                          Review Decision
                        </label>
                        <select
                          value={reviewStatusInput}
                          onChange={(e) => setReviewStatusInput(e.target.value)}
                          className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-white focus:border-cyan-500 focus:outline-none"
                        >
                          <option value="APPROVED">
                            APPROVED — Investigator Verified Dossier
                          </option>
                          <option value="UNDER_REVIEW">
                            UNDER_REVIEW — Active Verification in Progress
                          </option>
                          <option value="REQUIRES_REVISION">
                            REQUIRES_REVISION — Additional Evidence Required
                          </option>
                          <option value="UNAPPROVED_AI_ASSISTED">
                            UNAPPROVED_AI_ASSISTED — Reset to Unapproved
                          </option>
                          <option value="ARCHIVED">
                            ARCHIVED — Superseded Dossier Version
                          </option>
                        </select>
                      </div>

                      <div>
                        <label className="block font-mono text-[11px] uppercase text-slate-400">
                          Authenticated Reviewer Identity (Session-Derived)
                        </label>
                        <input
                          type="text"
                          required
                          readOnly={Boolean(currentUser)}
                          value={
                            currentUser
                              ? `${currentUser.full_name} (${currentUser.role})`
                              : reviewerNameInput
                          }
                          onChange={(e) => setReviewerNameInput(e.target.value)}
                          className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-cyan-200 focus:border-cyan-500 focus:outline-none"
                        />
                      </div>

                      <div>
                        <label className="block font-mono text-[11px] uppercase text-slate-400">
                          Investigator Sign-Off Notes
                        </label>
                        <textarea
                          rows={3}
                          value={reviewNotesInput}
                          onChange={(e) => setReviewNotesInput(e.target.value)}
                          placeholder="Record human verification findings, subpoena references, or approval rationale..."
                          className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                        />
                      </div>

                      <button
                        type="submit"
                        disabled={submittingReview}
                        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-500 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-emerald-500/20 hover:brightness-110 disabled:opacity-50"
                      >
                        {submittingReview ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <CheckCircle2 className="h-4 w-4" />
                        )}
                        Record Human Investigator Decision
                      </button>
                    </form>

                    {/* Review History Log */}
                    <div className="mt-6 border-t border-slate-800 pt-4">
                      <div className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
                        Dossier Review Audit Log (
                        {selectedDossier.review_history.length})
                      </div>
                      {selectedDossier.review_history.length === 0 ? (
                        <p className="mt-2 text-xs text-slate-500">
                          No human review decisions recorded yet for Dossier v
                          {selectedDossier.version_number}.
                        </p>
                      ) : (
                        <div className="mt-2.5 space-y-2">
                          {selectedDossier.review_history.map((rev) => (
                            <div
                              key={rev.review_id}
                              className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs"
                            >
                              <div className="flex items-center justify-between font-mono text-[11px]">
                                <span className="font-bold text-emerald-300">
                                  {rev.previous_status} → {rev.new_status}
                                </span>
                                <span className="text-slate-500">
                                  {new Date(rev.created_at).toLocaleString()}
                                </span>
                              </div>
                              <div className="mt-1 text-slate-300">
                                Reviewer: <strong>{rev.reviewer}</strong>
                              </div>
                              {rev.notes && (
                                <p className="mt-1 text-slate-400">
                                  {rev.notes}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
