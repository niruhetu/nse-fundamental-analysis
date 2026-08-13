import os
import json
from datetime import datetime, date

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
# FIND WORKSHEETS
# ============================================================

fundamental_sheet = None
quarterly_sheet = None
balance_sheet = None

for ws in spreadsheet.worksheets():

    print("Found worksheet:", repr(ws.title))

    name = ws.title.strip().lower()

    if name == "fundamental analysis":
        fundamental_sheet = ws

    elif name == "quarterly results":
        quarterly_sheet = ws

    elif name == "balance sheet":
        balance_sheet = ws

if fundamental_sheet is None:
    print("ERROR: Fundamental Analysis worksheet not found!")
    raise SystemExit(1)

if quarterly_sheet is None:
    print("ERROR: Quarterly Results worksheet not found!")
    raise SystemExit(1)

if balance_sheet is None:
    print("ERROR: Balance Sheet worksheet not found!")
    raise SystemExit(1)


# ============================================================
# READ STOCK
# ============================================================

stock_name = fundamental_sheet.acell("A2").value
nse_code = fundamental_sheet.acell("B2").value

if not stock_name:
    print("ERROR: Stock name missing in A2")
    raise SystemExit(1)

if not nse_code:
    print("ERROR: NSE code missing in B2")
    raise SystemExit(1)

symbol = nse_code.upper().replace("NSE:", "").strip()

print("Stock:", stock_name)
print("Symbol:", symbol)


# ============================================================
# FETCH NSE FILINGS
# ============================================================

try:

    nse_client = NSEClient()

    filings = nse_client.fetch_financials(
        symbol,
        stock_name,
        max_filings=12
    )

except Exception as e:

    print("ERROR: NSE financial fetch failed")
    print(e)
    raise SystemExit(1)


if not filings:
    print("ERROR: No NSE filings found")
    raise SystemExit(1)

print("========== FILING LIST ==========")

for i, filing in enumerate(filings, start=1):
    print(
        i,
        "Period:",
        getattr(filing, "period_end", None),
        "Consolidated:",
        getattr(filing, "is_consolidated", None)
    )

print("=================================")


# ============================================================
# PREFER CONSOLIDATED FILINGS
# ============================================================

consolidated = [
    f for f in filings
    if getattr(f, "is_consolidated", False)
]

if consolidated:
    filings = consolidated


# ============================================================
# DATE HELPER
# ============================================================

def get_date(value):

    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d"
    ]

    for fmt in formats:

        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    return None


# ============================================================
# SORT FILINGS
# ============================================================

valid_filings = []

for filing in filings:

    filing_date = get_date(
        getattr(filing, "period_end", None)
    )

    if filing_date:
        valid_filings.append(
            (filing_date, filing)
        )


if not valid_filings:

    print("ERROR: Could not identify filing dates")
    raise SystemExit(1)


valid_filings.sort(
    key=lambda x: x[0],
    reverse=True
)


# ============================================================
# LATEST FILING
# ============================================================

latest_date, latest = valid_filings[0]
print("========== BALANCE SHEET RAW DATA ==========")

raw_facts = getattr(latest, "raw_facts", {})

for tag, contexts in raw_facts.items():
    tag_lower = tag.lower()

    if any(x in tag_lower for x in [
        "equity",
        "liabil",
        "borrow",
        "debt",
        "capital"
    ]):
        print(tag, "=", contexts)

print("============================================")

latest_revenue = getattr(
    latest,
    "q_revenue",
    None
)

latest_profit = getattr(
    latest,
    "q_pat",
    None
)

latest_eps = getattr(
    latest,
    "q_diluted_eps",
    None
)

latest_ebitda = getattr(
    latest,
    "q_ebitda",
    None
)


print("--------------------------------")
print("LATEST RESULT")
print("Date:", latest_date)
print("Revenue:", latest_revenue)
print("Profit:", latest_profit)
print("EPS:", latest_eps)
print("--------------------------------")


# ============================================================
# FIND SAME QUARTER LAST YEAR
# ============================================================

previous_year = None

for filing_date, filing in valid_filings[1:]:

    if (
        filing_date.year == latest_date.year - 1
        and filing_date.month == latest_date.month
    ):

        previous_year = filing

        print(
            "Previous-year quarter found:",
            filing_date
        )

        break


# ============================================================
# PREVIOUS YEAR VALUES
# ============================================================

previous_revenue = None
previous_profit = None
previous_eps = None

if previous_year:

    previous_revenue = getattr(
        previous_year,
        "q_revenue",
        None
    )

    previous_profit = getattr(
        previous_year,
        "q_pat",
        None
    )

    previous_eps = getattr(
        previous_year,
        "q_diluted_eps",
        None
    )

    print("Previous Revenue:", previous_revenue)
    print("Previous Profit:", previous_profit)
    print("Previous EPS:", previous_eps)

