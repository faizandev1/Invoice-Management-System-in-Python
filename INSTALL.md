# Invoice Manager — Installation Guide

## System Requirements
- Windows 10 / 11 (64-bit)
- Python 3.11 (for rebuilding from source)
- .NET Framework 4.8 (usually pre-installed on Windows 10)

---

## Option A: Run from Source (Recommended for developers)

### Step 1 — Install Python 3.11
Download from https://www.python.org/downloads/release/python-3119/
Select "Add Python to PATH" during install.

### Step 2 — Install Dependencies
Open Command Prompt in the project folder and run:
```
pip install -r requirements.txt
```

### Step 3 — Run the Application
```
python main.py
```

---

## Option B: Build .EXE (Windows Standalone)

After completing Option A steps 1-2:

```
pyinstaller InvoiceManager.spec
```

The built EXE will be in the `dist/` folder: `dist/InvoiceManager.exe`

Double-click `InvoiceManager.exe` to launch — no Python required on target machine.

---

## Data Storage
All invoice data is stored locally at:
```
C:\Users\<YourName>\InvoiceApp\
  invoices.db       ← SQLite database (all invoices + settings)
  uploads\          ← Uploaded logo files
  invoice_*.html    ← Generated invoice HTML/PDF files
```

---

## Features
- ✅ New Invoice with auto-generated factuurnummer
- ✅ Customer details (Dutch format)
- ✅ Dynamic product/service rows with auto-totals
- ✅ BTW (VAT) calculation (default 21%, configurable)
- ✅ Invoice list with search & filter
- ✅ Invoice preview
- ✅ PDF/HTML generation & auto-open
- ✅ CSV export
- ✅ Revenue reports by period and purpose
- ✅ Company settings with logo upload
- ✅ 100% offline — no internet required

---

## Troubleshooting

**App doesn't open:**
- Make sure .NET Framework 4.8 is installed
- Try running from Command Prompt to see error messages: `python main.py`

**PDF won't open:**
- Invoice is saved as HTML file in `C:\Users\<YourName>\InvoiceApp\`
- Open the `.html` file in any browser and use Ctrl+P to print to PDF

**Logo not showing:**
- Go to Settings → Upload a PNG or JPG file
- Restart the app after uploading

---

## Support
This application runs fully offline.
Invoice data is never sent anywhere.
