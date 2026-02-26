import webview
import json
import os
import sys
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
    DATA_DIR = Path(os.path.expanduser("~")) / "InvoiceApp"
else:
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "invoices.db"
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS invoices (
        id TEXT PRIMARY KEY, factuurnummer TEXT UNIQUE,
        date TEXT, due_date TEXT, purpose TEXT, bestelnummer TEXT,
        customer_company TEXT, customer_dept TEXT, customer_address TEXT,
        customer_postal TEXT, customer_city TEXT, customer_country TEXT,
        customer_phone TEXT, customer_email TEXT, customer_kvk TEXT, customer_name TEXT,
        items TEXT, subtotaal REAL, btw_pct REAL, btw_amount REAL, totaal REAL,
        notes TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

def generate_factuurnummer(purpose):
    prefix_map = {"BOL": "BOL", "Best4Juniors": "B4J", "Other": "OTH", "": "INV"}
    prefix = prefix_map.get(purpose, "INV")
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    conn.close()
    rand = uuid.uuid4().hex[:4].upper()
    return f"{prefix}-NL{rand}{count+1:04d}"

def fmt_euro(val):
    """Format float as Dutch euro string: 1234.56 -> 1.234,56"""
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class API:
    def get_settings(self):
        conn = get_db()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        return {r["key"]: r["value"] for r in rows}

    def save_settings(self, data):
        conn = get_db()
        for k, v in data.items():
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, str(v)))
        conn.commit()
        conn.close()
        return {"success": True}

    def upload_logo(self, base64data, filename):
        import base64 as b64
        ext = filename.rsplit(".", 1)[-1].lower()
        logo_path = UPLOADS_DIR / f"logo.{ext}"
        data = base64data.split(",", 1)[-1]
        with open(logo_path, "wb") as f:
            f.write(b64.b64decode(data))
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", ("logo_path", str(logo_path)))
        conn.commit()
        conn.close()
        return {"success": True}

    def get_logo_base64(self):
        import base64 as b64
        conn = get_db()
        row = conn.execute("SELECT value FROM settings WHERE key='logo_path'").fetchone()
        conn.close()
        if not row:
            return {"data": None}
        path = Path(row["value"])
        if not path.exists():
            return {"data": None}
        ext = path.suffix.lstrip(".")
        with open(path, "rb") as f:
            data = b64.b64encode(f.read()).decode()
        return {"data": f"data:image/{ext};base64,{data}"}

    def new_invoice_number(self, purpose=""):
        return {"factuurnummer": generate_factuurnummer(purpose)}

    def save_invoice(self, data):
        conn = get_db()
        inv_id = data.get("id") or str(uuid.uuid4())
        now = datetime.now().isoformat()
        items = data.get("items", [])
        items_json = json.dumps(items)
        btw_pct = float(data.get("btw_pct", 21))
        # Price is INCL. BTW → total = sum(prijs * aantal), extract subtotaal
        totaal = round(sum(float(i.get("prijs",0)) * float(i.get("aantal",0)) for i in items), 2)
        subtotaal = round(totaal / (1 + btw_pct / 100), 2)
        btw_amount = round(totaal - subtotaal, 2)
        existing = conn.execute("SELECT id FROM invoices WHERE id=?", (inv_id,)).fetchone()
        vals = (data.get("factuurnummer",""), data.get("date",""), data.get("due_date",""),
                data.get("purpose",""), data.get("bestelnummer",""),
                data.get("customer_company",""), data.get("customer_dept",""),
                data.get("customer_address",""), data.get("customer_postal",""),
                data.get("customer_city",""), data.get("customer_country","Netherlands"),
                data.get("customer_phone",""), data.get("customer_email",""),
                data.get("customer_kvk",""), data.get("customer_name",""),
                items_json, subtotaal, btw_pct, btw_amount, totaal, data.get("notes",""))
        if existing:
            conn.execute('''UPDATE invoices SET factuurnummer=?,date=?,due_date=?,purpose=?,bestelnummer=?,
                customer_company=?,customer_dept=?,customer_address=?,customer_postal=?,customer_city=?,
                customer_country=?,customer_phone=?,customer_email=?,customer_kvk=?,customer_name=?,
                items=?,subtotaal=?,btw_pct=?,btw_amount=?,totaal=?,notes=? WHERE id=?''',
                vals + (inv_id,))
        else:
            conn.execute('''INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (inv_id,) + vals + (now,))
        conn.commit()
        conn.close()
        return {"success": True, "id": inv_id, "totaal": totaal,
                "subtotaal": subtotaal, "btw_amount": btw_amount}

    def get_invoices(self, filters=None):
        conn = get_db()
        q = "SELECT * FROM invoices WHERE 1=1"
        params = []
        if filters:
            if filters.get("purpose") and filters["purpose"] != "all":
                q += " AND purpose=?"; params.append(filters["purpose"])
            if filters.get("date_from"):
                q += " AND date>=?"; params.append(filters["date_from"])
            if filters.get("date_to"):
                q += " AND date<=?"; params.append(filters["date_to"])
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, params).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["items"] = json.loads(d["items"]) if d["items"] else []
            result.append(d)
        return result

    def get_invoice(self, inv_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()
        conn.close()
        if not row: return None
        d = dict(row)
        d["items"] = json.loads(d["items"]) if d["items"] else []
        return d

    def delete_invoice(self, inv_id):
        conn = get_db()
        conn.execute("DELETE FROM invoices WHERE id=?", (inv_id,))
        conn.commit()
        conn.close()
        return {"success": True}

    def get_report(self, filters=None):
        invoices = self.get_invoices(filters)
        total_revenue = sum(i["totaal"] for i in invoices)
        total_btw = sum(i["btw_amount"] for i in invoices)
        subtotaal = sum(i["subtotaal"] for i in invoices)
        by_purpose = {}
        for inv in invoices:
            p = inv["purpose"] or "Other"
            if p not in by_purpose:
                by_purpose[p] = {"count": 0, "revenue": 0, "btw": 0, "subtotaal": 0}
            by_purpose[p]["count"] += 1
            by_purpose[p]["revenue"] += inv["totaal"]
            by_purpose[p]["btw"] += inv["btw_amount"]
            by_purpose[p]["subtotaal"] += inv["subtotaal"]
        return {"count": len(invoices), "subtotaal": round(subtotaal,2),
                "total_btw": round(total_btw,2), "total_revenue": round(total_revenue,2),
                "by_purpose": by_purpose}

    def export_csv(self):
        import csv, io
        invoices = self.get_invoices()
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["Factuurnummer","Datum","Klant","Doel","Subtotaal","BTW","Totaal"])
        for inv in invoices:
            w.writerow([inv["factuurnummer"], inv["date"],
                        inv["customer_company"] or inv["customer_name"],
                        inv["purpose"], inv["subtotaal"], inv["btw_amount"], inv["totaal"]])
        return {"csv": out.getvalue()}

    def get_invoice_html(self, inv_id):
        inv = self.get_invoice(inv_id)
        if not inv: return {"success": False}
        settings = self.get_settings()
        logo = self.get_logo_base64()
        html = build_invoice_html(inv, settings, logo.get("data"))
        return {"success": True, "html": html}

    def save_invoice_file(self, inv_id):
        """Save invoice as PDF using reportlab (A4, proper layout)"""
        inv = self.get_invoice(inv_id)
        if not inv: return {"success": False, "error": "Invoice not found"}
        settings = self.get_settings()
        logo_data = self.get_logo_base64()
        safe_name = inv["factuurnummer"].replace("/","_").replace("\\","_").replace(":","_")
        pdf_path = DATA_DIR / f"Factuur_{safe_name}.pdf"
        try:
            generate_pdf_reportlab(inv, settings, logo_data.get("data"), str(pdf_path))
            return {"success": True, "path": str(pdf_path)}
        except Exception as e:
            # Fallback to HTML if PDF fails
            html = build_invoice_html(inv, settings, logo_data.get("data"))
            html_path = DATA_DIR / f"Factuur_{safe_name}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            return {"success": True, "path": str(html_path), "fallback": True}

    def save_report_html(self, html_content, filename):
        """Save report HTML to file"""
        path = DATA_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return {"success": True, "path": str(path)}

    def open_file(self, path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess; subprocess.run(["open", path])
            else:
                import subprocess; subprocess.run(["xdg-open", path])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_data_dir(self):
        return str(DATA_DIR)


def generate_pdf_reportlab(inv, settings, logo_b64, output_path):
    """A4 PDF matching the sample invoice exactly. Footer pinned to page bottom."""
    import io, base64
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, HRFlowable, Image)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from reportlab.pdfgen import canvas as rl_canvas

    s    = settings
    W, H = A4
    LM   = 18*mm
    RM   = 18*mm
    TM   = 16*mm
    BM   = 20*mm       # leave room for footer
    CW   = W - LM - RM

    # colours
    BLACK = colors.HexColor("#111111")
    MGRAY = colors.HexColor("#444444")
    LGRAY = colors.HexColor("#777777")
    THEAD = colors.white
    TBORD = colors.HexColor("#CCCCCC")
    TLINE = colors.HexColor("#EEEEEE")
    WHITE = colors.white
    DARK  = colors.HexColor("#111111")

    def P(txt, size=9, bold=False, clr=MGRAY, align=TA_LEFT, lead=None):
        fn = "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(str(txt), ParagraphStyle(
            "s", fontSize=size, fontName=fn, textColor=clr,
            alignment=align, leading=lead or size*1.45,
            spaceAfter=0, spaceBefore=0))

    def eu(v):
        s2 = f"{float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
        return f"\u20ac {s2}"

    # ── footer drawn on every page ──────────────────────────────
    support = s.get("support_email") or s.get("email","")
    def draw_footer(canv, doc):
        canv.saveState()
        canv.setStrokeColor(TBORD)
        canv.setLineWidth(0.5)
        footer_y = BM - 10*mm
        canv.line(LM, footer_y + 5*mm, W - RM, footer_y + 5*mm)
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(LGRAY)
        canv.drawCentredString(W/2, footer_y, f"Vragen over deze factuur? Mail ons via {support}")
        canv.restoreState()

    # ── logo ────────────────────────────────────────────────────
    if logo_b64:
        try:
            raw = base64.b64decode(logo_b64.split(",",1)[-1])
            logo_cell = Image(io.BytesIO(raw), width=44*mm, height=18*mm, kind="proportional")
        except:
            logo_cell = P(s.get("company_name",""), 16, True, BLACK)
    else:
        logo_cell = P(s.get("company_name",""), 16, True, BLACK)

    # ── company info ─────────────────────────────────────────────
    co = []
    if s.get("address"):    co.append(s["address"])
    pc = (s.get("postal","")+" "+s.get("city","")).strip()
    if pc:                  co.append(pc)
    if s.get("phone"):      co.append("Tel: "+s["phone"])
    if s.get("email"):      co.append("E-mail: "+s["email"])
    if s.get("website"):    co.append("Website: "+s["website"])
    if s.get("kvk"):        co.append("KVK: "+s["kvk"])
    if s.get("btw_number"): co.append("BTW: "+s["btw_number"])
    co_para = P("<br/>".join(co), 8.5, clr=BLACK)

    # ── invoice meta ─────────────────────────────────────────────
    meta_rows = [
        [P("Factuurnummer:", 8.5, clr=MGRAY, align=TA_RIGHT),
         P(inv.get("factuurnummer",""), 8.5, clr=BLACK, align=TA_RIGHT)],
        [P("Datum:",         8.5, clr=MGRAY, align=TA_RIGHT),
         P(inv.get("date",""),          8.5, clr=BLACK, align=TA_RIGHT)],
        [P("Vervaldatum:",   8.5, clr=MGRAY, align=TA_RIGHT),
         P(inv.get("due_date",""),      8.5, clr=BLACK, align=TA_RIGHT)],
    ]
    if inv.get("bestelnummer"):
        meta_rows.append([
            P("Bestelnummer:", 8.5, clr=MGRAY, align=TA_RIGHT),
            P(inv["bestelnummer"],      8.5, clr=BLACK, align=TA_RIGHT)])

    # ── customer block under meta ────────────────────────────────
    meta_rows.append([P(""), P("")])   # spacer row
    meta_rows.append([P("Klantgegevens:", 8.5, True, BLACK, TA_RIGHT),
                      P("", 8.5)])

    company = inv.get("customer_company","").strip()
    dept    = inv.get("customer_dept","").strip()
    cname   = inv.get("customer_name","").strip()
    addr    = inv.get("customer_address","").strip()
    postal  = inv.get("customer_postal","").strip()
    city    = inv.get("customer_city","").strip()
    country = inv.get("customer_country","NL").strip()
    cust = []
    if company: cust.append(company + (" t.a.v. "+dept if dept else ""))
    if cname:   cust.append(cname)
    if addr:    cust.append(addr)
    pc2 = (postal+" "+city).strip()
    if pc2:     cust.append(pc2)
    if country: cust.append(country)
    for line in cust:
        meta_rows.append([P(""), P(line, 8.5, clr=BLACK, align=TA_RIGHT)])

    meta_tbl = Table(meta_rows, colWidths=[CW*0.24, CW*0.26])
    meta_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 1.5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1.5),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))

    # ── header: logo+co LEFT | FACTUUR+meta RIGHT ────────────────
    hdr_tbl = Table(
        [[[logo_cell, Spacer(1,3*mm), co_para],
          [P("FACTUUR", 26, True, BLACK, TA_RIGHT), Spacer(1,3*mm), meta_tbl]]],
        colWidths=[CW*0.50, CW*0.50])
    hdr_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))

    # ── BTW calc ─────────────────────────────────────────────────
    btw_pct = float(inv.get("btw_pct", 21))
    totaal  = float(inv.get("totaal", 0))
    sub     = round(totaal / (1 + btw_pct/100), 2)
    btw     = round(totaal - sub, 2)

    # ── items table ──────────────────────────────────────────────
    rows = [[
        P("Omschrijving", 9, True, BLACK),
        P("Aantal",       9, True, BLACK, TA_RIGHT),
        P("Prijs (\u20ac)", 9, True, BLACK, TA_RIGHT),
        P("Totaal (\u20ac)", 9, True, BLACK, TA_RIGHT),
    ]]
    for item in inv.get("items", []):
        pr = float(item.get("prijs",  0))
        an = float(item.get("aantal", 0))
        ns = str(int(an)) if an == int(an) else str(an)
        rows.append([
            P(item.get("productnaam",""), 9, clr=BLACK),
            P(ns,       9, clr=MGRAY, align=TA_RIGHT),
            P(eu(pr),   9, clr=MGRAY, align=TA_RIGHT),
            P(eu(pr*an),9, clr=MGRAY, align=TA_RIGHT),
        ])

    items_tbl = Table(rows, colWidths=[CW*0.52, CW*0.12, CW*0.18, CW*0.18], repeatRows=1)
    items_tbl.setStyle(TableStyle([
        # header
        ("LINEABOVE",     (0,0), (-1,0), 0.8, TBORD),
        ("LINEBELOW",     (0,0), (-1,0), 0.8, TBORD),
        ("TOPPADDING",    (0,0), (-1,0), 7),
        ("BOTTOMPADDING", (0,0), (-1,0), 7),
        # data
        ("TOPPADDING",    (0,1), (-1,-1), 7),
        ("BOTTOMPADDING", (0,1), (-1,-1), 7),
        ("LINEBELOW",     (0,1), (-1,-2), 0.3, TLINE),
        # col separators
        ("LINEAFTER",     (0,0), (2,-1), 0.5, TBORD),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
        ("RIGHTPADDING",  (0,0), (-1,-1), 7),
    ]))

    # ── totals ───────────────────────────────────────────────────
    TW = CW * 0.42
    SW = CW - TW
    tot_data = [
        [P("Subtotaal (excl. BTW):", 9, clr=MGRAY), P(eu(sub),    9, clr=BLACK, align=TA_RIGHT)],
        [P(f"BTW ({btw_pct:.0f}%):", 9, clr=MGRAY), P(eu(btw),    9, clr=BLACK, align=TA_RIGHT)],
        [P("TOTAAL (incl. BTW):",    9, True, WHITE),P(eu(totaal), 9, True, WHITE, TA_RIGHT)],
    ]
    tot_tbl = Table(tot_data, colWidths=[TW*0.58, TW*0.42])
    tot_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("LINEBELOW",     (0,0), (-1,1), 0.3, TLINE),
        ("BACKGROUND",    (0,2), (-1,2), DARK),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    outer_tot = Table([[Spacer(SW,1), tot_tbl]], colWidths=[SW, TW])
    outer_tot.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0),(-1,-1), 0), ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0), ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
    ]))

    # ── notes ────────────────────────────────────────────────────
    extra = []
    if inv.get("notes","").strip():
        extra += [Spacer(1,4*mm), P(inv["notes"], 8.5, clr=LGRAY)]

    # ── build doc ────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=LM, rightMargin=RM,
        topMargin=TM,  bottomMargin=BM,
        title=f"Factuur {inv.get('factuurnummer','')}",
    )

    story = [
        hdr_tbl,
        Spacer(1, 6*mm),
        HRFlowable(width=CW, thickness=0.8, color=TBORD, spaceAfter=4*mm),
        items_tbl,
        Spacer(1, 5*mm),
        outer_tot,
        *extra,
    ]

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)


def build_invoice_html(inv, settings, logo_b64=None):
    """
    Generates invoice HTML that matches the sample exactly:
    - White page, no coloured bar
    - Logo top-left | FACTUUR title top-right
    - Company info left | meta + Klantgegevens right (all right-aligned)
    - Horizontal rule
    - Items table with borders
    - Totals right-aligned (dark grand total row)
    - Footer pinned to bottom of A4 page
    """
    s = settings

    # Logo
    if logo_b64:
        logo_html = f'<img src="{logo_b64}" style="max-height:52pt;max-width:160pt;object-fit:contain;display:block;" alt="Logo">'
    else:
        logo_html = f'<div style="font-size:20pt;font-weight:800;color:#111;">{s.get("company_name","")}</div>'

    # Company info
    co = []
    if s.get("address"):    co.append(s["address"])
    pc = (s.get("postal","")+" "+s.get("city","")).strip()
    if pc:                  co.append(pc)
    if s.get("phone"):      co.append("Tel: "+s["phone"])
    if s.get("email"):      co.append("E-mail: "+s["email"])
    if s.get("website"):    co.append("Website: "+s["website"])
    if s.get("kvk"):        co.append("KVK: "+s["kvk"])
    if s.get("btw_number"): co.append("BTW: "+s["btw_number"])
    co_html = "<br>".join(co)

    # Customer lines (right-aligned, below meta)
    cust = []
    company = inv.get("customer_company","").strip()
    dept    = inv.get("customer_dept","").strip()
    cname   = inv.get("customer_name","").strip()
    addr    = inv.get("customer_address","").strip()
    postal  = inv.get("customer_postal","").strip()
    city    = inv.get("customer_city","").strip()
    country = inv.get("customer_country","NL").strip()
    if company: cust.append(company + (" t.a.v. "+dept if dept else ""))
    if cname:   cust.append(cname)
    if addr:    cust.append(addr)
    pc2 = (postal+" "+city).strip()
    if pc2:     cust.append(pc2)
    if country: cust.append(country)
    cust_html = "<br>".join(cust)

    # Items
    btw_pct   = float(inv.get("btw_pct", 21))
    totaal    = float(inv.get("totaal", 0))
    subtotaal = round(totaal / (1 + btw_pct / 100), 2)
    btw_amt   = round(totaal - subtotaal, 2)

    items_rows = ""
    for item in inv.get("items", []):
        p  = float(item.get("prijs", 0))
        n  = float(item.get("aantal", 0))
        ns = str(int(n)) if n == int(n) else str(n)
        items_rows += f"""<tr>
          <td class="td-name">{item.get("productnaam","")}</td>
          <td class="td-r">{ns}</td>
          <td class="td-r">€ {fmt_euro(p)}</td>
          <td class="td-r td-bold">€ {fmt_euro(p*n)}</td>
        </tr>"""

    bestelnr = f'<tr><td class="ml">Bestelnummer:</td><td class="mv">{inv.get("bestelnummer","")}</td></tr>' if inv.get("bestelnummer") else ""
    notes_html = f'<p style="margin-top:10pt;font-size:8.5pt;color:#777;">{inv.get("notes","")}</p>' if inv.get("notes","").strip() else ""
    support = s.get("support_email") or s.get("email","")

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<title>Factuur {inv.get("factuurnummer","")}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html{{height:100%;}}
  body{{
    font-family:Arial,Helvetica,sans-serif;
    font-size:9pt;
    color:#333;
    background:#e8e8e8;
    min-height:100%;
  }}
  /* A4 page wrapper */
  .page{{
    width:210mm;
    min-height:297mm;
    margin:0 auto;
    background:white;
    padding:16mm 18mm 14mm 18mm;
    position:relative;
    display:flex;
    flex-direction:column;
  }}
  /* Header row: logo left | FACTUUR right */
  .hdr{{display:table;width:100%;margin-bottom:10pt;}}
  .hdr-l{{display:table-cell;vertical-align:top;width:50%;}}
  .hdr-r{{display:table-cell;vertical-align:top;width:50%;text-align:right;}}
  .factuur-title{{font-size:26pt;font-weight:700;letter-spacing:1px;color:#111;line-height:1;}}
  /* Info row: company info left | meta+customer right */
  .info{{display:table;width:100%;margin-top:6pt;}}
  .info-l{{display:table-cell;vertical-align:top;width:50%;}}
  .info-r{{display:table-cell;vertical-align:top;width:50%;text-align:right;}}
  .co-info{{font-size:8.5pt;line-height:1.65;color:#333;}}
  /* Meta table */
  .meta{{border-collapse:collapse;margin-left:auto;}}
  .meta td{{padding:1.5pt 0;font-size:8.5pt;line-height:1.55;}}
  .ml{{color:#555;padding-right:14pt;white-space:nowrap;text-align:left;}}
  .mv{{color:#111;font-weight:normal;text-align:right;white-space:nowrap;}}
  /* Klantgegevens */
  .klant-label{{font-size:8.5pt;font-weight:bold;color:#333;margin-top:8pt;text-align:right;}}
  .klant-body{{font-size:8.5pt;line-height:1.65;color:#333;text-align:right;margin-top:1pt;}}
  /* Divider */
  .divider{{height:1px;background:#ccc;margin:10pt 0;}}
  /* Items table */
  table.items{{width:100%;border-collapse:collapse;}}
  table.items th{{
    padding:7pt 8pt;font-size:9pt;font-weight:bold;
    color:#333;background:transparent;
    border-top:1px solid #ccc;border-bottom:1px solid #ccc;
    text-align:left;
  }}
  table.items th.th-r{{text-align:right;}}
  .td-name{{padding:8pt 8pt;font-size:9pt;color:#333;border-bottom:1px solid #eee;}}
  .td-r{{padding:8pt 8pt;font-size:9pt;color:#333;text-align:right;border-bottom:1px solid #eee;}}
  .td-bold{{font-weight:normal;}}
  table.items tbody tr:last-child td{{border-bottom:none;}}
  /* Totals */
  .totals-wrap{{margin-top:8pt;}}
  .totals-tbl{{margin-left:auto;border-collapse:collapse;width:230pt;}}
  .totals-tbl td{{padding:4pt 8pt;font-size:9pt;}}
  .totals-tbl td.tl{{color:#333;text-align:left;}}
  .totals-tbl td.tv{{color:#333;text-align:right;white-space:nowrap;}}
  .tot-grand td{{background:#111;color:white!important;font-weight:bold;padding:6pt 8pt;}}
  /* Content area grows to push footer down */
  .content-area{{flex:1;}}
  /* Footer — pinned to bottom of page */
  .footer{{
    position:absolute;
    bottom:14mm;
    left:18mm;
    right:18mm;
    text-align:center;
    font-size:8pt;
    color:#777;
    border-top:1px solid #ddd;
    padding-top:6pt;
  }}
  @media print{{
    body{{background:white;}}
    .page{{margin:0;width:100%;min-height:0;padding:12mm 15mm 20mm 15mm;}}
    @page{{size:A4;margin:0;}}
  }}
</style>
</head>
<body>
<div class="page">

  <!-- HEADER: Logo | FACTUUR -->
  <div class="hdr">
    <div class="hdr-l">{logo_html}</div>
    <div class="hdr-r"><div class="factuur-title">FACTUUR</div></div>
  </div>

  <!-- INFO: Company left | Meta + Klantgegevens right -->
  <div class="info">
    <div class="info-l">
      <div class="co-info">{co_html}</div>
    </div>
    <div class="info-r">
      <table class="meta">
        <tr><td class="ml">Factuurnummer:</td><td class="mv">{inv.get("factuurnummer","")}</td></tr>
        <tr><td class="ml">Datum:</td><td class="mv">{inv.get("date","")}</td></tr>
        <tr><td class="ml">Vervaldatum:</td><td class="mv">{inv.get("due_date","")}</td></tr>
        {bestelnr}
      </table>
      <div class="klant-label">Klantgegevens:</div>
      <div class="klant-body">{cust_html}</div>
    </div>
  </div>

  <!-- DIVIDER -->
  <div class="divider"></div>

  <!-- ITEMS -->
  <div class="content-area">
    <table class="items">
      <thead>
        <tr>
          <th style="width:56%;">Omschrijving</th>
          <th class="th-r" style="width:10%;">Aantal</th>
          <th class="th-r" style="width:17%;">Prijs (€)</th>
          <th class="th-r" style="width:17%;">Totaal (€)</th>
        </tr>
      </thead>
      <tbody>{items_rows}</tbody>
    </table>

    <!-- TOTALS -->
    <div class="totals-wrap">
      <table class="totals-tbl">
        <tr><td class="tl">Subtotaal (excl. BTW):</td><td class="tv">€ {fmt_euro(subtotaal)}</td></tr>
        <tr><td class="tl">BTW ({btw_pct:.0f}%):</td><td class="tv">€ {fmt_euro(btw_amt)}</td></tr>
        <tr class="tot-grand"><td class="tl">TOTAAL (incl. BTW):</td><td class="tv">€ {fmt_euro(totaal)}</td></tr>
      </table>
    </div>

    {notes_html}
  </div>

  <!-- FOOTER pinned to bottom -->
  <div class="footer">
    Vragen over deze factuur? Mail ons via {support}
  </div>

</div>
</body>
</html>"""



def build_report_html(report_data, filters_label):
    by_purpose = report_data.get("by_purpose", {})
    rows = ""
    for p, d in by_purpose.items():
        rows += f"""<tr>
          <td>{p}</td>
          <td style="text-align:center">{d['count']}</td>
          <td style="text-align:right">€ {fmt_euro(d['subtotaal'])}</td>
          <td style="text-align:right">€ {fmt_euro(d['btw'])}</td>
          <td style="text-align:right;font-weight:700">€ {fmt_euro(d['revenue'])}</td>
        </tr>"""
    now = datetime.now().strftime("%d-%m-%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Inter',Arial,sans-serif; background:#f5f5f5; padding:20px; }}
  .wrapper {{ max-width:800px; margin:0 auto; background:white; border-radius:12px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,.08); }}
  .top-bar {{ height:6px; background:linear-gradient(90deg,#1a1a2e,#0f3460); }}
  .content {{ padding:32px; }}
  h1 {{ font-size:22pt; font-weight:800; color:#1a1a2e; margin-bottom:4px; }}
  .sub {{ font-size:10pt; color:#999; margin-bottom:24px; }}
  .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:28px; }}
  .stat {{ background:#f8f9fc; border-radius:10px; padding:16px; }}
  .stat-label {{ font-size:9pt; font-weight:700; color:#aaa; text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }}
  .stat-value {{ font-size:18pt; font-weight:800; color:#1a1a2e; }}
  h2 {{ font-size:12pt; font-weight:700; color:#1a1a2e; margin-bottom:12px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ padding:9px 12px; text-align:left; font-size:9pt; font-weight:700; color:#888; text-transform:uppercase; letter-spacing:.5px; border-bottom:2px solid #e8e8e8; background:#fafafa; }}
  td {{ padding:10px 12px; border-bottom:1px solid #f0f0f0; font-size:9.5pt; color:#333; }}
  .footer {{ margin-top:24px; text-align:center; font-size:8pt; color:#ccc; }}
  @media print {{ body {{ background:white; padding:0; }} .wrapper {{ box-shadow:none; border-radius:0; }} @page {{ size:A4; margin:10mm; }} }}
</style>
</head><body>
<div class="wrapper">
  <div class="top-bar"></div>
  <div class="content">
    <h1>Omzetrapport</h1>
    <div class="sub">Periode: {filters_label} &nbsp;·&nbsp; Gegenereerd op: {now}</div>
    <div class="stats">
      <div class="stat"><div class="stat-label">Facturen</div><div class="stat-value">{report_data['count']}</div></div>
      <div class="stat"><div class="stat-label">Subtotaal</div><div class="stat-value">€ {fmt_euro(report_data['subtotaal'])}</div></div>
      <div class="stat"><div class="stat-label">BTW</div><div class="stat-value">€ {fmt_euro(report_data['total_btw'])}</div></div>
      <div class="stat"><div class="stat-label">Omzet</div><div class="stat-value">€ {fmt_euro(report_data['total_revenue'])}</div></div>
    </div>
    <h2>Per doel</h2>
    <table>
      <thead><tr><th>Doel</th><th style="text-align:center">Facturen</th><th style="text-align:right">Subtotaal</th><th style="text-align:right">BTW</th><th style="text-align:right">Totaal</th></tr></thead>
      <tbody>{rows if rows else '<tr><td colspan="5" style="text-align:center;color:#ccc;padding:20px;">Geen gegevens</td></tr>'}</tbody>
    </table>
    <div class="footer">Invoice Manager · {now}</div>
  </div>
</div>
</body></html>"""


class App:
    def __init__(self):
        self.api = API()

    def run(self):
        init_db()
        html_file = BASE_DIR / "src" / "index.html"
        window = webview.create_window(
            "Invoice Manager", str(html_file),
            js_api=self.api, width=1260, height=840,
            min_size=(960, 640), background_color="#F2F4F8"
        )
        webview.start(debug=False)

if __name__ == "__main__":
    App().run()
