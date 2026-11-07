from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Tuple
import cv2
import fitz  # PyMuPDF
import numpy as np
from app.services.extraction_engine import DocumentExtractionResult, ExtractedBlockData, ExtractedPageData


DISPLAY_LABELS: Dict[str, str] = {
    "COMMERCIAL_INVOICE": "Commercial Invoice",
    "BANK_STATEMENT": "Bank Statement",
    "TAX_CERTIFICATE": "Tax Certificate",
    "IDENTITY_DOCUMENT": "Identity Document",
    "RECEIPT": "Receipt",
    "CONTRACT": "Contract",
    "APPLICATION_FORM": "Application Form",
    "OTHER_UNKNOWN": "Other / Unknown",
}


@dataclass
class LayoutRegionData:
    id: str
    page_number: int
    region_type: str
    reading_order: int
    parent_region_id: Optional[str]
    label: str
    text_content: str
    bounding_box: Dict[str, float]
    extraction_method: str
    confidence: float


@dataclass
class TableCellData:
    row_index: int
    col_index: int
    cell_text: str
    is_header: bool
    bounding_box: Dict[str, float]
    confidence: float


@dataclass
class ExtractedTableData:
    id: str
    table_identifier: str
    page_number: int
    row_count: int
    column_count: int
    headers: List[str]
    bounding_box: Dict[str, float]
    extraction_method: str
    confidence: float
    cells: List[TableCellData] = field(default_factory=list)


@dataclass
class ExtractedEntityData:
    page_number: int
    entity_type: str
    raw_value: str
    normalized_value: str
    bounding_box: Dict[str, float]
    extraction_method: str
    confidence: float
    source_reference: str


@dataclass
class ClassificationResultData:
    document_type: str
    display_label: str
    confidence: float
    is_certain: bool
    status_label: str
    signals: List[str] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StructureAnalysisBundle:
    classification: ClassificationResultData
    layout_regions: List[LayoutRegionData] = field(default_factory=list)
    tables: List[ExtractedTableData] = field(default_factory=list)
    entities: List[ExtractedEntityData] = field(default_factory=list)


# ============================================================================
# MODULE 3: TABLE DETECTION & EXTRACTION
# ============================================================================


def _extract_native_pymupdf_tables(
    file_bytes: bytes, page_count: int
) -> Dict[int, List[ExtractedTableData]]:
    """
    Uses PyMuPDF's native `page.find_tables()` to detect vector-bordered tables,
    preserving exact cell coordinates and never inventing missing cell values.
    """
    tables_by_page: Dict[int, List[ExtractedTableData]] = {}
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as pdf_doc:
            for page_idx in range(min(len(pdf_doc), page_count)):
                page_number = page_idx + 1
                page = pdf_doc[page_idx]
                page_w = round(float(page.rect.width), 2)
                page_h = round(float(page.rect.height), 2)

                finder = page.find_tables()
                if not finder or not finder.tables:
                    continue

                page_tables: List[ExtractedTableData] = []
                for t_idx, tbl in enumerate(finder.tables):
                    extracted_rows = tbl.extract()
                    if not extracted_rows or len(extracted_rows) < 2:
                        continue

                    row_count = len(extracted_rows)
                    col_count = max((len(r) for r in extracted_rows), default=0)
                    if col_count < 2:
                        continue

                    tb = tbl.bbox
                    t_bbox = {
                        "x0": round(float(tb[0]), 2),
                        "y0": round(float(tb[1]), 2),
                        "x1": round(float(tb[2]), 2),
                        "y1": round(float(tb[3]), 2),
                        "page_width": page_w,
                        "page_height": page_h,
                    }

                    headers: List[str] = [
                        (str(c).strip().replace("\n", " ") if c is not None else "")
                        for c in extracted_rows[0]
                    ]

                    cells_data: List[TableCellData] = []
                    # Map cell coordinates from tbl.rows if available
                    tbl_rows_meta = getattr(tbl, "rows", [])

                    for r_i, row_vals in enumerate(extracted_rows):
                        row_cells_bbox = (
                            tbl_rows_meta[r_i].cells
                            if r_i < len(tbl_rows_meta)
                            else []
                        )
                        for c_i in range(col_count):
                            raw_val = row_vals[c_i] if c_i < len(row_vals) else ""
                            cell_str = (
                                str(raw_val).strip() if raw_val is not None else ""
                            )

                            if (
                                c_i < len(row_cells_bbox)
                                and row_cells_bbox[c_i] is not None
                            ):
                                cb = row_cells_bbox[c_i]
                                c_bbox = {
                                    "x0": round(float(cb[0]), 2),
                                    "y0": round(float(cb[1]), 2),
                                    "x1": round(float(cb[2]), 2),
                                    "y1": round(float(cb[3]), 2),
                                    "page_width": page_w,
                                    "page_height": page_h,
                                }
                            else:
                                # Proportional cell bounding box within table
                                row_h = (t_bbox["y1"] - t_bbox["y0"]) / max(
                                    1, row_count
                                )
                                col_w = (t_bbox["x1"] - t_bbox["x0"]) / max(
                                    1, col_count
                                )
                                c_bbox = {
                                    "x0": round(t_bbox["x0"] + c_i * col_w, 2),
                                    "y0": round(t_bbox["y0"] + r_i * row_h, 2),
                                    "x1": round(t_bbox["x0"] + (c_i + 1) * col_w, 2),
                                    "y1": round(t_bbox["y0"] + (r_i + 1) * row_h, 2),
                                    "page_width": page_w,
                                    "page_height": page_h,
                                }

                            cells_data.append(
                                TableCellData(
                                    row_index=r_i,
                                    col_index=c_i,
                                    cell_text=cell_str,
                                    is_header=(r_i == 0),
                                    bounding_box=c_bbox,
                                    confidence=1.0,
                                )
                            )

                    page_tables.append(
                        ExtractedTableData(
                            id="",
                            table_identifier=f"TBL-P{page_number}-{t_idx + 1:02d}",
                            page_number=page_number,
                            row_count=row_count,
                            column_count=col_count,
                            headers=headers,
                            bounding_box=t_bbox,
                            extraction_method="NATIVE_PDF",
                            confidence=1.0,
                            cells=cells_data,
                        )
                    )
                if page_tables:
                    tables_by_page[page_number] = page_tables
    except Exception:
        pass
    return tables_by_page


