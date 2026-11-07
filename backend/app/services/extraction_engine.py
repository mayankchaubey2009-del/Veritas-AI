import io
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import fitz  # PyMuPDF
from PIL import Image
from app.core.config import settings

# Prevent Paddle / OpenMP thread contention on macOS arm64
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "2")

_OCR_LOCK = threading.Lock()
_OCR_INSTANCE: Any = None
_OCR_BACKEND_TYPE: Optional[str] = None


@dataclass
class ExtractedBlockData:
    page_number: int
    block_index: int
    extracted_text: str
    field_name: Optional[str]
    field_value: Optional[str]
    bounding_box: Dict[str, float]
    extraction_method: str  # "NATIVE_PDF" | "VISUAL_OCR"
    confidence: float
    source_reference: str
    font_name: Optional[str] = None
    font_size: Optional[float] = None


@dataclass
class ExtractedPageData:
    page_number: int
    width: float
    height: float
    extraction_method: str  # "NATIVE_PDF" | "VISUAL_OCR"
    is_scanned_page: bool
    raw_text: str
    char_count: int
    block_count: int
    average_confidence: float
    fonts: List[Dict[str, Any]] = field(default_factory=list)
    blocks: List[ExtractedBlockData] = field(default_factory=list)


@dataclass
class DocumentExtractionResult:
    page_count: int
    extraction_method_summary: str  # "NATIVE_PDF" | "VISUAL_OCR" | "HYBRID_PDF_OCR"
    is_scanned: bool
    average_confidence: float
    extracted_char_count: int
    pages: List[ExtractedPageData] = field(default_factory=list)


# Deterministic key-value patterns for structured forensic field tagging
STRUCTURED_FIELD_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "INVOICE_NUMBER",
        re.compile(
            r"(?:invoice\s*(?:no\.?|number|#|id))\s*[:\-]?\s*([A-Z0-9\-\/]{3,40})",
            re.IGNORECASE,
        ),
    ),
    (
        "CONTRACT_REFERENCE",
        re.compile(
            r"(?:contract\s*(?:no\.?|number|#|ref|id)|agreement\s*(?:no\.?|id))\s*[:\-]?\s*([A-Z0-9\-\/]{3,40})",
            re.IGNORECASE,
        ),
    ),
    (
        "PURCHASE_ORDER",
        re.compile(
            r"(?:p\.?o\.?\s*(?:no\.?|number|#)|purchase\s*order)\s*[:\-]?\s*([A-Z0-9\-\/]{3,40})",
            re.IGNORECASE,
        ),
    ),
    (
        "DOCUMENT_DATE",
        re.compile(
            r"(?:date|issued\s*on|effective\s*date|invoice\s*date|billing\s*date)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
            re.IGNORECASE,
        ),
    ),
    (
        "SUBTOTAL_AMOUNT",
        re.compile(
            r"\b(?:subtotal|sub-total)\s*[:\-]?\s*([\$€£¥₹]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?:\s*(?:USD|EUR|GBP|INR))?)",
            re.IGNORECASE,
        ),
    ),
    (
        "TOTAL_AMOUNT",
        re.compile(
            r"\b(?:total\s*(?:amount|due|payable)?|grand\s*total|balance\s*due|net\s*amount)\s*[:\-]?\s*([\$€£¥₹]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?:\s*(?:USD|EUR|GBP|INR))?)",
            re.IGNORECASE,
        ),
    ),
    (
        "TAX_AMOUNT",
        re.compile(
            r"(?:tax|vat|gst)\s*(?:\(\d+%?\))?\s*[:\-]?\s*([\$€£¥₹]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
            re.IGNORECASE,
        ),
    ),
    (
        "VENDOR_ENTITY",
        re.compile(
            r"(?:vendor|supplier|seller|issued\s*by|beneficiary)\s*[:\-]\s*([^\n\r]{2,80})",
            re.IGNORECASE,
        ),
    ),
    (
        "CLIENT_ENTITY",
        re.compile(
            r"(?:client|customer|bill\s*to|buyer|recipient)\s*[:\-]\s*([^\n\r]{2,80})",
            re.IGNORECASE,
        ),
    ),
    (
        "TAX_OR_REG_ID",
        re.compile(
            r"(?:tax\s*id|ein|vat\s*reg|registration\s*no\.?)\s*[:\-]?\s*([A-Z0-9\-]{5,30})",
            re.IGNORECASE,
        ),
    ),
    (
        "AUTHORIZED_SIGNATORY",
        re.compile(
            r"(?:authorized\s*signatory|signed\s*by|approved\s*by)\s*[:\-]\s*([^\n\r]{2,70})",
            re.IGNORECASE,
        ),
    ),
]

GENERIC_KV_PATTERN = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9\s\/\_\-]{1,32})\s*:\s*([^\n\r]{1,120})\s*$"
)


