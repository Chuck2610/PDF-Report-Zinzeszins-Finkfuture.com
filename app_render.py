
from flask import Flask, request, send_file, abort, make_response
from flask_cors import CORS, cross_origin
from io import BytesIO
from datetime import datetime, date
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
# ✅ Correct import for TOC (ReportLab >=3)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

app = Flask(__name__)

# Restrict CORS to your domains (add both variants)
ALLOWED_ORIGINS = ["https://finkfuture.com", "https://www.finkfuture.com", "http://localhost:5500", "http://127.0.0.1:5500"]
CORS(app,
     resources={r"/generate-pdf": {"origins": ALLOWED_ORIGINS}},
     supports_credentials=False,
     methods=["POST", "OPTIONS"],
     allow_headers=["Content-Type"],
     max_age=600)

def calc_plan(initial_capital: float, daily_rate: float, months: int, start_date: date):
    import calendar
    months_out = []
    capital = initial_capital
    y = start_date.year
    m = start_date.month
    for mi in range(months):
        dim = calendar.monthrange(y, m)[1]
        first_day = start_date.day if mi == 0 else 1
        gross_sum = fee_sum = reinvest_sum = 0.0
        month_start_cap = capital
        rows = []
        for d in range(first_day, dim+1):
            gross = capital * daily_rate
            fee = gross * 0.10
            reinvest = gross * 0.90
            end_cap = capital + reinvest
            rows.append([d, capital, gross, fee, reinvest, end_cap])
            gross_sum += gross; fee_sum += fee; reinvest_sum += reinvest
            capital = end_cap
        months_out.append({
            "label": date(y,m,1).strftime("%B %Y"),
            "rows": rows,
            "totals": { "start": month_start_cap, "end": capital, "gross": gross_sum, "fee": fee_sum, "reinvest": reinvest_sum }
        })
        m += 1
        if m > 12: m = 1; y += 1
    overall = {
        "gross": sum(mo["totals"]["gross"] for mo in months_out),
        "fee": sum(mo["totals"]["fee"] for mo in months_out),
        "reinvest": sum(mo["totals"]["reinvest"] for mo in months_out),
        "final": months_out[-1]["totals"]["end"] if months_out else initial_capital
    }
    return months_out, overall

class TOCDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height-1*cm, id='F1')
        template = PageTemplate(id='normal', frames=[frame], onPage=self._header_footer)
        self.addPageTemplates(template)
    def _header_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(doc.pagesize[0]-doc.rightMargin, 1.2*cm, f"Seite {doc.page}")
        canvas.restoreState()
    def afterFlowable(self, flowable):
        from reportlab.platypus import Paragraph
        if isinstance(flowable, Paragraph):
            style_name = flowable.style.name
            if style_name in ("H1","H2"):
                level = 0 if style_name == "H1" else 1
                text = flowable.getPlainText()
                self.notify('TOCEntry', (level, text, self.page))