LINE_ITEM_ROW_PATTERN = re.compile(
    r"^(?:line\s*item\s*\d+|item\s*\d+|\d+\.)\s*[:\-]?\s*(.+?)\s+(?:[\-\|]\s*)?([\$€£¥₹]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?)$",
    re.IGNORECASE,
)


def _extract_spatial_or_structured_tables_from_page(
    page_data: ExtractedPageData, existing_count: int = 0
) -> List[ExtractedTableData]:
    """
    Detects tabular structures from coordinate blocks when a document uses
    whitespace-aligned columns (common in bank statements, commercial invoices,
    and scanned OCR documents) or explicit line-item rows.
    Never invents missing cell values.
    """
    blocks = page_data.blocks
    if not blocks:
        return []

    page_w = page_data.width
    page_h = page_data.height
    tables: List[ExtractedTableData] = []

    # Strategy 1: Spatial horizontal row clustering of multi-column blocks (2+ blocks on the same Y band)
    sorted_by_y = sorted(
        blocks, key=lambda b: (b.bounding_box["y0"], b.bounding_box["x0"])
    )
    row_clusters: List[List[ExtractedBlockData]] = []
    y_tolerance = max(8.0, page_h * 0.012)

    for blk in sorted_by_y:
        cy = (blk.bounding_box["y0"] + blk.bounding_box["y1"]) / 2.0
        placed = False
        for cluster in row_clusters:
            ref_cy = (
                cluster[0].bounding_box["y0"] + cluster[0].bounding_box["y1"]
            ) / 2.0
            if abs(cy - ref_cy) <= y_tolerance:
                cluster.append(blk)
                placed = True
                break
        if not placed:
            row_clusters.append([blk])

    # Find contiguous runs of multi-column rows (>= 2 rows where at least 2 rows have >= 2 columns)
    multi_col_runs: List[List[List[ExtractedBlockData]]] = []
    current_run: List[List[ExtractedBlockData]] = []

    for cluster in row_clusters:
        cluster_sorted = sorted(cluster, key=lambda b: b.bounding_box["x0"])
        if len(cluster_sorted) >= 2:
            current_run.append(cluster_sorted)
        else:
            if len(current_run) >= 2:
                multi_col_runs.append(current_run)
            current_run = []
    if len(current_run) >= 2:
        multi_col_runs.append(current_run)

    for run_idx, run in enumerate(multi_col_runs):
        col_count = max(len(r) for r in run)
        if col_count < 2:
            continue

        # Determine column X anchors from the widest row(s)
        col_anchors: List[float] = []
        for r in run:
            if len(r) == col_count:
                col_anchors = [b.bounding_box["x0"] for b in r]
                break
        if not col_anchors:
            col_anchors = [b.bounding_box["x0"] for b in run[0]]

        all_run_blocks = [b for r in run for b in r]
        t_x0 = round(min(b.bounding_box["x0"] for b in all_run_blocks), 2)
        t_y0 = round(min(b.bounding_box["y0"] for b in all_run_blocks), 2)
        t_x1 = round(max(b.bounding_box["x1"] for b in all_run_blocks), 2)
        t_y1 = round(max(b.bounding_box["y1"] for b in all_run_blocks), 2)

        cells: List[TableCellData] = []
        headers: List[str] = []

        for r_i, r_blocks in enumerate(run):
            # Map each block in the row to its closest column index
            mapped_cols: Dict[int, ExtractedBlockData] = {}
            for b in r_blocks:
                bx = b.bounding_box["x0"]
                best_c = min(
                    range(col_count),
                    key=lambda c_i: abs(
                        bx - (col_anchors[c_i] if c_i < len(col_anchors) else bx)
                    ),
                )
                while best_c in mapped_cols and best_c + 1 < col_count:
                    best_c += 1
                mapped_cols[best_c] = b

            row_y0 = round(min(b.bounding_box["y0"] for b in r_blocks), 2)
            row_y1 = round(max(b.bounding_box["y1"] for b in r_blocks), 2)

            for c_i in range(col_count):
                matched_b = mapped_cols.get(c_i)
                cell_txt = matched_b.extracted_text.strip() if matched_b else ""
                if r_i == 0:
                    headers.append(cell_txt or f"Column {c_i + 1}")

                if matched_b:
                    c_bbox = dict(matched_b.bounding_box)
                    c_conf = matched_b.confidence
                else:
                    # Empty cell — preserve exact empty string without inventing values
                    col_w = (t_x1 - t_x0) / max(1, col_count)
                    c_bbox = {
                        "x0": round(t_x0 + c_i * col_w, 2),
                        "y0": row_y0,
                        "x1": round(t_x0 + (c_i + 1) * col_w, 2),
                        "y1": row_y1,
                        "page_width": page_w,
                        "page_height": page_h,
                    }
                    c_conf = 1.0 if page_data.extraction_method == "NATIVE_PDF" else page_data.average_confidence

                cells.append(
                    TableCellData(
                        row_index=r_i,
                        col_index=c_i,
                        cell_text=cell_txt,
                        is_header=(r_i == 0),
                        bounding_box=c_bbox,
                        confidence=round(c_conf, 4),
                    )
                )

        avg_conf = round(
            sum(b.confidence for b in all_run_blocks) / len(all_run_blocks), 4
        )
        t_num = existing_count + len(tables) + 1
        tables.append(
            ExtractedTableData(
                id="",
                table_identifier=f"TBL-P{page_data.page_number}-{t_num:02d}",
                page_number=page_data.page_number,
                row_count=len(run),
                column_count=col_count,
                headers=headers,
                bounding_box={
                    "x0": t_x0,
                    "y0": t_y0,
                    "x1": t_x1,
                    "y1": t_y1,
                    "page_width": page_w,
                    "page_height": page_h,
                },
                extraction_method=page_data.extraction_method,
                confidence=avg_conf,
                cells=cells,
            )
        )

    # Strategy 2: Structured Line-Item blocks (e.g., "Line Item 1: Description - $100,000.00")
    if not tables and existing_count == 0:
        line_item_rows: List[Tuple[ExtractedBlockData, str, str]] = []
        for blk in sorted_by_y:
            m = LINE_ITEM_ROW_PATTERN.match(blk.extracted_text.strip())
            if m:
                desc = m.group(1).strip()
                amt = m.group(2).strip()
                line_item_rows.append((blk, desc, amt))

        if len(line_item_rows) >= 2:
            t_x0 = round(
                min(b.bounding_box["x0"] for b, _, _ in line_item_rows), 2
            )
            t_y0 = round(
                min(b.bounding_box["y0"] for b, _, _ in line_item_rows), 2
            )
            t_x1 = round(
                max(b.bounding_box["x1"] for b, _, _ in line_item_rows), 2
            )
            t_y1 = round(
                max(b.bounding_box["y1"] for b, _, _ in line_item_rows), 2
            )
            mid_x = round(t_x0 + (t_x1 - t_x0) * 0.72, 2)

            cells_list: List[TableCellData] = []
            for r_i, (blk, desc, amt) in enumerate(line_item_rows):
                by0 = blk.bounding_box["y0"]
                by1 = blk.bounding_box["y1"]
                cells_list.append(
                    TableCellData(
                        row_index=r_i,
                        col_index=0,
                        cell_text=desc,
                        is_header=False,
                        bounding_box={
                            "x0": blk.bounding_box["x0"],
                            "y0": by0,
                            "x1": mid_x,
                            "y1": by1,
                            "page_width": page_w,
                            "page_height": page_h,
                        },
                        confidence=blk.confidence,
                    )
                )
                cells_list.append(
                    TableCellData(
                        row_index=r_i,
                        col_index=1,
                        cell_text=amt,
                        is_header=False,
                        bounding_box={
                            "x0": mid_x,
                            "y0": by0,
                            "x1": blk.bounding_box["x1"],
                            "y1": by1,
                            "page_width": page_w,
                            "page_height": page_h,
                        },
                        confidence=blk.confidence,
                    )
                )

            avg_conf = round(
                sum(b.confidence for b, _, _ in line_item_rows)
                / len(line_item_rows),
                4,
            )
            tables.append(
                ExtractedTableData(
                    id="",
                    table_identifier=f"TBL-P{page_data.page_number}-01",
                    page_number=page_data.page_number,
                    row_count=len(line_item_rows),
                    column_count=2,
                    headers=["Line Item Description", "Amount"],
                    bounding_box={
                        "x0": t_x0,
                        "y0": t_y0,
                        "x1": t_x1,
                        "y1": t_y1,
                        "page_width": page_w,
                        "page_height": page_h,
                    },
                    extraction_method=page_data.extraction_method,
                    confidence=avg_conf,
                    cells=cells_list,
                )
            )

    return tables


