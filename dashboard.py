from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime, timedelta
import pytz

# Cargar configuraciones
def cargar_configuraciones():
    with open('config/servers.json') as f:
        SERVERS = json.load(f)
    with open('config/apis.json') as f:
        APIS = json.load(f)
    with open('config/general.json') as f:
        GENERAL_CONFIG = json.load(f)
    return SERVERS, APIS, GENERAL_CONFIG

SERVERS, APIS, GENERAL_CONFIG = cargar_configuraciones()

# Definir la ruta de la base de datos
DB_PATH = os.path.join(os.path.expanduser('~'), 'events.db')

app = Flask(__name__)
CORS(app)

def get_status_from_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, state FROM states")
    results = c.fetchall()
    conn.close()
    status = {name: json.loads(state) for name, state in results}
    print("Estado leído de la base de datos:", json.dumps(status, indent=2))
    return status

def get_events(limit=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if limit:
        c.execute("SELECT timestamp, message FROM events ORDER BY id DESC LIMIT ?", (limit,))
    else:
        c.execute("SELECT timestamp, message FROM events ORDER BY id DESC")
    events = [{"timestamp": row[0], "message": row[1]} for row in c.fetchall()]
    conn.close()
    return events

@app.route('/')
def dashboard():
    return render_template('dashboard.html', config=GENERAL_CONFIG)

@app.route('/servers')
def servers():
    return render_template('servers.html', config=GENERAL_CONFIG, servers=SERVERS)

@app.route('/apis')
def apis():
    return render_template('apis.html', config=GENERAL_CONFIG)

@app.route('/api/dashboard-data')
def api_dashboard_data():
    page = request.args.get('page', 1, type=int)
    events_per_page = GENERAL_CONFIG['dashboard']['max_events_displayed']
    status = get_status_from_db()
    event_log = get_events()
    total_events = len(event_log)
    
    # Depuración: imprimir el estado completo
    print("Estado completo:", json.dumps(status, indent=2))
    
    data = {
        'servers': [
            {
                **server,
                'status': status.get(f"ssh_{server['name']}", False),
                'info': status.get(f"{server['name']}_info", {}),
                'load_state': status.get(f"{server['name']}_load_state", ''),
                'ram_state': status.get(f"{server['name']}_ram_state", ''),
                'disk_states': {
                    disk: status.get(f"{server['name']}_disk_usage_{disk.replace('/', '_')}_state", '')
                    for disk in server.get('disks', [])
                }
            }
            for server in SERVERS
        ],
        'apis': [
            {
                **api,
                'status': status.get(f"api_{api['name']}", False)
            }
            for api in APIS
        ],
        'event_log': event_log[(page-1)*events_per_page:page*events_per_page],
        'total_events': total_events,
        'current_page': page,
        'total_pages': (total_events + events_per_page - 1) // events_per_page,
        'events_per_page': events_per_page,
        'overallStatus': status.get('overall_status', 'Desconocido')
    }
    
    # Depuración: imprimir los datos que se envían al frontend
    print("Datos enviados al frontend:", json.dumps(data, indent=2))
    
    return jsonify(data)

@app.route('/api/historical-data')
def api_historical_data():
    name = request.args.get('name')
    minutes = request.args.get('minutes', default=60, type=int)
    data = get_historical_data(name, minutes)
    if isinstance(data, tuple):  # Error case
        return jsonify(data[0]), data[1]
    return jsonify(data)

def get_historical_data(name, minutes):
    if not name:
        return {"error": "Se requiere el parámetro 'name'"}, 400
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=minutes)
    query = "SELECT timestamp, state FROM historical_states WHERE name = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp"
    c.execute(query, (name, start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S')))
    results = c.fetchall()
    conn.close()
    
    historical_data = [{"timestamp": row[0], "state": json.loads(row[1])} for row in results]
    return historical_data

@app.route('/api/multi-historical-data')
def api_multi_historical_data():
    name = request.args.get('name')
    if not name:
        return jsonify({"error": "Se requiere el parámetro 'name'"}), 400
    
    data = {
        '5min': get_historical_data(name, 5),
        '15min': get_historical_data(name, 15),
        '30min': get_historical_data(name, 30),
        '60min': get_historical_data(name, 60)
    }
    return jsonify(data)

@app.route('/api/server-historical-data')
def api_server_historical_data():
    server_name = request.args.get('server')
    resource = request.args.get('resource')
    if not server_name or not resource:
        return jsonify({"error": "Se requieren los parámetros 'server' y 'resource'"}), 400
    
    def get_data_for_range(minutes):
        return get_historical_data(f"{server_name}_{resource}", minutes)
    
    data = {
        '5min': get_data_for_range(5),
        '15min': get_data_for_range(15),
        '30min': get_data_for_range(30),
        '60min': get_data_for_range(60)
    }
    return jsonify(data)

if __name__ == '__main__':
    port = GENERAL_CONFIG['dashboard'].get('port', 9000)
    app.run(debug=True, host='0.0.0.0', port=port)