# Google Sheets Integration Setup Guide

This guide will help you set up and test Google Sheets integration for the Pure Bhakti Base book loading workflow.

## Prerequisites

You mentioned you already have:
- ✅ GCP project created
- ✅ OAuth configured for Google Sheets API
- ✅ Service account created

## Step-by-Step Setup

### 1. Download Service Account Credentials

1. Go to [GCP Console](https://console.cloud.google.com/)
2. Navigate to: **IAM & Admin** → **Service Accounts**
3. Click on your service account email
4. Go to the **Keys** tab
5. Click **Add Key** → **Create new key**
6. Select **JSON** format
7. Click **Create** - the file will download automatically (usually named something like `your-project-xxxxx.json`)

### 2. Save Credentials File

Move the downloaded JSON file to the credentials directory:

```bash
mv ~/Downloads/your-project-xxxxx.json /Users/kamaldivi/Development/Python/pure_bhakti_valut/credentials/google_service_account.json
```

Or manually:
1. Find the downloaded file in your Downloads folder
2. Rename it to `google_service_account.json`
3. Move it to: `/Users/kamaldivi/Development/Python/pure_bhakti_valut/credentials/`

### 3. Find Your Service Account Email

Open the JSON credentials file and look for the `client_email` field:

```bash
# Quick way to find the email:
cat /Users/kamaldivi/Development/Python/pure_bhakti_valut/credentials/google_service_account.json | grep client_email
```

The email will look like:
```
your-service-account@your-project.iam.gserviceaccount.com
```

**Copy this email - you'll need it for the next step!**

### 4. Create a Test Google Sheet

1. Go to [Google Sheets](https://sheets.google.com)
2. Click **+ Blank** to create a new spreadsheet
3. Name it: "Pure Bhakti Base - Test Sheet"
4. Click the **Share** button (top right)
5. Paste your **service account email** (from step 3)
6. Change permission to **Editor**
7. **Uncheck** "Notify people" (service accounts don't receive emails)
8. Click **Share**

### 5. Get the Sheet ID

The Sheet ID is in the URL of your Google Sheet:

```
https://docs.google.com/spreadsheets/d/1ABC123xyz-SHEET_ID_HERE/edit
                                     ^^^^^^^^^^^^^^^^
```

Copy the Sheet ID from the URL.

### 6. Update .env File

Open your `.env` file and update the Google Sheets section:

```bash
# Google Sheets Configuration
GOOGLE_SERVICE_ACCOUNT_FILE=/Users/kamaldivi/Development/Python/pure_bhakti_valut/credentials/google_service_account.json
GOOGLE_TEST_SHEET_ID=YOUR_SHEET_ID_HERE
```

Replace `YOUR_SHEET_ID_HERE` with the Sheet ID you copied in step 5.

### 7. Run the Test Script

Now you're ready to test!

```bash
cd /Users/kamaldivi/Development/Python/pure_bhakti_valut
python src/prod_utils/google_sheets_test.py
```

## What the Test Script Does

The test script will:

1. ✅ **Authenticate** with Google Sheets API using your service account
2. ✅ **Write test data** to your sheet:
   - Single cell writes
   - Multiple cell writes
   - Row appends
   - Batch updates
   - Cell formatting
3. ✅ **Read test data** from your sheet:
   - Single cell reads
   - Range reads
   - All records as dictionaries
   - Find cells by value
   - Column reads
4. ✅ **Advanced operations**:
   - Create new worksheets
   - Add data validation (dropdowns)
   - Get sheet metadata

## Expected Output

If everything works correctly, you should see:

```
======================================================================
📚 GOOGLE SHEETS TEST UTILITY
======================================================================

📧 Service Account Email: your-service-account@your-project.iam.gserviceaccount.com

⚠️  IMPORTANT: Make sure to:
   1. Share your Google Sheet with this service account email
   2. Give it 'Editor' permissions
   3. Save the Sheet ID in your .env file
======================================================================

✍️  Testing WRITE operations...
   Worksheet: 'Sheet1'
   1. Writing to cell A1...
   2. Writing multiple cells...
   3. Appending a new row...
   4. Batch updating cells...
   5. Formatting header row...
✅ All WRITE tests passed!

📖 Testing READ operations...
   Worksheet: 'Sheet1'
   1. Reading cell A1...
      Value: 'Test Header'
   2. Reading range A2:F4...
      Rows read: 3
   3. Reading all records as dictionaries...
      Records found: 3
      First record: {'Book ID': 1, 'PDF Name': 'test_book.pdf', ...}
   4. Finding cells with 'APPROVED' status...
      Matches found: 1
   5. Getting all values from sheet...
      Total rows: 6
   6. Reading column B (PDF Names)...
      Values in column B: ['PDF Name', 'test_book.pdf', ...]
✅ All READ tests passed!

🚀 Testing ADVANCED operations...
   1. Creating new worksheet 'TOC Data'...
      ✅ Worksheet created
   2. Adding data validation (dropdown) to column E...
      ✅ Validation added
   3. Adding conditional formatting...
      ⚠️  Conditional formatting requires additional setup
   4. Getting sheet metadata...
      Title: Pure Bhakti Base - Test Sheet
      Worksheets: 2
   5. Testing share permissions...
      📧 Current service account: your-service-account@...
✅ Advanced tests completed!

======================================================================
📊 TEST SUMMARY
======================================================================
   AUTHENTICATION      : ✅ PASS
   WRITE               : ✅ PASS
   READ                : ✅ PASS
   ADVANCED            : ✅ PASS

   Total: 4/4 tests passed

🎉 All tests passed! Google Sheets integration is working correctly.

🔗 View your test sheet: https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID
======================================================================
```

## Troubleshooting

### Error: "Credentials file not found"

Make sure you:
1. Downloaded the JSON credentials file from GCP
2. Saved it to the correct location: `credentials/google_service_account.json`
3. Updated the path in your `.env` file

### Error: "Permission denied" or "Requested entity was not found"

This means the service account doesn't have access to the sheet:
1. Open your Google Sheet
2. Click **Share**
3. Add the service account email with **Editor** permissions
4. Make sure you didn't type the email wrong (copy/paste from JSON file)

### Error: "API has not been used in project"

You need to enable the Google Sheets API:
1. Go to [GCP Console](https://console.cloud.google.com/)
2. Navigate to: **APIs & Services** → **Library**
3. Search for "Google Sheets API"
4. Click **Enable**

Also enable the Google Drive API:
1. Search for "Google Drive API"
2. Click **Enable**

### The script creates a new sheet instead of using mine

This happens if you don't set `GOOGLE_TEST_SHEET_ID` in your `.env` file:
1. Get the Sheet ID from your Google Sheet URL
2. Add it to `.env`: `GOOGLE_TEST_SHEET_ID=your_sheet_id_here`
3. Run the test script again

## Next Steps

Once all tests pass, you're ready to:

1. **Create production Google Sheets** for:
   - Book Metadata review
   - TOC data entry/validation
   - Glossary extraction review
   - Verse Index validation

2. **Build automation utilities**:
   - `google_sheets_prepopulator.py` - Extract from PDFs → write to sheets
   - `google_sheets_loader.py` - Read approved data → load to database

3. **Set up Google Drive integration** for PDF storage

## Security Notes

⚠️ **IMPORTANT:**
- Never commit `google_service_account.json` to git (already in .gitignore)
- Never share your service account credentials
- The service account email is safe to share (it's in the JSON file)
- Only share Google Sheets with the service account email, not with other users

## Support

If you encounter issues not covered here:
1. Check the error message in the test output
2. Verify your GCP project has Google Sheets API enabled
3. Confirm the service account has the correct permissions
4. Make sure the sheet is shared with the service account email

---

**Ready to test?** Run:
```bash
python src/prod_utils/google_sheets_test.py
```