# ============================================================================
# MODULE 2: LAYOUT UNDERSTANDING (Regions + OpenCV Visual Stamp Detection)
# ============================================================================

SECTION_HEADING_RE = re.compile(
    r"^(?:schedule\s+[a-z0-9]+|section\s+\d+|article\s+[ivx0-9]+|part\s+[a-z0-9]+|clause\s+\d+|terms\s+and\s+conditions|payment\s+schedule|summary\s+of\s+account)",
    re.IGNORECASE,
)

SIGNATURE_RE = re.compile(
    r"(?:authorized\s+signatory|signature\b|signed\s+by|approved\s+by|witness\s+signature|on\s+behalf\s+of|director\s+signature)",
    re.IGNORECASE,
)

STAMP_RE = re.compile(
    r"(?:official\s+seal|company\s+stamp|certified\s+true\s+copy|notarized|stamp\s+duty|paid\s+stamp|verified\s+seal|escrow\s+seal)",
    re.IGNORECASE,
)

FOOTER_RE = re.compile(
    r"(?:page\s+\d+\s+of\s+\d+|confidential|all\s+rights\s+reserved|registered\s+in\s+england|member\s+fdic)",
    re.IGNORECASE,
)


def _detect_opencv_stamp_regions(
    file_bytes: bytes, file_type: str, page_number: int, page_w: float, page_h: float
) -> List[Dict[str, float]]:
    """
    Uses OpenCV HSV color segmentation and contour geometry to detect high-saturation
    red/blue/purple circular or rectangular stamp regions on raster images or PDF pages.
    """
    detected_boxes: List[Dict[str, float]] = []
    try:
        if file_type.upper() == "PDF":
            with fitz.open(stream=file_bytes, filetype="pdf") as pdf_doc:
                if page_number - 1 >= len(pdf_doc):
                    return []
                page = pdf_doc[page_number - 1]
                pix = page.get_pixmap(dpi=150, alpha=False)
                img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        else:
            arr = np.frombuffer(file_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is None:
                return []

        img_h, img_w = bgr.shape[:2]
        scale_x = page_w / float(img_w) if img_w > 0 else 1.0
        scale_y = page_h / float(img_h) if img_h > 0 else 1.0

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        # Detect saturated red/crimson stamp ink
        mask_red1 = cv2.inRange(hsv, np.array([0, 90, 80]), np.array([12, 255, 255]))
        mask_red2 = cv2.inRange(hsv, np.array([165, 90, 80]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(mask_red1, mask_red2)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            # Stamp candidate must be reasonably sized (not tiny text or full page border)
            if (img_w * img_h * 0.004) <= area <= (img_w * img_h * 0.18):
                aspect = float(w) / float(max(1, h))
                if 0.4 <= aspect <= 3.5:
                    detected_boxes.append(
                        {
                            "x0": round(x * scale_x, 2),
                            "y0": round(y * scale_y, 2),
                            "x1": round((x + w) * scale_x, 2),
                            "y1": round((y + h) * scale_y, 2),
                            "page_width": page_w,
                            "page_height": page_h,
                        }
                    )
    except Exception:
        pass
    return detected_boxes


def extract_layout_regions_for_page(
    page_data: ExtractedPageData,
    page_tables: List[ExtractedTableData],
    file_bytes: bytes,
    file_type: str,
) -> List[LayoutRegionData]:
    """
    MODULE 2: LAYOUT UNDERSTANDING
    Identifies and preserves Document Title, Headers, Sections, Paragraphs, Tables,
    Key-Value Regions, Signature Regions, Stamp Regions, and Footer Information
    with original page coordinates and parent-child reading hierarchy.
    """
    regions: List[LayoutRegionData] = []
    page_w = page_data.width
    page_h = page_data.height
    p_num = page_data.page_number

    sorted_blocks = sorted(
        page_data.blocks,
        key=lambda b: (b.bounding_box["y0"], b.bounding_box["x0"]),
    )

    # Determine median font size if available
    font_sizes = [b.font_size for b in sorted_blocks if b.font_size and b.font_size > 0]
    max_font = max(font_sizes) if font_sizes else 0.0

    # Track blocks that are already part of a detected table bounding box
    def _is_inside_table(blk: ExtractedBlockData) -> bool:
        bx0, by0, bx1, by1 = (
            blk.bounding_box["x0"],
            blk.bounding_box["y0"],
            blk.bounding_box["x1"],
            blk.bounding_box["y1"],
        )
        cx = (bx0 + bx1) / 2.0
        cy = (by0 + by1) / 2.0
        for tbl in page_tables:
            tb = tbl.bounding_box
            if (tb["x0"] - 4.0) <= cx <= (tb["x1"] + 4.0) and (
                tb["y0"] - 4.0
            ) <= cy <= (tb["y1"] + 4.0):
                return True
        return False

    title_region_id: Optional[str] = None
    active_section_id: Optional[str] = None
    reading_order = 0

    for idx, blk in enumerate(sorted_blocks):
        if _is_inside_table(blk):
            continue

        txt = blk.extracted_text.strip()
        if not txt:
            continue

        y0 = blk.bounding_box["y0"]
        y1 = blk.bounding_box["y1"]
        rel_y0 = y0 / page_h if page_h > 0 else 0.0
        rel_y1 = y1 / page_h if page_h > 0 else 0.0

        region_type = "PARAGRAPH"
        label = "Narrative Paragraph"
        parent_id = active_section_id or title_region_id

        # 1. Document Title detection (first prominent block near top of page 1)
        if (
            p_num == 1
            and title_region_id is None
            and idx <= 1
            and rel_y0 <= 0.25
            and (
                (blk.font_size and blk.font_size >= max_font - 0.5)
                or txt.isupper()
                or len(txt) <= 90
            )
        ):
            region_type = "DOCUMENT_TITLE"
            label = "Document Title"
            parent_id = None
        # 2. Signature Region detection
        elif SIGNATURE_RE.search(txt):
            region_type = "SIGNATURE_REGION"
            label = "Signatory & Authorization Block"
        # 3. Stamp Region detection (lexical)
        elif STAMP_RE.search(txt):
            region_type = "STAMP_REGION"
            label = "Official Seal / Stamp Callout"
        # 4. Footer detection
        elif rel_y1 >= 0.88 or FOOTER_RE.search(txt):
            region_type = "FOOTER"
            label = "Page Footer Metadata"
        # 5. Section Heading detection
        elif SECTION_HEADING_RE.search(txt) or (
            blk.font_size
            and max_font > 0
            and blk.font_size >= 13.0
            and len(txt) < 100
            and ":" not in txt
        ):
            region_type = "SECTION_HEADING"
            label = f"Section: {txt[:48]}"
            parent_id = title_region_id
        # 6. Top Running Header detection
        elif rel_y0 <= 0.11 and idx == 0 and p_num > 1:
            region_type = "HEADER"
            label = "Page Header"
            parent_id = None
        # 7. Key-Value Region detection
        elif blk.field_name is not None or (
            ":" in txt and len(txt.splitlines()) <= 3 and len(txt) <= 140
        ):
            region_type = "KEY_VALUE_REGION"
            label = (
                f"Key-Value ({blk.field_name})"
                if blk.field_name
                else "Key-Value Metadata"
            )
        else:
            region_type = "PARAGRAPH"
            label = "Body Text Block"

        reg_id = f"LREG-P{p_num}-{reading_order + 1:03d}"
        if region_type == "DOCUMENT_TITLE":
            title_region_id = reg_id
        elif region_type == "SECTION_HEADING":
            active_section_id = reg_id

        regions.append(
            LayoutRegionData(
                id=reg_id,
                page_number=p_num,
                region_type=region_type,
                reading_order=reading_order,
                parent_region_id=parent_id,
                label=label,
                text_content=txt,
                bounding_box=dict(blk.bounding_box),
                extraction_method=blk.extraction_method,
                confidence=blk.confidence,
            )
        )
        reading_order += 1

    # Add Table Layout Regions
    for tbl in page_tables:
        reg_id = f"LREG-P{p_num}-{reading_order + 1:03d}"
        regions.append(
            LayoutRegionData(
                id=reg_id,
                page_number=p_num,
                region_type="TABLE",
                reading_order=reading_order,
                parent_region_id=active_section_id or title_region_id,
                label=f"Structured Table ({tbl.table_identifier}: {tbl.row_count}×{tbl.column_count})",
                text_content=" | ".join(tbl.headers),
                bounding_box=dict(tbl.bounding_box),
                extraction_method=tbl.extraction_method,
                confidence=tbl.confidence,
            )
        )
        reading_order += 1

    # Check OpenCV visual stamp contours if no lexical stamp region already overlaps
    cv_stamp_boxes = _detect_opencv_stamp_regions(
        file_bytes, file_type, p_num, page_w, page_h
    )
    for s_bbox in cv_stamp_boxes:
        reg_id = f"LREG-P{p_num}-{reading_order + 1:03d}"
        regions.append(
            LayoutRegionData(
                id=reg_id,
                page_number=p_num,
                region_type="STAMP_REGION",
                reading_order=reading_order,
                parent_region_id=title_region_id,
                label="Visual Stamp / Seal Contour (OpenCV)",
                text_content="[Visual Stamp Contour Region]",
                bounding_box=s_bbox,
                extraction_method="OPENCV_CONTOUR",
                confidence=0.88,
            )
        )
        reading_order += 1

    # Sort all regions on the page in top-to-bottom reading order
    regions.sort(key=lambda r: (r.bounding_box["y0"], r.bounding_box["x0"]))
    for idx, reg in enumerate(regions):
        reg.reading_order = idx

    return regions


# ============================================================================
# MODULE 4: ENTITY EXTRACTION & NORMALIZATION
# ============================================================================

CURRENCY_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
}

MONETARY_RE = re.compile(
    r"(?:([\$€£¥₹])\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)(?:\s*(USD|EUR|GBP|INR|JPY))?|\b(\d{1,3}(?:,\d{3})*(?:\.\d{2}))\s*(USD|EUR|GBP|INR|JPY)\b)"
)

DATE_PATTERNS = [
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})\b"),
    re.compile(
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
        re.IGNORECASE,
    ),
]

