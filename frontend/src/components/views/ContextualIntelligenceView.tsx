"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Calculator,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Eye,
  FileSearch,
  FileSpreadsheet,
  FileWarning,
  Filter,
  GitCompareArrows,
  HelpCircle,
  History,
  Info,
  Layers,
  Network,
  RefreshCw,
  Scale,
  ScanEye,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { veritasApi } from "@/lib/api";
import {
  ContextualAnalysisBundle,
  ContextualFinding,
  EntityMatchCluster,
  EvidenceValueItem,
  FinancialValidationResult,
  GraphEdge,
  GraphNode,
  Investigation,
  NavigationSectionId,
} from "@/types/veritas";

type WorkspaceTab =
  | "CONTRADICTION_EXPLORER"
  | "EVIDENCE_GRAPH"
  | "ENTITY_RESOLUTION"
  | "FINANCIAL_VALIDATION"
  | "TIMELINE";

interface ContextualIntelligenceViewProps {
  activeSection: NavigationSectionId;
  investigations: Investigation[];
  selectedInvestigation: Investigation | null;
  onSelectInvestigation: (inv: Investigation) => void;
  onGlobalRefresh: () => void;
  onOpenDocumentIntelligence?: (docId: string) => void;
  onOpenVisualForensics?: (docId: string) => void;
}

function statusBadgeStyle(status: string): string {
  switch (status) {
    case "CONFIRMED_DATA_MISMATCH":
      return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    case "POTENTIAL_INCONSISTENCY":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    case "MISSING_INFORMATION":
      return "border-purple-500/40 bg-purple-500/15 text-purple-300";
    case "CONSISTENT_EVIDENCE":
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    case "INCONCLUSIVE_RESULT":
      return "border-slate-500/40 bg-slate-500/15 text-slate-300";
    default:
      return "border-cyan-500/40 bg-cyan-500/15 text-cyan-300";
  }
}

function statusDisplayLabel(status: string): string {
  switch (status) {
    case "CONFIRMED_DATA_MISMATCH":
      return "Confirmed Data Mismatch";
    case "POTENTIAL_INCONSISTENCY":
      return "Potential Inconsistency";
    case "MISSING_INFORMATION":
      return "Missing Information";
    case "CONSISTENT_EVIDENCE":
      return "Consistent Evidence";
    case "INCONCLUSIVE_RESULT":
      return "Inconclusive Result";
    default:
      return status.replace(/_/g, " ");
  }
}

function severityBadgeStyle(severity: string): string {
  switch (severity) {
    case "HIGH":
      return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    case "MEDIUM":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    case "LOW":
      return "border-blue-500/40 bg-blue-500/15 text-blue-300";
    default:
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
  }
}

function reviewBadgeStyle(reviewStatus: string): string {
  switch (reviewStatus) {
    case "CONFIRMED":
      return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    case "REVIEWED":
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    case "INCONCLUSIVE":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    case "DISMISSED":
      return "border-slate-600 bg-slate-800/80 text-slate-400";
    default:
      return "border-cyan-500/40 bg-cyan-500/10 text-cyan-300";
  }
}

