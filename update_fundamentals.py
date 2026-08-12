import os
import json
from datetime import datetime

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
    raise SystemExit(1)

try:
    creds_dict = json.loads(creds_json)
except Exception as e:
    print("ERROR: Cannot read GCP_CREDENTIALS")
    print(e)
    raise SystemExit(1)

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

print("Google Sheet connected:", spreadsheet.title)


# ============================================================
# FIND WORKSHEETS SAFELY
# ============================================================

worksheets = spreadsheet.worksheets()

fundamental_sheet = None
quarterly_sheet = None

for ws in worksheets:
    print("Found worksheet:", repr(ws.title), "ID:", ws.id)

    clean_name = ws.title.strip().lower()

    if clean_name == "fundamental analysis":
        fundamental_sheet = ws

    if clean_name == "quarterly results":
        quarterly_sheet = ws

if fundamental_sheet is None:
    print("ERROR: Fundamental Analysis worksheet not found!")
    raise SystemExit(1)

if quarterly_sheet is None:
    print("ERROR: Quarterly Results worksheet not found!")
    raise SystemExit(1)

print("Using Fundamental Analysis:", fundamental_sheet.title)
print("Using Quarterly Results:", quarterly_sheet.title)


# ============================================================
# READ STOCK FROM FUNDAMENTAL ANALYSIS
# ============================================================

stock_name = fundamental_sheet.acell("A2").value
nse_code = fundamental_sheet.acell("B2").value

if not stock_name:
    print("ERROR: A2 is empty.")
    raise SystemExit(1)

if not nse_code:
    print("ERROR: B2 is empty.")
    raise SystemExit(1)

symbol = nse_code.upper().replace("NSE:", "").strip()

print("Stock Name:", stock_name)
print("NSE Symbol:", symbol)


# ============================================================
# DIRECT SHEET WRITE TEST
# ============================================================

fundamental_sheet.update_cell(
    3,
    1,
    "GitHub update: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)

print("DIRECT WRITE TEST SUCCESSFUL")


# ============================================================
# FETCH NSE FINANCIAL FILINGS
# ============================================================

try:
    nse_client = NSEClient()

    filings = nse_client.fetch_financials(
        symbol,
        stock_name,
        max_filings=4
    )

except Exception as e:
    print("ERROR: NSE financial fetch failed.")
    print(e)
    raise SystemExit(1)

if not filings:
    print("ERROR: No NSE filings found.")
    raise SystemExit(1)

print("NSE filings found:", len(filings))


# ============================================================
# SELECT LATEST FILING
# Prefer consolidated when available
# ============================================================

consolidated_filings = [
    f for f in filings
    if getattr(f, "is_consolidated", False)
]

if consolidated_filings:
    usable_filings = consolidated_filings
else:
    usable_filings = filings


def filing_date(filing):
    value = getattr(filing, "period_end", None)

    if value is None:
        return ""

    return str(value)


usable_filings = sorted(
    usable_filings,
    key=filing_date,
    reverse=True
)

selected = usable_filings[0]

period_end = getattr(selected, "period_end", None)

revenue = getattr(selected, "q_revenue", None)
profit = getattr(selected, "q_pat", None)
eps = getattr(selected, "q_diluted_eps", None)
ebitda = getattr(selected, "q_ebitda", None)

print("Selected period:", period_end)
print("Revenue:", revenue)
print("Profit:", profit)
print("EPS:", eps)
print("EBITDA:", ebitda)


# ============================================================
# OPERATING MARGIN
# ============================================================

operating_margin = None

if revenue not in (None, 0) and ebitda is not None:
    operating_margin = (ebitda / revenue) * 100


# ============================================================
# UPDATE QUARTERLY RESULTS
# WITHOUT DUPLICATING SAME STOCK + PERIOD
# ============================================================

all_rows = quarterly_sheet.get_all_values()

matching_rows = []

for row_number, row in enumerate(all_rows[1:], start=2):

    if len(row) < 3:
        continue

    row_symbol = row[0].strip().upper()
    row_period = row[2].strip()

    if (
        row_symbol == symbol
        and row_period == str(period_end)
    ):
        matching_rows.append(row_number)


quarterly_row = [
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


if matching_rows:

    # Update the first matching row
    target_row = matching_rows[0]

    quarterly_sheet.update(
        f"A{target_row}:P{target_row}",
        [quarterly_row]
    )

    print(
        "Updated existing Quarterly Results row:",
        target_row
    )

    # Delete duplicate matching rows
    for duplicate_row in reversed(matching_rows[1:]):
        quarterly_sheet.delete_rows(duplicate_row)
        print(
            "Deleted duplicate Quarterly Results row:",
            duplicate_row
        )

else:

    next_row = len(quarterly_sheet.get_all_values()) + 1

    quarterly_sheet.update(
        f"A{next_row}:P{next_row}",
        [quarterly_row]
    )

    print(
        "Added new Quarterly Results row:",
        next_row
    )


# ============================================================
# UPDATE FUNDAMENTAL ANALYSIS
# ============================================================

fundamental_sheet.update_cell(
    2,
    5,
    "Latest NSE Result"
)

fundamental_sheet.update_cell(
    2,
    6,
    str(period_end) if period_end else ""
)

fundamental_sheet.update_cell(
    2,
    13,
    operating_margin if operating_margin is not None else ""
)

fundamental_sheet.update_cell(
    2,
    17,
    eps if eps is not None else ""
)

fundamental_sheet.update_cell(
    2,
    25,
    revenue if revenue is not None else ""
)

fundamental_sheet.update_cell(
    2,
    26,
    profit if profit is not None else ""
)


# ============================================================
# FINAL STATUS
# ============================================================

fundamental_sheet.update_cell(
    3,
    1,
    "Fundamental Analysis updated successfully"
)

print("==========================================")
print("SUCCESS")
print("Fundamental Analysis updated")
print("Quarterly Results updated")
print("Duplicate results handled")
print("==========================================")
