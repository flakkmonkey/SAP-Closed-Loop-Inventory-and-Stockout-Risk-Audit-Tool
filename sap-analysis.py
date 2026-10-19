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
from bs4 import BeautifulSoup                                                # Imports BeautifulSoup for parsing raw HTML/MHTML structures
# Import Pandas for data manipulation, cleaning, pivoting, and merging
import pandas as pd                                                         # Imports Pandas for dataframe operations and analytics
# Import datetime to generate timestamps for the report header
import datetime                                                             # Imports datetime to timestamp the generated dashboard
# Import io to wrap string HTML data into a file-like stream for Pandas read_html
import io                                                                   # Imports io to handle string streams for HTML table reading
# Import webbrowser to automatically launch the generated HTML report in the default browser
import webbrowser                                                           # Imports webbrowser to auto-open the final HTML report
# Import os to check file paths and resolve absolute paths locally
import os                                                                   # Imports os for path checking and file system operations
# Import glob to automatically scan directories for text files
import glob                                                                 # Imports glob to scan local directories for line txt files

# Print a welcome banner to the terminal console
print("=== SAP Closed-Loop Inventory Audit Tool ===")                           # Prints introductory title to the terminal

# --- DYNAMIC FILE PROMPTS WITH EXISTENCE CHECKS ---
default_mb52 = 'september_stock.mhtml'                                      # Sets default filename string for MB52 inventory export
default_mb51 = 'september_log.mhtml'                                        # Sets default filename string for MB51 movement log export

# Prompt for MB52 snapshot filename with validation loop
while True:                                                                 # Starts infinite loop to validate MB52 user input file existence
    mb52_input = input(f"Enter MB52 inventory snapshot filename [default: {default_mb52}]: ").strip() # Prompts user for MB52 filename and strips whitespace
    MB52_FILENAME = mb52_input if mb52_input else default_mb52              # Assigns custom filename if entered, else defaults to preset
    if os.path.exists(MB52_FILENAME):                                       # Checks if the specified MB52 file exists in the directory
        break                                                               # Breaks validation loop if file is confirmed present
    print(f"-> Error: File '{MB52_FILENAME}' not found in current directory. Please check the name and try again.") # Prints error if file is missing

# Prompt for MB51 log filename with validation loop
while True:                                                                 # Starts infinite loop to validate MB51 user input file existence
    mb51_input = input(f"Enter MB51 transaction log filename [default: {default_mb51}]: ").strip() # Prompts user for MB51 filename and strips whitespace
    MB51_FILENAME = mb51_input if mb51_input else default_mb51              # Assigns custom filename if entered, else defaults to preset
    if os.path.exists(MB51_FILENAME):                                       # Checks if the specified MB51 file exists in the directory
        break                                                               # Breaks validation loop if file is confirmed present
    print(f"-> Error: File '{MB51_FILENAME}' not found in current directory. Please check the name and try again.") # Prints error if file is missing

# --- DYNAMIC TEXT FILE DISCOVERY ---
TARGET_MOVEMENTS = ['101', '311', '261', 'Z61', '221', '201', '551']          # Defines list of SAP movement types to filter and track

# Automatically scan the local directory for ANY .txt file (Lines, Validation Builds, Trials, etc.)
discovered_files = glob.glob('*.txt')                                       # Finds all text files in current working directory using glob
discovered_files.sort()                                                     # Sorts discovered text files alphabetically for consistent menus

LINE_FILES = {}                                                             # Initializes empty dictionary to hold menu mapping for line files
menu_counter = 1                                                            # Initializes menu numbering counter starting at 1

# Populate the menu dynamically based on available text files
for file_path in discovered_files:                                          # Iterates through each discovered text file path
    base_name = os.path.basename(file_path)                                 # Extracts just the file name from the path
    clean_name = base_name.replace('.txt', '').replace('_', ' ').title()    # Cleans filename string into a readable title case format
    
    LINE_FILES[str(menu_counter)] = {'name': clean_name, 'filename': base_name} # Maps menu number string to display name and filename
    menu_counter += 1                                                       # Increments menu counter for the next item