INVOICE_NUM_RE = re.compile(
    r"(?:invoice\s*(?:no\.?|number|#|id)\s*[:\-]?\s*([A-Z0-9\-\/]{3,35})|\b(INV-[A-Z0-9\-]{3,30})\b)",
    re.IGNORECASE,
)

TAX_ID_RE = re.compile(
    r"(?:(?:tax\s*id|vat\s*(?:no\.?|reg)?|ein|tin|gstin|registration\s*no\.?)\s*[:\-]?\s*([A-Z0-9\-]{5,30})|\b(REG-[A-Z0-9\-]{4,25}|EIN-\d{2}-\d{7}|GB\d{9})\b)",
    re.IGNORECASE,
)

ACCOUNT_REF_RE = re.compile(
    r"(?:(?:contract\s*(?:id|no\.?|ref)|purchase\s*order|p\.?o\.?\s*no\.?|account\s*(?:no\.?|number|id)|iban)\s*[:\-]?\s*([A-Z0-9\-]{4,35})|\b(CTR-[A-Z0-9\-]{3,25}|PO-\d{4}-\d{3,10}|ACCT-[A-Z0-9\-]{4,25}|[A-Z]{2}\d{2}[A-Z0-9]{11,30})\b)",
    re.IGNORECASE,
)

