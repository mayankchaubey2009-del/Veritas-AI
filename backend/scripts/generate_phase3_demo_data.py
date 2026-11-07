import io
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

SAMPLE_DIR = Path("/Users/mayankchaubey/Desktop/VERITAS-AI/sample-data")


def generate_clean_synthetic_invoice(output_path: Path) -> None:
    """
    1. One clean synthetic invoice (SYNTHETIC DEMONSTRATION MATERIAL).
    Consistent Helvetica typography, aligned left margin rail (X=50), clean table, single-pass metadata.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Top synthetic demonstration banner
    page.draw_rect(fitz.Rect(40, 22, 555, 40), color=(0.12, 0.25, 0.45), fill=(0.93, 0.96, 1.0))
    page.insert_text(
        fitz.Point(50, 34),
        "SYNTHETIC DEMONSTRATION MATERIAL — FOR FORENSIC EVALUATION ONLY (NO REAL PII/FINANCIAL DATA)",
        fontsize=8.0,
        fontname="helv",
        color=(0.1, 0.2, 0.45),
    )

    # Document Title & Header
    page.insert_text(
        fitz.Point(50, 72),
        "COMMERCIAL INVOICE",
        fontsize=18.0,
        fontname="hebo",
        color=(0.05, 0.1, 0.2),
    )
    page.insert_text(
        fitz.Point(50, 92),
        "Sovereign Procurement Reference Baseline — Clean Reference Copy",
        fontsize=9.5,
        fontname="helv",
        color=(0.3, 0.35, 0.45),
    )

    # Perfectly aligned Key-Value metadata block on X=50 rail
    kv_lines = [
        ("Invoice Number:", "INV-2026-8841"),
        ("Invoice Date:", "2026-10-15"),
        ("Purchase Order:", "PO-NS-2026-0412"),
        ("Vendor:", "Aegis Orbital Logistics Ltd"),
        ("Vendor Tax ID:", "TIN-99-4102884"),
        ("Bill To:", "Northstar Sovereign Holdings Inc"),
        ("Client Address:", "740 Meridian Plaza, Suite 1200, Zurich"),
        ("Beneficiary IBAN:", "CH9300000011623852957"),
    ]
    y_cursor = 126.0
    for label, val in kv_lines:
        page.insert_text(
            fitz.Point(50, y_cursor),
            f"{label} {val}",
            fontsize=10.0,
            fontname="helv",
            color=(0.1, 0.12, 0.16),
        )
        y_cursor += 18.0

    # Section Heading
    page.insert_text(
        fitz.Point(50, 290),
        "SCHEDULE OF DELIVERED EQUIPMENT & SERVICES",
        fontsize=11.0,
        fontname="hebo",
        color=(0.08, 0.15, 0.28),
    )

    # Clean 4x4 Vector Bordered Table (y=305..425)
    col_x = [50.0, 120.0, 340.0, 430.0, 545.0]
    row_y = [305.0, 332.0, 362.0, 392.0, 422.0]
    table_rows = [
        ["Item Code", "Description", "Qty", "Line Total"],
        ["AOL-101", "Cryogenic Telemetry Sensor Array", "2", "$95,000.00 USD"],
        ["AOL-204", "Redundant Optical Uplink Transceiver", "3", "$64,500.00 USD"],
        ["AOL-309", "Site Calibration & Validation Protocol", "1", "$30,000.00 USD"],
    ]

    # Header shading
    page.draw_rect(
        fitz.Rect(col_x[0], row_y[0], col_x[-1], row_y[1]),
        color=(0.2, 0.25, 0.35),
        fill=(0.92, 0.95, 0.98),
    )
    for r_idx in range(4):
        for c_idx in range(4):
            rect = fitz.Rect(col_x[c_idx], row_y[r_idx], col_x[c_idx + 1], row_y[r_idx + 1])
            page.draw_rect(rect, color=(0.4, 0.45, 0.55), width=0.7)
            fn = "hebo" if r_idx == 0 else "helv"
            page.insert_text(
                fitz.Point(col_x[c_idx] + 6, row_y[r_idx] + 18),
                table_rows[r_idx][c_idx],
                fontsize=9.5,
                fontname=fn,
                color=(0.08, 0.1, 0.15),
            )

    # Financial Summary block (aligned on X=50)
    page.insert_text(
        fitz.Point(50, 460),
        "Subtotal Amount: $189,500.00 USD",
        fontsize=10.0,
        fontname="helv",
        color=(0.1, 0.12, 0.16),
    )
    page.insert_text(
        fitz.Point(50, 478),
        "VAT (0% Export Exempt): $0.00 USD",
        fontsize=10.0,
        fontname="helv",
        color=(0.1, 0.12, 0.16),
    )
    page.insert_text(
        fitz.Point(50, 496),
        "Total Amount Due: $189,500.00 USD",
        fontsize=10.0,
        fontname="hebo",
        color=(0.05, 0.1, 0.2),
    )

    # Signature & Stamp Regions
    page.insert_text(
        fitz.Point(50, 560),
        "Authorized Signatory: Dr. Marcus Vance (Director of Billing)",
        fontsize=10.0,
        fontname="helv",
        color=(0.1, 0.12, 0.16),
    )
    page.draw_line(fitz.Point(50, 578), fitz.Point(250, 578), color=(0.3, 0.35, 0.4), width=0.8)

    # Vector Corporate Seal / Stamp
    stamp_rect = fitz.Rect(380, 535, 525, 600)
    page.draw_rect(stamp_rect, color=(0.75, 0.12, 0.15), width=1.6)
    page.insert_text(
        fitz.Point(392, 560),
        "OFFICIAL CORPORATE SEAL",
        fontsize=9.0,
        fontname="hebo",
        color=(0.75, 0.12, 0.15),
    )
    page.insert_text(
        fitz.Point(392, 578),
        "AEGIS ORBITAL VERIFIED",
        fontsize=8.5,
        fontname="helv",
        color=(0.75, 0.12, 0.15),
    )

    # Footer
    page.insert_text(
        fitz.Point(50, 795),
        "SYNTHETIC DEMONSTRATION DOCUMENT — VERITAS AI PHASE 3 FORENSIC SUITE | Page 1 of 1",
        fontsize=8.0,
        fontname="helv",
        color=(0.45, 0.5, 0.55),
    )

    doc.set_metadata(
        {
            "title": "Synthetic Clean Commercial Invoice INV-2026-8841",
            "author": "Aegis Orbital Automated Billing Engine (Synthetic Demo)",
            "subject": "SYNTHETIC DEMONSTRATION MATERIAL",
            "keywords": "SYNTHETIC, DEMO, CLEAN, INVOICE",
            "creator": "VERITAS Synthetic ERP Generator v1.0",
            "producer": "PyMuPDF Single-Pass PDF Engine",
            "creationDate": "D:20261015093000Z",
            "modDate": "D:20261015093000Z",
        }
    )
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()


def generate_inconsistent_synthetic_invoice(output_path: Path) -> None:
    """
    2. One synthetic invoice containing deliberately introduced visual inconsistencies
    (SYNTHETIC DEMONSTRATION MATERIAL):
    - Module A: Localized off-white background masking patch behind the altered Total Amount.
    - Module C: Font family substitution (Courier-Bold vs Helvetica) + point size jump (12.5pt vs 10pt)
      + baseline vertical offset (+2.3pt) on the Total Amount and IBAN spans.
    - Module D: Left-margin column rail drift (+7.5pt at X=57.5 vs X=50.0 rail) on Payment Reference
      and right-column value drift.
    - Module E: Modified timestamp (modDate > creationDate), PDF annotation object, and incremental save (2 %%EOF markers).
    - Module F: Embedded raster stamp XObject + signature region.
    - Module G: Visually occluded/zero-contrast native PDF text ('Original Approved Total: $189,500.00')
      masked underneath the altered total box.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Top synthetic demonstration banner
    page.draw_rect(fitz.Rect(40, 22, 555, 40), color=(0.55, 0.2, 0.1), fill=(1.0, 0.95, 0.92))
    page.insert_text(
        fitz.Point(50, 34),
        "SYNTHETIC DEMONSTRATION MATERIAL — DELIBERATE VISUAL INCONSISTENCIES SPECIMEN",
        fontsize=8.0,
        fontname="hebo",
        color=(0.55, 0.15, 0.08),
    )

    # Document Title & Header
    page.insert_text(
        fitz.Point(50, 72),
        "COMMERCIAL INVOICE",
        fontsize=18.0,
        fontname="hebo",
        color=(0.05, 0.1, 0.2),
    )
    page.insert_text(
        fitz.Point(50, 92),
        "Sovereign Procurement Submission — Disputed Counterparty Copy",
        fontsize=9.5,
        fontname="helv",
        color=(0.3, 0.35, 0.45),
    )

    # Key-value rows on X=50 rail, EXCEPT one row deliberately shifted to X=57.5 (Module D alignment anomaly)
    # and IBAN value set in Courier-Bold with a baseline shift (Module C typography anomaly)
    page.insert_text(fitz.Point(50, 126), "Invoice Number: INV-2026-8841", fontsize=10.0, fontname="helv")
    page.insert_text(fitz.Point(50, 144), "Invoice Date: 2026-10-15", fontsize=10.0, fontname="helv")
    page.insert_text(fitz.Point(50, 162), "Purchase Order: PO-NS-2026-0412", fontsize=10.0, fontname="helv")
    page.insert_text(fitz.Point(50, 180), "Vendor: Aegis Orbital Logistics Ltd", fontsize=10.0, fontname="helv")
    page.insert_text(fitz.Point(50, 198), "Vendor Tax ID: TIN-99-4102884", fontsize=10.0, fontname="helv")
    page.insert_text(fitz.Point(50, 216), "Bill To: Northstar Sovereign Holdings Inc", fontsize=10.0, fontname="helv")
    # Deliberate Module D Left-Margin Rail Drift (+7.5pt from X=50.0 rail)
    page.insert_text(
        fitz.Point(57.5, 234),
        "Payment Reference: ESCROW-OVERRIDE-9941",
        fontsize=10.0,
        fontname="helv",
    )
    # Deliberate Module C Intra-Line Font Family Substitution + Baseline Offset on Beneficiary IBAN
    page.insert_text(fitz.Point(50, 252), "Beneficiary IBAN:", fontsize=10.0, fontname="helv")
    page.insert_text(
        fitz.Point(145, 254.2),
        "CH9300000099887766551",
        fontsize=11.5,
        fontname="cobo",
        color=(0.05, 0.05, 0.05),
    )

    # Section Heading
    page.insert_text(
        fitz.Point(50, 290),
        "SCHEDULE OF DELIVERED EQUIPMENT & SERVICES",
        fontsize=11.0,
        fontname="hebo",
        color=(0.08, 0.15, 0.28),
    )

    # 4x4 Table with a deliberate right-column alignment drift on Row 1
    col_x = [50.0, 120.0, 340.0, 430.0, 545.0]
    row_y = [305.0, 332.0, 362.0, 392.0, 422.0]
    table_rows = [
        ["Item Code", "Description", "Qty", "Line Total"],
        ["AOL-101", "Cryogenic Telemetry Sensor Array", "2", "$395,000.00 USD"],
        ["AOL-204", "Redundant Optical Uplink Transceiver", "3", "$64,500.00 USD"],
        ["AOL-309", "Site Calibration & Validation Protocol", "1", "$30,000.00 USD"],
    ]

    page.draw_rect(
        fitz.Rect(col_x[0], row_y[0], col_x[-1], row_y[1]),
        color=(0.2, 0.25, 0.35),
        fill=(0.92, 0.95, 0.98),
    )
    for r_idx in range(4):
        for c_idx in range(4):
            rect = fitz.Rect(col_x[c_idx], row_y[r_idx], col_x[c_idx + 1], row_y[r_idx + 1])
            page.draw_rect(rect, color=(0.4, 0.45, 0.55), width=0.7)
            fn = "hebo" if r_idx == 0 else ("cobo" if (r_idx == 1 and c_idx == 3) else "helv")
            x_offset = 12.5 if (r_idx == 1 and c_idx == 3) else 6.0
            page.insert_text(
                fitz.Point(col_x[c_idx] + x_offset, row_y[r_idx] + 18),
                table_rows[r_idx][c_idx],
                fontsize=9.5,
                fontname=fn,
                color=(0.08, 0.1, 0.15),
            )

    # Module G: Hidden / Zero-Contrast Native Text Span (white text on white background)
    page.insert_text(
        fitz.Point(320, 460),
        "Superseded Original Total: $189,500.00 USD",
        fontsize=9.0,
        fontname="helv",
        color=(1.0, 1.0, 1.0),
    )

    # Financial Summary block with Module A Localized Off-White Patch + Module C Font/Size/Baseline jump
    page.insert_text(
        fitz.Point(50, 460),
        "Subtotal Amount: $489,500.00 USD",
        fontsize=10.0,
        fontname="helv",
    )
    page.insert_text(
        fitz.Point(50, 478),
        "VAT (0% Export Exempt): $0.00 USD",
        fontsize=10.0,
        fontname="helv",
    )

    # Module A: Localized off-white rectangular patch behind the altered Total Amount
    patch_rect = fitz.Rect(142, 484, 298, 503)
    page.draw_rect(patch_rect, color=None, fill=(0.94, 0.93, 0.89))

    page.insert_text(
        fitz.Point(50, 496),
        "Total Amount Due:",
        fontsize=10.0,
        fontname="hebo",
        color=(0.05, 0.1, 0.2),
    )
    # Module C: Font family switch (Courier-Bold) + size jump (12.5pt) + baseline shift (y=498.2 vs 496.0)
    page.insert_text(
        fitz.Point(148, 498.2),
        "$489,500.00 USD",
        fontsize=12.5,
        fontname="cobo",
        color=(0.02, 0.02, 0.02),
    )

    # Module E: Add a PDF Annotation object around the modified payment reference
    annot = page.add_rect_annot(fitz.Rect(48, 222, 310, 240))
    annot.set_info(
        title="External PDF Editor",
        content="Synthetic demonstration annotation layer over Payment Reference.",
    )
    annot.update()

    # Module F: Signature block + Embedded Raster XObject Stamp
    page.insert_text(
        fitz.Point(50, 560),
        "Authorized Signatory: Dr. Marcus Vance (Director of Billing)",
        fontsize=10.0,
        fontname="helv",
    )
    page.draw_line(fitz.Point(50, 578), fitz.Point(250, 578), color=(0.3, 0.35, 0.4), width=0.8)

    # Create a raster stamp image with a slightly grey background box and embed it as an XObject
    stamp_pil = Image.new("RGB", (260, 110), color=(234, 232, 226))
    s_draw = ImageDraw.Draw(stamp_pil)
    s_draw.rectangle([4, 4, 255, 105], outline=(195, 25, 30), width=3)
    s_draw.text((20, 24), "OFFICIAL CORPORATE SEAL", fill=(195, 25, 30))
    s_draw.text((20, 52), "AEGIS ORBITAL STAMPED", fill=(195, 25, 30))
    s_draw.text((20, 76), "SYNTHETIC DEMO XOBJECT", fill=(140, 30, 30))
    s_buf = io.BytesIO()
    stamp_pil.save(s_buf, format="JPEG", quality=72)
    page.insert_image(fitz.Rect(375, 530, 530, 605), stream=s_buf.getvalue())

    # Also keep visible stamp text nearby for Phase 2B layout region detection
    page.insert_text(
        fitz.Point(380, 618),
        "OFFICIAL CORPORATE SEAL — STAMP VERIFICATION",
        fontsize=8.5,
        fontname="hebo",
        color=(0.75, 0.12, 0.15),
    )

    # Footer
    page.insert_text(
        fitz.Point(50, 795),
        "SYNTHETIC DEMONSTRATION DOCUMENT (ALTERED SPECIMEN) — VERITAS AI PHASE 3 | Page 1 of 1",
        fontsize=8.0,
        fontname="helv",
        color=(0.45, 0.5, 0.55),
    )

    doc.set_metadata(
        {
            "title": "Synthetic Commercial Invoice INV-2026-8841 (Edited Copy)",
            "author": "Aegis Orbital Automated Billing Engine (Synthetic Demo)",
            "subject": "SYNTHETIC DEMONSTRATION MATERIAL — VISUAL INCONSISTENCIES",
            "keywords": "SYNTHETIC, DEMO, INCONSISTENT, INVOICE",
            "creator": "Desktop PDF Compositor Pro (Synthetic Demo)",
            "producer": "Modified PDF Writer v4.2",
            "creationDate": "D:20261015093000Z",
            "modDate": "D:20261029231419Z",
        }
    )

    # First save cleanly, then perform an incremental save so the file genuinely contains 2 %%EOF trailer markers!
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()

    doc2 = fitz.open(str(output_path))
    doc2.set_metadata(
        {
            "title": "Synthetic Commercial Invoice INV-2026-8841 (Edited Copy)",
            "author": "Aegis Orbital Automated Billing Engine (Synthetic Demo)",
            "subject": "SYNTHETIC DEMONSTRATION MATERIAL — VISUAL INCONSISTENCIES",
            "keywords": "SYNTHETIC, DEMO, INCONSISTENT, INVOICE",
            "creator": "Desktop PDF Compositor Pro (Synthetic Demo)",
            "producer": "Modified PDF Writer v4.2 (Incremental Save)",
            "creationDate": "D:20261015093000Z",
            "modDate": "D:20261029231419Z",
        }
    )
    doc2.saveIncr()
    doc2.close()


