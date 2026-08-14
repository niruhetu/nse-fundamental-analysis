import os
import json
import subprocess
import sys
import time

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# SETTINGS
# ============================================================

SPREADSHEET_ID = "1Z4dAZIKKHKm9bg8i8-OI6Cka_vz3YSGFGp6PykxpnHw"

FUNDAMENTAL_SHEET = "Fundamental Analysis"
TOP250_SHEET = "Top 250 Stocks"

# FIRST TEST = 3 STOCKS
TEST_STOCK_COUNT = 3

WORKER_FILE = "fundamental_worker.py"


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

    return spreadsheet


# ============================================================
# READ TOP 250
# ============================================================

def get_top250_stocks(top250_sheet):

    print("Waiting for Top 250 list...")

    # Google Sheets formulas may need time to recalculate.
    for attempt in range(1, 7):

        time.sleep(10)

        data = top250_sheet.get(
            "A2:B251",
            value_render_option="UNFORMATTED_VALUE"
        )

        stocks = []

        for row in data:

            if len(row) < 2:
                continue

            stock_name = str(row[0]).strip()
            nse_code = str(row[1]).strip()

            if stock_name and nse_code:
                stocks.append(
                    [stock_name, nse_code]
                )

        print(
            "Attempt",
            attempt,
            "- stocks found:",
            len(stocks)
        )

        if len(stocks) >= TEST_STOCK_COUNT:
            return stocks

    raise ValueError(
        "Top 250 list did not return at least "
        f"{TEST_STOCK_COUNT} stocks."
    )


# ============================================================
# RUN ORIGINAL WORKING PROGRAM
# ============================================================

def run_worker():

    print("------------------------------------------")
    print("Running fundamental_worker.py")
    print("------------------------------------------")

    subprocess.run(
        [sys.executable, WORKER_FILE],
        check=True
    )


# ============================================================
# MAIN
# ============================================================

def main():

    spreadsheet = connect_google_sheet()

    fundamental_sheet = spreadsheet.worksheet(
        FUNDAMENTAL_SHEET
    )

    top250_sheet = spreadsheet.worksheet(
        TOP250_SHEET
    )

    # --------------------------------------------------------
    # GET STOCKS
    # --------------------------------------------------------

    stocks = get_top250_stocks(
        top250_sheet
    )

    stocks = stocks[:TEST_STOCK_COUNT]

    print("==========================================")
    print("3-STOCK FUNDAMENTAL TEST")
    print("Stocks found:", len(stocks))
    print("==========================================")

    # --------------------------------------------------------
    # CLEAR OLD TEST RESULTS
    # --------------------------------------------------------

    fundamental_sheet.batch_clear([
        "A2:AH251"
    ])

    # --------------------------------------------------------
    # PROCESS STOCKS
    # --------------------------------------------------------

    for output_row, stock in enumerate(
        stocks,
        start=2
    ):

        stock_name = stock[0]
        nse_code = stock[1]

        print("==========================================")
        print(
            "Processing stock",
            output_row - 1,
            "of",
            len(stocks)
        )
        print("Stock:", stock_name)
        print("NSE:", nse_code)
        print("==========================================")

        # Put current stock into worker input row.
        fundamental_sheet.update(
            "A2:B2",
            [[stock_name, nse_code]],
            value_input_option="USER_ENTERED"
        )

        # Run original proven worker.
        run_worker()

        # Give Sheets a moment to finish writes.
        time.sleep(3)

        # Read completed analysis from row 2.
        completed = fundamental_sheet.get(
            "A2:AH2",
            value_render_option="UNFORMATTED_VALUE"
        )

        if not completed:
            raise ValueError(
                "No completed analysis returned for "
                + stock_name
            )

        completed_row = completed[0]

        # Save completed result permanently.
        fundamental_sheet.update(
            f"A{output_row}:AH{output_row}",
            [completed_row],
            value_input_option="USER_ENTERED"
        )

        print(
            "Saved:",
            stock_name,
            "to row",
            output_row
        )

    # --------------------------------------------------------
    # REMOVE WORKER SUCCESS MESSAGE
    # --------------------------------------------------------

    fundamental_sheet.batch_clear([
        "A5:AH251"
    ])

    print("==========================================")
    print("3-STOCK TEST COMPLETED SUCCESSFULLY")
    print("==========================================")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
