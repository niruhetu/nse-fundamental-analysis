import os
import json
import csv
import io
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# SETTINGS
# ============================================================

SPREADSHEET_ID = "1Z4dAZIKKHKm9bg8i8-OI6Cka_vz3YSGFGp6PykxpnHw"
SHEET_NAME = "Top 250 Stocks"

NIFTY500_URL = (
    "https://www.niftyindices.com/IndexConstituent/"
    "ind_nifty500list.csv"
)


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

def connect_google_sheet():
    creds_json = os.environ.get("GCP_CREDENTIALS")

    if not creds_json:
        raise ValueError("GCP_CREDENTIALS secret is missing")

    creds_dict = json.loads(creds_json)

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
    worksheet = spreadsheet.worksheet(SHEET_NAME)

    return worksheet


# ============================================================
# GET NIFTY 500 STOCK LIST
# ============================================================

def get_nifty500_stocks():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
        )
    }

    response = requests.get(
        NIFTY500_URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    text = response.content.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(text))

    stocks = []

    for row in reader:

        symbol = (
            row.get("Symbol")
            or row.get("SYMBOL")
            or ""
        ).strip()

        company = (
            row.get("Company Name")
            or row.get("CompanyName")
            or row.get("COMPANY NAME")
            or ""
        ).strip()

        if symbol:
            stocks.append([
                company,
                "NSE:" + symbol
            ])

    if not stocks:
        raise ValueError(
            "Nifty 500 stock list could not be read."
        )

    return stocks


# ============================================================
# UPDATE TOP 250 SHEET
# ============================================================

def update_sheet():

    worksheet = connect_google_sheet()

    stocks = get_nifty500_stocks()

    # --------------------------------------------------------
    # CLEAR OLD DATA
    # --------------------------------------------------------

    worksheet.batch_clear([
        "A2:C1000",
        "E2:G1000"
    ])

    # --------------------------------------------------------
    # HEADERS
    # --------------------------------------------------------

    worksheet.update(
        "A1:C1",
        [["Stock Name", "NSE Code", "Market Cap"]]
    )

    worksheet.update(
        "E1:G1",
        [["Stock Name", "NSE Code", "Market Cap"]]
    )

    # --------------------------------------------------------
    # WRITE NIFTY 500 SOURCE
    # --------------------------------------------------------

    source_rows = []

    for company, nse_code in stocks:
        source_rows.append([
            company,
            nse_code,
            ""
        ])

    last_source_row = len(source_rows) + 1

    worksheet.update(
        f"E2:G{last_source_row}",
        source_rows,
        value_input_option="USER_ENTERED"
    )

    # --------------------------------------------------------
    # GOOGLE FINANCE MARKET CAP
    # --------------------------------------------------------

    formulas = []

    for row in range(2, last_source_row + 1):
        formulas.append([
            f'=IFERROR(GOOGLEFINANCE(F{row},"marketcap"),"")'
        ])

    worksheet.update(
        f"G2:G{last_source_row}",
        formulas,
        value_input_option="USER_ENTERED"
    )

    # --------------------------------------------------------
    # TOP 250 FORMULA
    # --------------------------------------------------------
    #
    # Sort by Market Cap, highest to lowest,
    # and return only the first 250 stocks.
    #

    top250_formula = (
        f'=IFERROR('
        f'SORTN('
        f'FILTER(E2:G{last_source_row},'
        f'G2:G{last_source_row}<>""),'
        f'250,'
        f'0,'
        f'3,'
        f'FALSE'
        f'),"")'
    )

    worksheet.update(
        "A2",
        [[top250_formula]],
        value_input_option="USER_ENTERED"
    )

    print("==========================================")
    print("TOP 250 STOCKS UPDATED")
    print("Nifty 500 source:", len(stocks))
    print("Top 250 sorted by Market Cap")
    print("Highest to Lowest")
    print("==========================================")


# ============================================================
# START
# ============================================================

def main():
    update_sheet()


if __name__ == "__main__":
    main()