def detect_structured_field(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Deterministically extracts a structured (field_name, field_value) pair from a text block
    if an explicit label/value pattern is present. Never guesses or fabricates values.
    """
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return None, None

    for field_name, pattern in STRUCTURED_FIELD_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            val = match.group(1).strip()
            if val:
                return field_name, val

    # Check single-line explicit "Label: Value" format
    if "\n" not in text.strip():
        kv_match = GENERIC_KV_PATTERN.match(cleaned)
        if kv_match:
            raw_key = kv_match.group(1).strip().upper()
            normalized_key = re.sub(r"[^A-Z0-9]+", "_", raw_key).strip("_")
            val = kv_match.group(2).strip()
            if 2 <= len(normalized_key) <= 32 and val:
                return normalized_key, val

    return None, None


def _get_ocr_engine() -> Tuple[Any, str]:
    """
    Lazy-initializes the PaddleOCR / PP-OCRv4 engine.
    Prefers RapidOCR (PP-OCRv4 ONNX Runtime bundled models) or PaddleOCR native engine.
    """
    global _OCR_INSTANCE, _OCR_BACKEND_TYPE
    with _OCR_LOCK:
        if _OCR_INSTANCE is not None and _OCR_BACKEND_TYPE is not None:
            return _OCR_INSTANCE, _OCR_BACKEND_TYPE

        # 1. Try RapidOCR (PaddleOCR PP-OCRv4 models running on ONNXRuntime — zero external download failure risk)
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            _OCR_INSTANCE = RapidOCR()
            _OCR_BACKEND_TYPE = "PADDLE_PPOCRV4_ONNX"
            return _OCR_INSTANCE, _OCR_BACKEND_TYPE
        except Exception:
            pass

        # 2. Try native PaddleOCR package
        try:
            from paddleocr import PaddleOCR  # type: ignore

            _OCR_INSTANCE = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            _OCR_BACKEND_TYPE = "PADDLEOCR_NATIVE"
            return _OCR_INSTANCE, _OCR_BACKEND_TYPE
        except Exception as exc:
            raise RuntimeError(
                f"Visual OCR engine (PaddleOCR) could not be initialized: {exc}"
            ) from exc


def _run_visual_ocr_on_image_bytes(
    image_bytes: bytes,
    document_id: str,
    page_number: int,
    target_width: Optional[float] = None,
    target_height: Optional[float] = None,
) -> ExtractedPageData:
    """
    PATH B: VISUAL OCR
    Runs PaddleOCR (PP-OCRv4) on a raster image (PNG/JPG or rendered scanned PDF page),
    preserving exact bounding boxes, OCR confidence scores, and page dimensions.
    Never modifies or replaces low-confidence OCR tokens with guesses.
    """
    with Image.open(io.BytesIO(image_bytes)) as pil_img:
        rgb_img = pil_img.convert("RGB")
        img_w, img_h = float(rgb_img.width), float(rgb_img.height)
        buf = io.BytesIO()
        rgb_img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

    page_w = target_width if target_width and target_width > 0 else img_w
    page_h = target_height if target_height and target_height > 0 else img_h
    scale_x = page_w / img_w if img_w > 0 else 1.0
    scale_y = page_h / img_h if img_h > 0 else 1.0

    ocr_engine, backend_type = _get_ocr_engine()

    raw_detections: List[Tuple[List[List[float]], str, float]] = []

    if backend_type == "PADDLE_PPOCRV4_ONNX":
        result, _elapse = ocr_engine(png_bytes)
        if result:
            for item in result:
                # item format: [ [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, confidence ]
                box_pts, text_str, score = item[0], str(item[1]), float(item[2])
                raw_detections.append((box_pts, text_str, score))
    else:
        import numpy as np

        with Image.open(io.BytesIO(png_bytes)) as im_arr:
            np_img = np.array(im_arr)
        result = ocr_engine.ocr(np_img, cls=True)
        if result and result[0]:
            for line in result[0]:
                box_pts = line[0]
                text_str = str(line[1][0])
                score = float(line[1][1])
                raw_detections.append((box_pts, text_str, score))

    blocks: List[ExtractedBlockData] = []
    text_lines: List[str] = []
    confidences: List[float] = []

    for idx, (pts, text_val, conf_val) in enumerate(raw_detections):
        cleaned_text = text_val.strip()
        if not cleaned_text:
            continue

        xs = [float(p[0]) * scale_x for p in pts]
        ys = [float(p[1]) * scale_y for p in pts]
        x0 = round(max(0.0, min(xs)), 2)
        y0 = round(max(0.0, min(ys)), 2)
        x1 = round(min(page_w, max(xs)), 2)
        y1 = round(min(page_h, max(ys)), 2)

        conf = round(max(0.0, min(1.0, float(conf_val))), 4)
        field_name, field_value = detect_structured_field(cleaned_text)

        bbox = {
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "page_width": round(page_w, 2),
            "page_height": round(page_h, 2),
        }
        source_ref = (
            f"doc:{document_id}#page:{page_number}@bbox:[{x0},{y0},{x1},{y1}]"
        )

        blocks.append(
            ExtractedBlockData(
                page_number=page_number,
                block_index=idx,
                extracted_text=cleaned_text,
                field_name=field_name,
                field_value=field_value,
                bounding_box=bbox,
                extraction_method="VISUAL_OCR",
                confidence=conf,
                source_reference=source_ref,
                font_name=None,
                font_size=None,
            )
        )
        text_lines.append(cleaned_text)
        confidences.append(conf)

    raw_text = "\n".join(text_lines)
    avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

    return ExtractedPageData(
        page_number=page_number,
        width=round(page_w, 2),
        height=round(page_h, 2),
        extraction_method="VISUAL_OCR",
        is_scanned_page=True,
        raw_text=raw_text,
        char_count=len(raw_text),
        block_count=len(blocks),
        average_confidence=avg_conf,
        fonts=[],
        blocks=blocks,
    )


def _extract_native_pdf_page(
    page: fitz.Page, document_id: str, page_number: int
) -> Tuple[ExtractedPageData, int]:
    """
    PATH A: NATIVE PDF EXTRACTION
    Uses PyMuPDF (fitz) to extract vector text blocks, bounding boxes, page dimensions,
    and font metadata (font names and sizes).
    Returns (ExtractedPageData, non_whitespace_char_count).
    """
    rect = page.rect
    page_w = round(float(rect.width), 2)
    page_h = round(float(rect.height), 2)

    page_dict = page.get_text("dict")
    raw_blocks = page_dict.get("blocks", [])

    font_counter: Dict[Tuple[str, float], int] = {}
    extracted_blocks: List[ExtractedBlockData] = []
    page_lines: List[str] = []
    block_idx = 0

    for blk in raw_blocks:
        # type 0 = text block in PyMuPDF
        if blk.get("type") != 0:
            continue

        blk_bbox = blk.get("bbox", (0.0, 0.0, 0.0, 0.0))
        x0 = round(float(blk_bbox[0]), 2)
        y0 = round(float(blk_bbox[1]), 2)
        x1 = round(float(blk_bbox[2]), 2)
        y1 = round(float(blk_bbox[3]), 2)

        block_text_lines: List[str] = []
        dominant_font: Optional[str] = None
        dominant_size: Optional[float] = None
        max_span_len = -1

        for line in blk.get("lines", []):
            line_parts: List[str] = []
            for span in line.get("spans", []):
                span_text = str(span.get("text", ""))
                if not span_text.strip():
                    continue
                line_parts.append(span_text)

                f_name = str(span.get("font", "UnknownFont")).strip() or "UnknownFont"
                f_size = round(float(span.get("size", 0.0)), 2)
                font_counter[(f_name, f_size)] = (
                    font_counter.get((f_name, f_size), 0) + 1
                )

                if len(span_text) > max_span_len:
                    max_span_len = len(span_text)
                    dominant_font = f_name
                    dominant_size = f_size

            if line_parts:
                block_text_lines.append("".join(line_parts).strip())

        full_block_text = "\n".join(block_text_lines).strip()
        if not full_block_text:
            continue

        # Check structured fields across individual lines or the whole block
        field_name, field_value = detect_structured_field(full_block_text)
        if not field_name and len(block_text_lines) > 1:
            for single_line in block_text_lines:
                fn, fv = detect_structured_field(single_line)
                if fn:
                    field_name, field_value = fn, fv
                    break

        bbox_dict = {
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "page_width": page_w,
            "page_height": page_h,
        }
        source_ref = (
            f"doc:{document_id}#page:{page_number}@bbox:[{x0},{y0},{x1},{y1}]"
        )

        extracted_blocks.append(
            ExtractedBlockData(
                page_number=page_number,
                block_index=block_idx,
                extracted_text=full_block_text,
                field_name=field_name,
                field_value=field_value,
                bounding_box=bbox_dict,
                extraction_method="NATIVE_PDF",
                confidence=1.0,
                source_reference=source_ref,
                font_name=dominant_font,
                font_size=dominant_size,
            )
        )
        page_lines.append(full_block_text)
        block_idx += 1

    raw_text = "\n\n".join(page_lines)
    non_ws_chars = len("".join(raw_text.split()))

    fonts_list = [
        {"font_name": f_name, "font_size": f_size, "span_count": cnt}
        for (f_name, f_size), cnt in sorted(
            font_counter.items(), key=lambda x: (-x[1], x[0][0])
        )
    ]

    page_data = ExtractedPageData(
        page_number=page_number,
        width=page_w,
        height=page_h,
        extraction_method="NATIVE_PDF",
        is_scanned_page=False,
        raw_text=raw_text,
        char_count=len(raw_text),
        block_count=len(extracted_blocks),
        average_confidence=1.0 if extracted_blocks else 0.0,
        fonts=fonts_list,
        blocks=extracted_blocks,
    )
    return page_data, non_ws_chars


class DualPathExtractionEngine:
    """
    VERITAS AI Phase 2A Dual-Path Document Intelligence Engine.
    - Path A: Native PDF vector text, bounding box, and font metadata extraction via PyMuPDF.
    - Path B: Visual OCR via PaddleOCR (PP-OCRv4) for scanned PDFs and raster images (PNG/JPG/JPEG).
    """

    @staticmethod
    def extract_document(
        file_bytes: bytes, file_type: str, document_id: str
    ) -> DocumentExtractionResult:
        normalized_type = file_type.upper().lstrip(".")

        if normalized_type == "PDF":
            return DualPathExtractionEngine._process_pdf(file_bytes, document_id)
        elif normalized_type in ("PNG", "JPG", "JPEG"):
            return DualPathExtractionEngine._process_image(file_bytes, document_id)
        else:
            raise ValueError(f"Unsupported document file_type: {file_type}")

    @staticmethod
    def _process_pdf(
        file_bytes: bytes, document_id: str
    ) -> DocumentExtractionResult:
        pages_output: List[ExtractedPageData] = []
        methods_used = set()
        any_scanned = False

        with fitz.open(stream=file_bytes, filetype="pdf") as pdf_doc:
            total_pages = len(pdf_doc)
            if total_pages == 0:
                return DocumentExtractionResult(
                    page_count=0,
                    extraction_method_summary="NATIVE_PDF",
                    is_scanned=False,
                    average_confidence=0.0,
                    extracted_char_count=0,
                    pages=[],
                )

            for page_idx in range(total_pages):
                page_number = page_idx + 1
                page = pdf_doc[page_idx]

                native_page, non_ws_chars = _extract_native_pdf_page(
                    page, document_id, page_number
                )

                # Scanned PDF page detection: if little or no extractable vector text,
                # route this page through Path B (Visual OCR)
                if non_ws_chars < settings.native_pdf_min_chars_per_page:
                    any_scanned = True
                    pix = page.get_pixmap(dpi=200, alpha=False)
                    png_bytes = pix.tobytes("png")
                    ocr_page = _run_visual_ocr_on_image_bytes(
                        image_bytes=png_bytes,
                        document_id=document_id,
                        page_number=page_number,
                        target_width=float(page.rect.width),
                        target_height=float(page.rect.height),
                    )
                    # If OCR found text or if native had 0 chars, use the OCR page result
                    if ocr_page.char_count > 0 or non_ws_chars == 0:
                        pages_output.append(ocr_page)
                        methods_used.add("VISUAL_OCR")
                    else:
                        native_page.is_scanned_page = True
                        pages_output.append(native_page)
                        methods_used.add("NATIVE_PDF")
                else:
                    pages_output.append(native_page)
                    methods_used.add("NATIVE_PDF")

        if methods_used == {"NATIVE_PDF"}:
            summary_method = "NATIVE_PDF"
        elif methods_used == {"VISUAL_OCR"}:
            summary_method = "VISUAL_OCR"
        else:
            summary_method = "HYBRID_PDF_OCR"

        total_chars = sum(p.char_count for p in pages_output)
        all_block_confs = [
            b.confidence for p in pages_output for b in p.blocks
        ]
        if all_block_confs:
            avg_conf = round(sum(all_block_confs) / len(all_block_confs), 4)
        else:
            page_confs = [p.average_confidence for p in pages_output if p.block_count > 0]
            avg_conf = (
                round(sum(page_confs) / len(page_confs), 4) if page_confs else 0.0
            )

        return DocumentExtractionResult(
            page_count=len(pages_output),
            extraction_method_summary=summary_method,
            is_scanned=any_scanned,
            average_confidence=avg_conf,
            extracted_char_count=total_chars,
            pages=pages_output,
        )

    @staticmethod
    def _process_image(
        file_bytes: bytes, document_id: str
    ) -> DocumentExtractionResult:
        ocr_page = _run_visual_ocr_on_image_bytes(
            image_bytes=file_bytes,
            document_id=document_id,
            page_number=1,
        )
        return DocumentExtractionResult(
            page_count=1,
            extraction_method_summary="VISUAL_OCR",
            is_scanned=True,
            average_confidence=ocr_page.average_confidence,
            extracted_char_count=ocr_page.char_count,
            pages=[ocr_page],
        )
