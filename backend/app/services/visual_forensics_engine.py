import hashlib
import io
import json
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageChops, ImageEnhance
from app.core.config import settings
from app.models.entities import (
    ForensicArtifactType,
    ForensicFindingSeverity,
    ForensicModuleName,
    ForensicReviewStatus,
)
from app.services.extraction_engine import _run_visual_ocr_on_image_bytes

MODULE_DISPLAY_NAMES: Dict[str, str] = {
    ForensicModuleName.MODULE_A_IMAGE_CONSISTENCY.value: "Module A — Image Consistency & Local Noise Analysis",
    ForensicModuleName.MODULE_B_ELA.value: "Module B — Error Level Analysis (ELA)",
    ForensicModuleName.MODULE_C_TYPOGRAPHY.value: "Module C — Typography & Font Geometry Consistency",
    ForensicModuleName.MODULE_D_ALIGNMENT.value: "Module D — Spatial Alignment & Table Rail Analysis",
    ForensicModuleName.MODULE_E_PDF_METADATA.value: "Module E — PDF Metadata & Object Stream Inspection",
    ForensicModuleName.MODULE_F_SIGNATURE_STAMP.value: "Module F — Signature & Stamp Region Forensics",
    ForensicModuleName.MODULE_G_TEXT_VISUAL.value: "Module G — Text-to-Visual & Cross-Stream Consistency",
}


@dataclass
class GeneratedForensicArtifact:
    artifact_id: str
    page_number: int
    artifact_type: str
    module_name: str
    title: str
    description: str
    mime_type: str
    png_bytes: bytes
    sha256_hash: str
    is_derived_from_pdf_render: bool
    parameters: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedForensicFinding:
    finding_id: str
    module_name: str
    finding_category: str
    severity: str
    title: str
    observation: str
    technical_explanation: str
    possible_benign_explanations: List[str]
    confidence_score: float
    confidence_interpretation: str
    limitations: str
    page_number: int
    bounding_box: Optional[Dict[str, float]]
    evidence_reference: str
    artifact_id: Optional[str]
    analysis_parameters: Dict[str, Any]
    evidence_metrics: Dict[str, Any]
    recommended_human_action: str


@dataclass
class ModuleExecutionRecord:
    module_name: str
    display_name: str
    status: str
    findings_count: int
    duration_ms: float
    methodology_summary: str
    limitations_note: str


@dataclass
class VisualForensicsRunResult:
    modules_executed: List[str]
    module_summaries: List[ModuleExecutionRecord]
    metadata_inspection: Dict[str, Any]
    artifacts: List[GeneratedForensicArtifact]
    findings: List[GeneratedForensicFinding]
    processing_duration_ms: float


def _cap_image_dimensions(pil_img: Image.Image, max_dim: int) -> Tuple[Image.Image, float]:
    """Caps raster image dimensions for bounded memory usage while returning scale factor."""
    w, h = pil_img.size
    largest = max(w, h)
    if largest <= max_dim or max_dim <= 0:
        return pil_img, 1.0
    scale = max_dim / float(largest)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS), scale


def _normalize_font_family(font_name: str) -> str:
    """Strips 6-letter PDF subset prefix (e.g., ABCDEF+Helvetica-Bold -> HELVETICA)."""
    cleaned = font_name.strip()
    if "+" in cleaned and len(cleaned.split("+", 1)[0]) == 6:
        cleaned = cleaned.split("+", 1)[1]
    base = re.split(r"[\-,_]", cleaned)[0].strip().upper()
    if base in ("HELV", "HELVETICA", "ARIAL", "SWISS"):
        return "SANS_HELVETICA"
    if base in ("TIMO", "TIMES", "TIMESNEWROMAN", "TIRO"):
        return "SERIF_TIMES"
    if base in ("COUR", "COURIER", "COURIERNEW"):
        return "MONO_COURIER"
    return base or "UNKNOWN"


def _bbox_iou_or_overlap(b1: Dict[str, float], b2: Dict[str, float]) -> float:
    x_left = max(float(b1.get("x0", 0.0)), float(b2.get("x0", 0.0)))
    y_top = max(float(b1.get("y0", 0.0)), float(b2.get("y0", 0.0)))
    x_right = min(float(b1.get("x1", 0.0)), float(b2.get("x1", 0.0)))
    y_bottom = min(float(b1.get("y1", 0.0)), float(b2.get("y1", 0.0)))
    if x_right <= x_left or y_bottom <= y_top:
        return 0.0
    inter = (x_right - x_left) * (y_bottom - y_top)
    a1 = max(1.0, (float(b1.get("x1", 0.0)) - float(b1.get("x0", 0.0))) * (float(b1.get("y1", 0.0)) - float(b1.get("y0", 0.0))))
    a2 = max(1.0, (float(b2.get("x1", 0.0)) - float(b2.get("x0", 0.0))) * (float(b2.get("y1", 0.0)) - float(b2.get("y0", 0.0))))
    return inter / min(a1, a2)


