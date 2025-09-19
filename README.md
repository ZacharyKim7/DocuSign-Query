# DocuSign Envelope Query API

## Demo
![Demo](https://github.com/user-attachments/assets/83a90cdc-2002-4f9b-b51d-b44d25031996)

A Python Flask API that integrates with DocuSign to:
- Pull envelope data from the DocuSign API using `listStatusChanges`
- Store envelope information in a MySQL database with incremental sync tracking
- Provide REST endpoints to query envelope data
- Support both manual and automated periodic syncing

## Features

- **Incremental Sync**: Efficient syncing using DocuSign's `listStatusChanges` API with last sync date tracking
- **Manual & Automated Sync**: On-demand sync via API or automated periodic sync script
- **Database Storage**: MySQL database with envelope, recipient, and sync tracking
- **REST API**: Query endpoints with filtering, stats, and detailed envelope information
- **Web Interface**: User-friendly HTML interface for searching and viewing envelopes
- **Advanced Search**: Full-text search across deal names, subjects, and sender emails
- **Date Range Filtering**: Filter envelopes by various date fields (created, sent, delivered, completed, updated)
- **Recipient Status Tracking**: Detailed recipient information with hover tooltips showing signature status
- **Deal Name Extraction**: Intelligent extraction of deal names from custom fields and subject lines
- **Sync History**: Track sync history, status, and error logging
- **Custom Status Mapping**: Application-specific status derived from DocuSign statuses
- **Production Support**: Easy switching between demo and production DocuSign environments

## Quick Start

### 1. Prerequisites

- Python 3.8+
- MySQL database
- DocuSign developer account with Integration Key and RSA keypair

### 2. Installation

```bash
# Create a python virtual environment (its named .venv here but you can choose your own name):
\DocuSign-Query>python -m venv .venv
```

```bash
# Activate the venv (you will need scripts activated to activate in PowerShell; alternatively, activate in a cmd):
.venv\Scripts\activate
```

```bash
# Clone and ensure you are in the DocuSign-Query directory
cd DocuSign-Query

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create the MySQL database (will need to be installed separately; cannot be installed with pip):

Sign in with the root user (this is only required for the database setup, and is used in case of an access denied issue):
```
mysql -u root -p
```

Then create the database:
```
mysql> CREATE DATABASE docusign_db
  -> CHARACTER SET utf8mb4
  -> COLLATE utf8mb4_unicode_ci;
```

Create a .env file in the root directory and then edit `.env` with your settings:

```env
# DocuSign API Configuration
INTEGRATION_KEY=your_docusign_integration_key
USER_ID=your_docusign_user_id
RSA_KEY=rsa_private_key
DOCUSIGN_DEMO=false

DATABASE_URL="mysql+pymysql://username:password@127.0.0.1:3306/docusign_db?charset=utf8mb4"

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=1
FLASK_BASE_URL=http://localhost:5000
```

### 4. Database Setup

The application will automatically create the necessary database tables when it starts.

### 5. Running the Application

```bash
\DocuSign-Query>python app.py  # Note that the first startup will take a while to pull all DocuSign envelopes.
```

The API will be available at `http://localhost:5000`

## API Endpoints

### Web Interface

- **GET /** - Main web interface for searching and viewing envelopes

### Envelope Querying

- **GET /envelopes** - List envelopes with optional filtering (limit: 500 results)
  - Query parameters:
    - `status`: DocuSign status (sent, completed, etc.)
    - `app_status`: Application status (Awaiting Customer, Completed, etc.)
    - `search`: Full-text search across deal names, subjects, and sender emails
    - `date_field`: Date field to filter by (created_at, sent_at, delivered_at, completed_at, updated_at)
    - `start_date`: Start date for filtering (YYYY-MM-DD format)
    - `end_date`: End date for filtering (YYYY-MM-DD format)
- **GET /envelopes/{envelope_id}** - Get detailed envelope information including recipients
- **GET /envelopes/stats** - Get envelope statistics and counts
- **GET /envelopes/custom-fields** - Inspect custom field names from recent envelopes

### Data Synchronization

- **POST /sync/envelopes** - Pull envelopes from DocuSign API
  - Body options:
    - `{}` - Incremental sync (default, syncs from last successful sync date)
    - `{"days_back": 7}` - Sync from specific days back
    - `{"force_full_sync": true}` - Full sync (last 30 days)
- **GET /sync/status** - Get sync status and history

### Deal Name Management

- **POST /envelopes/deals/refresh-deal-names** - Re-process existing envelopes to extract deal names using updated logic

## Example Usage

### Sync Envelopes from DocuSign

```bash
# Incremental sync (recommended for regular use)
curl -X POST http://localhost:5000/sync/envelopes \
  -H "Content-Type: application/json" \
  -d '{}'

# Sync specific days back
curl -X POST http://localhost:5000/sync/envelopes \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7}'

# Force full sync
curl -X POST http://localhost:5000/sync/envelopes \
  -H "Content-Type: application/json" \
  -d '{"force_full_sync": true}'

# Check sync status
curl http://localhost:5000/sync/status
```

### Query Envelopes

```bash
# Get all completed envelopes
curl "http://localhost:5000/envelopes?status=completed"

# Get envelopes awaiting customer signature
curl "http://localhost:5000/envelopes?app_status=Awaiting%20Customer"

# Search for envelopes containing "Angiex" in deal name, subject, or sender
curl "http://localhost:5000/envelopes?search=Angiex"

# Search for Vision-related envelopes
curl "http://localhost:5000/envelopes?search=Vision"

# Get envelopes sent in the last week
curl "http://localhost:5000/envelopes?date_field=sent_at&start_date=2025-09-11&end_date=2025-09-18"

# Get envelopes completed in September 2025
curl "http://localhost:5000/envelopes?date_field=completed_at&start_date=2025-09-01&end_date=2025-09-30"

# Combined search: Vision envelopes that are completed
curl "http://localhost:5000/envelopes?search=Vision&status=completed"
```

### Get Statistics

```bash
curl http://localhost:5000/envelopes/stats
```

### Analyze Custom Fields

```bash
# Inspect custom field names to understand deal name sources
curl http://localhost:5000/envelopes/custom-fields
```

### Deal Name Management

```bash
# Refresh deal name extraction for existing envelopes
curl -X POST http://localhost:5000/envelopes/deals/refresh-deal-names
```

## Web Interface

The application includes a user-friendly web interface accessible at `http://localhost:5000`. Features include:

### Search and Filtering
- **Universal Search**: Single search field that searches across deal names, subjects, and sender emails
- **Status Filtering**: Filter by DocuSign status (sent, completed, etc.) and application status
- **Date Range Filtering**: Filter by any date field with start/end date pickers
- **Real-time Results**: Instant search results without page reload

### Envelope Display
- **Card-based Layout**: Clean, organized display of envelope information
- **Hover Tooltips**: Hover over status badges to see detailed recipient signature status
- **Signature Tracking**: Visual indicators showing who has signed and who is pending
- **Responsive Design**: Works on desktop, tablet, and mobile devices

### Key Features
- **Recipient Status Details**: See who needs to sign, who has completed, and who declined
- **Deal Name Highlighting**: Automatically extracted deal names prominently displayed
- **Statistics Dashboard**: Real-time counts of envelopes by status
- **Flexible Layout**: Responsive grid that adapts to content and screen size

## Deal Name Extraction

The system intelligently extracts deal names from multiple sources:

### Custom Fields
- Checks for traditional deal name fields: `deal`, `deal_name`, `dealname`
- Uses `envelopeTypes` field for categorization (consent, purchase, investment, etc.)
- Configurable field mapping in `map.py`

### Subject Line Patterns
- Extracts company names like "Angiex", "Vision", "Morgan Mutual"
- Handles various subject formats:
  - "Complete with DocuSign: Company Name"
  - "Name: Company Action"
  - "FINAL APPROVAL: Company / Client"
  - Direct company name matches

### Configuration
To add new deal name sources, update the `DEAL_NAME_FIELD_MAPPINGS` in `map.py`:

```python
DEAL_NAME_FIELD_MAPPINGS = {
    "your_custom_field": "direct_value",
    "another_field": "category_value",
}
```

## Environment Configuration

### Switching Between Demo and Production

To switch from DocuSign demo to production:

```env
# For Demo Environment
DOCUSIGN_DEMO=true

# For Production Environment  
DOCUSIGN_DEMO=false
```

Make sure to update your credentials accordingly:
- Use production Integration Key
- Use production User ID
- Use production RSA private key

## Database Schema

### Envelopes Table
- `id`: DocuSign envelope ID (primary key)
- `subject`: Envelope email subject
- `sender_email`: Sender's email address
- `deal_name`: Associated deal name (from custom fields)
- `status`: DocuSign status (sent, completed, etc.)
- `app_status`: Application-derived status
- `created_at`, `sent_at`, `delivered_at`, `completed_at`: Timestamps
- `updated_at`: Last update timestamp

### Recipients Table
- `id`: Auto-increment primary key
- `envelope_id`: Foreign key to envelopes
- `name`, `email`: Recipient information
- `role`: Recipient role
- `routing_order`: Signing order
- `recipient_status`: Recipient-specific status
- `raw`: Full recipient JSON data

### Sync Logs Table
- `id`: Auto-increment primary key
- `sync_type`: Type of sync (envelope_sync)
- `last_sync_date`: Date of the sync operation
- `envelopes_synced`: Number of envelopes processed
- `sync_status`: success, error, or partial
- `error_message`: Error details if sync failed
- `created_at`: When the sync log was created

## Application Status Mapping

The system maps DocuSign statuses to application-specific statuses:

- **Draft**: Envelope created but not sent
- **Awaiting Customer**: Sent but no signatures yet
- **Partially Signed**: Some but not all recipients have signed
- **Awaiting Processing**: All recipients signed, awaiting completion
- **Completed**: Envelope fully completed
- **Declined**: Envelope declined by recipient
- **Cancelled**: Envelope voided

## Periodic Sync Setup

For automated syncing, you can use the provided `periodic_sync.py` script:

```bash
# Run incremental sync
python periodic_sync.py

# Check sync status
python periodic_sync.py status

# Set up as a cron job (Linux/Mac)
# Run every hour
0 * * * * cd /path/to/Flask-MySQL && python periodic_sync.py

# Or use Windows Task Scheduler on Windows
```

The script will:
- Perform incremental sync based on the last successful sync date
- Log results with timestamps
- Exit with appropriate status codes for monitoring

## Testing

Run the integration test to verify your setup:

```bash
python test_integration.py
```

This will test all API endpoints and verify the integration is working correctly.

## Security Considerations

- Use HTTPS in production
- Secure your DocuSign RSA private key
- Use environment variables for sensitive configuration
- Implement proper authentication/authorization for API endpoints
- Consider rate limiting for sync endpoints
- Monitor sync logs for unusual activity

## Dependencies

- Flask: Web framework
- SQLAlchemy: ORM and database toolkit
- PyMySQL: MySQL database connector
- DocuSign eSignature SDK: DocuSign API integration
- PyJWT: JWT token handling
- python-dotenv: Environment variable management

## Project Structure

```
Flask-MySQL/
├── app.py                 # Main Flask application with web interface and API endpoints
├── models.py             # Database models (Envelope, Recipient, SyncLog)
├── map.py                # Data mapping and deal name extraction functions
├── docusign_client.py    # DocuSign API client with listStatusChanges
├── Templates/
│   └── index.html        # Web interface with search, filtering, and envelope display
├── periodic_sync.py      # Automated sync script for cron/scheduler
├── test_integration.py   # Integration tests
├── requirements.txt      # Python dependencies
├── .env.example         # Environment configuration template
└── README.md            # This file
```
