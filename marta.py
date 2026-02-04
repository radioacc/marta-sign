import os
import datetime
import sqlite3
import requests
import json
from flask import Flask, render_template, request, jsonify

# --- CONFIGURATION ---
API_KEY = os.environ.get('MARTA_API_KEY', 'PASTE_YOUR_API_KEY_HERE')
DEFAULT_STATION = "MIDTOWN"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'marta_schedule.db')

# HEADERS (Required to look like a browser)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- CACHE ---
CACHE = {'all_trains': [], 'last_updated': None}
CACHE_DURATION = 15

# --- TIMEZONE SAFETY ---
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/New_York")
except Exception:
    TZ = datetime.datetime.now().astimezone().tzinfo

app = Flask(__name__)

# --- HELPER FUNCTIONS ---
def get_db_connection():
    try:
        if not os.path.exists(DB_PATH): return None
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row 
        return conn
    except: return None

def clean_dest(text):
    if not text: return ""
    d = str(text).upper().replace(" STATION", "")
    for p in ["RED NORTHBOUND TO ", "RED SOUTHBOUND TO ", "GOLD NORTHBOUND TO ", "GOLD SOUTHBOUND TO ", "BLUE EASTBOUND TO ", "BLUE WESTBOUND TO ", "GREEN EASTBOUND TO ", "GREEN WESTBOUND TO "]:
        d = d.replace(p, "")
    return d.title()

def parse_gtfs_time(time_str):
    try:
        hours, minutes, seconds = map(int, time_str.split(':'))
        days = 0
        if hours >= 24:
            days = hours // 24
            hours = hours % 24
        return datetime.time(hours, minutes, seconds), days
    except: return None, 0

# Add this near the CACHE definition
DEPARTED = {}  # {train_id: {'timestamp': datetime, 'station': str, 'data': dict}}

