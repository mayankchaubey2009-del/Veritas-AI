"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Boxes,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Copy,
  Cpu,
  Eye,
  FileCode2,
  FileImage,
  FileSearch,
  FileText,
  FolderPlus,
  GitBranch,
  Hash,
  Layers,
  Loader2,
  RefreshCw,
  ScanText,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Table2,
  Tags,
  Type,
  UploadCloud,
  X,
} from "lucide-react";
import {
  BoundingBox,
  DocumentDetail,
  DocumentPage,
  DocumentSummary,
  Investigation,
} from "@/types/veritas";
import { veritasApi } from "@/lib/api";

interface DocumentIntelligenceViewProps {
  investigations: Investigation[];
  selectedInvestigation: Investigation | null;
  onSelectInvestigation: (inv: Investigation) => void;
  onOpenNewInvestigation: () => void;
  onGlobalRefresh: () => void;
  onOpenVisualForensics?: (documentId: string) => void;
}

type InspectorTab =
  | "preview-overlay"
  | "layout-tree"
  | "tables"
  | "entities"
  | "blocks-raw";

type OverlayLayerMode = "layout" | "tables" | "entities" | "blocks";

interface OverlayBoxItem {
  id: string;
  category: string;
  title: string;
  subtitle: string;
  bbox: BoundingBox;
  confidence: number;
  strokeColor: string;
  fillColor: string;
  badgeStyle: string;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function getMethodBadge(method: string) {
  switch (method) {
    case "NATIVE_PDF":
      return {
        label: "PATH A · NATIVE PDF (PyMuPDF)",
        shortLabel: "NATIVE PDF",
        style: "border-blue-500/40 bg-blue-500/15 text-blue-300",
      };
    case "VISUAL_OCR":
      return {
        label: "PATH B · VISUAL OCR (PaddleOCR)",
        shortLabel: "VISUAL OCR",
        style: "border-cyan-500/40 bg-cyan-500/15 text-cyan-300",
      };
    case "HYBRID_PDF_OCR":
      return {
        label: "HYBRID · NATIVE PDF + VISUAL OCR",
        shortLabel: "HYBRID PDF+OCR",
        style: "border-purple-500/40 bg-purple-500/15 text-purple-300",
      };
    default:
      return {
        label: method,
        shortLabel: method,
        style: "border-slate-700 bg-slate-800 text-slate-300",
      };
  }
}

function getRegionColors(regionType: string) {
  switch (regionType) {
    case "DOCUMENT_TITLE":
      return {
        stroke: "#38bdf8",
        fill: "rgba(56, 189, 248, 0.16)",
        badge: "border-sky-500/40 bg-sky-500/15 text-sky-300",
      };
    case "SECTION_HEADING":
    case "HEADER":
      return {
        stroke: "#818cf8",
        fill: "rgba(129, 140, 248, 0.16)",
        badge: "border-indigo-500/40 bg-indigo-500/15 text-indigo-300",
      };
    case "TABLE":
      return {
        stroke: "#34d399",
        fill: "rgba(52, 211, 153, 0.15)",
        badge: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
      };
    case "KEY_VALUE_REGION":
      return {
        stroke: "#22d3ee",
        fill: "rgba(34, 211, 238, 0.14)",
        badge: "border-cyan-500/40 bg-cyan-500/15 text-cyan-300",
      };
    case "SIGNATURE_REGION":
      return {
        stroke: "#fbbf24",
        fill: "rgba(251, 191, 36, 0.18)",
        badge: "border-amber-500/40 bg-amber-500/15 text-amber-300",
      };
    case "STAMP_REGION":
      return {
        stroke: "#f43f5e",
        fill: "rgba(244, 63, 94, 0.18)",
        badge: "border-rose-500/40 bg-rose-500/15 text-rose-300",
      };
    case "FOOTER":
      return {
        stroke: "#94a3b8",
        fill: "rgba(148, 163, 184, 0.14)",
        badge: "border-slate-600 bg-slate-800 text-slate-300",
      };
    default:
      return {
        stroke: "#60a5fa",
        fill: "rgba(96, 165, 250, 0.12)",
        badge: "border-blue-500/35 bg-blue-500/10 text-blue-300",
      };
  }
}

function getEntityBadgeStyle(entityType: string) {
  switch (entityType) {
    case "MONETARY_AMOUNT":
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    case "INVOICE_NUMBER":
    case "ACCOUNT_REFERENCE":
      return "border-cyan-500/40 bg-cyan-500/15 text-cyan-300";
    case "COMPANY_NAME":
      return "border-blue-500/40 bg-blue-500/15 text-blue-300";
    case "PERSON_NAME":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    case "TAX_IDENTIFIER":
      return "border-purple-500/40 bg-purple-500/15 text-purple-300";
    case "DATE":
      return "border-indigo-500/40 bg-indigo-500/15 text-indigo-300";
    case "ADDRESS":
      return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    default:
      return "border-slate-700 bg-slate-800 text-slate-300";
  }
}

export default function DocumentIntelligenceView({
  investigations,
  selectedInvestigation,
  onSelectInvestigation,
  onOpenNewInvestigation,
  onGlobalRefresh,
  onOpenVisualForensics,
}: DocumentIntelligenceViewProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [docDetail, setDocDetail] = useState<DocumentDetail | null>(null);
  const [activePageNumber, setActivePageNumber] = useState<number>(1);
  const [activePageDetail, setActivePageDetail] =
    useState<DocumentPage | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [inspectorTab, setInspectorTab] =
    useState<InspectorTab>("preview-overlay");
  const [overlayMode, setOverlayMode] = useState<OverlayLayerMode>("layout");
  const [selectedOverlayItem, setSelectedOverlayItem] =
    useState<OverlayBoxItem | null>(null);
  const [entityFilter, setEntityFilter] = useState<string>("ALL");
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const loadDocuments = useCallback(async (invId: string) => {
    setDocsLoading(true);
    setUploadError(null);
    try {
      const list = await veritasApi.listInvestigationDocuments(invId);
      setDocuments(list);
      setSelectedDocId((prev) => {
        if (list.length === 0) return null;
        if (prev && list.some((d) => d.id === prev)) return prev;
        return list[0].id;
      });
    } catch (err: unknown) {
      setUploadError(
        err instanceof Error
          ? err.message
          : "Failed to load investigation documents."
      );
    } finally {
      setDocsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedInvestigation?.id) {
      loadDocuments(selectedInvestigation.id);
    } else {
      setDocuments([]);
      setSelectedDocId(null);
      setDocDetail(null);
      setActivePageDetail(null);
    }
  }, [selectedInvestigation?.id, loadDocuments]);

  const loadDocumentAndPage = useCallback(
    async (docId: string, pageNum = 1) => {
      setDetailLoading(true);
      try {
        const detail = await veritasApi.getDocumentDetail(docId);
        setDocDetail(detail);
        const clampedPage = Math.max(
          1,
          Math.min(pageNum, Math.max(1, detail.page_count))
        );
        setActivePageNumber(clampedPage);
        const pageMatch =
          detail.pages.find((p) => p.page_number === clampedPage) ||
          detail.pages[0] ||
          null;
        setActivePageDetail(pageMatch);
        setSelectedOverlayItem(null);
      } catch (err: unknown) {
        setUploadError(
          err instanceof Error
            ? err.message
            : "Failed to load document intelligence details."
        );
      } finally {
        setDetailLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (selectedDocId) {
      loadDocumentAndPage(selectedDocId, 1);
    } else {
      setDocDetail(null);
      setActivePageDetail(null);
    }
  }, [selectedDocId, loadDocumentAndPage]);

  const handleSelectPage = async (pageNum: number) => {
    if (!docDetail) return;
    if (pageNum < 1 || pageNum > docDetail.page_count) return;
    setActivePageNumber(pageNum);
    setSelectedOverlayItem(null);

    const cached = docDetail.pages.find((p) => p.page_number === pageNum);
    if (cached) {
      setActivePageDetail(cached);
    }
    try {
      const livePage = await veritasApi.getDocumentPage(docDetail.id, pageNum);
      setActivePageDetail(livePage);
    } catch {
      // Fallback to cached page
    }
  };

  const enqueueFiles = (fileList: FileList | File[]) => {
    setUploadError(null);
    const incoming = Array.from(fileList);
    if (incoming.length === 0) return;

    setQueuedFiles((prev) => {
      const existingKeys = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const additions = incoming.filter(
        (f) => !existingKeys.has(`${f.name}:${f.size}`)
      );
      return [...prev, ...additions];
    });
  };

  const handleUploadQueued = async () => {
    if (!selectedInvestigation) {
      setUploadError("Please select or create an investigation first.");
      return;
    }
    if (queuedFiles.length === 0) return;

    setUploading(true);
    setUploadProgress(5);
    setUploadError(null);

    try {
      const response = await veritasApi.uploadInvestigationDocuments(
        selectedInvestigation.id,
        queuedFiles,
        selectedInvestigation.lead_investigator,
        (pct) => setUploadProgress(pct)
      );
      setQueuedFiles([]);
      await loadDocuments(selectedInvestigation.id);
      if (response.documents.length > 0) {
        setSelectedDocId(response.documents[0].id);
      }
      onGlobalRefresh();
    } catch (err: unknown) {
      setUploadError(
        err instanceof Error
          ? err.message
          : "Document upload and structure analysis failed."
      );
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Build bounding-box overlay items for the active page based on selected layer mode
  const overlayItems: OverlayBoxItem[] = React.useMemo(() => {
    if (!activePageDetail) return [];

    if (overlayMode === "layout") {
      return activePageDetail.layout_regions.map((reg) => {
        const col = getRegionColors(reg.region_type);
        return {
          id: reg.id,
          category: reg.region_type,
          title: reg.label,
          subtitle: reg.text_content,
          bbox: reg.bounding_box,
          confidence: reg.confidence,
          strokeColor: col.stroke,
          fillColor: col.fill,
          badgeStyle: col.badge,
        };
      });
    }

    if (overlayMode === "tables") {
      const items: OverlayBoxItem[] = [];
      for (const tbl of activePageDetail.tables) {
        items.push({
          id: tbl.id,
          category: `TABLE ${tbl.table_identifier}`,
          title: `${tbl.table_identifier} (${tbl.row_count}×${tbl.column_count})`,
          subtitle: `Headers: ${tbl.headers.join(" | ")}`,
          bbox: tbl.bounding_box,
          confidence: tbl.confidence,
          strokeColor: "#34d399",
          fillColor: "rgba(52, 211, 153, 0.10)",
          badgeStyle:
            "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
        });
        for (const cell of tbl.cells) {
          items.push({
            id: cell.id,
            category: cell.is_header
              ? `HEADER CELL [${cell.row_index},${cell.col_index}]`
              : `CELL [${cell.row_index},${cell.col_index}]`,
            title: cell.cell_text || "(Empty Cell)",
            subtitle: `Table ${tbl.table_identifier} · Row ${cell.row_index + 1}, Col ${cell.col_index + 1}`,
            bbox: cell.bounding_box,
            confidence: cell.confidence,
            strokeColor: cell.is_header ? "#22d3ee" : "#10b981",
            fillColor: cell.is_header
              ? "rgba(34, 211, 238, 0.16)"
              : "rgba(16, 185, 129, 0.12)",
            badgeStyle:
              "border-emerald-500/35 bg-emerald-500/10 text-emerald-300",
          });
        }
      }
      return items;
    }

    if (overlayMode === "entities") {
      return activePageDetail.entities.map((ent) => ({
        id: ent.id,
        category: ent.entity_type,
        title: `Normalized: ${ent.normalized_value}`,
        subtitle: `Raw Extracted: "${ent.raw_value}"`,
        bbox: ent.bounding_box,
        confidence: ent.confidence,
        strokeColor: "#a855f7",
        fillColor: "rgba(168, 85, 247, 0.16)",
        badgeStyle: getEntityBadgeStyle(ent.entity_type),
      }));
    }

    // Default: "blocks"
    return activePageDetail.extractions.map((blk) => ({
      id: blk.id,
      category: blk.field_name || blk.extraction_method,
      title: blk.field_name
        ? `${blk.field_name}: ${blk.field_value}`
        : `Block #${blk.block_index + 1}`,
      subtitle: blk.extracted_text,
      bbox: blk.bounding_box,
      confidence: blk.confidence,
      strokeColor: "#3b82f6",
      fillColor: "rgba(59, 130, 246, 0.14)",
      badgeStyle: "border-blue-500/40 bg-blue-500/15 text-blue-300",
    }));
  }, [activePageDetail, overlayMode]);

  const filteredEntities = React.useMemo(() => {
    if (!docDetail) return [];
    if (entityFilter === "ALL") return docDetail.entities;
    return docDetail.entities.filter((e) => e.entity_type === entityFilter);
  }, [docDetail, entityFilter]);

  return (
    <div className="space-y-6">
      {/* Top Banner & Active Investigation Selector */}
      <section className="rounded-2xl border border-cyan-500/25 bg-gradient-to-r from-[#0A1328] via-[#0B152A] to-[#080E1C] p-6">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-cyan-500/35 bg-cyan-500/10 text-cyan-400 shadow-glow">
              <FileSearch className="h-6 w-6" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-bold text-white">
                  Document Structure Understanding &amp; Intelligent Classification
                </h2>
                <span className="rounded-md border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-emerald-300">
                  PHASE 2B ACTIVE
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-300 sm:text-sm">
                Dual-Path extraction (<strong className="text-blue-300">PyMuPDF</strong>{" "}
                + <strong className="text-cyan-300">PaddleOCR</strong>) combined
                with <strong className="text-emerald-300">OpenCV</strong>{" "}
                structural layout trees, multi-column table grid extraction,
                entity normalization, and confidence-gated document
                classification.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {investigations.length > 0 ? (
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs uppercase text-slate-400">
                  Target Case:
                </span>
                <select
                  aria-label="Select target investigation for document ingestion"
                  value={selectedInvestigation?.id || ""}
                  onChange={(e) => {
                    const found = investigations.find(
                      (i) => i.id === e.target.value
                    );
                    if (found) onSelectInvestigation(found);
                  }}
                  className="rounded-xl border border-cyan-500/35 bg-[#060A14] px-3.5 py-2.5 text-xs font-medium text-white outline-none focus:border-cyan-400"
                >
                  {investigations.map((inv) => (
                    <option key={inv.id} value={inv.id}>
                      {inv.case_code} — {inv.title}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <button
                type="button"
                onClick={onOpenNewInvestigation}
                className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-4 py-2.5 text-xs font-semibold text-white shadow-glow"
              >
                <FolderPlus className="h-4 w-4" />
                <span>Create Investigation First</span>
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Drag & Drop Multi-Document Upload Zone */}
      <section className="rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setIsDragging(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            if (e.dataTransfer.files?.length) {
              enqueueFiles(e.dataTransfer.files);
            }
          }}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              fileInputRef.current?.click();
            }
          }}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-5 text-center transition-all ${
            isDragging
              ? "border-cyan-400 bg-cyan-500/10 shadow-glow"
              : "border-slate-700/80 bg-[#060A14]/70 hover:border-cyan-500/40 hover:bg-slate-900/50"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            onChange={(e) => {
              if (e.target.files) {
                enqueueFiles(e.target.files);
                e.target.value = "";
              }
            }}
            className="hidden"
          />

          <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 text-cyan-400">
            <UploadCloud className="h-5 w-5" />
          </div>
          <h3 className="text-sm font-semibold text-white">
            Drag &amp; Drop Evidentiary Documents or Click to Browse (PDF, PNG,
            JPG, JPEG)
          </h3>
          <p className="mt-1 max-w-2xl text-xs text-slate-400">
            Executes SHA-256 fingerprinting, Dual-Path Extraction (Path A
            PyMuPDF / Path B PaddleOCR), automated document classification,
            layout region tree decomposition, table extraction, and entity
            normalization.
          </p>
        </div>

        {queuedFiles.length > 0 && (
          <div className="mt-4 space-y-3 rounded-xl border border-slate-800 bg-[#070B16] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-mono text-xs font-semibold uppercase tracking-wider text-cyan-300">
                Staged for Ingestion ({queuedFiles.length} file
                {queuedFiles.length > 1 ? "s" : ""})
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => setQueuedFiles([])}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                >
                  Clear Queue
                </button>
                <button
                  type="button"
                  disabled={uploading || !selectedInvestigation}
                  onClick={handleUploadQueued}
                  className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/50 bg-gradient-to-r from-blue-600 to-cyan-500 px-4 py-1.5 text-xs font-semibold text-white shadow-glow disabled:opacity-50"
                >
                  {uploading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Ingesting &amp; Analyzing Structure...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5" />
                      <span>Upload &amp; Run Structure Intelligence</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {queuedFiles.map((file, idx) => (
                <div
                  key={`${file.name}-${idx}`}
                  className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-200">
                      {file.name}
                    </p>
                    <p className="font-mono text-[10px] text-slate-400">
                      {formatBytes(file.size)}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() =>
                      setQueuedFiles((prev) =>
                        prev.filter((_, i) => i !== idx)
                      )
                    }
                    className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-rose-300"
                    aria-label="Remove file from queue"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>

            {uploading && (
              <div className="space-y-1.5 pt-1">
                <div className="flex items-center justify-between font-mono text-[11px] text-cyan-300">
                  <span>
                    Executing SHA-256, Dual-Path Extraction &amp; Phase 2B
                    Structure Analysis...
                  </span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all duration-200"
                    style={{ width: `${Math.max(8, uploadProgress)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {uploadError && (
          <div className="mt-4 flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-950/30 p-3.5 text-xs text-rose-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
            <div>
              <span className="font-semibold">Ingestion / Validation Error: </span>
              <span>{uploadError}</span>
            </div>
          </div>
        )}
      </section>

      {/* Main Split Workspace: Document Corpus List (Left 4 cols) + Deep Document Inspector (Right 8 cols) */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        {/* Left: Ingested Document List */}
        <section className="flex flex-col rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 xl:col-span-4">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-white">
                  Ingested Evidentiary Corpus
                </h3>
                <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 font-mono text-xs text-cyan-300">
                  {documents.length}
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Select a document to inspect classification, layout &amp;
                overlays
              </p>
            </div>

            {selectedInvestigation && (
              <button
                type="button"
                onClick={() => loadDocuments(selectedInvestigation.id)}
                disabled={docsLoading}
                className="rounded-lg border border-slate-800 bg-slate-900 p-2 text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300"
                title="Refresh document list"
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 ${docsLoading ? "animate-spin" : ""}`}
                />
              </button>
            )}
          </div>

          {docsLoading && documents.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-xs text-slate-400">
              <Loader2 className="mr-2 h-4 w-4 animate-spin text-cyan-400" />
              <span>Loading documents from SQLite...</span>
            </div>
          ) : documents.length === 0 ? (
            <div className="my-6 rounded-xl border border-dashed border-slate-800 bg-[#060A14]/60 p-8 text-center">
              <FileText className="mx-auto mb-2.5 h-7 w-7 text-slate-500" />
              <p className="text-xs font-medium text-slate-300">
                No documents uploaded for this investigation yet.
              </p>
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              {documents.map((doc) => {
                const isSelected = selectedDocId === doc.id;
                const badge = getMethodBadge(doc.extraction_method_summary);

                return (
                  <div
                    key={doc.id}
                    onClick={() => setSelectedDocId(doc.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        setSelectedDocId(doc.id);
                      }
                    }}
                    className={`cursor-pointer rounded-xl border p-3.5 transition-all ${
                      isSelected
                        ? "border-cyan-500/50 bg-gradient-to-r from-blue-950/45 via-cyan-950/25 to-slate-900/70 shadow-glow"
                        : "border-slate-800/80 bg-[#070B16]/85 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        {doc.file_type === "PDF" ? (
                          <FileText className="h-4 w-4 shrink-0 text-blue-400" />
                        ) : (
                          <FileImage className="h-4 w-4 shrink-0 text-cyan-400" />
                        )}
                        <span className="truncate text-xs font-semibold text-white">
                          {doc.filename}
                        </span>
                      </div>

                      <span
                        className={`shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                          doc.processing_status === "COMPLETED"
                            ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-300"
                            : "border-amber-500/35 bg-amber-500/10 text-amber-300"
                        }`}
                      >
                        {doc.processing_status}
                      </span>
                    </div>

                    {/* Classification + Extraction Method Badges */}
                    <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                      <span
                        className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${
                          doc.classification_is_certain
                            ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                            : "border-amber-500/40 bg-amber-500/15 text-amber-300"
                        }`}
                      >
                        {doc.document_type_label} (
                        {(doc.classification_confidence * 100).toFixed(0)}%)
                      </span>
                      <span
                        className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${badge.style}`}
                      >
                        {badge.shortLabel}
                      </span>
                    </div>

                    {/* Structure Counters */}
                    <div className="mt-2.5 grid grid-cols-3 gap-1.5 rounded-lg border border-slate-800/80 bg-[#050811] px-2.5 py-1.5 text-center font-mono text-[10px]">
                      <div>
                        <span className="text-slate-500">Regions: </span>
                        <span className="font-semibold text-slate-200">
                          {doc.layout_region_count}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">Tables: </span>
                        <span className="font-semibold text-emerald-300">
                          {doc.table_count}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">Entities: </span>
                        <span className="font-semibold text-cyan-300">
                          {doc.entity_count}
                        </span>
                      </div>
                    </div>

                    {/* SHA-256 Fingerprint */}
                    <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-slate-400">
                      <span className="truncate" title={doc.sha256_hash}>
                        SHA-256: {doc.sha256_hash.slice(0, 18)}...
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCopyHash(doc.sha256_hash);
                        }}
                        className="ml-2 shrink-0 text-cyan-400 hover:text-cyan-300"
                        title="Copy full SHA-256 hash"
                      >
                        {copiedHash === doc.sha256_hash ? (
                          <Check className="h-3 w-3 text-emerald-400" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </button>
                    </div>

                    {onOpenVisualForensics && (
                      <div className="mt-2 border-t border-slate-800/70 pt-2">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenVisualForensics(doc.id);
                          }}
                          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-[11px] font-semibold text-cyan-300 transition hover:bg-cyan-500/20"
                        >
                          <Eye className="h-3 w-3" />
                          <span>Inspect in Visual Forensics</span>
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Right: Deep Document Structure & Overlay Inspector */}
        <section className="flex flex-col rounded-2xl border border-slate-800/90 bg-[#0A1020]/90 p-5 xl:col-span-8">
          {!selectedDocId ? (
            <div className="flex flex-1 flex-col items-center justify-center py-24 text-center">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 text-cyan-400">
                <ScanText className="h-6 w-6" />
              </div>
              <h3 className="text-sm font-semibold text-white">
                Document Structure &amp; Classification Inspector
              </h3>
              <p className="mt-1 max-w-md text-xs text-slate-400">
                Select an ingested document on the left to inspect its
                automated classification, bounding-box page overlay, layout
                hierarchy tree, extracted tables, and normalized entities.
              </p>
            </div>
          ) : detailLoading || !docDetail ? (
            <div className="flex flex-1 items-center justify-center py-24 text-xs text-slate-400">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-cyan-400" />
              <span>
                Loading Phase 2B structure, tables, entities &amp; coordinates...
              </span>
            </div>
          ) : (
            <div className="space-y-5">
              {/* 1. Document Classification & Uncertainty Banner (MODULE 1) */}
              <div className="rounded-xl border border-slate-800 bg-[#070B16] p-4">
                <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-base font-bold text-white">
                        {docDetail.filename}
                      </h3>
                      <span
                        className={`rounded border px-2.5 py-0.5 font-mono text-[10px] font-semibold ${
                          getMethodBadge(docDetail.extraction_method_summary)
                            .style
                        }`}
                      >
                        {
                          getMethodBadge(docDetail.extraction_method_summary)
                            .label
                        }
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-3 font-mono text-[11px] text-slate-400">
                      <span className="flex items-center gap-1 text-cyan-300">
                        <Hash className="h-3 w-3" />
                        SHA-256: {docDetail.sha256_hash}
                      </span>
                    </div>
                  </div>

                  {/* Classification Readout */}
                  <div className="flex flex-wrap items-center gap-3">
                    <div
                      className={`rounded-xl border px-3.5 py-2 ${
                        docDetail.classification.is_certain
                          ? "border-emerald-500/35 bg-emerald-950/20"
                          : "border-amber-500/40 bg-amber-950/25"
                      }`}
                    >
                      <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-slate-400">
                        {docDetail.classification.is_certain ? (
                          <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                        ) : (
                          <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
                        )}
                        <span>Predicted Document Class</span>
                      </div>
                      <div className="mt-0.5 flex items-baseline gap-2">
                        <span className="text-sm font-bold text-white">
                          {docDetail.classification.display_label}
                        </span>
                        <span
                          className={`font-mono text-xs font-semibold ${
                            docDetail.classification.is_certain
                              ? "text-emerald-300"
                              : "text-amber-300"
                          }`}
                        >
                          {(
                            docDetail.classification.confidence * 100
                          ).toFixed(1)}
                          %
                        </span>
                      </div>
                      <div className="mt-0.5 font-mono text-[10px] text-slate-400">
                        {docDetail.classification.status_label}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Matched Classification Signals */}
                {docDetail.classification.signals.length > 0 && (
                  <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-slate-800/80 pt-2.5">
                    <span className="font-mono text-[10px] uppercase text-slate-500">
                      Classification Signals:
                    </span>
                    {docDetail.classification.signals.map((sig, i) => (
                      <span
                        key={i}
                        className="rounded border border-slate-800 bg-[#050811] px-2 py-0.5 font-mono text-[10px] text-slate-300"
                      >
                        {sig}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* 2. Page Navigation Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800/90 bg-[#070B16] p-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={activePageNumber <= 1}
                    onClick={() => handleSelectPage(activePageNumber - 1)}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-300 transition hover:border-cyan-500/40 disabled:opacity-40"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                    <span>Prev</span>
                  </button>

                  <div className="flex items-center gap-1">
                    {docDetail.pages.map((p) => (
                      <button
                        key={p.page_number}
                        type="button"
                        onClick={() => handleSelectPage(p.page_number)}
                        className={`rounded-lg border px-2.5 py-1 font-mono text-xs font-semibold transition ${
                          activePageNumber === p.page_number
                            ? "border-cyan-400 bg-cyan-500/20 text-cyan-300"
                            : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-white"
                        }`}
                      >
                        P{p.page_number}
                      </button>
                    ))}
                  </div>

                  <button
                    type="button"
                    disabled={activePageNumber >= docDetail.page_count}
                    onClick={() => handleSelectPage(activePageNumber + 1)}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-300 transition hover:border-cyan-500/40 disabled:opacity-40"
                  >
                    <span>Next</span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>

                {activePageDetail && (
                  <div className="flex flex-wrap items-center gap-2.5 font-mono text-[11px] text-slate-300">
                    <span
                      className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${
                        getMethodBadge(activePageDetail.extraction_method).style
                      }`}
                    >
                      Page {activePageDetail.page_number}:{" "}
                      {activePageDetail.extraction_method}
                    </span>
                    <span className="text-slate-400">
                      {activePageDetail.width} × {activePageDetail.height}
                    </span>
                    <span className="text-cyan-300">
                      {activePageDetail.layout_regions.length} regions ·{" "}
                      {activePageDetail.tables.length} tables ·{" "}
                      {activePageDetail.entities.length} entities
                    </span>
                  </div>
                )}
              </div>

              {/* 3. Five-Tab Forensic Document Inspector Navigation */}
              <div className="flex flex-wrap gap-2 border-b border-slate-800/80 pb-3">
                <button
                  type="button"
                  onClick={() => setInspectorTab("preview-overlay")}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition ${
                    inspectorTab === "preview-overlay"
                      ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
                      : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Eye className="h-3.5 w-3.5" />
                  <span>Page Preview &amp; Overlays</span>
                </button>

                <button
                  type="button"
                  onClick={() => setInspectorTab("layout-tree")}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition ${
                    inspectorTab === "layout-tree"
                      ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
                      : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <GitBranch className="h-3.5 w-3.5" />
                  <span>Layout Tree ({docDetail.layout_regions.length})</span>
                </button>

                <button
                  type="button"
                  onClick={() => setInspectorTab("tables")}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition ${
                    inspectorTab === "tables"
                      ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
                      : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Table2 className="h-3.5 w-3.5" />
                  <span>Extracted Tables ({docDetail.tables.length})</span>
                </button>

                <button
                  type="button"
                  onClick={() => setInspectorTab("entities")}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition ${
                    inspectorTab === "entities"
                      ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
                      : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Tags className="h-3.5 w-3.5" />
                  <span>Normalized Entities ({docDetail.entities.length})</span>
                </button>

                <button
                  type="button"
                  onClick={() => setInspectorTab("blocks-raw")}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition ${
                    inspectorTab === "blocks-raw"
                      ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
                      : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Layers className="h-3.5 w-3.5" />
                  <span>Raw Text &amp; Font Streams</span>
                </button>
              </div>

              {/* TAB 1: Interactive Page Preview & SVG Bounding-Box Overlays */}
              {inspectorTab === "preview-overlay" && activePageDetail && (
                <div className="space-y-4">
                  {/* Overlay Layer Switcher */}
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-800 bg-[#060A14] px-3.5 py-2.5">
                    <span className="font-mono text-[11px] uppercase text-slate-400">
                      Active Coordinate Overlay Layer:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {(
                        [
                          { id: "layout", label: "Layout Regions" },
                          { id: "tables", label: "Tables & Cells" },
                          { id: "entities", label: "Extracted Entities" },
                          { id: "blocks", label: "Coordinate Blocks" },
                        ] as Array<{ id: OverlayLayerMode; label: string }>
                      ).map((m) => (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => {
                            setOverlayMode(m.id);
                            setSelectedOverlayItem(null);
                          }}
                          className={`rounded-lg border px-2.5 py-1 font-mono text-[11px] font-semibold transition ${
                            overlayMode === m.id
                              ? "border-cyan-400 bg-cyan-500/20 text-cyan-300"
                              : "border-slate-800 bg-slate-900 text-slate-400 hover:text-white"
                          }`}
                        >
                          {m.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
                    {/* Visual Document Canvas with SVG Bounding Box Overlay */}
                    <div className="overflow-hidden rounded-xl border border-slate-800 bg-[#050811] p-3 lg:col-span-7">
                      <div className="relative mx-auto w-full overflow-hidden rounded-lg border border-slate-700/80 bg-slate-950">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={veritasApi.getDocumentPagePreviewUrl(
                            docDetail.id,
                            activePageDetail.page_number
                          )}
                          alt={`Document ${docDetail.filename} Page ${activePageDetail.page_number}`}
                          className="block h-auto w-full select-none"
                        />

                        {activePageDetail.width > 0 &&
                          activePageDetail.height > 0 && (
                            <svg
                              viewBox={`0 0 ${activePageDetail.width} ${activePageDetail.height}`}
                              className="absolute inset-0 h-full w-full"
                            >
                              {overlayItems.map((item) => {
                                const isActive =
                                  selectedOverlayItem?.id === item.id;
                                const bw = Math.max(
                                  2,
                                  item.bbox.x1 - item.bbox.x0
                                );
                                const bh = Math.max(
                                  2,
                                  item.bbox.y1 - item.bbox.y0
                                );
                                return (
                                  <g
                                    key={item.id}
                                    onClick={() => setSelectedOverlayItem(item)}
                                    onMouseEnter={() =>
                                      setSelectedOverlayItem(item)
                                    }
                                    className="cursor-pointer transition-opacity"
                                  >
                                    <rect
                                      x={item.bbox.x0}
                                      y={item.bbox.y0}
                                      width={bw}
                                      height={bh}
                                      fill={
                                        isActive
                                          ? "rgba(6, 182, 212, 0.28)"
                                          : item.fillColor
                                      }
                                      stroke={
                                        isActive ? "#22d3ee" : item.strokeColor
                                      }
                                      strokeWidth={isActive ? 2.5 : 1.4}
                                      rx={2}
                                    />
                                  </g>
                                );
                              })}
                            </svg>
                          )}
                      </div>
                    </div>

                    {/* Right Side Inspector for Selected/Hovered Bounding Box + Layer List */}
                    <div className="flex flex-col space-y-3 lg:col-span-5">
                      <div className="rounded-xl border border-cyan-500/30 bg-[#070B16] p-3.5">
                        <div className="font-mono text-[10px] font-semibold uppercase tracking-wider text-cyan-400">
                          Selected Coordinate Region Telemetry
                        </div>
                        {selectedOverlayItem ? (
                          <div className="mt-2 space-y-2 text-xs">
                            <div className="flex items-center justify-between gap-2">
                              <span
                                className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${selectedOverlayItem.badgeStyle}`}
                              >
                                {selectedOverlayItem.category}
                              </span>
                              <span className="font-mono text-[11px] text-emerald-300">
                                {(selectedOverlayItem.confidence * 100).toFixed(
                                  1
                                )}
                                % conf
                              </span>
                            </div>
                            <p className="font-semibold text-white">
                              {selectedOverlayItem.title}
                            </p>
                            <p className="rounded-lg border border-slate-800 bg-[#050811] p-2 font-mono text-[11px] text-slate-200">
                              {selectedOverlayItem.subtitle}
                            </p>
                            <div className="font-mono text-[10px] text-slate-400">
                              Coordinates: [x0={selectedOverlayItem.bbox.x0}, y0=
                              {selectedOverlayItem.bbox.y0}, x1=
                              {selectedOverlayItem.bbox.x1}, y1=
                              {selectedOverlayItem.bbox.y1}]
                            </div>
                          </div>
                        ) : (
                          <p className="mt-2 text-xs text-slate-400">
                            Hover or click any highlighted bounding box on the
                            document preview (or in the list below) to inspect
                            its coordinates and extracted content.
                          </p>
                        )}
                      </div>

                      <div className="max-h-96 flex-1 space-y-2 overflow-y-auto rounded-xl border border-slate-800 bg-[#060A14] p-3">
                        <div className="font-mono text-[10px] uppercase text-slate-400">
                          Overlay Elements on Page {activePageDetail.page_number}{" "}
                          ({overlayItems.length})
                        </div>
                        {overlayItems.map((item) => {
                          const active = selectedOverlayItem?.id === item.id;
                          return (
                            <button
                              key={item.id}
                              type="button"
                              onClick={() => setSelectedOverlayItem(item)}
                              className={`w-full rounded-lg border p-2.5 text-left text-xs transition ${
                                active
                                  ? "border-cyan-400 bg-cyan-950/30 text-white"
                                  : "border-slate-800/80 bg-[#070B16] text-slate-300 hover:border-slate-700"
                              }`}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span
                                  className={`rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold ${item.badgeStyle}`}
                                >
                                  {item.category}
                                </span>
                                <span className="font-mono text-[10px] text-slate-400">
                                  [{item.bbox.x0}, {item.bbox.y0}]
                                </span>
                              </div>
                              <p className="mt-1 truncate font-medium text-slate-200">
                                {item.title}
                              </p>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: Document Layout Tree (MODULE 2) */}
              {inspectorTab === "layout-tree" && (
                <div className="max-h-[540px] space-y-2.5 overflow-y-auto pr-1">
                  {docDetail.layout_regions.length === 0 ? (
                    <div className="py-12 text-center text-xs text-slate-400">
                      No layout regions detected.
                    </div>
                  ) : (
                    docDetail.layout_regions.map((reg) => {
                      const col = getRegionColors(reg.region_type);
                      const isChild = Boolean(reg.parent_region_id);
                      return (
                        <div
                          key={reg.id}
                          className={`rounded-xl border border-slate-800/80 bg-[#070B16]/90 p-3.5 ${
                            isChild ? "ml-5 border-l-2 border-l-cyan-500/40" : ""
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="rounded bg-slate-900 px-2 py-0.5 font-mono text-[10px] text-slate-400">
                                P{reg.page_number} · Order #{reg.reading_order + 1}
                              </span>
                              <span
                                className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${col.badge}`}
                              >
                                {reg.region_type}
                              </span>
                              <span className="text-xs font-semibold text-white">
                                {reg.label}
                              </span>
                            </div>
                            <span className="font-mono text-[10px] text-slate-400">
                              BBox: [{reg.bounding_box.x0}, {reg.bounding_box.y0},{" "}
                              {reg.bounding_box.x1}, {reg.bounding_box.y1}]
                            </span>
                          </div>
                          <p className="mt-2 whitespace-pre-wrap rounded-lg border border-slate-800/60 bg-[#050811] p-2.5 font-mono text-xs text-slate-200">
                            {reg.text_content}
                          </p>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* TAB 3: Extracted Tables & Cell Coordinates (MODULE 3) */}
              {inspectorTab === "tables" && (
                <div className="space-y-5">
                  {docDetail.tables.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-800 p-12 text-center text-xs text-slate-400">
                      No structured tables detected in this document.
                    </div>
                  ) : (
                    docDetail.tables.map((tbl) => {
                      // Organize cells into 2D grid [row_index][col_index]
                      const grid: Array<Array<(typeof tbl.cells)[0] | null>> =
                        Array.from({ length: tbl.row_count }, () =>
                          Array.from({ length: tbl.column_count }, () => null)
                        );
                      for (const c of tbl.cells) {
                        if (
                          c.row_index >= 0 &&
                          c.row_index < tbl.row_count &&
                          c.col_index >= 0 &&
                          c.col_index < tbl.column_count
                        ) {
                          grid[c.row_index][c.col_index] = c;
                        }
                      }

                      return (
                        <div
                          key={tbl.id}
                          className="overflow-hidden rounded-xl border border-slate-800 bg-[#070B16]"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-[#050811] px-4 py-3">
                            <div className="flex items-center gap-2.5">
                              <Boxes className="h-4 w-4 text-emerald-400" />
                              <span className="font-mono text-xs font-bold text-white">
                                {tbl.table_identifier}
                              </span>
                              <span className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] text-emerald-300">
                                {tbl.row_count} Rows × {tbl.column_count} Columns
                              </span>
                              <span className="font-mono text-[11px] text-slate-400">
                                Page {tbl.page_number}
                              </span>
                            </div>
                            <span className="font-mono text-[10px] text-slate-400">
                              Table BBox: [{tbl.bounding_box.x0},{" "}
                              {tbl.bounding_box.y0}, {tbl.bounding_box.x1},{" "}
                              {tbl.bounding_box.y1}] · Conf:{" "}
                              {(tbl.confidence * 100).toFixed(1)}%
                            </span>
                          </div>

                          <div className="overflow-x-auto">
                            <table className="w-full border-collapse text-left text-xs">
                              <tbody>
                                {grid.map((rowCells, rIdx) => (
                                  <tr
                                    key={rIdx}
                                    className={
                                      rIdx === 0
                                        ? "border-b border-slate-700 bg-slate-900/90 font-semibold text-cyan-300"
                                        : "border-b border-slate-800/70 hover:bg-slate-900/40"
                                    }
                                  >
                                    {rowCells.map((cell, cIdx) => (
                                      <td
                                        key={cIdx}
                                        className="border-r border-slate-800/70 px-3.5 py-2.5 last:border-r-0"
                                      >
                                        <div className="text-slate-100">
                                          {cell?.cell_text || ""}
                                        </div>
                                        {cell && (
                                          <div className="mt-1 font-mono text-[9px] text-slate-500">
                                            [{cell.bounding_box.x0},{" "}
                                            {cell.bounding_box.y0},{" "}
                                            {cell.bounding_box.x1},{" "}
                                            {cell.bounding_box.y1}]
                                          </div>
                                        )}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* TAB 4: Structured & Normalized Entities (MODULE 4) */}
              {inspectorTab === "entities" && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {[
                      "ALL",
                      "PERSON_NAME",
                      "COMPANY_NAME",
                      "INVOICE_NUMBER",
                      "TAX_IDENTIFIER",
                      "DATE",
                      "MONETARY_AMOUNT",
                      "ACCOUNT_REFERENCE",
                      "ADDRESS",
                    ].map((et) => (
                      <button
                        key={et}
                        type="button"
                        onClick={() => setEntityFilter(et)}
                        className={`rounded-lg border px-2.5 py-1 font-mono text-[10px] font-semibold transition ${
                          entityFilter === et
                            ? "border-cyan-400 bg-cyan-500/20 text-cyan-300"
                            : "border-slate-800 bg-slate-900 text-slate-400 hover:text-white"
                        }`}
                      >
                        {et.replace(/_/g, " ")}
                      </button>
                    ))}
                  </div>

                  {filteredEntities.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-800 p-12 text-center text-xs text-slate-400">
                      No entities matched the selected filter.
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-xl border border-slate-800">
                      <table className="w-full text-left text-xs">
                        <thead className="border-b border-slate-800 bg-[#070B16] font-mono text-[10px] uppercase tracking-wider text-slate-400">
                          <tr>
                            <th className="px-4 py-3">Entity Type</th>
                            <th className="px-4 py-3">Raw Extracted Value</th>
                            <th className="px-4 py-3">Normalized Value</th>
                            <th className="px-4 py-3">Page</th>
                            <th className="px-4 py-3">Coordinates</th>
                            <th className="px-4 py-3">Confidence</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/70 bg-[#050811]/70">
                          {filteredEntities.map((ent) => (
                            <tr
                              key={ent.id}
                              className="transition hover:bg-slate-900/60"
                            >
                              <td className="whitespace-nowrap px-4 py-3">
                                <span
                                  className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getEntityBadgeStyle(
                                    ent.entity_type
                                  )}`}
                                >
                                  {ent.entity_type}
                                </span>
                              </td>
                              <td className="px-4 py-3 font-mono text-slate-300">
                                {ent.raw_value}
                              </td>
                              <td className="px-4 py-3 font-mono font-semibold text-white">
                                {ent.normalized_value}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 font-mono text-cyan-300">
                                Page {ent.page_number}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 font-mono text-[10px] text-slate-400">
                                [{ent.bounding_box.x0}, {ent.bounding_box.y0},{" "}
                                {ent.bounding_box.x1}, {ent.bounding_box.y1}]
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 font-mono text-emerald-300">
                                {(ent.confidence * 100).toFixed(1)}%
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 5: Raw Page Text & Font Stream Telemetry (Phase 2A Preserved) */}
              {inspectorTab === "blocks-raw" && activePageDetail && (
                <div className="space-y-4">
                  <div className="rounded-xl border border-slate-800 bg-[#050811] p-4">
                    <div className="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-wider text-slate-400">
                      <span className="flex items-center gap-1.5">
                        <Type className="h-3.5 w-3.5 text-cyan-400" />
                        <span>
                          Page {activePageDetail.page_number} Extracted Text (
                          {activePageDetail.char_count} chars)
                        </span>
                      </span>
                      <span>{activePageDetail.extraction_method}</span>
                    </div>
                    <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-200">
                      {activePageDetail.raw_text ||
                        "(No text extracted on this page)"}
                    </pre>
                  </div>

                  {activePageDetail.fonts.length > 0 && (
                    <div className="rounded-xl border border-slate-800 bg-[#070B16] p-4">
                      <div className="mb-3 flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-blue-300">
                        <Cpu className="h-4 w-4" />
                        <span>
                          Native PDF Font Stream Telemetry (Page{" "}
                          {activePageDetail.page_number})
                        </span>
                      </div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                        {activePageDetail.fonts.map((f, idx) => (
                          <div
                            key={`${f.font_name}-${f.font_size}-${idx}`}
                            className="flex items-center justify-between rounded-lg border border-slate-800 bg-[#050811] px-3 py-2 font-mono text-xs"
                          >
                            <span className="truncate text-slate-200">
                              {f.font_name} ({f.font_size}pt)
                            </span>
                            <span className="text-cyan-300">
                              {f.span_count} span{f.span_count !== 1 ? "s" : ""}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {docDetail.structured_fields.length > 0 && (
                    <div className="rounded-xl border border-slate-800 bg-[#070B16] p-4">
                      <div className="mb-3 flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-cyan-300">
                        <FileCode2 className="h-4 w-4" />
                        <span>
                          Phase 2A Key-Value Extraction Records (
                          {docDetail.structured_fields.length})
                        </span>
                      </div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {docDetail.structured_fields.map((sf) => (
                          <div
                            key={sf.id}
                            className="rounded-lg border border-slate-800 bg-[#050811] p-2.5 text-xs"
                          >
                            <div className="flex items-center justify-between font-mono text-[10px]">
                              <span className="font-semibold text-cyan-300">
                                {sf.field_name}
                              </span>
                              <span className="text-slate-400">
                                P{sf.page_number} · [{sf.bounding_box.x0},{" "}
                                {sf.bounding_box.y0}]
                              </span>
                            </div>
                            <p className="mt-1 font-medium text-white">
                              {sf.field_value}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Compliance Footer */}
              <div className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-[#060A14] px-4 py-2.5 text-[11px] text-slate-400">
                <span className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-cyan-400" />
                  <span>
                    Phase 2B Governance: Document classifications are automated
                    probabilistic signals and are not treated as verified facts.
                  </span>
                </span>
                <span className="font-mono text-[10px] text-slate-500">
                  Original coordinates preserved
                </span>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
