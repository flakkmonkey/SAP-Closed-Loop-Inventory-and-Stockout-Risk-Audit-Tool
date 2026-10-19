"""
=============================================================================
Script Name: SAP Closed-Loop Inventory & Stockout Risk Audit Tool
Description: 
    This script processes local SAP HTML/MHTML exports (MB52 inventory snapshots 
    and MB51 transaction logs) to perform a closed-loop historical stock audit. 
    It calculates projected ending stock balances using a net movement model 
    (Starting Stock + Receipts - Outflows), categorizes movement types, 
    flags high-risk stockouts (red for missed orders, yellow for BOM/sizing 
    discrepancies), dynamically auto-scans the folder for any production line 
    or validation build text files, features an instant "Exceptions Only" 
    view toggle, live search filtering, clickable column sorting, and 
    robust error handling for standalone executable deployments.
=============================================================================
"""

# Import BeautifulSoup to parse HTML/MHTML exports exported from SAP
from bs4 import BeautifulSoup
# Import Pandas for data manipulation, cleaning, pivoting, and merging
import pandas as pd
# Import datetime to generate timestamps for the report header
import datetime
# Import io to wrap string HTML data into a file-like stream for Pandas read_html
import io
# Import webbrowser to automatically launch the generated HTML report in the default browser
import webbrowser
# Import os to check file paths and resolve absolute paths locally
import os
# Import glob to automatically scan directories for text files
import glob

# Print a welcome banner to the terminal console
print("=== SAP Closed-Loop Inventory Audit Tool ===")

# --- DYNAMIC FILE PROMPTS WITH EXISTENCE CHECKS ---
default_mb52 = 'september_stock.mhtml'
default_mb51 = 'september_log.mhtml'

# Prompt for MB52 snapshot filename with validation loop
while True:
    mb52_input = input(f"Enter MB52 inventory snapshot filename [default: {default_mb52}]: ").strip()
    MB52_FILENAME = mb52_input if mb52_input else default_mb52
    if os.path.exists(MB52_FILENAME):
        break
    print(f"-> Error: File '{MB52_FILENAME}' not found in current directory. Please check the name and try again.")

# Prompt for MB51 log filename with validation loop
while True:
    mb51_input = input(f"Enter MB51 transaction log filename [default: {default_mb51}]: ").strip()
    MB51_FILENAME = mb51_input if mb51_input else default_mb51
    if os.path.exists(MB51_FILENAME):
        break
    print(f"-> Error: File '{MB51_FILENAME}' not found in current directory. Please check the name and try again.")

# --- DYNAMIC TEXT FILE DISCOVERY ---
TARGET_MOVEMENTS = ['101', '311', '261', 'Z61', '221', '201', '551']

# Automatically scan the local directory for ANY .txt file (Lines, Validation Builds, Trials, etc.)
discovered_files = glob.glob('*.txt')
discovered_files.sort()

LINE_FILES = {}
menu_counter = 1

# Populate the menu dynamically based on available text files
for file_path in discovered_files:
    base_name = os.path.basename(file_path)
    clean_name = base_name.replace('.txt', '').replace('_', ' ').title()
    
    LINE_FILES[str(menu_counter)] = {'name': clean_name, 'filename': base_name}
    menu_counter += 1

# Always include a plant-wide option at the very end of the menu
plant_wide_key = str(menu_counter)
LINE_FILES[plant_wide_key] = {'name': 'Plant-Wide (All Lines)', 'filename': None}

# Print the dynamically generated line selection menu options to the terminal
print("\nSelect target production scope:")
for key, info in LINE_FILES.items():
    print(f"  [{key}] {info['name']}")

# Capture the user's line selection choice, defaulting to the plant-wide option if nothing is entered
choice = input(f"Enter choice number (default {plant_wide_key}): ").strip()
selected_line = LINE_FILES.get(choice, LINE_FILES[plant_wide_key])

# Echo the active configurations back to the console
print(f"\n-> Selected Scope: {selected_line['name']}")
print(f"-> Using MB52: {MB52_FILENAME} | MB51: {MB51_FILENAME}\n")
print("Starting dual-file SAP inventory audit...")


# ==========================================
# 1. PARSE MB52 (Starting Inventory Snapshot)
# ==========================================
print(f"Reading and parsing MB52 snapshot ({MB52_FILENAME})...")

with open(MB52_FILENAME, 'r', encoding='utf-8', errors='ignore') as f:
    soup_52 = BeautifulSoup(f.read(), 'html.parser')

table_52 = soup_52.find('table')
if not table_52:
    raise ValueError(f"Could not find an HTML table in {MB52_FILENAME}. Check your export format.")

df_52 = pd.read_html(io.StringIO(str(table_52)))[0]

