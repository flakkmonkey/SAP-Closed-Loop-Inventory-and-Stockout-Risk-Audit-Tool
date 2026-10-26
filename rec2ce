import pandas as pd
import numpy as np
from datetime import datetime
import os

# ==========================================
# 1. PALLET CAPACITY CONFIG & EXCEPTION LOGGER
# ==========================================
def load_pallet_capacities(config_filename="pallet_capacity.csv"):
    """
    Loads standard units-per-pallet packaging configuration from CSV.
    Returns a dictionary keyed by Material.
    """
    capacities = {}
    if not os.path.exists(config_filename):
        print(f"⚠️ Warning: Config file '{config_filename}' not found. Defaulting to 1 unit per pallet.")
        return capacities
        
    try:
        df_config = pd.read_csv(config_filename, dtype={'Material': str})
        for _, row in df_config.iterrows():
            mat = str(row['Material']).strip()
            units_per_pallet = float(row['Units_Per_Pallet'])
            if units_per_pallet > 0:
                capacities[mat] = units_per_pallet
        print(f"✅ Successfully loaded {len(capacities)} pallet capacity rule(s) from '{config_filename}'.")
    except Exception as e:
        print(f"❌ Error reading '{config_filename}': {e}")
        
    return capacities

# Outflow movements crossing warehouse threshold to WIP / tents / production
OUTFLOW_MOVEMENTS = ['261', 'Z61', '221', '311', '551']

class WarehouseExceptionLogger:
    def __init__(self, filename="warehouse_exceptions.csv"):
        self.filename = filename
        self.exceptions = []
        
    def log(self, material, issue_type, details):
        self.exceptions.append({
            'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'Material': str(material).strip(),
            'Issue_Type': issue_type,
            'Details': details
        })
        
    def flush(self):
        if not self.exceptions:
            return
        df_ex = pd.DataFrame(self.exceptions)
        file_exists = os.path.exists(self.filename)
        df_ex.to_csv(self.filename, mode='a', index=False, header=not file_exists)
        print(f"⚠️ Logged {len(self.exceptions)} warehouse audit exception(s) to {self.filename}")


# ==========================================
# 2. WAREHOUSE VELOCITY & PALLET FOOTPRINT ENGINE
# ==========================================
def analyze_warehouse_velocity(df_52, df_51, pallet_capacities, dead_stock_days=180, analysis_window_days=90):
    """
    Calculates warehouse velocity, dead stock, and converts on-hand stock 
    into estimated Pallet Spaces occupied based on pallet capacity rules.
    """
    current_date = pd.Timestamp.today()
    
    # Filter MB51 for warehouse outflows
    df_outflows = df_51[df_51['Movement_Type'].astype(str).isin(OUTFLOW_MOVEMENTS)].copy()
    df_outflows['Posting_Date'] = pd.to_datetime(df_outflows['Posting_Date'])
    
    # Find the Last Outflow Date for each material
    last_movement = df_outflows.groupby('Material')['Posting_Date'].max().reset_index()
    last_movement.rename(columns={'Posting_Date': 'Last_Outflow_Date'}, inplace=True)
    
    # Calculate total volume moved out over the recent analysis window
    cutoff_date = current_date - pd.Timedelta(days=analysis_window_days)
    df_recent_outflows = df_outflows[df_outflows['Posting_Date'] >= cutoff_date]
    
    total_movement = df_recent_outflows.groupby('Material')['Quantity'].sum().reset_index()
    total_movement.rename(columns={'Quantity': f'Outflow_{analysis_window_days}D'}, inplace=True)
    
    # Merge velocity metrics into MB52 On-Hand snapshot
    df_warehouse = pd.merge(
        df_52[['Material', 'Description', 'On_Hand_Stock', 'Storage_Location']], 
        last_movement, 
        on='Material', 
        how='left'
    )
    df_warehouse = pd.merge(df_warehouse, total_movement, on='Material', how='left')
    
    # Fill NaNs for inactive items
    df_warehouse['Last_Outflow_Date'] = df_warehouse['Last_Outflow_Date'].fillna(pd.Timestamp('2020-01-01'))
    df_warehouse[f'Outflow_{analysis_window_days}D'] = df_warehouse[f'Outflow_{analysis_window_days}D'].fillna(0.0)
    
    # Calculate Days Since Last Movement
    df_warehouse['Days_Since_Last_Move'] = (current_date - df_warehouse['Last_Outflow_Date']).dt.days
    
    # Calculate Pallet Spaces Occupied
    def calc_pallets(row):
        mat = str(row['Material']).strip()
        stock = row['On_Hand_Stock']
        # Lookup units per pallet; default to stock quantity (1 unit = 1 pallet slot equivalent) if unconfigured
        units_per_pallet = pallet_capacities.get(mat, 1.0)
        if units_per_pallet <= 0:
            return stock
        return stock / units_per_pallet
        
    df_warehouse['Pallet_Spaces'] = df_warehouse.apply(calc_pallets, axis=1)
    
    # Classify into Actionable Warehouse Space Categories
    def classify_velocity(row):
        stock = row['On_Hand_Stock']
        days_idle = row['Days_Since_Last_Move']
        recent_outflow = row[f'Outflow_{analysis_window_days}D']
        
        if stock <= 0:
            return 'Zero Stock'
        elif days_idle >= dead_stock_days and recent_outflow == 0:
            return 'Dead Stock (Space Hog)'
        elif days_idle >= 90 and recent_outflow < 5.0:
            return 'Slow Mover'
        else:
            return 'Fast / Active Mover'
            
    df_warehouse['Velocity_Class'] = df_warehouse.apply(classify_velocity, axis=1)
    df_warehouse['Last_Outflow_Str'] = df_warehouse['Last_Outflow_Date'].apply(
        lambda x: x.strftime('%Y-%m-%d') if x.year > 2020 else 'No Recorded Outflow'
    )
    
    return df_warehouse.sort_values(by=['Days_Since_Last_Move', 'Pallet_Spaces'], ascending=[False, False])