# Always include a plant-wide option at the very end of the menu
plant_wide_key = str(menu_counter)                                          # Converts final counter value to string key for plant-wide option
LINE_FILES[plant_wide_key] = {'name': 'Plant-Wide (All Lines)', 'filename': None} # Adds plant-wide fallback entry with no file restriction

# Print the dynamically generated line selection menu options to the terminal
print("\nSelect target production scope:")                                   # Prints selection prompt header
for key, info in LINE_FILES.items():                                        # Iterates through menu dictionary items
    print(f"  [{key}] {info['name']}")                                      # Prints formatted menu option line to terminal

# Capture the user's line selection choice, defaulting to the plant-wide option if nothing is entered
choice = input(f"Enter choice number (default {plant_wide_key}): ").strip()   # Captures user menu selection input
selected_line = LINE_FILES.get(choice, LINE_FILES[plant_wide_key])          # Retrieves selected line config dictionary or defaults to plant-wide

# Echo the active configurations back to the console
print(f"\n-> Selected Scope: {selected_line['name']}")                       # Prints selected scope title
print(f"-> Using MB52: {MB52_FILENAME} | MB51: {MB51_FILENAME}\n")            # Prints active filenames being processed
print("Starting dual-file SAP inventory audit...")                            # Prints status message indicating audit execution start


# ==========================================
# 1. PARSE MB52 (Starting Inventory Snapshot)
# ==========================================
print(f"Reading and parsing MB52 snapshot ({MB52_FILENAME})...")              # Prints parsing status for MB52 file

with open(MB52_FILENAME, 'r', encoding='utf-8', errors='ignore') as f:      # Opens MB52 MHTML file safely with utf-8 encoding
    soup_52 = BeautifulSoup(f.read(), 'html.parser')                        # Parses raw HTML contents of MB52 file using BeautifulSoup

table_52 = soup_52.find('table')                                            # Locates the primary data table element in MB52 parse tree
if not table_52:                                                            # Checks if HTML table was successfully found
    raise ValueError(f"Could not find an HTML table in {MB52_FILENAME}. Check your export format.") # Raises error if table is missing

df_52 = pd.read_html(io.StringIO(str(table_52)))[0]                         # Reads extracted HTML table into a Pandas DataFrame

header_idx_52 = None                                                        # Initializes variable to track header row index in MB52 table
for idx, row in df_52.head(15).iterrows():                                  # Iterates through first 15 rows to find correct table header row
    row_vals = [str(val).strip() for val in row.values]                     # Converts row values to stripped string list
    if any('material' in v.lower() for v in row_vals) and any('unrestrict' in v.lower() or 'stock' in v.lower() for v in row_vals): # Checks if row matches expected header keywords
        header_idx_52 = idx                                                 # Records row index matching header criteria
        break                                                               # Breaks header search loop

if header_idx_52 is not None:                                               # If header row was successfully identified
    df_52.columns = [str(val).strip() for val in df_52.iloc[header_idx_52].values] # Assigns identified row as DataFrame column headers
    df_52 = df_52.iloc[header_idx_52 + 1:].reset_index(drop=True)           # Drops header and pre-header rows and resets index
else:                                                                       # Fallback if specific header row wasn't matched
    df_52.columns = [str(col).strip() for col in df_52.columns]             # Uses default DataFrame columns stripped of whitespace

mat_col_52 = next((c for c in df_52.columns if 'material' in c.lower() and 'desc' not in c.lower() and 'text' not in c.lower()), df_52.columns[0]) # Identifies exact material number column name
uom_col_52 = next((c for c in df_52.columns if 'unit' in c.lower() or 'uom' in c.lower() or 'bun' in c.lower()), None) # Identifies unit of measure column name if present
stock_col = next((c for c in df_52.columns if 'unrestrict' in c.lower() or 'stock' in c.lower() or 'qty' in c.lower()), df_52.columns[1]) # Identifies unrestricted stock quantity column name

def clean_qty(val):                                                         # Defines helper function to clean and convert string quantities to float
    if pd.isna(val):                                                        # Checks if value is null or NaN
        return 0.0                                                          # Returns zero float for null values
    val_str = str(val).strip().replace(',', '')                             # Converts value to string, strips whitespace, removes commas
    if val_str.endswith('-'):                                               # Checks if negative sign is formatted at the end of the string
        val_str = '-' + val_str[:-1]                                        # Moves trailing minus sign to the front of the number string
    try:                                                                    # Attempts float conversion
        return float(val_str)                                               # Returns converted float value
    except ValueError:                                                      # Catches conversion errors on non-numeric text
        return 0.0                                                          # Returns zero float fallback on error

