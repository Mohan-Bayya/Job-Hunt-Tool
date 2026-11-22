"""YOUR RESUME. The job tool builds every tailored resume from this file.

Step 1. Replace the placeholder text in the constants below (name, contact details, summary, skills,
        experience, education) with your own. Keep the same structure.
Step 2. Run   python3 build_resume_codes/build_resume_final.py   to build a test PDF and DOCX and
        look at them. It should fit on ONE page; the build prints a warning if a line wraps too far.

Rules the tool relies on
- Text between **double asterisks** is printed in bold.
- HEADLINE is "Job Title | Skill | Skill | Skill". The tool reorders the skills to match each job.
- SKILLS rows are "Category", "item, item, item". The tool decides which skills you have from the
  headline and this section only, so list every tool you actually know.
- EXPERIENCE[0] must be your current or latest job. The tool reorders ITS bullets for each posting.
  It never edits or invents text; it only changes the order of what you wrote.
- Write bullets that start with what you achieved and include numbers where you honestly can.

The tool refuses to build resumes while NAME is still "Your Name".
"""
import os
import re
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Table, TableStyle

# Test builds go here, next to the other generated files, wherever you run the command from.
OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "generated (resume)", "Your_Name_Resume")

NAME = "Your Name"
HEADLINE = "Data Engineer | Python | SQL | Spark | AWS"
LOCATION = "City, Country"
PHONE = "+00 0000000000"
EMAIL = "you@example.com"
LINKEDIN = "linkedin.com/in/your-name"

SUMMARY = (
    "SAMPLE TEXT, REPLACE IT. Two or three sentences: your role, years of experience, the main tools you "
    "use, and one result with a number, such as **cut a pipeline's runtime by 40%**."
)

SKILLS = [
    ("Languages", "Python, SQL, Bash"),
    ("Big Data", "Apache Spark, PySpark, ETL, Data Modeling"),
    ("Cloud", "AWS (S3, EMR, Glue, Athena), Docker, Git"),
    ("Orchestration", "Apache Airflow"),
    ("Databases", "PostgreSQL, MySQL, Parquet"),
]

EXPERIENCE = [
    {
        "title": "Your Job Title",
        "organization": "Company Name",
        "location": "City, Country",
        "dates": "Mon YYYY - Present",
        "bullets": [
            "SAMPLE, REPLACE: Built a **PySpark** pipeline on **AWS EMR** that processes **N GB/day** and "
            "delivers a daily output within an agreed deadline.",
            "SAMPLE, REPLACE: Cut a long-running job's runtime by **X%** by fixing slow joins and uneven data "
            "distribution.",
            "SAMPLE, REPLACE: Scheduled and monitored **N jobs** in **Airflow**, with alerts and retries.",
            "SAMPLE, REPLACE: Wrote data quality checks that caught **N issues** before they reached users.",
            "SAMPLE, REPLACE: Wrote **SQL** models for reporting used by **N teams**.",
        ],
    },
    {
        "title": "Previous Job Title or Internship",
        "organization": "Company Name",
        "location": "City, Country",
        "dates": "Mon YYYY - Mon YYYY",
        "bullets": [
            "SAMPLE, REPLACE: One line about what you built and the result.",
        ],
    },
]

EDUCATION = [
    {
        "school": "University Name",
        "location": "City, Country",
        "dates": "YYYY - YYYY",
        "degree": "Degree and Major | GPA: X.X/X.X",
    },
]

NAVY_HEX = "1F3864"
NAVY = RGBColor(0x1F, 0x38, 0x64)
FONT = "Arial"  # Installed on Windows and macOS, and available in Google Docs.
FONT_DIR = "/System/Library/Fonts/Supplemental"
DOCX_BODY_PT = 9.5  # Matches the PDF so both versions wrap the same way.

# Layout limits checked after the PDF is built.
MAX_SUMMARY_LINES = 3
MAX_SKILL_LINES = 1
MAX_BULLET_LINES = 2


def split_bold(text):
    """Yield (segment, is_bold) pairs from text that uses **bold** markup."""
    for part in re.split(r"(\*\*[^*]+\*\*)", text):
        if part.startswith("**") and part.endswith("**"):
            yield part[2:-2], True
        elif part:
            yield part, False


def plain(text):
    return text.replace("**", "")


# ---------------------------------------------------------------- DOCX

# Elements that must follow <w:pBdr> inside <w:pPr> (OOXML schema order).
PBDR_SUCCESSORS = (
    "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
    "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid",
    "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
    "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId",
    "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)


def style_run(run, size, bold=False, color=None):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    return run


def add_text(paragraph, text, size, bold=False, color=None):
    for segment, is_bold in split_bold(text):
        style_run(paragraph.add_run(segment), size, bold or is_bold, color)


def add_hyperlink(paragraph, url, text, size):
    rel_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rel_id)
    run = OxmlElement("w:r")
    run_props = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)
    run_props.append(fonts)
    font_size = OxmlElement("w:sz")
    font_size.set(qn("w:val"), str(int(size * 2)))
    run_props.append(font_size)
    run.append(run_props)
    text_element = OxmlElement("w:t")
    text_element.text = text
    run.append(text_element)
    link.append(run)
    paragraph._p.append(link)


