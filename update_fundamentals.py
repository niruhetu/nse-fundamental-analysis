import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from nse_xbrl import NSEClient

# ============================================================
# SETTINGS
# ============================================================

SPREADSHEET_ID = "1Z4dAZIKKHKm9bg8i8-OI6Cka_vz3YSGFGp6PykxpnHw"

# ============================================================
# GOOGLE SHEET CONNECTION
# ============================================================

creds_json = os.environ.get("GCP_CREDENTIALS")

if not creds_json:
    print("ERROR: GCP_CREDENTIALS secret is missing!")
    exit(1)

try:
    creds_dict = json.loads(creds_json)
except Exception as e:
    print("ERROR: Could not read GCP_CREDENTIALS.")
    print(e)
    exit(1)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

credentials = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_dict,
    scope
)

client = gspread.authorize(credentials)

spreadsheet = client.open_by_key(SPREADSHEET_ID)

fundamental_sheet = spreadsheet.worksheet("Fundamental Analysis")
quarterly_sheet = spreadsheet.worksheet("Quarterly Results")

# ============================================================
# READ STOCK FROM GOOGLE SHEET
# ============================================================

stock_name = fundamental_sheet.acell("A2").value
nse_code = fundamental_sheet.acell("B2").value

if not stock_name:
    print("ERROR: Stock name is missing in A2.")
    exit(1)

if not nse_code:
    print("ERROR: NSE code is missing in B2.")
    exit(1)

symbol = nse_code.upper().replace("NSE:", "").strip()

print("Stock:", stock_name)
print("NSE Symbol:", symbol)

# ============================================================
# FETCH NSE INTEGRATED FINANCIAL FILINGS
# ============================================================

try:
    nse_client = NSEClient()

    filings = nse_client.fetch_financials(
        symbol,
        stock_name,
        max_filings=4
    )

except Exception as e:
    print("ERROR: Could not fetch NSE financial filings.")
    print(e)
    exit(1)

if not filings:
    print("ERROR: No financial filings found.")
    exit(1)

print("Number of filings found:", len(filings))

# ============================================================
# SELECT LATEST CONSOLIDATED FILING
# ============================================================

selected = None

for filing in filings:
    if getattr(filing, "is_consolidated", False):
        selected = filing
        break

if selected is None:
    selected = filings[0]

# ============================================================
# LATEST RESULT VALUES
# ============================================================

period_end = getattr(selected, "period_end", None)

revenue = getattr(selected, "q_revenue", None)
profit = getattr(selected, "q_pat", None)
eps = getattr(selected, "q_diluted_eps", None)

ebitda = getattr(selected, "q_ebitda", None)
ebit = getattr(selected, "q_ebit", None)

print("Latest quarter:", period_end)
print("Revenue:", revenue)
print("Profit:", profit)
print("EPS:", eps)
print("EBITDA:", ebitda)

# ============================================================
# CALCULATE OPERATING MARGIN
# ============================================================

operating_margin = None

if revenue not in (None, 0) and ebitda is not None:
    operating_margin = (ebitda / revenue) * 100

# ============================================================
# WRITE LATEST RESULT TO QUARTERLY RESULTS
# ============================================================

headers = quarterly_sheet.row_values(1)

# Find next empty row
all_values = quarterly_sheet.get_all_values()
next_row = len(all_values) + 1

row_data = [
    symbol,
    stock_name,
    str(period_end) if period_end else "",
    "",
    revenue if revenue is not None else "",
    "",
    profit if profit is not None else "",
    "",
    eps if eps is not None else "",
    "",
    ebitda if ebitda is not None else "",
    operating_margin if operating_margin is not None else "",
    "",
    "",
    "",
    "NSE Integrated Filing"
]

quarterly_sheet.update(
    f"A{next_row}:P{next_row}",
    [row_data]
)

# ============================================================
# UPDATE FUNDAMENTAL ANALYSIS SHEET
# ============================================================

fundamental_sheet.update("E2", [[
    "Latest NSE result"
]])

fundamental_sheet.update("F2", [[
    str(period_end) if period_end else ""
]])

# Revenue Growth
fundamental_sheet.update("G2", [[
    ""
]])

# Profit Growth
fundamental_sheet.update("H2", [[
    ""
]])

# EPS Growth
fundamental_sheet.update("I2", [[
    ""
]])

# EPS
fundamental_sheet.update("Q2", [[
    eps if eps is not None else ""
]])

# Quarterly Sales
fundamental_sheet.update("Y2", [[
    revenue if revenue is not None else ""
]])

# Quarterly Profit
fundamental_sheet.update("Z2", [[
    profit if profit is not None else ""
]])

# Operating Margin
fundamental_sheet.update("M2", [[
    operating_margin if operating_margin is not None else ""
]])

print("SUCCESS: Latest NSE result written to Google Sheet.")
print("SUCCESS: Quarterly Results updated.")
