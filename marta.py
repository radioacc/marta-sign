import os
import datetime
import requests
from flask import Flask, render_template, request, jsonify

# --- TOGGLE SETTINGS ---
ENABLE_DATABASE = False 

# --- CONFIGURATION ---
API_KEY = os.environ.get('MARTA_API_KEY', 'PASTE_YOUR_API_KEY_HERE')
DEFAULT_STATION = "MIDTOWN"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# HEADERS (Required to look like a browser)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- CACHE ---
CACHE = {'all_trains': [], 'last_updated': None}
CACHE_DURATION = 15

app = Flask(__name__)

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
                if isinstance(data, list):
                    CACHE['all_trains'] = data
                    CACHE['last_updated'] = now
                    return
        except Exception as e:
            print(f"⚠️ API Connection Error: {e}")

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
        fetch_marta_data()
        target = station.upper()
        results = []
        for t in CACHE['all_trains']:
            t_station = (t.get('STATION') or t.get('Station') or "").upper()
            if target in t_station:
                results.append({
                    'destination': clean_dest(t.get('DESTINATION') or t.get('Destination')),
                    'line': t.get('LINE') or t.get('Line'),
                    'direction': t.get('DIRECTION') or t.get('Direction'),
                    'waiting_time': t.get('WAITING_TIME') or t.get('WaitingTime'),
                    'waiting_seconds': t.get('WAITING_SECONDS') or t.get('WaitingSeconds') or "9999"
                })
        results.sort(key=lambda x: int(x['waiting_seconds']) if str(x['waiting_seconds']).isdigit() else 9999)
        return jsonify(results)
    except Exception as e:
        return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