PERSON_LABEL_RE = re.compile(
    r"(?:authorized\s*signatory|approved\s*by|signed\s*by|prepared\s*by|applicant\s*name|holder\s*name|beneficiary\s*name|officer)\s*[:\-]\s*([A-Z][A-Za-z\.\s\-]{2,55})",
    re.IGNORECASE,
)

HONORIFIC_PERSON_RE = re.compile(
    r"\b((?:Dr\.|Mr\.|Ms\.|Mrs\.|Prof\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
)

COMPANY_LABEL_RE = re.compile(
    r"(?:vendor|supplier|seller|client|customer|bill\s*to|issued\s*by|received\s*from|paid\s*to(?:\s*beneficiary)?|account\s*holder|employer|institution|bank\s*name)\s*[:\-]\s*([A-Z][A-Za-z0-9\s\.,&\-\']{2,75})",
    re.IGNORECASE,
)

COMPANY_SUFFIX_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z0-9&\-\']+\s+){0,5}[A-Z][A-Za-z0-9&\-\']*\s*(?:Ltd\.?|Limited|Holdings|Corp\.?|Corporation|Inc\.?|LLC|PLC|Bank|Group))\b"
)

ADDRESS_RE = re.compile(
    r"(?:(?:address|registered\s*office|billing\s*address|location)\s*[:\-]\s*([^\n\r]{8,110})|\b(\d{1,5}\s+[A-Z][A-Za-z0-9\s]{3,35},\s*[A-Z][A-Za-z\s]{2,25}(?:,\s*[A-Z0-9\s]{3,15})?)\b)",
    re.IGNORECASE,
)


def _normalize_date(raw_date: str) -> str:
    cleaned = raw_date.strip().replace(",", "")
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%B %d %Y",
        "%b %d %Y",
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw_date.strip()


def _normalize_monetary(
    sym: Optional[str], num_str: str, code: Optional[str]
) -> str:
    curr = (code or "").strip().upper()
    if not curr and sym:
        curr = CURRENCY_MAP.get(sym.strip(), "USD")
    if not curr:
        curr = "USD"
    numeric_clean = num_str.replace(",", "").strip()
    try:
        val = float(numeric_clean)
        return f"{curr} {val:.2f}"
    except ValueError:
        return f"{curr} {numeric_clean}"


