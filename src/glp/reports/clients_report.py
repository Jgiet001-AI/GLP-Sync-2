"""Client network report generator.

Generates comprehensive network client reports with:
- Client health and connectivity status
- Site-level statistics
- Network segmentation analysis
- Connection details
"""

import logging
from typing import Any

from openpyxl.styles import Font

from .generator import BaseReportGenerator

logger = logging.getLogger(__name__)


class ClientsReportGenerator(BaseReportGenerator):
    """Generate detailed network client reports."""

    CLIENT_COLUMNS = [
        ("mac", "MAC Address"),
        ("name", "Client Name"),
        ("site_name", "Site"),
        ("health", "Health"),
        ("status", "Status"),
        ("type", "Type"),
        ("ipv4", "IPv4"),
        ("ipv6", "IPv6"),
        ("network", "Network/SSID"),
        ("vlan_id", "VLAN"),
        ("port", "Port"),
        ("connected_to", "Connected To"),
        ("connected_since", "Connected Since"),
        ("last_seen_at", "Last Seen"),
        ("authentication", "Authentication"),
        ("key_management", "Key Management"),
    ]

    def generate_excel(
        self,
        data: dict[str, Any],
        filters: dict[str, Any] | None = None,
    ) -> bytes:
        """Generate multi-sheet client network Excel report.

        Sheets:
        1. Summary - Health and connectivity overview
        2. Client List - Full client inventory
        3. Site Statistics - Per-site breakdown
        4. Network Analysis - VLAN and SSID distribution
        """
        wb = self.create_workbook()

        items = data.get("items", [])
        total = data.get("total", len(items))
        summary = data.get("summary", {})

        # Sheet 1: Summary
        ws_summary = wb.active
        ws_summary.title = "Summary"
        self._create_summary_sheet(ws_summary, items, total, summary, filters)

        # Sheet 2: Client List
        ws_clients = wb.create_sheet("Client List")
        self._create_client_list_sheet(ws_clients, items)

        # Sheet 3: Site Statistics
        ws_sites = wb.create_sheet("Site Statistics")
        self._create_site_stats_sheet(ws_sites, items)

        # Sheet 4: Network Analysis
        ws_network = wb.create_sheet("Network Analysis")
        self._create_network_analysis_sheet(ws_network, items)

        return self._workbook_to_bytes(wb)

    def generate_csv(
        self,
        data: dict[str, Any],
        filters: dict[str, Any] | None = None,
    ) -> str:
        """Generate CSV with client data."""
        items = data.get("items", [])

        rows = []
        for item in items:
            row = {field: item.get(field, "") for field, _ in self.CLIENT_COLUMNS}
            rows.append(row)

        fieldnames = [field for field, _ in self.CLIENT_COLUMNS]
        return self._dict_to_csv(rows, fieldnames)

    def _create_summary_sheet(
        self,
        ws,
        items: list[dict],
        total: int,
        summary: dict[str, Any],
        filters: dict[str, Any] | None,
    ) -> None:
        """Create summary sheet with health KPIs."""
        row = self.add_report_header(
            ws,
            "Network Clients Report",
            f"{total:,} Clients",
            filters,
        )

        # Calculate stats if not provided
        if not summary:
            summary = {
                "total_clients": len(items),
                "connected": sum(1 for c in items if c.get("status") == "Connected"),
                "wired": sum(1 for c in items if c.get("type") == "Wired"),
                "wireless": sum(1 for c in items if c.get("type") == "Wireless"),
                "health_good": sum(1 for c in items if c.get("health") == "Good"),
                "health_fair": sum(1 for c in items if c.get("health") == "Fair"),
                "health_poor": sum(1 for c in items if c.get("health") == "Poor"),
            }

        # KPIs
        ws.cell(row=row, column=1, value="Client Overview")
        ws.cell(row=row, column=1).font = self.styles.get_subtitle_font()
        row += 2

        total_clients = summary.get("total_clients", len(items)) or 1
        connected = summary.get("connected", 0)
        conn_pct = f"{(connected / total_clients * 100):.1f}%"

        kpi_data = [
            ("Total Clients", total_clients, None),
            ("Connected", connected, conn_pct),
            ("Wireless", summary.get("wireless", 0), None),
            ("Wired", summary.get("wired", 0), None),
        ]

        col = 1
        kpi_row = row
        for label, value, subtitle in kpi_data:
            self.add_kpi_card(ws, kpi_row, col, label, value, subtitle)
            col += 2

        row = kpi_row + 6

        # Health breakdown
        ws.cell(row=row, column=1, value="Health Distribution")
        ws.cell(row=row, column=1).font = self.styles.get_subtitle_font()
        row += 2

        health_data = [
            ("Good", summary.get("health_good", 0), "success"),
            ("Fair", summary.get("health_fair", 0), "warning"),
            ("Poor", summary.get("health_poor", 0), "error"),
            ("Unknown", summary.get("health_unknown", 0), "info"),
        ]

        headers = ["Health Status", "Count", "Percentage"]
        self.add_table_headers(ws, headers, row)
        row += 1

        for health, count, status_type in health_data:
            pct = f"{(count / total_clients * 100):.1f}%"
            self.add_data_row(ws, [health, count, pct], row, alternate=(row % 2 == 0))

            if status_type == "success":
                ws.cell(row=row, column=1).fill = self.styles.get_success_fill()
            elif status_type == "warning":
                ws.cell(row=row, column=1).fill = self.styles.get_warning_fill()
            elif status_type == "error":
                ws.cell(row=row, column=1).fill = self.styles.get_error_fill()

            row += 1

        row += 2

        # Status breakdown
        ws.cell(row=row, column=1, value="Connection Status")
        ws.cell(row=row, column=1).font = self.styles.get_subtitle_font()
        row += 2

        status_counts: dict[str, int] = {}
        for item in items:
            status = item.get("status", "Unknown") or "Unknown"
            status_counts[status] = status_counts.get(status, 0) + 1

        headers = ["Status", "Count", "Percentage"]
        self.add_table_headers(ws, headers, row)
        row += 1

        for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
            pct = f"{(count / total_clients * 100):.1f}%"
            self.add_data_row(ws, [status, count, pct], row, alternate=(row % 2 == 0))
            ws.cell(row=row, column=1).fill = self.styles.get_status_fill(status)
            row += 1

        self.auto_fit_columns(ws)
        self.freeze_panes(ws, row=8)

    def _create_client_list_sheet(self, ws, items: list[dict]) -> None:
        """Create the main client list sheet."""
        row = 1

        headers = [label for _, label in self.CLIENT_COLUMNS]
        self.add_table_headers(ws, headers, row)
        row += 1

        for item in items:
            row_data = [item.get(field, "") for field, _ in self.CLIENT_COLUMNS]
            self.add_data_row(ws, row_data, row, alternate=(row % 2 == 0))

            # Color code health
            health = item.get("health")
            if health:
                ws.cell(row=row, column=4).fill = self.styles.get_status_fill(health)

            # Color code status
            status = item.get("status")
            if status:
                ws.cell(row=row, column=5).fill = self.styles.get_status_fill(status)

            row += 1

        self.auto_fit_columns(ws, max_width=35)
        self.freeze_panes(ws, row=2)

    def _create_site_stats_sheet(self, ws, items: list[dict]) -> None:
        """Create per-site statistics sheet."""
        row = self.add_report_header(
            ws,
            "Site Statistics",
            "Client Distribution by Site",
        )

        # Aggregate by site
        site_stats: dict[str, dict] = {}
        for item in items:
            site = item.get("site_name", "Unknown") or "Unknown"
            if site not in site_stats:
                site_stats[site] = {
                    "total": 0,
                    "connected": 0,
                    "wireless": 0,
                    "wired": 0,
                    "good": 0,
                    "fair": 0,
                    "poor": 0,
                }
            site_stats[site]["total"] += 1
            if item.get("status") == "Connected":
                site_stats[site]["connected"] += 1
            if item.get("type") == "Wireless":
                site_stats[site]["wireless"] += 1
            elif item.get("type") == "Wired":
                site_stats[site]["wired"] += 1
            health = item.get("health", "").lower()
            if health in site_stats[site]:
                site_stats[site][health] += 1

        headers = [
            "Site",
            "Total Clients",
            "Connected",
            "Wireless",
            "Wired",
            "Health Good",
            "Health Fair",
            "Health Poor",
        ]
        self.add_table_headers(ws, headers, row)
        row += 1

        for site, stats in sorted(site_stats.items(), key=lambda x: -x[1]["total"]):
            self.add_data_row(
                ws,
                [
                    site,
                    stats["total"],
                    stats["connected"],
                    stats["wireless"],
                    stats["wired"],
                    stats["good"],
                    stats["fair"],
                    stats["poor"],
                ],
                row,
                alternate=(row % 2 == 0),
            )

            # Highlight poor health sites
            if stats["poor"] > 0:
                ws.cell(row=row, column=8).fill = self.styles.get_error_fill()

            row += 1

        self.auto_fit_columns(ws)
        self.freeze_panes(ws, row=6)

    def _create_network_analysis_sheet(self, ws, items: list[dict]) -> None:
        """Create network segmentation analysis sheet."""
        row = self.add_report_header(
            ws,
            "Network Analysis",
            "VLAN and Network Distribution",
        )

        # VLAN breakdown
        ws.cell(row=row, column=1, value="VLAN Distribution")
        ws.cell(row=row, column=1).font = self.styles.get_subtitle_font()
        row += 2

        vlan_counts: dict[str, int] = {}
        for item in items:
            vlan = item.get("vlan_id", "Unknown") or "Unknown"
            vlan_counts[str(vlan)] = vlan_counts.get(str(vlan), 0) + 1

        headers = ["VLAN", "Client Count", "Percentage"]
        self.add_table_headers(ws, headers, row)
        row += 1

        total_items = max(len(items), 1)
        for vlan, count in sorted(vlan_counts.items(), key=lambda x: -x[1])[:20]:
            pct = f"{(count / total_items * 100):.1f}%"
            self.add_data_row(ws, [vlan, count, pct], row, alternate=(row % 2 == 0))
            row += 1

        if len(vlan_counts) > 20:
            ws.cell(row=row, column=1, value=f"... and {len(vlan_counts) - 20} more VLANs")
            ws.cell(row=row, column=1).font = Font(italic=True)
            row += 1

        row += 2

        # Network/SSID breakdown (for wireless)
        ws.cell(row=row, column=1, value="Wireless Network (SSID) Distribution")
        ws.cell(row=row, column=1).font = self.styles.get_subtitle_font()
        row += 2

        network_counts: dict[str, int] = {}
        for item in items:
            if item.get("type") == "Wireless":
                network = item.get("network", "Unknown") or "Unknown"
                network_counts[network] = network_counts.get(network, 0) + 1

        if network_counts:
            headers = ["Network/SSID", "Client Count", "Percentage"]
            self.add_table_headers(ws, headers, row)
            row += 1

            wireless_total = max(sum(network_counts.values()), 1)
            for network, count in sorted(network_counts.items(), key=lambda x: -x[1])[:15]:
                pct = f"{(count / wireless_total * 100):.1f}%"
                self.add_data_row(ws, [network, count, pct], row, alternate=(row % 2 == 0))
                row += 1
        else:
            ws.cell(row=row, column=1, value="No wireless clients found.")
            ws.cell(row=row, column=1).font = Font(italic=True)

        self.auto_fit_columns(ws)
        self.freeze_panes(ws, row=6)
