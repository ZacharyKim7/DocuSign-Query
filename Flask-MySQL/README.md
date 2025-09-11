# DocuSign Flask API Integration

A Python Flask API that integrates with DocuSign to:
- Receive real-time envelope updates via DocuSign Connect webhooks
- Pull envelope data from the DocuSign API
- Store envelope information in a MySQL database
- Provide REST endpoints to query envelope data

## Features

- **Real-time Updates**: DocuSign Connect webhook endpoint for immediate envelope status updates
- **Bulk Sync**: Pull and sync envelopes from DocuSign API
- **Database Storage**: MySQL database with envelope and recipient tracking
- **REST API**: Query endpoints with filtering, stats, and detailed envelope information
- **Security**: HMAC signature verification for webhooks
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

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# DocuSign API Configuration
INTEGRATION_KEY=your_docusign_integration_key
USER_ID=your_docusign_user_id
RSA_KEY=path/to/private.key
DOCUSIGN_DEMO=true

# Database Configuration
DATABASE_URL=mysql+pymysql://username:password@localhost/docusign_db

# Optional: DocuSign Connect webhook HMAC key
DOCUSIGN_WEBHOOK_HMAC_KEY=your_webhook_hmac_key
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
  - Body: `{"days_back": 30}` (optional, defaults to 30 days)

### Webhooks

- **POST /docusign/webhook** - DocuSign Connect webhook endpoint
  - Accepts XML payloads from DocuSign Connect
  - Verifies HMAC signature if configured

## Example Usage

### Sync Envelopes from DocuSign

```bash
curl -X POST http://localhost:5000/sync/envelopes \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7}'
```

### Query Envelopes

```bash
# Get all completed envelopes
curl "http://localhost:5000/envelopes?status=completed"

# Get envelopes awaiting customer signature
curl "http://localhost:5000/envelopes?app_status=Awaiting Customer"

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

## Application Status Mapping

The system maps DocuSign statuses to application-specific statuses:

- **Draft**: Envelope created but not sent
- **Awaiting Customer**: Sent but no signatures yet
- **Partially Signed**: Some but not all recipients have signed
- **Awaiting Processing**: All recipients signed, awaiting completion
- **Completed**: Envelope fully completed
- **Declined**: Envelope declined by recipient
- **Cancelled**: Envelope voided

## DocuSign Connect Configuration

In your DocuSign Connect configuration:

1. **Webhook URL**: `https://your-domain.com/docusign/webhook`
2. **Include Data**: Envelope status, recipient status, custom fields
3. **Events**: All envelope and recipient events
4. **HMAC**: Configure HMAC key for security (recommended)

## Testing

Run the integration test to verify your setup:

```bash
python test_integration.py
```

This will test all API endpoints and verify the integration is working correctly.

## Security Considerations

- Use HTTPS in production
- Configure HMAC signature verification for webhooks
- Secure your DocuSign RSA private key
- Use environment variables for sensitive configuration
- Implement proper authentication/authorization for API endpoints

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
├── models.py             # Database models
├── map.py                # Data mapping functions
├── docusign_client.py    # DocuSign API client
├── test_integration.py   # Integration tests
├── requirements.txt      # Python dependencies
├── .env.example         # Environment configuration template
└── README.md            # This file
```