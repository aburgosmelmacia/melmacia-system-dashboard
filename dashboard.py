import json
import os
import paramiko
import requests
from pymsteams import connectorcard
from dotenv import load_dotenv
from datetime import datetime
import sqlite3
import pytz
import threading
from paramiko import SSHConfig, ProxyCommand
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import logging

load_dotenv()

# Lock para operaciones thread-safe
status_lock = threading.Lock()

# Definir la ruta de la base de datos en un lugar persistente
DB_PATH = os.path.join(os.path.expanduser('~'), 'events.db')

# Definir umbrales para los recursos
load_thresholds = {'warning': 0.7, 'critical': 1.0}
ram_thresholds = {'warning': 70, 'critical': 85}
disk_thresholds = {'warning': 70, 'critical': 85}

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def cargar_configuraciones():
    """
    Carga las configuraciones desde los archivos JSON.
    
    Returns:
        tuple: SERVERS, APIS, GENERAL_CONFIG
    """
    with open('config/servers.json') as f:
        SERVERS = json.load(f)
    with open('config/apis.json') as f:
        APIS = json.load(f)
    with open('config/general.json') as f:
        GENERAL_CONFIG = json.load(f)
    return SERVERS, APIS, GENERAL_CONFIG

# Inicializar las configuraciones
SERVERS, APIS, GENERAL_CONFIG = cargar_configuraciones()

def check_ssh(server):
    """
    Establece una conexión SSH con el servidor especificado.
    
    Args:
        server (dict): Diccionario con la configuración del servidor.
    
    Returns:
        paramiko.SSHClient or None: Cliente SSH conectado o None si falla la conexión.
    """
    try:
        # Cargar la configuración SSH del usuario
        ssh_config = SSHConfig()
        user_config_file = os.path.expanduser("~/.ssh/config")
        if os.path.exists(user_config_file):
            with open(user_config_file) as f:
                ssh_config.parse(f)

        # Obtener la configuración para el servidor
        host_config = ssh_config.lookup(server['ssh']['hostname'])

        # Crear el cliente SSH
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Configurar la conexión
        connect_kwargs = {}
        if 'hostname' in host_config:
            connect_kwargs['hostname'] = host_config['hostname']
        elif 'host' in host_config:
            connect_kwargs['hostname'] = host_config['host']
        if 'user' in host_config:
            connect_kwargs['username'] = host_config['user']
        if 'port' in host_config:
            connect_kwargs['port'] = int(host_config['port'])
        if 'identityfile' in host_config:
            connect_kwargs['key_filename'] = host_config['identityfile'][0]
        if 'proxycommand' in host_config:
            connect_kwargs['sock'] = ProxyCommand(host_config['proxycommand'])

        # Conectar
        client.connect(**connect_kwargs)
        return client
    except Exception as e:
        logging.error(f"Error de conexión SSH para {server['name']}: {str(e)}")
        return None

def check_api(api):
    """
    Verifica el estado de una API.
    
    Args:
        api (dict): Diccionario con la configuración de la API.
    
    Returns:
        bool: True si la API está activa, False en caso contrario.
    """
    try:
        if api['requires_ssh']:
            server = next(s for s in SERVERS if s['name'] == api['server'])
            ssh_client = check_ssh(server)
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command(f"curl -s -o /dev/null -w '%{{http_code}}' {api['url']}")
                status_code = stdout.read().decode().strip()
                ssh_client.close()
                return status_code == "200"
        else:
            response = requests.get(api['url'], timeout=5)  # Añadir un timeout
            return response.status_code == 200
    except Exception as e:
        logging.error(f"Error al verificar API {api['name']}: {str(e)}")
        return False

def add_event(message):
    """
    Añade un evento a la base de datos.
    
    Args:
        message (str): Mensaje del evento.
    """
    madrid_tz = pytz.timezone('Europe/Madrid')
    timestamp = datetime.now(madrid_tz).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO events (timestamp, message) VALUES (?, ?)", (timestamp, message))
    conn.commit()
    conn.close()

def send_teams_alert(message, general_config):
    """
    Envía una alerta a Microsoft Teams si las notificaciones están habilitadas.
    
    Args:
        message (str): Mensaje de la alerta.
    """
    if general_config['notifications']['enabled']:
        teams_webhook = os.getenv('TEAMS_WEBHOOK')
        myTeamsMessage = connectorcard(teams_webhook)
        myTeamsMessage.text(message)
        myTeamsMessage.send()
        logging.info(f"Alerta enviada: {message}")
    add_event(f"Alerta: {message}")

def get_server_info(ssh_client, disks):
    """
    Obtiene información del servidor mediante SSH.
    
    Args:
        ssh_client (paramiko.SSHClient): Cliente SSH conectado.
        disks (list): Lista de discos a monitorear.
    
    Returns:
        dict: Información del servidor.
    """
    server_info = {}
    
    # Obtener el tiempo de arranque
    stdin, stdout, stderr = ssh_client.exec_command("cat /proc/uptime")
    uptime = float(stdout.read().decode().split()[0])
    
    # Tiempo en marcha
    server_info["uptime"] = f"{int(uptime // 86400)} días, {int((uptime % 86400) // 3600)} horas, {int((uptime % 3600) // 60)} minutos"
    
    # Carga actual
    stdin, stdout, stderr = ssh_client.exec_command("cat /proc/loadavg")
    load = stdout.read().decode().split()[:3]
    server_info["load"] = f"{load[0]}, {load[1]}, {load[2]}"
    
    # Memoria RAM utilizada
    stdin, stdout, stderr = ssh_client.exec_command("free -m | awk '/Mem:/ {print $3,$2}'")
    mem = stdout.read().decode().split()
    server_info["ram_usage"] = f"{int(mem[0])/int(mem[1])*100:.2f}% ({int(mem[0])} MB / {int(mem[1])} MB)"
    
    # Espacio de disco
    stdin, stdout, stderr = ssh_client.exec_command(f"df -h {' '.join(disks)}")
    disk_info = stdout.read().decode().splitlines()[1:]
    for line in disk_info:
        parts = line.split()
        server_info[f"disk_usage_{parts[5].replace('/', '_')}"] = f"{parts[4]} ({parts[2]} / {parts[1]})"
    
    return server_info

