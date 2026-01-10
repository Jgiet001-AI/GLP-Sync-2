# Architecture Plan: Excel-Based Device Assignment Workflow

## Overview

This plan implements a feature that allows users to:
1. Upload an Excel file with serial numbers and MAC addresses
2. Look up devices in the database to find their UUIDs
3. Check what's already assigned (subscription, application, region, tags)
4. Present options for missing assignments based on device type
5. Intelligently patch only what's needed
6. Resync with GreenLake and generate a report

---

## Architecture: Clean Architecture with Hexagonal (Ports & Adapters)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           React Frontend                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐ │
│  │ FileUpload  │  │ DeviceTable  │  │ OptionPanel │  │ ReportViewer  │ │
│  └─────────────┘  └──────────────┘  └─────────────┘  └───────────────┘ │
└───────────────────────────────────────┬─────────────────────────────────┘
                                        │ REST API
┌───────────────────────────────────────┴─────────────────────────────────┐
│                        FastAPI Controllers (Adapters)                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │ /api/upload     │  │ /api/devices    │  │ /api/assignments        │  │
│  │ /api/options    │  │ /api/apply      │  │ /api/sync & /api/report │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└───────────────────────────────────────┬─────────────────────────────────┘
                                        │
┌───────────────────────────────────────┴─────────────────────────────────┐
│                          Use Cases (Application Layer)                   │
│  ┌────────────────────┐  ┌────────────────────┐  ┌───────────────────┐  │
│  │ ProcessExcelUseCase│  │ LookupDevicesUseCase│  │ GetOptionsUseCase │  │
│  ├────────────────────┤  ├────────────────────┤  ├───────────────────┤  │
│  │ - Parse Excel      │  │ - Find by serial   │  │ - Subscriptions   │  │
│  │ - Validate rows    │  │ - Find by MAC      │  │ - Regions only    │  │
│  │ - Extract devices  │  │ - Enrich with DB   │  │ - Tags available  │  │
│  └────────────────────┘  └────────────────────┘  └───────────────────┘  │
│                                                                          │
│  ┌────────────────────┐  ┌────────────────────┐  ┌───────────────────┐  │
│  │ ApplyAssignments   │  │ SyncWithGreenLake  │  │ GenerateReport    │  │
│  │ UseCase            │  │ UseCase            │  │ UseCase           │  │
│  ├────────────────────┤  ├────────────────────┤  ├───────────────────┤  │
│  │ - Detect gaps      │  │ - Full resync      │  │ - PDF/Excel       │  │
│  │ - Patch only needed│  │ - Update DB        │  │ - Summary stats   │  │
│  │ - Wait for async   │  │ - Validate success │  │ - Error details   │  │
│  └────────────────────┘  └────────────────────┘  └───────────────────┘  │
└───────────────────────────────────────┬─────────────────────────────────┘
                                        │
┌───────────────────────────────────────┴─────────────────────────────────┐
│                     Domain Layer (Entities & Interfaces)                 │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                          Entities                                    ││
│  │  DeviceAssignment, SubscriptionOption, RegionMapping, AssignmentGap ││
│  └─────────────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                        Ports (Interfaces)                            ││
│  │  IDeviceRepository, ISubscriptionRepository, IDeviceManagerPort     ││
│  │  IExcelParser, ISyncService, IReportGenerator                       ││
│  └─────────────────────────────────────────────────────────────────────┘│
└───────────────────────────────────────┬─────────────────────────────────┘
                                        │
┌───────────────────────────────────────┴─────────────────────────────────┐
│                     Infrastructure Adapters                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐ │
│  │ PostgresDevice   │  │ GLPDeviceManager │  │ OpenpyxlExcelParser    │ │
│  │ Repository       │  │ Adapter          │  │                        │ │
│  └──────────────────┘  └──────────────────┘  └────────────────────────┘ │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐ │
│  │ PostgresSubscr.  │  │ DeviceSyncer     │  │ ReportLabGenerator     │ │
│  │ Repository       │  │ (existing)       │  │                        │ │
│  └──────────────────┘  └──────────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Domain Entities

