# Disclaimer: This script was written with the help of Microsoft Copilot. 

import os
import csv
import sqlite3
from datetime import datetime

# --- CONFIG ---
csv_file = input("Enter the path to your CSV file: ").strip()

if not os.path.isfile(csv_file):
    print(f"Error: File '{csv_file}' not found.")
    exit(1)

db_file = "electric_usage.db"

# --- CONNECT TO DATABASE ---
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

# --- CREATE TABLE ---
cursor.execute("DROP TABLE IF EXISTS usage")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE,
    start_time TIME,
    end_time TIME,
    import_kwh REAL,
    pmo CHAR(1)
)
""")
conn.commit()

# --- PARSE FUNCTION ---
def parse_row(row, headers):
    try:
        date_str = row[headers['DATE']].strip()
        start_str = row[headers['START TIME']].strip() + ":00"
        end_str = row[headers['END TIME']].strip() + ":00"
        import_kwh = float(row[headers['IMPORT (KWH)']])
        return (date_str, start_str, end_str, import_kwh)
    except Exception as e:
        print("Skipping row due to error:", e)
        return None

# --- LOAD AND INSERT DATA ---
with open(csv_file, newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    
    # Skip first 6 rows
    for _ in range(6):
        next(reader)
    
    # Read header and normalize
    raw_headers = next(reader)
    headers = {col.strip().upper().replace('\ufeff', ''): idx for idx, col in enumerate(raw_headers)}
    
    records = []
    for row in reader:
        parsed = parse_row(row, headers)
        if parsed:
            records.append(parsed)

    cursor.executemany("""
        INSERT INTO usage (date, start_time, end_time, import_kwh)
        VALUES (?, ?, ?, ?)
    """, records)

conn.commit()

# --- UPDATE TOU RATES ---
cursor.execute("""
UPDATE usage
SET pmo = CASE

    -- Sunday and Holidays mid-peak from 06:00 to 23:59
    WHEN (
        strftime('%w', date) = '0' OR
        date IN (
            -- 2024 Holidays
            '2024-01-01', '2024-01-15', '2024-02-19', '2024-05-27',
            '2024-06-19', '2024-07-04', '2024-09-02', '2024-10-14',
            '2024-11-11', '2024-11-28', '2024-11-29', '2024-12-25',

            -- 2025 Holidays
            '2025-01-01', '2025-01-20', '2025-02-17', '2025-05-26',
            '2025-06-19', '2025-07-04', '2025-09-01', '2025-10-13',
            '2025-11-11', '2025-11-27', '2025-11-28', '2025-12-25'
            )
    ) AND start_time >= '06:00:00' AND end_time < '24:00:00' THEN 'm'

    -- Off-peak: midnight to 06:00
    WHEN start_time >= '00:00:00' AND end_time < '06:00:00' THEN 'o'

    -- Peak: 17:00 to 21:00
    WHEN start_time >= '17:00:00' AND end_time < '21:00:00' THEN 'p'

    -- Mid-peak: 06:00 to 17:00 and 21:00 to midnight
    WHEN (start_time >= '06:00:00' AND end_time < '17:00:00') OR (start_time >= '21:00:00' AND end_time < '24:00:00') THEN 'm'
    
    ELSE NULL
END;
""")
conn.commit()

# --- (debug) PRINT RESULTS ---
#cursor.execute("SELECT * FROM usage LIMIT 100")
#for row in cursor.fetchall():
#    print(row)

# --- PRINT ORIGINAL COST ---
cursor.execute("SELECT SUM(import_kwh) FROM usage")
total_kwh = cursor.fetchone()[0] or 0.0  # Handle None if table is empty
print(f"Total usage: {total_kwh:.2f} kWh")

# Rate per kWh
rate = 0.1375
total_cost = total_kwh * rate

# Print result
print(f"Pre-TOU cost: ${total_cost:.2f}\n")

# --- PRINT TOTAL USAGE BY TOU ---
# Define rates
rates = {
    'p': 0.1656,  # Peak
    'm': 0.1449,  # Mid
    'o': 0.0828   # Off-peak
}

# Query total import_kwh per PMO category
cursor.execute("""
    SELECT pmo, SUM(import_kwh)
    FROM usage
    GROUP BY pmo
""")

# Calculate total cost
tou_cost = 0.0
for pmo, kwh in cursor.fetchall():
    rate = rates.get(pmo, 0.0)
    cost = kwh * rate
    print(f"{pmo.upper()} usage: {kwh:.2f} kWh × ${rate:.4f}/kWh = ${cost:.2f}")
    tou_cost += cost

print(f"Post-TOU cost: ${tou_cost:.2f}")

conn.close()


# --- PRINT OUTCOME ---#
print(f"\nYour savings: ${total_cost - tou_cost:.2f}")

# --- CLEANUP SQLITE DB FILE ---
if os.path.exists(db_file):
    os.remove(db_file)
else:
    print(f"File not found: {db_file}")