def generate_scanned_jpeg_receipt(output_path: Path) -> None:
    """
    3. One scanned receipt in JPEG format (SYNTHETIC DEMONSTRATION MATERIAL)
    Supports authentic JPEG ELA analysis + localized high-contrast spliced region + PaddleOCR extraction.
    """
    img = Image.new("RGB", (900, 1150), color=(248, 247, 243))
    draw = ImageDraw.Draw(img)

    try:
        font_banner = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 15)
        font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 28)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 20)
        font_body = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
    except Exception:
        font_banner = ImageFont.load_default()
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_body = ImageFont.load_default()

    draw.rectangle([35, 25, 865, 62], fill=(232, 238, 248), outline=(60, 90, 140), width=2)
    draw.text(
        (50, 35),
        "SYNTHETIC DEMONSTRATION MATERIAL - SCANNED ESCROW RECEIPT SPECIMEN",
        fill=(30, 55, 110),
        font=font_banner,
    )

    draw.text((55, 95), "OFFICIAL PAYMENT RECEIPT & DISBURSEMENT VOUCHER", fill=(20, 25, 35), font=font_title)
    draw.line([(55, 138), (845, 138)], fill=(120, 130, 145), width=2)

    lines = [
        "Receipt Number: RCP-2026-99201",
        "Date: 2026-10-18",
        "Related Invoice Number: INV-2026-8841",
        "Received From: Northstar Sovereign Holdings Inc",
        "Paid To Beneficiary: Aegis Orbital Logistics Ltd",
        "Beneficiary Account IBAN: CH9300000011623852957",
        "Payment Method: Sovereign Escrow Wire Settlement",
        "Amount Paid: $189,500.00 USD",
        "Payment Status: PAID IN FULL - VERIFIED ESCROW RELEASE",
        "Authorized Signatory: Helena Vance (Escrow Officer)",
    ]
    y = 175
    for line in lines:
        draw.text((60, y), line, fill=(25, 30, 40), font=font_body)
        y += 52

    # Save base scan at lower JPEG quality (Q=65) first so background has settled quantization
    first_pass = io.BytesIO()
    img.save(first_pass, format="JPEG", quality=65)
    first_pass.seek(0)
    base_jpeg = Image.open(first_pass).convert("RGB")

    # Paste a fresh high-saturation/sharp verification stamp patch onto the settled JPEG and re-save at Q=92
    # so ELA on JPEG detects a genuine localized recompression residual difference!
    patch_draw = ImageDraw.Draw(base_jpeg)
    patch_draw.rectangle([520, 740, 835, 890], fill=(255, 255, 255), outline=(210, 20, 30), width=4)
    patch_draw.text((542, 765), "ESCROW STAMP SEAL", fill=(210, 20, 30), font=font_sub)
    patch_draw.text((542, 805), "CLEARED: $189,500.00", fill=(210, 20, 30), font=font_sub)
    patch_draw.text((542, 845), "SYNTHETIC DEMO SEAL", fill=(160, 20, 30), font=font_banner)

    base_jpeg.save(str(output_path), format="JPEG", quality=92)


