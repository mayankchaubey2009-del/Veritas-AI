"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FolderPlus,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import {
  Investigation,
  InvestigationClassification,
  InvestigationCreatePayload,
  InvestigationPriority,
} from "@/types/veritas";
import { veritasApi } from "@/lib/api";

interface NewInvestigationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (investigation: Investigation) => void;
}

const CLASSIFICATION_OPTIONS: Array<{
  value: InvestigationClassification;
  label: string;
}> = [
  { value: "FINANCIAL_FORENSICS", label: "Financial Statement & Invoice Forensics" },
  { value: "CONTRACT_INTEGRITY", label: "Contract & Legal Instrument Integrity" },
  { value: "IDENTITY_VERIFICATION", label: "Identity & Credential Verification" },
  { value: "REGULATORY_COMPLIANCE", label: "Regulatory & Audit Compliance" },
  { value: "SUPPLY_CHAIN_AUDIT", label: "Supply Chain & Customs Documentation" },
  { value: "GENERAL_FORENSICS", label: "General Multi-Document Investigation" },
];

const PRIORITY_OPTIONS: Array<{
  value: InvestigationPriority;
  label: string;
}> = [
  { value: "CRITICAL", label: "CRITICAL — Immediate Executive Escalation" },
  { value: "HIGH", label: "HIGH — Priority Forensic Review" },
  { value: "MEDIUM", label: "MEDIUM — Standard Investigation Queue" },
  { value: "LOW", label: "LOW — Routine Audit Verification" },
];

const QUICK_SCENARIOS: Array<{
  label: string;
  payload: InvestigationCreatePayload;
}> = [
  {
    label: "Vendor Invoice Discrepancy",
    payload: {
      title: "Q4 Sovereign Procurement & Vendor Invoice Audit",
      description:
        "Cross-examination of procurement master agreements, customs bills of lading, and settlement invoices for potential signature synthesis and line-item alterations.",
      priority: "CRITICAL",
      classification: "FINANCIAL_FORENSICS",
      lead_investigator: "Dr. Elena Rostova (Principal Forensic Analyst)",
    },
  },
  {
    label: "M&A Contract Amendment Review",
    payload: {
      title: "Meridian Holdings Escrow & Addendum Integrity Case",
      description:
        "Forensic verification of multi-party escrow addenda and board resolutions to detect retroactive date modifications or clause substitutions.",
      priority: "HIGH",
      classification: "CONTRACT_INTEGRITY",
      lead_investigator: "Marcus Vance (Senior Legal Forensics)",
    },
  },
];

export default function NewInvestigationModal({
  isOpen,
  onClose,
  onCreated,
}: NewInvestigationModalProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<InvestigationPriority>("HIGH");
  const [classification, setClassification] =
    useState<InvestigationClassification>("FINANCIAL_FORENSICS");
  const [leadInvestigator, setLeadInvestigator] = useState(
    "Lead Forensic Analyst"
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const applyPreset = (preset: InvestigationCreatePayload) => {
    setTitle(preset.title);
    setDescription(preset.description);
    setPriority(preset.priority);
    setClassification(preset.classification);
    setLeadInvestigator(preset.lead_investigator);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (title.trim().length < 3) {
      setError("Investigation title must be at least 3 characters.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const created = await veritasApi.createInvestigation({
        title: title.trim(),
        description: description.trim(),
        priority,
        classification,
        lead_investigator: leadInvestigator.trim() || "Lead Forensic Analyst",
      });
      setTitle("");
      setDescription("");
      setPriority("HIGH");
      setClassification("FINANCIAL_FORENSICS");
      onCreated(created);
      onClose();
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to persist investigation in SQLite database.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-md">
      <div className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-cyan-500/30 bg-[#0A1020] shadow-[0_0_50px_-12px_rgba(6,182,212,0.35)]">
        {/* Top Accent Line */}
        <div className="h-1 w-full bg-gradient-to-r from-blue-600 via-cyan-400 to-blue-600" />

        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800/90 px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 text-cyan-400">
              <FolderPlus className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">
                Initialize Forensic Investigation
              </h2>
              <p className="font-mono text-xs text-slate-400">
                Creates a persistent SQLite case record &amp; immutable audit log
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-800 hover:text-white"
            aria-label="Close modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="space-y-5 p-6">
          {/* Quick Scenario Fillers */}
          <div className="rounded-xl border border-slate-800/90 bg-slate-900/50 p-3.5">
            <div className="mb-2 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-cyan-400">
              <Sparkles className="h-3.5 w-3.5" />
              <span>Quick Forensic Case Templates</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {QUICK_SCENARIOS.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => applyPreset(item.payload)}
                  className="rounded-lg border border-slate-700/80 bg-slate-800/70 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-cyan-500/40 hover:bg-cyan-500/10 hover:text-cyan-300"
                >
                  + {item.label}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-950/30 p-3.5 text-sm text-rose-200">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          <div>
            <label
              htmlFor="inv-title"
              className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-300"
            >
              Investigation Title <span className="text-cyan-400">*</span>
            </label>
            <input
              id="inv-title"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Q4 Sovereign Procurement & Vendor Invoice Audit"
              className="w-full rounded-xl border border-slate-800 bg-[#060A15] px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-cyan-400"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="inv-classification"
                className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-300"
              >
                Forensic Classification
              </label>
              <select
                id="inv-classification"
                value={classification}
                onChange={(e) =>
                  setClassification(
                    e.target.value as InvestigationClassification
                  )
                }
                className="w-full rounded-xl border border-slate-800 bg-[#060A15] px-3.5 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400"
              >
                {CLASSIFICATION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="inv-priority"
                className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-300"
              >
                Priority Level
              </label>
              <select
                id="inv-priority"
                value={priority}
                onChange={(e) =>
                  setPriority(e.target.value as InvestigationPriority)
                }
                className="w-full rounded-xl border border-slate-800 bg-[#060A15] px-3.5 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400"
              >
                {PRIORITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label
              htmlFor="inv-lead"
              className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-300"
            >
              Assigned Lead Investigator
            </label>
            <input
              id="inv-lead"
              type="text"
              required
              value={leadInvestigator}
              onChange={(e) => setLeadInvestigator(e.target.value)}
              placeholder="e.g., Dr. Elena Rostova"
              className="w-full rounded-xl border border-slate-800 bg-[#060A15] px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-cyan-400"
            />
          </div>

          <div>
            <label
              htmlFor="inv-description"
              className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-300"
            >
              Investigation Hypothesis &amp; Scope Briefing
            </label>
            <textarea
              id="inv-description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the target evidentiary documents, suspected anomalies, or audit scope..."
              className="w-full rounded-xl border border-slate-800 bg-[#060A15] px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-cyan-400"
            />
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-slate-800/80 pt-4">
            <div className="flex items-center gap-2 font-mono text-xs text-slate-400">
              <CheckCircle2 className="h-4 w-4 text-cyan-400" />
              <span>Persists directly to SQLite database</span>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-300 transition hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-5 py-2 text-sm font-semibold text-white shadow-glow transition hover:from-blue-500 hover:to-cyan-400 disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Creating Case...</span>
                  </>
                ) : (
                  <>
                    <FolderPlus className="h-4 w-4" />
                    <span>Create Investigation</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
