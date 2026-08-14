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

# FIRST TEST
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

    return client.open_by_key(SPREADSHEET_ID)


# ============================================================
# GET TOP 250 STOCKS
# ============================================================

def get_top250_stocks(top250_sheet):

    print("Waiting for Top 250 list...")

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
        "Top 250 list did not return enough stocks."
    )


# ============================================================
# RUN ORIGINAL WORKER
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
    print("Stocks:", len(stocks))
    print("==========================================")

    # --------------------------------------------------------
    # CLEAR OLD TEST AREA
    # --------------------------------------------------------

    fundamental_sheet.batch_clear([
        "A2:AH251"
    ])

    # --------------------------------------------------------
    # MEMORY STORAGE
    #
    # IMPORTANT:
    # We DO NOT write permanent rows 2,3,4
    # until ALL workers have finished.
    # --------------------------------------------------------

    completed_results = []

    # --------------------------------------------------------
    # PROCESS EACH STOCK
    # --------------------------------------------------------

    for number, stock in enumerate(
        stocks,
        start=1
    ):

        stock_name = stock[0]
        nse_code = stock[1]

        print("==========================================")
        print(
            "Processing",
            number,
            "of",
            len(stocks)
        )
        print("Stock:", stock_name)
        print("NSE:", nse_code)
        print("==========================================")

        # Put stock into worker input row.
        fundamental_sheet.update(
            "A2:B2",
            [[stock_name, nse_code]],
            value_input_option="USER_ENTERED"
        )

        # Run original working program.
        run_worker()

        time.sleep(3)

        # Read ONLY the completed worker result.
        result = fundamental_sheet.get(
            "A2:AH2",
            value_render_option="UNFORMATTED_VALUE"
        )

        if not result:
            raise ValueError(
                "No result returned for "
                + stock_name
            )

        completed_row = result[0]

        # Store in Python memory.
        completed_results.append(
            completed_row
        )

        print(
            "Stored result in memory:",
            stock_name
        )

    # --------------------------------------------------------
    # NOW WRITE ALL RESULTS AT ONCE
    # --------------------------------------------------------

    print("==========================================")
    print("Writing final results to rows 2 onward")
    print("==========================================")

    end_row = 1 + len(completed_results)

    fundamental_sheet.update(
        f"A2:AH{end_row}",
        completed_results,
        value_input_option="USER_ENTERED"
    )

    # Remove anything left below the test results.
    if end_row < 251:

        fundamental_sheet.batch_clear([
            f"A{end_row + 1}:AH251"
        ])

    print("==========================================")
    print("3-STOCK TEST COMPLETED")
    print("==========================================")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