### 1. DeviceAssignment (Value Object)
```python
@dataclass(frozen=True)
class DeviceAssignment:
    """Represents a device from Excel with its current state."""
    serial_number: str
    mac_address: Optional[str]

    # Looked up from DB
    device_id: Optional[UUID]  # None = device not in DB, needs POST
    device_type: Optional[str]  # NETWORK, COMPUTE, STORAGE

    # Current assignments (from DB)
    current_subscription_id: Optional[UUID]
    current_application_id: Optional[UUID]
    current_region: Optional[str]
    current_tags: dict[str, str]

    # User-selected assignments
    selected_subscription_id: Optional[UUID]
    selected_application_id: Optional[UUID]
    selected_region: Optional[str]  # Display only (derived from app_id)
    selected_tags: dict[str, str]
```

### 2. AssignmentGap (Value Object)
```python
@dataclass(frozen=True)
class AssignmentGap:
    """What needs to be assigned for a device."""
    device_id: UUID
    needs_subscription: bool
    needs_application: bool
    needs_tags: bool

    # If gaps exist, what to assign
    subscription_id: Optional[UUID]
    application_id: Optional[UUID]
    tags_to_add: dict[str, str]
    tags_to_remove: list[str]
```

### 3. RegionMapping (Entity)
```python
@dataclass
class RegionMapping:
    """Maps application UUID to region name (1:1 relationship)."""
    application_id: UUID
    region: str  # e.g., "us-west", "eu-central"
    display_name: str  # e.g., "US West", "EU Central"
```

### 4. SubscriptionOption (Value Object)
```python
@dataclass(frozen=True)
class SubscriptionOption:
    """A subscription available for assignment."""
    id: UUID
    key: str
    subscription_type: str  # CENTRAL_AP, CENTRAL_SWITCH, etc.
    tier: str
    available_quantity: int
    end_time: datetime

    # Computed
    compatible_device_types: list[str]  # Which device types can use this
```

---

## Port Interfaces (Domain Layer)

### IDeviceRepository
```python
class IDeviceRepository(ABC):
    @abstractmethod
    async def find_by_serial(self, serial: str) -> Optional[Device]: ...

    @abstractmethod
    async def find_by_mac(self, mac: str) -> Optional[Device]: ...

    @abstractmethod
    async def find_by_serials(self, serials: list[str]) -> list[Device]: ...

    @abstractmethod
    async def get_device_with_assignments(self, device_id: UUID) -> DeviceAssignment: ...
```

### ISubscriptionRepository
```python
class ISubscriptionRepository(ABC):
    @abstractmethod
    async def get_available_subscriptions(
        self,
        device_type: str
    ) -> list[SubscriptionOption]: ...

    @abstractmethod
    async def get_region_mappings(self) -> list[RegionMapping]: ...
```

### IDeviceManagerPort
```python
class IDeviceManagerPort(ABC):
    @abstractmethod
    async def add_device(
        self,
        serial: str,
        device_type: str,
        mac_address: Optional[str]
    ) -> UUID: ...

    @abstractmethod
    async def assign_subscription(
        self,
        device_ids: list[UUID],
        subscription_id: UUID
    ) -> OperationResult: ...

    @abstractmethod
    async def assign_application(
        self,
        device_ids: list[UUID],
        application_id: UUID
    ) -> OperationResult: ...

    @abstractmethod
    async def update_tags(
        self,
        device_ids: list[UUID],
        tags: dict[str, Optional[str]]
    ) -> OperationResult: ...
```

### IExcelParser
```python
class IExcelParser(ABC):
    @abstractmethod
    def parse(self, file_content: bytes) -> list[ExcelRow]: ...

    @abstractmethod
    def validate(self, rows: list[ExcelRow]) -> ValidationResult: ...
```

---

## Use Cases (Application Layer)

### 1. ProcessExcelUseCase
**Input:** Excel file bytes
**Output:** List of DeviceAssignment with gaps identified

