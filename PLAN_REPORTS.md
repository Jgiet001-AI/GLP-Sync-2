# Comprehensive CSV/Excel Reports Implementation Plan

## Overview
This plan outlines the implementation of a beautiful, comprehensive reporting system across all pages and workflows in the HPE GreenLake Device & Subscription Sync application.

## Architecture

### Backend: Report Generation API Endpoints

#### New Report Endpoints
```
GET /api/reports/dashboard/export?format={csv|xlsx}
GET /api/reports/devices/export?format={csv|xlsx}&{all device filters}
GET /api/reports/subscriptions/export?format={csv|xlsx}&{all subscription filters}
GET /api/reports/clients/export?format={csv|xlsx}&{all client filters}
GET /api/reports/assignment/template - Download sample CSV for assignments
GET /api/reports/assignment/report?session_id={id} - Final assignment report
```

### Frontend: Global Report Button Component

#### ReportButton Component
A reusable component that appears on every page with contextual exports:
- Dashboard: Export KPIs, device breakdown, subscription breakdown, sync history
- Devices List: Export filtered/full device inventory
- Subscriptions List: Export filtered/full subscription inventory
- Clients Page: Export filtered/full clients data
- Device Assignment: Sample template download + final workflow report

---

## Phase 1: Backend Report Generator Framework

### File: `src/glp/reports/generator.py`

```python
"""
Comprehensive Report Generator Framework

Generates beautiful, data-rich Excel and CSV reports with:
- Multi-sheet Excel workbooks with professional styling
- Executive summary sections
- Data storytelling with charts and KPIs
- Conditional formatting for insights
- Filtered vs full export support
"""

class ReportGenerator:
    # Shared styling themes
    THEMES = {
        'hpe_green': '#01A982',
        'hpe_purple': '#7630EA',
        'header_blue': '#4472C4',
        'success_green': '#C6EFCE',
        'warning_amber': '#FFEB9C',
        'error_red': '#FFC7CE',
    }

    def generate_excel_report(self, report_type, data, filters) -> bytes
    def generate_csv_report(self, report_type, data, filters) -> str
```

---

## Phase 2: Report Types Implementation

### 2.1 Dashboard Executive Report (Excel)

**Sheets:**
1. **Executive Summary**
   - Report metadata (generated date, filters applied, data scope)
   - KPI cards: Total Devices, Active Subscriptions, Utilization %, Expiring Soon
   - Key insights text block

2. **Device Inventory**
   - Device breakdown by type (with totals and percentages)
   - Device breakdown by region
   - Device assignment status distribution

3. **Subscription Analysis**
   - Subscription breakdown by type with utilization
   - License capacity analysis
   - Expiration timeline

4. **Expiring Items**
   - Full list sorted by urgency (days remaining)
   - Color-coded: Red (<7d), Amber (<30d), Yellow (<90d), Green (>90d)

5. **Sync History**
   - Recent sync operations with metrics
   - Success/failure rates

### 2.2 Device Inventory Report (Excel/CSV)

**Excel Sheets:**
1. **Summary**
   - Total devices, filters applied
   - Breakdown by type, region, status

2. **Device List**
   - All device columns with professional formatting
   - Serial, MAC, Type, Model, Region, Location, Status
   - Subscription details (key, type, expiration)
   - Tags (formatted as key:value pairs)
   - Aruba Central info (status, IP, site, software version)

3. **Insights**
   - Devices without subscriptions
   - Devices with expiring subscriptions
   - Offline Aruba Central devices

**CSV Format:**
- Flat structure with all columns
- Tags as JSON string or pipe-separated

### 2.3 Subscription Report (Excel/CSV)

**Excel Sheets:**
1. **Summary**
   - Total subscriptions, active count, utilization
   - Breakdown by type and tier

2. **Subscription List**
   - Key, Type, Status, Tier, Licenses, Utilization %
   - Device count per subscription
   - Start/End dates, Days remaining

3. **Capacity Analysis**
   - Per-type utilization with charts
   - Available vs used licenses

4. **Renewal Planning**
   - Expiring subscriptions sorted by date
   - Renewal recommendations

### 2.4 Clients Report (Excel/CSV)

**Excel Sheets:**
1. **Summary**
   - Total clients, connected/disconnected
   - Health distribution
   - By site breakdown

2. **Clients List**
   - MAC, Name, Site, Health, Status, Type
   - Network details (IP, VLAN, SSID)
   - Connection info (connected to, duration)

3. **Site Statistics**
   - Per-site aggregations
   - Health trends

### 2.5 Assignment Workflow Reports

**Sample Template (CSV):**
```csv
serial_number,mac_address,device_type,subscription_key,application_id,tags
ABC123,00:11:22:33:44:55,AP,SUB-KEY-001,app-id-001,"env:prod;team:networking"
DEF456,66:77:88:99:AA:BB,SWITCH,SUB-KEY-002,app-id-002,"env:dev;team:infrastructure"
```

**Final Report (Excel) - Enhanced:**
1. **Executive Summary**
   - Workflow timestamp and duration
   - Total devices processed
   - Success rate with visual indicator

2. **Operations Breakdown**
   - Devices created vs updated
   - Subscriptions assigned
   - Applications assigned
   - Tags updated

