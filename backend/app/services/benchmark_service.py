import hashlib
import io
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFilter
from app.services.contextual_intelligence_engine import ContextualIntelligenceEngine
from app.services.extraction_engine import DualPathExtractionEngine
from app.services.investigation_reasoning_engine import InvestigationReasoningEngine
from app.services.structure_intelligence_engine import StructureIntelligenceEngine


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Computes exact character-level Levenshtein edit distance for OCR CER calculation."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _compute_cer(ground_truth: str, hypothesis: str) -> float:
    """Computes normalized Character Error Rate (CER) between ground truth and extracted text."""
    gt_clean = " ".join(ground_truth.upper().split())
    hyp_clean = " ".join(hypothesis.upper().split())
    if not gt_clean:
        return 0.0
    dist = _levenshtein_distance(gt_clean, hyp_clean)
    return round(min(1.0, dist / len(gt_clean)), 4)


class BenchmarkService:
    """
    Phase 6 Module E — Reproducible Extraction & Analysis Quality Benchmark Suite.
    Synthesizes 10 distinct forensic evaluation documents in-memory (completely isolated
    from production investigations) and executes the real Phase 2A, 2B, 4, and 5 engines
    to compute genuine accuracy, CER, Precision/Recall/F1, table cell accuracy,
    bounding-box localization validity, Decimal financial accuracy, and evidence completeness.
    """

    @staticmethod
    def _build_10_synthetic_specimens() -> List[Dict[str, Any]]:
        specimens: List[Dict[str, Any]] = []

        # 1. Native PDF Commercial Invoice
        doc1 = fitz.open()
        p1 = doc1.new_page(width=595, height=842)
        gt_text_1 = (
            "COMMERCIAL INVOICE\n"
            "Invoice No: INV-2026-9901\n"
            "Invoice Date: 2026-03-10\n"
            "Vendor: Helios Precision Components GmbH\n"
            "Bill To: Meridian Logistics Corp\n"
            "Tax ID: DE819204511\n"
            "IBAN: DE89370400440532013000\n"
            "Subtotal: $10,000.00\n"
            "Tax: $1,900.00\n"
            "Total Amount Due: $11,900.00"
        )
        y = 50
        for line in gt_text_1.split("\n"):
            p1.insert_text(fitz.Point(50, y), line, fontsize=11, fontname="helv")
            y += 22
        # Add a 2-row line item table
        headers1 = ["Description", "Qty", "Unit Price", "Amount"]
        rows1 = [
            headers1,
            ["Turbine Sensor Array", "2", "$3,000.00", "$6,000.00"],
            ["Calibration Unit", "1", "$4,000.00", "$4,000.00"],
        ]
        ty = 300
        for r_idx, r_vals in enumerate(rows1):
            tx = 50
            for c_val in r_vals:
                p1.draw_rect(fitz.Rect(tx, ty, tx + 120, ty + 22), color=(0.2, 0.2, 0.2))
                p1.insert_text(
                    fitz.Point(tx + 5, ty + 15),
                    c_val,
                    fontsize=9.5,
                    fontname="hebo" if r_idx == 0 else "helv",
                )
                tx += 120
            ty += 22
        specimens.append(
            {
                "specimen_id": "BENCH-01-NATIVE-INVOICE",
                "category": "Native PDF Invoice",
                "filename": "bench_01_native_invoice.pdf",
                "file_type": "PDF",
                "bytes": doc1.tobytes(),
                "expected_doc_type": "COMMERCIAL_INVOICE",
                "expected_certain": True,
                "gt_text": gt_text_1
                + "\n"
                + "\n".join(" ".join(r) for r in rows1),
                "gt_entities": {
                    "INVOICE_NUMBER": {"INV-2026-9901"},
                    "DATE": {"2026-03-10"},
                    "ACCOUNT_REFERENCE": {"DE89370400440532013000"},
                    "TAX_IDENTIFIER": {"DE819204511"},
                    "MONETARY_AMOUNT": {
                        "USD 11900.00",
                        "USD 10000.00",
                        "USD 1900.00",
                        "USD 3000.00",
                        "USD 6000.00",
                        "USD 4000.00",
                    },
                },
                "gt_table_cells": [
                    "Turbine Sensor Array",
                    "$6,000.00",
                    "Calibration Unit",
                    "$4,000.00",
                ],
                "expected_financial_status": "CONSISTENT_EVIDENCE",
            }
        )
        doc1.close()

        # 2. Scanned Commercial Invoice (PNG raster image)
        img2 = Image.new("RGB", (1000, 700), color=(255, 255, 255))
        draw2 = ImageDraw.Draw(img2)
        gt_text_2 = (
            "COMMERCIAL INVOICE\n"
            "INVOICE NUMBER: INV-2026-9902\n"
            "INVOICE DATE: 2026-03-12\n"
            "IBAN: DE89370400440532013000\n"
            "TOTAL AMOUNT DUE: $11,900.00"
        )
        y2 = 60
        for line in gt_text_2.split("\n"):
            draw2.text((60, y2), line, fill=(10, 10, 10))
            y2 += 48
        buf2 = io.BytesIO()
        img2.save(buf2, format="PNG")
        specimens.append(
            {
                "specimen_id": "BENCH-02-SCANNED-INVOICE",
                "category": "Scanned Invoice (PNG)",
                "filename": "bench_02_scanned_invoice.png",
                "file_type": "PNG",
                "bytes": buf2.getvalue(),
                "expected_doc_type": "COMMERCIAL_INVOICE",
                "expected_certain": True,
                "gt_text": gt_text_2,
                "gt_entities": {
                    "INVOICE_NUMBER": {"INV-2026-9902"},
                    "DATE": {"2026-03-12"},
                },
                "gt_table_cells": [],
                "expected_financial_status": None,
            }
        )

        # 3. Bank Statement (PDF with reconciliation table)
        doc3 = fitz.open()
        p3 = doc3.new_page(width=595, height=842)
        gt_text_3 = (
            "CORPORATE BANK STATEMENT\n"
            "Statement Period: 2026-03-01 to 2026-03-31\n"
            "Account Holder: Meridian Logistics Corp\n"
            "Account Number: 4405320130\n"
            "IBAN: DE89370400440532013000\n"
            "Opening Balance: $50,000.00\n"
            "Closing Balance: $38,100.00"
        )
        y = 50
        for line in gt_text_3.split("\n"):
            p3.insert_text(fitz.Point(50, y), line, fontsize=11, fontname="helv")
            y += 22
        rows3 = [
            ["Date", "Reference", "Debit", "Balance"],
            ["2026-03-15", "INV-2026-9901 Wire", "$11,900.00", "$38,100.00"],
        ]
        ty = 260
        for r_idx, r_vals in enumerate(rows3):
            tx = 45
            for c_val in r_vals:
                p3.draw_rect(fitz.Rect(tx, ty, tx + 120, ty + 22), color=(0.2, 0.2, 0.2))
                p3.insert_text(
                    fitz.Point(tx + 4, ty + 15),
                    c_val,
                    fontsize=9.0,
                    fontname="hebo" if r_idx == 0 else "helv",
                )
                tx += 120
            ty += 22
        specimens.append(
            {
                "specimen_id": "BENCH-03-BANK-STATEMENT",
                "category": "Bank Statement",
                "filename": "bench_03_bank_statement.pdf",
                "file_type": "PDF",
                "bytes": doc3.tobytes(),
                "expected_doc_type": "BANK_STATEMENT",
                "expected_certain": True,
                "gt_text": gt_text_3
                + "\n"
                + "\n".join(" ".join(r) for r in rows3),
                "gt_entities": {
                    "ACCOUNT_REFERENCE": {"DE89370400440532013000", "4405320130"},
                    "DATE": {"2026-03-01", "2026-03-31", "2026-03-15"},
                    "MONETARY_AMOUNT": {
                        "USD 50000.00",
                        "USD 38100.00",
                        "USD 11900.00",
                    },
                },
                "gt_table_cells": ["2026-03-15", "INV-2026-9901 Wire", "$38,100.00"],
                "expected_financial_status": "CONSISTENT_EVIDENCE",
            }
        )
        doc3.close()

        # 4. Payment Receipt
        doc4 = fitz.open()
        p4 = doc4.new_page(width=595, height=842)
        gt_text_4 = (
            "OFFICIAL PAYMENT RECEIPT\n"
            "Receipt Number: RCP-2026-4410\n"
            "Transaction Date: 2026-03-15\n"
            "Payment Method: Wire Transfer\n"
            "Reference Invoice: INV-2026-9901\n"
            "Amount Paid: $11,900.00\n"
            "Merchant: Helios Precision Components GmbH"
        )
        y = 50
        for line in gt_text_4.split("\n"):
            p4.insert_text(fitz.Point(50, y), line, fontsize=11, fontname="helv")
            y += 22
        specimens.append(
            {
                "specimen_id": "BENCH-04-RECEIPT",
                "category": "Receipt",
                "filename": "bench_04_payment_receipt.pdf",
                "file_type": "PDF",
                "bytes": doc4.tobytes(),
                "expected_doc_type": "RECEIPT",
                "expected_certain": True,
                "gt_text": gt_text_4,
                "gt_entities": {
                    "DATE": {"2026-03-15"},
                    "MONETARY_AMOUNT": {"USD 11900.00"},
                },
                "gt_table_cells": [],
                "expected_financial_status": None,
            }
        )
        doc4.close()

        # 5. Master Service Contract
        doc5 = fitz.open()
        p5 = doc5.new_page(width=595, height=842)
        gt_text_5 = (
            "MASTER SERVICE AGREEMENT & CONTRACT\n"
            "Effective Date: 2026-01-15\n"
            "Between Party A: Meridian Logistics Corp\n"
            "And Party B: Helios Precision Components GmbH\n"
            "WHEREAS the parties agree to the following Terms and Conditions:\n"
            "Governing Law: Federal Republic of Germany\n"
            "Authorized Signatory: Dr. Lukas Weber\n"
            "Contract Value: $120,000.00"
        )
        y = 50
        for line in gt_text_5.split("\n"):
            p5.insert_text(fitz.Point(50, y), line, fontsize=11, fontname="helv")
            y += 22
        specimens.append(
            {
                "specimen_id": "BENCH-05-CONTRACT",
                "category": "Contract",
                "filename": "bench_05_master_contract.pdf",
                "file_type": "PDF",
                "bytes": doc5.tobytes(),
                "expected_doc_type": "CONTRACT",
                "expected_certain": True,
                "gt_text": gt_text_5,
                "gt_entities": {
                    "DATE": {"2026-01-15"},
                    "MONETARY_AMOUNT": {"USD 120000.00"},
                },
                "gt_table_cells": [],
                "expected_financial_status": None,
            }
        )
        doc5.close()

        # 6. Tax Certificate
        doc6 = fitz.open()
        p6 = doc6.new_page(width=595, height=842)
        gt_text_6 = (
            "TAX COMPLIANCE CERTIFICATE\n"
            "Certificate of Tax Clearance\n"
            "Taxpayer Identification Number (TIN): 84-2910482\n"
            "VAT Registration: DE819204511\n"
            "Assessment Year: 2025\n"
            "Issue Date: 2026-02-01\n"
            "Issuing Authority: Revenue & Customs Directorate"
        )
        y = 50
        for line in gt_text_6.split("\n"):
            p6.insert_text(fitz.Point(50, y), line, fontsize=11, fontname="helv")
            y += 22
        specimens.append(
            {
                "specimen_id": "BENCH-06-TAX-CERTIFICATE",
                "category": "Tax Certificate",
                "filename": "bench_06_tax_certificate.pdf",
                "file_type": "PDF",
                "bytes": doc6.tobytes(),
                "expected_doc_type": "TAX_CERTIFICATE",
                "expected_certain": True,
                "gt_text": gt_text_6,
                "gt_entities": {
                    "DATE": {"2026-02-01"},
                    "TAX_IDENTIFIER": {"84-2910482", "DE819204511"},
                },
                "gt_table_cells": [],
                "expected_financial_status": None,
            }
        )
        doc6.close()

        # 7. Low-Quality Scan (JPEG with blur + compression artifacts)
        img7 = Image.new("RGB", (1000, 700), color=(246, 246, 242))
        draw7 = ImageDraw.Draw(img7)
        gt_text_7 = (
            "OFFICIAL PAYMENT RECEIPT\n"
            "RECEIPT NO: RCP-2026-7788\n"
            "DATE: 2026-03-18\n"
            "AMOUNT PAID: $4,250.00\n"
            "PAYMENT METHOD: BANK TRANSFER"
        )
        y7 = 60
        for line in gt_text_7.split("\n"):
            draw7.text((60, y7), line, fill=(35, 35, 35))
            y7 += 50
        img7_blurred = img7.filter(ImageFilter.GaussianBlur(radius=0.5))
        buf7 = io.BytesIO()
        img7_blurred.save(buf7, format="JPEG", quality=55)
        specimens.append(
            {
                "specimen_id": "BENCH-07-LOW-QUALITY-SCAN",
                "category": "Low-Quality Scan (JPEG Q55)",
                "filename": "bench_07_low_quality_receipt.jpg",
                "file_type": "JPG",
                "bytes": buf7.getvalue(),
                "expected_doc_type": "RECEIPT",
                "expected_certain": True,
                "gt_text": gt_text_7,
                "gt_entities": {
                    "DATE": {"2026-03-18"},
                },
                "gt_table_cells": [],
                "expected_financial_status": None,
            }
        )

        # 8. Ambiguous Document (Internal briefing memo with no strong category markers)
        doc8 = fitz.open()
        p8 = doc8.new_page(width=595, height=842)
        gt_text_8 = (
            "INTERNAL OPERATIONAL NOTE\n"
            "Reference Code: MEMO-2026-09\n"
            "Date: 2026-03-20\n"
            "Subject: Warehouse inspection observation log for Sector 4."
        )
        y = 50
        for line in gt_text_8.split("\n"):
            p8.insert_text(fitz.Point(50, y), line, fontsize=11, fontname="helv")
            y += 22
        specimens.append(
            {
                "specimen_id": "BENCH-08-AMBIGUOUS-DOC",
                "category": "Ambiguous Document",
                "filename": "bench_08_ambiguous_memo.pdf",
                "file_type": "PDF",
                "bytes": doc8.tobytes(),
                "expected_doc_type": "OTHER_UNKNOWN",
                "expected_certain": False,
                "gt_text": gt_text_8,
                "gt_entities": {
                    "DATE": {"2026-03-20"},
                },
                "gt_table_cells": [],
                "expected_financial_status": None,
            }
        )
        doc8.close()

        # 9. Multi-Page Document (3-Page Contract Addendum)
        doc9 = fitz.open()
        gt_pages_9 = [
            "MASTER SERVICE AGREEMENT\nPage 1 of 3\nEffective Date: 2026-01-20\nBetween Meridian Logistics Corp and Helios GmbH",
            "TERMS AND CONDITIONS\nPage 2 of 3\nSection 4: Delivery obligations and milestone schedule.\nPenalty Cap: $15,000.00",
            "EXECUTION AND SIGNATURES\nPage 3 of 3\nGoverning Law: Germany\nAuthorized Signatory: Elena Rostova\nSigned Date: 2026-01-22",
        ]
        for p_txt in gt_pages_9:
            pg = doc9.new_page(width=595, height=842)
            y = 50
            for line in p_txt.split("\n"):
                pg.insert_text(fitz.Point(50, y), line, fontsize=11, fontname="helv")
                y += 22
        specimens.append(
            {
                "specimen_id": "BENCH-09-MULTIPAGE-DOC",
                "category": "Multi-Page Document (3 Pages)",
                "filename": "bench_09_multipage_agreement.pdf",
                "file_type": "PDF",
                "bytes": doc9.tobytes(),
                "expected_doc_type": "CONTRACT",
                "expected_certain": True,
                "gt_text": "\n".join(gt_pages_9),
                "gt_entities": {
                    "DATE": {"2026-01-20", "2026-01-22"},
                    "MONETARY_AMOUNT": {"USD 15000.00"},
                },
                "gt_table_cells": [],
                "expected_financial_status": None,
            }
        )
        doc9.close()

        # 10. Table-Heavy Document (Commercial Invoice with Arithmetic Mismatch for Financial Validation Test)
        doc10 = fitz.open()
        p10 = doc10.new_page(width=595, height=842)
        gt_text_10 = (
            "COMMERCIAL INVOICE\n"
            "Invoice No: INV-2026-9901\n"
            "Invoice Date: 2026-03-10\n"
            "Vendor: Helios Precision Components GmbH\n"
            "Bill To: Meridian Logistics Corp\n"
            "Subtotal: $10,000.00\n"
            "Tax: $1,900.00\n"
            "Total Amount Due: $14,500.00"
        )
        y = 50
        for line in gt_text_10.split("\n"):
            p10.insert_text(fitz.Point(50, y), line, fontsize=11, fontname="helv")
            y += 22
        rows10 = [
            ["Item Code", "Description", "Qty", "Unit Cost", "Line Total"],
            ["HX-101", "Optical Gyroscope", "2", "$2,500.00", "$5,000.00"],
            ["HX-204", "Thermal Telemetry Bus", "2", "$1,500.00", "$3,000.00"],
            ["HX-309", "Shielded Harness", "4", "$500.00", "$2,000.00"],
        ]
        ty = 260
        for r_idx, r_vals in enumerate(rows10):
            tx = 40
            for c_val in r_vals:
                p10.draw_rect(fitz.Rect(tx, ty, tx + 100, ty + 22), color=(0.2, 0.2, 0.2))
                p10.insert_text(
                    fitz.Point(tx + 4, ty + 15),
                    c_val,
                    fontsize=9.0,
                    fontname="hebo" if r_idx == 0 else "helv",
                )
                tx += 100
            ty += 22
        specimens.append(
            {
                "specimen_id": "BENCH-10-TABLE-HEAVY-INVOICE",
                "category": "Table-Heavy Invoice (Arithmetic Discrepancy)",
                "filename": "bench_10_table_heavy_invoice.pdf",
                "file_type": "PDF",
                "bytes": doc10.tobytes(),
                "expected_doc_type": "COMMERCIAL_INVOICE",
                "expected_certain": True,
                "gt_text": gt_text_10
                + "\n"
                + "\n".join(" ".join(r) for r in rows10),
                "gt_entities": {
                    "INVOICE_NUMBER": {"INV-2026-9901"},
                    "DATE": {"2026-03-10"},
                    "MONETARY_AMOUNT": {
                        "USD 14500.00",
                        "USD 10000.00",
                        "USD 1900.00",
                        "USD 2500.00",
                        "USD 5000.00",
                        "USD 1500.00",
                        "USD 3000.00",
                        "USD 500.00",
                        "USD 2000.00",
                    },
                },
                "gt_table_cells": [
                    "HX-101",
                    "Optical Gyroscope",
                    "$5,000.00",
                    "HX-204",
                    "Thermal Telemetry Bus",
                    "$3,000.00",
                    "HX-309",
                    "Shielded Harness",
                    "$2,000.00",
                ],
                "expected_financial_status": "CONFIRMED_DATA_MISMATCH",
            }
        )
        doc10.close()

        return specimens

    @staticmethod
    def run_quality_benchmark() -> Dict[str, Any]:
        started_t = time.perf_counter()
        specimens = BenchmarkService._build_10_synthetic_specimens()

        specimen_reports: List[Dict[str, Any]] = []
        classification_correct = 0
        cer_values_native: List[float] = []
        cer_values_ocr: List[float] = []

        total_tp = 0
        total_fp = 0
        total_fn = 0

        total_gt_cells = 0
        matched_gt_cells = 0

        total_bboxes_checked = 0
        valid_bboxes_count = 0

        documents_bundle_for_context: List[Dict[str, Any]] = []

        for spec in specimens:
            t0 = time.perf_counter()
            doc_id = spec["specimen_id"]
            file_bytes = spec["bytes"]
            file_type = spec["file_type"]
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()

            ext_res = DualPathExtractionEngine.extract_document(
                file_bytes=file_bytes,
                file_type=file_type,
                document_id=doc_id,
            )
            struct_res = StructureIntelligenceEngine.analyze_document_structure(
                file_bytes=file_bytes,
                file_type=file_type,
                extraction_result=ext_res,
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            pred_type = struct_res.classification.document_type
            is_cls_match = pred_type == spec["expected_doc_type"]
            if is_cls_match:
                classification_correct += 1

            extracted_full_text = "\n".join(p.raw_text for p in ext_res.pages)
            cer = _compute_cer(spec["gt_text"], extracted_full_text)
            if ext_res.is_scanned:
                cer_values_ocr.append(cer)
            else:
                cer_values_native.append(cer)

            # Evaluate entity Precision / Recall on targeted ground-truth entity types
            pred_entities_by_type: Dict[str, Set[str]] = {}
            for ent in struct_res.entities:
                pred_entities_by_type.setdefault(ent.entity_type, set()).add(
                    ent.normalized_value
                )

            spec_tp = 0
            spec_fp = 0
            spec_fn = 0
            for e_type, gt_set in spec["gt_entities"].items():
                pred_set = pred_entities_by_type.get(e_type, set())
                tp = len(gt_set & pred_set)
                fn = len(gt_set - pred_set)
                # Only count FP if predicted entity of that type is not in ground truth
                fp = len(pred_set - gt_set)
                spec_tp += tp
                spec_fn += fn
                spec_fp += fp

            total_tp += spec_tp
            total_fp += spec_fp
            total_fn += spec_fn

            # Evaluate table cell extraction accuracy
            extracted_cells_text = {
                c.cell_text.strip()
                for tbl in struct_res.tables
                for c in tbl.cells
                if c.cell_text.strip()
            }
            spec_gt_cells = spec["gt_table_cells"]
            spec_matched_cells = sum(
                1
                for gt_c in spec_gt_cells
                if any(gt_c.lower() in ec.lower() for ec in extracted_cells_text)
            )
            total_gt_cells += len(spec_gt_cells)
            matched_gt_cells += spec_matched_cells

            # Evaluate bounding box localization validity
            spec_bbox_total = 0
            spec_bbox_valid = 0
            for p in ext_res.pages:
                pw, ph = p.width, p.height
                for blk in p.blocks:
                    bb = blk.bounding_box
                    spec_bbox_total += 1
                    if (
                        0.0 <= bb.get("x0", -1) <= bb.get("x1", -1) <= pw + 2.0
                        and 0.0 <= bb.get("y0", -1) <= bb.get("y1", -1) <= ph + 2.0
                    ):
                        spec_bbox_valid += 1
            total_bboxes_checked += spec_bbox_total
            valid_bboxes_count += spec_bbox_valid

            # Build in-memory document bundle for Phase 4 & Phase 5 evaluation
            documents_bundle_for_context.append(
                {
                    "id": doc_id,
                    "investigation_id": "BENCHMARK-INV-001",
                    "filename": spec["filename"],
                    "file_type": file_type,
                    "sha256_hash": sha256_hash,
                    "page_count": ext_res.page_count,
                    "extraction_method_summary": ext_res.extraction_method_summary,
                    "is_scanned": ext_res.is_scanned,
                    "average_confidence": ext_res.average_confidence,
                    "document_type": pred_type,
                    "document_type_label": struct_res.classification.display_label,
                    "classification_confidence": struct_res.classification.confidence,
                    "classification_is_certain": struct_res.classification.is_certain,
                    "pages": [
                        {
                            "page_number": p.page_number,
                            "width": p.width,
                            "height": p.height,
                            "extraction_method": p.extraction_method,
                            "is_scanned_page": p.is_scanned_page,
                            "raw_text": p.raw_text,
                            "extractions": [
                                {
                                    "id": f"{doc_id}-B{b.block_index}",
                                    "document_id": doc_id,
                                    "page_number": b.page_number,
                                    "block_index": b.block_index,
                                    "extracted_text": b.extracted_text,
                                    "field_name": b.field_name,
                                    "field_value": b.field_value,
                                    "bounding_box": b.bounding_box,
                                    "extraction_method": b.extraction_method,
                                    "confidence": b.confidence,
                                    "source_reference": b.source_reference,
                                }
                                for b in p.blocks
                            ],
                        }
                        for p in ext_res.pages
                    ],
                    "structured_fields": [
                        {
                            "id": f"{doc_id}-SF{b.block_index}",
                            "document_id": doc_id,
                            "page_number": b.page_number,
                            "block_index": b.block_index,
                            "extracted_text": b.extracted_text,
                            "field_name": b.field_name,
                            "field_value": b.field_value,
                            "bounding_box": b.bounding_box,
                            "extraction_method": b.extraction_method,
                            "confidence": b.confidence,
                            "source_reference": b.source_reference,
                        }
                        for p in ext_res.pages
                        for b in p.blocks
                        if b.field_name
                    ],
                    "layout_regions": [
                        {
                            "id": f"{doc_id}-{r.id}",
                            "document_id": doc_id,
                            "page_number": r.page_number,
                            "region_type": r.region_type,
                            "reading_order": r.reading_order,
                            "label": r.label,
                            "text_content": r.text_content,
                            "bounding_box": r.bounding_box,
                            "extraction_method": r.extraction_method,
                            "confidence": r.confidence,
                        }
                        for r in struct_res.layout_regions
                    ],
                    "tables": [
                        {
                            "id": f"{doc_id}-{t.table_identifier}",
                            "table_identifier": t.table_identifier,
                            "document_id": doc_id,
                            "page_number": t.page_number,
                            "row_count": t.row_count,
                            "column_count": t.column_count,
                            "headers": t.headers,
                            "bounding_box": t.bounding_box,
                            "extraction_method": t.extraction_method,
                            "confidence": t.confidence,
                            "cells": [
                                {
                                    "id": f"{doc_id}-{t.table_identifier}-R{c.row_index}C{c.col_index}",
                                    "row_index": c.row_index,
                                    "col_index": c.col_index,
                                    "cell_text": c.cell_text,
                                    "is_header": c.is_header,
                                    "bounding_box": c.bounding_box,
                                    "confidence": c.confidence,
                                }
                                for c in t.cells
                            ],
                        }
                        for t in struct_res.tables
                    ],
                    "entities": [
                        {
                            "id": f"{doc_id}-ENT-{idx}",
                            "document_id": doc_id,
                            "investigation_id": "BENCHMARK-INV-001",
                            "page_number": e.page_number,
                            "entity_type": e.entity_type,
                            "raw_value": e.raw_value,
                            "normalized_value": e.normalized_value,
                            "bounding_box": e.bounding_box,
                            "extraction_method": e.extraction_method,
                            "confidence": e.confidence,
                            "source_reference": e.source_reference,
                        }
                        for idx, e in enumerate(struct_res.entities)
                    ],
                }
            )

            specimen_reports.append(
                {
                    "specimen_id": doc_id,
                    "category": spec["category"],
                    "filename": spec["filename"],
                    "file_type": file_type,
                    "page_count": ext_res.page_count,
                    "extraction_method": ext_res.extraction_method_summary,
                    "expected_doc_type": spec["expected_doc_type"],
                    "predicted_doc_type": pred_type,
                    "classification_match": is_cls_match,
                    "classification_confidence": round(
                        struct_res.classification.confidence, 4
                    ),
                    "classification_is_certain": struct_res.classification.is_certain,
                    "cer": cer,
                    "entity_tp": spec_tp,
                    "entity_fp": spec_fp,
                    "entity_fn": spec_fn,
                    "gt_table_cells": len(spec_gt_cells),
                    "matched_table_cells": spec_matched_cells,
                    "bboxes_valid": f"{spec_bbox_valid}/{spec_bbox_total}",
                    "duration_ms": elapsed_ms,
                }
            )

        # Evaluate Phase 4 Contextual Intelligence & Financial Validation on the benchmark set
        ctx_out = ContextualIntelligenceEngine.analyze_investigation_context(
            investigation_id="BENCHMARK-INV-001",
            documents_bundle=documents_bundle_for_context,
            forensic_analyses_by_doc={},
        )

        # Check expected financial validation statuses on BENCH-01, BENCH-03, BENCH-10
        fin_by_doc: Dict[str, List[str]] = {}
        for fv in ctx_out.financial_validations:
            fin_by_doc.setdefault(fv["document_id"], []).append(fv["status"])

        fin_checks_expected = 0
        fin_checks_correct = 0
        for spec in specimens:
            exp_fin = spec["expected_financial_status"]
            if exp_fin:
                fin_checks_expected += 1
                observed_statuses = fin_by_doc.get(spec["specimen_id"], [])
                if exp_fin in observed_statuses:
                    fin_checks_correct += 1

        # Evaluate Phase 5 Evidence-Grounded Reasoning & Claim Completeness
        ctx_bundle_dict = {
            "analysis_id": "BENCH-CTX-001",
            "financial_validations": ctx_out.financial_validations,
            "findings": ctx_out.findings,
            "entity_matches": ctx_out.entity_matches,
            "timeline_events": ctx_out.timeline_events,
        }
        reas_out = InvestigationReasoningEngine.generate_investigation_reasoning(
            investigation_row={
                "id": "BENCHMARK-INV-001",
                "case_code": "VRT-BENCH-2026",
                "title": "Synthetic Quality Benchmark Suite",
                "classification": "FINANCIAL_FORENSICS",
                "priority": "HIGH",
                "lead_investigator": "VERITAS Benchmark Harness",
            },
            documents_bundle=documents_bundle_for_context,
            forensic_analyses=[],
            forensic_findings=[],
            contextual_bundle=ctx_bundle_dict,
            audit_logs_count=10,
            use_ai_provider_if_available=False,
        )

        manifest = reas_out.evidence_manifest
        claims_total = len(reas_out.claims)
        claims_fully_grounded = 0
        for clm in reas_out.claims:
            all_ids = clm.supporting_evidence_ids + clm.contradicting_evidence_ids
            if clm.supporting_evidence_ids and all(eid in manifest for eid in all_ids):
                claims_fully_grounded += 1

        precision = (
            round(total_tp / (total_tp + total_fp), 4)
            if (total_tp + total_fp) > 0
            else 1.0
        )
        recall = (
            round(total_tp / (total_tp + total_fn), 4)
            if (total_tp + total_fn) > 0
            else 1.0
        )
        f1_score = (
            round(2 * precision * recall / (precision + recall), 4)
            if (precision + recall) > 0
            else 0.0
        )

        classification_accuracy = round(classification_correct / len(specimens), 4)
        mean_cer_native = (
            round(sum(cer_values_native) / len(cer_values_native), 4)
            if cer_values_native
            else 0.0
        )
        mean_cer_ocr = (
            round(sum(cer_values_ocr) / len(cer_values_ocr), 4)
            if cer_values_ocr
            else 0.0
        )
        mean_cer_overall = round(
            (sum(cer_values_native) + sum(cer_values_ocr)) / len(specimens), 4
        )
        table_cell_accuracy = (
            round(matched_gt_cells / total_gt_cells, 4) if total_gt_cells > 0 else 1.0
        )
        bbox_localization_accuracy = (
            round(valid_bboxes_count / total_bboxes_checked, 4)
            if total_bboxes_checked > 0
            else 1.0
        )
        financial_calc_accuracy = (
            round(fin_checks_correct / fin_checks_expected, 4)
            if fin_checks_expected > 0
            else 1.0
        )
        evidence_completeness = (
            round(claims_fully_grounded / claims_total, 4)
            if claims_total > 0
            else 1.0
        )

        total_duration_ms = round((time.perf_counter() - started_t) * 1000.0, 2)

        return {
            "benchmark_suite_version": "1.0.0-phase6",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "isolated_from_production_db": True,
            "specimens_evaluated": len(specimens),
            "total_duration_ms": total_duration_ms,
            "aggregate_metrics": {
                "document_classification_accuracy": classification_accuracy,
                "ocr_cer_native_pdf": mean_cer_native,
                "ocr_cer_scanned_images": mean_cer_ocr,
                "ocr_cer_overall": mean_cer_overall,
                "entity_extraction_precision": precision,
                "entity_extraction_recall": recall,
                "entity_extraction_f1": f1_score,
                "table_cell_extraction_accuracy": table_cell_accuracy,
                "bounding_box_localization_accuracy": bbox_localization_accuracy,
                "financial_calculation_accuracy": financial_calc_accuracy,
                "evidence_reference_completeness": evidence_completeness,
                "grounded_claims_verified": f"{claims_fully_grounded}/{claims_total}",
            },
            "specimens": specimen_reports,
        }