else:

    print("WARNING: Previous-year quarter not found")


# ============================================================
# GROWTH FUNCTION
# ============================================================

def calculate_growth(current, previous):

    if current is None or previous in (None, 0):
        return None

    return ((current - previous) / abs(previous)) * 100


revenue_growth = calculate_growth(
    latest_revenue,
    previous_revenue
)

profit_growth = calculate_growth(
    latest_profit,
    previous_profit
)

eps_growth = calculate_growth(
    latest_eps,
    previous_eps
)


print("--------------------------------")
print("GROWTH")
print("Revenue Growth:", revenue_growth)
print("Profit Growth:", profit_growth)
print("EPS Growth:", eps_growth)
print("--------------------------------")


# ============================================================
# OPERATING MARGIN
# ============================================================

operating_margin = None

if latest_revenue not in (None, 0) and latest_ebitda is not None:

    operating_margin = (
        latest_ebitda / latest_revenue
    ) * 100


# ============================================================
# RESULT SIGNAL
# ============================================================

signals = []

for value in [
    revenue_growth,
    profit_growth,
    eps_growth
]:

    if value is not None:

        if value > 0:
            signals.append(1)

        elif value < 0:
            signals.append(-1)

        else:
            signals.append(0)


if signals:

    signal_total = sum(signals)

    if signal_total >= 2:
        result_signal = "POSITIVE"

    elif signal_total <= -2:
        result_signal = "NEGATIVE"

    else:
        result_signal = "MIXED"

else:

    result_signal = "DATA NOT AVAILABLE"


# ============================================================
# QUARTERLY RESULTS ROW
# ============================================================

quarterly_row = [
    symbol,
    stock_name,
    str(latest_date),
    "",
    latest_revenue if latest_revenue is not None else "",
    revenue_growth if revenue_growth is not None else "",
    latest_profit if latest_profit is not None else "",
    profit_growth if profit_growth is not None else "",
    latest_eps if latest_eps is not None else "",
    eps_growth if eps_growth is not None else "",
    latest_ebitda if latest_ebitda is not None else "",
    operating_margin if operating_margin is not None else "",
    result_signal,
    "",
    "",
    "NSE Integrated Filing"
]


# ============================================================
# UPDATE EXISTING QUARTERLY ROW
# ============================================================

all_rows = quarterly_sheet.get_all_values()

matching_rows = []

for row_number, row in enumerate(
    all_rows[1:],
    start=2
):

    if len(row) < 3:
        continue

    row_symbol = row[0].strip().upper()
    row_date = row[2].strip()

    if (
        row_symbol == symbol
        and row_date == str(latest_date)
    ):

        matching_rows.append(row_number)


if matching_rows:

    target_row = matching_rows[0]

    quarterly_sheet.update(
        f"A{target_row}:P{target_row}",
        [quarterly_row]
    )

    print(
        "Updated Quarterly Results row:",
        target_row
    )

    # Remove duplicates
    for duplicate_row in reversed(
        matching_rows[1:]
    ):

        quarterly_sheet.delete_rows(
            duplicate_row
        )

        print(
            "Deleted duplicate row:",
            duplicate_row
        )

else:

    next_row = len(
        quarterly_sheet.get_all_values()
    ) + 1

    quarterly_sheet.update(
        f"A{next_row}:P{next_row}",
        [quarterly_row]
    )

    print(
        "Added Quarterly Results row:",
        next_row
    )


# ============================================================
# UPDATE FUNDAMENTAL ANALYSIS
# ============================================================

# ------------------------------------------------------------
# BASIC RESULT DATA
# ------------------------------------------------------------

fundamental_sheet.update_cell(
    2,
    5,
    "Latest NSE Result"
)

fundamental_sheet.update_cell(
    2,
    6,
    str(latest_date)
)

# Revenue Growth - G2
fundamental_sheet.update_cell(
    2,
    7,
    revenue_growth if revenue_growth is not None else ""
)

# Profit Growth - H2
fundamental_sheet.update_cell(
    2,
    8,
    profit_growth if profit_growth is not None else ""
)

# EPS Growth - I2
fundamental_sheet.update_cell(
    2,
    9,
    eps_growth if eps_growth is not None else ""
)

# ------------------------------------------------------------
# NET PROFIT MARGIN - N2
# ------------------------------------------------------------

net_profit_margin = None

if latest_revenue not in (None, 0) and latest_profit is not None:
    net_profit_margin = (
        latest_profit / latest_revenue
    ) * 100

fundamental_sheet.update_cell(
    2,
    14,
    net_profit_margin if net_profit_margin is not None else ""
)