3. **Detailed Results**
   - Per-device status (Created, Updated, Error)
   - What was applied to each device
   - Any error messages

4. **Errors (if any)**
   - Detailed error list with device context
   - Suggested resolutions

---

## Phase 3: Frontend Implementation

### 3.1 Global Report Button Component

**File: `frontend/src/components/reports/ReportButton.tsx`**

```tsx
interface ReportButtonProps {
  reportType: 'dashboard' | 'devices' | 'subscriptions' | 'clients' | 'assignment'
  formats?: ('csv' | 'xlsx')[]
  filters?: Record<string, string>
  templateOnly?: boolean
  disabled?: boolean
}

export function ReportButton({ reportType, formats = ['xlsx', 'csv'], filters, templateOnly }: ReportButtonProps) {
  // Beautiful dropdown with format selection
  // Progress indicator during generation
  // Toast notification on success/error
}
```

### 3.2 Page Integration Points

**Dashboard.tsx:**
- Add ReportButton in header next to sync button
- Export options: Full dashboard report (Excel)

**DevicesList.tsx:**
- Add ReportButton in header next to refresh button
- Pass current filters to export matching data
- Options: Current view (filtered) or All devices

**SubscriptionsList.tsx:**
- Add ReportButton in header
- Pass current filters
- Options: Current view or All subscriptions

**ClientsPage.tsx:**
- Add ReportButton in header
- Pass current filters (type, status, health, site)
- Options: Current view or All clients

**DeviceAssignment.tsx:**
- Upload step: "Download Sample Template" button
- Report step: Enhanced "Download Report" button

### 3.3 Report Downloads Hook

**File: `frontend/src/hooks/useReportDownload.ts`**

```tsx
function useReportDownload() {
  const downloadReport = async (
    reportType: string,
    format: 'csv' | 'xlsx',
    filters?: Record<string, string>
  ) => {
    // Show loading toast
    // Fetch blob from API
    // Trigger download
    // Show success/error toast
  }

  return { downloadReport, isDownloading }
}
```

---

## Phase 4: API Endpoints Implementation

### File: `src/glp/reports/api.py`

```python
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("/dashboard/export")
async def export_dashboard(
    format: str = Query("xlsx", regex="^(csv|xlsx)$"),
    expiring_days: int = Query(90),
):
    """Export dashboard data as Excel or CSV"""
    pass

@router.get("/devices/export")
async def export_devices(
    format: str = Query("xlsx"),
    device_type: Optional[str] = None,
    region: Optional[str] = None,
    assigned_state: Optional[str] = None,
    search: Optional[str] = None,
    all_records: bool = Query(True),
):
    """Export device list with current filters"""
    pass

@router.get("/subscriptions/export")
async def export_subscriptions(
    format: str = Query("xlsx"),
    subscription_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    all_records: bool = Query(True),
):
    """Export subscription list with current filters"""
    pass

@router.get("/clients/export")
async def export_clients(
    format: str = Query("xlsx"),
    type: Optional[str] = None,
    status: Optional[str] = None,
    health: Optional[str] = None,
    site_id: Optional[str] = None,
    all_records: bool = Query(True),
):
    """Export clients list with current filters"""
    pass

@router.get("/assignment/template")
async def download_assignment_template():
    """Download sample CSV template for device assignments"""
    pass
```

---

## Phase 5: Styling & UX

### Excel Report Styling
- HPE brand colors (Green #01A982, Purple #7630EA)
- Professional header styling with frozen panes
- Conditional formatting for status indicators
- Auto-fit column widths
- Data validation where applicable
- Hyperlinks to related resources

### Report Button UX
- Dropdown menu for format selection
- Loading spinner during generation
- Progress toast for large exports
- Success notification with file name
- Error handling with retry option

---

## Implementation Order

1. **Backend Report Generator Framework** (reusable base)
2. **Device Inventory Report** (most requested)
3. **Subscription Report** (license management)
4. **Dashboard Executive Report** (executive overview)
5. **Clients Report** (network operations)
6. **Assignment Template & Enhanced Report**
7. **Frontend ReportButton Component**
8. **Page Integrations**

---

## File Structure

```
src/glp/reports/
├── __init__.py
├── generator.py          # Base report generator
├── styles.py             # Excel styling definitions
├── dashboard_report.py   # Dashboard export logic
├── devices_report.py     # Devices export logic
├── subscriptions_report.py
├── clients_report.py
├── assignment_report.py  # Template + final report
└── api.py                # FastAPI router

frontend/src/
├── components/reports/
│   ├── ReportButton.tsx
│   └── ReportDropdown.tsx
├── hooks/
│   └── useReportDownload.ts
└── api/
    └── reports.ts        # Report API client
```

---

## Success Criteria

1. ✅ Every page has accessible report download
2. ✅ Reports are visually rich with storytelling
3. ✅ Excel reports have multiple sheets with insights
4. ✅ CSV exports are clean and importable
5. ✅ Assignment workflow has sample template
6. ✅ Assignment workflow generates final report
7. ✅ Filters are respected in exports
8. ✅ Performance handles large datasets (10k+ rows)