def _normalize_person(raw_name: str) -> str:
    # Strip trailing role in parentheses e.g. "Dr. Viktor Kestrel (Director)"
    base = re.sub(r"\(.*?\)", "", raw_name).strip()
    base = re.sub(r"^(?:Dr\.?|Mr\.?|Ms\.?|Mrs\.?|Prof\.?)\s+", "", base, flags=re.IGNORECASE)
    return " ".join(base.split()).upper()


def _normalize_company(raw_comp: str) -> str:
    cleaned = raw_comp.strip().rstrip(".,;")
    cleaned = re.sub(r"\bLimited\b", "LTD", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bLtd\.?\b", "LTD", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bCorporation\b", "CORP", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bCorp\.?\b", "CORP", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bInc\.?\b", "INC", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).upper()


def extract_entities_from_document(
    extraction_result: DocumentExtractionResult,
) -> List[ExtractedEntityData]:
    """
    MODULE 4: ENTITY EXTRACTION
    Identifies and normalizes Person Names, Company Names, Invoice Numbers,
    Tax Identifiers, Dates, Monetary Amounts, Account References, and Addresses.
    Preserves raw_value alongside normalized_value and original page/coordinate references.
    """
    entities: List[ExtractedEntityData] = []
    seen_keys = set()

    def _add_entity(
        page_num: int,
        e_type: str,
        raw_val: str,
        norm_val: str,
        blk: ExtractedBlockData,
    ) -> None:
        r_clean = raw_val.strip()
        n_clean = norm_val.strip()
        if not r_clean or not n_clean:
            return
        dedup_key = (page_num, e_type, n_clean, blk.block_index)
        if dedup_key in seen_keys:
            return
        seen_keys.add(dedup_key)

        entities.append(
            ExtractedEntityData(
                page_number=page_num,
                entity_type=e_type,
                raw_value=r_clean,
                normalized_value=n_clean,
                bounding_box=dict(blk.bounding_box),
                extraction_method=blk.extraction_method,
                confidence=blk.confidence,
                source_reference=blk.source_reference,
            )
        )

    for page in extraction_result.pages:
        p_num = page.page_number
        for blk in page.blocks:
            txt = blk.extracted_text.strip()
            if not txt:
                continue

            # 1. Invoice Numbers
            for m in INVOICE_NUM_RE.finditer(txt):
                raw_v = (m.group(1) or m.group(2) or "").strip()
                if raw_v:
                    _add_entity(
                        p_num,
                        "INVOICE_NUMBER",
                        raw_v,
                        raw_v.upper().replace(" ", ""),
                        blk,
                    )

            # 2. Tax Identifiers
            for m in TAX_ID_RE.finditer(txt):
                raw_v = (m.group(1) or m.group(2) or "").strip()
                if raw_v:
                    _add_entity(
                        p_num,
                        "TAX_IDENTIFIER",
                        raw_v,
                        raw_v.upper().replace(" ", ""),
                        blk,
                    )

            # 3. Account / Contract / PO / IBAN References
            for m in ACCOUNT_REF_RE.finditer(txt):
                raw_v = (m.group(1) or m.group(2) or "").strip()
                if raw_v and not raw_v.upper().startswith("INV-"):
                    _add_entity(
                        p_num,
                        "ACCOUNT_REFERENCE",
                        raw_v,
                        raw_v.upper().replace(" ", ""),
                        blk,
                    )

            # 4. Dates
            for pat in DATE_PATTERNS:
                for m in pat.finditer(txt):
                    raw_d = m.group(1).strip()
                    _add_entity(
                        p_num, "DATE", raw_d, _normalize_date(raw_d), blk
                    )

            # 5. Monetary Amounts
            for m in MONETARY_RE.finditer(txt):
                full_raw = m.group(0).strip()
                sym = m.group(1)
                num1 = m.group(2)
                code1 = m.group(3)
                num2 = m.group(4)
                code2 = m.group(5)
                num_str = num1 if num1 else (num2 or "0")
                code_str = code1 if code1 else code2
                _add_entity(
                    p_num,
                    "MONETARY_AMOUNT",
                    full_raw,
                    _normalize_monetary(sym, num_str, code_str),
                    blk,
                )

            # 6. Person Names
            for m in PERSON_LABEL_RE.finditer(txt):
                raw_p = m.group(1).strip()
                _add_entity(
                    p_num, "PERSON_NAME", raw_p, _normalize_person(raw_p), blk
                )
            for m in HONORIFIC_PERSON_RE.finditer(txt):
                raw_p = m.group(1).strip()
                _add_entity(
                    p_num, "PERSON_NAME", raw_p, _normalize_person(raw_p), blk
                )

            # 7. Company Names
            for m in COMPANY_LABEL_RE.finditer(txt):
                raw_c = m.group(1).strip()
                _add_entity(
                    p_num, "COMPANY_NAME", raw_c, _normalize_company(raw_c), blk
                )
            for m in COMPANY_SUFFIX_RE.finditer(txt):
                raw_c = m.group(1).strip()
                if ":" in raw_c:
                    raw_c = raw_c.split(":")[-1].strip()
                raw_c = re.sub(
                    r"^(?:Wire\s+Transfer\s+to|Payment\s+to|Remit\s+to|Issued\s+by)\s+",
                    "",
                    raw_c,
                    flags=re.IGNORECASE,
                ).strip()
                _add_entity(
                    p_num, "COMPANY_NAME", raw_c, _normalize_company(raw_c), blk
                )

            # 8. Addresses
            for m in ADDRESS_RE.finditer(txt):
                raw_a = (m.group(1) or m.group(2) or "").strip()
                if raw_a and len(raw_a) >= 8:
                    norm_a = " ".join(raw_a.split()).upper()
                    _add_entity(p_num, "ADDRESS", raw_a, norm_a, blk)

    return entities