header_idx_52 = None
for idx, row in df_52.head(15).iterrows():
    row_vals = [str(val).strip() for val in row.values]
    if any('material' in v.lower() for v in row_vals) and any('unrestrict' in v.lower() or 'stock' in v.lower() for v in row_vals):
        header_idx_52 = idx
        break

if header_idx_52 is not None:
    df_52.columns = [str(val).strip() for val in df_52.iloc[header_idx_52].values]
    df_52 = df_52.iloc[header_idx_52 + 1:].reset_index(drop=True)
else:
    df_52.columns = [str(col).strip() for col in df_52.columns]

mat_col_52 = next((c for c in df_52.columns if 'material' in c.lower() and 'desc' not in c.lower() and 'text' not in c.lower()), df_52.columns[0])
uom_col_52 = next((c for c in df_52.columns if 'unit' in c.lower() or 'uom' in c.lower() or 'bun' in c.lower()), None)
stock_col = next((c for c in df_52.columns if 'unrestrict' in c.lower() or 'stock' in c.lower() or 'qty' in c.lower()), df_52.columns[1])

def clean_qty(val):
    if pd.isna(val):
        return 0.0
    val_str = str(val).strip().replace(',', '')
    if val_str.endswith('-'):
        val_str = '-' + val_str[:-1]
    try:
        return float(val_str)
    except ValueError:
        return 0.0

df_52['Clean_Stock'] = df_52[stock_col].apply(clean_qty)
df_52[mat_col_52] = df_52[mat_col_52].astype(str).str.strip()

agg_dict = {'Clean_Stock': 'sum'}
if uom_col_52:
    agg_dict[uom_col_52] = 'first'

stock_summary = df_52.groupby(mat_col_52, as_index=False).agg(agg_dict)

rename_dict = {mat_col_52: 'Material', 'Clean_Stock': 'Starting_Stock'}
if uom_col_52:
    rename_dict[uom_col_52] = 'UoM'

stock_summary = stock_summary.rename(columns=rename_dict)

if 'UoM' not in stock_summary.columns:
    stock_summary['UoM'] = ''

print(f"Loaded starting inventory for {len(stock_summary)} unique parts from MB52.")


# ==========================================
# 2. PARSE MB51 (Monthly Transaction Log)
# ==========================================
print(f"Reading and parsing MB51 log ({MB51_FILENAME})...")

with open(MB51_FILENAME, 'r', encoding='utf-8', errors='ignore') as f:
    soup_51 = BeautifulSoup(f.read(), 'html.parser')

table_51 = soup_51.find('table')
if not table_51:
    raise ValueError(f"Could not find an HTML table in {MB51_FILENAME}. Check your export format.")

df_51 = pd.read_html(io.StringIO(str(table_51)))[0]

header_idx_51 = None
for idx, row in df_51.head(15).iterrows():
    row_vals = [str(val).strip() for val in row.values]
    if 'Material' in row_vals and 'Movement Type' in row_vals:
        header_idx_51 = idx
        break

if header_idx_51 is not None:
    df_51.columns = [str(val).strip() for val in df_51.iloc[header_idx_51].values]
    df_51 = df_51.iloc[header_idx_51 + 1:].reset_index(drop=True)
else:
    df_51.columns = [str(col).strip() for col in df_51.columns]

mat_col_51 = 'Material'
mov_col = 'Movement Type'
qty_col_51 = 'Qty in Un. of Entry'

df_51[mat_col_51] = df_51[mat_col_51].astype(str).str.strip()
df_51['Clean_Mov'] = df_51[mov_col].astype(str).str.strip().str.replace('.0', '', regex=False)
df_51['Clean_Qty'] = df_51[qty_col_51].apply(clean_qty)

filtered_df = df_51[df_51['Clean_Mov'].isin(TARGET_MOVEMENTS)].copy()

def categorize_movement(row):
    m = row['Clean_Mov']
    if m == '101':
        return 'Vendor Receipt (Warehouse)'
    elif m == '311':
        return 'Internal Transfer (Staging / CE Move)'
    elif m in ['261', 'Z61']:
        return 'Production Order Consumption (CE)'
    elif m in ['221', '201']:
        return 'Product Development (PD) Issue (CE)'
    elif m == '551':
        return 'Standard Operational Scrap (551)'
    return 'Other'

filtered_df['Movement_Category'] = filtered_df.apply(categorize_movement, axis=1)

pivot_summary = filtered_df.pivot_table(
    index=mat_col_51,
    columns='Movement_Category',
    values='Clean_Qty',
    aggfunc='sum',
    fill_value=0
).reset_index()

expected_cols = [
    'Vendor Receipt (Warehouse)', 
    'Internal Transfer (Staging / CE Move)', 
    'Production Order Consumption (CE)', 
    'Product Development (PD) Issue (CE)', 
    'Standard Operational Scrap (551)'
]
for col in expected_cols:
    if col not in pivot_summary.columns:
        pivot_summary[col] = 0