class VisualForensicsEngine:
    """
    VERITAS AI Phase 3 — Explainable Visual Forensics & Document Authenticity Signal Engine.
    Implements Modules A through G using OpenCV, Pillow, and PyMuPDF.
    Strictly adheres to forensic neutrality: every finding reports an observed technical signal,
    technical explanation, possible benign explanations, confidence interpretation, limitations,
    exact page/bounding-box coordinates, and recommended human verification.
    """

    @staticmethod
    def analyze_document(
        document_id: str,
        file_bytes: bytes,
        file_type: str,
        filename: str,
        document_sha256: str,
        pages_db_data: List[Dict[str, Any]],
        layout_regions_db: List[Dict[str, Any]],
        tables_db: List[Dict[str, Any]],
        entities_db: List[Dict[str, Any]],
        ela_jpeg_quality: int = 90,
        ela_amplification_scale: float = 18.0,
    ) -> VisualForensicsRunResult:
        t_start = time.perf_counter()
        norm_type = file_type.upper().lstrip(".")
        is_pdf = norm_type == "PDF"

        artifacts: List[GeneratedForensicArtifact] = []
        findings: List[GeneratedForensicFinding] = []
        module_summaries: List[ModuleExecutionRecord] = []
        modules_executed: List[str] = []

        # Prepare page images and page dimensions for analysis
        # For PDFs: render pages at 150 DPI for visual analysis while preserving PDF coordinate mapping
        page_renders: Dict[int, Tuple[Image.Image, float, float]] = {}
        pdf_doc: Optional[fitz.Document] = None

        try:
            if is_pdf:
                pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                for idx in range(len(pdf_doc)):
                    pg_num = idx + 1
                    page = pdf_doc[idx]
                    pw, ph = float(page.rect.width), float(page.rect.height)
                    pix = page.get_pixmap(dpi=150, alpha=False)
                    pil_img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    pil_img, _ = _cap_image_dimensions(
                        pil_img, settings.forensics_max_image_dimension
                    )
                    page_renders[pg_num] = (pil_img, round(pw, 2), round(ph, 2))
            else:
                with Image.open(io.BytesIO(file_bytes)) as raw_pil:
                    rgb_img = raw_pil.convert("RGB")
                    orig_w, orig_h = float(rgb_img.width), float(rgb_img.height)
                    capped_img, _ = _cap_image_dimensions(
                        rgb_img, settings.forensics_max_image_dimension
                    )
                    page_renders[1] = (capped_img, round(orig_w, 2), round(orig_h, 2))

            # =========================================================================
            # MODULE E — PDF Metadata and Object Inspection
            # =========================================================================
            m_e_start = time.perf_counter()
            meta_inspection, mod_e_findings = (
                VisualForensicsEngine._run_module_e_metadata_inspection(
                    document_id=document_id,
                    file_bytes=file_bytes,
                    norm_type=norm_type,
                    is_pdf=is_pdf,
                    pdf_doc=pdf_doc,
                )
            )
            m_e_dur = round((time.perf_counter() - m_e_start) * 1000, 2)
            findings.extend(mod_e_findings)
            modules_executed.append(ForensicModuleName.MODULE_E_PDF_METADATA.value)
            module_summaries.append(
                ModuleExecutionRecord(
                    module_name=ForensicModuleName.MODULE_E_PDF_METADATA.value,
                    display_name=MODULE_DISPLAY_NAMES[
                        ForensicModuleName.MODULE_E_PDF_METADATA.value
                    ],
                    status="COMPLETED",
                    findings_count=len(mod_e_findings),
                    duration_ms=m_e_dur,
                    methodology_summary=(
                        "Inspected PDF document info dictionary, XRef table objects, embedded XObject raster streams, "
                        "font resource descriptors, annotation dictionaries, and trailer %%EOF markers."
                        if is_pdf
                        else "Inspected raster image container headers, color mode, resolution metadata, and quantization tables."
                    ),
                    limitations_note=(
                        "Metadata timestamps and producer strings reflect the software that last saved the file "
                        "and cannot independently prove or disprove document authenticity."
                    ),
                )
            )

            # =========================================================================
            # MODULE A — Image Consistency Analysis
            # =========================================================================
            m_a_start = time.perf_counter()
            mod_a_artifacts, mod_a_findings = (
                VisualForensicsEngine._run_module_a_image_consistency(
                    document_id=document_id,
                    document_sha256=document_sha256,
                    is_pdf=is_pdf,
                    pdf_doc=pdf_doc,
                    page_renders=page_renders,
                )
            )
            m_a_dur = round((time.perf_counter() - m_a_start) * 1000, 2)
            artifacts.extend(mod_a_artifacts)
            findings.extend(mod_a_findings)
            modules_executed.append(ForensicModuleName.MODULE_A_IMAGE_CONSISTENCY.value)
            module_summaries.append(
                ModuleExecutionRecord(
                    module_name=ForensicModuleName.MODULE_A_IMAGE_CONSISTENCY.value,
                    display_name=MODULE_DISPLAY_NAMES[
                        ForensicModuleName.MODULE_A_IMAGE_CONSISTENCY.value
                    ],
                    status="COMPLETED",
                    findings_count=len(mod_a_findings),
                    duration_ms=m_a_dur,
                    methodology_summary=(
                        "Evaluated spatial Laplacian high-frequency variance, local background luminance uniformity, "
                        "and rectangular patch boundary step-edges across 32x32 pixel grid regions."
                    ),
                    limitations_note=(
                        "Localized luminance or variance differences can arise from legitimate form boxes, shaded table headers, "
                        "embedded corporate logos, or scanner illumination gradients."
                    ),
                )
            )

            # =========================================================================
            # MODULE B — Error Level Analysis (ELA)
            # =========================================================================
            m_b_start = time.perf_counter()
            mod_b_artifacts, mod_b_findings = VisualForensicsEngine._run_module_b_ela(
                document_id=document_id,
                document_sha256=document_sha256,
                file_bytes=file_bytes,
                norm_type=norm_type,
                is_pdf=is_pdf,
                page_renders=page_renders,
                jpeg_quality=ela_jpeg_quality,
                amplification_scale=ela_amplification_scale,
            )
            m_b_dur = round((time.perf_counter() - m_b_start) * 1000, 2)
            artifacts.extend(mod_b_artifacts)
            findings.extend(mod_b_findings)
            modules_executed.append(ForensicModuleName.MODULE_B_ELA.value)
            module_summaries.append(
                ModuleExecutionRecord(
                    module_name=ForensicModuleName.MODULE_B_ELA.value,
                    display_name=MODULE_DISPLAY_NAMES[ForensicModuleName.MODULE_B_ELA.value],
                    status="COMPLETED",
                    findings_count=len(mod_b_findings),
                    duration_ms=m_b_dur,
                    methodology_summary=(
                        f"Generated separate derived recompression residual map at Q={ela_jpeg_quality} "
                        f"(amplification={ela_amplification_scale}x) without modifying the original source file."
                    ),
                    limitations_note=(
                        "ELA is native only to lossy JPEG images. For PDFs, ELA operates on derived rendered page images "
                        "and reflects rendering/embedded-image contrast rather than original camera JPEG quantization."
                    ),
                )
            )

            # =========================================================================
            # MODULE C — Typography Consistency Analysis
            # =========================================================================
            m_c_start = time.perf_counter()
            mod_c_findings = VisualForensicsEngine._run_module_c_typography(
                document_id=document_id,
                is_pdf=is_pdf,
                pdf_doc=pdf_doc,
                pages_db_data=pages_db_data,
                page_renders=page_renders,
            )
            m_c_dur = round((time.perf_counter() - m_c_start) * 1000, 2)
            findings.extend(mod_c_findings)
            modules_executed.append(ForensicModuleName.MODULE_C_TYPOGRAPHY.value)
            module_summaries.append(
                ModuleExecutionRecord(
                    module_name=ForensicModuleName.MODULE_C_TYPOGRAPHY.value,
                    display_name=MODULE_DISPLAY_NAMES[
                        ForensicModuleName.MODULE_C_TYPOGRAPHY.value
                    ],
                    status="COMPLETED",
                    findings_count=len(mod_c_findings),
                    duration_ms=m_c_dur,
                    methodology_summary=(
                        "Compared PyMuPDF span-level font families, point sizes, and horizontal baseline origins "
                        "within structurally comparable lines, key-value pairs, and table columns."
                        if is_pdf
                        else "Analyzed OCR text bounding-box vertical height consistency and stroke contrast across comparable lines."
                    ),
                    limitations_note=(
                        "Templates often intentionally style monetary totals, headers, or reference codes in distinct "
                        "fonts or sizes for visual emphasis."
                    ),
                )
            )

            # =========================================================================
            # MODULE D — Alignment and Spatial Analysis
            # =========================================================================
            m_d_start = time.perf_counter()
            mod_d_findings = VisualForensicsEngine._run_module_d_alignment(
                document_id=document_id,
                is_pdf=is_pdf,
                pdf_doc=pdf_doc,
                layout_regions_db=layout_regions_db,
                tables_db=tables_db,
                page_renders=page_renders,
            )
            m_d_dur = round((time.perf_counter() - m_d_start) * 1000, 2)
            findings.extend(mod_d_findings)
            modules_executed.append(ForensicModuleName.MODULE_D_ALIGNMENT.value)
            module_summaries.append(
                ModuleExecutionRecord(
                    module_name=ForensicModuleName.MODULE_D_ALIGNMENT.value,
                    display_name=MODULE_DISPLAY_NAMES[
                        ForensicModuleName.MODULE_D_ALIGNMENT.value
                    ],
                    status="COMPLETED",
                    findings_count=len(mod_d_findings),
                    duration_ms=m_d_dur,
                    methodology_summary=(
                        "Evaluated left-margin column rail alignment across stacked layout blocks, intra-line baseline "
                        "horizontal alignment, and table cell column/row alignment."
                    ),
                    limitations_note=(
                        "Minor coordinate offsets can result from manual tab spacing in word processors, OCR bounding-box "
                        "padding on skewed scans, or multi-column form templates."
                    ),
                )
            )

            # =========================================================================
            # MODULE F — Signature and Stamp Region Analysis
            # =========================================================================
            m_f_start = time.perf_counter()
            mod_f_artifacts, mod_f_findings = (
                VisualForensicsEngine._run_module_f_signature_and_stamp(
                    document_id=document_id,
                    document_sha256=document_sha256,
                    is_pdf=is_pdf,
                    pdf_doc=pdf_doc,
                    layout_regions_db=layout_regions_db,
                    page_renders=page_renders,
                )
            )
            m_f_dur = round((time.perf_counter() - m_f_start) * 1000, 2)
            artifacts.extend(mod_f_artifacts)
            findings.extend(mod_f_findings)
            modules_executed.append(ForensicModuleName.MODULE_F_SIGNATURE_STAMP.value)
            module_summaries.append(
                ModuleExecutionRecord(
                    module_name=ForensicModuleName.MODULE_F_SIGNATURE_STAMP.value,
                    display_name=MODULE_DISPLAY_NAMES[
                        ForensicModuleName.MODULE_F_SIGNATURE_STAMP.value
                    ],
                    status="COMPLETED",
                    findings_count=len(mod_f_findings),
                    duration_ms=m_f_dur,
                    methodology_summary=(
                        "Inspected Phase 2B SIGNATURE_REGION and STAMP_REGION blocks for vector vs. raster composition, "
                        "local background luminance contrast, and rectangular patch boundary transitions."
                    ),
                    limitations_note=(
                        "Visual inspection of signature or stamp regions cannot verify the identity of the signer "
                        "or the legal validity of the authorization."
                    ),
                )
            )

            # =========================================================================
            # MODULE G — Text-to-Visual Consistency
            # =========================================================================
            m_g_start = time.perf_counter()
            mod_g_findings = VisualForensicsEngine._run_module_g_text_to_visual(
                document_id=document_id,
                is_pdf=is_pdf,
                pdf_doc=pdf_doc,
                pages_db_data=pages_db_data,
                tables_db=tables_db,
                entities_db=entities_db,
                page_renders=page_renders,
            )
            m_g_dur = round((time.perf_counter() - m_g_start) * 1000, 2)
            findings.extend(mod_g_findings)
            modules_executed.append(ForensicModuleName.MODULE_G_TEXT_VISUAL.value)
            module_summaries.append(
                ModuleExecutionRecord(
                    module_name=ForensicModuleName.MODULE_G_TEXT_VISUAL.value,
                    display_name=MODULE_DISPLAY_NAMES[
                        ForensicModuleName.MODULE_G_TEXT_VISUAL.value
                    ],
                    status="COMPLETED",
                    findings_count=len(mod_g_findings),
                    duration_ms=m_g_dur,
                    methodology_summary=(
                        "Cross-checked native PDF text streams against Visual OCR run on rendered page images, "
                        "inspected text-background luminance contrast for occluded/masked text, and verified OCR confidence."
                    ),
                    limitations_note=(
                        "OCR-to-native differences on stylized fonts, stamps, or small footnotes can occur due to "
                        "normal optical character recognition errors rather than stream manipulation."
                    ),
                )
            )

        finally:
            if pdf_doc is not None:
                pdf_doc.close()

        total_dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
        return VisualForensicsRunResult(
            modules_executed=modules_executed,
            module_summaries=module_summaries,
            metadata_inspection=meta_inspection,
            artifacts=artifacts,
            findings=findings,
            processing_duration_ms=total_dur_ms,
        )

    # =========================================================================
    # MODULE E IMPLEMENTATION: PDF METADATA & OBJECT INSPECTION
    # =========================================================================
    @staticmethod
    def _run_module_e_metadata_inspection(
        document_id: str,
        file_bytes: bytes,
        norm_type: str,
        is_pdf: bool,
        pdf_doc: Optional[fitz.Document],
    ) -> Tuple[Dict[str, Any], List[GeneratedForensicFinding]]:
        findings: List[GeneratedForensicFinding] = []

        if not is_pdf or pdf_doc is None:
            # Raster image header inspection
            raster_info: Dict[str, Any] = {}
            with Image.open(io.BytesIO(file_bytes)) as im:
                raster_info["format"] = str(im.format or norm_type)
                raster_info["mode"] = str(im.mode)
                raster_info["width"] = int(im.width)
                raster_info["height"] = int(im.height)
                dpi = im.info.get("dpi")
                if dpi:
                    raster_info["dpi"] = [float(dpi[0]), float(dpi[1])]
                raster_info["has_quantization_tables"] = hasattr(im, "quantization") and bool(
                    getattr(im, "quantization", None)
                )
                exif_data = im.getexif() if hasattr(im, "getexif") else None
                raster_info["exif_tag_count"] = len(exif_data) if exif_data else 0

            meta_dict = {
                "source_format": norm_type,
                "is_pdf": False,
                "creator": "",
                "producer": "",
                "creation_date_raw": "",
                "modification_date_raw": "",
                "title": "",
                "author": "",
                "subject": "",
                "keywords": "",
                "pdf_version": "",
                "is_encrypted": False,
                "incremental_save_eof_count": 0,
                "xref_object_count": 0,
                "page_dimensions": [
                    {
                        "page_number": 1,
                        "width": float(raster_info.get("width", 0)),
                        "height": float(raster_info.get("height", 0)),
                        "rotation": 0,
                    }
                ],
                "embedded_images": [],
                "font_resources": [],
                "annotations": [],
                "raster_header_info": raster_info,
            }

            findings.append(
                GeneratedForensicFinding(
                    finding_id=str(uuid.uuid4()),
                    module_name=ForensicModuleName.MODULE_E_PDF_METADATA.value,
                    finding_category="RASTER_CONTAINER_PROPERTIES",
                    severity=ForensicFindingSeverity.INFORMATIONAL.value,
                    title=f"Standalone Raster Image Container ({norm_type}, {raster_info.get('width')}x{raster_info.get('height')} px)",
                    observation=(
                        f"Uploaded file is a standalone {norm_type} raster image "
                        f"({raster_info.get('width')}x{raster_info.get('height')} px, color mode {raster_info.get('mode')}, "
                        f"EXIF tags: {raster_info.get('exif_tag_count', 0)}). PDF object-tree inspection is not applicable."
                    ),
                    technical_explanation=(
                        "Standalone raster files (PNG/JPEG) store pixel arrays and optional image header tags rather than "
                        "PDF XRef object streams, vector font resources, or incremental trailer updates."
                    ),
                    possible_benign_explanations=[
                        "Document was captured via scanner, mobile camera, or image export pipeline.",
                        "EXIF metadata is routinely stripped by enterprise document scanners and messaging gateways for privacy.",
                    ],
                    confidence_score=0.99,
                    confidence_interpretation="Deterministic container header inspection (High technical reliability).",
                    limitations="Container headers do not record full prior editing history if re-saved cleanly.",
                    page_number=1,
                    bounding_box=None,
                    evidence_reference=f"doc:{document_id}#container:{norm_type}",
                    artifact_id=None,
                    analysis_parameters={"inspector": "Pillow Header & EXIF Parser"},
                    evidence_metrics=raster_info,
                    recommended_human_action="No action required for container format alone; review visual consistency and OCR extraction.",
                )
            )
            return meta_dict, findings

        # Native / Scanned PDF inspection via PyMuPDF
        raw_meta = pdf_doc.metadata or {}
        creator = str(raw_meta.get("creator") or "").strip()
        producer = str(raw_meta.get("producer") or "").strip()
        c_date = str(raw_meta.get("creationDate") or "").strip()
        m_date = str(raw_meta.get("modDate") or "").strip()
        title = str(raw_meta.get("title") or "").strip()
        author = str(raw_meta.get("author") or "").strip()
        subject = str(raw_meta.get("subject") or "").strip()
        keywords = str(raw_meta.get("keywords") or "").strip()
        pdf_format = str(raw_meta.get("format") or "PDF").strip()

        eof_count = len(re.findall(rb"%%EOF", file_bytes))
        xref_len = int(pdf_doc.xref_length())

        page_dims: List[Dict[str, Any]] = []
        embedded_images: List[Dict[str, Any]] = []
        font_resources: List[Dict[str, Any]] = []
        annotations: List[Dict[str, Any]] = []

        for idx in range(len(pdf_doc)):
            pg_num = idx + 1
            page = pdf_doc[idx]
            page_dims.append(
                {
                    "page_number": pg_num,
                    "width": round(float(page.rect.width), 2),
                    "height": round(float(page.rect.height), 2),
                    "rotation": int(page.rotation),
                }
            )

            for img_tuple in page.get_images(full=True):
                # (xref, smask, width, height, bpc, colorspace, alt_colorspace, name, filter, referencer)
                embedded_images.append(
                    {
                        "page_number": pg_num,
                        "xref": int(img_tuple[0]),
                        "width": int(img_tuple[2]),
                        "height": int(img_tuple[3]),
                        "bits_per_component": int(img_tuple[4]),
                        "colorspace": str(img_tuple[5] or ""),
                        "compression_filter": str(img_tuple[8] or ""),
                        "name": str(img_tuple[7] or ""),
                    }
                )

            for f_tuple in page.get_fonts(full=True):
                # (xref, ext, type, basefont, name, encoding, referencer)
                basefont = str(f_tuple[3] or "")
                is_subset = bool(re.match(r"^[A-Z]{6}\+", basefont))
                font_resources.append(
                    {
                        "page_number": pg_num,
                        "xref": int(f_tuple[0]),
                        "font_name": basefont,
                        "font_type": str(f_tuple[2] or ""),
                        "encoding": str(f_tuple[5] or ""),
                        "is_subset": is_subset,
                    }
                )

            annots = page.annots()
            if annots:
                for annot in annots:
                    r = annot.rect
                    info = annot.info or {}
                    annotations.append(
                        {
                            "page_number": pg_num,
                            "annot_type": str(annot.type[1] if annot.type else "Unknown"),
                            "rect": [
                                round(float(r.x0), 2),
                                round(float(r.y0), 2),
                                round(float(r.x1), 2),
                                round(float(r.y1), 2),
                            ],
                            "content": str(info.get("content") or ""),
                            "author": str(info.get("title") or ""),
                        }
                    )

        meta_dict = {
            "source_format": "PDF",
            "is_pdf": True,
            "creator": creator,
            "producer": producer,
            "creation_date_raw": c_date,
            "modification_date_raw": m_date,
            "title": title,
            "author": author,
            "subject": subject,
            "keywords": keywords,
            "pdf_version": pdf_format,
            "is_encrypted": bool(pdf_doc.is_encrypted),
            "incremental_save_eof_count": eof_count,
            "xref_object_count": xref_len,
            "page_dimensions": page_dims,
            "embedded_images": embedded_images,
            "font_resources": font_resources,
            "annotations": annotations,
            "raster_header_info": {},
        }

        # Check 1: Modification timestamp different from Creation timestamp OR multiple %%EOF incremental saves
        if (c_date and m_date and c_date != m_date) or eof_count > 1:
            sev = (
                ForensicFindingSeverity.MEDIUM.value
                if (c_date and m_date and c_date != m_date and eof_count > 1)
                else ForensicFindingSeverity.LOW.value
            )
            findings.append(
                GeneratedForensicFinding(
                    finding_id=str(uuid.uuid4()),
                    module_name=ForensicModuleName.MODULE_E_PDF_METADATA.value,
                    finding_category="PDF_MODIFICATION_OR_INCREMENTAL_SAVE",
                    severity=sev,
                    title="PDF Modification Timestamp Delta / Incremental Trailer Marker Observed",
                    observation=(
                        f"PDF metadata records creationDate='{c_date or 'N/A'}' and modDate='{m_date or 'N/A'}' "
                        f"(Creator: '{creator or 'Unspecified'}', Producer: '{producer or 'Unspecified'}') "
                        f"with {eof_count} trailer %%EOF marker(s) across {xref_len} XRef objects."
                    ),
                    technical_explanation=(
                        "When a PDF document is modified and saved after initial generation, PDF writers either update "
                        "the Info dictionary modDate field or append an incremental XRef section terminated by an additional %%EOF marker."
                    ),
                    possible_benign_explanations=[
                        "Routine enterprise workflow steps such as applying a digital archival stamp, Bates numbering, or PDF/A linearizer optimization.",
                        "Saving a PDF copy from a browser viewer or document management system without altering substantive content.",
                        "Automated email gateway or print-spooler normalization.",
                    ],
                    confidence_score=0.96,
                    confidence_interpretation="Direct deterministic read of PDF Info dictionary and byte-stream %%EOF markers.",
                    limitations="PDF metadata timestamps depend on the system clock of the generating software and do not indicate which objects changed.",
                    page_number=1,
                    bounding_box=None,
                    evidence_reference=f"doc:{document_id}#pdf_info:creationDate={c_date}|modDate={m_date}|eof={eof_count}",
                    artifact_id=None,
                    analysis_parameters={"inspector": "PyMuPDF XRef & Info Dictionary Inspector"},
                    evidence_metrics={
                        "creation_date": c_date,
                        "modification_date": m_date,
                        "creator": creator,
                        "producer": producer,
                        "eof_count": eof_count,
                        "xref_object_count": xref_len,
                    },
                    recommended_human_action=(
                        "Correlate the PDF modification timestamp against the stated document issue date and check whether "
                        "visual or typographic anomalies appear on specific fields."
                    ),
                )
            )
        else:
            findings.append(
                GeneratedForensicFinding(
                    finding_id=str(uuid.uuid4()),
                    module_name=ForensicModuleName.MODULE_E_PDF_METADATA.value,
                    finding_category="PDF_METADATA_BASELINE",
                    severity=ForensicFindingSeverity.INFORMATIONAL.value,
                    title=f"PDF Object Stream & Producer Profile ({producer or 'Standard PDF Library'})",
                    observation=(
                        f"Inspected {xref_len} PDF XRef objects, {len(font_resources)} font resource entries, "
                        f"{len(embedded_images)} embedded image XObjects, and {len(annotations)} annotations. "
                        f"Producer='{producer or 'Unspecified'}', CreationDate='{c_date or 'Unspecified'}'."
                    ),
                    technical_explanation=(
                        "Single-pass PDF generation writes a single %%EOF trailer and consistent creation/modification metadata."
                    ),
                    possible_benign_explanations=[
                        "Standard single-pass PDF export from billing, ERP, or reporting software."
                    ],
                    confidence_score=0.98,
                    confidence_interpretation="Deterministic PDF header and XRef table inspection.",
                    limitations="A cleanly regenerated PDF created from an edited source file will also exhibit a single %%EOF trailer.",
                    page_number=1,
                    bounding_box=None,
                    evidence_reference=f"doc:{document_id}#pdf_xref:{xref_len}",
                    artifact_id=None,
                    analysis_parameters={"inspector": "PyMuPDF XRef & Info Dictionary Inspector"},
                    evidence_metrics={
                        "producer": producer,
                        "creator": creator,
                        "creation_date": c_date,
                        "modification_date": m_date,
                        "eof_count": eof_count,
                        "embedded_images_count": len(embedded_images),
                        "font_resources_count": len(font_resources),
                    },
                    recommended_human_action="Review embedded image and font resource tables if hybrid raster/vector composition is unexpected.",
                )
            )

        # Check 2: Annotations or embedded raster images in a native text PDF
        if annotations:
            first_annot = annotations[0]
            r = first_annot["rect"]
            pw = page_dims[first_annot["page_number"] - 1]["width"]
            ph = page_dims[first_annot["page_number"] - 1]["height"]
            findings.append(
                GeneratedForensicFinding(
                    finding_id=str(uuid.uuid4()),
                    module_name=ForensicModuleName.MODULE_E_PDF_METADATA.value,
                    finding_category="PDF_ANNOTATION_LAYER_PRESENT",
                    severity=ForensicFindingSeverity.MEDIUM.value,
                    title=f"PDF Annotation Object Layer Detected ({len(annotations)} annotation(s))",
                    observation=(
                        f"Detected {len(annotations)} PDF annotation object(s) on page {first_annot['page_number']} "
                        f"(type: {first_annot['annot_type']}, rect: {r})."
                    ),
                    technical_explanation=(
                        "PDF annotations exist in a separate presentation layer above the base page content stream and can "
                        "visually overlay or mask underlying page text."
                    ),
                    possible_benign_explanations=[
                        "Legitimate reviewer comments, approval stamps, or fillable form widgets.",
                        "Hyperlink bounding boxes added by document authoring tools.",
                    ],
                    confidence_score=0.95,
                    confidence_interpretation="Direct enumeration of page /Annots dictionary objects.",
                    limitations="Presence of an annotation object does not by itself indicate malicious masking.",
                    page_number=first_annot["page_number"],
                    bounding_box={
                        "x0": r[0],
                        "y0": r[1],
                        "x1": r[2],
                        "y1": r[3],
                        "page_width": pw,
                        "page_height": ph,
                    },
                    evidence_reference=f"doc:{document_id}#page:{first_annot['page_number']}@annot:{first_annot['annot_type']}",
                    artifact_id=None,
                    analysis_parameters={"inspector": "PyMuPDF Page Annotation Inspector"},
                    evidence_metrics={"annotations": annotations},
                    recommended_human_action="Inspect the highlighted annotation coordinates to verify whether underlying text is obscured.",
                )
            )

        return meta_dict, findings

    # =========================================================================
    # MODULE A IMPLEMENTATION: IMAGE CONSISTENCY ANALYSIS
    # =========================================================================
    @staticmethod
    def _run_module_a_image_consistency(
        document_id: str,
        document_sha256: str,
        is_pdf: bool,
        pdf_doc: Optional[fitz.Document],
        page_renders: Dict[int, Tuple[Image.Image, float, float]],
    ) -> Tuple[List[GeneratedForensicArtifact], List[GeneratedForensicFinding]]:
        artifacts: List[GeneratedForensicArtifact] = []
        findings: List[GeneratedForensicFinding] = []

        for pg_num, (pil_img, page_w, page_h) in sorted(page_renders.items()):
            np_rgb = np.array(pil_img)
            img_h, img_w = np_rgb.shape[:2]
            gray = cv2.cvtColor(np_rgb, cv2.COLOR_RGB2GRAY)

            # Compute block-wise Laplacian variance and background luminance across a 32x32 grid
            grid_size = 32
            rows = max(1, img_h // grid_size)
            cols = max(1, img_w // grid_size)

            var_grid = np.zeros((rows, cols), dtype=np.float32)
            bg_grid = np.zeros((rows, cols), dtype=np.float32)

            lap = cv2.Laplacian(gray, cv2.CV_64F)
            abs_lap = np.abs(lap)

            for r in range(rows):
                y0_px = r * grid_size
                y1_px = min(img_h, (r + 1) * grid_size)
                for c in range(cols):
                    x0_px = c * grid_size
                    x1_px = min(img_w, (c + 1) * grid_size)
                    patch_gray = gray[y0_px:y1_px, x0_px:x1_px]
                    patch_lap = abs_lap[y0_px:y1_px, x0_px:x1_px]
                    var_grid[r, c] = float(np.var(patch_lap))
                    # 85th percentile approximates local background paper luminance in text regions
                    bg_grid[r, c] = float(np.percentile(patch_gray, 85))

            # Generate a derived Local Variance / Texture Consistency diagnostic heatmap for Page 1
            if pg_num == 1:
                norm_lap = cv2.GaussianBlur(abs_lap.astype(np.float32), (15, 15), 0)
                max_val = float(np.percentile(norm_lap, 99.2)) if norm_lap.size > 0 else 1.0
                scaled = np.clip((norm_lap / max(1.0, max_val)) * 255.0, 0, 255).astype(np.uint8)
                heatmap_bgr = cv2.applyColorMap(scaled, cv2.COLORMAP_OCEAN)
                heatmap_rgb = cv2.cvtColor(heatmap_bgr, cv2.COLOR_BGR2RGB)
                blended = cv2.addWeighted(np_rgb, 0.42, heatmap_rgb, 0.58, 0)

                out_pil = Image.fromarray(blended)
                buf = io.BytesIO()
                out_pil.save(buf, format="PNG")
                png_bytes = buf.getvalue()
                art_id = str(uuid.uuid4())
                artifacts.append(
                    GeneratedForensicArtifact(
                        artifact_id=art_id,
                        page_number=pg_num,
                        artifact_type=ForensicArtifactType.LOCAL_VARIANCE_HEATMAP.value,
                        module_name=ForensicModuleName.MODULE_A_IMAGE_CONSISTENCY.value,
                        title=f"Page {pg_num} Local High-Frequency Variance & Background Map",
                        description=(
                            "OpenCV spatial Laplacian variance and local luminance consistency map. "
                            "Highlights localized sharp rectangular overlays, spliced patches, or compression transitions."
                        ),
                        mime_type="image/png",
                        png_bytes=png_bytes,
                        sha256_hash=hashlib.sha256(png_bytes).hexdigest(),
                        is_derived_from_pdf_render=is_pdf,
                        parameters={
                            "grid_size_px": grid_size,
                            "gaussian_kernel": [15, 15],
                            "image_dimensions_px": [img_w, img_h],
                        },
                        stats={
                            "global_background_median": round(float(np.median(bg_grid)), 2),
                            "global_laplacian_variance_mean": round(float(np.mean(var_grid)), 2),
                        },
                    )
                )
            else:
                art_id = artifacts[0].artifact_id if artifacts else None

            # Check A1: For PDFs, check if page has a localized filled rectangle / patch overlay behind specific text
            # or an embedded raster image patch covering a small portion of the page
            if is_pdf and pdf_doc is not None and pg_num <= len(pdf_doc):
                page = pdf_doc[pg_num - 1]
                drawings = page.get_drawings()
                for d in drawings:
                    rect = d.get("rect")
                    fill = d.get("fill")
                    if not rect or not fill:
                        continue
                    rx0, ry0, rx1, ry1 = float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)
                    rw, rh = rx1 - rx0, ry1 - ry0
                    # Look for localized non-white rectangular fill patches (e.g., off-white/gray masking box over a single field/amount)
                    # Exclude wide table header bars (rw > page_w * 0.55) or tiny bullets
                    if 40.0 <= rw <= page_w * 0.48 and 10.0 <= rh <= 45.0:
                        r_c, g_c, b_c = float(fill[0]), float(fill[1]), float(fill[2])
                        mean_c = (r_c + g_c + b_c) / 3.0
                        # Off-white / light-tinted patch (between 0.85 and 0.995 luminance, not pure 1.0 white and not dark header)
                        if 0.84 <= mean_c < 0.995:
                            bbox_dict = {
                                "x0": round(rx0, 2),
                                "y0": round(ry0, 2),
                                "x1": round(rx1, 2),
                                "y1": round(ry1, 2),
                                "page_width": page_w,
                                "page_height": page_h,
                            }
                            findings.append(
                                GeneratedForensicFinding(
                                    finding_id=str(uuid.uuid4()),
                                    module_name=ForensicModuleName.MODULE_A_IMAGE_CONSISTENCY.value,
                                    finding_category="LOCAL_BACKGROUND_PATCH_DIFFERENCE",
                                    severity=ForensicFindingSeverity.MEDIUM.value,
                                    title=f"Localized Background Luminance Patch Detected (Page {pg_num})",
                                    observation=(
                                        f"Detected a localized rectangular background region at "
                                        f"[{round(rx0, 1)}, {round(ry0, 1)}, {round(rx1, 1)}, {round(ry1, 1)}] "
                                        f"with RGB fill ({round(r_c*255)}, {round(g_c*255)}, {round(b_c*255)}) that differs "
                                        f"from the surrounding pure page background (255, 255, 255)."
                                    ),
                                    technical_explanation=(
                                        "Local luminance and vector fill inspection identified a bounded rectangular patch "
                                        "immediately behind text content whose background reflectance deviates from the surrounding document canvas."
                                    ),
                                    possible_benign_explanations=[
                                        "Intentional template callout box or highlighted total/summary field.",
                                        "Form field background shading applied by an accounting or invoicing template.",
                                    ],
                                    confidence_score=0.91,
                                    confidence_interpretation="High technical reliability for the presence of a distinct background patch.",
                                    limitations="Cannot determine from pixel luminance alone whether the shaded box was part of the blank template or added later.",
                                    page_number=pg_num,
                                    bounding_box=bbox_dict,
                                    evidence_reference=f"doc:{document_id}#page:{pg_num}@bbox:[{round(rx0,2)},{round(ry0,2)},{round(rx1,2)},{round(ry1,2)}]",
                                    artifact_id=art_id,
                                    analysis_parameters={"detector": "OpenCV & Vector Luminance Patch Comparator"},
                                    evidence_metrics={
                                        "patch_rgb_255": [round(r_c * 255, 1), round(g_c * 255, 1), round(b_c * 255, 1)],
                                        "surrounding_background_rgb_255": [255.0, 255.0, 255.0],
                                        "patch_dimensions_pt": [round(rw, 2), round(rh, 2)],
                                    },
                                    recommended_human_action=(
                                        "Inspect the highlighted region in the Visual Evidence Viewer and compare against "
                                        "known reference templates from the same issuer."
                                    ),
                                )
                            )

            # Check A2: For raster images (or scanned pages), check if a localized interior block has an anomalous
            # background luminance step or noise variance outlier compared to immediate 8-connected neighbors
            global_bg_median = float(np.median(bg_grid))
            global_var_median = float(np.median(var_grid))
            global_var_std = max(1.0, float(np.std(var_grid)))

            best_outlier: Optional[Tuple[float, int, int, float, float]] = None
            for r in range(1, rows - 1):
                for c in range(1, cols - 1):
                    ring = [
                        bg_grid[r - 1, c],
                        bg_grid[r + 1, c],
                        bg_grid[r, c - 1],
                        bg_grid[r, c + 1],
                    ]
                    ring_bg_mean = float(np.mean(ring))
                    bg_diff = abs(float(bg_grid[r, c]) - ring_bg_mean)
                    var_z = (float(var_grid[r, c]) - global_var_median) / global_var_std
                    if bg_diff >= 18.0 and var_z >= 3.2:
                        score = bg_diff + var_z * 5.0
                        if best_outlier is None or score > best_outlier[0]:
                            best_outlier = (score, r, c, bg_diff, var_z)

            if best_outlier is not None and not is_pdf:
                _, r_idx, c_idx, bg_diff_val, var_z_val = best_outlier
                scale_x = page_w / float(img_w)
                scale_y = page_h / float(img_h)
                bx0 = round(max(0.0, (c_idx - 1) * grid_size * scale_x), 2)
                by0 = round(max(0.0, (r_idx - 1) * grid_size * scale_y), 2)
                bx1 = round(min(page_w, (c_idx + 2) * grid_size * scale_x), 2)
                by1 = round(min(page_h, (r_idx + 2) * grid_size * scale_y), 2)

                findings.append(
                    GeneratedForensicFinding(
                        finding_id=str(uuid.uuid4()),
                        module_name=ForensicModuleName.MODULE_A_IMAGE_CONSISTENCY.value,
                        finding_category="LOCAL_IMAGE_STATISTICS_OUTLIER",
                        severity=ForensicFindingSeverity.LOW.value,
                        title=f"Localized Image Variance & Luminance Contrast Region (Page {pg_num})",
                        observation=(
                            f"Grid region at [{bx0}, {by0}, {bx1}, {by1}] exhibits a local Laplacian variance "
                            f"z-score of {round(var_z_val, 2)} and background luminance delta of {round(bg_diff_val, 1)} "
                            f"relative to adjacent document blocks (global median background={round(global_bg_median, 1)})."
                        ),
                        technical_explanation=(
                            "High-frequency Laplacian variance measures local edge sharpness and compression noise floor. "
                            "Regions with dense ink, stamps, or pasted image patches exhibit higher local variance than surrounding text."
                        ),
                        possible_benign_explanations=[
                            "High-contrast stamp ink, handwritten signature strokes, or bold header graphics.",
                            "Local scanner sensor noise or paper crease shadow.",
                        ],
                        confidence_score=0.82,
                        confidence_interpretation="Statistical spatial outlier in local image variance.",
                        limitations="Local variance highlights contrast density and cannot distinguish a wet-ink stamp from a digital composite without context.",
                        page_number=pg_num,
                        bounding_box={
                            "x0": bx0,
                            "y0": by0,
                            "x1": bx1,
                            "y1": by1,
                            "page_width": page_w,
                            "page_height": page_h,
                        },
                        evidence_reference=f"doc:{document_id}#page:{pg_num}@bbox:[{bx0},{by0},{bx1},{by1}]",
                        artifact_id=art_id,
                        analysis_parameters={"grid_size_px": grid_size},
                        evidence_metrics={
                            "laplacian_variance_zscore": round(var_z_val, 2),
                            "local_background_delta": round(bg_diff_val, 2),
                            "global_background_median": round(global_bg_median, 2),
                        },
                        recommended_human_action="Toggle the Local Variance Heatmap in the Visual Evidence Viewer to inspect whether the region corresponds to a legitimate stamp or graphic.",
                    )
                )

        return artifacts, findings

    # =========================================================================
    # MODULE B IMPLEMENTATION: ERROR LEVEL ANALYSIS (ELA)
    # =========================================================================
    @staticmethod
    def _run_module_b_ela(
        document_id: str,
        document_sha256: str,
        file_bytes: bytes,
        norm_type: str,
        is_pdf: bool,
        page_renders: Dict[int, Tuple[Image.Image, float, float]],
        jpeg_quality: int = 90,
        amplification_scale: float = 18.0,
    ) -> Tuple[List[GeneratedForensicArtifact], List[GeneratedForensicFinding]]:
        artifacts: List[GeneratedForensicArtifact] = []
        findings: List[GeneratedForensicFinding] = []

        pil_img, page_w, page_h = page_renders[1]
        img_w, img_h = pil_img.size

        # Perform controlled in-memory JPEG recompression without touching the original file
        jpeg_buf = io.BytesIO()
        pil_img.save(jpeg_buf, format="JPEG", quality=jpeg_quality, subsampling=0)
        jpeg_buf.seek(0)
        with Image.open(jpeg_buf) as recompressed_pil:
            recompressed_rgb = recompressed_pil.convert("RGB")
            diff_pil = ImageChops.difference(pil_img, recompressed_rgb)

        np_diff = np.array(diff_pil, dtype=np.float32)
        mean_abs_error = float(np.mean(np_diff))
        max_abs_error = float(np.max(np_diff))

        # Create high-visibility amplified ELA image for the Visual Evidence Viewer
        amplified_arr = np.clip(np_diff * amplification_scale, 0, 255).astype(np.uint8)
        ela_pil = Image.fromarray(amplified_arr)
        ela_png_buf = io.BytesIO()
        ela_pil.save(ela_png_buf, format="PNG")
        ela_png_bytes = ela_png_buf.getvalue()

        source_format_label = (
            "ORIGINAL_JPEG"
            if norm_type in ("JPG", "JPEG")
            else ("DERIVED_PDF_PAGE_RENDER" if is_pdf else "LOSSLESS_PNG")
        )

        ela_artifact_id = str(uuid.uuid4())
        artifacts.append(
            GeneratedForensicArtifact(
                artifact_id=ela_artifact_id,
                page_number=1,
                artifact_type=ForensicArtifactType.ELA_DERIVED_IMAGE.value,
                module_name=ForensicModuleName.MODULE_B_ELA.value,
                title=f"Page 1 Error Level Analysis (ELA @ Q={jpeg_quality}, {amplification_scale}x)",
                description=(
                    f"Derived ELA residual map generated from {source_format_label} at JPEG quality {jpeg_quality} "
                    f"with {amplification_scale}x luminance amplification. Original upload preserved unchanged."
                ),
                mime_type="image/png",
                png_bytes=ela_png_bytes,
                sha256_hash=hashlib.sha256(ela_png_bytes).hexdigest(),
                is_derived_from_pdf_render=is_pdf,
                parameters={
                    "jpeg_quality": jpeg_quality,
                    "amplification_scale": amplification_scale,
                    "source_format": source_format_label,
                    "is_derived_from_pdf_render": is_pdf,
                },
                stats={
                    "mean_pixel_residual": round(mean_abs_error, 4),
                    "max_pixel_residual": round(max_abs_error, 4),
                    "image_dimensions_px": [img_w, img_h],
                },
            )
        )

        # Evaluate 32x32 block residuals
        grid_size = 32
        rows = max(1, img_h // grid_size)
        cols = max(1, img_w // grid_size)
        block_means = np.zeros((rows, cols), dtype=np.float32)
        for r in range(rows):
            for c in range(cols):
                patch = np_diff[
                    r * grid_size : min(img_h, (r + 1) * grid_size),
                    c * grid_size : min(img_w, (c + 1) * grid_size),
                ]
                block_means[r, c] = float(np.mean(patch))

        active_blocks = block_means[block_means > 0.4]
        active_mean = float(np.mean(active_blocks)) if active_blocks.size > 0 else float(np.mean(block_means))
        active_std = max(0.35, float(np.std(active_blocks)) if active_blocks.size > 0 else float(np.std(block_means)))
        max_r, max_c = np.unravel_index(int(np.argmax(block_means)), block_means.shape)
        peak_block_val = float(block_means[max_r, max_c])
        peak_z = (peak_block_val - active_mean) / active_std

        scale_x = page_w / float(img_w)
        scale_y = page_h / float(img_h)
        peak_bbox = {
            "x0": round(max(0.0, max_c * grid_size * scale_x), 2),
            "y0": round(max(0.0, max_r * grid_size * scale_y), 2),
            "x1": round(min(page_w, (max_c + 2) * grid_size * scale_x), 2),
            "y1": round(min(page_h, (max_r + 2) * grid_size * scale_y), 2),
            "page_width": page_w,
            "page_height": page_h,
        }

        if norm_type in ("JPG", "JPEG"):
            # Authentic JPEG ELA evaluation
            sev = (
                ForensicFindingSeverity.MEDIUM.value
                if (peak_z >= 2.8 and peak_block_val >= 2.2)
                else ForensicFindingSeverity.INFORMATIONAL.value
            )
            findings.append(
                GeneratedForensicFinding(
                    finding_id=str(uuid.uuid4()),
                    module_name=ForensicModuleName.MODULE_B_ELA.value,
                    finding_category="ELA_JPEG_RECOMPRESSION_ANALYSIS",
                    severity=sev,
                    title=(
                        "Localized JPEG ELA Recompression Divergence Observed"
                        if sev == ForensicFindingSeverity.MEDIUM.value
                        else "JPEG Error Level Analysis Baseline Profile"
                    ),
                    observation=(
                        f"Executed Error Level Analysis on original JPEG image at Q={jpeg_quality} "
                        f"(global mean residual={round(mean_abs_error, 3)}, peak 32x32 block residual={round(peak_block_val, 3)}, "
                        f"z-score={round(peak_z, 2)} at region [{peak_bbox['x0']}, {peak_bbox['y0']}, {peak_bbox['x1']}, {peak_bbox['y1']}])."
                    ),
                    technical_explanation=(
                        "Error Level Analysis recompresses a lossy JPEG image at a known quality level (Q=90) and measures "
                        "8x8 DCT quantization residuals. Regions saved at a different JPEG quality level or containing sharp "
                        "uncompressed graphic overlays exhibit higher recompression residuals than thrice-compressed background."
                    ),
                    possible_benign_explanations=[
                        "High-contrast text edges, saturated colored stamps, or sharp vector logos naturally produce stronger DCT ringing residuals.",
                        "Scanner firmware applying region-specific compression (MRC / mixed raster content).",
                        "Multiple legitimate saves across document workflow tools.",
                    ],
                    confidence_score=0.84 if sev == ForensicFindingSeverity.MEDIUM.value else 0.92,
                    confidence_interpretation=(
                        "Measures reliability of the observed JPEG recompression residual difference — NOT an authenticity probability."
                    ),
                    limitations=(
                        "ELA results depend heavily on image format, resolution, color saturation, and prior resaving history. "
                        "ELA alone can never prove or disprove tampering."
                    ),
                    page_number=1,
                    bounding_box=peak_bbox,
                    evidence_reference=f"doc:{document_id}#page:1@ela_q{jpeg_quality}:[{peak_bbox['x0']},{peak_bbox['y0']},{peak_bbox['x1']},{peak_bbox['y1']}]",
                    artifact_id=ela_artifact_id,
                    analysis_parameters={
                        "jpeg_quality": jpeg_quality,
                        "amplification_scale": amplification_scale,
                        "source_format": "ORIGINAL_JPEG",
                    },
                    evidence_metrics={
                        "mean_pixel_residual": round(mean_abs_error, 4),
                        "peak_block_residual": round(peak_block_val, 4),
                        "peak_block_zscore": round(peak_z, 2),
                    },
                    recommended_human_action=(
                        "Switch to the Derived ELA View in the Visual Evidence Viewer and inspect whether the peak residual "
                        "aligns with a high-contrast border/stamp or an isolated text/number field."
                    ),
                )
            )
        elif is_pdf:
            findings.append(
                GeneratedForensicFinding(
                    finding_id=str(uuid.uuid4()),
                    module_name=ForensicModuleName.MODULE_B_ELA.value,
                    finding_category="ELA_DERIVED_PDF_RENDER_DIAGNOSTIC",
                    severity=ForensicFindingSeverity.INFORMATIONAL.value,
                    title="Derived PDF Page-Render ELA Diagnostic Map Generated",
                    observation=(
                        f"Source document is a PDF container. Generated a derived page-render ELA map at Q={jpeg_quality} "
                        f"(mean residual={round(mean_abs_error, 3)}, peak block residual={round(peak_block_val, 3)} at "
                        f"[{peak_bbox['x0']}, {peak_bbox['y0']}, {peak_bbox['x1']}, {peak_bbox['y1']}])."
                    ),
                    technical_explanation=(
                        "Because native PDF pages store vector commands and fonts rather than a single camera JPEG stream, "
                        "this ELA artifact was computed on a derived 150 DPI page render. It highlights high-frequency edge contrast "
                        "and embedded raster XObject compression boundaries rather than native PDF stream edits."
                    ),
                    possible_benign_explanations=[
                        "Vector text and table borders rendered to raster pixels exhibit uniform first-generation JPEG quantization residuals.",
                        "Colored stamps and bold headings naturally respond more strongly to chroma/luma quantization.",
                    ],
                    confidence_score=0.95,
                    confidence_interpretation="Deterministic derived-render diagnostic (Informational context only).",
                    limitations=(
                        "PDF page-render ELA must be strictly distinguished from original JPEG ELA; rely on Module C (Typography), "
                        "Module D (Alignment), Module E (PDF Metadata), and Module G (Text-to-Visual) for vector PDF forensics."
                    ),
                    page_number=1,
                    bounding_box=peak_bbox,
                    evidence_reference=f"doc:{document_id}#page:1@derived_pdf_ela",
                    artifact_id=ela_artifact_id,
                    analysis_parameters={
                        "jpeg_quality": jpeg_quality,
                        "amplification_scale": amplification_scale,
                        "source_format": "DERIVED_PDF_PAGE_RENDER",
                        "render_dpi": 150,
                    },
                    evidence_metrics={
                        "mean_pixel_residual": round(mean_abs_error, 4),
                        "peak_block_residual": round(peak_block_val, 4),
                        "peak_block_zscore": round(peak_z, 2),
                    },
                    recommended_human_action=(
                        "Use the derived ELA map to inspect embedded raster objects or stamps, and prioritize Typography/Metadata "
                        "modules for native PDF text verification."
                    ),
                )
            )
        else:
            # Lossless PNG
            findings.append(
                GeneratedForensicFinding(
                    finding_id=str(uuid.uuid4()),
                    module_name=ForensicModuleName.MODULE_B_ELA.value,
                    finding_category="ELA_LOSSLESS_FORMAT_LIMITATION",
                    severity=ForensicFindingSeverity.INFORMATIONAL.value,
                    title="Lossless PNG Source — ELA Quantization History Not Applicable",
                    observation=(
                        f"Source file is a lossless PNG image ({img_w}x{img_h} px). Generated baseline Q={jpeg_quality} "
                        f"recompression map (mean residual={round(mean_abs_error, 3)}), which reflects first-pass edge contrast."
                    ),
                    technical_explanation=(
                        "Error Level Analysis relies on prior lossy 8x8 DCT quantization grids present in JPEG files. "
                        "Lossless PNG files use DEFLATE compression without quantization loss unless the image was previously "
                        "saved as a JPEG before conversion to PNG."
                    ),
                    possible_benign_explanations=[
                        "Document was scanned or exported directly to lossless PNG format.",
                        "High-contrast text edges and colored ink regions naturally show stronger first-pass JPEG residuals.",
                    ],
                    confidence_score=0.98,
                    confidence_interpretation="Deterministic format capability check.",
                    limitations="ELA cannot detect localized recompression history in native lossless PNG images.",
                    page_number=1,
                    bounding_box=peak_bbox,
                    evidence_reference=f"doc:{document_id}#page:1@png_ela_baseline",
                    artifact_id=ela_artifact_id,
                    analysis_parameters={
                        "jpeg_quality": jpeg_quality,
                        "amplification_scale": amplification_scale,
                        "source_format": "LOSSLESS_PNG",
                    },
                    evidence_metrics={
                        "mean_pixel_residual": round(mean_abs_error, 4),
                        "peak_block_residual": round(peak_block_val, 4),
                    },
                    recommended_human_action="Rely on Module A (Local Variance/Luminance), Module D (Alignment), and Module G (OCR Confidence) for PNG scans.",
                )
            )

        return artifacts, findings

    # =========================================================================
    # MODULE C IMPLEMENTATION: TYPOGRAPHY CONSISTENCY ANALYSIS
    # =========================================================================
    @staticmethod
    def _run_module_c_typography(
        document_id: str,
        is_pdf: bool,
        pdf_doc: Optional[fitz.Document],
        pages_db_data: List[Dict[str, Any]],
        page_renders: Dict[int, Tuple[Image.Image, float, float]],
    ) -> List[GeneratedForensicFinding]:
        findings: List[GeneratedForensicFinding] = []

        if is_pdf and pdf_doc is not None:
            for idx in range(len(pdf_doc)):
                pg_num = idx + 1
                page = pdf_doc[idx]
                page_w = round(float(page.rect.width), 2)
                page_h = round(float(page.rect.height), 2)
                p_dict = page.get_text("dict")

                # Collect all non-empty spans with their line & block coordinates
                spans_list: List[Dict[str, Any]] = []
                for blk in p_dict.get("blocks", []):
                    if blk.get("type") != 0:
                        continue
                    for line in blk.get("lines", []):
                        for sp in line.get("spans", []):
                            txt = str(sp.get("text", "")).strip()
                            if not txt:
                                continue
                            sb = sp.get("bbox", (0.0, 0.0, 0.0, 0.0))
                            orig = sp.get("origin", (sb[0], sb[3]))
                            f_raw = str(sp.get("font", "UnknownFont")).strip()
                            f_fam = _normalize_font_family(f_raw)
                            f_size = round(float(sp.get("size", 0.0)), 2)
                            spans_list.append(
                                {
                                    "text": txt,
                                    "font_raw": f_raw,
                                    "font_family": f_fam,
                                    "font_size": f_size,
                                    "flags": int(sp.get("flags", 0)),
                                    "color": int(sp.get("color", 0)),
                                    "x0": round(float(sb[0]), 2),
                                    "y0": round(float(sb[1]), 2),
                                    "x1": round(float(sb[2]), 2),
                                    "y1": round(float(sb[3]), 2),
                                    "yc": round((float(sb[1]) + float(sb[3])) / 2.0, 2),
                                    "origin_x": round(float(orig[0]), 2),
                                    "origin_y": round(float(orig[1]), 2),
                                }
                            )

                if not spans_list:
                    continue

                # Determine dominant document font family on this page
                fam_counts: Dict[str, int] = {}
                for sp in spans_list:
                    fam_counts[sp["font_family"]] = fam_counts.get(sp["font_family"], 0) + len(sp["text"])
                dominant_family = max(fam_counts.items(), key=lambda x: x[1])[0]

                # Group spans into horizontal visual rows (within 4.5pt vertical center)
                spans_sorted = sorted(spans_list, key=lambda s: (s["yc"], s["x0"]))
                visual_rows: List[List[Dict[str, Any]]] = []
                for sp in spans_sorted:
                    placed = False
                    for row in visual_rows:
                        row_yc = sum(item["yc"] for item in row) / len(row)
                        if abs(sp["yc"] - row_yc) <= 4.5:
                            row.append(sp)
                            placed = True
                            break
                    if not placed:
                        visual_rows.append([sp])

                # Check horizontal rows with >= 2 spans for:
                # 1) Font family switch within the same visual row (e.g. Helvetica row with Courier/Times value)
                # 2) Font size mismatch within a data/key-value row (excluding bold/italic style variants of same family/size)
                # 3) Baseline vertical shift (origin_y delta >= 1.2pt) within the same visual row
                for row in visual_rows:
                    if len(row) < 2:
                        continue
                    row = sorted(row, key=lambda s: s["x0"])
                    row_families = {s["font_family"] for s in row}
                    row_sizes = [s["font_size"] for s in row]
                    row_origins = [s["origin_y"] for s in row]

                    # 1. Intra-row font family inconsistency
                    if len(row_families) > 1:
                        outlier_spans = [s for s in row if s["font_family"] != dominant_family]
                        peer_spans = [s for s in row if s["font_family"] == dominant_family]
                        if outlier_spans and peer_spans:
                            out_sp = outlier_spans[0]
                            peer_sp = peer_spans[0]
                            findings.append(
                                GeneratedForensicFinding(
                                    finding_id=str(uuid.uuid4()),
                                    module_name=ForensicModuleName.MODULE_C_TYPOGRAPHY.value,
                                    finding_category="INTRA_LINE_FONT_FAMILY_MISMATCH",
                                    severity=ForensicFindingSeverity.HIGH.value,
                                    title=f"Font Family Substitution Within Comparable Line ('{out_sp['font_raw']}' vs '{peer_sp['font_raw']}')",
                                    observation=(
                                        f"On page {pg_num}, span '{out_sp['text']}' is set in font '{out_sp['font_raw']}' "
                                        f"({out_sp['font_size']}pt) whereas the adjacent text on the same horizontal row "
                                        f"('{peer_sp['text']}') and dominant page body use '{peer_sp['font_raw']}' ({peer_sp['font_size']}pt)."
                                    ),
                                    technical_explanation=(
                                        "PyMuPDF vector span inspection revealed that a specific field value on a horizontal line "
                                        "references a different font resource family than surrounding labels and peer table/body rows."
                                    ),
                                    possible_benign_explanations=[
                                        "Template designer intentionally formatted numeric amounts, account codes, or reference numbers in a monospace font.",
                                        "Automated form-filling engine populated a blank template field using a default system fallback font.",
                                    ],
                                    confidence_score=0.96,
                                    confidence_interpretation="Deterministic PDF font resource inspection on vector text spans.",
                                    limitations="Font substitution confirms dual font usage in the PDF stream but does not by itself prove unauthorized alteration.",
                                    page_number=pg_num,
                                    bounding_box={
                                        "x0": out_sp["x0"],
                                        "y0": out_sp["y0"],
                                        "x1": out_sp["x1"],
                                        "y1": out_sp["y1"],
                                        "page_width": page_w,
                                        "page_height": page_h,
                                    },
                                    evidence_reference=f"doc:{document_id}#page:{pg_num}@span:[{out_sp['x0']},{out_sp['y0']},{out_sp['x1']},{out_sp['y1']}]",
                                    artifact_id=None,
                                    analysis_parameters={"inspector": "PyMuPDF Span Typography Comparator"},
                                    evidence_metrics={
                                        "span_text": out_sp["text"],
                                        "span_font": out_sp["font_raw"],
                                        "span_font_size": out_sp["font_size"],
                                        "peer_text": peer_sp["text"],
                                        "peer_font": peer_sp["font_raw"],
                                        "peer_font_size": peer_sp["font_size"],
                                    },
                                    recommended_human_action=(
                                        "Verify whether the font change on this value occurs in known authentic documents from the same issuer "
                                        "and cross-check the numeric/entity value against supporting records."
                                    ),
                                )
                            )

                    # 2. Intra-row font size or baseline shift anomaly
                    max_origin_delta = max(row_origins) - min(row_origins)
                    max_size_delta = max(row_sizes) - min(row_sizes)
                    if max_origin_delta >= 1.25 or max_size_delta >= 1.25:
                        # Identify the span that deviates from the leftmost label span in the row
                        base_sp = row[0]
                        for cand_sp in row[1:]:
                            o_delta = round(abs(cand_sp["origin_y"] - base_sp["origin_y"]), 2)
                            s_delta = round(abs(cand_sp["font_size"] - base_sp["font_size"]), 2)
                            if o_delta >= 1.25 or s_delta >= 1.25:
                                findings.append(
                                    GeneratedForensicFinding(
                                        finding_id=str(uuid.uuid4()),
                                        module_name=ForensicModuleName.MODULE_C_TYPOGRAPHY.value,
                                        finding_category="BASELINE_OR_FONTSIZE_DISCONTINUITY",
                                        severity=ForensicFindingSeverity.MEDIUM.value,
                                        title=f"Intra-Line Baseline / Font-Size Discontinuity ('{cand_sp['text'][:28]}')",
                                        observation=(
                                            f"On page {pg_num}, span '{cand_sp['text']}' (baseline Y={cand_sp['origin_y']}pt, "
                                            f"size={cand_sp['font_size']}pt) deviates from its same-line peer '{base_sp['text']}' "
                                            f"(baseline Y={base_sp['origin_y']}pt, size={base_sp['font_size']}pt) by "
                                            f"Δbaseline={o_delta}pt and Δsize={s_delta}pt."
                                        ),
                                        technical_explanation=(
                                            "Standard typesetting engines place all spans within a single horizontal table row or key-value line "
                                            "on an identical baseline Y coordinate. A vertical baseline offset or point-size jump indicates "
                                            "an independently positioned text object."
                                        ),
                                        possible_benign_explanations=[
                                            "Two separate text boxes placed manually in a form designer or DTP layout tool.",
                                            "Intentional typographic emphasis on a total or summary value.",
                                        ],
                                        confidence_score=0.93,
                                        confidence_interpretation="Exact vector coordinate measurement from PDF text matrix.",
                                        limitations="Manual form templates occasionally exhibit slight baseline misalignments across columns.",
                                        page_number=pg_num,
                                        bounding_box={
                                            "x0": cand_sp["x0"],
                                            "y0": cand_sp["y0"],
                                            "x1": cand_sp["x1"],
                                            "y1": cand_sp["y1"],
                                            "page_width": page_w,
                                            "page_height": page_h,
                                        },
                                        evidence_reference=f"doc:{document_id}#page:{pg_num}@baseline:[{cand_sp['x0']},{cand_sp['y0']},{cand_sp['x1']},{cand_sp['y1']}]",
                                        artifact_id=None,
                                        analysis_parameters={
                                            "baseline_delta_threshold_pt": 1.25,
                                            "fontsize_delta_threshold_pt": 1.25,
                                        },
                                        evidence_metrics={
                                            "span_text": cand_sp["text"],
                                            "span_origin_y": cand_sp["origin_y"],
                                            "peer_origin_y": base_sp["origin_y"],
                                            "baseline_delta_pt": o_delta,
                                            "span_font_size": cand_sp["font_size"],
                                            "peer_font_size": base_sp["font_size"],
                                            "fontsize_delta_pt": s_delta,
                                        },
                                        recommended_human_action="Zoom into the highlighted span in the Visual Evidence Viewer to inspect vertical alignment against the row baseline.",
                                    )
                                )
                                break
        else:
            # Scanned document / OCR geometry typography check
            for pg_data in pages_db_data:
                pg_num = int(pg_data.get("page_number", 1))
                blocks = pg_data.get("extractions", [])
                if not blocks:
                    continue
                heights = [
                    float(b["bounding_box"]["y1"]) - float(b["bounding_box"]["y0"])
                    for b in blocks
                    if (float(b["bounding_box"]["y1"]) - float(b["bounding_box"]["y0"])) > 4.0
                ]
                med_h = float(np.median(heights)) if heights else 0.0
                findings.append(
                    GeneratedForensicFinding(
                        finding_id=str(uuid.uuid4()),
                        module_name=ForensicModuleName.MODULE_C_TYPOGRAPHY.value,
                        finding_category="SCANNED_OCR_TYPOGRAPHY_GEOMETRY",
                        severity=ForensicFindingSeverity.INFORMATIONAL.value,
                        title=f"Scanned Document OCR Line-Height Geometry Profile (Page {pg_num})",
                        observation=(
                            f"Page {pg_num} was extracted via Visual OCR ({len(blocks)} text blocks, "
                            f"median line bounding-box height={round(med_h, 1)} px). Native PDF font family descriptors "
                            f"are not embedded in raster scans."
                        ),
                        technical_explanation=(
                            "For raster images and scanned PDFs, font resource dictionaries do not exist; typography analysis "
                            "evaluates bounding-box line heights and stroke geometry without inventing font family names."
                        ),
                        possible_benign_explanations=[
                            "Physical paper document digitized via optical scanner."
                        ],
                        confidence_score=0.90,
                        confidence_interpretation="Direct measurement of OCR bounding-box geometry.",
                        limitations="Optical character recognition bounding boxes cannot identify exact PostScript/TrueType font names.",
                        page_number=pg_num,
                        bounding_box=None,
                        evidence_reference=f"doc:{document_id}#page:{pg_num}@ocr_typography",
                        artifact_id=None,
                        analysis_parameters={"mode": "VISUAL_OCR_BOUNDING_BOX_GEOMETRY"},
                        evidence_metrics={
                            "ocr_block_count": len(blocks),
                            "median_bbox_height_px": round(med_h, 2),
                        },
                        recommended_human_action="Inspect visual character stroke thickness and alignment in the Page Preview viewer.",
                    )
                )

        return findings

    # =========================================================================
    # MODULE D IMPLEMENTATION: ALIGNMENT AND SPATIAL ANALYSIS
    # =========================================================================
    @staticmethod
    def _run_module_d_alignment(
        document_id: str,
        is_pdf: bool,
        pdf_doc: Optional[fitz.Document],
        layout_regions_db: List[Dict[str, Any]],
        tables_db: List[Dict[str, Any]],
        page_renders: Dict[int, Tuple[Image.Image, float, float]],
    ) -> List[GeneratedForensicFinding]:
        findings: List[GeneratedForensicFinding] = []

        # Group layout regions by page
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for reg in layout_regions_db:
            by_page.setdefault(int(reg.get("page_number", 1)), []).append(reg)

        for pg_num, regs in sorted(by_page.items()):
            _, page_w, page_h = page_renders.get(pg_num, (None, 595.0, 842.0))
            # Check left-margin column rail alignment among vertically stacked body/key-value regions
            body_regs = [
                r
                for r in regs
                if r.get("region_type")
                in ("KEY_VALUE_REGION", "PARAGRAPH", "SECTION_HEADING")
            ]
            if len(body_regs) >= 3:
                x0_vals = [float(r["bounding_box"]["x0"]) for r in body_regs]
                # Find dominant left margin rail (cluster within 2.0pt)
                best_rail = x0_vals[0]
                best_cluster_size = 0
                for cand in x0_vals:
                    cnt = sum(1 for x in x0_vals if abs(x - cand) <= 1.5)
                    if cnt > best_cluster_size:
                        best_cluster_size = cnt
                        best_rail = cand

                if best_cluster_size >= 2:
                    for r in body_regs:
                        rx0 = float(r["bounding_box"]["x0"])
                        drift = round(rx0 - best_rail, 2)
                        # Flag blocks that are intended to be on the left rail but drift by 2.5pt to 18.0pt
                        if 2.5 <= abs(drift) <= 18.0:
                            bb = r["bounding_box"]
                            findings.append(
                                GeneratedForensicFinding(
                                    finding_id=str(uuid.uuid4()),
                                    module_name=ForensicModuleName.MODULE_D_ALIGNMENT.value,
                                    finding_category="LEFT_MARGIN_RAIL_MISALIGNMENT",
                                    severity=ForensicFindingSeverity.MEDIUM.value,
                                    title=f"Left-Margin Column Rail Drift ({drift:+.1f}pt from {round(best_rail, 1)}pt rail)",
                                    observation=(
                                        f"On page {pg_num}, layout region '{r.get('label')}' ('{str(r.get('text_content', ''))[:45]}') "
                                        f"starts at X0={rx0}pt, drifting by {drift:+.2f}pt from the established left margin rail "
                                        f"at X={round(best_rail, 2)}pt ({best_cluster_size} aligned blocks)."
                                    ),
                                    technical_explanation=(
                                        "Automated document templates align vertically stacked key-value blocks and headings along a fixed "
                                        "left X coordinate rail. A horizontal offset of several points indicates a manually positioned block or tab space."
                                    ),
                                    possible_benign_explanations=[
                                        "Leading space character or manual indentation in the source template.",
                                        "Sub-item indentation or OCR bounding-box horizontal jitter on scanned pages.",
                                    ],
                                    confidence_score=0.89 if is_pdf else 0.78,
                                    confidence_interpretation="Direct spatial coordinate comparison across Phase 2B layout regions.",
                                    limitations="Cannot distinguish an accidental spacebar/tab in the author's template from post-hoc text box repositioning.",
                                    page_number=pg_num,
                                    bounding_box={
                                        "x0": float(bb["x0"]),
                                        "y0": float(bb["y0"]),
                                        "x1": float(bb["x1"]),
                                        "y1": float(bb["y1"]),
                                        "page_width": page_w,
                                        "page_height": page_h,
                                    },
                                    evidence_reference=f"doc:{document_id}#page:{pg_num}@layout_rail:[{bb['x0']},{bb['y0']},{bb['x1']},{bb['y1']}]",
                                    artifact_id=None,
                                    analysis_parameters={"rail_drift_range_pt": [2.5, 18.0]},
                                    evidence_metrics={
                                        "region_x0": rx0,
                                        "dominant_rail_x0": round(best_rail, 2),
                                        "horizontal_drift_pt": drift,
                                        "aligned_peer_count": best_cluster_size,
                                    },
                                    recommended_human_action="Enable Bounding-Box Overlays in the Visual Evidence Viewer and inspect the vertical left-margin guide.",
                                )
                            )

        # Also check native PDF text lines inside tables or columns for horizontal alignment drift
        if is_pdf and pdf_doc is not None:
            for idx in range(len(pdf_doc)):
                pg_num = idx + 1
                page = pdf_doc[idx]
                page_w = round(float(page.rect.width), 2)
                page_h = round(float(page.rect.height), 2)
                p_dict = page.get_text("dict")

                # Collect spans in right-hand value columns (x0 > page_w * 0.45)
                right_spans: List[Dict[str, Any]] = []
                for blk in p_dict.get("blocks", []):
                    if blk.get("type") != 0:
                        continue
                    for line in blk.get("lines", []):
                        for sp in line.get("spans", []):
                            txt = str(sp.get("text", "")).strip()
                            if not txt:
                                continue
                            sb = sp.get("bbox", (0.0, 0.0, 0.0, 0.0))
                            if float(sb[0]) >= page_w * 0.45:
                                right_spans.append(
                                    {
                                        "text": txt,
                                        "x0": round(float(sb[0]), 2),
                                        "y0": round(float(sb[1]), 2),
                                        "x1": round(float(sb[2]), 2),
                                        "y1": round(float(sb[3]), 2),
                                    }
                                )

                # Check if a vertical column of >= 3 spans has one span shifted by 2.5pt..15pt
                for sp in right_spans:
                    peers = [
                        p
                        for p in right_spans
                        if p is not sp
                        and abs(p["x0"] - sp["x0"]) <= 1.2
                        and abs(p["y0"] - sp["y0"]) <= 140.0
                    ]
                    if len(peers) >= 2:
                        rail_x = round(sum(p["x0"] for p in peers + [sp]) / (len(peers) + 1), 2)
                        for cand in right_spans:
                            if cand in peers or cand is sp:
                                continue
                            if (
                                2.5 <= abs(cand["x0"] - rail_x) <= 15.0
                                and min(p["y0"] for p in peers + [sp]) - 35.0
                                <= cand["y0"]
                                <= max(p["y0"] for p in peers + [sp]) + 35.0
                            ):
                                drift = round(cand["x0"] - rail_x, 2)
                                findings.append(
                                    GeneratedForensicFinding(
                                        finding_id=str(uuid.uuid4()),
                                        module_name=ForensicModuleName.MODULE_D_ALIGNMENT.value,
                                        finding_category="TABLE_OR_COLUMN_CELL_MISALIGNMENT",
                                        severity=ForensicFindingSeverity.MEDIUM.value,
                                        title=f"Column / Table Value Horizontal Misalignment ('{cand['text'][:28]}')",
                                        observation=(
                                            f"On page {pg_num}, column value '{cand['text']}' starts at X0={cand['x0']}pt, "
                                            f"drifting by {drift:+.2f}pt relative to the vertically aligned column rail at X={rail_x}pt."
                                        ),
                                        technical_explanation=(
                                            "Values within the same table or summary column share a fixed horizontal X coordinate rail "
                                            "when generated programmatically. A localized horizontal shift indicates a separate text placement."
                                        ),
                                        possible_benign_explanations=[
                                            "Right-aligned numeric column where character width varies with digit count.",
                                            "Manual column adjustment in the source spreadsheet or word processor.",
                                        ],
                                        confidence_score=0.88,
                                        confidence_interpretation="Exact PDF span bounding-box column alignment measurement.",
                                        limitations="Right-aligned or centered columns naturally vary in left X0 coordinate when string lengths differ.",
                                        page_number=pg_num,
                                        bounding_box={
                                            "x0": cand["x0"],
                                            "y0": cand["y0"],
                                            "x1": cand["x1"],
                                            "y1": cand["y1"],
                                            "page_width": page_w,
                                            "page_height": page_h,
                                        },
                                        evidence_reference=f"doc:{document_id}#page:{pg_num}@col_align:[{cand['x0']},{cand['y0']},{cand['x1']},{cand['y1']}]",
                                        artifact_id=None,
                                        analysis_parameters={"column_drift_range_pt": [2.5, 15.0]},
                                        evidence_metrics={
                                            "value_text": cand["text"],
                                            "value_x0": cand["x0"],
                                            "column_rail_x0": rail_x,
                                            "drift_pt": drift,
                                        },
                                        recommended_human_action="Inspect the column alignment of the highlighted cell in the Visual Evidence Viewer.",
                                    )
                                )
                                break
                        break

        return findings

    # =========================================================================
    # MODULE F IMPLEMENTATION: SIGNATURE AND STAMP REGION ANALYSIS
    # =========================================================================
    @staticmethod
    def _run_module_f_signature_and_stamp(
        document_id: str,
        document_sha256: str,
        is_pdf: bool,
        pdf_doc: Optional[fitz.Document],
        layout_regions_db: List[Dict[str, Any]],
        page_renders: Dict[int, Tuple[Image.Image, float, float]],
    ) -> Tuple[List[GeneratedForensicArtifact], List[GeneratedForensicFinding]]:
        artifacts: List[GeneratedForensicArtifact] = []
        findings: List[GeneratedForensicFinding] = []

        sig_stamp_regions = [
            r
            for r in layout_regions_db
            if r.get("region_type") in ("SIGNATURE_REGION", "STAMP_REGION")
        ]

        for reg in sig_stamp_regions:
            pg_num = int(reg.get("page_number", 1))
            r_type = str(reg.get("region_type"))
            bb = reg.get("bounding_box", {})
            if pg_num not in page_renders:
                continue

            pil_img, page_w, page_h = page_renders[pg_num]
            img_w, img_h = pil_img.size
            scale_x = float(img_w) / max(1.0, page_w)
            scale_y = float(img_h) / max(1.0, page_h)

            x0_pt, y0_pt = float(bb.get("x0", 0.0)), float(bb.get("y0", 0.0))
            x1_pt, y1_pt = float(bb.get("x1", 0.0)), float(bb.get("y1", 0.0))

            # Crop region with small context padding (8px)
            pad = 8
            cx0 = max(0, int(round(x0_pt * scale_x)) - pad)
            cy0 = max(0, int(round(y0_pt * scale_y)) - pad)
            cx1 = min(img_w, int(round(x1_pt * scale_x)) + pad)
            cy1 = min(img_h, int(round(y1_pt * scale_y)) + pad)

            if cx1 <= cx0 + 4 or cy1 <= cy0 + 4:
                continue

            crop_pil = pil_img.crop((cx0, cy0, cx1, cy1))
            crop_buf = io.BytesIO()
            crop_pil.save(crop_buf, format="PNG")
            crop_bytes = crop_buf.getvalue()

            np_crop = np.array(crop_pil)
            crop_gray = cv2.cvtColor(np_crop, cv2.COLOR_RGB2GRAY)
            crop_bg_lum = float(np.percentile(crop_gray, 85))
            crop_ink_ratio = float(np.mean(crop_gray < 210))

            # Compare against surrounding page background
            np_full_gray = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
            page_bg_lum = float(np.percentile(np_full_gray, 85))
            bg_delta = round(abs(crop_bg_lum - page_bg_lum), 2)

            # Determine representation mode (Vector vs Embedded Raster vs Scanned Raster)
            composition_mode = "SCANNED_RASTER_REGION"
            if is_pdf and pdf_doc is not None and pg_num <= len(pdf_doc):
                page = pdf_doc[pg_num - 1]
                has_embedded_img_overlap = False
                for img_info in page.get_image_info():
                    ib = img_info.get("bbox", (0, 0, 0, 0))
                    if _bbox_iou_or_overlap(
                        {"x0": x0_pt, "y0": y0_pt, "x1": x1_pt, "y1": y1_pt},
                        {"x0": ib[0], "y0": ib[1], "x1": ib[2], "y1": ib[3]},
                    ) > 0.15:
                        has_embedded_img_overlap = True
                        break
                composition_mode = (
                    "EMBEDDED_RASTER_XOBJECT_IN_PDF"
                    if has_embedded_img_overlap
                    else "VECTOR_AND_TEXT_STREAM_IN_PDF"
                )

            art_id = str(uuid.uuid4())
            art_type = (
                ForensicArtifactType.STAMP_CROP.value
                if r_type == "STAMP_REGION"
                else ForensicArtifactType.SIGNATURE_CROP.value
            )
            artifacts.append(
                GeneratedForensicArtifact(
                    artifact_id=art_id,
                    page_number=pg_num,
                    artifact_type=art_type,
                    module_name=ForensicModuleName.MODULE_F_SIGNATURE_STAMP.value,
                    title=f"Page {pg_num} {r_type.replace('_', ' ').title()} Evidence Crop",
                    description=(
                        f"Isolated visual crop of {r_type} at [{round(x0_pt, 1)}, {round(y0_pt, 1)}, "
                        f"{round(x1_pt, 1)}, {round(y1_pt, 1)}] ({composition_mode})."
                    ),
                    mime_type="image/png",
                    png_bytes=crop_bytes,
                    sha256_hash=hashlib.sha256(crop_bytes).hexdigest(),
                    is_derived_from_pdf_render=is_pdf,
                    parameters={
                        "region_type": r_type,
                        "composition_mode": composition_mode,
                        "bounding_box": [round(x0_pt, 2), round(y0_pt, 2), round(x1_pt, 2), round(y1_pt, 2)],
                    },
                    stats={
                        "region_background_luminance": round(crop_bg_lum, 2),
                        "page_background_luminance": round(page_bg_lum, 2),
                        "background_luminance_delta": bg_delta,
                        "ink_coverage_ratio": round(crop_ink_ratio, 4),
                    },
                )
            )

            sev = (
                ForensicFindingSeverity.MEDIUM.value
                if (composition_mode == "EMBEDDED_RASTER_XOBJECT_IN_PDF" or bg_delta >= 12.0)
                else ForensicFindingSeverity.INFORMATIONAL.value
            )
            findings.append(
                GeneratedForensicFinding(
                    finding_id=str(uuid.uuid4()),
                    module_name=ForensicModuleName.MODULE_F_SIGNATURE_STAMP.value,
                    finding_category=f"{r_type}_FORENSIC_INSPECTION",
                    severity=sev,
                    title=f"{r_type.replace('_', ' ').title()} Inspection ({composition_mode})",
                    observation=(
                        f"Analyzed {r_type} on page {pg_num} at [{round(x0_pt, 1)}, {round(y0_pt, 1)}, "
                        f"{round(x1_pt, 1)}, {round(y1_pt, 1)}] (size: {round(x1_pt - x0_pt, 1)}x{round(y1_pt - y0_pt, 1)}). "
                        f"Composition: {composition_mode}; local background luminance delta={bg_delta} vs surrounding page; "
                        f"ink density={round(crop_ink_ratio * 100, 1)}%."
                    ),
                    technical_explanation=(
                        "Signature and stamp regions are inspected for whether they are rendered via native PDF vector paths/text, "
                        "inserted as an independent raster XObject bitmap, or captured as part of a full-page raster scan, and whether "
                        "their local background luminance matches surrounding paper."
                    ),
                    possible_benign_explanations=[
                        "Digital approval stamps and facsimile signatures are routinely applied by ERP/accounting systems.",
                        "Colored stamp ink naturally alters local 85th-percentile luminance within a tight bounding box.",
                    ],
                    confidence_score=0.92,
                    confidence_interpretation="High technical reliability for region localization and composition mode.",
                    limitations=(
                        "IMPORTANT: Visual inspection of a signature or stamp region cannot verify a person's identity, "
                        "handwriting authenticity, or legal authority."
                    ),
                    page_number=pg_num,
                    bounding_box={
                        "x0": round(x0_pt, 2),
                        "y0": round(y0_pt, 2),
                        "x1": round(x1_pt, 2),
                        "y1": round(y1_pt, 2),
                        "page_width": page_w,
                        "page_height": page_h,
                    },
                    evidence_reference=f"doc:{document_id}#page:{pg_num}@{r_type.lower()}:[{round(x0_pt,2)},{round(y0_pt,2)},{round(x1_pt,2)},{round(y1_pt,2)}]",
                    artifact_id=art_id,
                    analysis_parameters={"inspector": "Signature & Stamp Composition Analyzer"},
                    evidence_metrics={
                        "composition_mode": composition_mode,
                        "background_luminance_delta": bg_delta,
                        "ink_coverage_ratio": round(crop_ink_ratio, 4),
                        "region_text": str(reg.get("text_content", "")),
                    },
                    recommended_human_action=(
                        "Inspect the isolated crop artifact and compare the signatory/stamp details against authorized corporate specimen records."
                    ),
                )
            )

        return artifacts, findings

    # =========================================================================
    # MODULE G IMPLEMENTATION: TEXT-TO-VISUAL CONSISTENCY
    # =========================================================================
    @staticmethod
    def _run_module_g_text_to_visual(
        document_id: str,
        is_pdf: bool,
        pdf_doc: Optional[fitz.Document],
        pages_db_data: List[Dict[str, Any]],
        tables_db: List[Dict[str, Any]],
        entities_db: List[Dict[str, Any]],
        page_renders: Dict[int, Tuple[Image.Image, float, float]],
    ) -> List[GeneratedForensicFinding]:
        findings: List[GeneratedForensicFinding] = []

        for pg_data in pages_db_data:
            pg_num = int(pg_data.get("page_number", 1))
            ext_method = str(pg_data.get("extraction_method", "NATIVE_PDF"))
            blocks = pg_data.get("extractions", [])
            if pg_num not in page_renders:
                continue

            pil_img, page_w, page_h = page_renders[pg_num]
            np_gray = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
            img_h, img_w = np_gray.shape[:2]
            scale_x = float(img_w) / max(1.0, page_w)
            scale_y = float(img_h) / max(1.0, page_h)

            if is_pdf and ext_method == "NATIVE_PDF":
                # 1. Check whether any native PDF text span or block is visually invisible/occluded on the rendered page
                if pdf_doc is not None and pg_num <= len(pdf_doc):
                    page = pdf_doc[pg_num - 1]
                    for blk in page.get_text("dict").get("blocks", []):
                        if blk.get("type") != 0:
                            continue
                        for line in blk.get("lines", []):
                            for sp in line.get("spans", []):
                                txt = str(sp.get("text", "")).strip()
                                if len(txt) < 3:
                                    continue
                                sb = sp.get("bbox", (0.0, 0.0, 0.0, 0.0))
                                bx0, by0 = round(float(sb[0]), 2), round(float(sb[1]), 2)
                                bx1, by1 = round(float(sb[2]), 2), round(float(sb[3]), 2)
                                px0 = max(0, int(round(bx0 * scale_x)))
                                py0 = max(0, int(round(by0 * scale_y)))
                                px1 = min(img_w, int(round(bx1 * scale_x)))
                                py1 = min(img_h, int(round(by1 * scale_y)))
                                if px1 > px0 + 2 and py1 > py0 + 2:
                                    patch = np_gray[py0:py1, px0:px1]
                                    contrast_std = float(np.std(patch))
                                    if contrast_std < 2.5:
                                        findings.append(
                                            GeneratedForensicFinding(
                                                finding_id=str(uuid.uuid4()),
                                                module_name=ForensicModuleName.MODULE_G_TEXT_VISUAL.value,
                                                finding_category="OCCLUDED_OR_ZERO_CONTRAST_NATIVE_TEXT",
                                                severity=ForensicFindingSeverity.HIGH.value,
                                                title=f"Visually Occluded or Zero-Contrast Native PDF Text ('{txt[:32]}')",
                                                observation=(
                                                    f"Native PDF stream on page {pg_num} contains text span '{txt}' at "
                                                    f"[{bx0}, {by0}, {bx1}, {by1}], but the rendered visual page region has "
                                                    f"near-zero pixel contrast (luminance std={round(contrast_std, 2)}) and is invisible to Visual OCR."
                                                ),
                                                technical_explanation=(
                                                    "Text exists in the underlying PDF content stream (extractable by native PDF parsers) "
                                                    "but is either colored identical to the background or occluded by an opaque vector shape."
                                                ),
                                                possible_benign_explanations=[
                                                    "Invisible OCR text layer embedded by a scanner over a background image.",
                                                    "Template placeholder text covered by a header graphic in an automated PDF export.",
                                                ],
                                                confidence_score=0.95,
                                                confidence_interpretation="Direct comparison of PDF text span coordinates against rendered pixel contrast and Visual OCR.",
                                                limitations="Cannot determine author intent without inspecting the surrounding document context.",
                                                page_number=pg_num,
                                                bounding_box={
                                                    "x0": bx0,
                                                    "y0": by0,
                                                    "x1": bx1,
                                                    "y1": by1,
                                                    "page_width": page_w,
                                                    "page_height": page_h,
                                                },
                                                evidence_reference=f"doc:{document_id}#page:{pg_num}@occluded_text:[{bx0},{by0},{bx1},{by1}]",
                                                artifact_id=None,
                                                analysis_parameters={"min_contrast_std_threshold": 2.5},
                                                evidence_metrics={
                                                    "native_text": txt,
                                                    "rendered_luminance_std": round(contrast_std, 2),
                                                    "span_color_int": int(sp.get("color", 0)),
                                                },
                                                recommended_human_action="Compare the Raw Text & Font Stream tab against the Page Preview at these coordinates.",
                                            )
                                        )

                # 2. Run Visual OCR on Page 1 of the rendered PDF and compare numeric/key tokens against Native PDF text
                if pg_num == 1 and settings.enable_ocr_pipeline:
                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    ocr_page = _run_visual_ocr_on_image_bytes(
                        image_bytes=buf.getvalue(),
                        document_id=document_id,
                        page_number=pg_num,
                        target_width=page_w,
                        target_height=page_h,
                    )
                    # Check if any high-confidence OCR block overlaps native blocks but has materially different numeric digits
                    for ocr_b in ocr_page.blocks:
                        if ocr_b.confidence < 0.90:
                            continue
                        ocr_digits = re.sub(r"[^0-9]", "", ocr_b.extracted_text)
                        if len(ocr_digits) < 3:
                            continue
                        overlapping_nats = [
                            nat_b
                            for nat_b in blocks
                            if _bbox_iou_or_overlap(
                                ocr_b.bounding_box, nat_b.get("bounding_box", {})
                            )
                            >= 0.35
                        ]
                        if not overlapping_nats:
                            continue
                        combined_nat_txt = " ".join(
                            str(nb.get("extracted_text", "")) for nb in overlapping_nats
                        )
                        combined_nat_digits = re.sub(r"[^0-9]", "", combined_nat_txt)
                        if (
                            combined_nat_digits
                            and ocr_digits not in combined_nat_digits
                            and combined_nat_digits not in ocr_digits
                        ):
                            nat_txt = combined_nat_txt
                            if True:
                                if True:
                                    findings.append(
                                        GeneratedForensicFinding(
                                            finding_id=str(uuid.uuid4()),
                                            module_name=ForensicModuleName.MODULE_G_TEXT_VISUAL.value,
                                            finding_category="NATIVE_VS_VISUAL_OCR_DISCREPANCY",
                                            severity=ForensicFindingSeverity.HIGH.value,
                                            title="Disagreement Between Native PDF Stream and Visible Rendered Text",
                                            observation=(
                                                f"At coordinates [{ocr_b.bounding_box['x0']}, {ocr_b.bounding_box['y0']}, "
                                                f"{ocr_b.bounding_box['x1']}, {ocr_b.bounding_box['y1']}], Native PDF extraction "
                                                f"read '{nat_txt}' while Visual OCR on the rendered page read '{ocr_b.extracted_text}' "
                                                f"(OCR confidence: {round(ocr_b.confidence * 100, 1)}%)."
                                            ),
                                            technical_explanation=(
                                                "Cross-stream verification runs optical character recognition on the rendered page "
                                                "and compares the visible characters against the underlying PDF character codes. Discrepancies "
                                                "can occur when vector paths/images overlay native text or custom font ToUnicode CMap mappings differ."
                                            ),
                                            possible_benign_explanations=[
                                                "Optical character recognition misread a stylized font, currency symbol, or tightly kerned digit.",
                                                "PDF subset font ToUnicode table mapping nuance.",
                                            ],
                                            confidence_score=round(float(ocr_b.confidence), 4),
                                            confidence_interpretation="Cross-stream comparison weighted by OCR token recognition confidence.",
                                            limitations="OCR misclassifications on small or stylized fonts can trigger false discrepancies; always verify visually.",
                                            page_number=pg_num,
                                            bounding_box=ocr_b.bounding_box,
                                            evidence_reference=f"doc:{document_id}#page:{pg_num}@text_visual_diff:[{ocr_b.bounding_box['x0']},{ocr_b.bounding_box['y0']}]",
                                            artifact_id=None,
                                            analysis_parameters={"cross_check_engine": "PyMuPDF Native vs PaddleOCR PP-OCRv4"},
                                            evidence_metrics={
                                                "native_pdf_text": nat_txt,
                                                "visual_ocr_text": ocr_b.extracted_text,
                                                "ocr_confidence": ocr_b.confidence,
                                            },
                                            recommended_human_action="Inspect the visible text in the Page Preview and verify both original extraction outputs.",
                                        )
                                    )
            else:
                # Scanned document: identify any OCR blocks with uncertain extraction confidence (< 0.88)
                low_conf_blocks = [
                    b for b in blocks if float(b.get("confidence", 1.0)) < 0.88
                ]
                if low_conf_blocks:
                    lowest = min(low_conf_blocks, key=lambda x: float(x.get("confidence", 1.0)))
                    l_bb = lowest.get("bounding_box", {})
                    l_conf = float(lowest.get("confidence", 0.0))
                    findings.append(
                        GeneratedForensicFinding(
                            finding_id=str(uuid.uuid4()),
                            module_name=ForensicModuleName.MODULE_G_TEXT_VISUAL.value,
                            finding_category="UNCERTAIN_OCR_EXTRACTION_REGION",
                            severity=ForensicFindingSeverity.LOW.value,
                            title=f"Uncertain Visual OCR Extraction Region ({round(l_conf * 100, 1)}% Confidence)",
                            observation=(
                                f"On scanned page {pg_num}, {len(low_conf_blocks)} OCR text block(s) exhibited confidence below 88%. "
                                f"Lowest-confidence block '{lowest.get('extracted_text')}' scored {round(l_conf * 100, 1)}% at "
                                f"[{l_bb.get('x0')}, {l_bb.get('y0')}, {l_bb.get('x1')}, {l_bb.get('y1')}]."
                            ),
                            technical_explanation=(
                                "VERITAS AI preserves raw OCR outputs without silently guessing or auto-correcting uncertain tokens. "
                                "Low OCR confidence indicates blurred scan resolution, overlapping stamp ink, or unusual kerning."
                            ),
                            possible_benign_explanations=[
                                "Normal optical scan blur, tight character kerning, or stamp overlap.",
                            ],
                            confidence_score=round(l_conf, 4),
                            confidence_interpretation="Direct PP-OCRv4 recognition confidence score for the flagged text block.",
                            limitations="Low OCR confidence reflects optical legibility, never document fraud.",
                            page_number=pg_num,
                            bounding_box={
                                "x0": float(l_bb.get("x0", 0.0)),
                                "y0": float(l_bb.get("y0", 0.0)),
                                "x1": float(l_bb.get("x1", 0.0)),
                                "y1": float(l_bb.get("y1", 0.0)),
                                "page_width": page_w,
                                "page_height": page_h,
                            },
                            evidence_reference=f"doc:{document_id}#page:{pg_num}@low_ocr_conf:[{l_bb.get('x0')},{l_bb.get('y0')}]",
                            artifact_id=None,
                            analysis_parameters={"ocr_uncertainty_threshold": 0.88},
                            evidence_metrics={
                                "uncertain_block_count": len(low_conf_blocks),
                                "lowest_confidence_text": lowest.get("extracted_text"),
                                "lowest_confidence_score": round(l_conf, 4),
                            },
                            recommended_human_action="Visually read the highlighted region on the original page preview to confirm the exact characters.",
                        )
                    )

        # Also check extracted tables for empty cells that still show visible ink density
        for tbl in tables_db:
            pg_num = int(tbl.get("page_number", 1))
            if pg_num not in page_renders:
                continue
            pil_img, page_w, page_h = page_renders[pg_num]
            np_gray = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
            img_h, img_w = np_gray.shape[:2]
            scale_x = float(img_w) / max(1.0, page_w)
            scale_y = float(img_h) / max(1.0, page_h)

            for cell in tbl.get("cells", []):
                c_txt = str(cell.get("cell_text", "")).strip()
                if c_txt:
                    continue
                cbb = cell.get("bounding_box", {})
                cx0 = max(0, int(round(float(cbb.get("x0", 0.0)) * scale_x)) + 4)
                cy0 = max(0, int(round(float(cbb.get("y0", 0.0)) * scale_y)) + 4)
                cx1 = min(img_w, int(round(float(cbb.get("x1", 0.0)) * scale_x)) - 4)
                cy1 = min(img_h, int(round(float(cbb.get("y1", 0.0)) * scale_y)) - 4)
                if cx1 > cx0 + 4 and cy1 > cy0 + 4:
                    patch = np_gray[cy0:cy1, cx0:cx1]
                    ink_ratio = float(np.mean(patch < 200))
                    if ink_ratio > 0.04:
                        findings.append(
                            GeneratedForensicFinding(
                                finding_id=str(uuid.uuid4()),
                                module_name=ForensicModuleName.MODULE_G_TEXT_VISUAL.value,
                                finding_category="TABLE_CELL_EXTRACTION_DISCREPANCY",
                                severity=ForensicFindingSeverity.MEDIUM.value,
                                title=f"Visible Content in Unextracted Table Cell (Row {cell['row_index'] + 1}, Col {cell['col_index'] + 1})",
                                observation=(
                                    f"Table {tbl.get('table_identifier')} cell at row {cell['row_index'] + 1}, col {cell['col_index'] + 1} "
                                    f"returned an empty string during extraction, but the rendered cell interior shows "
                                    f"{round(ink_ratio * 100, 1)}% dark pixel density."
                                ),
                                technical_explanation=(
                                    "Visible markings inside a table cell that do not appear in extracted cell text may be "
                                    "handwritten annotations, vector symbols, or text positioned slightly outside the cell clipping box."
                                ),
                                possible_benign_explanations=[
                                    "Checkmark, dash, or graphic icon inside the table cell.",
                                    "Cell border line encroaching into the interior crop margin.",
                                ],
                                confidence_score=0.85,
                                confidence_interpretation="Direct pixel ink-density check inside extracted table cell coordinates.",
                                limitations="Does not interpret the semantic meaning of the non-extracted marking.",
                                page_number=pg_num,
                                bounding_box={
                                    "x0": float(cbb.get("x0", 0.0)),
                                    "y0": float(cbb.get("y0", 0.0)),
                                    "x1": float(cbb.get("x1", 0.0)),
                                    "y1": float(cbb.get("y1", 0.0)),
                                    "page_width": page_w,
                                    "page_height": page_h,
                                },
                                evidence_reference=f"doc:{document_id}#page:{pg_num}@table_cell:r{cell['row_index']}_c{cell['col_index']}",
                                artifact_id=None,
                                analysis_parameters={"min_ink_density_ratio": 0.04},
                                evidence_metrics={
                                    "table_identifier": tbl.get("table_identifier"),
                                    "row_index": cell["row_index"],
                                    "col_index": cell["col_index"],
                                    "interior_ink_ratio": round(ink_ratio, 4),
                                },
                                recommended_human_action="Inspect the highlighted table cell in the Visual Evidence Viewer.",
                            )
                        )

        return findings