def build_pdf(trader_name, capital, daily_rate, months, start_date):
    buf = BytesIO()
    doc = TOCDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm, title="Copy Trader Businessplan")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCover", fontSize=26, leading=32, textColor=colors.HexColor("#0b1721"), alignment=1, spaceAfter=12))
    styles.add(ParagraphStyle(name="SubCover", fontSize=13, leading=18, textColor=colors.HexColor("#5f6b76"), alignment=1, spaceAfter=4))
    styles.add(ParagraphStyle(name="H1", fontSize=18, leading=24, textColor=colors.HexColor("#00b0b8"), spaceBefore=10, spaceAfter=10))
    styles.add(ParagraphStyle(name="H2", fontSize=14, leading=20, textColor=colors.HexColor("#0b1721"), spaceBefore=8, spaceAfter=6))
    styles.add(ParagraphStyle(name="Body", fontSize=11, leading=16, textColor=colors.HexColor("#0b1721")))
    styles.add(ParagraphStyle(name="Info", fontSize=11, leading=16, backColor=colors.HexColor("#e9f7ff"), textColor=colors.HexColor("#0b1721"), leftIndent=6, rightIndent=6, spaceBefore=6, spaceAfter=6))
    styles.add(ParagraphStyle(name="Footer", fontSize=9, leading=12, alignment=1, textColor=colors.HexColor("#666666")))

    story = []

    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Flowable
    class TopBar(Flowable):
        def __init__(self, h=36): self.h = h
        def draw(self):
            self.canv.setFillColor(HexColor("#00d8d8"))
            w = self.canv._pagesize[0]
            self.canv.rect(0, self.canv._pagesize[1]-self.h, w, self.h, fill=1, stroke=0)

    story.append(TopBar(36))
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph(f"Businessplan – {trader_name}", styles["TitleCover"]))
    story.append(Paragraph("Zinseszinsstrategie im Daytrading", styles["SubCover"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(datetime.now().strftime("Erstellt am %d.%m.%Y"), styles["SubCover"]))
    story.append(Spacer(1, 8*cm))
    story.append(Paragraph("© 2025 Tim Finkbeiner – Alle Rechte vorbehalten", styles["Footer"]))
    story.append(PageBreak())

    story.append(Paragraph("Inhaltsverzeichnis", styles["H1"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(fontSize=11, name='TOCHeading1', leftIndent=0, firstLineIndent=0, spaceBefore=4, leading=14),
        ParagraphStyle(fontSize=10, name='TOCHeading2', leftIndent=12, firstLineIndent=0, spaceBefore=2, leading=12),
    ]
    story.append(toc)
    story.append(PageBreak())

    story.append(Paragraph("Überblick", styles["H1"]))
    story.append(Paragraph(
        "Dieser Businessplan beschreibt die Zinseszinsstrategie eines Copy Traders. "
        "Die täglichen Gewinne werden nach Abzug einer 10%igen Gebühr zu 90% reinvestiert. "
        "Damit wächst das Kapital kontinuierlich – professionell, seriös und sauber dokumentiert.", styles["Body"]
    ))

    story.append(Paragraph("Finanzielle Ausgangsdaten", styles["H1"]))
    eur = lambda x: f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    data = [
        ["Copy Trader", trader_name],
        ["Startdatum", start_date.strftime("%d.%m.%Y")],
        ["Startkapital", eur(capital)],
        ["Tägliche Verzinsung", f"{daily_rate*100:.2f}%"],
        ["Laufzeit (Monate)", str(months)],
    ]
    t = Table(data, colWidths=[7*cm, 7*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), colors.HexColor("#f0f6f8")),
        ('TEXTCOLOR',(0,0),(-1,-1), colors.HexColor("#0b1721")),
        ('GRID',(0,0),(-1,-1), 0.25, colors.gray),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('BOTTOMPADDING',(0,0),(-1,-1),6), ('TOPPADDING',(0,0),(-1,-1),6),
    ]))
    story.append(t)

    months_out, overall = calc_plan(capital, daily_rate, months, start_date)
    story.append(Paragraph("Kennzahlen & Ergebnisübersicht", styles["H1"]))
    kpi = Table([
        ["Startkapital", eur(capital), "Kumul. Gewinn (brutto)", eur(overall["gross"])],
        ["Gebühren (10%)", eur(overall["fee"]), "Endkapital", eur(overall["final"])],
    ], colWidths=[5*cm, 4.5*cm, 5*cm, 4.5*cm])
    kpi.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1), colors.whitesmoke),
        ('TEXTCOLOR',(0,0),(-1,-1), colors.HexColor("#0b1721")),
        ('BOX',(0,0),(-1,-1), 0.4, colors.gray),
        ('INNERGRID',(0,0),(-1,-1), 0.25, colors.gray),
        ('FONTNAME',(0,0),(-1,-1),'Helvetica'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('BOTTOMPADDING',(0,0),(-1,-1),8), ('TOPPADDING',(0,0),(-1,-1),8),
    ]))
    story.append(kpi)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Hinweis: 10% der Tagesgewinne werden als Gebühr abgezogen, 90% werden reinvestiert. "
        "Somit entspricht das Wachstum pro Tag 90% des Bruttogewinns auf das jeweils aktuelle Kapital.", styles["Info"]
    ))

    for mi, mo in enumerate(months_out, start=1):
        story.append(Paragraph(f"Monat {mi}: {mo['label']}", styles["H2"]))
        header = ["Tag", "Startkapital", "Gewinn (brutto)", "Fee 10%", "Reinvest 90%", "Endkapital"]
        rows = [header]
        for r in mo["rows"]:
            d, start_cap, gross, fee, reinv, end_cap = r
            rows.append([d, eur(start_cap), eur(gross), eur(fee), eur(reinv), eur(end_cap)])
        table = Table(rows, colWidths=[1.4*cm, 3.2*cm, 3.2*cm, 3.0*cm, 3.2*cm, 3.2*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0), colors.HexColor("#eefcff")),
            ('TEXTCOLOR',(0,0),(-1,-1), colors.HexColor("#0b1721")),
            ('GRID',(0,0),(-1,-1), 0.25, colors.gray),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('BOTTOMPADDING',(0,0),(-1,-1),5), ('TOPPADDING',(0,0),(-1,-1),5),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("Zinseszins – Erklärung", styles["H1"]))
    expl = [
        "💸 <b>Der tägliche Zinseszins – Dein geheimer Wachstumsbooster im Daytrading</b><br/><br/>"
        "Stell dir vor, dein Tradingkapital ist wie ein Schneeball, den du einen Hügel hinunterrollst. "
        "Mit jedem Tag, an dem du Gewinne machst und diese direkt wieder einsetzt, wird der Schneeball größer und größer. "
        "Das ist täglicher Zinseszins in der Praxis.",
        "🧮 <b>Beispiel: Kleine tägliche Gewinne – große Wirkung</b><br/>"
        "Startkapital: 5.000 €<br/>Durchschnittlicher Gewinn pro Tag: 0,2 %<br/>Handelstage pro Jahr: 365<br/><br/>"
        "Wenn du deine Gewinne jeden Tag wieder ins Kapital steckst, sieht das so aus:<br/>"
        "<b>5.000 € × (1 + 0,002)<sup>365</sup> ≈ 13.316 €</b><br/><br/>"
        "✅ Aus 5.000 € werden in einem Jahr über 13.000 €, nur durch den Zinseszinseffekt! "
        "Du verdienst also nicht nur auf dein Startkapital, sondern jeden Tag auch auf deine Vortagesgewinne.",
        "🌟 <b>Warum das so stark ist</b><br/>"
        "📈 Dein Kapital wächst täglich, nicht nur einmal im Jahr.<br/>"
        "🔁 Jeder Gewinn arbeitet für dich weiter, ab dem nächsten Tag.<br/>"
        "🧠 Selbst kleine Prozentsätze summieren sich über viele Tage extrem.<br/>"
        "⏳ Je länger du dranbleibst, desto stärker wird der Effekt.",
        "💪 <b>Realitätsnah gedacht</b><br/>"
        "Natürlich hat jeder Trader auch mal Verlusttage – das ist normal. "
        "Aber wenn du mehr Gewinner- als Verlusttage hast und konsequent deine Gewinne im Konto lässt, "
        "baust du Schritt für Schritt ein immer größeres Tradingkapital auf.",
        "Beispiele:<br/>"
        "0,2 % Gewinn auf 5.000 € = 10 € am Tag<br/>"
        "0,2 % Gewinn auf 10.000 € = 20 € am Tag<br/>"
        "0,2 % Gewinn auf 20.000 € = 40 € am Tag<br/>"
        "➡️ Gleiches Können – aber viel mehr Ertrag, nur weil du dein Kapital wachsen lässt.",
        "📝 <b>Zusammengefasst</b><br/>"
        "💰 Täglicher Zinseszins ist im Daytrading wie ein „Turbo“. "
        "📆 Kleine tägliche Gewinne, regelmäßig reinvestiert, erzeugen große Jahresergebnisse. "
        "🧠 Du musst keine Riesensprünge machen – Kontinuität ist der Schlüssel. "
        "🚀 Je länger du diszipliniert handelst, desto stärker wirkt der Effekt.<br/><br/>"
        "© 2025 Tim Finkbeiner – Alle Rechte vorbehalten"
    ]
    for p in expl:
        story.append(Paragraph(p, styles["Body"]))
        story.append(Spacer(1, 0.2*cm))

    doc.build(story)
    buf.seek(0)
    return buf

@app.route("/generate-pdf", methods=["OPTIONS"])
@cross_origin(origins=ALLOWED_ORIGINS, methods=["POST","OPTIONS"], headers=["Content-Type"])
def options_pdf():
    return "", 204

@app.post("/generate-pdf")
@cross_origin(origins=ALLOWED_ORIGINS, methods=["POST"], headers=["Content-Type"])
def generate_pdf():
    try:
        data = request.get_json(force=True)
        trader_name = data.get("trader_name","—").strip()[:80]
        capital = float(data.get("capital", 0.0))
        daily_rate = float(data.get("daily_rate", 0.0))
        months = int(data.get("months", 12))
        sd_str = data.get("start_date")
        if sd_str:
            start_date = datetime.strptime(sd_str, "%Y-%m-%d").date()
        else:
            start_date = date.today()
    except Exception as e:
        return abort(400, f"Bad payload: {e}")

    pdf = build_pdf(trader_name, capital, daily_rate, months, start_date)
    filename = f"Businessplan_{trader_name.replace(' ','_')}.pdf"
    return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name=filename)
