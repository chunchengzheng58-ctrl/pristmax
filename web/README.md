# Web Management Console

Management interface for the Semantic Data Reduction System.

## Quick Start

### 1. Start the Web Server

```bash
cd C:/Users/zcc36/Documents/ChatGPT/存储项目
python web/run_web.py
```

This will:
- Generate sample audit data (30 days)
- Create sample policies
- Start the Flask server on http://localhost:5000
- Open your browser automatically

### 2. Manual Start

```bash
cd C:/Users/zcc36/Documents/ChatGPT/存储项目
python web/api.py
```

Then open http://localhost:5000 in your browser.

## Features

### Dashboard
- Real-time storage reduction metrics
- Storage trend charts
- Recent alerts and anomalies
- Data processing activity log

### Policy Management
- Create policies from templates
- Edit policy configurations
- Version history tracking
- Rollback to previous versions
- Activate/suspend policies

### Camera Management
- View all cameras
- Assign policies to cameras
- Monitor storage usage
- Track savings per camera

### Audit Log
- Query audit entries by time range, type
- Verify audit trail integrity
- Export audit data
- View processing history

### Compliance
- Generate GDPR compliance reports
- Generate SOC2 compliance reports
- View audit trail integrity
- Track open findings

### ROI Calculator
- Calculate savings projections
- Estimate implementation costs
- ROI and payback period

## API Endpoints

### Dashboard
- `GET /api/dashboard/stats` - Dashboard statistics
- `GET /api/dashboard/trend?days=7` - Trend data
- `GET /api/dashboard/alerts` - Recent alerts

### Policies
- `GET /api/policies` - List all policies
- `POST /api/policies` - Create policy
- `GET /api/policies/<id>` - Get policy details
- `PUT /api/policies/<id>` - Update policy
- `POST /api/policies/<id>/activate` - Activate policy
- `POST /api/policies/<id>/suspend` - Suspend policy
- `POST /api/policies/<id>/rollback` - Rollback policy
- `GET /api/policies/templates` - List templates

### Cameras
- `GET /api/cameras` - List cameras
- `POST /api/cameras` - Add camera
- `PUT /api/cameras/<id>/policy` - Assign policy

### Audit
- `GET /api/audit` - Query audit log
- `GET /api/audit/verify` - Verify integrity
- `GET /api/audit/stats` - Audit statistics

### Compliance
- `POST /api/compliance/report` - Generate report
- `GET /api/compliance/status` - Compliance status

### ROI
- `GET /api/roi/calculate` - Calculate ROI

## File Structure

```
web/
├── index.html      # Main HTML page
├── api.py          # Flask API server
├── run_web.py      # Demo runner with sample data
└── README.md       # This file
```

## Configuration

The web console stores data in:
- `web_data/audit/` - Audit log storage
- `web_data/policies/` - Policy storage

## Screenshots

### Dashboard
Real-time metrics showing:
- Total storage saved (892 TB)
- Reduction percentage (68%)
- Active policies (12)
- System status

### Policy Management
Visual policy editor with:
- Template selection
- Preservation rules
- Retention settings
- Version history

### Compliance Reports
Automated compliance reports for:
- GDPR data retention
- SOC2 audit trail
- ISO27001 controls
