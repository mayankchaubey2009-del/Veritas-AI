"use client";

import React, { useState } from "react";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Compass,
  Play,
  ShieldCheck,
  Sparkles,
  UserCheck,
  X,
} from "lucide-react";
import { AuthenticatedUser, NavigationSectionId } from "@/types/veritas";

export interface DemoStepSpec {
  stepNumber: number;
  title: string;
  targetSection: NavigationSectionId;
  requiredPersona?: string;
  personaBadge: string;
  summary: string;
  verificationHighlight: string;
}

export const GUIDED_DEMO_STEPS: DemoStepSpec[] = [
  {
    stepNumber: 1,
    title: "Log In as Forensic Investigator",
    targetSection: "command-centre",
    requiredPersona: "dr.rostova",
    personaBadge: "INVESTIGATOR (Dr. Elena Rostova)",
    summary:
      "Establishes an authenticated session using HttpOnly SameSite cookies + Bearer token backed by SQLite user_sessions.",
    verificationHighlight:
      "PBKDF2-HMAC-SHA256 (310,000 iterations) & scrypt KDF active; session logged in audit_logs.",
  },
  {
    stepNumber: 2,
    title: "Select Active Forensic Investigation",
    targetSection: "investigations",
    requiredPersona: "dr.rostova",
    personaBadge: "INVESTIGATOR",
    summary:
      "Inspects case VRT-2026-0001 (Helios / Meridian Procurement Discrepancy) with RBAC ownership and cross-investigation isolation.",
    verificationHighlight:
      "Unauthorized cross-investigation access is blocked with HTTP 403 CROSS_INVESTIGATION_ACCESS_DENIED.",
  },
  {
    stepNumber: 3,
    title: "Multi-Document Ingestion & SHA-256 Fingerprints",
    targetSection: "document-intelligence",
    requiredPersona: "dr.rostova",
    personaBadge: "INVESTIGATOR",
    summary:
      "Validates MIME types, magic signatures (%PDF-, PNG, JPEG), page/pixel limits, and stores files under randomized UUID filenames.",
    verificationHighlight:
      "Every document is fingerprinted with SHA-256 and stored outside frontend/public with path containment checks.",
  },
  {
    stepNumber: 4,
    title: "Document Structure, Tables & Entities",
    targetSection: "document-intelligence",
    requiredPersona: "dr.rostova",
    personaBadge: "INVESTIGATOR",
    summary:
      "Inspects automated classification confidence, layout regions, extracted line-item tables, and normalized entities with page coordinates.",
    verificationHighlight:
      "Interactive page preview overlays exact [x0, y0, x1, y1] bounding boxes from PyMuPDF & PaddleOCR.",
  },
  {
    stepNumber: 5,
    title: "7-Module Visual Forensics & ELA Heatmaps",
    targetSection: "visual-forensics",
    requiredPersona: "dr.rostova",
    personaBadge: "INVESTIGATOR",
    summary:
      "Examines pixel-level Error Level Analysis (ELA), local noise variance heatmaps, typography consistency, and PDF metadata signals.",
    verificationHighlight:
      "Every visual finding includes benign explanations, technical metrics, and human disposition controls.",
  },
  {
    stepNumber: 6,
    title: "Cross-Document Contradictions & Decimal Arithmetic",
    targetSection: "cross-document-analysis",
    requiredPersona: "dr.rostova",
    personaBadge: "INVESTIGATOR",
    summary:
      "Detects the $11,900.00 vs $14,500.00 invoice total contradiction, line-item sum mismatch, and conflicting IBAN settlement accounts.",
    verificationHighlight:
      "All financial checks use exact Python decimal.Decimal (ROUND_HALF_UP) — zero floating-point drift.",
  },
  {
    stepNumber: 7,
    title: "Entity Relationship Graph & Chronological Timeline",
    targetSection: "evidence-explorer",
    requiredPersona: "dr.rostova",
    personaBadge: "INVESTIGATOR",
    summary:
      "Explores cross-document entity clusters, supporting vs contradicting graph edges, and chronological timeline events.",
    verificationHighlight:
      "OCR-similar strings are separated from exact matches so distinct entities are never falsely merged.",
  },
  {
    stepNumber: 8,
    title: "Generate Evidence-Grounded Investigation Dossier",
    targetSection: "investigation-dossiers",
    requiredPersona: "dr.rostova",
    personaBadge: "INVESTIGATOR (Self-Approval Blocked)",
    summary:
      "Synthesizes Sections A–N with 100% claim-to-evidence validation. Newly generated dossiers always begin as UNAPPROVED_AI_ASSISTED.",
    verificationHighlight:
      "Separation of duties: Dr. Rostova cannot approve a dossier she generated (HTTP 403 SELF_DOSSIER_APPROVAL_PROHIBITED).",
  },
  {
    stepNumber: 9,
    title: "Switch to Reviewer & Approve Dossier",
    targetSection: "investigation-dossiers",
    requiredPersona: "m.vance",
    personaBadge: "REVIEWER (Marcus Vance)",
    summary:
      "Switches to independent Compliance Reviewer Marcus Vance to review and formally approve the dossier with session-enforced attribution.",
    verificationHighlight:
      "Reviewer identity is derived strictly from the authenticated server session — request body spoofing is ignored.",
  },
  {
    stepNumber: 10,
    title: "Verify Cryptographic SHA-256 Audit Hash Chain",
    targetSection: "audit-history",
    requiredPersona: "m.vance",
    personaBadge: "REVIEWER",
    summary:
      "Runs live cryptographic verification across all audit_logs entries, checking sequence numbers, prev_hash links, and event_hash digests.",
    verificationHighlight:
      "Clearly distinguishes AUTHENTICATED_HUMAN, SYSTEM, BACKGROUND_WORKER, and HISTORICAL_SEED_SIMULATION origins.",
  },
  {
    stepNumber: 11,
    title: "Export Immutable PDF & JSON Dossier",
    targetSection: "investigation-dossiers",
    requiredPersona: "m.vance",
    personaBadge: "REVIEWER",
    summary:
      "Downloads the multi-page forensic PDF report and machine-readable JSON bundle with verified SHA-256 integrity digests.",
    verificationHighlight:
      "Includes Prominent Synthetic Demo Watermark, Evidence Reference Manifest, and Review History.",
  },
  {
    stepNumber: 12,
    title: "Run 10-Specimen Quality Benchmark & SQLite Backup",
    targetSection: "settings",
    requiredPersona: "admin.nair",
    personaBadge: "ADMIN (Director Priya Nair)",
    summary:
      "Switches to Platform Administrator to run the reproducible 10-specimen extraction benchmark and create an online SQLite backup.",
    verificationHighlight:
      "Reports real CER, Precision/Recall/F1, table accuracy, and verifies SQLite backup SHA-256 & PRAGMA integrity_check.",
  },
];