def add_bottom_border(paragraph):
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", NAVY_HEX)):
        bottom.set(qn(key), value)
    borders.append(bottom)
    paragraph._p.get_or_add_pPr().insert_element_before(borders, *PBDR_SUCCESSORS)


def build_docx(path):
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.left_margin = section.right_margin = Inches(0.6)
    section.top_margin = section.bottom_margin = Inches(0.45)
    text_width = section.page_width - section.left_margin - section.right_margin

    props = document.core_properties
    props.title = f"{NAME} - Data Engineer Resume"
    props.author = NAME
    props.subject = "Data Engineer Resume"
    props.keywords = "Data Engineer, PySpark, Apache Spark, AWS, EMR, Airflow, Python, SQL, ETL"

    normal = document.styles["Normal"]
    normal.font.name = FONT
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.font.size = Pt(DOCX_BODY_PT)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.0

    def paragraph(before=0, after=0, align=None, keep=False, style=None):
        p = document.add_paragraph(style=style)
        fmt = p.paragraph_format
        fmt.space_before, fmt.space_after, fmt.keep_with_next = Pt(before), Pt(after), keep
        if align is not None:
            p.alignment = align
        return p

    def section_heading(text):
        p = paragraph(before=6, after=2, keep=True)
        style_run(p.add_run(text.upper()), 10.5, bold=True, color=NAVY)
        add_bottom_border(p)

    def entry_header(left_bold, left_rest, right):
        p = paragraph(before=3, after=1, keep=True)
        p.paragraph_format.tab_stops.add_tab_stop(text_width, WD_TAB_ALIGNMENT.RIGHT)
        style_run(p.add_run(left_bold), 10, bold=True)
        style_run(p.add_run(left_rest), DOCX_BODY_PT)
        style_run(p.add_run("\t" + right), DOCX_BODY_PT, bold=True)

    def bullet(text):
        # Word's built-in bulleted list: renders the same in Word, Google Docs, and LibreOffice,
        # and ATS parsers read it as a list item.
        p = paragraph(after=1.5, style="List Bullet")
        p.paragraph_format.left_indent = Inches(0.2)
        p.paragraph_format.first_line_indent = Inches(-0.16)
        add_text(p, text, DOCX_BODY_PT)

    p = paragraph(align=WD_ALIGN_PARAGRAPH.CENTER)
    style_run(p.add_run(NAME), 19, bold=True, color=NAVY)
    p = paragraph(align=WD_ALIGN_PARAGRAPH.CENTER, after=1)
    style_run(p.add_run(HEADLINE), 10.5, bold=True)
    p = paragraph(align=WD_ALIGN_PARAGRAPH.CENTER)
    style_run(p.add_run(f"{LOCATION} | {PHONE} | "), 9)
    add_hyperlink(p, f"mailto:{EMAIL}", EMAIL, 9)
    style_run(p.add_run(" | "), 9)
    add_hyperlink(p, f"https://www.{LINKEDIN}", LINKEDIN, 9)

    section_heading("Professional Summary")
    add_text(paragraph(), SUMMARY, DOCX_BODY_PT)

    section_heading("Technical Skills")
    for category, items in SKILLS:
        p = paragraph(after=0.5)
        style_run(p.add_run(f"{category}: "), DOCX_BODY_PT, bold=True)
        style_run(p.add_run(items), DOCX_BODY_PT)

    section_heading("Professional Experience")
    for job in EXPERIENCE:
        entry_header(f"{job['title']} | {job['organization']}", f" | {job['location']}", job["dates"])
        for text in job["bullets"]:
            bullet(text)

    section_heading("Education")
    for item in EDUCATION:
        entry_header(item["school"], f" | {item['location']}", item["dates"])
        style_run(paragraph(after=1).add_run(item["degree"]), DOCX_BODY_PT)

    document.save(path)


# ----------------------------------------------------------------- PDF

def register_pdf_fonts():
    """Embed Arial so bullets and symbols extract as real Unicode text.

    ReportLab's built-in Helvetica writes the bullet as an undefined byte, which ATS parsers
    and text extractors read as a control character instead of a bullet.
    """
    regular = os.path.join(FONT_DIR, "Arial.ttf")
    bold = os.path.join(FONT_DIR, "Arial Bold.ttf")
    if not (os.path.exists(regular) and os.path.exists(bold)):
        print("WARNING: Arial not found; using Helvetica, so bullets may not extract as text.")
        return "Helvetica", "Helvetica-Bold"
    pdfmetrics.registerFont(TTFont("Arial", regular))
    pdfmetrics.registerFont(TTFont("Arial-Bold", bold))
    pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                                  italic="Arial", boldItalic="Arial-Bold")
    return "Arial", "Arial-Bold"


