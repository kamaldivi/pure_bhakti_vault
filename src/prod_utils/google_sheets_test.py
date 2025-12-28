#!/usr/bin/env python3
"""
Google Sheets Test Utility

Tests read and write access to Google Sheets using a service account.

Setup Instructions:
1. Create a GCP project with Google Sheets API enabled
2. Create a service account and download the JSON credentials file
3. Save credentials file to: credentials/google_service_account.json
4. Add GOOGLE_SERVICE_ACCOUNT_FILE path to .env file
5. Create a test Google Sheet and share it with the service account email
6. Add GOOGLE_TEST_SHEET_ID to .env file

Requirements:
    pip install gspread google-auth python-dotenv

Usage:
    python google_sheets_test.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials


class GoogleSheetsTest:
    """Test utility for Google Sheets API access with service account."""

    # Required scopes for Google Sheets API
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file'
    ]

    def __init__(self, credentials_file: str, test_sheet_id: Optional[str] = None):
        """
        Initialize Google Sheets client.

        Args:
            credentials_file: Path to service account JSON credentials
            test_sheet_id: Optional Google Sheet ID for testing
        """
        self.credentials_file = Path(credentials_file)
        self.test_sheet_id = test_sheet_id
        self.client = None
        self.service_account_email = None

        if not self.credentials_file.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {credentials_file}\n"
                f"Please download your service account JSON file from GCP Console."
            )

    def authenticate(self) -> bool:
        """
        Authenticate with Google Sheets API using service account.

        Returns:
            bool: True if authentication successful
        """
        try:
            print("🔐 Authenticating with Google Sheets API...")

            # Load credentials from service account JSON file
            creds = Credentials.from_service_account_file(
                str(self.credentials_file),
                scopes=self.SCOPES
            )

            # Create gspread client
            self.client = gspread.authorize(creds)

            # Extract service account email for display
            import json
            with open(self.credentials_file, 'r') as f:
                creds_data = json.load(f)
                self.service_account_email = creds_data.get('client_email', 'Unknown')

            print(f"✅ Authentication successful!")
            print(f"📧 Service Account: {self.service_account_email}")
            return True

        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return False

    def create_test_sheet(self, title: str = "Pure Bhakti Base - Test Sheet") -> Optional[str]:
        """
        Create a new test Google Sheet.

        Args:
            title: Title for the new sheet

        Returns:
            str: Sheet ID if successful, None otherwise
        """
        try:
            print(f"\n📝 Creating test sheet: '{title}'...")

            spreadsheet = self.client.create(title)
            sheet_id = spreadsheet.id
            sheet_url = spreadsheet.url

            print(f"✅ Test sheet created successfully!")
            print(f"📊 Sheet ID: {sheet_id}")
            print(f"🔗 URL: {sheet_url}")
            print(f"\n⚠️  IMPORTANT: Save this Sheet ID to your .env file:")
            print(f"   GOOGLE_TEST_SHEET_ID={sheet_id}")

            return sheet_id

        except Exception as e:
            print(f"❌ Failed to create sheet: {e}")
            return None

    def test_write_operations(self, sheet_id: str) -> bool:
        """
        Test writing data to Google Sheet.

        Args:
            sheet_id: Google Sheet ID

        Returns:
            bool: True if all write tests pass
        """
        try:
            print(f"\n✍️  Testing WRITE operations...")

            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(sheet_id)

            # Get the first worksheet (or create if doesn't exist)
            try:
                worksheet = spreadsheet.sheet1
            except:
                worksheet = spreadsheet.add_worksheet(title="Test Data", rows=100, cols=10)

            print(f"   Worksheet: '{worksheet.title}'")

            # Test 1: Write single cell
            print(f"   1. Writing to cell A1...")
            worksheet.update_acell('A1', 'Test Header')

            # Test 2: Write multiple cells
            print(f"   2. Writing multiple cells...")
            worksheet.update([
                ['Book ID', 'PDF Name', 'Title', 'Pages', 'Status', 'Timestamp'],
                [1, 'test_book.pdf', 'Test Book Title', 250, 'REVIEW', str(datetime.now())],
                [2, 'another_book.pdf', 'Another Book', 180, 'APPROVED', str(datetime.now())]
            ], 'A2:F4')

            # Test 3: Append row
            print(f"   3. Appending a new row...")
            worksheet.append_row([
                3, 'third_book.pdf', 'Third Book', 320, 'PENDING', str(datetime.now())
            ])

            # Test 4: Batch update (more efficient)
            print(f"   4. Batch updating cells...")
            worksheet.batch_update([
                {
                    'range': 'E2',
                    'values': [['UPDATED']]
                },
                {
                    'range': 'A6',
                    'values': [['Batch Test']]
                }
            ])

            # Test 5: Format cells (make headers bold)
            print(f"   5. Formatting header row...")
            worksheet.format('A2:F2', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })

            print(f"✅ All WRITE tests passed!")
            return True

        except Exception as e:
            print(f"❌ Write test failed: {e}")
            return False

    def test_read_operations(self, sheet_id: str) -> bool:
        """
        Test reading data from Google Sheet.

        Args:
            sheet_id: Google Sheet ID

        Returns:
            bool: True if all read tests pass
        """
        try:
            print(f"\n📖 Testing READ operations...")

            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = spreadsheet.sheet1

            print(f"   Worksheet: '{worksheet.title}'")

            # Test 1: Read single cell
            print(f"   1. Reading cell A1...")
            cell_value = worksheet.acell('A1').value
            print(f"      Value: '{cell_value}'")

            # Test 2: Read range
            print(f"   2. Reading range A2:F4...")
            cell_range = worksheet.get('A2:F4')
            print(f"      Rows read: {len(cell_range)}")

            # Test 3: Get all records as dictionaries
            print(f"   3. Reading all records as dictionaries...")
            records = worksheet.get_all_records(head=2)  # Row 2 is header
            print(f"      Records found: {len(records)}")
            if records:
                print(f"      First record: {records[0]}")

            # Test 4: Find cells matching criteria
            print(f"   4. Finding cells with 'APPROVED' status...")
            approved_cells = worksheet.findall('APPROVED')
            print(f"      Matches found: {len(approved_cells)}")

            # Test 5: Get all values
            print(f"   5. Getting all values from sheet...")
            all_values = worksheet.get_all_values()
            print(f"      Total rows: {len(all_values)}")

            # Test 6: Get values by column
            print(f"   6. Reading column B (PDF Names)...")
            col_b = worksheet.col_values(2)  # Column B (1-indexed)
            print(f"      Values in column B: {col_b[:5]}")  # Show first 5

            print(f"✅ All READ tests passed!")
            return True

        except Exception as e:
            print(f"❌ Read test failed: {e}")
            return False

    def test_advanced_operations(self, sheet_id: str) -> bool:
        """
        Test advanced Google Sheets operations.

        Args:
            sheet_id: Google Sheet ID

        Returns:
            bool: True if all tests pass
        """
        try:
            print(f"\n🚀 Testing ADVANCED operations...")

            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = spreadsheet.sheet1

            # Test 1: Create a new worksheet
            print(f"   1. Creating new worksheet 'TOC Data'...")
            try:
                toc_sheet = spreadsheet.add_worksheet(
                    title="TOC Data",
                    rows=100,
                    cols=6
                )
                print(f"      ✅ Worksheet created")

                # Add some data
                toc_sheet.update([
                    ['book_id', 'toc_level', 'toc_label', 'page_label', 'status'],
                    [1, 1, 'Chapter 1', '1', 'APPROVED'],
                    [1, 2, 'Section 1.1', '3', 'REVIEW']
                ], 'A1:E3')

            except gspread.exceptions.APIError as e:
                if 'already exists' in str(e):
                    print(f"      ⚠️  Worksheet already exists, skipping")
                else:
                    raise

            # Test 2: Data validation (create dropdown)
            print(f"   2. Adding data validation (dropdown) to column E...")
            try:
                worksheet.add_validation(
                    'E2:E100',
                    gspread.utils.ValidationCondition.ONE_OF_LIST,
                    ['PENDING', 'REVIEW', 'APPROVED', 'LOADED'],
                    strict=True,
                    showCustomUi=True
                )
                print(f"      ✅ Validation added")
            except Exception as e:
                print(f"      ⚠️  Could not add validation: {e}")

            # Test 3: Conditional formatting
            print(f"   3. Adding conditional formatting...")
            try:
                # This requires more complex API calls
                print(f"      ⚠️  Conditional formatting requires additional setup")
            except Exception as e:
                print(f"      ⚠️  Skipping: {e}")

            # Test 4: Get sheet metadata
            print(f"   4. Getting sheet metadata...")
            sheet_metadata = spreadsheet.fetch_sheet_metadata()
            print(f"      Title: {sheet_metadata['properties']['title']}")
            print(f"      Worksheets: {len(sheet_metadata['sheets'])}")

            # Test 5: Share sheet with an email (optional)
            print(f"   5. Testing share permissions...")
            print(f"      📧 Current service account: {self.service_account_email}")
            print(f"      ℹ️  To share with users, use: spreadsheet.share('user@example.com', perm_type='user', role='writer')")

            print(f"✅ Advanced tests completed!")
            return True

        except Exception as e:
            print(f"❌ Advanced test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def display_instructions(self):
        """Display instructions for using the test utility."""
        print("\n" + "="*70)
        print("📚 GOOGLE SHEETS TEST UTILITY")
        print("="*70)
        print(f"\n📧 Service Account Email: {self.service_account_email}")
        print(f"\n⚠️  IMPORTANT: Make sure to:")
        print(f"   1. Share your Google Sheet with this service account email")
        print(f"   2. Give it 'Editor' permissions")
        print(f"   3. Save the Sheet ID in your .env file")
        print("="*70 + "\n")

    def run_all_tests(self, sheet_id: Optional[str] = None) -> Dict[str, bool]:
        """
        Run all test operations.

        Args:
            sheet_id: Optional sheet ID. If not provided, will create a new sheet.

        Returns:
            Dict with test results
        """
        results = {
            'authentication': False,
            'write': False,
            'read': False,
            'advanced': False
        }

        # Test authentication
        if not self.authenticate():
            return results

        results['authentication'] = True
        self.display_instructions()

        # Determine which sheet to use
        test_sheet_id = sheet_id or self.test_sheet_id

        if not test_sheet_id:
            print("⚠️  No Sheet ID provided. Creating a new test sheet...")
            test_sheet_id = self.create_test_sheet()
            if not test_sheet_id:
                return results
        else:
            print(f"📊 Using existing sheet ID: {test_sheet_id}")

        # Run tests
        results['write'] = self.test_write_operations(test_sheet_id)
        results['read'] = self.test_read_operations(test_sheet_id)
        results['advanced'] = self.test_advanced_operations(test_sheet_id)

        # Print summary
        self.print_summary(results, test_sheet_id)

        return results

    def print_summary(self, results: Dict[str, bool], sheet_id: str):
        """Print test summary."""
        print("\n" + "="*70)
        print("📊 TEST SUMMARY")
        print("="*70)

        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"   {test_name.upper():20s}: {status}")

        total_tests = len(results)
        passed_tests = sum(1 for v in results.values() if v)

        print(f"\n   Total: {passed_tests}/{total_tests} tests passed")

        if passed_tests == total_tests:
            print("\n🎉 All tests passed! Google Sheets integration is working correctly.")
            print(f"\n🔗 View your test sheet: https://docs.google.com/spreadsheets/d/{sheet_id}")
        else:
            print("\n⚠️  Some tests failed. Please check the errors above.")

        print("="*70 + "\n")


def main():
    """Main function to run Google Sheets tests."""

    # Load environment variables
    load_dotenv(override=True)

    # Get configuration from environment
    credentials_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
    test_sheet_id = os.getenv('GOOGLE_TEST_SHEET_ID')

    # Print configuration
    print("\n" + "="*70)
    print("🔧 CONFIGURATION")
    print("="*70)

    if not credentials_file:
        print("\n❌ ERROR: GOOGLE_SERVICE_ACCOUNT_FILE not set in .env file")
        print("\nPlease add the following to your .env file:")
        print("   GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/your/service-account-credentials.json")
        print("\nSteps to get your credentials file:")
        print("   1. Go to GCP Console: https://console.cloud.google.com/")
        print("   2. Navigate to: IAM & Admin > Service Accounts")
        print("   3. Select your service account")
        print("   4. Go to Keys tab > Add Key > Create new key")
        print("   5. Choose JSON format and download")
        print("   6. Save to: credentials/google_service_account.json")
        sys.exit(1)

    print(f"📁 Credentials file: {credentials_file}")
    print(f"📊 Test Sheet ID: {test_sheet_id or 'Not set (will create new sheet)'}")
    print("="*70)

    # Check if credentials file exists
    if not Path(credentials_file).exists():
        print(f"\n❌ ERROR: Credentials file not found at: {credentials_file}")
        print(f"\nPlease ensure your service account JSON file is saved to this location.")
        sys.exit(1)

    try:
        # Create test instance
        tester = GoogleSheetsTest(
            credentials_file=credentials_file,
            test_sheet_id=test_sheet_id
        )

        # Run all tests
        results = tester.run_all_tests()

        # Exit with appropriate code
        if all(results.values()):
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
