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

# TEST WITH 3 STOCKS FIRST
TEST_STOCK_COUNT = 250

# Retry a stock if the worker fails
MAX_RETRIES = 3

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

    print("==========================================")
    print("Reading Top 250 Stocks")
    print("==========================================")

    for attempt in range(1, 7):

        time.sleep(5)

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
        "Top 250 Stocks did not provide enough stocks."
    )


# ============================================================
# RUN FUNDAMENTAL WORKER WITH RETRIES
# ============================================================

def run_worker(stock_name):

    for attempt in range(1, MAX_RETRIES + 1):

        print("------------------------------------------")
        print(
            "Running fundamental_worker.py",
            "Attempt",
            attempt,
            "of",
            MAX_RETRIES
        )
        print("Stock:", stock_name)
        print("------------------------------------------")

        result = subprocess.run(
            [sys.executable, WORKER_FILE],
            capture_output=True,
            text=True
        )

        # Always show worker output in GitHub Actions.
        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        if result.returncode == 0:

            print(
                "Worker SUCCESS:",
                stock_name
            )

            return True

        print(
            "Worker FAILED:",
            stock_name,
            "Return code:",
            result.returncode
        )

        if attempt < MAX_RETRIES:

            print(
                "Waiting 10 seconds before retry..."
            )

            time.sleep(10)

    return False


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
    print("==========================================")

    for number, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            number,
            ":",
            stock[0],
            stock[1]
        )

    print("==========================================")

    # --------------------------------------------------------
    # CLEAR OLD RESULTS
    # --------------------------------------------------------

    fundamental_sheet.batch_clear([
        "A2:AH251"
    ])

    # --------------------------------------------------------
    # STORE COMPLETED RESULTS IN MEMORY
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
            "PROCESSING STOCK",
            number,
            "OF",
            len(stocks)
        )
        print("Stock:", stock_name)
        print("NSE:", nse_code)
        print("==========================================")

        # Put stock into the worker's normal input cells.
        fundamental_sheet.update(
            range_name="A2:B2",
            values=[[stock_name, nse_code]],
            value_input_option="USER_ENTERED"
        )

        time.sleep(3)

        # Run worker with automatic retry.
        success = run_worker(stock_name)

        if not success:

            print("==========================================")
            print("WARNING - STOCK FAILED")
            print("Stock:", stock_name)
            print("NSE:", nse_code)
            print("Skipping this stock after retries.")
            print("==========================================")

            continue

        time.sleep(3)

        # Read the completed result from row 2.
        result = fundamental_sheet.get(
            "A2:AH2",
            value_render_option="UNFORMATTED_VALUE"
        )

        if not result:

            print(
                "No result returned for:",
                stock_name
            )

            continue

        completed_row = result[0]

        # Save result in Python memory.
        completed_results.append(
            completed_row
        )

        print(
            "Stored result in memory:",
            stock_name
        )

    # --------------------------------------------------------
    # WRITE ALL SUCCESSFUL RESULTS
    # --------------------------------------------------------

    print("==========================================")
    print(
        "Writing",
        len(completed_results),
        "successful results"
    )
    print("==========================================")

    if completed_results:

        end_row = 1 + len(completed_results)

        fundamental_sheet.update(
            range_name=f"A2:AH{end_row}",
            values=completed_results,
            value_input_option="USER_ENTERED"
        )

    # --------------------------------------------------------
    # CLEAR EVERYTHING AFTER THE RESULTS
    # --------------------------------------------------------

    final_end_row = 1 + len(completed_results)

    if final_end_row < 251:

        fundamental_sheet.batch_clear([
            f"A{final_end_row + 1}:AH251"
        ])

    print("==========================================")
    print("3-STOCK TEST FINISHED")
    print(
        "Successful stocks:",
        len(completed_results),
        "of",
        len(stocks)
    )
    print("==========================================")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