def rich(text):
    """Escape XML and convert **bold** markup to ReportLab <b> tags."""
    return "".join(f"<b>{escape(s)}</b>" if b else escape(s) for s, b in split_bold(text))


def build_pdf(path):
    regular, bold = register_pdf_fonts()
    margin_x, margin_y = 0.6 * inch, 0.45 * inch
    width = letter[0] - 2 * margin_x
    doc = SimpleDocTemplate(
        path, pagesize=letter, leftMargin=margin_x, rightMargin=margin_x,
        topMargin=margin_y, bottomMargin=margin_y,
        title=f"{NAME} - Data Engineer Resume", author=NAME, subject="Data Engineer Resume",
        keywords=["Data Engineer", "PySpark", "Apache Spark", "AWS", "EMR", "Airflow", "Python", "SQL"],
    )
    body = ParagraphStyle("Body", fontName=regular, fontSize=9.6, leading=11.9)
    name = ParagraphStyle("Name", parent=body, fontName=bold, fontSize=19, leading=23,
                          alignment=TA_CENTER, textColor="#" + NAVY_HEX)
    headline = ParagraphStyle("Headline", parent=body, fontName=bold, fontSize=10.4,
                              leading=13, alignment=TA_CENTER)
    contact = ParagraphStyle("Contact", parent=body, fontSize=9, leading=11, alignment=TA_CENTER)
    heading = ParagraphStyle("Heading", parent=body, fontName=bold, fontSize=10.6, leading=13,
                             spaceBefore=6, textColor="#" + NAVY_HEX)
    skill = ParagraphStyle("Skill", parent=body, spaceAfter=0.6)
    entry_left = ParagraphStyle("EntryLeft", parent=body, fontSize=9.9, leading=12.2)
    entry_right = ParagraphStyle("EntryRight", parent=entry_left, alignment=TA_RIGHT)
    bullet = ParagraphStyle("Bullet", parent=body, fontSize=9.5, leading=11.8, leftIndent=11,
                            bulletIndent=1.5, bulletFontName=regular, spaceAfter=1.2)

    def section_heading(text):
        return [Paragraph(text.upper(), heading),
                HRFlowable(width="100%", thickness=0.7, color="#" + NAVY_HEX, spaceBefore=1, spaceAfter=3)]

    def entry_header(left_html, right_html):
        table = Table([[Paragraph(left_html, entry_left), Paragraph(right_html, entry_right)]],
                      colWidths=[width * 0.74, width * 0.26])
        table.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ]))
        return table

    checks = []  # (label, paragraph, max_lines)
    flow = [
        Paragraph(escape(NAME), name),
        Paragraph(escape(HEADLINE), headline),
        Paragraph(
            f"{escape(LOCATION)} | {escape(PHONE)} | "
            f'<link href="mailto:{EMAIL}">{escape(EMAIL)}</link> | '
            f'<link href="https://www.{LINKEDIN}">{escape(LINKEDIN)}</link>',
            contact,
        ),
    ]
    summary = Paragraph(rich(SUMMARY), body)
    checks.append(("summary", summary, MAX_SUMMARY_LINES))
    flow += section_heading("Professional Summary") + [summary]

    flow += section_heading("Technical Skills")
    for category, items in SKILLS:
        p = Paragraph(f"<b>{escape(category)}:</b> {escape(items)}", skill)
        checks.append((f"skills row '{category}'", p, MAX_SKILL_LINES))
        flow.append(p)

    flow += section_heading("Professional Experience")
    for job in EXPERIENCE:
        flow.append(entry_header(
            f"<b>{escape(job['title'])} | {escape(job['organization'])}</b> | {escape(job['location'])}",
            f"<b>{escape(job['dates'])}</b>",
        ))
        for text in job["bullets"]:
            p = Paragraph(rich(text), bullet, bulletText="\u2022")
            checks.append((f"bullet '{plain(text)[:50]}...'", p, MAX_BULLET_LINES))
            flow.append(p)

    flow += section_heading("Education")
    for item in EDUCATION:
        flow.append(entry_header(f"<b>{escape(item['school'])}</b> | {escape(item['location'])}",
                                 f"<b>{escape(item['dates'])}</b>"))
        flow.append(Paragraph(escape(item["degree"]), body))

    doc.build(flow)

    if doc.page > 1:
        print(f"WARNING: resume runs to {doc.page} pages; trim content to fit one page.")
    for label, p, max_lines in checks:
        lines = len(p.blPara.lines)
        if lines > max_lines:
            print(f"WARNING: {label} wraps to {lines} lines (limit {max_lines}).")


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    build_docx(OUTPUT + ".docx")
    build_pdf(OUTPUT + ".pdf")
    print(f"Built {OUTPUT}.pdf and {OUTPUT}.docx")
