import os
import json
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
# ============================================================
# SETTINGS
# ============================================================

SPREADSHEET_ID = "1Z4dAZIKKHKm9bg8i8-OI6Cka_vz3YSGFGp6PykxpnHw"
SHEET_NAME = "Top 250 Stocks"
# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

def connect_google_sheet():
  # ============================================================
# TEST CONNECTION
# ============================================================

def main():
    worksheet = connect_google_sheet()
    print("Connected to:", worksheet.title)


if __name__ == "__main__":
    main()
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
