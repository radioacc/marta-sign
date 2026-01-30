import os
import datetime
import requests
import json
from flask import Flask, render_template, request, jsonify

# --- TOGGLE SETTINGS ---
ENABLE_DATABASE = False 

if ENABLE_DATABASE:
    try:
        import sqlite3
    except ImportError:
        ENABLE_DATABASE = False
        print("⚠️ sqlite3 module not found. Database features have been auto-disabled.")

# --- COPYRIGHT AND MISC INFO ---
# Copyright (C) 2025-2026 Adam Caskey
# Modified by Assistant on 2025-05-22 to update status labels and UI components.
# Licensed under GNU General Public License Version 3

# --- CONFIGURATION ---
API_KEY = os.environ.get('MARTA_API_KEY', 'PASTE_YOUR_API_KEY_HERE')
DEFAULT_STATION = "MIDTOWN"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'marta_schedule.db')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

CACHE = {'all_trains': [], 'last_updated': None}
CACHE_DURATION = 15

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/New_York")
except Exception:
    TZ = datetime.datetime.now().astimezone().tzinfo

app = Flask(__name__)

def get_db_connection():
    if not ENABLE_DATABASE:
        return None
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

def fetch_marta_data():
    global CACHE
    now = datetime.datetime.now()
    
    if CACHE['last_updated'] and (now - CACHE['last_updated']).total_seconds() < CACHE_DURATION:
        return

    urls = [
        f"https://developerservices.itsmarta.com:18096/itsmarta/railrealtimearrivals/developerservices/traindata?apiKey={API_KEY}",
        f"http://developer.itsmarta.com/RealtimeTrain/RestServiceNextTrain/GetRealtimeArrivals?apikey={API_KEY}"
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    for key in ['Trains', 'trains', 'TRAINS']:
                        if key in data:
                            data = data[key]
                            break
                if isinstance(data, dict): data = [data]
                if isinstance(data, list):
                    CACHE['all_trains'] = data
                    CACHE['last_updated'] = now
                    return
        except Exception as e:
            print(f"⚠️ API Attempt Failed: {e}")

def get_realtime_trains(station_name):
    fetch_marta_data()
    target = station_name.upper().replace(" STATION", "")
    results = []

    for t in CACHE['all_trains']:
        try:
            t_station = (t.get('STATION') or t.get('Station') or "").upper()
            if target in t_station:
                results.append({
                    'station': t_station,
                    'destination': clean_dest(t.get('DESTINATION') or t.get('Destination')),
                    'line': t.get('LINE') or t.get('Line'),
                    'direction': t.get('DIRECTION') or t.get('Direction'),
                    'waiting_time': t.get('WAITING_TIME') or t.get('WaitingTime'),
                    'waiting_seconds': t.get('WAITING_SECONDS') or t.get('WaitingSeconds') or "9999",
                    'status': 'Realtime'
                })
        except Exception: continue

    results.sort(key=lambda x: int(x['waiting_seconds']) if str(x['waiting_seconds']).isdigit() else 9999)
    return results

@app.route('/')
def home():
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
        trains = get_realtime_trains(station)
        return jsonify(trains)
    except Exception as e:
        print(f"🔥 Error: {e}")
        return jsonify([]) 

if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Serving on http://0.0.0.0:{port}")
    serve(app, host='0.0.0.0', port=port)
