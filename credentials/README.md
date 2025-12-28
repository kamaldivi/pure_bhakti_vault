# Google Service Account Credentials

This folder should contain your Google Cloud Platform service account credentials.

## Setup Instructions

### 1. Download Your Service Account JSON Credentials

Since you already have a GCP service account set up:

1. Go to [GCP Console](https://console.cloud.google.com/)
2. Navigate to: **IAM & Admin** > **Service Accounts**
3. Find your service account in the list
4. Click on the service account email
5. Go to the **Keys** tab
6. Click **Add Key** > **Create new key**
7. Choose **JSON** format
8. Click **Create** - the file will download automatically

### 2. Save the Credentials File

Save the downloaded JSON file to this directory:

```
/Users/kamaldivi/Development/Python/pure_bhakti_valut/credentials/google_service_account.json
```

### 3. Verify the File

Your JSON file should look something like this:

```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
  "client_id": "123456789...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  ...
}
```

### 4. Important Notes

- **NEVER commit this file to git** (already in .gitignore)
- The service account email (`client_email` in JSON) must be shared with your Google Sheets
- Give the service account **Editor** permissions on your sheets

### 5. Share Google Sheets with Service Account

After downloading credentials:

1. Open the JSON file and copy the `client_email` value
   - It will look like: `your-service-account@your-project.iam.gserviceaccount.com`
2. Open your Google Sheet
3. Click **Share** button
4. Paste the service account email
5. Select **Editor** permission
6. Click **Send**

Now your service account can read and write to that sheet!

## Testing

Once you've saved your credentials file, run:

```bash
python src/prod_utils/google_sheets_test.py
```

This will test your authentication and Google Sheets access.