df_52['Clean_Stock'] = df_52[stock_col].apply(clean_qty)                    # Applies qty cleaning function to stock column creating new clean column
df_52[mat_col_52] = df_52[mat_col_52].astype(str).str.strip()               # Standardizes material column values as cleaned strings

agg_dict = {'Clean_Stock': 'sum'}                                           # Sets up dictionary for aggregating stock sums by material
if uom_col_52:                                                              # If unit of measure column exists
    agg_dict[uom_col_52] = 'first'                                          # Includes uom column aggregation rule

stock_summary = df_52.groupby(mat_col_52, as_index=False).agg(agg_dict)     # Groups MB52 dataframe by material to summarize total stock on hand

rename_dict = {mat_col_52: 'Material', 'Clean_Stock': 'Starting_Stock'}     # Sets up dictionary to standardize summary column names
if uom_col_52:                                                              # If uom column exists in summary
    rename_dict[uom_col_52] = 'UoM'                                         # Renames uom column to standard name

stock_summary = stock_summary.rename(columns=rename_dict)                   # Applies column renaming dictionary to stock summary dataframe

if 'UoM' not in stock_summary.columns:                                      # Checks if UoM column is missing from summary
    stock_summary['UoM'] = ''                                               # Adds empty UoM column if not present

print(f"Loaded starting inventory for {len(stock_summary)} unique parts from MB52.") # Prints total unique parts loaded from MB52 snapshot


# ==========================================
# 2. PARSE MB51 (Monthly Transaction Log)
# ==========================================
print(f"Reading and parsing MB51 log ({MB51_FILENAME})...")                  # Prints parsing status for MB51 log file

with open(MB51_FILENAME, 'r', encoding='utf-8', errors='ignore') as f:      # Opens MB51 MHTML file safely with utf-8 encoding
    soup_51 = BeautifulSoup(f.read(), 'html.parser')                        # Parses raw HTML contents of MB51 file using BeautifulSoup

table_51 = soup_51.find('table')                                            # Locates the primary data table element in MB51 parse tree
if not table_51:                                                            # Checks if HTML table was successfully found
    raise ValueError(f"Could not find an HTML table in {MB51_FILENAME}. Check your export format.") # Raises error if table is missing

df_51 = pd.read_html(io.StringIO(str(table_51)))[0]                         # Reads extracted HTML movement table into a Pandas DataFrame

header_idx_51 = None                                                        # Initializes variable to track header row index in MB51 table
for idx, row in df_51.head(15).iterrows():                                  # Iterates through first 15 rows to find correct MB51 table header row
    row_vals = [str(val).strip() for val in row.values]                     # Converts row values to stripped string list
    if 'Material' in row_vals and 'Movement Type' in row_vals:              # Checks if row contains necessary SAP header identifiers
        header_idx_51 = idx                                                 # Records row index matching header criteria
        break                                                               # Breaks header search loop

if header_idx_51 is not None:                                               # If header row was successfully identified
    df_51.columns = [str(val).strip() for val in df_51.iloc[header_idx_51].values] # Assigns identified row as DataFrame column headers
    df_51 = df_51.iloc[header_idx_51 + 1:].reset_index(drop=True)           # Drops header and pre-header rows and resets index
else:                                                                       # Fallback if specific header row wasn't matched
    df_51.columns = [str(col).strip() for col in df_51.columns]             # Uses default DataFrame columns stripped of whitespace

mat_col_51 = 'Material'                                                     # Sets standard material column name for MB51 log
mov_col = 'Movement Type'                                                   # Sets standard movement type column name for MB51 log
qty_col_51 = 'Qty in Un. of Entry'                                          # Sets standard quantity entry column name for MB51 log

df_51[mat_col_51] = df_51[mat_col_51].astype(str).str.strip()               # Standardizes material column values as cleaned strings
df_51['Clean_Mov'] = df_51[mov_col].astype(str).str.strip().str.replace('.0', '', regex=False) # Cleans movement type codes by casting to string and stripping decimals
df_51['Clean_Qty'] = df_51[qty_col_51].apply(clean_qty)                     # Cleans movement quantities using qty cleaning helper function