export default function ContextualIntelligenceView({
  activeSection,
  investigations,
  selectedInvestigation,
  onSelectInvestigation,
  onGlobalRefresh,
  onOpenDocumentIntelligence,
  onOpenVisualForensics,
}: ContextualIntelligenceViewProps) {
  const defaultTabForSection = useCallback(
    (section: NavigationSectionId): WorkspaceTab => {
      if (section === "cross-document-analysis") return "EVIDENCE_GRAPH";
      if (section === "evidence-explorer") return "ENTITY_RESOLUTION";
      return "CONTRADICTION_EXPLORER";
    },
    []
  );

  const [activeTab, setActiveTab] = useState<WorkspaceTab>(() =>
    defaultTabForSection(activeSection)
  );

  useEffect(() => {
    setActiveTab(defaultTabForSection(activeSection));
  }, [activeSection, defaultTabForSection]);

  const [contextBundle, setContextBundle] =
    useState<ContextualAnalysisBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters & Selection in Contradiction Explorer
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [reviewFilter, setReviewFilter] = useState<string>("ALL");
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(
    null
  );
  const [selectedEvidencePreview, setSelectedEvidencePreview] =
    useState<EvidenceValueItem | null>(null);

  // Selection in Evidence Relationship Graph
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [graphFilterEdgeType, setGraphFilterEdgeType] = useState<string>("ALL");

  // Selection in Entity Resolution
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>("ALL");
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(
    null
  );

  // Human Review state
  const [reviewStatusInput, setReviewStatusInput] =
    useState<string>("CONFIRMED");
  const [reviewerInput, setReviewerInput] = useState<string>(
    "Dr. Elena Rostova (Principal Forensic Analyst)"
  );
  const [reviewNotesInput, setReviewNotesInput] = useState<string>("");
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewSuccessMsg, setReviewSuccessMsg] = useState<string | null>(null);

  const loadInvestigationContext = useCallback(async (invId: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await veritasApi.getInvestigationContext(invId);
      setContextBundle(data);
      if (data.findings.length > 0) {
        setSelectedFindingId((prev) => {
          if (prev && data.findings.some((f) => f.finding_id === prev)) {
            return prev;
          }
          return data.findings[0].finding_id;
        });
      } else {
        setSelectedFindingId(null);
      }
      if (data.entity_matches.length > 0) {
        setSelectedClusterId((prev) => {
          if (prev && data.entity_matches.some((m) => m.match_id === prev)) {
            return prev;
          }
          return data.entity_matches[0].match_id;
        });
      }
      if (data.graph.nodes.length > 0) {
        setSelectedNodeId(data.graph.nodes[0].node_id);
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to load Contextual Intelligence analysis.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedInvestigation) {
      loadInvestigationContext(selectedInvestigation.id);
    }
  }, [selectedInvestigation, loadInvestigationContext]);

  const handleRunContextualAnalysis = async () => {
    if (!selectedInvestigation) return;
    setReanalyzing(true);
    setError(null);
    try {
      const updated = await veritasApi.analyzeInvestigationContext(
        selectedInvestigation.id,
        {
          actor: reviewerInput || "Dr. Elena Rostova (Principal Forensic Analyst)",
          force_reanalyze: true,
        }
      );
      setContextBundle(updated);
      if (updated.findings.length > 0) {
        setSelectedFindingId(updated.findings[0].finding_id);
      }
      onGlobalRefresh();
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to execute Cross-Document Contextual Analysis.";
      setError(msg);
    } finally {
      setReanalyzing(false);
    }
  };

  const filteredFindings = useMemo(() => {
    if (!contextBundle) return [];
    return contextBundle.findings.filter((f) => {
      if (statusFilter !== "ALL" && f.status !== statusFilter) return false;
      if (reviewFilter !== "ALL" && f.review_status !== reviewFilter)
        return false;
      return true;
    });
  }, [contextBundle, statusFilter, reviewFilter]);

  const selectedFinding: ContextualFinding | null = useMemo(() => {
    if (!contextBundle || filteredFindings.length === 0) return null;
    return (
      filteredFindings.find((f) => f.finding_id === selectedFindingId) ??
      filteredFindings[0]
    );
  }, [contextBundle, filteredFindings, selectedFindingId]);

  useEffect(() => {
    if (selectedFinding) {
      setSelectedEvidencePreview(
        selectedFinding.evidence_values.length > 0
          ? selectedFinding.evidence_values[0]
          : null
      );
      setReviewStatusInput(
        selectedFinding.review_status === "REQUIRES_REVIEW"
          ? "CONFIRMED"
          : selectedFinding.review_status
      );
      setReviewNotesInput(selectedFinding.review_notes ?? "");
      setReviewSuccessMsg(null);
    } else {
      setSelectedEvidencePreview(null);
    }
  }, [selectedFinding]);

  const handleReviewSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFinding || !selectedInvestigation) return;
    setSubmittingReview(true);
    setReviewSuccessMsg(null);
    setError(null);
    try {
      const updatedFinding = await veritasApi.reviewContextualFinding(
        selectedFinding.finding_id,
        {
          review_status: reviewStatusInput,
          reviewer:
            reviewerInput.trim() ||
            "Dr. Elena Rostova (Principal Forensic Analyst)",
          notes: reviewNotesInput.trim(),
        }
      );
      setContextBundle((prev) => {
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
      setReviewSuccessMsg(
        `Recorded human review disposition (${updatedFinding.review_status}) in SQLite and immutable audit ledger.`
      );
      onGlobalRefresh();
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to record contextual finding review.";
      setError(msg);
    } finally {
      setSubmittingReview(false);
    }
  };

  // Compute deterministic circular/layered SVG layout for the Investigation Entity Graph
  const graphLayout = useMemo(() => {
    if (!contextBundle) return { nodes: [], edges: [] };
    const nodes = contextBundle.graph.nodes;
    const edges = contextBundle.graph.edges.filter((e) =>
      graphFilterEdgeType === "ALL" ? true : e.edge_type === graphFilterEdgeType
    );

    const width = 920;
    const height = 520;
    const docNodes = nodes.filter((n) => n.node_type === "DOCUMENT");
    const entityNodes = nodes.filter((n) => n.node_type !== "DOCUMENT");

    const positionedNodes: Record<
      string,
      GraphNode & { x: number; y: number }
    > = {};

    // Place DOCUMENT nodes on the left column, and resolved Entity/Invoice/IBAN/Amount nodes on the right/center arc
    docNodes.forEach((dn, idx) => {
      const spacing = height / (docNodes.length + 1);
      positionedNodes[dn.node_id] = {
        ...dn,
        x: 185,
        y: Math.round(spacing * (idx + 1)),
      };
    });

    entityNodes.forEach((en, idx) => {
      // Two columns on the right side for clarity
      const col = idx % 2;
      const row = Math.floor(idx / 2);
      const totalRows = Math.ceil(entityNodes.length / 2);
      const spacingY = height / (totalRows + 1);
      positionedNodes[en.node_id] = {
        ...en,
        x: col === 0 ? 520 : 770,
        y: Math.round(spacingY * (row + 1)),
      };
    });

    return {
      nodes: Object.values(positionedNodes),
      nodeMap: positionedNodes,
      edges,
    };
  }, [contextBundle, graphFilterEdgeType]);

  const filteredClusters = useMemo(() => {
    if (!contextBundle) return [];
    return contextBundle.entity_matches.filter((m) =>
      entityTypeFilter === "ALL" ? true : m.entity_type === entityTypeFilter
    );
  }, [contextBundle, entityTypeFilter]);

  const selectedCluster: EntityMatchCluster | null = useMemo(() => {
    if (filteredClusters.length === 0) return null;
    return (
      filteredClusters.find((c) => c.match_id === selectedClusterId) ??
      filteredClusters[0]
    );
  }, [filteredClusters, selectedClusterId]);

  const selectedGraphNode = useMemo(() => {
    if (!contextBundle || !selectedNodeId) return null;
    return (
      contextBundle.graph.nodes.find((n) => n.node_id === selectedNodeId) ??
      null
    );
  }, [contextBundle, selectedNodeId]);

  const selectedGraphEdge = useMemo(() => {
    if (!contextBundle || !selectedEdgeId) return null;
    return (
      contextBundle.graph.edges.find(
        (e) => e.relationship_id === selectedEdgeId
      ) ?? null
    );
  }, [contextBundle, selectedEdgeId]);

  return (
    <div className="space-y-6">
      {/* Top Workspace Header & Investigation Selector */}
      <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6 shadow-xl backdrop-blur-md">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/40 bg-cyan-500/10 px-3 py-1 font-mono text-xs font-semibold text-cyan-300">
                <BrainCircuit className="h-3.5 w-3.5" />
                PHASE 4 — CONTEXTUAL INTELLIGENCE ENGINE
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-[11px] text-emerald-300">
                <Calculator className="h-3 w-3" />
                DECIMAL ARITHMETIC VERIFIED
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-0.5 font-mono text-[11px] text-blue-300">
                <Scale className="h-3 w-3" />
                NON-ACCUSATORY EVIDENCE CORRELATION
              </span>
            </div>
            <h1 className="mt-2.5 text-2xl font-bold tracking-tight text-white">
              Contextual Intelligence & Cross-Document Contradiction Analysis
            </h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-400">
              Correlates entities, monetary amounts, IBANs, line-item tables,
              bank statements, and timestamps across all documents in the active
              investigation with page and bounding-box evidence coordinates.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-[260px]">
              <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-slate-400">
                Active Investigation Case
              </label>
              <select
                value={selectedInvestigation?.id ?? ""}
                onChange={(e) => {
                  const found = investigations.find(
                    (inv) => inv.id === e.target.value
                  );
                  if (found) onSelectInvestigation(found);
                }}
                className="w-full rounded-xl border border-slate-700/80 bg-slate-900/90 px-3.5 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
              >
                {investigations.map((inv) => (
                  <option key={inv.id} value={inv.id}>
                    {inv.case_code} — {inv.title}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={handleRunContextualAnalysis}
              disabled={reanalyzing || !selectedInvestigation}
              className="mt-4 inline-flex items-center gap-2 rounded-xl border border-cyan-500/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-cyan-500/20 transition hover:brightness-110 disabled:opacity-50 lg:mt-5"
            >
              <RefreshCw
                className={`h-4 w-4 ${reanalyzing ? "animate-spin" : ""}`}
              />
              {reanalyzing
                ? "Correlating Documents..."
                : "Re-Run Cross-Document Analysis"}
            </button>
          </div>
        </div>

        {/* SECTION A: INVESTIGATION SUMMARY METRICS */}
        {contextBundle && (
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Documents Analyzed</span>
                <Layers className="h-4 w-4 text-cyan-400" />
              </div>
              <div className="mt-1.5 font-mono text-2xl font-bold text-white">
                {contextBundle.documents_analyzed_count}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                {contextBundle.financial_checks_count} Decimal checks run
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Entities Resolved</span>
                <Users className="h-4 w-4 text-blue-400" />
              </div>
              <div className="mt-1.5 font-mono text-2xl font-bold text-white">
                {contextBundle.entities_resolved_count}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-blue-300">
                Exact + OCR-Normalized
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Graph Relationships</span>
                <Network className="h-4 w-4 text-indigo-400" />
              </div>
              <div className="mt-1.5 font-mono text-2xl font-bold text-white">
                {contextBundle.relationships_discovered_count}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-indigo-300">
                {contextBundle.graph.node_count} nodes mapped
              </div>
            </div>

            <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3.5">
              <div className="flex items-center justify-between text-xs text-emerald-300">
                <span>Consistent Matches</span>
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              </div>
              <div className="mt-1.5 font-mono text-2xl font-bold text-emerald-300">
                {contextBundle.consistent_matches_count}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-emerald-400/80">
                Corroborated across docs
              </div>
            </div>

            <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-3.5">
              <div className="flex items-center justify-between text-xs text-rose-300">
                <span>Confirmed / Potential Conflicts</span>
                <AlertTriangle className="h-4 w-4 text-rose-400" />
              </div>
              <div className="mt-1.5 font-mono text-2xl font-bold text-rose-300">
                {contextBundle.confirmed_mismatches_count}{" "}
                <span className="text-sm font-normal text-amber-300">
                  (+
                  {Math.max(
                    0,
                    contextBundle.potential_contradictions_count -
                      contextBundle.confirmed_mismatches_count
                  )}{" "}
                  potential)
                </span>
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-rose-400/80">
                {contextBundle.pending_review_count} awaiting review
              </div>
            </div>

            <div className="rounded-xl border border-purple-500/30 bg-purple-950/20 p-3.5">
              <div className="flex items-center justify-between text-xs text-purple-300">
                <span>Missing Evidence</span>
                <FileWarning className="h-4 w-4 text-purple-400" />
              </div>
              <div className="mt-1.5 font-mono text-2xl font-bold text-purple-300">
                {contextBundle.missing_information_count}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-purple-400/80">
                Referenced unuploaded docs
              </div>
            </div>
          </div>
        )}

        {/* Workspace Sub-Navigation Tabs */}
        <div className="mt-6 flex flex-wrap gap-2 border-t border-slate-800/80 pt-4">
          {[
            {
              id: "CONTRADICTION_EXPLORER" as WorkspaceTab,
              label: "C. Contradiction Explorer & Human Review",
              icon: GitCompareArrows,
              badge: contextBundle?.findings.length ?? 0,
            },
            {
              id: "EVIDENCE_GRAPH" as WorkspaceTab,
              label: "B. Interactive Evidence Relationship Graph",
              icon: Network,
              badge: contextBundle?.graph.edge_count ?? 0,
            },
            {
              id: "FINANCIAL_VALIDATION" as WorkspaceTab,
              label: "D. Deterministic Financial Validation (Decimal)",
              icon: Calculator,
              badge: contextBundle?.financial_validations.length ?? 0,
            },
            {
              id: "ENTITY_RESOLUTION" as WorkspaceTab,
              label: "Entity Resolution & OCR Normalization",
              icon: Users,
              badge: contextBundle?.entity_matches.length ?? 0,
            },
            {
              id: "TIMELINE" as WorkspaceTab,
              label: "E. Investigation Chronology Timeline",
              icon: CalendarClock,
              badge: contextBundle?.timeline_events.length ?? 0,
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
                    ? "border-cyan-500/50 bg-cyan-500/15 text-white shadow-sm"
                    : "border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700 hover:text-slate-200"
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
                      ? "bg-cyan-500/25 text-cyan-200"
                      : "bg-slate-800 text-slate-400"
                  }`}
                >
                  {tab.badge}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-sm text-rose-200">
          <div className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="h-4 w-4 text-rose-400" />
            <span>Contextual Analysis Alert</span>
          </div>
          <p className="mt-1 text-xs text-rose-300">{error}</p>
        </div>
      )}

      {loading && !contextBundle && (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-slate-800 bg-[#0A1020]/80">
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <RefreshCw className="h-5 w-5 animate-spin text-cyan-400" />
            <span>
              Loading cross-document entity resolution, Decimal validations, and
              contradiction findings...
            </span>
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 1: CONTRADICTION EXPLORER & HUMAN REVIEW (SECTIONS C & F)
      ===================================================================== */}
      {contextBundle && activeTab === "CONTRADICTION_EXPLORER" && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          {/* Left Column: Filterable Findings List */}
          <div className="space-y-4 xl:col-span-5">
            <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-sm font-semibold text-white">
                  <Filter className="h-4 w-4 text-cyan-400" />
                  <span>Cross-Document Findings ({filteredFindings.length})</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-200"
                  >
                    <option value="ALL">All Evaluation Statuses</option>
                    <option value="CONFIRMED_DATA_MISMATCH">
                      Confirmed Data Mismatch
                    </option>
                    <option value="POTENTIAL_INCONSISTENCY">
                      Potential Inconsistency
                    </option>
                    <option value="MISSING_INFORMATION">
                      Missing Information
                    </option>
                    <option value="CONSISTENT_EVIDENCE">
                      Consistent Evidence
                    </option>
                    <option value="INCONCLUSIVE_RESULT">
                      Inconclusive Result
                    </option>
                  </select>

                  <select
                    value={reviewFilter}
                    onChange={(e) => setReviewFilter(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-200"
                  >
                    <option value="ALL">All Review Dispositions</option>
                    <option value="REQUIRES_REVIEW">Requires Review</option>
                    <option value="CONFIRMED">Confirmed</option>
                    <option value="REVIEWED">Reviewed</option>
                    <option value="INCONCLUSIVE">Inconclusive</option>
                    <option value="DISMISSED">Dismissed</option>
                  </select>
                </div>
              </div>

              <div className="mt-4 max-h-[780px] space-y-3 overflow-y-auto pr-1">
                {filteredFindings.map((f) => {
                  const isSelected =
                    selectedFinding?.finding_id === f.finding_id;
                  return (
                    <button
                      key={f.finding_id}
                      type="button"
                      onClick={() => setSelectedFindingId(f.finding_id)}
                      className={`w-full rounded-xl border p-4 text-left transition ${
                        isSelected
                          ? "border-cyan-500/60 bg-slate-900/95 shadow-lg shadow-cyan-500/10"
                          : "border-slate-800/80 bg-slate-900/50 hover:border-slate-700 hover:bg-slate-900/80"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span
                          className={`rounded-md border px-2 py-0.5 font-mono text-[10px] font-semibold ${statusBadgeStyle(
                            f.status
                          )}`}
                        >
                          {statusDisplayLabel(f.status)}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold ${severityBadgeStyle(
                              f.severity
                            )}`}
                          >
                            {f.severity}
                          </span>
                          <span
                            className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${reviewBadgeStyle(
                              f.review_status
                            )}`}
                          >
                            {f.review_status}
                          </span>
                        </div>
                      </div>

                      <h3 className="mt-2 text-sm font-semibold text-white">
                        {f.title}
                      </h3>
                      <p className="mt-1 line-clamp-2 text-xs text-slate-400">
                        {f.description}
                      </p>

                      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/80 pt-2.5 font-mono text-[11px] text-slate-400">
                        <span>
                          {f.document_references.length} doc(s) •{" "}
                          {f.evidence_values.length} evidence point(s)
                        </span>
                        <span className="text-cyan-300">
                          Confidence: {(f.confidence_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Right Column: Side-by-Side Contradiction Comparison, Page Coordinate Preview & Human Review */}
          <div className="space-y-6 xl:col-span-7">
            {selectedFinding ? (
              <>
                {/* Finding Header & Side-by-Side Conflicting Evidence Cards */}
                <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-md border px-2.5 py-1 font-mono text-xs font-semibold ${statusBadgeStyle(
                          selectedFinding.status
                        )}`}
                      >
                        {statusDisplayLabel(selectedFinding.status)}
                      </span>
                      <span
                        className={`rounded-md border px-2.5 py-1 font-mono text-xs font-semibold ${severityBadgeStyle(
                          selectedFinding.severity
                        )}`}
                      >
                        SEVERITY: {selectedFinding.severity}
                      </span>
                      <span className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 font-mono text-xs text-slate-300">
                        {selectedFinding.finding_type}
                      </span>
                    </div>
                    <span className="font-mono text-xs text-cyan-300">
                      Confidence:{" "}
                      {(selectedFinding.confidence_score * 100).toFixed(1)}%
                    </span>
                  </div>

                  <h2 className="mt-3 text-lg font-bold text-white">
                    {selectedFinding.title}
                  </h2>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-300">
                    {selectedFinding.description}
                  </p>

                  {/* Methodology & Rationale Box */}
                  <div className="mt-4 grid grid-cols-1 gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4 md:grid-cols-2">
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-wider text-cyan-400">
                        Comparison Methodology
                      </div>
                      <div className="mt-1 text-xs font-medium text-slate-200">
                        {selectedFinding.comparison_method}
                      </div>
                    </div>
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-wider text-cyan-400">
                        Matching & Correlation Rationale
                      </div>
                      <div className="mt-1 text-xs text-slate-300">
                        {selectedFinding.matching_rationale}
                      </div>
                    </div>
                  </div>

                  {/* Side-by-Side Conflicting / Corroborating Evidence Cards */}
                  <div className="mt-5">
                    <div className="mb-2.5 flex items-center justify-between">
                      <h3 className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-300">
                        Side-by-Side Document Evidence Values (
                        {selectedFinding.evidence_values.length})
                      </h3>
                      <span className="text-[11px] text-slate-400">
                        Click any evidence card to inspect its page & bounding
                        box below
                      </span>
                    </div>

                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      {selectedFinding.evidence_values.map((ev, idx) => {
                        const isPreviewed =
                          selectedEvidencePreview?.document_id ===
                            ev.document_id &&
                          selectedEvidencePreview?.raw_value === ev.raw_value &&
                          selectedEvidencePreview?.field_label ===
                            ev.field_label;
                        return (
                          <div
                            key={`${ev.document_id}-${idx}`}
                            onClick={() => setSelectedEvidencePreview(ev)}
                            className={`cursor-pointer rounded-xl border p-4 transition ${
                              isPreviewed
                                ? "border-cyan-500/70 bg-cyan-950/20 shadow-md"
                                : "border-slate-800 bg-slate-900/70 hover:border-slate-700"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="truncate font-mono text-xs font-semibold text-cyan-300">
                                {ev.filename}
                              </span>
                              <span className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                                Page {ev.page_number}
                              </span>
                            </div>

                            <div className="mt-1 font-mono text-[11px] text-slate-400">
                              {ev.field_label || ev.document_type} •{" "}
                              {ev.extraction_method} (
                              {(ev.confidence * 100).toFixed(0)}%)
                            </div>

                            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/90 p-2.5">
                              <div className="font-mono text-[10px] uppercase text-slate-500">
                                Raw Extracted Value
                              </div>
                              <div className="mt-0.5 font-mono text-sm font-bold text-white">
                                {ev.raw_value}
                              </div>
                              <div className="mt-1.5 font-mono text-[10px] uppercase text-slate-500">
                                Normalized Comparison Value
                              </div>
                              <div className="mt-0.5 font-mono text-xs text-cyan-300">
                                {ev.normalized_value}
                              </div>
                            </div>

                            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                              <span className="font-mono text-[10px] text-slate-500">
                                SHA-256: {ev.document_sha256.slice(0, 12)}...
                              </span>
                              <div className="flex items-center gap-1.5">
                                {onOpenDocumentIntelligence && (
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onOpenDocumentIntelligence(
                                        ev.document_id
                                      );
                                    }}
                                    className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[10px] font-medium text-slate-200 hover:border-cyan-500/50 hover:text-cyan-300"
                                  >
                                    <FileSearch className="h-3 w-3" />
                                    Doc Intel
                                  </button>
                                )}
                                {onOpenVisualForensics && (
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onOpenVisualForensics(ev.document_id);
                                    }}
                                    className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[10px] font-medium text-slate-200 hover:border-cyan-500/50 hover:text-cyan-300"
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

                  {/* Interactive Source Document Page Preview with Bounding-Box Overlay */}
                  {selectedEvidencePreview && (
                    <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/90 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div>
                          <div className="flex items-center gap-2 text-xs font-semibold text-white">
                            <Eye className="h-4 w-4 text-cyan-400" />
                            <span>
                              Source Evidence Page Preview:{" "}
                              {selectedEvidencePreview.filename} (Page{" "}
                              {selectedEvidencePreview.page_number})
                            </span>
                          </div>
                          <p className="mt-0.5 font-mono text-[11px] text-slate-400">
                            Field: {selectedEvidencePreview.field_label} | Raw:{" "}
                            &ldquo;{selectedEvidencePreview.raw_value}&rdquo;
                            {selectedEvidencePreview.bounding_box
                              ? ` | BBox: [${selectedEvidencePreview.bounding_box.x0.toFixed(
                                  1
                                )}, ${selectedEvidencePreview.bounding_box.y0.toFixed(
                                  1
                                )}, ${selectedEvidencePreview.bounding_box.x1.toFixed(
                                  1
                                )}, ${selectedEvidencePreview.bounding_box.y1.toFixed(
                                  1
                                )}]`
                              : ""}
                          </p>
                        </div>
                      </div>

                      <div className="mt-3 flex justify-center overflow-hidden rounded-lg border border-slate-800 bg-slate-900 p-3">
                        <div className="relative inline-block max-w-full">
                          <img
                            src={veritasApi.getDocumentPagePreviewUrl(
                              selectedEvidencePreview.document_id,
                              selectedEvidencePreview.page_number
                            )}
                            alt={`Evidence preview for ${selectedEvidencePreview.filename}`}
                            className="max-h-[420px] w-auto rounded object-contain"
                          />
                          {selectedEvidencePreview.bounding_box &&
                            selectedEvidencePreview.bounding_box.page_width >
                              0 &&
                            selectedEvidencePreview.bounding_box.page_height >
                              0 && (
                              <div
                                className="pointer-events-none absolute border-2 border-rose-500 bg-rose-500/20 shadow-[0_0_12px_rgba(244,63,94,0.7)]"
                                style={{
                                  left: `${
                                    (selectedEvidencePreview.bounding_box.x0 /
                                      selectedEvidencePreview.bounding_box
                                        .page_width) *
                                    100
                                  }%`,
                                  top: `${
                                    (selectedEvidencePreview.bounding_box.y0 /
                                      selectedEvidencePreview.bounding_box
                                        .page_height) *
                                    100
                                  }%`,
                                  width: `${Math.max(
                                    2,
                                    ((selectedEvidencePreview.bounding_box.x1 -
                                      selectedEvidencePreview.bounding_box.x0) /
                                      selectedEvidencePreview.bounding_box
                                        .page_width) *
                                      100
                                  )}%`,
                                  height: `${Math.max(
                                    2,
                                    ((selectedEvidencePreview.bounding_box.y1 -
                                      selectedEvidencePreview.bounding_box.y0) /
                                      selectedEvidencePreview.bounding_box
                                        .page_height) *
                                      100
                                  )}%`,
                                }}
                              />
                            )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Possible Explanations & Recommended Action */}
                  <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                      <div className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-amber-300">
                        <HelpCircle className="h-4 w-4" />
                        <span>Possible Explanations (Forensic & Benign)</span>
                      </div>
                      <ul className="mt-2 space-y-1.5 text-xs text-slate-300">
                        {selectedFinding.possible_explanations.map(
                          (exp, idx) => (
                            <li key={idx} className="flex items-start gap-2">
                              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                              <span>{exp}</span>
                            </li>
                          )
                        )}
                      </ul>
                    </div>

                    <div className="rounded-xl border border-cyan-500/30 bg-cyan-950/15 p-4">
                      <div className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-cyan-300">
                        <ClipboardCheck className="h-4 w-4" />
                        <span>Recommended Human Verification</span>
                      </div>
                      <p className="mt-2 text-xs leading-relaxed text-slate-200">
                        {selectedFinding.recommended_human_action}
                      </p>
                      <p className="mt-2 font-mono text-[11px] text-slate-400">
                        Confidence Note:{" "}
                        {selectedFinding.confidence_interpretation}
                      </p>
                    </div>
                  </div>
                </div>

                {/* SECTION F: HUMAN REVIEW PANEL */}
                <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-5 w-5 text-cyan-400" />
                      <h3 className="text-base font-bold text-white">
                        Human Investigator Review & Disposition
                      </h3>
                    </div>
                    <span
                      className={`rounded-md border px-2.5 py-1 font-mono text-xs font-semibold ${reviewBadgeStyle(
                        selectedFinding.review_status
                      )}`}
                    >
                      Current: {selectedFinding.review_status}
                    </span>
                  </div>

                  <form onSubmit={handleReviewSubmit} className="mt-4 space-y-4">
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      <div>
                        <label className="mb-1 block font-mono text-[11px] uppercase text-slate-400">
                          Review Disposition
                        </label>
                        <select
                          value={reviewStatusInput}
                          onChange={(e) => setReviewStatusInput(e.target.value)}
                          className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                        >
                          <option value="CONFIRMED">
                            CONFIRMED — Verified Contradiction / Evidence
                          </option>
                          <option value="REVIEWED">
                            REVIEWED — Inspected & Logged
                          </option>
                          <option value="INCONCLUSIVE">
                            INCONCLUSIVE — Requires External Corroboration
                          </option>
                          <option value="DISMISSED">
                            DISMISSED — Benign / Explained Variance
                          </option>
                        </select>
                      </div>

                      <div>
                        <label className="mb-1 block font-mono text-[11px] uppercase text-slate-400">
                          Reviewing Investigator
                        </label>
                        <input
                          type="text"
                          value={reviewerInput}
                          onChange={(e) => setReviewerInput(e.target.value)}
                          className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="mb-1 block font-mono text-[11px] uppercase text-slate-400">
                        Investigator Review Notes & Evidentiary Rationale
                      </label>
                      <textarea
                        rows={2}
                        value={reviewNotesInput}
                        onChange={(e) => setReviewNotesInput(e.target.value)}
                        placeholder="Document your human verification rationale for the audit ledger..."
                        className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                      />
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <button
                        type="submit"
                        disabled={submittingReview}
                        className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-xs font-semibold text-white shadow transition hover:brightness-110 disabled:opacity-50"
                      >
                        <ClipboardCheck className="h-4 w-4" />
                        {submittingReview
                          ? "Recording Decision..."
                          : "Record Human Review Decision"}
                      </button>

                      {reviewSuccessMsg && (
                        <span className="text-xs text-emerald-300">
                          {reviewSuccessMsg}
                        </span>
                      )}
                    </div>
                  </form>

                  {selectedFinding.review_history.length > 0 && (
                    <div className="mt-5 border-t border-slate-800 pt-4">
                      <div className="flex items-center gap-1.5 font-mono text-xs font-semibold uppercase text-slate-400">
                        <History className="h-3.5 w-3.5 text-cyan-400" />
                        <span>
                          Finding Review History (
                          {selectedFinding.review_history.length})
                        </span>
                      </div>
                      <div className="mt-2 space-y-2">
                        {selectedFinding.review_history.map((rev) => (
                          <div
                            key={rev.review_id}
                            className="rounded-lg border border-slate-800 bg-slate-900/70 p-2.5 text-xs"
                          >
                            <div className="flex items-center justify-between font-mono text-[11px] text-slate-400">
                              <span>
                                {rev.reviewer}: {rev.previous_status} →{" "}
                                <strong className="text-cyan-300">
                                  {rev.new_status}
                                </strong>
                              </span>
                              <span>
                                {new Date(rev.created_at).toLocaleString()}
                              </span>
                            </div>
                            {rev.notes && (
                              <p className="mt-1 text-slate-300">{rev.notes}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="rounded-2xl border border-slate-800 bg-[#0A1020]/90 p-8 text-center text-sm text-slate-400">
                No contextual findings match the current filter criteria.
              </div>
            )}
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 2: INTERACTIVE EVIDENCE RELATIONSHIP GRAPH (SECTION B)
      ===================================================================== */}
      {contextBundle && activeTab === "EVIDENCE_GRAPH" && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <div className="xl:col-span-8">
            <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-bold text-white">
                    Investigation Entity & Evidence Relationship Graph
                  </h2>
                  <p className="text-xs text-slate-400">
                    Click any node or relationship edge to inspect cross-document
                    links, contradicting values, and source coordinates.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <select
                    value={graphFilterEdgeType}
                    onChange={(e) => setGraphFilterEdgeType(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200"
                  >
                    <option value="ALL">
                      All Edge Types ({contextBundle.graph.edge_count})
                    </option>
                    <option value="CONTRADICTS">
                      CONTRADICTS ({contextBundle.graph.contradiction_edge_count}
                      )
                    </option>
                    <option value="SUPPORTS">
                      SUPPORTS ({contextBundle.graph.supporting_edge_count})
                    </option>
                    <option value="REFERENCES">REFERENCES</option>
                    <option value="ISSUED_BY">ISSUED_BY</option>
                    <option value="PAID_TO">PAID_TO</option>
                    <option value="MENTIONS">MENTIONS</option>
                  </select>
                </div>
              </div>

              {/* Interactive SVG Graph Canvas */}
              <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800 bg-[#060A14] p-2">
                <svg
                  viewBox="0 0 920 520"
                  className="h-[480px] w-full min-w-[760px]"
                >
                  <defs>
                    <marker
                      id="arrow-contradicts"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#f43f5e" />
                    </marker>
                    <marker
                      id="arrow-supports"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#10b981" />
                    </marker>
                    <marker
                      id="arrow-neutral"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="5"
                      markerHeight="5"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8" />
                    </marker>
                  </defs>

                  {/* Edges */}
                  {graphLayout.edges.map((edge) => {
                    const s = graphLayout.nodeMap?.[edge.source_node_id];
                    const t = graphLayout.nodeMap?.[edge.target_node_id];
                    if (!s || !t) return null;
                    const isContradict = edge.edge_type === "CONTRADICTS";
                    const isSupport = edge.edge_type === "SUPPORTS";
                    const strokeColor = isContradict
                      ? "#f43f5e"
                      : isSupport
                      ? "#10b981"
                      : "#334155";
                    const isSelected =
                      selectedEdgeId === edge.relationship_id;
                    const midX = (s.x + t.x) / 2;
                    const midY = (s.y + t.y) / 2;

                    return (
                      <g
                        key={edge.relationship_id}
                        onClick={() => {
                          setSelectedEdgeId(edge.relationship_id);
                          setSelectedNodeId(null);
                        }}
                        className="cursor-pointer"
                      >
                        <line
                          x1={s.x}
                          y1={s.y}
                          x2={t.x}
                          y2={t.y}
                          stroke={strokeColor}
                          strokeWidth={
                            isSelected
                              ? 3.2
                              : isContradict || isSupport
                              ? 2.2
                              : 1.3
                          }
                          strokeDasharray={isContradict ? "6 3" : undefined}
                          markerEnd={
                            isContradict
                              ? "url(#arrow-contradicts)"
                              : isSupport
                              ? "url(#arrow-supports)"
                              : "url(#arrow-neutral)"
                          }
                          opacity={isSelected ? 1 : 0.85}
                        />
                        {(isContradict || isSupport || isSelected) && (
                          <g transform={`translate(${midX}, ${midY})`}>
                            <rect
                              x="-42"
                              y="-9"
                              width="84"
                              height="18"
                              rx="4"
                              fill="#0A1020"
                              stroke={strokeColor}
                              strokeWidth="1"
                            />
                            <text
                              textAnchor="middle"
                              dy="3.5"
                              fill={
                                isContradict
                                  ? "#fda4af"
                                  : isSupport
                                  ? "#6ee7b7"
                                  : "#bae6fd"
                              }
                              fontSize="8.5"
                              fontFamily="monospace"
                            >
                              {edge.edge_type}
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}

                  {/* Nodes */}
                  {graphLayout.nodes.map((node) => {
                    const isConflict = node.status === "CONTRADICTION";
                    const isConsistent = node.status === "CONSISTENT";
                    const isSelected = selectedNodeId === node.node_id;
                    const borderColor = isConflict
                      ? "#f43f5e"
                      : isConsistent
                      ? "#10b981"
                      : "#06b6d4";
                    const fillBg = isConflict
                      ? "#3b0a19"
                      : isConsistent
                      ? "#062c22"
                      : "#0f172a";

                    return (
                      <g
                        key={node.node_id}
                        transform={`translate(${node.x}, ${node.y})`}
                        onClick={() => {
                          setSelectedNodeId(node.node_id);
                          setSelectedEdgeId(null);
                        }}
                        className="cursor-pointer"
                      >
                        <rect
                          x="-115"
                          y="-24"
                          width="230"
                          height="48"
                          rx="10"
                          fill={fillBg}
                          stroke={isSelected ? "#ffffff" : borderColor}
                          strokeWidth={isSelected ? "2.5" : "1.6"}
                        />
                        <text
                          x="0"
                          y="-5"
                          textAnchor="middle"
                          fill="#94a3b8"
                          fontSize="8.5"
                          fontFamily="monospace"
                        >
                          [{node.node_type}]
                        </text>
                        <text
                          x="0"
                          y="11"
                          textAnchor="middle"
                          fill="#f8fafc"
                          fontSize="10.5"
                          fontWeight="bold"
                        >
                          {node.label.length > 28
                            ? `${node.label.slice(0, 26)}...`
                            : node.label}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
            </div>
          </div>

          {/* Right Column: Graph Node / Edge Inspector */}
          <div className="space-y-4 xl:col-span-4">
            <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5">
              <h3 className="text-sm font-bold text-white">
                Graph Evidence Inspector
              </h3>

              {selectedGraphNode && (
                <div className="mt-3 space-y-3">
                  <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                    <div className="flex items-center justify-between">
                      <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] text-cyan-300">
                        NODE: {selectedGraphNode.node_type}
                      </span>
                      <span className="font-mono text-[10px] text-slate-400">
                        Status: {selectedGraphNode.status}
                      </span>
                    </div>
                    <div className="mt-2 font-mono text-sm font-bold text-white">
                      {selectedGraphNode.label}
                    </div>
                    {selectedGraphNode.subtitle && (
                      <div className="mt-0.5 text-xs text-slate-400">
                        {selectedGraphNode.subtitle}
                      </div>
                    )}
                    {selectedGraphNode.document_id && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {onOpenDocumentIntelligence && (
                          <button
                            type="button"
                            onClick={() =>
                              onOpenDocumentIntelligence(
                                selectedGraphNode.document_id!
                              )
                            }
                            className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1.5 text-xs font-medium text-cyan-300 hover:bg-cyan-500/20"
                          >
                            <FileSearch className="h-3.5 w-3.5" />
                            Inspect in Document Intelligence
                          </button>
                        )}
                        {onOpenVisualForensics && (
                          <button
                            type="button"
                            onClick={() =>
                              onOpenVisualForensics(
                                selectedGraphNode.document_id!
                              )
                            }
                            className="inline-flex items-center gap-1.5 rounded-lg border border-blue-500/40 bg-blue-500/10 px-2.5 py-1.5 text-xs font-medium text-blue-300 hover:bg-blue-500/20"
                          >
                            <ScanEye className="h-3.5 w-3.5" />
                            Inspect in Visual Forensics
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="font-mono text-xs font-semibold uppercase text-slate-400">
                    Connected Relationships
                  </div>
                  <div className="max-h-[340px] space-y-2 overflow-y-auto pr-1">
                    {contextBundle.graph.edges
                      .filter(
                        (e) =>
                          e.source_node_id === selectedGraphNode.node_id ||
                          e.target_node_id === selectedGraphNode.node_id
                      )
                      .map((e) => (
                        <div
                          key={e.relationship_id}
                          onClick={() => setSelectedEdgeId(e.relationship_id)}
                          className="cursor-pointer rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-xs hover:border-slate-700"
                        >
                          <div className="flex items-center justify-between font-mono text-[10px]">
                            <span
                              className={
                                e.edge_type === "CONTRADICTS"
                                  ? "font-bold text-rose-400"
                                  : e.edge_type === "SUPPORTS"
                                  ? "font-bold text-emerald-400"
                                  : "text-cyan-300"
                              }
                            >
                              {e.edge_type}
                            </span>
                            <span className="text-slate-400">
                              {(e.confidence_score * 100).toFixed(0)}% conf
                            </span>
                          </div>
                          <div className="mt-1 font-medium text-slate-200">
                            {e.source_label} → {e.target_label}
                          </div>
                          <p className="mt-1 text-[11px] text-slate-400">
                            {e.matching_rationale}
                          </p>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {selectedGraphEdge && (
                <div className="mt-3 space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                  <div className="flex items-center justify-between">
                    <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-xs font-semibold text-cyan-300">
                      EDGE: {selectedGraphEdge.edge_type}
                    </span>
                    <span className="font-mono text-xs text-slate-400">
                      Confidence:{" "}
                      {(selectedGraphEdge.confidence_score * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="text-xs font-semibold text-white">
                    {selectedGraphEdge.source_label} →{" "}
                    {selectedGraphEdge.target_label}
                  </div>
                  <p className="text-xs text-slate-300">
                    {selectedGraphEdge.matching_rationale}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 3: DETERMINISTIC FINANCIAL VALIDATION (SECTION D)
      ===================================================================== */}
      {contextBundle && activeTab === "FINANCIAL_VALIDATION" && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-bold text-white">
                  Deterministic Financial Validation (Exact Python Decimal
                  Engine)
                </h2>
                <p className="text-xs text-slate-400">
                  Every invoice line-item table, tax sum, bank statement
                  opening/debit/closing balance, and cross-document settlement is
                  verified using exact Decimal(ROUND_HALF_UP) arithmetic — never
                  floating-point approximations.
                </p>
              </div>
              <span className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 font-mono text-xs font-semibold text-emerald-300">
                {contextBundle.financial_validations.length} Validation Checks
                Executed
              </span>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
              {contextBundle.financial_validations.map((fv) => {
                const isPass = fv.status === "CONSISTENT_EVIDENCE";
                return (
                  <div
                    key={fv.validation_id}
                    className={`rounded-xl border p-5 ${
                      isPass
                        ? "border-slate-800 bg-slate-900/70"
                        : "border-rose-500/40 bg-rose-950/15"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span
                        className={`rounded-md border px-2.5 py-0.5 font-mono text-[10px] font-semibold ${statusBadgeStyle(
                          fv.status
                        )}`}
                      >
                        {statusDisplayLabel(fv.status)}
                      </span>
                      <span className="font-mono text-xs text-cyan-300">
                        {fv.check_type}
                      </span>
                    </div>

                    <div className="mt-2.5 flex items-center justify-between">
                      <h3 className="text-sm font-bold text-white">
                        {fv.filename}
                      </h3>
                      <span className="font-mono text-xs text-slate-400">
                        Page {fv.page_number}
                      </span>
                    </div>

                    <div className="mt-1 font-mono text-[11px] text-slate-400">
                      Formula: {fv.formula_used}
                    </div>

                    <div className="mt-4 grid grid-cols-3 gap-2 rounded-lg border border-slate-800 bg-slate-950/90 p-3 font-mono text-xs">
                      <div>
                        <div className="text-[10px] uppercase text-slate-500">
                          Expected (Decimal)
                        </div>
                        <div className="mt-0.5 font-bold text-slate-200">
                          {fv.expected_value}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase text-slate-500">
                          Observed (Declared)
                        </div>
                        <div className="mt-0.5 font-bold text-white">
                          {fv.observed_value}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase text-slate-500">
                          Discrepancy (Δ)
                        </div>
                        <div
                          className={`mt-0.5 font-bold ${
                            isPass ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {fv.discrepancy_amount} {fv.currency}
                        </div>
                      </div>
                    </div>

                    {/* Line Items / Bank Transactions Detail Breakdown */}
                    {Array.isArray(fv.details?.line_items) && (
                      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-800/80 bg-slate-950/60 p-2.5">
                        <div className="mb-1.5 font-mono text-[10px] uppercase text-slate-400">
                          Extracted Invoice Line Items (Decimal Summation)
                        </div>
                        <table className="w-full text-left font-mono text-[11px]">
                          <thead>
                            <tr className="border-b border-slate-800 text-slate-400">
                              <th className="pb-1">Code</th>
                              <th className="pb-1">Description</th>
                              <th className="pb-1">Qty</th>
                              <th className="pb-1 text-right">Line Total</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/50 text-slate-200">
                            {(
                              fv.details.line_items as Array<
                                Record<string, string>
                              >
                            ).map((li, idx) => (
                              <tr key={idx}>
                                <td className="py-1 text-cyan-300">
                                  {li.item_code}
                                </td>
                                <td className="py-1">{li.description}</td>
                                <td className="py-1">{li.quantity}</td>
                                <td className="py-1 text-right font-semibold">
                                  {li.currency} {li.line_total_decimal}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {Array.isArray(fv.details?.transactions) && (
                      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-800/80 bg-slate-950/60 p-2.5">
                        <div className="mb-1.5 font-mono text-[10px] uppercase text-slate-400">
                          Bank Statement Ledger Progression (Opening:{" "}
                          {String(fv.details.opening_balance)} → Closing:{" "}
                          {String(fv.details.observed_closing_balance)})
                        </div>
                        <table className="w-full text-left font-mono text-[11px]">
                          <thead>
                            <tr className="border-b border-slate-800 text-slate-400">
                              <th className="pb-1">Posting Date</th>
                              <th className="pb-1">Reference</th>
                              <th className="pb-1 text-right">Debit</th>
                              <th className="pb-1 text-right">
                                Running Balance
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/50 text-slate-200">
                            {(
                              fv.details.transactions as Array<
                                Record<string, string>
                              >
                            ).map((tx, idx) => (
                              <tr key={idx}>
                                <td className="py-1 text-cyan-300">
                                  {tx.posting_date}
                                </td>
                                <td className="py-1">{tx.description}</td>
                                <td className="py-1 text-right text-amber-300">
                                  ${tx.debit_decimal}
                                </td>
                                <td className="py-1 text-right font-semibold text-emerald-300">
                                  ${tx.running_balance_decimal}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 4: ENTITY RESOLUTION & OCR NORMALIZATION
      ===================================================================== */}
      {contextBundle && activeTab === "ENTITY_RESOLUTION" && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <div className="space-y-4 xl:col-span-5">
            <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-white">
                  Resolved Entity Clusters ({filteredClusters.length})
                </h3>
                <select
                  value={entityTypeFilter}
                  onChange={(e) => setEntityTypeFilter(e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-200"
                >
                  <option value="ALL">All Entity Types</option>
                  <option value="INVOICE_NUMBER">INVOICE_NUMBER</option>
                  <option value="COMPANY_NAME">COMPANY_NAME</option>
                  <option value="ACCOUNT_REFERENCE">ACCOUNT_REFERENCE</option>
                  <option value="MONETARY_AMOUNT">MONETARY_AMOUNT</option>
                  <option value="PERSON_NAME">PERSON_NAME</option>
                  <option value="DATE">DATE</option>
                  <option value="TAX_IDENTIFIER">TAX_IDENTIFIER</option>
                </select>
              </div>

              <div className="mt-3 max-h-[620px] space-y-2.5 overflow-y-auto pr-1">
                {filteredClusters.map((c) => {
                  const active = selectedCluster?.match_id === c.match_id;
                  return (
                    <button
                      key={c.match_id}
                      type="button"
                      onClick={() => setSelectedClusterId(c.match_id)}
                      className={`w-full rounded-xl border p-3.5 text-left transition ${
                        active
                          ? "border-cyan-500/60 bg-slate-900"
                          : "border-slate-800 bg-slate-900/50 hover:border-slate-700"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-cyan-300">
                          {c.entity_type}
                        </span>
                        <span
                          className={`rounded border px-2 py-0.5 font-mono text-[10px] ${
                            c.match_status === "EXACT_MATCH"
                              ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                              : c.match_status ===
                                "UNCERTAIN_OCR_NORMALIZED_MATCH"
                              ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                              : "border-slate-700 bg-slate-800 text-slate-400"
                          }`}
                        >
                          {c.match_status}
                        </span>
                      </div>
                      <div className="mt-2 font-mono text-sm font-bold text-white">
                        {c.canonical_value}
                      </div>
                      <div className="mt-1 font-mono text-[11px] text-slate-400">
                        Appears in {c.document_count} document(s) •{" "}
                        {c.member_entities.length} occurrence(s)
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="xl:col-span-7">
            {selectedCluster && (
              <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="rounded-md border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1 font-mono text-xs font-semibold text-cyan-300">
                    {selectedCluster.entity_type}
                  </span>
                  <span className="font-mono text-xs text-slate-300">
                    Resolution Confidence:{" "}
                    {(selectedCluster.confidence_score * 100).toFixed(1)}%
                  </span>
                </div>

                <h3 className="mt-3 font-mono text-lg font-bold text-white">
                  Canonical Value: {selectedCluster.canonical_value}
                </h3>
                <p className="mt-1 text-xs text-slate-300">
                  {selectedCluster.matching_rationale}
                </p>

                <div className="mt-5 space-y-3">
                  <div className="font-mono text-xs font-semibold uppercase text-slate-400">
                    Preserved Raw vs. Normalized Mentions Across Documents (
                    {selectedCluster.member_entities.length})
                  </div>
                  {selectedCluster.member_entities.map((m, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-slate-800 bg-slate-900/70 p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-xs font-semibold text-cyan-300">
                          {m.filename} (Page {m.page_number})
                        </span>
                        <span className="font-mono text-[11px] text-slate-400">
                          {m.extraction_method} •{" "}
                          {(m.confidence * 100).toFixed(0)}% confidence
                        </span>
                      </div>
                      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5 font-mono text-xs">
                          <span className="block text-[10px] text-slate-500">
                            Original Raw Value
                          </span>
                          <span className="font-semibold text-white">
                            {m.raw_value}
                          </span>
                        </div>
                        <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5 font-mono text-xs">
                          <span className="block text-[10px] text-slate-500">
                            Normalized Value
                          </span>
                          <span className="text-cyan-300">
                            {m.normalized_value}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 5: INVESTIGATION TIMELINE (SECTION E)
      ===================================================================== */}
      {contextBundle && activeTab === "TIMELINE" && (
        <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-bold text-white">
                Investigation Chronology & Metadata Timestamp Timeline
              </h2>
              <p className="text-xs text-slate-400">
                Orders all extracted document dates, bank posting dates, escrow
                release dates, and PDF container modification timestamps to
                surface post-settlement alteration anomalies.
              </p>
            </div>
            <span className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 font-mono text-xs text-cyan-300">
              {contextBundle.timeline_events.length} Chronological Events
            </span>
          </div>

          <div className="mt-6 space-y-4">
            {contextBundle.timeline_events.map((ev) => {
              const isWarning = ev.status === "CHRONOLOGY_WARNING";
              return (
                <div
                  key={ev.event_id}
                  className={`flex flex-col justify-between gap-4 rounded-xl border p-4 sm:flex-row sm:items-center ${
                    isWarning
                      ? "border-amber-500/50 bg-amber-950/20"
                      : "border-slate-800 bg-slate-900/60"
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div
                      className={`mt-0.5 rounded-xl border px-3 py-2 text-center font-mono text-xs font-bold ${
                        isWarning
                          ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                          : "border-cyan-500/30 bg-cyan-500/10 text-cyan-300"
                      }`}
                    >
                      {ev.date_iso}
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
                          {ev.event_type}
                        </span>
                        {isWarning && (
                          <span className="rounded border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-300">
                            POST-SETTLEMENT MODIFICATION ANOMALY
                          </span>
                        )}
                      </div>
                      <h3 className="mt-1 text-sm font-bold text-white">
                        {ev.title}
                      </h3>
                      <p className="mt-0.5 text-xs text-slate-300">
                        {ev.description}
                      </p>
                      <div className="mt-1.5 font-mono text-[11px] text-slate-400">
                        Source: {ev.filename} (Page {ev.page_number}) • Raw
                        Date: &ldquo;{ev.raw_date_value}&rdquo;
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