# ==========================================
# 3. HTML DASHBOARD WITH SUMMARY METRIC CARDS
# ==========================================
def generate_warehouse_dashboard(df_warehouse_results, output_filename="warehouse_space_audit.html"):
    """
    Generates an interactive HTML dashboard featuring top summary metric cards, 
    live search, velocity filters, and a Space Hogs toggle.
    """
    # Calculate Summary Metrics for Cards
    total_items = len(df_warehouse_results)
    dead_df = df_warehouse_results[df_warehouse_results['Velocity_Class'] == 'Dead Stock (Space Hog)']
    slow_df = df_warehouse_results[df_warehouse_results['Velocity_Class'] == 'Slow Mover']
    
    total_dead_skus = len(dead_df)
    total_dead_pallets = dead_df['Pallet_Spaces'].sum()
    total_slow_pallets = slow_df['Pallet_Spaces'].sum()
    total_wasted_pallets = total_dead_pallets + total_slow_pallets

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Warehouse Space & Pallet Footprint Audit</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f8f9fa; color: #333; }}
            h1 {{ font-size: 24px; margin-bottom: 5px; }}
            
            /* Metric Cards Styling */
            .metrics-container {{ display: flex; gap: 20px; margin-bottom: 20px; }}
            .metric-card {{ background: #fff; padding: 20px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); flex: 1; border-left: 5px solid #343a40; }}
            .metric-card.danger {{ border-left-color: #dc3545; }}
            .metric-card.warning {{ border-left-color: #ffc107; }}
            .metric-title {{ font-size: 13px; color: #666; text-transform: uppercase; font-weight: bold; margin-bottom: 5px; }}
            .metric-value {{ font-size: 24px; font-weight: bold; color: #212529; }}
            
            .controls {{ display: flex; gap: 15px; margin-bottom: 20px; align-items: center; background: #fff; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            input[type="text"], select {{ padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; width: 220px; }}
            table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #dee2e6; font-size: 14px; }}
            th {{ background: #343a40; color: #fff; }}
            tr:hover {{ background: #f1f3f5; }}
            .badge-dead {{ background: #f8d7da; color: #721c24; padding: 4px 8px; border-radius: 4px; font-weight: bold; }}
            .badge-slow {{ background: #fff3cd; color: #856404; padding: 4px 8px; border-radius: 4px; font-weight: bold; }}
            .badge-active {{ background: #d4edda; color: #155724; padding: 4px 8px; border-radius: 4px; }}
            .badge-zero {{ background: #e2e3e5; color: #383d41; padding: 4px 8px; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <h1>Warehouse Space & Pallet Footprint Audit</h1>
        <p style="color: #666; margin-bottom: 20px;">Tracking Rack Congestion, Slow Movers, and Dead Stock Footprint (Outflow to WIP / Tents)</p>
        
        <!-- Summary Metric Cards -->
        <div class="metrics-container">
            <div class="metric-card danger">
                <div class="metric-title">Dead Stock SKUs (180D Idle)</div>
                <div class="metric-value">{total_dead_skus:,}</div>
            </div>
            <div class="metric-card danger">
                <div class="metric-title">Dead Stock Pallet Spaces Wasted</div>
                <div class="metric-value">{total_dead_pallets:,.1f} Pallets</div>
            </div>
            <div class="metric-card warning">
                <div class="metric-title">Total Choked Footprint (Dead + Slow)</div>
                <div class="metric-value">{total_wasted_pallets:,.1f} Pallets</div>
            </div>
        </div>

        <div class="controls">
            <input type="text" id="searchInput" onkeyup="applyFilters()" placeholder="Search material, description, location...">
            
            <select id="velocityFilter" onchange="applyFilters()">
                <option value="ALL">All Velocity Classes</option>
                <option value="DEAD STOCK (SPACE HOG)">Dead Stock (Space Hog)</option>
                <option value="SLOW MOVER">Slow Mover</option>
                <option value="FAST / ACTIVE MOVER">Fast / Active Mover</option>
                <option value="ZERO STOCK">Zero Stock</option>
            </select>
            
            <label style="cursor: pointer; display: flex; align-items: center; gap: 5px;">
                <input type="checkbox" id="spaceHogsToggle" onclick="applyFilters()"> Space Hogs Only (Dead/Slow)
            </label>
        </div>

        <table id="warehouseTable">
            <thead>
                <tr>
                    <th>Material</th>
                    <th>Description</th>
                    <th>Location</th>
                    <th>On-Hand Stock</th>
                    <th>Est. Pallet Spaces</th>
                    <th>Last Outflow Date</th>
                    <th>Days Idle</th>
                    <th>Velocity Class</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for _, row in df_warehouse_results.iterrows():
        v_class = row['Velocity_Class']
        badge_class = "badge-active"
        if v_class == 'Dead Stock (Space Hog)':
            badge_class = "badge-dead"
        elif v_class == 'Slow Mover':
            badge_class = "badge-slow"
        elif v_class == 'Zero Stock':
            badge_class = "badge-zero"
            
        is_hog = 1 if v_class in ['Dead Stock (Space Hog)', 'Slow Mover'] else 0
            
        html_content += f"""
                <tr data-spacehog="{is_hog}">
                    <td>{row['Material']}</td>
                    <td>{row.get('Description', '')}</td>
                    <td>{row.get('Storage_Location', 'N/A')}</td>
                    <td>{row['On_Hand_Stock']:,.2f}</td>
                    <td><strong>{row['Pallet_Spaces']:,.1f}</strong></td>
                    <td>{row['Last_Outflow_Str']}</td>
                    <td>{row['Days_Since_Last_Move']:,}</td>
                    <td><span class="{badge_class}">{v_class}</span></td>
                </tr>
        """
        
    html_content += """
            </tbody>
        </table>

        <script>
        function applyFilters() {
            const searchInput = document.getElementById('searchInput').value.toUpperCase();
            const velocityFilter = document.getElementById('velocityFilter').value.toUpperCase();
            const spaceHogsOnly = document.getElementById('spaceHogsToggle').checked;
            
            const table = document.getElementById('warehouseTable');
            const rows = table.getElementsByTagName('tr');

            for (let i = 1; i < rows.length; i++) {
                const row = rows[i];
                const rowText = row.textContent.toUpperCase();
                const isSpaceHog = row.getAttribute('data-spacehog') === '1';
                
                let matchesSearch = rowText.includes(searchInput);
                let matchesVelocity = (velocityFilter === 'ALL' || rowText.includes(velocityFilter));
                let matchesSpaceHog = (!spaceHogsOnly || isSpaceHog);

                if (matchesSearch && matchesVelocity && matchesSpaceHog) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            }
        }
        </script>
    </body>
    </html>
    """
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Warehouse Pallet Footprint Dashboard generated: {output_filename}")


# ==========================================
# 4. MAIN EXECUTION PIPELINE
# ==========================================
if __name__ == '__main__':
    # 1. Load pallet capacities config
    pallet_capacities = load_pallet_capacities("pallet_capacity.csv")
    
    # 2. Initialize exception logger
    logger = WarehouseExceptionLogger("warehouse_exceptions.csv")
    
    print("Running Warehouse Pallet & Space Footprint Audit...")
    
    # Example execution hooks:
    # df_51 = pd.read_excel("MB51_export.XLSX")
    # df_52 = pd.read_excel("MB52_export.XLSX")
    
    # df_results = analyze_warehouse_velocity(df_52, df_51, pallet_capacities, dead_stock_days=180, analysis_window_days=90)
    # generate_warehouse_dashboard(df_results, "warehouse_space_audit.html")