filtered_df = df_51[df_51['Clean_Mov'].isin(TARGET_MOVEMENTS)].copy()       # Filters movement dataframe to only include target SAP movement codes

def categorize_movement(row):                                               # Defines function to map raw movement codes to descriptive business categories
    m = row['Clean_Mov']                                                    # Extracts cleaned movement code string
    if m == '101':                                                          # Checks if movement code is goods receipt against purchase order
        return 'Vendor Receipt (Warehouse)'                                 # Returns descriptive label for vendor receipts
    elif m == '311':                                                        # Checks if movement code is storage location transfer
        return 'Internal Transfer (Staging / CE Move)'                      # Returns descriptive label for internal movements
    elif m in ['261', 'Z61']:                                               # Checks if movement code is production order material consumption
        return 'Production Order Consumption (CE)'                          # Returns descriptive label for production consumption
    elif m in ['221', '201']:                                               # Checks if movement code is cost center or project withdrawal
        return 'Product Development (PD) Issue (CE)'                        # Returns descriptive label for project or R&D issues
    elif m == '551':                                                        # Checks if movement code is scrap write-off
        return 'Standard Operational Scrap (551)'                           # Returns descriptive label for scrapping movements
    return 'Other'                                                          # Returns fallback label for unmapped movement types

filtered_df['Movement_Category'] = filtered_df.apply(categorize_movement, axis=1) # Applies movement categorization logic across filtered dataframe rows

pivot_summary = filtered_df.pivot_table(                                    # Creates pivot table summarizing quantities grouped by material and movement category
    index=mat_col_51,                                                       # Sets material as pivot table rows
    columns='Movement_Category',                                            # Sets movement categories as pivot table columns
    values='Clean_Qty',                                                     # Aggregates cleaned quantities in pivot cells
    aggfunc='sum',                                                          # Uses sum aggregation for quantities
    fill_value=0                                                            # Fills missing values with zero
).reset_index()                                                             # Resets index of the resulting pivot summary dataframe

expected_cols = [                                                           # Defines standard list of expected movement category columns
    'Vendor Receipt (Warehouse)', 
    'Internal Transfer (Staging / CE Move)', 
    'Production Order Consumption (CE)', 
    'Product Development (PD) Issue (CE)', 
    'Standard Operational Scrap (551)'
]
for col in expected_cols:                                                   # Iterates through expected movement category columns
    if col not in pivot_summary.columns:                                    # Checks if expected column is missing from pivot result
        pivot_summary[col] = 0                                              # Creates missing column filled with zeros if absent

for col in ['Production Order Consumption (CE)', 'Product Development (PD) Issue (CE)', 'Standard Operational Scrap (551)']: # Iterates through outflow category columns
    pivot_summary[col] = pivot_summary[col].abs()                           # Converts outflow figures to absolute positive values for calculations


# ==========================================
# 3. MERGE MB52 & MB51 & APPLY LINE FILTER
# ==========================================
print("Merging starting inventory with monthly transaction velocity...")      # Prints merging status message to console
master_df = pd.merge(stock_summary, pivot_summary, on='Material', how='outer') # Outer merges starting stock summary with transaction movement pivot summary on material number

numeric_cols = ['Starting_Stock'] + expected_cols                             # Combines starting stock and movement columns into numeric list
for col in numeric_cols:                                                    # Iterates through numeric columns
    if col in master_df.columns:                                            # Checks if column exists in master dataframe
        master_df[col] = master_df[col].fillna(0.0)                         # Fills NaN numeric values with 0.0 float

if 'UoM' not in master_df.columns:                                          # Checks if UoM column is missing from master dataframe
    master_df['UoM'] = ''                                                   # Initializes empty UoM column if absent
else:                                                                       # If UoM column exists
    master_df['UoM'] = master_df['UoM'].fillna('')                          # Fills any NaN UoM values with empty string strings