for col in ['Production Order Consumption (CE)', 'Product Development (PD) Issue (CE)', 'Standard Operational Scrap (551)']:
    pivot_summary[col] = pivot_summary[col].abs()


# ==========================================
# 3. MERGE MB52 & MB51 & APPLY LINE FILTER
# ==========================================
print("Merging starting inventory with monthly transaction velocity...")
master_df = pd.merge(stock_summary, pivot_summary, on='Material', how='outer')

numeric_cols = ['Starting_Stock'] + expected_cols
for col in numeric_cols:
    if col in master_df.columns:
        master_df[col] = master_df[col].fillna(0.0)

if 'UoM' not in master_df.columns:
    master_df['UoM'] = ''
else:
    master_df['UoM'] = master_df['UoM'].fillna('')

if selected_line['filename']:
    target_file = selected_line['filename']
    if os.path.exists(target_file):
        with open(target_file, 'r') as f:
            line_parts = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        master_df = master_df[master_df['Material'].isin(line_parts)]
        print(f"-> Filtered to {len(master_df)} parts listed in '{target_file}' for {selected_line['name']}.")
    else:
        print(f"-> Warning: Could not find part list file '{target_file}'. Running without line filtering.")

master_df['Total Outflow'] = (
    master_df['Production Order Consumption (CE)'] + 
    master_df['Product Development (PD) Issue (CE)'] + 
    master_df['Standard Operational Scrap (551)']
)

master_df['Projected Ending Stock'] = (
    master_df['Starting_Stock'] + 
    master_df['Vendor Receipt (Warehouse)'] - 
    master_df['Total Outflow']
)

master_df = master_df.sort_values(by='Total Outflow', ascending=False)