# ============================================================================
# MODULE 1: DOCUMENT CLASSIFICATION (Lexical + Structural Signals)
# ============================================================================

CLASSIFICATION_RULES: Dict[str, List[Tuple[str, re.Pattern[str], float]]] = {
    "COMMERCIAL_INVOICE": [
        ("Title/Keyword: Commercial Invoice", re.compile(r"\bcommercial\s+invoice\b", re.I), 0.38),
        ("Keyword: Invoice No / Number", re.compile(r"\binvoice\s*(?:no\.?|number|#)\b", re.I), 0.24),
        ("Keyword: Line Item / Qty / Unit Price", re.compile(r"\b(?:line\s*item|unit\s*price|qty|quantity|bill\s*to)\b", re.I), 0.16),
        ("Keyword: Subtotal & Tax", re.compile(r"\b(?:subtotal|sub-total)\b[\s\S]{0,120}\b(?:tax|vat|gst)\b", re.I), 0.18),
    ],
    "BANK_STATEMENT": [
        ("Title/Keyword: Bank / Account Statement", re.compile(r"\b(?:bank\s+statement|statement\s+of\s+account|account\s+statement)\b", re.I), 0.42),
        ("Keyword: Opening / Closing Balance", re.compile(r"\b(?:opening\s+balance|closing\s+balance|ending\s+balance|beginning\s+balance)\b", re.I), 0.28),
        ("Keyword: IBAN / Sort Code / Routing", re.compile(r"\b(?:iban|swift|bic|sort\s+code|routing\s+number|withdrawals|deposits)\b", re.I), 0.22),
    ],
    "TAX_CERTIFICATE": [
        ("Title/Keyword: Tax Certificate / Clearance", re.compile(r"\b(?:tax\s+certificate|certificate\s+of\s+tax|tax\s+clearance|withholding\s+tax|vat\s+registration\s+certificate)\b", re.I), 0.45),
        ("Keyword: Tax Authority / Assessment Year", re.compile(r"\b(?:assessment\s+year|taxpayer\s+identification|revenue\s+authority|internal\s+revenue|hmrc)\b", re.I), 0.28),
    ],
    "IDENTITY_DOCUMENT": [
        ("Title/Keyword: Passport / National ID / Driver License", re.compile(r"\b(?:passport|national\s+identity|identity\s+card|driver\'?s?\s+licen[cs]e|republic\s+of)\b", re.I), 0.44),
        ("Keyword: Date of Birth / Nationality / Document No", re.compile(r"\b(?:date\s+of\s+birth|nationality|place\s+of\s+birth|sex\b|expiry\s+date)\b", re.I), 0.30),
    ],
    "RECEIPT": [
        ("Title/Keyword: Receipt / Disbursement Voucher", re.compile(r"\b(?:receipt|disbursement\s*voucher|payment\s*voucher|cash\s*receipt|escrow\s*disbursement)\b", re.I), 0.42),
        ("Keyword: Amount Paid / Approved By / Total Amount", re.compile(r"\b(?:amount\s*paid|received\s*from|payment\s*received|approved\s*by|total\s*amount)\b", re.I), 0.24),
    ],
    "CONTRACT": [
        ("Title/Keyword: Agreement / Contract / Addendum", re.compile(r"\b(?:master\s+service\s+agreement|contract\s+addendum|escrow\s+agreement|this\s+agreement|memorandum\s+of\s+understanding)\b", re.I), 0.40),
        ("Keyword: Whereas / Parties / Governing Law / Clause", re.compile(r"\b(?:whereas|hereinafter|governing\s+law|indemnification|schedule\s+[a-z0-9]|obligations)\b", re.I), 0.26),
        ("Keyword: Authorized Signatory / In Witness Whereof", re.compile(r"\b(?:in\s+witness\s+whereof|authorized\s+signatory|executed\s+by)\b", re.I), 0.18),
    ],
    "APPLICATION_FORM": [
        ("Title/Keyword: Application Form / Registration Form", re.compile(r"\b(?:application\s+form|registration\s+form|enrollment\s+form|kyc\s+application)\b", re.I), 0.42),
        ("Keyword: Applicant Details / Declaration", re.compile(r"\b(?:applicant\s+name|applicant\s+details|for\s+official\s+use\s+only|declaration\s+by\s+applicant)\b", re.I), 0.28),
    ],
}


