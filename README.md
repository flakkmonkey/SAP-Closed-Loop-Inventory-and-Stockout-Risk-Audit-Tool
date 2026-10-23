# SAP-Closed-Loop-Inventory-and-Stockout-Risk-Audit-Tool
SAP Closed-Loop Inventory & Stockout Risk Audit Tool
A Python-based data integration and analytics tool designed to process local SAP HTML/MHTML exports (⁠MB52⁠ inventory snapshots and ⁠MB51⁠ movement logs). The tool calculates projected ending stock balances using a net movement model, categorizes SAP movement types, flags high-risk stockouts, normalizes unit-of-measure discrepancies (such as liquids, wires, and extrusions), and generates an interactive, searchable HTML reporting dashboard.
Key Features
Business Context & SAP Movement Types
The tool categorizes raw SAP transaction codes into meaningful operational flow metrics:
Movement Code
Operational Category
Flow Classification
101
Vendor Receipt (Warehouse)
Inflow (+)
261 / Z61
Production Order Consumption (CE)
Outflow (-)
221 / 201
Product Development / Project Issue (CE)
Outflow (-)
551
Standard Operational Scrap
Outflow (-)
311
Internal Staging / Location Transfer
Ignored (Net Zero)

File Structure & Dependencies
Prerequisites
Directory Structure
Configuration & Usage
1. Preparing SAP Exports
1. MB52 (Starting Inventory): Export your inventory snapshot at the beginning of the audit period as an HTML/MHTML document.
2. MB51 (Transaction Log): Export all movement logs for the target date range as an HTML/MHTML document. Ensure columns for ⁠Material⁠, ⁠Movement Type⁠, and ⁠Qty in Un. of Entry⁠ are present.
2. Optional: Unit Conversions (⁠conversions.txt⁠)
To automatically convert alternative entry units (e.g., cases, yards, gallons) into base units for continuous materials (liquids, wires, extrusions), create a ⁠conversions.txt⁠ file in the working directory formatted as follows:
3. Execution
Run the script from your terminal:
1. Prompt 1: Confirm or enter the filename for the ⁠MB52⁠ snapshot.
2. Prompt 2: Confirm or enter the filename for the ⁠MB51⁠ movement log.
3. Prompt 3: Select a scope from the dynamically discovered ⁠.txt⁠ line files or choose ⁠Plant-Wide⁠.
Upon completion, the script automatically launches ⁠inventory_dashboard.html⁠ in your default browser and exports ⁠component_flow_analysis.csv⁠ for further analysis.
Dashboard Interactivity
￼ Exceptions Toggle: Click "Switch to Exceptions Only" to instantly filter out healthy stock levels and isolate critical red and yellow inventory risk items.
￼ Search Bar: Type any part number or unit of measure to filter table records in real time.
￼ Column Sorting: Click any column header to sort ascending or descending (supports numeric and alphanumeric sorting).