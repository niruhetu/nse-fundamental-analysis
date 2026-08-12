import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheet ID
SPREADSHEET_ID = "1Z4dAZIKKHKm9bg8i8-OI6Cka_vz3YSGFGp6PykxpnHw"

# Google credentials
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

# Google API access
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

credentials = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_dict,
    scope
)

client = gspread.authorize(credentials)

# Open spreadsheet
spreadsheet = client.open_by_key(SPREADSHEET_ID)

# Open Fundamental Analysis sheet
worksheet = spreadsheet.worksheet("Fundamental Analysis")

# Test connection
worksheet.update("A3", [["GitHub connection successful"]])

print("SUCCESS: Connected to Google Sheet.")
print("SUCCESS: Fundamental Analysis sheet updated.")