def generate_supporting_bank_statement(output_path: Path) -> None:
    """
    4. One synthetic supporting document (Bank Statement — SYNTHETIC DEMONSTRATION MATERIAL)
    Corroborates the clean invoice amount ($189,500.00 USD) and IBAN (CH9300000011623852957).
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    page.draw_rect(fitz.Rect(40, 22, 555, 40), color=(0.12, 0.25, 0.45), fill=(0.93, 0.96, 1.0))
    page.insert_text(
        fitz.Point(50, 34),
        "SYNTHETIC DEMONSTRATION MATERIAL — SUPPORTING BANK STATEMENT SPECIMEN",
        fontsize=8.0,
        fontname="helv",
        color=(0.1, 0.2, 0.45),
    )

    page.insert_text(
        fitz.Point(50, 72),
        "CORPORATE BANK STATEMENT OF ACCOUNT",
        fontsize=17.0,
        fontname="hebo",
        color=(0.05, 0.1, 0.2),
    )
    page.insert_text(
        fitz.Point(50, 92),
        "Meridian Sovereign Custody Bank — Institutional Settlement Ledger",
        fontsize=9.5,
        fontname="helv",
        color=(0.3, 0.35, 0.45),
    )

    kv_lines = [
        "Account Holder: Northstar Sovereign Holdings Inc",
        "Account IBAN: CH9300000011623852957",
        "Statement Period: 2026-10-01 to 2026-10-31",
        "Opening Balance: $1,250,000.00 USD",
        "Closing Balance: $1,060,500.00 USD",
    ]
    y_c = 126.0
    for line in kv_lines:
        page.insert_text(fitz.Point(50, y_c), line, fontsize=10.0, fontname="helv")
        y_c += 18.0

    page.insert_text(
        fitz.Point(50, 240),
        "SETTLED WIRE & ESCROW TRANSACTIONS",
        fontsize=11.0,
        fontname="hebo",
        color=(0.08, 0.15, 0.28),
    )

    col_x = [50.0, 120.0, 365.0, 455.0, 545.0]
    row_y = [255.0, 282.0, 312.0, 342.0]
    rows = [
        ["Posting Date", "Transaction Counterparty & Reference", "Debit", "Running Balance"],
        ["2026-10-15", "Invoice Recorded INV-2026-8841 (Aegis Orbital)", "$0.00 USD", "$1,250,000.00 USD"],
        ["2026-10-18", "Wire Settlement INV-2026-8841 (Aegis Orbital)", "$189,500.00 USD", "$1,060,500.00 USD"],
    ]
    page.draw_rect(
        fitz.Rect(col_x[0], row_y[0], col_x[-1], row_y[1]),
        color=(0.2, 0.25, 0.35),
        fill=(0.92, 0.95, 0.98),
    )
    for r_i in range(3):
        for c_i in range(4):
            rect = fitz.Rect(col_x[c_i], row_y[r_i], col_x[c_i + 1], row_y[r_i + 1])
            page.draw_rect(rect, color=(0.4, 0.45, 0.55), width=0.7)
            fn = "hebo" if r_i == 0 else "helv"
            page.insert_text(
                fitz.Point(col_x[c_i] + 5, row_y[r_i] + 18),
                rows[r_i][c_i],
                fontsize=8.5,
                fontname=fn,
            )

    page.insert_text(
        fitz.Point(50, 410),
        "Authorized Signatory: Viktor Lindqvist (Chief Custody Officer)",
        fontsize=10.0,
        fontname="helv",
    )
    page.insert_text(
        fitz.Point(50, 795),
        "SYNTHETIC DEMONSTRATION MATERIAL — VERITAS AI SUPPORTING STATEMENT | Page 1 of 1",
        fontsize=8.0,
        fontname="helv",
        color=(0.45, 0.5, 0.55),
    )

    doc.set_metadata(
        {
            "title": "Synthetic Supporting Bank Statement (Oct 2026)",
            "author": "Meridian Sovereign Custody Bank (Synthetic Demo)",
            "subject": "SYNTHETIC DEMONSTRATION MATERIAL",
            "creator": "Meridian Core Banking Ledger v3.1",
            "producer": "PyMuPDF Single-Pass PDF Engine",
            "creationDate": "D:20261031180000Z",
            "modDate": "D:20261031180000Z",
        }
    )
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()


def generate_all_phase3_demo_files() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    generate_clean_synthetic_invoice(SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf")
    generate_inconsistent_synthetic_invoice(SAMPLE_DIR / "demo_inconsistent_synthetic_invoice.pdf")
    generate_scanned_jpeg_receipt(SAMPLE_DIR / "demo_scanned_escrow_receipt.jpg")
    generate_supporting_bank_statement(SAMPLE_DIR / "demo_supporting_bank_statement.pdf")
    print("Generated all 4 Phase 3 synthetic demonstration documents in", SAMPLE_DIR)


if __name__ == "__main__":
    generate_all_phase3_demo_files()