# --- ROBUST FETCH FUNCTION ---
def fetch_marta_data():
    global CACHE, DEPARTED
    now = datetime.datetime.now()
    
    # Cache Check
    if CACHE['last_updated'] and (now - CACHE['last_updated']).total_seconds() < CACHE_DURATION:
        return

    previous_trains = {t.get('TRAIN_ID'): t for t in CACHE['all_trains'] if t.get('TRAIN_ID')}  # Backup previous data

    # Try Both URLs
    urls = [
        f"https://developerservices.itsmarta.com:18096/itsmarta/railrealtimearrivals/developerservices/traindata?apiKey={API_KEY}",
        f"https://developer.itsmarta.com/RealtimeTrain/RestServiceNextTrain/GetRealtimeArrivals?apiKey={API_KEY}"
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            print(f"Trying URL: {url}")
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    print(f"Data type: {type(data)}")
                    if isinstance(data, dict):
                        print(f"Dict keys: {list(data.keys())}")
                    elif isinstance(data, list):
                        print(f"List length: {len(data)}")
                    else:
                        print(f"Unexpected data: {data}")
                    
                    # Unwrap dictionary if needed
                    if isinstance(data, dict):
                        for key in ['Trains', 'trains', 'TRAINS', 'data', 'Data', 'results', 'Results']:
                            if key in data:
                                data = data[key]
                                print(f"Unwrapped using key: {key}")
                                break
                    
                    # Handle single object vs list
                    if isinstance(data, dict) and ('DESTINATION' in data or 'Destination' in data):
                        data = [data]
                        print("Converted single dict to list")

                    if isinstance(data, list):
                        # Detect departed trains
                        current_train_ids = {t.get('TRAIN_ID') for t in data if t.get('TRAIN_ID')}
                        for train_id, prev_data in previous_trains.items():
                            if train_id not in current_train_ids:
                                DEPARTED[train_id] = {
                                    'timestamp': now,
                                    'station': prev_data.get('STATION', ''),
                                    'data': prev_data
                                }
                        
                        # Clean up old departed entries (>30 seconds)
                        to_remove = [tid for tid, info in DEPARTED.items() if (now - info['timestamp']).total_seconds() > 30]
                        for tid in to_remove:
                            del DEPARTED[tid]

                        CACHE['all_trains'] = data
                        CACHE['last_updated'] = now
                        print("Data cached successfully")
                        return
                    else:
                        print("Data is not a list, skipping")
                except Exception as json_e:
                    print(f"JSON parse error: {json_e}, Response text: {resp.text[:500]}")
            else:
                print(f"Non-200 status, response: {resp.text[:500]}")
        except Exception as e:
            print(f"Request failed: {e}")
    
    print("❌ All API attempts failed (or no trains running).")

def get_realtime_trains(station_name):
    fetch_marta_data()
    target = station_name.upper().replace(" STATION", "")
    results = []

    # Add current trains
    for t in CACHE['all_trains']:
        try:
            if not isinstance(t, dict): continue

            t_station = (t.get('STATION') or t.get('Station') or "").upper()
            t_dest = t.get('DESTINATION') or t.get('Destination')
            t_line = t.get('LINE') or t.get('Line')
            t_dir = t.get('DIRECTION') or t.get('Direction')
            t_wait = t.get('WAITING_SECONDS') or t.get('WaitingSeconds') or "9999"
            t_time = t.get('WAITING_TIME') or t.get('WaitingTime')

            if target in t_station:
                print(f"DEBUG: WAITING_TIME = '{t_time}' for train {t.get('TRAIN_ID', 'unknown')} at {t_station}")  # Add this
                
                # Determine status
                if t_time in ["Arriving", "Boarding"]:
                    status = t_time
                else:
                    status = 'Realtime'  # Or change to status = t_time if you want to show the time
                
                results.append({
                    'station': t_station,
                    'destination': clean_dest(t_dest),
                    'line': t_line,
                    'direction': t_dir,
                    'waiting_time': t_time,
                    'waiting_seconds': t_wait,
                    'status': status
                })
        except Exception: continue


    # Add departed trains for this station (within 30 seconds)
    now = datetime.datetime.now()
    for train_id, info in DEPARTED.items():
        if target in info['station'].upper() and (now - info['timestamp']).total_seconds() <= 30:
            dep_data = info['data']
            results.append({
                'station': info['station'],
                'destination': clean_dest(dep_data.get('DESTINATION', '')),
                'line': dep_data.get('LINE', ''),
                'direction': dep_data.get('DIRECTION', ''),
                'waiting_time': 'Departing',
                'waiting_seconds': '0',  # Treat as immediate
                'status': 'Departing'
            })

    results.sort(key=lambda x: int(x['waiting_seconds']) if str(x['waiting_seconds']).isdigit() else 9999)
    return results

# --- SCHEDULE DATABASE LOGIC (Restored) ---
def get_backup_schedule(station_name, limit=6):
    conn = get_db_connection()
    if not conn: return []
    
    try:
        cursor = conn.cursor()
        now = datetime.datetime.now(TZ)
        current_time_str = now.strftime("%H:%M:%S")
        
        # Determine Day (Simple Logic)
        day_name = now.strftime("%A").lower()
        today_date = now.date()
        # Holiday overrides (Example)
        if today_date == datetime.date(2025, 11, 27): day_name = 'sunday'
        elif today_date == datetime.date(2025, 11, 28): day_name = 'saturday'

        # Get Stop IDs
        cursor.execute("SELECT stop_id FROM stops WHERE stop_name LIKE ?", (f"%{station_name}%",))
        stop_ids = [row['stop_id'] for row in cursor.fetchall()]
        if not stop_ids: return []
        
        placeholders = ','.join('?' * len(stop_ids))
        
        # Query next scheduled trains
        query = f"""
            SELECT r.route_long_name as line, t.trip_headsign as destination, 
                   t.direction_id, st.arrival_time
            FROM stop_times st
            JOIN trips t ON st.trip_id = t.trip_id
            JOIN routes r ON t.route_id = r.route_id
            JOIN calendar c ON t.service_id = c.service_id
            WHERE st.stop_id IN ({placeholders})
              AND st.arrival_time > ?
              AND c.{day_name} = 1
            ORDER BY st.arrival_time ASC
            LIMIT ?
        """
        cursor.execute(query, stop_ids + [current_time_str, limit])
        rows = cursor.fetchall()
        
        scheduled = []
        for row in rows:
            display_time = row['arrival_time']
            try:
                t_obj, days = parse_gtfs_time(row['arrival_time'])
                if t_obj:
                    target = now.date() + datetime.timedelta(days=days)
                    arr_dt = datetime.datetime.combine(target, t_obj).replace(tzinfo=TZ)
                    diff = (arr_dt - now).total_seconds() / 60
                    display_time = f"{int(diff)} min" if diff > 0 else "0 min"
            except: pass
            
            line_raw = row['line'].upper()
            line_color = 'GRAY'
            if 'RED' in line_raw: line_color = 'RED'
            elif 'GOLD' in line_raw: line_color = 'GOLD'
            elif 'BLUE' in line_raw: line_color = 'BLUE'
            elif 'GREEN' in line_raw: line_color = 'GREEN'

            direction_code = 'N' if row['direction_id'] == 1 else 'S' 
            if 'East' in line_raw: direction_code = 'E'
            if 'West' in line_raw: direction_code = 'W'

            scheduled.append({
                'station': station_name,
                'destination': clean_dest(row['destination']),
                'line': line_color,
                'direction': direction_code,
                'waiting_time': display_time,
                'waiting_seconds': 99999, # Push to bottom
                'status': 'Scheduled'
            })
        return scheduled
    except Exception as e:
        print(f"DB Error: {e}")
        return []
    finally:
        if conn: conn.close()

# --- ROUTES ---
@app.route('/')
def home():
    # Pass full station list for dropdown
    STATION_LIST = sorted([
        "AIRPORT", "ARTS CENTER", "ASHBY", "AVONDALE", "BANKHEAD", "BROOKHAVEN", 
        "BUCKHEAD", "CHAMBLEE", "CIVIC CENTER", "COLLEGE PARK", "DECATUR", 
        "DORAVILLE", "DUNWOODY", "EAST LAKE", "EAST POINT", "EDGEWOOD CANDLER PARK", 
        "FIVE POINTS", "GARNETT", "GEORGIA STATE", "GOLD DOME", "HAMILTON E HOLMES", 
        "INDIAN CREEK", "INMAN PARK", "KENSINGTON", "KING MEMORIAL", "LAKEWOOD", 
        "LENOX", "LINDBERGH", "MEDICAL CENTER", "MIDTOWN", "NORTH AVENUE", 
        "NORTH SPRINGS", "OAKLAND CITY", "PEACHTREE CENTER", "SANDY SPRINGS", 
        "VINE CITY", "WEST END", "WEST LAKE"
    ])
    return render_template('index.html', stations=STATION_LIST, initial_station=DEFAULT_STATION)

@app.route('/api/arrivals')
def api_arrivals():
    try:
        station = request.args.get('station', DEFAULT_STATION)
        
        # 1. Get Realtime
        trains = get_realtime_trains(station)
        
        # 2. Get Schedule Backup (if we have fewer than 6 trains)
        if len(trains) < 6:
            backups = get_backup_schedule(station, limit=10)
            needed = 6 - len(trains)
            added = 0
            
            for b in backups:
                if added >= needed: break
                
                # Deduplicate: Don't add if a Realtime train already exists for this dest/dir
                is_duplicate = False
                for r in trains:
                    if r['destination'] == b['destination'] and r['direction'] == b['direction']:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    trains.append(b)
                    added += 1

        return jsonify(trains)
    except Exception as e:
        print(f"🔥 CRITICAL ERROR: {e}")
        return jsonify([]) 

if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Serving on http://0.0.0.0:{port}")
    serve(app, host='0.0.0.0', port=port)