```python
class ProcessExcelUseCase:
    def __init__(
        self,
        excel_parser: IExcelParser,
        device_repo: IDeviceRepository,
    ):
        self.parser = excel_parser
        self.devices = device_repo

    async def execute(self, file_content: bytes) -> ProcessResult:
        # 1. Parse Excel
        rows = self.parser.parse(file_content)
        validation = self.parser.validate(rows)
        if not validation.is_valid:
            return ProcessResult(success=False, errors=validation.errors)

        # 2. Batch lookup devices
        serials = [r.serial_number for r in rows]
        devices = await self.devices.find_by_serials(serials)
        device_map = {d.serial_number: d for d in devices}

        # 3. Build assignments with gaps
        assignments = []
        for row in rows:
            device = device_map.get(row.serial_number)
            assignment = DeviceAssignment(
                serial_number=row.serial_number,
                mac_address=row.mac_address,
                device_id=device.id if device else None,
                device_type=device.device_type if device else None,
                current_subscription_id=device.subscription_id if device else None,
                # ... etc
            )
            assignments.append(assignment)

        return ProcessResult(success=True, assignments=assignments)
```

### 2. GetOptionsUseCase
**Input:** Device type
**Output:** Available subscriptions, regions (as application mappings)

```python
class GetOptionsUseCase:
    def __init__(
        self,
        subscription_repo: ISubscriptionRepository,
    ):
        self.subscriptions = subscription_repo

    async def execute(self, device_type: str) -> OptionsResult:
        # Get subscriptions compatible with device type
        subscriptions = await self.subscriptions.get_available_subscriptions(device_type)

        # Get regions (which are 1:1 with application IDs)
        regions = await self.subscriptions.get_region_mappings()

        return OptionsResult(
            subscriptions=subscriptions,
            regions=regions,  # User sees region name, we store app_id
        )
```

### 3. ApplyAssignmentsUseCase
**Input:** List of DeviceAssignment with user selections
**Output:** Operation results, devices created/patched

```python
class ApplyAssignmentsUseCase:
    def __init__(
        self,
        device_manager: IDeviceManagerPort,
        device_repo: IDeviceRepository,
    ):
        self.manager = device_manager
        self.devices = device_repo

    async def execute(self, assignments: list[DeviceAssignment]) -> ApplyResult:
        results = []

        # Group by operation type for batching (max 25 per API call)
        new_devices = [a for a in assignments if a.device_id is None]
        need_subscription = [a for a in assignments if a.needs_subscription_patch]
        need_application = [a for a in assignments if a.needs_application_patch]
        need_tags = [a for a in assignments if a.needs_tag_patch]

        # 1. Add new devices (POST)
        for device in new_devices:
            result = await self.manager.add_device(
                serial=device.serial_number,
                device_type=device.device_type,
                mac_address=device.mac_address,
            )
            results.append(result)

        # 2. Assign subscriptions (PATCH - batched)
        for batch in chunk(need_subscription, 25):
            device_ids = [d.device_id for d in batch]
            result = await self.manager.assign_subscription(
                device_ids=device_ids,
                subscription_id=batch[0].selected_subscription_id,  # Same sub for batch
            )
            results.append(result)

        # 3. Assign applications (PATCH - batched)
        for batch in chunk(need_application, 25):
            device_ids = [d.device_id for d in batch]
            result = await self.manager.assign_application(
                device_ids=device_ids,
                application_id=batch[0].selected_application_id,
            )
            results.append(result)

        # 4. Update tags (PATCH - batched)
        for batch in chunk(need_tags, 25):
            device_ids = [d.device_id for d in batch]
            result = await self.manager.update_tags(
                device_ids=device_ids,
                tags=batch[0].selected_tags,
            )
            results.append(result)

        return ApplyResult(operations=results)
```

### 4. SyncAndReportUseCase
**Input:** None (uses existing DeviceSyncer)
**Output:** Sync results + report

