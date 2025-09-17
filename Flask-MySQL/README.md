# DocuSign Flask API Integration

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
- **Sync History**: Track sync history, status, and error logging
- **Custom Status Mapping**: Application-specific status derived from DocuSign statuses

## Quick Start

### 1. Prerequisites

- Python 3.8+
- MySQL database
- DocuSign developer account with Integration Key and RSA keypair

### 2. Installation

```bash
# Clone and navigate to the Flask-MySQL directory
cd Flask-MySQL

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create the MySQL database (will need to be installed separately; cannot be installed with pip):
```
mysql> CREATE DATABASE docusign_db
  -> CHARACTER SET utf8mb4
  -> COLLATE utf8mb4_unicode_ci;
```

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# DocuSign API Configuration
INTEGRATION_KEY=your_docusign_integration_key
USER_ID=your_docusign_user_id
RSA_KEY=rsa_private_key
DOCUSIGN_DEMO=false

DATABASE_URL=mysql+pymysql://username:password@localhost/docusign_db
```

### 4. Database Setup

The application will automatically create the necessary database tables when it starts.

### 5. Running the Application

```bash
python app.py
```

The API will be available at `http://localhost:5000`

## API Endpoints

### Envelope Querying

- **GET /envelopes** - List envelopes with optional filtering
  - Query parameters:
    - `status`: DocuSign status (sent, completed, etc.)
    - `app_status`: Application status (Awaiting Customer, Completed, etc.)
    - `deal`: Filter by deal name
- **GET /envelopes/{envelope_id}** - Get detailed envelope information
- **GET /envelopes/stats** - Get envelope statistics

### Data Synchronization

- **POST /sync/envelopes** - Pull envelopes from DocuSign API
  - Body options:
    - `{}` - Incremental sync (default, syncs from last successful sync date)
    - `{"days_back": 7}` - Sync from specific days back
    - `{"force_full_sync": true}` - Full sync (last 30 days)
- **GET /sync/status** - Get sync status and history

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

# Get envelopes for a specific deal
curl "http://localhost:5000/envelopes?deal=Deal123"
```

### Get Statistics

```bash
curl http://localhost:5000/envelopes/stats
```

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
├── app.py                 # Main Flask application
├── models.py             # Database models (Envelope, Recipient, SyncLog)
├── map.py                # Data mapping functions
├── docusign_client.py    # DocuSign API client with listStatusChanges
├── periodic_sync.py      # Automated sync script for cron/scheduler
├── test_integration.py   # Integration tests
├── requirements.txt      # Python dependencies
├── .env.example         # Environment configuration template
└── README.md            # This file
```