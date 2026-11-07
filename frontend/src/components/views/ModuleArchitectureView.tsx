"use client";

import React from "react";
import {
  BrainCircuit,
  Database,
  FileSearch,
  FileSpreadsheet,
  FolderPlus,
  GitCompareArrows,
  Layers,
  ScanEye,
  ShieldCheck,
} from "lucide-react";
import {
  CommandCentreSummary,
  Investigation,
  NavigationSectionId,
} from "@/types/veritas";

interface ModuleArchitectureViewProps {
  section: NavigationSectionId;
  summary: CommandCentreSummary | null;
  selectedInvestigation: Investigation | null;
  onSelectInvestigation: (inv: Investigation) => void;
  onOpenNewInvestigation: () => void;
}

interface ModuleSpec {
  title: string;
  subtitle: string;
  phase: string;
  engineStack: string[];
  sqliteTable: string;
  capabilities: string[];
  emptyMessage: string;
  icon: React.ComponentType<{ className?: string }>;
}

const MODULE_SPECS: Record<string, ModuleSpec> = {
  "document-intelligence": {
    title: "Document Intelligence & Optical Extraction",
    subtitle:
      "Multi-format evidentiary ingestion, SHA-256 cryptographic hashing, and layout-aware OCR.",
    phase: "Phase 2 Pipeline",
    engineStack: ["PyMuPDF (fitz)", "PaddleOCR", "SHA-256 Digest", "SQLite WAL"],
    sqliteTable: "documents",
    capabilities: [
      "Cryptographic SHA-256 file fingerprinting upon upload",
      "Multi-page PDF & raster document layout decomposition",
      "Structured key-value, table, and entity token extraction via PaddleOCR",
      "Relational linkage to parent investigation case record in SQLite",
    ],
    emptyMessage:
      "0 documents currently ingested in SQLite table `documents`. Document ingestion and PaddleOCR extraction will be activated in Phase 2.",
    icon: FileSearch,
  },
  "visual-forensics": {
    title: "Visual Forensics & Tampering Inspection",
    subtitle:
      "Pixel-level anomaly detection, Error Level Analysis (ELA), and clone region inspection.",
    phase: "Phase 3 Pipeline",
    engineStack: ["OpenCV", "PyMuPDF", "ELA Matrix", "EXIF/XMP Inspector"],
    sqliteTable: "findings (finding_type = 'VISUAL_ANOMALY')",
    capabilities: [
      "Compression artifact & Error Level Analysis (ELA) variance mapping",
      "Copy-move / clone region & spliced signature boundary detection",
      "Font metrics and kerning misalignment detection across PDF streams",
      "PDF incremental-save & metadata modification history verification",
    ],
    emptyMessage:
      "0 visual anomaly findings recorded in SQLite table `findings`. OpenCV & PyMuPDF visual forensics will be activated in Phase 3.",
    icon: ScanEye,
  },
  "contextual-intelligence": {
    title: "Contextual Intelligence & Semantic Reasoning",
    subtitle:
      "Deep semantic verification of dates, financial figures, clauses, and internal document logic.",
    phase: "Phase 4 Pipeline",
    engineStack: ["Google Gemini API", "Pydantic Structured Output", "SQLite"],
    sqliteTable: "findings (finding_type = 'CONTEXTUAL_INCONSISTENCY')",
    capabilities: [
      "Chronological timeline validation (e.g., invoice date preceding contract execution)",
      "Arithmetic & tax/subtotal reconciliation across financial schedules",
      "Clause contradiction and unusual legal obligation surfacing",
      "Evidence-grounded citations with confidence scoring",
    ],
    emptyMessage:
      "0 contextual inconsistency findings in SQLite table `findings`. Gemini contextual reasoning will be activated in Phase 4.",
    icon: BrainCircuit,
  },
  "cross-document-analysis": {
    title: "Cross-Document Correlation & Entity Graph",
    subtitle:
      "Correlating entities, amounts, counterparties, and timelines across an entire investigation corpus.",
    phase: "Phase 4 Pipeline",
    engineStack: ["Google Gemini API", "Relational Entity Linker", "SQLite"],
    sqliteTable: "findings (finding_type = 'CROSS_DOC_CONFLICT')",
    capabilities: [
      "Counterparty name, registration ID, and bank account cross-verification",
      "Purchase Order ↔ Bill of Lading ↔ Commercial Invoice triad matching",
      "Cross-document discrepancy matrix generation",
      "Automated linking of conflicting passages across separate PDFs",
    ],
    emptyMessage:
      "0 cross-document conflicts recorded in SQLite. Multi-document correlation requires ingested documents and will be activated in Phase 4.",
    icon: GitCompareArrows,
  },
  "evidence-explorer": {
    title: "Unified Forensic Evidence Explorer",
    subtitle:
      "Centralized evidentiary ledger aggregating visual, metadata, and contextual findings.",
    phase: "Phase 3–4 Pipeline",
    engineStack: ["SQLite Relational Store", "FastAPI Query Engine"],
    sqliteTable: "findings",
    capabilities: [
      "Unified severity & confidence filtering across all forensic modalities",
      "Analyst review workflow: REQUIRES_REVIEW → CONFIRMED / DISMISSED",
      "Direct traceability from finding to source document SHA-256 hash",
      "Immutable audit trail recording for every evidentiary review decision",
    ],
    emptyMessage:
      "0 evidentiary findings currently stored in SQLite table `findings`. No simulated or placeholder findings are generated.",
    icon: ShieldCheck,
  },
  "investigation-dossiers": {
    title: "Evidentiary Investigation Dossiers",
    subtitle:
      "Court- and executive-ready forensic intelligence reports backed by verified findings.",
    phase: "Phase 5 Pipeline",
    engineStack: ["ReportLab PDF Engine", "Gemini Executive Synthesis", "SQLite"],
    sqliteTable: "investigations + findings + audit_logs",
    capabilities: [
      "Automated compilation of case metadata, SHA-256 document manifest, and findings",
      "Visual anomaly heatmaps and side-by-side discrepancy citations",
      "Complete chronological chain-of-custody audit ledger export",
      "Deterministic PDF generation via ReportLab",
    ],
    emptyMessage:
      "No investigation dossiers compiled yet. ReportLab PDF dossier generation will be activated after forensic analysis modules are online.",
    icon: FileSpreadsheet,
  },
};