```python
class SyncAndReportUseCase:
    def __init__(
        self,
        device_syncer: DeviceSyncer,
        subscription_syncer: SubscriptionSyncer,
        report_generator: IReportGenerator,
    ):
        self.device_syncer = device_syncer
        self.subscription_syncer = subscription_syncer
        self.report_gen = report_generator

    async def execute(self, operation_results: list[OperationResult]) -> Report:
        # 1. Trigger full sync
        sync_result = await self.device_syncer.sync_all()

        # 2. Generate report
        report = self.report_gen.generate(
            operations=operation_results,
            sync_result=sync_result,
        )

        return report
```

---

## Intelligent Gap Detection Logic

```python
def detect_gaps(assignment: DeviceAssignment) -> AssignmentGap:
    """Determine what needs to be patched for this device."""

    # Device doesn't exist - needs POST first
    if assignment.device_id is None:
        return AssignmentGap(
            device_id=None,
            needs_creation=True,
            needs_subscription=True,
            needs_application=True,
            needs_tags=bool(assignment.selected_tags),
        )

    # Device exists - check what's missing
    needs_sub = (
        assignment.current_subscription_id is None
        and assignment.selected_subscription_id is not None
    )

    needs_app = (
        assignment.current_application_id is None
        and assignment.selected_application_id is not None
    )

    needs_tags = (
        assignment.selected_tags
        and assignment.selected_tags != assignment.current_tags
    )

    return AssignmentGap(
        device_id=assignment.device_id,
        needs_creation=False,
        needs_subscription=needs_sub,
        needs_application=needs_app,
        needs_tags=needs_tags,
        subscription_id=assignment.selected_subscription_id if needs_sub else None,
        application_id=assignment.selected_application_id if needs_app else None,
        tags_to_add={k: v for k, v in assignment.selected_tags.items() if v},
        tags_to_remove=[k for k, v in assignment.selected_tags.items() if v is None],
    )
```

---

## API Endpoints (FastAPI)

```python
# POST /api/upload
# Upload Excel file, returns parsed devices with gaps
@router.post("/upload")
async def upload_excel(file: UploadFile) -> UploadResponse:
    result = await process_excel_use_case.execute(await file.read())
    return UploadResponse(
        devices=result.assignments,
        errors=result.errors,
    )

# GET /api/options/{device_type}
# Get available subscriptions and regions for device type
@router.get("/options/{device_type}")
async def get_options(device_type: str) -> OptionsResponse:
    result = await get_options_use_case.execute(device_type)
    return OptionsResponse(
        subscriptions=result.subscriptions,
        regions=[
            {"id": r.application_id, "name": r.display_name}  # Show region, store app_id
            for r in result.regions
        ],
    )

# POST /api/apply
# Apply user-selected assignments
@router.post("/apply")
async def apply_assignments(request: ApplyRequest) -> ApplyResponse:
    result = await apply_assignments_use_case.execute(request.assignments)
    return ApplyResponse(operations=result.operations)

# POST /api/sync
# Trigger resync with GreenLake
@router.post("/sync")
async def sync_and_report(request: SyncRequest) -> ReportResponse:
    result = await sync_and_report_use_case.execute(request.operation_results)
    return ReportResponse(report=result)
```

---

