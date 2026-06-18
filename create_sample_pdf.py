"""
create_sample_pdf.py — generates data/sample_intake.pdf from the sample email.

Run once to produce the test PDF for the Marker integration demo.
Uses reportlab to produce a realistic multi-section compliance document
with headers, body text, and a structured table — the kind of layout
that breaks naive text extraction.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER

OUTPUT = "data/sample_intake.pdf"

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=letter,
    rightMargin=inch,
    leftMargin=inch,
    topMargin=inch,
    bottomMargin=inch,
)

styles = getSampleStyleSheet()

heading1 = ParagraphStyle(
    "Heading1Custom",
    parent=styles["Heading1"],
    fontSize=14,
    spaceAfter=6,
    textColor=colors.HexColor("#1a1a1a"),
)
heading2 = ParagraphStyle(
    "Heading2Custom",
    parent=styles["Heading2"],
    fontSize=11,
    spaceAfter=4,
    spaceBefore=12,
    textColor=colors.HexColor("#333333"),
)
normal = ParagraphStyle(
    "NormalCustom",
    parent=styles["Normal"],
    fontSize=10,
    leading=14,
    spaceAfter=6,
)
meta = ParagraphStyle(
    "Meta",
    parent=styles["Normal"],
    fontSize=9,
    textColor=colors.HexColor("#666666"),
    spaceAfter=2,
)
label = ParagraphStyle(
    "Label",
    parent=styles["Normal"],
    fontSize=9,
    textColor=colors.HexColor("#444444"),
    fontName="Helvetica-Bold",
)

story = []

# Header
story.append(Paragraph("CRESTVIEW CAPITAL GROUP", ParagraphStyle(
    "FirmName", parent=styles["Normal"],
    fontSize=11, fontName="Helvetica-Bold",
    textColor=colors.HexColor("#666666"), alignment=TA_CENTER,
)))
story.append(Paragraph("Client Onboarding — New Account Intake Form", ParagraphStyle(
    "DocTitle", parent=styles["Heading1"],
    fontSize=16, alignment=TA_CENTER, spaceAfter=4,
    textColor=colors.HexColor("#1a1a1a"),
)))
story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
story.append(Spacer(1, 0.15 * inch))

# Email metadata table
meta_data = [
    ["From:", "Sarah Chen <s.chen@crestview.com>"],
    ["To:", "onboarding-ops@crestview.com"],
    ["CC:", "David Holloway <d.holloway@crestview.com>"],
    ["Subject:", "New account enquiry — Kessler-Bright Advisory Group — please prioritise"],
    ["Date:", "Thursday, 9 January 2026"],
]
meta_table = Table(meta_data, colWidths=[1.0 * inch, 5.5 * inch])
meta_table.setStyle(TableStyle([
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
    ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#222222")),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
]))
story.append(meta_table)
story.append(Spacer(1, 0.2 * inch))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#eeeeee")))
story.append(Spacer(1, 0.15 * inch))

# Intro
story.append(Paragraph(
    "Hi team, forwarding this one from my network. The principals are keen to move quickly — "
    "they have capital sitting in a cash position and want to get allocated before end of Q1.",
    normal
))
story.append(Spacer(1, 0.1 * inch))

# Client section
story.append(Paragraph("CLIENT DETAILS", heading2))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
story.append(Spacer(1, 0.05 * inch))

client_data = [
    ["Entity Name:", "Kessler-Bright Advisory Group Ltd"],
    ["Domicile:", "Jersey, Channel Islands"],
    ["Entity Age:", "Approximately 8 years"],
    ["AUM:", "€58 million (approximately USD 63.2M at current rates)"],
    ["Strategy:", "Alternatives with real assets exposure"],
    ["Additional Vehicle:", "UK feeder vehicle for British LP investors"],
]
client_table = Table(client_data, colWidths=[1.6 * inch, 4.9 * inch])
client_table.setStyle(TableStyle([
    ("FONTSIZE", (0, 0), (-1, -1), 10),
    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#333333")),
    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
    ("BACKGROUND", (0, 1), (-1, 1), colors.white),
    ("BACKGROUND", (0, 3), (-1, 3), colors.white),
    ("BACKGROUND", (0, 5), (-1, 5), colors.white),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#eeeeee")),
]))
story.append(client_table)
story.append(Spacer(1, 0.15 * inch))

# Principals
story.append(Paragraph("PRINCIPALS", heading2))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
story.append(Spacer(1, 0.05 * inch))

principals_data = [
    ["Name", "Role", "Ownership", "Background", "PEP Status"],
    [
        "Marcus Kessler",
        "Managing Partner",
        "65%",
        "12 years HM Treasury. Last role: Senior Economic Advisor to Secretary of State for Business. Left 2016.",
        "YES — former senior government official",
    ],
    [
        "Dominique Bright",
        "Partner — Investor Relations",
        "35%",
        "French national, based in Paris. No government background.",
        "No",
    ],
]
principals_table = Table(
    principals_data,
    colWidths=[1.2 * inch, 1.0 * inch, 0.8 * inch, 2.5 * inch, 1.0 * inch]
)
principals_table.setStyle(TableStyle([
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fff8f8")),
    ("TEXTCOLOR", (4, 1), (4, 1), colors.HexColor("#cc0000")),
    ("FONTNAME", (4, 1), (4, 1), "Helvetica-Bold"),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#eeeeee")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
]))
story.append(principals_table)
story.append(Spacer(1, 0.15 * inch))

# Source of funds
story.append(Paragraph("SOURCE OF FUNDS", heading2))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
story.append(Paragraph(
    "Management fees and carried interest from their fund vehicles. They had a successful exit "
    "on their third fund in 2022, which is where most of the current AUM growth came from. "
    "The 2023 audited accounts are attached to the original email — Sarah has not reviewed them in detail.",
    normal
))

# Documentation
story.append(Paragraph("DOCUMENTATION STATUS", heading2))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
story.append(Spacer(1, 0.05 * inch))

docs_data = [
    ["Document", "Status", "Notes"],
    ["Fund formation documents", "Received", ""],
    ["LP list (24 names)", "Received — incomplete", "5 addresses missing. Updated version promised by end of next week."],
    ["2023 audited accounts", "Received — unreviewed", "Attached to original email. Not reviewed by Sarah."],
    ["Gulf LP KYC — Dubai individual", "Pending", "Flagged as longstanding clean relationship."],
    ["Gulf LP KYC — Abu Dhabi family office", "Pending", "Flagged as longstanding clean relationship."],
]
docs_table = Table(docs_data, colWidths=[1.8 * inch, 1.5 * inch, 3.2 * inch])
docs_table.setStyle(TableStyle([
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("TEXTCOLOR", (1, 2), (1, 2), colors.HexColor("#cc6600")),
    ("TEXTCOLOR", (1, 3), (1, 3), colors.HexColor("#cc6600")),
    ("TEXTCOLOR", (1, 4), (1, 4), colors.HexColor("#cc0000")),
    ("TEXTCOLOR", (1, 5), (1, 5), colors.HexColor("#cc0000")),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#eeeeee")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fafafa")),
    ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#fafafa")),
    ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#fafafa")),
]))
story.append(docs_table)
story.append(Spacer(1, 0.15 * inch))

# Timeline
story.append(Paragraph("TIMELINE & URGENCY", heading2))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
story.append(Paragraph(
    "<font color='#cc0000'><b>URGENT:</b></font> Client requests to be live within 2 weeks. "
    "Marcus Kessler has a board meeting on the 27th January and wants this resolved before then. "
    "Capital is currently sitting in a cash position. Sarah is available for a call with compliance if needed.",
    normal
))

story.append(Spacer(1, 0.1 * inch))
story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
story.append(Spacer(1, 0.05 * inch))
story.append(Paragraph(
    "This document was generated for demonstration purposes — Crestview Capital Group POC.",
    ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8,
                   textColor=colors.HexColor("#999999"), alignment=TA_CENTER)
))

doc.build(story)
print(f"Created: {OUTPUT}")
