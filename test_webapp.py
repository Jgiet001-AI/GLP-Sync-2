"""Comprehensive web application testing script for GreenLake Sync frontend."""
import os
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = "/tmp/glp_screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def test_dashboard(page):
    """Test Dashboard page interactivity."""
    print("\n=== Testing Dashboard ===")
    page.goto("http://localhost:3000/")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=f"{SCREENSHOTS_DIR}/01_dashboard_initial.png", full_page=True)
    print(f"Screenshot: {SCREENSHOTS_DIR}/01_dashboard_initial.png")

    # Check KPI cards
    kpi_cards = page.locator('[class*="rounded-xl"]').all()
    print(f"Found {len(kpi_cards)} card elements")

    # Check for refresh button
    refresh_btn = page.locator('button:has-text("Refresh")')
    if refresh_btn.count() > 0:
        print("Found refresh button - clicking...")
        refresh_btn.first.click()
        page.wait_for_timeout(2000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/02_dashboard_after_refresh.png", full_page=True)
        print(f"Screenshot after refresh: {SCREENSHOTS_DIR}/02_dashboard_after_refresh.png")

    # Check navigation links
    nav_links = page.locator('nav a, header a').all()
    print(f"Navigation links found: {len(nav_links)}")
    for link in nav_links[:5]:
        text = link.text_content().strip()
        href = link.get_attribute('href')
        print(f"  - '{text}' -> {href}")

def test_devices_page(page):
    """Test Devices list page with filtering and sorting."""
    print("\n=== Testing Devices Page ===")
    page.goto("http://localhost:3000/devices")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    page.screenshot(path=f"{SCREENSHOTS_DIR}/03_devices_initial.png", full_page=True)
    print(f"Screenshot: {SCREENSHOTS_DIR}/03_devices_initial.png")

    # Test search functionality
    search_input = page.locator('input[placeholder*="Search"]')
    if search_input.count() > 0:
        print("Testing search...")
        search_input.first.fill("AP")
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/04_devices_search.png", full_page=True)
        print(f"Screenshot after search: {SCREENSHOTS_DIR}/04_devices_search.png")
        search_input.first.clear()

    # Test filter toggle
    filter_btn = page.locator('button:has-text("Filters"), button:has-text("Filter")')
    if filter_btn.count() > 0:
        print("Opening filters...")
        filter_btn.first.click()
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/05_devices_filters_open.png", full_page=True)
        print(f"Screenshot with filters: {SCREENSHOTS_DIR}/05_devices_filters_open.png")

    # Test sorting by clicking column headers
    sortable_headers = page.locator('th button, thead button').all()
    if sortable_headers:
        print(f"Found {len(sortable_headers)} sortable headers")
        if len(sortable_headers) > 0:
            sortable_headers[0].click()
            page.wait_for_timeout(500)
            page.screenshot(path=f"{SCREENSHOTS_DIR}/06_devices_sorted.png", full_page=True)
            print(f"Screenshot after sorting: {SCREENSHOTS_DIR}/06_devices_sorted.png")

    # Check pagination
    pagination = page.locator('button:has-text("Next"), button:has-text(">")')
    if pagination.count() > 0:
        print("Pagination controls found")

    # Count table rows
    rows = page.locator('tbody tr').all()
    print(f"Table rows displayed: {len(rows)}")

def test_subscriptions_page(page):
    """Test Subscriptions list page."""
    print("\n=== Testing Subscriptions Page ===")
    page.goto("http://localhost:3000/subscriptions")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    page.screenshot(path=f"{SCREENSHOTS_DIR}/07_subscriptions_initial.png", full_page=True)
    print(f"Screenshot: {SCREENSHOTS_DIR}/07_subscriptions_initial.png")

    # Test search
    search_input = page.locator('input[placeholder*="Search"]')
    if search_input.count() > 0:
        print("Testing search...")
        search_input.first.fill("CENTRAL")
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/08_subscriptions_search.png", full_page=True)
        print(f"Screenshot after search: {SCREENSHOTS_DIR}/08_subscriptions_search.png")

    # Check utilization bars
    progress_bars = page.locator('[role="progressbar"], .bg-violet-500, .bg-amber-500').all()
    print(f"Utilization indicators found: {len(progress_bars)}")

    # Count rows
    rows = page.locator('tbody tr').all()
    print(f"Subscription rows: {len(rows)}")

def test_assignment_page(page):
    """Test Assignment workflow page."""
    print("\n=== Testing Assignment Page ===")
    page.goto("http://localhost:3000/assignment")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    page.screenshot(path=f"{SCREENSHOTS_DIR}/09_assignment_initial.png", full_page=True)
    print(f"Screenshot: {SCREENSHOTS_DIR}/09_assignment_initial.png")

    # Check workflow steps indicator
    steps = page.locator('[class*="step"], [class*="workflow"]').all()
    print(f"Workflow step elements: {len(steps)}")

    # Check file upload zone
    dropzone = page.locator('[class*="dropzone"], [class*="upload"], input[type="file"]')
    if dropzone.count() > 0:
        print("File upload zone found")

    # Look for action buttons
    buttons = page.locator('button').all()
    print(f"Action buttons on assignment page: {len(buttons)}")
    for btn in buttons[:5]:
        text = btn.text_content().strip()
        if text:
            print(f"  - Button: '{text}'")

def test_navigation_flow(page):
    """Test navigation between pages."""
    print("\n=== Testing Navigation Flow ===")

    # Start at Dashboard
    page.goto("http://localhost:3000/")
    page.wait_for_load_state("networkidle")

    # Click on Devices nav link
    devices_link = page.locator('a[href="/devices"], a:has-text("Devices")')
    if devices_link.count() > 0:
        print("Navigating to Devices...")
        devices_link.first.click()
        page.wait_for_load_state("networkidle")
        assert page.url.endswith("/devices"), f"Expected /devices URL, got {page.url}"
        print(f"  URL: {page.url} ✓")

    # Click on Subscriptions nav link
    subs_link = page.locator('a[href="/subscriptions"], a:has-text("Subscriptions")')
    if subs_link.count() > 0:
        print("Navigating to Subscriptions...")
        subs_link.first.click()
        page.wait_for_load_state("networkidle")
        assert page.url.endswith("/subscriptions"), f"Expected /subscriptions URL, got {page.url}"
        print(f"  URL: {page.url} ✓")

    # Click on Assignment nav link
    assign_link = page.locator('a[href="/assignment"], a:has-text("Assignment")')
    if assign_link.count() > 0:
        print("Navigating to Assignment...")
        assign_link.first.click()
        page.wait_for_load_state("networkidle")
        assert page.url.endswith("/assignment"), f"Expected /assignment URL, got {page.url}"
        print(f"  URL: {page.url} ✓")

    # Return to Dashboard
    home_link = page.locator('a[href="/"], a:has-text("Dashboard")')
    if home_link.count() > 0:
        print("Navigating back to Dashboard...")
        home_link.first.click()
        page.wait_for_load_state("networkidle")
        print(f"  URL: {page.url} ✓")

def analyze_interactivity(page):
    """Analyze interactive elements across pages."""
    print("\n=== Interactivity Analysis ===")

    all_interactions = {
        "Dashboard": [],
        "Devices": [],
        "Subscriptions": [],
        "Assignment": []
    }

    pages_to_check = [
        ("/", "Dashboard"),
        ("/devices", "Devices"),
        ("/subscriptions", "Subscriptions"),
        ("/assignment", "Assignment")
    ]

    for path, name in pages_to_check:
        page.goto(f"http://localhost:3000{path}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Count interactive elements
        buttons = page.locator('button').count()
        links = page.locator('a').count()
        inputs = page.locator('input').count()
        selects = page.locator('select').count()
        checkboxes = page.locator('input[type="checkbox"]').count()

        all_interactions[name] = {
            "buttons": buttons,
            "links": links,
            "inputs": inputs,
            "selects": selects,
            "checkboxes": checkboxes
        }

        print(f"\n{name}:")
        print(f"  Buttons: {buttons}")
        print(f"  Links: {links}")
        print(f"  Inputs: {inputs}")
        print(f"  Selects: {selects}")
        print(f"  Checkboxes: {checkboxes}")

    return all_interactions

def main():
    print("=" * 60)
    print("GreenLake Sync Frontend - Comprehensive Testing")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        try:
            # Run all tests
            test_dashboard(page)
            test_devices_page(page)
            test_subscriptions_page(page)
            test_assignment_page(page)
            test_navigation_flow(page)
            interactions = analyze_interactivity(page)

            print("\n" + "=" * 60)
            print("Testing Complete!")
            print("=" * 60)
            print(f"\nScreenshots saved to: {SCREENSHOTS_DIR}")
            print("\nInteractive Elements Summary:")
            total_buttons = sum(i["buttons"] for i in interactions.values())
            total_inputs = sum(i["inputs"] for i in interactions.values())
            print(f"  Total buttons across all pages: {total_buttons}")
            print(f"  Total input fields: {total_inputs}")

        except Exception as e:
            print(f"\nError during testing: {e}")
            page.screenshot(path=f"{SCREENSHOTS_DIR}/error_screenshot.png", full_page=True)
            raise
        finally:
            browser.close()

if __name__ == "__main__":
    main()