if selected_line['filename']:                                               # Checks if a specific production line text file was selected by user
    target_file = selected_line['filename']                                 # Retrieves target line part filename string
    if os.path.exists(target_file):                                         # Checks if part list text file exists locally
        with open(target_file, 'r') as f:                                   # Opens target part list text file for reading
            line_parts = [line.strip() for line in f if line.strip() and not line.startswith('#')] # Reads stripped part numbers ignoring comments and empty lines
        master_df = master_df[master_df['Material'].isin(line_parts)]       # Filters master dataframe to only keep parts present in the selected line file
        print(f"-> Filtered to {len(master_df)} parts listed in '{target_file}' for {selected_line['name']}.") # Prints filtered part count and line scope name
    else:                                                                   # Fallback if line text file cannot be found
        print(f"-> Warning: Could not find part list file '{target_file}'. Running without line filtering.") # Prints warning message about missing file

master_df['Total Outflow'] = (                                              # Calculates total monthly outflow by summing all consumption and scrap columns
    master_df['Production Order Consumption (CE)'] + 
    master_df['Product Development (PD) Issue (CE)'] + 
    master_df['Standard Operational Scrap (551)']
)

master_df['Projected Ending Stock'] = (                                     # Calculates projected ending stock using closed-loop formula
    master_df['Starting_Stock'] + 
    master_df['Vendor Receipt (Warehouse)'] - 
    master_df['Total Outflow']
)

master_df = master_df.sort_values(by='Total Outflow', ascending=False)       # Sorts master dataframe rows by highest total monthly outflow descending


# ==========================================
# 4. GENERATE HTML DASHBOARD REPORT
# ==========================================
report_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")              # Formats current date and time string for report header
scope_title = selected_line['name']                                         # Retrieves active scope title name string

html_content = f"""                                                         # Opens multi-line string template for HTML report generation
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
        let showingExceptionsOnly = false;                                  # Initializes JavaScript tracking state for exception view toggle

        // Unified filter function evaluating both Search input and Exception Toggle simultaneously
        function applyFilters() {{
            let input = document.getElementById("tableSearch");             # Gets search input HTML element object
            let filter = input ? input.value.toUpperCase() : "";            # Retrieves uppercase search string query
            let rows = document.querySelectorAll("tbody tr");               # Selects all table body data rows

            rows.forEach(row => {{                                          # Iterates through each table row element
                let isException = row.classList.contains('risk-high') || row.classList.contains('risk-warning'); # Checks if row carries high risk or warning flags
                
                // 1. Exception Toggle check
                let passesExceptionFilter = !showingExceptionsOnly || isException; # Evaluates if row satisfies current exception view mode

                // 2. Search Bar check
                let passesSearchFilter = false;                             # Initializes search match boolean to false
                let tds = row.querySelectorAll("td");                       # Selects all column cells in current row
                tds.forEach(td => {{                                        # Iterates through each cell in the row
                    if (td.innerText.toUpperCase().indexOf(filter) > -1) {{ # Checks if cell text contains search filter query string
                        passesSearchFilter = true;                          # Marks search filter check as passed if match found
                    }}
                }});

                // Display row only if it satisfies both criteria
                if (passesExceptionFilter && passesSearchFilter) {{         # Checks if row meets both exception mode and search query criteria
                    row.style.display = "";                                 # Displays row if conditions are satisfied
                }} else {{                                                  # Otherwise
                    row.style.display = "none";                             # Hides row if conditions are unmet
                }}
            }});
        }}

        // Triggered by the Exceptions button
        function toggleExceptions() {{
            showingExceptionsOnly = !showingExceptionsOnly;                 # Inverts exception toggle state boolean value
            let btn = document.getElementById('toggleBtn');                 # Selects exception toggle button element object
            if (showingExceptionsOnly) {{                                   # Checks if exception view mode is now active
                btn.innerText = "Switch to Show All Parts";                 # Updates button text label to show all parts option
                btn.style.backgroundColor = "#e67e22";                      # Changes button background color scheme to orange indicator
            }} else {{                                                      # Otherwise when returning to all parts view
                btn.innerText = "Switch to Exceptions Only (Hide Normal Parts)"; # Resets button text label back to default
                btn.style.backgroundColor = "#3498db";                      # Resets button background color scheme back to blue
            }}
            applyFilters();                                                 # Triggers unified filter update function
        }}

        // Triggered live while typing in the search bar
        function filterTable() {{
            applyFilters();                                                 # Calls unified filter function on keyup events inside search input
        }}

        // Click-to-Sort Column Headers (fully compatible with active filters and search)
        document.addEventListener("DOMContentLoaded", () => {{              # Listens for DOM content to fully load before attaching sorting events
            const table = document.querySelector("table");                  # Selects target main table element
            if (!table) return;                                             # Exits event listener registration if table is absent
            const headers = table.querySelectorAll("th");                   # Selects all table header column elements

            headers.forEach((th, idx) => {{                                 # Iterates through each header element and its column index
                th.title = "Click to sort column";                          # Sets helpful hover tooltip text for table headers

                th.addEventListener("click", () => {{                       # Attaches click event listener to sort table data by column
                    const tbody = table.querySelector("tbody");             # Selects table body element containing rows
                    const rows = Array.from(tbody.querySelectorAll("tr"));  # Converts table body rows into an array object
                    const asc = th.asc = !th.asc;                           # Toggles ascending/descending sort direction state boolean

                    rows.sort((a, b) => {{                                  # Sorts row elements based on cell values
                        let v1 = a.children[idx].innerText.trim();          # Retrieves trimmed text string from row A cell at column index
                        let v2 = b.children[idx].innerText.trim();          # Retrieves trimmed text string from row B cell at column index

                        let n1 = parseFloat(v1.replace(/,/g, ''));          # Attempts to parse string A as a clean float number
                        let n2 = parseFloat(v2.replace(/,/g, ''));          # Attempts to parse string B as a clean float number

                        if (!isNaN(n1) && !isNaN(n2)) {{                    # Checks if both values successfully parsed as numeric floats
                            return asc ? n1 - n2 : n2 - n1;                 # Returns numeric comparison result based on sort direction
                        }}
                        return asc ? v1.localeCompare(v2) : v2.localeCompare(v1); # Returns alphanumeric text comparison result as fallback
                    }});

                    // Re-attach sorted rows and maintain current filter/search state
                    rows.forEach(row => tbody.appendChild(row));            # Appends sorted rows back into table body DOM tree in order
                    applyFilters();                                         # Re-applies active search and exception filters after sorting
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
"""                                                                         # Closes header portion of HTML string template