# ------------------------------------------------------------
# ------------------------------------------------------------
# BUSINESS QUALITY DATA
# ------------------------------------------------------------

# Total Equity
total_equity = getattr(
    latest,
    "bs_equity",
    None
)

# Financial liabilities
noncurrent_financial_liabilities = getattr(
    latest,
    "bs_noncurrent_fin_liab",
    None
)

current_financial_liabilities = getattr(
    latest,
    "bs_current_fin_liab",
    None
)

# ------------------------------------------------------------
# ------------------------------------------------------------
# DEBT / EQUITY - L2
# ------------------------------------------------------------

debt_equity = None

raw_debt = raw_facts.get("DebtEquityRatio", {})

if isinstance(raw_debt, dict):
    debt_equity = raw_debt.get("OneD")

if debt_equity is not None:
    try:
        debt_equity = float(debt_equity)
    except (ValueError, TypeError):
        debt_equity = None

fundamental_sheet.update_cell(
    2,
    12,
    debt_equity if debt_equity is not None else ""
)

print("Debt/Equity from NSE:", debt_equity)
    debt_equity if debt_equity is not None else ""
)

# ------------------------------------------------------------
# BOOK VALUE - R2
# ------------------------------------------------------------

paid_up_equity = getattr(
    latest,
    "paid_up_equity",
    None
)

face_value = getattr(
    latest,
    "face_value",
    None
)

book_value = None

if (
    total_equity not in (None, 0)
    and paid_up_equity not in (None, 0)
    and face_value not in (None, 0)
):

    shares_outstanding = (
        paid_up_equity / face_value
    )

    if shares_outstanding:
        book_value = (
            total_equity / shares_outstanding
        )

fundamental_sheet.update_cell(
    2,
    18,
    book_value if book_value is not None else ""
)

# ------------------------------------------------------------
# CASH FLOW - V2
# ------------------------------------------------------------

net_change_cash = getattr(
    latest,
    "cf_net_change_in_cash",
    None
)

fundamental_sheet.update_cell(
    2,
    22,
    net_change_cash if net_change_cash is not None else ""
)

# ------------------------------------------------------------
# FREE CASH FLOW - W2
# ------------------------------------------------------------

# We do not calculate FCF until genuine operating
# cash-flow data is available.
fundamental_sheet.update_cell(
    2,
    23,
    ""
)

# ------------------------------------------------------------
# BALANCE SHEET TAB
# ------------------------------------------------------------

balance_sheet_row = [
    stock_name,
    "NSE:" + symbol,
    str(latest_date),
    latest_profit if latest_profit is not None else "",
    total_equity if total_equity is not None else "",
    (
        (
            noncurrent_financial_liabilities
            if noncurrent_financial_liabilities is not None
            else 0
        )
        +
        (
            current_financial_liabilities
            if current_financial_liabilities is not None
            else 0
        )
    )
    if (
        noncurrent_financial_liabilities is not None
        or current_financial_liabilities is not None
    )
    else "",
    getattr(latest, "q_ebit", None) or "",
    "",
    "",
    debt_equity if debt_equity is not None else ""
]

balance_sheet.append_row(
    balance_sheet_row,
    value_input_option="USER_ENTERED"
)

print("Balance Sheet updated")
fundamental_sheet.update_cell(
    2,
    17,
    latest_eps if latest_eps is not None else ""
)

# ------------------------------------------------------------
# QUARTERLY SALES - Y2
# ------------------------------------------------------------

fundamental_sheet.update_cell(
    2,
    25,
    latest_revenue if latest_revenue is not None else ""
)

# ------------------------------------------------------------
# QUARTERLY PROFIT - Z2
# ------------------------------------------------------------

fundamental_sheet.update_cell(
    2,
    26,
    latest_profit if latest_profit is not None else ""
)

# ------------------------------------------------------------
# ------------------------------------------------------------
# RESULT SIGNAL - AC2
# ------------------------------------------------------------

fundamental_sheet.update_cell(
    2,
    29,
    result_signal if result_signal else "DATA NOT AVAILABLE"
)
# ------------------------------------------------------------

fundamental_sheet.update_cell(
    2,
    29,
    result_signal
)

# ------------------------------------------------------------
# SUCCESS MESSAGE
# ------------------------------------------------------------

fundamental_sheet.update_cell(
    3,
    1,
    "Fundamental Analysis updated successfully"
)

print("==========================================")
print("SUCCESS")
print("Revenue Growth:", revenue_growth)
print("Profit Growth:", profit_growth)
print("EPS Growth:", eps_growth)
print("Net Profit Margin:", net_profit_margin)
print("Debt/Equity:", debt_equity)
print("Book Value:", book_value)
print("Net Change in Cash:", net_change_cash)
print("Result Signal:", result_signal)
print("==========================================")