# ==========================================
# 4. GENERATE HTML DASHBOARD REPORT
# ==========================================
report_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
scope_title = selected_line['name']

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>SAP Inventory & Stockout Risk Report - {scope_title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 30px; background-color: #f8f9fa; color: #333; }}
        h1 {{ color: #2c3e50; margin-bottom: 5px; }}
        .subtitle {{ color: #7f8c8d; margin-bottom: 20px; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-top: 20px; font-size: 13px; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #dee2e6; }}
        th {{ background-color: #34495e; color: white; position: sticky; top: 0; cursor: pointer; user-select: none; }}
        th:hover {{ background-color: #2c3e50; }}
        tr:hover {{ background-color: #f1f1f1; }}
        .risk-high {{ background-color: #fadbd8; color: #78281f; font-weight: bold; }}
        .risk-warning {{ background-color: #fcf3cf; color: #7d6608; font-weight: bold; }}
        
        .summary-box {{ background: white; padding: 15px; border-left: 5px solid #3498db; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; line-height: 1.5; }}
        .badge {{ background: #e2e8f0; padding: 3px 6px; border-radius: 4px; font-size: 11px; }}
        .controls-container {{ margin-top: 12px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
        .toggle-btn {{ background-color: #3498db; color: white; border: none; padding: 8px 14px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: bold; transition: background 0.2s; }}
        .toggle-btn:hover {{ background-color: #2980b9; }}
        .search-input {{ padding: 7px 10px; width: 280px; border-radius: 4px; border: 1px solid #ccc; font-size: 13px; }}
    </style>
    <script>
        let showingExceptionsOnly = false;

        // Unified filter function evaluating both Search input and Exception Toggle simultaneously
        function applyFilters() {{
            let input = document.getElementById("tableSearch");
            let filter = input ? input.value.toUpperCase() : "";
            let rows = document.querySelectorAll("tbody tr");

            rows.forEach(row => {{
                let isException = row.classList.contains('risk-high') || row.classList.contains('risk-warning');
                
                // 1. Exception Toggle check
                let passesExceptionFilter = !showingExceptionsOnly || isException;

                // 2. Search Bar check
                let passesSearchFilter = false;
                let tds = row.querySelectorAll("td");
                tds.forEach(td => {{
                    if (td.innerText.toUpperCase().indexOf(filter) > -1) {{
                        passesSearchFilter = true;
                    }}
                }});

                // Display row only if it satisfies both criteria
                if (passesExceptionFilter && passesSearchFilter) {{
                    row.style.display = "";
                }} else {{
                    row.style.display = "none";
                }}
            }});
        }}

        // Triggered by the Exceptions button
        function toggleExceptions() {{
            showingExceptionsOnly = !showingExceptionsOnly;
            let btn = document.getElementById('toggleBtn');
            if (showingExceptionsOnly) {{
                btn.innerText = "Switch to Show All Parts";
                btn.style.backgroundColor = "#e67e22";
            }} else {{
                btn.innerText = "Switch to Exceptions Only (Hide Normal Parts)";
                btn.style.backgroundColor = "#3498db";
            }}
            applyFilters();
        }}

        // Triggered live while typing in the search bar
        function filterTable() {{
            applyFilters();
        }}

        // Click-to-Sort Column Headers (fully compatible with active filters and search)
        document.addEventListener("DOMContentLoaded", () => {{
            const table = document.querySelector("table");
            if (!table) return;
            const headers = table.querySelectorAll("th");

            headers.forEach((th, idx) => {{
                th.title = "Click to sort column";

                th.addEventListener("click", () => {{
                    const tbody = table.querySelector("tbody");
                    const rows = Array.from(tbody.querySelectorAll("tr"));
                    const asc = th.asc = !th.asc;

                    rows.sort((a, b) => {{
                        let v1 = a.children[idx].innerText.trim();
                        let v2 = b.children[idx].innerText.trim();

                        let n1 = parseFloat(v1.replace(/,/g, ''));
                        let n2 = parseFloat(v2.replace(/,/g, ''));

                        if (!isNaN(n1) && !isNaN(n2)) {{
                            return asc ? n1 - n2 : n2 - n1;
                        }}
                        return asc ? v1.localeCompare(v2) : v2.localeCompare(v1);
                    }});

                    // Re-attach sorted rows and maintain current filter/search state
                    rows.forEach(row => tbody.appendChild(row));
                    applyFilters();
                }});
            }});
        }});
    </script>
</head>
<body>
    <h1>Closed-Loop SAP Inventory & Risk Report</h1>
    <div class="subtitle">Generated: {report_date} | Scope: <strong>{scope_title}</strong> | Files: {MB52_FILENAME} + {MB51_FILENAME}</div>
    
    <div class="summary-box">
        <strong>Workflow Overview:</strong> Combines starting inventory snapshot (<span class="badge">MB52</span>) with monthly velocity (<span class="badge">MB51</span>). 
        Calculates: <br><code>Starting Stock + Vendor Receipts (101) - Total Outflows (261/Z61/221/201/551) = Projected Ending Stock</code>.<br>
        <span style="color: #78281f; font-weight: bold;">Red rows</span> indicate stockouts with zero vendor receipts (missed orders). 
        <span style="color: #7d6608; font-weight: bold;">Yellow rows</span> indicate negative stock *despite* vendor receipts, pointing to ordering quantity or BOM discrepancies.<br>
        <div class="controls-container">
            <button class="toggle-btn" id="toggleBtn" onclick="toggleExceptions()">Switch to Exceptions Only (Hide Normal Parts)</button>
            <input type="text" id="tableSearch" class="search-input" placeholder="Search Material ID, UoM, numbers..." onkeyup="filterTable()">
            <span style="font-size: 12px; color: #555;">💡 Click any column header to sort.</span>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Material ID</th>
                <th>UoM</th>
                <th>Sept 1 Starting Stock</th>
                <th>Vendor Receipts (101)</th>
                <th>Internal Transfers (311)</th>
                <th>Production Consumption (261/Z61)</th>
                <th>PD Issue (221/201)</th>
                <th>Operational Scrap (551)</th>
                <th>Total Outflow</th>
                <th>Projected Ending Stock</th>
            </tr>
        </thead>
        <tbody>
"""

for _, row in master_df.iterrows():
    ending_stock = row['Projected Ending Stock']
    vendor_receipts = row['Vendor Receipt (Warehouse)']
    
    if ending_stock < 0 and vendor_receipts == 0:
        status_class = "risk-high"
    elif ending_stock < 0 and vendor_receipts > 0:
        status_class = "risk-warning"
    else:
        status_class = ""
    
    html_content += f"""
            <tr class="{status_class}">
                <td>{row['Material']}</td>
                <td><span class="badge">{row['UoM']}</span></td>
                <td>{row['Starting_Stock']}</td>
                <td>{vendor_receipts}</td>
                <td>{row['Internal Transfer (Staging / CE Move)']}</td>
                <td>{row['Production Order Consumption (CE)']}</td>
                <td>{row['Product Development (PD) Issue (CE)']}</td>
                <td>{row['Standard Operational Scrap (551)']}</td>
                <td><strong>{row['Total Outflow']}</strong></td>
                <td>{ending_stock}</td>
            </tr>
    """

html_content += """
        </tbody>
    </table>
</body>
</html>
"""

with open('inventory_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

master_df.to_csv('component_flow_analysis.csv', index=False)

print("\nProcessing complete!")
print(f"-> Consolidated {len(master_df)} unique parts for {selected_line['name']}.")
print("-> Interactive Dashboard saved to: 'inventory_dashboard.html'")

dashboard_path = "file://" + os.path.abspath("inventory_dashboard.html")
webbrowser.open(dashboard_path)

input("\nPress Enter to exit...")