export default function ModuleArchitectureView({
  section,
  summary,
  selectedInvestigation,
  onSelectInvestigation,
  onOpenNewInvestigation,
}: ModuleArchitectureViewProps) {
  const spec = MODULE_SPECS[section] || MODULE_SPECS["document-intelligence"];
  const Icon = spec.icon;
  const investigations = summary?.recent_investigations ?? [];

  return (
    <div className="space-y-6">
      {/* Module Header Card */}
      <div className="rounded-2xl border border-cyan-500/25 bg-gradient-to-r from-[#0A1328] via-[#0B152A] to-[#080E1C] p-6">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-cyan-500/35 bg-cyan-500/10 text-cyan-400 shadow-glow">
              <Icon className="h-6 w-6" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-bold text-white">{spec.title}</h2>
                <span className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-cyan-300">
                  {spec.phase}
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-300">{spec.subtitle}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {spec.engineStack.map((tech) => (
              <span
                key={tech}
                className="rounded-lg border border-slate-700/80 bg-slate-900/90 px-3 py-1 font-mono text-xs text-slate-300"
              >
                {tech}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Live SQLite State & Active Case Context */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: Genuine Database Empty State + Capabilities */}
        <div className="space-y-6 lg:col-span-7">
          <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
              <div className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-cyan-400">
                <Database className="h-4 w-4" />
                <span>Live SQLite Table State</span>
              </div>
              <code className="rounded bg-slate-900 px-2 py-0.5 font-mono text-xs text-slate-300">
                {spec.sqliteTable}
              </code>
            </div>

            <div className="mt-5 rounded-xl border border-dashed border-slate-800 bg-[#060A14]/80 p-8 text-center">
              <p className="text-sm font-medium text-slate-200">
                {spec.emptyMessage}
              </p>
              <p className="mt-2 font-mono text-xs text-slate-400">
                Phase 1 Foundation Policy: Zero fake scans, zero placeholder AI
                outputs, 100% genuine database state.
              </p>
            </div>

            <div className="mt-6">
              <h3 className="mb-3 flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
                <Layers className="h-4 w-4 text-blue-400" />
                <span>Architectural Specification</span>
              </h3>
              <ul className="space-y-2.5">
                {spec.capabilities.map((cap) => (
                  <li
                    key={cap}
                    className="flex items-start gap-2.5 rounded-xl border border-slate-800/70 bg-[#070B16]/70 px-3.5 py-2.5 text-xs text-slate-300"
                  >
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" />
                    <span>{cap}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* Right: Active Investigation Selector from SQLite */}
        <div className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-6 lg:col-span-5">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
            <div>
              <h3 className="text-sm font-semibold text-white">
                Target Investigation Context
              </h3>
              <p className="text-xs text-slate-400">
                Select a database-backed case to scope this module
              </p>
            </div>
            <button
              type="button"
              onClick={onOpenNewInvestigation}
              className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/35 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300"
            >
              <FolderPlus className="h-3.5 w-3.5" />
              <span>New Case</span>
            </button>
          </div>

          {investigations.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">
              No investigations in SQLite yet. Create an investigation to bind
              it to this forensic module.
            </div>
          ) : (
            <div className="mt-4 space-y-2.5">
              {investigations.map((inv) => {
                const active = selectedInvestigation?.id === inv.id;
                return (
                  <button
                    key={inv.id}
                    type="button"
                    onClick={() => onSelectInvestigation(inv)}
                    className={`w-full rounded-xl border p-3.5 text-left transition ${
                      active
                        ? "border-cyan-500/50 bg-cyan-950/25 text-white"
                        : "border-slate-800/80 bg-[#070B16]/80 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono text-xs">
                      <span className="font-semibold text-cyan-300">
                        {inv.case_code}
                      </span>
                      <span className="text-[10px] text-slate-400">
                        {inv.status}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-xs font-medium text-white">
                      {inv.title}
                    </p>
                    <p className="mt-1 font-mono text-[11px] text-slate-400">
                      {inv.document_count} documents · {inv.findings_count}{" "}
                      findings in SQLite
                    </p>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