## React Frontend Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── FileUpload.tsx        # Drag-and-drop Excel upload
│   │   ├── DeviceTable.tsx       # Shows devices with status
│   │   ├── AssignmentPanel.tsx   # Subscription/region/tag selection
│   │   ├── OptionSelector.tsx    # Dropdown for options
│   │   ├── TagEditor.tsx         # Add/edit/remove tags
│   │   └── ReportViewer.tsx      # Shows final report
│   │
│   ├── pages/
│   │   └── DeviceAssignment.tsx  # Main workflow page
│   │
│   ├── hooks/
│   │   ├── useUpload.ts          # Upload handling
│   │   ├── useDevices.ts         # Device state management
│   │   └── useAssignments.ts     # Assignment operations
│   │
│   ├── api/
│   │   └── client.ts             # API client
│   │
│   └── types/
│       └── index.ts              # TypeScript types
```

### UI Flow

1. **Upload Screen**
   - Drag-and-drop zone for Excel file
   - Shows preview of parsed devices
   - Highlights devices not found in DB (need creation)

2. **Assignment Screen**
   - Table showing all devices with current status
   - Color-coded columns: green (assigned), yellow (missing), red (not in DB)
   - Bulk selection for applying same assignment to multiple devices
   - Per-device type filtering for subscriptions

3. **Options Panel**
   - Subscription dropdown (filtered by device type)
   - Region dropdown (shows region name, maps to application_id)
   - Tag editor (key-value pairs, can add/remove)

4. **Apply & Sync**
   - "Apply Changes" button shows what will happen
   - Progress indicator for async operations
   - "Sync with GreenLake" triggers resync
   - Report viewer shows summary

---

## File Structure (Backend)

```
src/
├── glp/
│   ├── api/                      # Existing
│   │   ├── device_manager.py     # Existing - reuse
│   │   ├── devices.py            # Existing DeviceSyncer
│   │   └── ...
│   │
│   └── assignment/               # NEW module
│       ├── __init__.py
│       │
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── entities.py       # DeviceAssignment, AssignmentGap, etc.
│       │   └── ports.py          # IDeviceRepository, IExcelParser, etc.
│       │
│       ├── use_cases/
│       │   ├── __init__.py
│       │   ├── process_excel.py
│       │   ├── get_options.py
│       │   ├── apply_assignments.py
│       │   └── sync_and_report.py
│       │
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── postgres_device_repo.py
│       │   ├── postgres_subscription_repo.py
│       │   ├── glp_device_manager_adapter.py
│       │   └── openpyxl_parser.py
│       │
│       └── api/
│           ├── __init__.py
│           ├── router.py         # FastAPI routes
│           └── schemas.py        # Pydantic models
│
├── app.py                        # FastAPI app entry point
└── ...
```

---

## Key Design Decisions

### 1. Region = Application ID (1:1 Mapping)
- User sees: "US West", "EU Central"
- System stores: Application UUID
- The DeviceManager.assign_application() uses the UUID

### 2. Intelligent Patching
- Only patch what's missing
- Device has subscription but no application → only PATCH application
- Device has both → no PATCH needed

### 3. Batching for API Limits
- Max 25 devices per PATCH
- Group by same subscription/application for efficient batching

### 4. Async Operation Handling
- Use DeviceManager.wait_for_completion() for async ops
- Show progress in UI via SSE or polling

### 5. Report Generation
- After sync, compare expected vs actual state
- Flag any failures for retry

---

## Implementation Steps

### Phase 1: Domain & Use Cases
1. Create `src/glp/assignment/domain/entities.py`
2. Create `src/glp/assignment/domain/ports.py`
3. Implement use cases in `src/glp/assignment/use_cases/`

### Phase 2: Adapters
1. `postgres_device_repo.py` - Query devices from DB
2. `postgres_subscription_repo.py` - Query available subscriptions
3. `glp_device_manager_adapter.py` - Wrap existing DeviceManager
4. `openpyxl_parser.py` - Parse Excel files

### Phase 3: API Layer
1. Create FastAPI router with endpoints
2. Create Pydantic schemas for request/response
3. Wire up dependency injection

### Phase 4: React Frontend
1. Set up React project with TypeScript
2. Implement components (FileUpload, DeviceTable, etc.)
3. Create API client
4. Build main workflow page

### Phase 5: Integration & Testing
1. Integration tests for use cases
2. E2E tests for API
3. Frontend unit tests

---

## Dependencies

### Backend
- `openpyxl` - Excel parsing
- `fastapi` - API framework
- `pydantic` - Request/response validation
- `asyncpg` - Existing, for DB queries

### Frontend
- `react` - UI framework
- `typescript` - Type safety
- `tanstack-query` - Data fetching
- `tailwindcss` - Styling
- `react-dropzone` - File upload
- `react-table` - Device table

---

## Example Excel Format

| Serial Number | MAC Address       |
|---------------|-------------------|
| SN12345       | 00:1B:44:11:3A:B7 |
| SN67890       |                   |
| SN11111       | AA:BB:CC:DD:EE:FF |

- Serial Number: Required
- MAC Address: Required for NETWORK devices, optional for others