def check_resource_state(current_value, thresholds, resource_name, server_name):
    def extract_percentage(value):
        if isinstance(value, str):
            import re
            match = re.search(r'(\d+(\.\d+)?)%', value)
            if match:
                return float(match.group(1))
        return value

    try:
        current_value = extract_percentage(current_value)
        if isinstance(current_value, str):
            current_value = float(current_value)
    except ValueError:
        logging.error(f"Error al convertir {current_value} a float para {resource_name}")
        return None

    if current_value >= thresholds['critical']:
        new_state = 'critical'
    elif current_value >= thresholds['warning']:
        new_state = 'warning'
    else:
        new_state = 'good'
    
    state_key = f"{server_name}_{resource_name}_state"
    last_state = load_saved_state(state_key)
    
    if new_state != last_state:
        message = f"El {resource_name} de {server_name} ha cambiado a estado {new_state}: {current_value:.2f}%"
        send_teams_alert(message, GENERAL_CONFIG)
        add_event(message)
        save_state(state_key, new_state)
        logging.info(f"Cambio de estado detectado: {message}")
    else:
        logging.debug(f"No hay cambio de estado para {resource_name} de {server_name}")
    
    return new_state

def check_status():
    # Recargar configuraciones antes de cada comprobación
    global SERVERS, APIS, GENERAL_CONFIG
    SERVERS, APIS, GENERAL_CONFIG = cargar_configuraciones()
    
    status = {}
    
    for server in SERVERS:
        ssh_client = check_ssh(server)
        server_status = ssh_client is not None
        status[f"ssh_{server['name']}"] = server_status
        
        if server_status:
            server_info = get_server_info(ssh_client, server['disks'])
            status[f"{server['name']}_info"] = server_info
            ssh_client.close()
            
            # Actualizar estados de los recursos
            load_value = float(server_info.get('load', '0').split(',')[0])
            status[f"{server['name']}_load_state"] = check_resource_state(load_value, load_thresholds, 'carga del sistema', server['name'])
            
            ram_usage = float(server_info.get('ram_usage', '0%').split('%')[0])
            status[f"{server['name']}_ram_state"] = check_resource_state(ram_usage, ram_thresholds, 'uso de RAM', server['name'])
            
            for disk in server['disks']:
                disk_key = f"disk_usage_{disk.replace('/', '_')}"
                disk_usage = float(server_info.get(disk_key, '0%').split('%')[0])
                status[f"{server['name']}_{disk_key}_state"] = check_resource_state(disk_usage, disk_thresholds, f'uso de disco {disk}', server['name'])
        else:
            logging.warning(f"No se pudo conectar al servidor {server['name']}")
    
    for api in APIS:
        api_status = check_api(api)
        status[f"api_{api['name']}"] = api_status
        
        state_key = f"api_{api['name']}_state"
        last_state = load_saved_state(state_key)
        if api_status != last_state:
            message = f"El estado de la API {api['name']} ha cambiado a {'activo' if api_status else 'inactivo'}"
            send_teams_alert(message, GENERAL_CONFIG)
            add_event(message)
            save_state(state_key, api_status)
            logging.info(f"Cambio de estado de API detectado: {message}")
        else:
            logging.debug(f"No hay cambio de estado para la API {api['name']}")
    
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

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  message TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS states
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  state TEXT)''')
    conn.commit()
    conn.close()

def save_state(name, state):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO states (name, state) VALUES (?, ?)", (name, json.dumps(state)))
    conn.commit()
    conn.close()

def load_saved_state(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT state FROM states WHERE name = ?", (name,))
    result = c.fetchone()
    conn.close()
    if result:
        try:
            return json.loads(result[0])
        except json.JSONDecodeError:
            return result[0]
    return None

def clean_old_events():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE timestamp < date('now', ?)", (f"-{GENERAL_CONFIG['log_retention_days']} days",))
    conn.commit()
    conn.close()

def get_overall_status():
    # Implementa la lógica para determinar el estado general
    return 'Estable'  # o 'Crítico', 'Advertencia', etc.

# Inicializar la base de datos al importar el módulo
init_db()

app = Flask(__name__)
CORS(app)

@app.route('/')
def dashboard():
    return render_template('dashboard.html', config=GENERAL_CONFIG)

@app.route('/servers')
def servers():
    return render_template('servers.html', config=GENERAL_CONFIG)

@app.route('/apis')
def apis():
    return render_template('apis.html', config=GENERAL_CONFIG)

@app.route('/api/dashboard-data')
def api_dashboard_data():
    page = request.args.get('page', 1, type=int)
    events_per_page = GENERAL_CONFIG['dashboard']['max_events_displayed']
    status = check_status()
    event_log = get_events()
    total_events = len(event_log)
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
        'overallStatus': get_overall_status()
    }
    return jsonify(data)

if __name__ == '__main__':
    port = GENERAL_CONFIG['dashboard'].get('port', 9000)  # Usa 9000 como puerto predeterminado si no está definido
    app.run(debug=True, host='0.0.0.0', port=port)