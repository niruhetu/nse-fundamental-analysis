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
    failed_stocks = []

    # Keep every Top-250 stock even when NSE fundamental data fails.
    def make_unavailable_row(stock_name, nse_code):
        return [
            stock_name, nse_code, "", "", "DATA NOT AVAILABLE",
            "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
            "DATA NOT AVAILABLE", "", "", "", "", ""
        ]

    # --------------------------------------------------------
    # PROCESS ALL 250 STOCKS
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
            print("FUNDAMENTAL DATA FAILED:", stock_name)
            print("Keeping stock with DATA NOT AVAILABLE.")
            print("==========================================")

            completed_results.append(
                make_unavailable_row(stock_name, nse_code)
            )
            failed_stocks.append(stock_name)
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

            print("No result returned for:", stock_name)

            completed_results.append(
                make_unavailable_row(stock_name, nse_code)
            )
            failed_stocks.append(stock_name)
            continue

        completed_row = result[0]

        # Always keep exactly 34 columns (A:AH).
        if len(completed_row) < 34:
            completed_row += [""] * (34 - len(completed_row))
        elif len(completed_row) > 34:
            completed_row = completed_row[:34]

        completed_results.append(completed_row)

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

    # ========================================================
    # RESTORE GOOGLE SHEETS FORMULAS
    # ========================================================
    # These formulas are recreated after every GitHub run because
    # A2:AH251 is cleared before processing.

    formula_end_row = 1 + len(stocks)

    def formula_column(builder):
        return [[builder(r)] for r in range(2, formula_end_row + 1)]

    # O = P/E
    pe = formula_column(
        lambda r: f'=IF(A{r}="","",IFERROR(GOOGLEFINANCE(B{r},"price")/Q{r},"DATA NOT AVAILABLE"))'
    )

    # P = P/B
    pb = formula_column(
        lambda r: f'=IF(A{r}="","",IFERROR(GOOGLEFINANCE(B{r},"price")/R{r},"DATA NOT AVAILABLE"))'
    )

    # AA = Quarterly Sales Growth
    aa = formula_column(
        lambda r: f'=IF(A{r}="","",IFERROR(INDEX(\'Quarterly Results\'!F:F,MATCH(SUBSTITUTE(B{r},"NSE:",""),\'Quarterly Results\'!A:A,0)),"DATA NOT AVAILABLE"))'
    )

    # AB = Quarterly Profit Growth
    ab = formula_column(
        lambda r: f'=IF(A{r}="","",IFERROR(INDEX(\'Quarterly Results\'!H:H,MATCH(SUBSTITUTE(B{r},"NSE:",""),\'Quarterly Results\'!A:A,0)),"DATA NOT AVAILABLE"))'
    )

    # AD = Business Quality
    ad = formula_column(
        lambda r: (
            f'=IF(A{r}="","",IF(COUNT(J{r}:N{r},X{r})=0,"DATA NOT AVAILABLE",'
            f'IF(ISNUMBER(J{r}),IF(J{r}>20,5,IF(J{r}>=15,4,IF(J{r}>=10,2,0))),0)+'
            f'IF(ISNUMBER(K{r}),IF(K{r}>20,5,IF(K{r}>=15,4,IF(K{r}>=10,2,0))),0)+'
            f'IF(ISNUMBER(L{r}),IF(L{r}<0.5,5,IF(L{r}<=1,4,IF(L{r}<=2,2,0))),0)+'
            f'IF(ISNUMBER(M{r}),IF(M{r}>20,5,IF(M{r}>=12,4,IF(M{r}>=5,2,0))),0)+'
            f'IF(ISNUMBER(N{r}),IF(N{r}>15,5,IF(N{r}>=10,4,IF(N{r}>=5,2,0))),0)+'
            f'IF(ISNUMBER(X{r}),IF(X{r}>5,5,IF(X{r}>=3,4,IF(X{r}>=2,2,0))),0)))'
        )
    )

    # AE = Result Momentum
    ae = formula_column(
        lambda r: (
            f'=IF(A{r}="","",IF(COUNT(I{r},AA{r}:AB{r})=0,"DATA NOT AVAILABLE",'
            f'IF(ISNUMBER(AA{r}),IF(AA{r}>20,5,IF(AA{r}>=10,4,IF(AA{r}>=0,2,0))),0)+'
            f'IF(ISNUMBER(AB{r}),IF(AB{r}>20,5,IF(AB{r}>=10,4,IF(AB{r}>=0,2,0))),0)+'
            f'IF(ISNUMBER(I{r}),IF(I{r}>20,5,IF(I{r}>=10,4,IF(I{r}>=0,2,0))),0)))'
        )
    )

    # AF = Valuation Score
    af = formula_column(
        lambda r: (
            f'=IF(A{r}="","",IF(COUNT(O{r}:P{r})=0,"DATA NOT AVAILABLE",'
            f'IF(ISNUMBER(O{r}),IF(O{r}<0,0,IF(O{r}<15,5,IF(O{r}<=25,4,IF(O{r}<=40,2,0)))),0)+'
            f'IF(ISNUMBER(P{r}),IF(P{r}<1,5,IF(P{r}<=2,4,IF(P{r}<=4,2,0))),0)))'
        )
    )

    # AG = Overall Fundamental Score
    ag = formula_column(
        lambda r: f'=IF(A{r}="","",IF(COUNT(AD{r}:AF{r})=0,"DATA NOT AVAILABLE",ROUND((AD{r}/30*40)+(AE{r}/15*35)+(AF{r}/10*25),1)))'
    )

    # AH = Final Indication
    ah = formula_column(
        lambda r: (
            f'=IF(A{r}="","",IF(NOT(ISNUMBER(AG{r})),"DATA NOT AVAILABLE",'
            f'IF(AG{r}>=75,"STRONG BUY",IF(AG{r}>=60,"BUY",IF(AG{r}>=45,"HOLD",IF(AG{r}>=30,"AVOID","STRONG AVOID")))))'
        )
    )

    safe_update(fundamental_sheet, f"O2:O{formula_end_row}", pe)
    safe_update(fundamental_sheet, f"P2:P{formula_end_row}", pb)
    safe_update(fundamental_sheet, f"AA2:AA{formula_end_row}", aa)
    safe_update(fundamental_sheet, f"AB2:AB{formula_end_row}", ab)
    safe_update(fundamental_sheet, f"AD2:AD{formula_end_row}", ad)
    safe_update(fundamental_sheet, f"AE2:AE{formula_end_row}", ae)
    safe_update(fundamental_sheet, f"AF2:AF{formula_end_row}", af)
    safe_update(fundamental_sheet, f"AG2:AG{formula_end_row}", ag)
    safe_update(fundamental_sheet, f"AH2:AH{formula_end_row}", ah)

    print("FORMULAS RESTORED: O, P, AA, AB, AD:AH")

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
        "Final rows:",
        len(completed_results)
    )
    print(
        "Requested:",
        len(stocks)
    )
    print(
        "Failed / DATA NOT AVAILABLE:",
        len(failed_stocks)
    )
    if failed_stocks:
        print("Stocks kept with DATA NOT AVAILABLE:")
        for failed_stock in failed_stocks:
            print("-", failed_stock)
    print("==========================================")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