for _, row in master_df.iterrows():                                         # Iterates through each row in master results dataframe
    ending_stock = row['Projected Ending Stock']                            # Extracts projected ending stock value for current row
    vendor_receipts = row['Vendor Receipt (Warehouse)']                     # Extracts vendor receipt quantity value for current row
    
    if ending_stock < 0 and vendor_receipts == 0:                           # Checks if part has stockout deficit with zero incoming vendor receipts
        status_class = "risk-high"                                          # Assigns high-risk red CSS class flag
    elif ending_stock < 0 and vendor_receipts > 0:                          # Checks if part has stockout deficit despite positive vendor receipts
        status_class = "risk-warning"                                       # Assigns warning-level yellow CSS class flag
    else:                                                                   # Fallback for healthy stock levels
        status_class = ""                                                   # Leaves status class empty for normal rows
    
    html_content += f"""                                                    # Appends table row HTML markup for each part record
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

html_content += """                                                         # Appends closing HTML document tags and footer structure
        </tbody>
    </table>
</body>
</html>
"""

with open('inventory_dashboard.html', 'w', encoding='utf-8') as f:          # Opens local HTML output file for writing with utf-8 encoding
    f.write(html_content)                                                   # Writes complete generated HTML string content to output file

master_df.to_csv('component_flow_analysis.csv', index=False)                # Exports master dataframe analysis results to a backup CSV file

print("\nProcessing complete!")                                              # Prints completion status message to terminal console
print(f"-> Consolidated {len(master_df)} unique parts for {selected_line['name']}.") # Prints total part count processed
print("-> Interactive Dashboard saved to: 'inventory_dashboard.html'")       # Prints confirmation path of generated HTML report file

dashboard_path = "file://" + os.path.abspath("inventory_dashboard.html")    # Resolves absolute file path URI string for browser launch
webbrowser.open(dashboard_path)                                             # Automatically opens the generated HTML dashboard in default web browser

input("\nPress Enter to exit...")                                             # Pauses terminal execution waiting for user keystroke exit
