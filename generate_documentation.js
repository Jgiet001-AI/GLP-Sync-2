const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, LevelFormat, HeadingLevel, BorderStyle,
        WidthType, ShadingType, VerticalAlign, PageNumber, TableOfContents, PageBreak } = require('docx');
const fs = require('fs');

// Define colors
const colors = {
  primary: "1E40AF",      // Deep Blue
  secondary: "6B7280",    // Gray
  accent: "059669",       // Green
  black: "000000",
  white: "FFFFFF",
  lightGray: "F3F4F6",
  lightBlue: "DBEAFE",
  lightGreen: "D1FAE5"
};

// Table borders
const tableBorder = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const cellBorders = { top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder };

// Create the document
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal",
        run: { size: 56, bold: true, color: colors.primary, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 120 }, alignment: AlignmentType.CENTER } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, color: colors.primary, font: "Arial" },
        paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, color: colors.black, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: colors.secondary, font: "Arial" },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 2 } },
      { id: "Code", name: "Code", basedOn: "Normal",
        run: { font: "Courier New", size: 18, color: "334155" },
        paragraph: { spacing: { before: 60, after: 60 } } }
    ]
  },
  numbering: {
    config: [
      { reference: "bullet-list",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "\u25E6", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 1080, hanging: 360 } } } }] },
      { reference: "features-list",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "workflow-list",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "setup-list",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "api-list",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }
    ]
  },
  sections: [{
    properties: {
      page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } }
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: "HPE GreenLake Device Sync - Technical Documentation", italics: true, size: 18, color: colors.secondary })]
      })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "Page ", size: 18 }), new TextRun({ children: [PageNumber.CURRENT], size: 18 }), new TextRun({ text: " of ", size: 18 }), new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18 })]
      })] })
    },
    children: [
      // TITLE PAGE
      new Paragraph({ spacing: { before: 2000 } }),
      new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("HPE GreenLake")] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
        children: [new TextRun({ text: "Device & Subscription Sync Platform", size: 36, color: colors.secondary })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400, after: 400 },
        children: [new TextRun({ text: "Technical Documentation & Developer Guide", size: 28 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 800 },
        children: [new TextRun({ text: "Version 1.0", size: 22, color: colors.secondary })] }),
      new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }), size: 22, color: colors.secondary })] }),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // TABLE OF CONTENTS
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Table of Contents")] }),
      new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 1: EXECUTIVE SUMMARY
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("1. Executive Summary")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("The HPE GreenLake Device & Subscription Sync Platform is a production-grade enterprise solution for synchronizing device and subscription inventory from the HPE GreenLake Platform API to a PostgreSQL database. The system features OAuth2 authentication, automated scheduling, a React-based web UI for bulk operations, and comprehensive resilience patterns.")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("1.1 Key Capabilities")] }),
      new Paragraph({ numbering: { reference: "features-list", level: 0 }, children: [new TextRun("Automated synchronization of 45,000+ devices in under 4 minutes")] }),
      new Paragraph({ numbering: { reference: "features-list", level: 0 }, children: [new TextRun("Real-time web UI for bulk device assignment operations")] }),
      new Paragraph({ numbering: { reference: "features-list", level: 0 }, children: [new TextRun("Circuit breaker pattern for API resilience")] }),
      new Paragraph({ numbering: { reference: "features-list", level: 0 }, children: [new TextRun("Full-text search with PostgreSQL tsvector indexing")] }),
      new Paragraph({ numbering: { reference: "features-list", level: 0 }, children: [new TextRun("Multi-platform support: GreenLake and Aruba Central")] }),
      new Paragraph({ numbering: { reference: "features-list", level: 0 }, children: [new TextRun("Clean Architecture design with dependency injection")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("1.2 Technology Stack")] }),
      new Table({
        columnWidths: [3120, 6240],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Layer", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Technologies", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Backend")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Python 3.11+, FastAPI, aiohttp, asyncpg, pydantic")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Frontend")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("React 18+, TypeScript, TanStack Router/Query, Tailwind CSS")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Database")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("PostgreSQL 16+, pg_trgm, uuid-ossp")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Infrastructure")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Docker, Docker Compose, nginx, Redis")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Testing")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("pytest, pytest-asyncio, httpx, 49+ tests")] })] })
          ]})
        ]
      }),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 2: ARCHITECTURE
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("2. System Architecture")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("2.1 High-Level Architecture")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("The system follows Clean Architecture principles with clear separation between layers:")
      ]}),

      new Paragraph({ style: "Code", spacing: { before: 120, after: 120 }, children: [new TextRun("GreenLake API")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      |")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      v")] }),
      new Paragraph({ style: "Code", children: [new TextRun("TokenManager (OAuth2 - auto-refresh with 5-min buffer)")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      |")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      v")] }),
      new Paragraph({ style: "Code", children: [new TextRun("GLPClient (HTTP layer - pagination, rate limits, retries)")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      |")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      +-----------------+")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      v                 v")] }),
      new Paragraph({ style: "Code", children: [new TextRun("DeviceSyncer    SubscriptionSyncer")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      |                 |")] }),
      new Paragraph({ style: "Code", children: [new TextRun("      +--------+--------+")] }),
      new Paragraph({ style: "Code", children: [new TextRun("               v")] }),
      new Paragraph({ style: "Code", spacing: { after: 200 }, children: [new TextRun("          PostgreSQL")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("2.2 Clean Architecture Layers")] }),
      new Table({
        columnWidths: [2340, 3510, 3510],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Layer", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Responsibility", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Key Components", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightGreen, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Domain", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Pure business entities and interfaces")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Device, Subscription, DeviceAssignment")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightGreen, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Use Cases", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Business logic orchestration")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("SyncDevices, ApplyAssignments")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightGreen, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Adapters", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("External system integration")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("PostgresRepo, GLPDeviceAPI, ExcelParser")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightGreen, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "API", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("HTTP endpoints and schemas")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("FastAPI routers, Pydantic models")] })] })
          ]})
        ]
      }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("2.3 Key Design Decisions")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Pagination Strategy: ", bold: true }), new TextRun("Devices use 2000/page, Subscriptions use 50/page for optimal memory usage")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Rate Limiting: ", bold: true }), new TextRun("Sequential processing with guaranteed intervals (PATCH: 3.5s, POST: 2.6s)")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Circuit Breaker: ", bold: true }), new TextRun("Prevents cascading failures with 5-failure threshold and 60-second timeout")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "JSONB Storage: ", bold: true }), new TextRun("Full API responses stored alongside normalized columns for flexibility")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Async Everywhere: ", bold: true }), new TextRun("All I/O operations use asyncio for non-blocking execution")
      ]}),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 3: CORE COMPONENTS
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("3. Core Components")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("3.1 TokenManager (OAuth2 Authentication)")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun({ text: "Location: ", bold: true }), new TextRun("src/glp/api/auth.py")
      ]}),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("Provides secure, thread-safe OAuth2 token management using the client credentials grant flow.")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Key Features")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [new TextRun("Automatic token caching with 5-minute expiration buffer")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [new TextRun("Thread-safe token refresh using asyncio.Lock")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [new TextRun("Exponential backoff retry on failures (1s, 2s, 4s)")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [new TextRun("Transparent token refresh on 401 responses")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Usage Example")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100, after: 100 }, children: [new TextRun("manager = TokenManager()")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("token = await manager.get_token()  # Fetches or returns cached")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { after: 200 }, children: [new TextRun("manager.invalidate()  # Force refresh on next call")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("3.2 GLPClient (HTTP Layer)")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun({ text: "Location: ", bold: true }), new TextRun("src/glp/api/client.py")
      ]}),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("Generic HTTP client handling authentication, pagination, rate limiting, and circuit breaker patterns.")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Capabilities")] }),
      new Table({
        columnWidths: [3120, 6240],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Feature", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Description", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Pagination")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Automatic offset-based pagination with configurable page sizes")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Rate Limiting")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Handles 429 responses with Retry-After header parsing")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Circuit Breaker")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Fails fast after 5 consecutive failures, recovers after 60s")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Error Handling")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Typed exceptions with exponential backoff retries")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Connection Pooling")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 6240, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Shared aiohttp session with 10 concurrent connections")] })] })
          ]})
        ]
      }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("3.3 DeviceSyncer")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun({ text: "Location: ", bold: true }), new TextRun("src/glp/api/devices.py")
      ]}),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("High-performance device inventory synchronization with optimized bulk database operations.")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Performance Optimizations")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "UPSERT: ", bold: true }), new TextRun("Uses INSERT ON CONFLICT to eliminate N SELECT queries")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Bulk DELETE: ", bold: true }), new TextRun("Single query with ANY() for all device IDs")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "executemany(): ", bold: true }), new TextRun("Batched inserts for subscriptions and tags")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Result: ", bold: true }), new TextRun("~47,000 queries reduced to ~5 queries for 11,000 devices")
      ]}),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 4: DATABASE SCHEMA
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("4. Database Schema")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("4.1 Core Tables")] }),
      new Table({
        columnWidths: [2340, 1560, 5460],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Table", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Columns", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5460, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Purpose", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: "devices", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("28")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5460, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Main device inventory with full-text search vector")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: "subscriptions", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("20")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5460, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("License and subscription inventory")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: "device_subscriptions", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("4")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5460, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Many-to-many junction table")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: "device_tags", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("4")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5460, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Key-value tags per device")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: "sync_history", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("9")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5460, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Audit log of sync operations")] })] })
          ]})
        ]
      }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("4.2 Key Indexes")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Full-text Search: ", bold: true }), new TextRun("GIN index on search_vector (serial, name, MAC, model, type)")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "JSONB Queries: ", bold: true }), new TextRun("GIN index with jsonb_path_ops on raw_data")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Exact Lookups: ", bold: true }), new TextRun("B-tree on serial_number, mac_address")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Filters: ", bold: true }), new TextRun("B-tree on device_type, region, assigned_state")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("4.3 Views")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "active_devices: ", bold: true }), new TextRun("Non-archived devices with subscriptions and tags")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "devices_expiring_soon: ", bold: true }), new TextRun("Devices with subscriptions expiring in 90 days")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "devices_with_subscriptions: ", bold: true }), new TextRun("Full join with subscription details")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "device_summary: ", bold: true }), new TextRun("Aggregated counts by type and region")
      ]}),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 5: DEVICE ASSIGNMENT
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("5. Device Assignment System")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("5.1 Workflow Overview")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("The device assignment system provides a web UI for bulk device operations using a 4-phase workflow:")
      ]}),

      new Paragraph({ numbering: { reference: "workflow-list", level: 0 }, children: [
        new TextRun({ text: "Upload: ", bold: true }), new TextRun("User drops Excel file with serials/MACs")
      ]}),
      new Paragraph({ numbering: { reference: "workflow-list", level: 0 }, children: [
        new TextRun({ text: "Review: ", bold: true }), new TextRun("System shows devices found in DB and their status")
      ]}),
      new Paragraph({ numbering: { reference: "workflow-list", level: 0 }, children: [
        new TextRun({ text: "Assign: ", bold: true }), new TextRun("User selects subscription, region, and tags")
      ]}),
      new Paragraph({ numbering: { reference: "workflow-list", level: 0 }, children: [
        new TextRun({ text: "Apply: ", bold: true }), new TextRun("Intelligent patching (only patches what's missing)")
      ]}),
      new Paragraph({ numbering: { reference: "workflow-list", level: 0 }, children: [
        new TextRun({ text: "Report: ", bold: true }), new TextRun("Resync with GreenLake and view summary")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("5.2 Rate Limiting Algorithm")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("The system uses a mathematically guaranteed rate limiting approach:")
      ]}),

      new Table({
        columnWidths: [2340, 2340, 2340, 2340],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Operation", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "API Limit", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Our Rate", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Interval", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("PATCH")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("20/min")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("17/min")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("3.5 seconds")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("POST")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("25/min")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("23/min")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("2.6 seconds")] })] })
          ]})
        ]
      }),

      new Paragraph({ spacing: { before: 200, after: 200 }, children: [
        new TextRun({ text: "Example for 308 devices: ", bold: true }), new TextRun("13 batches x 3.5s = ~42 seconds for applications + ~42 seconds for subscriptions = ~84 seconds total wait time")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("5.3 Assignment Constraints")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Application BEFORE Subscription: ", bold: true }), new TextRun("GreenLake requires application assignment before subscription")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Region Required: ", bold: true }), new TextRun("Both application_id AND region are required for application assignment")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Max Batch Size: ", bold: true }), new TextRun("25 devices per API call")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Fire-then-Poll: ", bold: true }), new TextRun("Sends all requests first, then polls for completion")
      ]}),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 6: API REFERENCE
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("6. API Reference")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("6.1 REST Endpoints")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Dashboard")] }),
      new Table({
        columnWidths: [1560, 3120, 4680],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Method", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Endpoint", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Description", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: colors.lightGreen, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun("GET")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("/api/dashboard/stats")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Get device/subscription statistics")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: colors.lightGreen, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun("GET")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("/api/devices")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("List devices (paginated, filterable)")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: colors.lightGreen, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun("GET")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("/api/subscriptions")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("List subscriptions")] })] })
          ]})
        ]
      }),

      new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 300 }, children: [new TextRun("Assignment")] }),
      new Table({
        columnWidths: [1560, 3120, 4680],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Method", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Endpoint", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Description", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: "FEF3C7", type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun("POST")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("/api/assignment/upload")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Upload Excel file for processing")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: colors.lightGreen, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun("GET")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("/api/assignment/options")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Get available subscriptions/regions")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: "FEF3C7", type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun("POST")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("/api/assignment/apply")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Apply assignments to devices")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 1560, type: WidthType.DXA }, shading: { fill: "FEF3C7", type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun("POST")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("/api/assignment/sync")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 4680, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Resync and generate report")] })] })
          ]})
        ]
      }),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 7: DEPLOYMENT
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("7. Deployment Guide")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("7.1 Environment Variables")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Required")] }),
      new Table({
        columnWidths: [3510, 5850],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Variable", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5850, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Description", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("GLP_CLIENT_ID")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5850, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("OAuth2 client ID")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("GLP_CLIENT_SECRET")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5850, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("OAuth2 client secret")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("GLP_TOKEN_URL")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5850, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("OAuth2 token endpoint")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("DATABASE_URL")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 5850, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("PostgreSQL connection string")] })] })
          ]})
        ]
      }),

      new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 300 }, children: [new TextRun("Optional")] }),
      new Table({
        columnWidths: [3510, 3510, 2340],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Variable", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Description", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Default", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("GLP_BASE_URL")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("API base URL")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("global.api...")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("SYNC_INTERVAL_MINUTES")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Scheduler interval")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("60")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("HEALTH_CHECK_PORT")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3510, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Health endpoint port")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2340, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("8080")] })] })
          ]})
        ]
      }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("7.2 Docker Commands")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100 }, children: [new TextRun("# Start full stack")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("docker compose up -d")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100 }, children: [new TextRun("# View logs")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("docker compose logs -f scheduler")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100 }, children: [new TextRun("# One-time sync")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("docker compose run --rm sync-once")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100 }, children: [new TextRun("# Stop and cleanup")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("docker compose down -v")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("7.3 Development Setup")] }),
      new Paragraph({ numbering: { reference: "setup-list", level: 0 }, children: [new TextRun("Install dependencies: "), new TextRun({ text: "uv sync", font: "Courier New" })] }),
      new Paragraph({ numbering: { reference: "setup-list", level: 0 }, children: [new TextRun("Start backend: "), new TextRun({ text: "uv run uvicorn src.glp.assignment.app:app --reload --port 8000", font: "Courier New" })] }),
      new Paragraph({ numbering: { reference: "setup-list", level: 0 }, children: [new TextRun("Start frontend: "), new TextRun({ text: "cd frontend && npm install && npm run dev", font: "Courier New" })] }),
      new Paragraph({ numbering: { reference: "setup-list", level: 0 }, children: [new TextRun("Run tests: "), new TextRun({ text: "uv run pytest tests/ -v", font: "Courier New" })] }),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 8: TESTING
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("8. Testing")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("8.1 Test Structure")] }),
      new Table({
        columnWidths: [3120, 3120, 3120],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Test Type", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Location", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Requirements", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Unit Tests")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("tests/test_*.py")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("None (uses mocks)")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Database Tests")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("tests/test_database.py")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("PostgreSQL")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Integration Tests")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("tests/assignment/")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("PostgreSQL")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Resilience Tests")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("tests/test_resilience.py")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("None")] })] })
          ]})
        ]
      }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("8.2 Running Tests")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100 }, children: [new TextRun("# All tests")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("uv run pytest tests/ -v")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100 }, children: [new TextRun("# Unit tests only (no DB)")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("uv run pytest tests/test_auth.py tests/test_devices.py -v")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100 }, children: [new TextRun("# Assignment module")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("uv run pytest tests/assignment/ -v")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("8.3 Test Coverage")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "OAuth2 Authentication: ", bold: true }), new TextRun("Token caching, refresh, error handling")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "HTTP Client: ", bold: true }), new TextRun("Pagination, retries, circuit breaker")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Device Syncer: ", bold: true }), new TextRun("Fetch, upsert, bulk operations")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Assignment Workflow: ", bold: true }), new TextRun("Excel parsing, validation, apply")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "Resilience: ", bold: true }), new TextRun("Circuit breaker states, backoff timing")
      ]}),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 9: PERFORMANCE
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("9. Performance Characteristics")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("9.1 Benchmarks")] }),
      new Table({
        columnWidths: [3900, 2730, 2730],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 3900, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Operation", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Scale", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Duration", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3900, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Device Sync")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("45,000 devices")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("~4 minutes")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3900, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Subscription Sync")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("500 subscriptions")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("~30 seconds")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3900, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("API Response (GET)")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("-")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("<100ms")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3900, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Full-text Search")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("-")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("<100ms")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3900, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Index Lookups")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("-")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2730, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("<50ms")] })] })
          ]})
        ]
      }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("9.2 Known Optimization Opportunities")] }),
      new Table({
        columnWidths: [3120, 3120, 3120],
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Issue", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Location", bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: colors.lightBlue, type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: "Potential Fix", bold: true })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Per-device transactions")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("devices.py:117")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Batch transactions")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("N+1 existence checks")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("sync_to_postgres()")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Use UPSERT (done)")] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("DELETE + INSERT tags")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ style: "Code", children: [new TextRun("_sync_tags()")] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3120, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun("Check before delete")] })] })
          ]})
        ]
      }),

      // PAGE BREAK
      new Paragraph({ children: [new PageBreak()] }),

      // SECTION 10: APPENDIX
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("10. Appendix")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("10.1 Source File Directory")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Core API (src/glp/api/)")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "auth.py", font: "Courier New" }), new TextRun(" - OAuth2 TokenManager with token caching")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "client.py", font: "Courier New" }), new TextRun(" - GLPClient with pagination, rate limiting, circuit breaker")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "devices.py", font: "Courier New" }), new TextRun(" - DeviceSyncer with bulk database operations")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "subscriptions.py", font: "Courier New" }), new TextRun(" - SubscriptionSyncer for license management")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "device_manager.py", font: "Courier New" }), new TextRun(" - Device write operations (PATCH/POST)")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "resilience.py", font: "Courier New" }), new TextRun(" - Circuit breaker and retry decorators")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Assignment Module (src/glp/assignment/)")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "domain/entities.py", font: "Courier New" }), new TextRun(" - DeviceAssignment, SubscriptionOption")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "adapters/excel_parser.py", font: "Courier New" }), new TextRun(" - Excel file parsing and validation")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "use_cases/apply_assignments.py", font: "Courier New" }), new TextRun(" - 4-phase assignment workflow")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "api/router.py", font: "Courier New" }), new TextRun(" - FastAPI REST endpoints")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Frontend (frontend/src/)")] }),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "pages/Dashboard.tsx", font: "Courier New" }), new TextRun(" - KPIs and statistics")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "pages/DeviceAssignment.tsx", font: "Courier New" }), new TextRun(" - 5-step assignment workflow")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "pages/DevicesList.tsx", font: "Courier New" }), new TextRun(" - Searchable device inventory")
      ]}),
      new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, children: [
        new TextRun({ text: "hooks/useAssignment.ts", font: "Courier New" }), new TextRun(" - Assignment form state management")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("10.2 CLI Commands Reference")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, spacing: { before: 100 }, children: [new TextRun("python main.py                      # Sync both")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("python main.py --devices           # Devices only")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("python main.py --subscriptions     # Subscriptions only")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("python main.py --json-only         # Export to JSON")] }),
      new Paragraph({ style: "Code", shading: { fill: colors.lightGray, type: ShadingType.CLEAR }, children: [new TextRun("python main.py --expiring-days 90  # Expiring subscriptions")] }),

      // FINAL SECTION
      new Paragraph({ spacing: { before: 600 } }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "--- End of Documentation ---", color: colors.secondary, size: 20 })] }),
    ]
  }]
});

// Generate and save the document
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("HPE_GreenLake_Device_Sync_Documentation.docx", buffer);
  console.log("Documentation generated: HPE_GreenLake_Device_Sync_Documentation.docx");
});
