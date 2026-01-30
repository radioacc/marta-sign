import os
import datetime
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- CONFIG ---
API_KEY = os.environ.get('MARTA_API_KEY', 'PASTE_YOUR_API_KEY_HERE')
DEFAULT_STATION = "MIDTOWN"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
CACHE = {'all_trains': [], 'last_updated': None}

def fetch_data():
    global CACHE
    now = datetime.datetime.now()
    if CACHE['last_updated'] and (now - CACHE['last_updated']).total_seconds() < 15:
        return
    url = f"http://developer.itsmarta.com/RealtimeTrain/RestServiceNextTrain/GetRealtimeArrivals?apikey={API_KEY}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            CACHE['all_trains'] = resp.json()
            CACHE['last_updated'] = now
    except Exception as e: print(f"Error: {e}")

@app.route('/')
def home():
    STATIONS = sorted(["AIRPORT", "ARTS CENTER", "ASHBY", "AVONDALE", "BANKHEAD", "BROOKHAVEN", "BUCKHEAD", "CHAMBLEE", "CIVIC CENTER", "COLLEGE PARK", "DECATUR", "DORAVILLE", "DUNWOODY", "EAST LAKE", "EAST POINT", "EDGEWOOD CANDLER PARK", "FIVE POINTS", "GARNETT", "GEORGIA STATE", "HAMILTON E HOLMES", "INDIAN CREEK", "INMAN PARK", "KENSINGTON", "KING MEMORIAL", "LAKEWOOD", "LENOX", "LINDBERGH", "MEDICAL CENTER", "MIDTOWN", "NORTH AVENUE", "NORTH SPRINGS", "OAKLAND CITY", "PEACHTREE CENTER", "SANDY SPRINGS", "VINE CITY", "WEST END", "WEST LAKE"])
    return render_template('index.html', stations=STATIONS, initial_station=DEFAULT_STATION)

@app.route('/api/arrivals')
def api_arrivals():
    station = request.args.get('station', DEFAULT_STATION).upper()
    fetch_data()
    results = []
    for t in CACHE['all_trains']:
        if station in t.get('STATION', '').upper():
            results.append({
                'destination': t.get('DESTINATION', '').title(),
                'line': t.get('LINE'),
                'direction': t.get('DIRECTION'),
                'waiting_time': t.get('WAITING_TIME'),
                'waiting_seconds': t.get('WAITING_SECONDS', '9999')
            })
    results.sort(key=lambda x: int(x['waiting_seconds']) if x['waiting_seconds'].isdigit() else 9999)
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