interface GuidedDemoWalkthroughProps {
  isOpen: boolean;
  onClose: () => void;
  activeSection: NavigationSectionId;
  onNavigateSection: (section: NavigationSectionId) => void;
  currentUser: AuthenticatedUser | null;
  onSwitchPersona: (username: string) => Promise<void>;
}

export default function GuidedDemoWalkthrough({
  isOpen,
  onClose,
  onNavigateSection,
  currentUser,
  onSwitchPersona,
}: GuidedDemoWalkthroughProps) {
  const [currentStepIdx, setCurrentStepIdx] = useState(0);
  const [executingStep, setExecutingStep] = useState(false);

  if (!isOpen) return null;

  const step = GUIDED_DEMO_STEPS[currentStepIdx];

  const activateStep = async (index: number) => {
    const target = GUIDED_DEMO_STEPS[index];
    setCurrentStepIdx(index);
    setExecutingStep(true);
    try {
      if (
        target.requiredPersona &&
        currentUser?.username !== target.requiredPersona
      ) {
        await onSwitchPersona(target.requiredPersona);
      }
      onNavigateSection(target.targetSection);
    } finally {
      setExecutingStep(false);
    }
  };

  return (
    <div className="border-b border-cyan-500/30 bg-gradient-to-r from-[#071126] via-[#0A1832] to-[#071126] px-4 py-3.5 shadow-lg sm:px-6">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/15 px-2.5 py-1 font-mono text-[11px] font-bold uppercase tracking-wider text-cyan-300">
              <Compass className="h-3.5 w-3.5 text-cyan-400" />
              Guided Live Demo Mode · Step {step.stepNumber} of{" "}
              {GUIDED_DEMO_STEPS.length}
            </span>
            <span className="inline-flex items-center gap-1 rounded border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-blue-300">
              <UserCheck className="h-3 w-3 text-cyan-400" />
              {step.personaBadge}
            </span>
            <span className="hidden rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] text-amber-300 xl:inline-block">
              SYNTHETIC DEMONSTRATION ENVIRONMENT
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            {GUIDED_DEMO_STEPS.map((s, idx) => (
              <button
                key={s.stepNumber}
                type="button"
                onClick={() => activateStep(idx)}
                disabled={executingStep}
                title={`Step ${s.stepNumber}: ${s.title}`}
                className={`h-6 w-6 rounded-md font-mono text-[10px] font-bold transition ${
                  idx === currentStepIdx
                    ? "border border-cyan-400 bg-cyan-500 text-slate-950 shadow-glow"
                    : idx < currentStepIdx
                    ? "border border-emerald-500/40 bg-emerald-950/40 text-emerald-300 hover:border-emerald-400"
                    : "border border-slate-800 bg-slate-900/80 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                {s.stepNumber}
              </button>
            ))}

            <button
              type="button"
              onClick={onClose}
              className="ml-2 rounded-lg border border-slate-800 bg-slate-900/80 p-1.5 text-slate-400 hover:border-slate-700 hover:text-white"
              title="Close Guided Demo Bar"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex flex-col justify-between gap-3 rounded-xl border border-slate-800/90 bg-[#050914]/90 p-3.5 lg:flex-row lg:items-center">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">
                Step {step.stepNumber}: {step.title}
              </h3>
            </div>
            <p className="text-xs text-slate-300">{step.summary}</p>
            <div className="flex items-center gap-1.5 pt-0.5 font-mono text-[11px] text-emerald-300">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
              <span>{step.verificationHighlight}</span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => activateStep(Math.max(0, currentStepIdx - 1))}
              disabled={currentStepIdx === 0 || executingStep}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-cyan-500/40 hover:text-white disabled:opacity-40"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              <span>Previous</span>
            </button>

            <button
              type="button"
              onClick={() => activateStep(currentStepIdx)}
              disabled={executingStep}
              className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-500/15 px-3.5 py-2 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/25"
            >
              <Play className="h-3.5 w-3.5 text-cyan-400" />
              <span>Execute Step {step.stepNumber}</span>
            </button>

            <button
              type="button"
              onClick={() =>
                activateStep(
                  Math.min(GUIDED_DEMO_STEPS.length - 1, currentStepIdx + 1)
                )
              }
              disabled={
                currentStepIdx === GUIDED_DEMO_STEPS.length - 1 || executingStep
              }
              className="inline-flex items-center gap-1 rounded-xl border border-cyan-400/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-3.5 py-2 text-xs font-semibold text-white transition hover:from-blue-500 hover:to-cyan-400 disabled:opacity-40"
            >
              <span>Next Step</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