def classify_document(
    extraction_result: DocumentExtractionResult,
    layout_regions: List[LayoutRegionData],
    tables: List[ExtractedTableData],
    entities: List[ExtractedEntityData],
) -> ClassificationResultData:
    """
    MODULE 1: DOCUMENT CLASSIFICATION
    Combines extracted text and structural layout/table/entity signals.
    Never claims certainty when confidence is low (< 0.68).
    """
    full_text = "\n".join(p.raw_text for p in extraction_result.pages)
    if not full_text.strip():
        return ClassificationResultData(
            document_type="OTHER_UNKNOWN",
            display_label=DISPLAY_LABELS["OTHER_UNKNOWN"],
            confidence=0.0,
            is_certain=False,
            status_label="LOW_CONFIDENCE — No Extractable Text Signals",
            signals=["Document contains 0 extracted characters"],
            candidates=[],
        )

    has_tables = len(tables) > 0
    kv_count = sum(1 for r in layout_regions if r.region_type == "KEY_VALUE_REGION")
    sig_count = sum(1 for r in layout_regions if r.region_type == "SIGNATURE_REGION")
    para_count = sum(1 for r in layout_regions if r.region_type == "PARAGRAPH")
    entity_types = {e.entity_type for e in entities}

    candidates: List[Dict[str, Any]] = []

    for doc_type, rules in CLASSIFICATION_RULES.items():
        score = 0.0
        matched_signals: List[str] = []

        for label, pattern, weight in rules:
            if pattern.search(full_text):
                score += weight
                matched_signals.append(label)

        # Structural & Entity reinforcement signals (only applied if at least 1 lexical signal matched)
        if matched_signals:
            if doc_type == "COMMERCIAL_INVOICE":
                if "INVOICE_NUMBER" in entity_types and "MONETARY_AMOUNT" in entity_types:
                    score += 0.16
                    matched_signals.append(
                        "Structure: Contains INVOICE_NUMBER + MONETARY_AMOUNT entities"
                    )
                if has_tables:
                    score += 0.10
                    matched_signals.append("Structure: Contains line-item table")
            elif doc_type == "BANK_STATEMENT":
                if has_tables and "ACCOUNT_REFERENCE" in entity_types:
                    score += 0.18
                    matched_signals.append(
                        "Structure: Tabular ledger + ACCOUNT_REFERENCE entity"
                    )
            elif doc_type == "RECEIPT":
                if "MONETARY_AMOUNT" in entity_types and kv_count >= 3:
                    score += 0.16
                    matched_signals.append(
                        f"Structure: {kv_count} key-value regions + MONETARY_AMOUNT"
                    )
            elif doc_type == "CONTRACT":
                if sig_count > 0 and para_count >= 1:
                    score += 0.16
                    matched_signals.append(
                        "Structure: Contains narrative clauses + SIGNATURE_REGION"
                    )
            elif doc_type == "TAX_CERTIFICATE":
                if "TAX_IDENTIFIER" in entity_types:
                    score += 0.18
                    matched_signals.append("Structure: Contains TAX_IDENTIFIER entity")
            elif doc_type == "APPLICATION_FORM":
                if kv_count >= 4:
                    score += 0.15
                    matched_signals.append(
                        f"Structure: High form key-value density ({kv_count} fields)"
                    )

        # Cap automated confidence at 0.96 (classifications are never treated as verified facts)
        capped_conf = round(min(0.96, score), 4)
        if capped_conf > 0:
            candidates.append(
                {
                    "document_type": doc_type,
                    "display_label": DISPLAY_LABELS[doc_type],
                    "confidence": capped_conf,
                    "matched_signals": matched_signals,
                }
            )

    candidates.sort(key=lambda c: c["confidence"], reverse=True)

    if not candidates or candidates[0]["confidence"] < 0.35:
        fallback_signals = (
            candidates[0]["matched_signals"]
            if candidates
            else ["Insufficient domain-specific lexical or structural markers"]
        )
        raw_conf = candidates[0]["confidence"] if candidates else 0.20
        return ClassificationResultData(
            document_type="OTHER_UNKNOWN",
            display_label=DISPLAY_LABELS["OTHER_UNKNOWN"],
            confidence=round(raw_conf, 4),
            is_certain=False,
            status_label="LOW_CONFIDENCE_UNCLASSIFIED — Manual Analyst Review Required",
            signals=fallback_signals,
            candidates=candidates[:4],
        )

    top = candidates[0]
    runner_up_conf = candidates[1]["confidence"] if len(candidates) > 1 else 0.0
    margin = top["confidence"] - runner_up_conf

    # Only mark `is_certain = True` if confidence >= 0.68 AND clear margin over runner-up
    is_certain = bool(top["confidence"] >= 0.68 and margin >= 0.12)
    if is_certain:
        status_label = "AUTOMATED_CLASSIFICATION — High Signal Match (Unverified)"
    else:
        status_label = (
            "AMBIGUOUS_OR_LOW_CONFIDENCE — Do Not Treat As Verified Fact"
        )

    return ClassificationResultData(
        document_type=top["document_type"],
        display_label=top["display_label"],
        confidence=top["confidence"],
        is_certain=is_certain,
        status_label=status_label,
        signals=top["matched_signals"],
        candidates=candidates[:4],
    )


class StructureIntelligenceEngine:
    """
    VERITAS AI Phase 2B Document Structure Understanding & Intelligent Classification Engine.
    Transforms Phase 2A extraction output into:
    - Module 1: Document Classification (with confidence & uncertainty handling)
    - Module 2: Layout Understanding (9 semantic region types with original coordinates)
    - Module 3: Table Detection & Extraction (rows, columns, cells, cell coordinates)
    - Module 4: Entity Extraction & Normalization (raw_value + normalized_value + coordinates)
    """

    @staticmethod
    def analyze_document_structure(
        file_bytes: bytes,
        file_type: str,
        extraction_result: DocumentExtractionResult,
    ) -> StructureAnalysisBundle:
        all_tables: List[ExtractedTableData] = []
        all_layout_regions: List[LayoutRegionData] = []

        native_tables_by_page: Dict[int, List[ExtractedTableData]] = {}
        if file_type.upper().lstrip(".") == "PDF":
            native_tables_by_page = _extract_native_pymupdf_tables(
                file_bytes, extraction_result.page_count
            )

        for page_data in extraction_result.pages:
            p_num = page_data.page_number
            page_tables = list(native_tables_by_page.get(p_num, []))

            if not page_tables:
                spatial_tables = _extract_spatial_or_structured_tables_from_page(
                    page_data, existing_count=len(page_tables)
                )
                page_tables.extend(spatial_tables)

            all_tables.extend(page_tables)

            page_regions = extract_layout_regions_for_page(
                page_data=page_data,
                page_tables=page_tables,
                file_bytes=file_bytes,
                file_type=file_type,
            )
            all_layout_regions.extend(page_regions)

        entities = extract_entities_from_document(extraction_result)
        classification = classify_document(
            extraction_result=extraction_result,
            layout_regions=all_layout_regions,
            tables=all_tables,
            entities=entities,
        )

        return StructureAnalysisBundle(
            classification=classification,
            layout_regions=all_layout_regions,
            tables=all_tables,
            entities=entities,
        )
