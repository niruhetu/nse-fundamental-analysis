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

# PROCESS ALL 250 STOCKS
TEST_STOCK_COUNT = 250

# Worker retry
MAX_RETRIES = 3

# Google Sheets quota protection
WRITE_RETRY_COUNT = 6
WAIT_BETWEEN_STOCKS = 15

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
# SAFE GOOGLE SHEETS UPDATE
# ============================================================

def safe_update(
    worksheet,
    range_name,
    values,
    value_input_option="USER_ENTERED"
):

    for attempt in range(1, WRITE_RETRY_COUNT + 1):

        try:

            worksheet.update(
                range_name=range_name,
                values=values,
                value_input_option=value_input_option
            )

            return True

        except gspread.exceptions.APIError as e:

            error_text = str(e)

            if "429" not in error_text:
                raise

            wait_time = 20 * attempt

            print("==========================================")
            print("GOOGLE SHEETS WRITE QUOTA REACHED")
            print("Attempt:", attempt, "of", WRITE_RETRY_COUNT)
            print("Waiting:", wait_time, "seconds")
            print("==========================================")

            time.sleep(wait_time)

    raise RuntimeError(
        "Google Sheets write quota remained exceeded "
        "after multiple retries."
    )


# ============================================================
# SAFE CLEAR
# ============================================================

def safe_clear(worksheet, ranges):

    for attempt in range(1, WRITE_RETRY_COUNT + 1):

        try:

            worksheet.batch_clear(ranges)

            return True

        except gspread.exceptions.APIError as e:

            error_text = str(e)

            if "429" not in error_text:
                raise

            wait_time = 20 * attempt

            print(
                "Google Sheets clear quota reached."
            )

            print(
                "Waiting",
                wait_time,
                "seconds..."
            )

            time.sleep(wait_time)

    raise RuntimeError(
        "Google Sheets clear quota remained exceeded."
    )


# ============================================================
# GET TOP 250
# ============================================================

def get_top250_stocks(top250_sheet):

    print("==========================================")
    print("READING TOP 250 STOCKS")
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
            return stocks[:TEST_STOCK_COUNT]

    raise ValueError(
        "Top 250 Stocks did not provide 250 stocks."
    )


# ============================================================
# RUN FUNDAMENTAL WORKER
# ============================================================

def run_worker(stock_name):

    for attempt in range(1, MAX_RETRIES + 1):

        print("------------------------------------------")
        print(
            "Running fundamental_worker.py"
        )
        print(
            "Stock:",
            stock_name
        )
        print(
            "Attempt:",
            attempt,
            "of",
            MAX_RETRIES
        )
        print("------------------------------------------")

        result = subprocess.run(
            [sys.executable, WORKER_FILE],
            capture_output=True,
            text=True
        )

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
            stock_name
        )

        if attempt < MAX_RETRIES:

            print(
                "Waiting 30 seconds before retry..."
            )

            time.sleep(30)

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
    # GET TOP 250
    # --------------------------------------------------------

    stocks = get_top250_stocks(
        top250_sheet
    )

    print("==========================================")
    print(
        "TOTAL STOCKS TO PROCESS:",
        len(stocks)
    )
    print("==========================================")

    # --------------------------------------------------------
    # CLEAR OLD RESULTS
    # --------------------------------------------------------

    safe_clear(
        fundamental_sheet,
        ["A2:AH251"]
    )

    completed_results = []

    # --------------------------------------------------------
    # PROCESS STOCKS
    # --------------------------------------------------------

    for number, stock in enumerate(
        stocks,
        start=1
    ):

        stock_name = stock[0]
        nse_code = stock[1]

        print("")
        print("==========================================")
        print(
            "PROCESSING STOCK",
            number,
            "OF",
            len(stocks)
        )
        print(
            "Stock:",
            stock_name
        )
        print(
            "NSE:",
            nse_code
        )
        print("==========================================")

        # ----------------------------------------------------
        # PUT STOCK INTO WORKER INPUT
        # ----------------------------------------------------

        safe_update(
            fundamental_sheet,
            "A2:B2",
            [[stock_name, nse_code]]
        )

        time.sleep(3)

        # ----------------------------------------------------
        # RUN WORKER
        # ----------------------------------------------------

        success = run_worker(
            stock_name
        )

        if not success:

            print("==========================================")
            print(
                "SKIPPING FAILED STOCK:",
                stock_name
            )
            print("==========================================")

            continue

        time.sleep(3)

        # ----------------------------------------------------
        # READ RESULT
        # ----------------------------------------------------

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

        completed_results.append(
            completed_row
        )

        print(
            "Stored result:",
            stock_name
        )

        # ----------------------------------------------------
        # IMPORTANT:
        # SLOW DOWN BEFORE NEXT STOCK
        # ----------------------------------------------------

        if number < len(stocks):

            print(
                "Waiting",
                WAIT_BETWEEN_STOCKS,
                "seconds before next stock..."
            )

            time.sleep(
                WAIT_BETWEEN_STOCKS
            )

    # ========================================================
    # WRITE ALL RESULTS
    # ========================================================

    print("==========================================")
    print(
        "SUCCESSFUL RESULTS:",
        len(completed_results),
        "OF",
        len(stocks)
    )
    print("==========================================")

    if completed_results:

        end_row = 1 + len(
            completed_results
        )

        safe_update(
            fundamental_sheet,
            f"A2:AH{end_row}",
            completed_results
        )

    # --------------------------------------------------------
    # CLEAR REMAINING OLD AREA
    # --------------------------------------------------------

    final_end_row = 1 + len(
        completed_results
    )

    if final_end_row < 251:

        safe_clear(
            fundamental_sheet,
            [
                f"A{final_end_row + 1}:AH251"
            ]
        )

    print("==========================================")
    print("FUNDAMENTAL ANALYSIS FINISHED")
    print(
        "Successful:",
        len(completed_results)
    )
    print(
        "Requested:",
        len(stocks)
    )
    print("==========================================")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
