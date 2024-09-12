import time
import schedule
import logging
import json
import os
import paramiko
import requests
from pymsteams import connectorcard
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sqlite3
import pytz
from paramiko import SSHConfig, ProxyCommand

# Cargar variables de entorno
load_dotenv()

# Configurar el logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Definir la ruta de la base de datos
DB_PATH = os.path.join(os.path.expanduser('~'), 'events.db')

def cargar_configuraciones():
    with open('config/servers.json') as f:
        SERVERS = json.load(f)
    with open('config/apis.json') as f:
        APIS = json.load(f)
    with open('config/general.json') as f:
        GENERAL_CONFIG = json.load(f)
    return SERVERS, APIS, GENERAL_CONFIG

SERVERS, APIS, GENERAL_CONFIG = cargar_configuraciones()

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
    c.execute('''CREATE TABLE IF NOT EXISTS historical_states
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  name TEXT,
                  state TEXT)''')
    conn.commit()
    conn.close()

def save_state(name, state):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    timestamp = datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT OR REPLACE INTO states (name, state) VALUES (?, ?)", (name, json.dumps(state)))
    c.execute("INSERT INTO historical_states (timestamp, name, state) VALUES (?, ?, ?)", (timestamp, name, json.dumps(state)))
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

def add_event(message):
    madrid_tz = pytz.timezone('Europe/Madrid')
    timestamp = datetime.now(madrid_tz).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO events (timestamp, message) VALUES (?, ?)", (timestamp, message))
    conn.commit()
    conn.close()

def send_teams_alert(message):
    if GENERAL_CONFIG['notifications']['enabled']:
        teams_webhook = os.getenv('TEAMS_WEBHOOK')
        myTeamsMessage = connectorcard(teams_webhook)
        myTeamsMessage.text(message)
        myTeamsMessage.send()
        logging.info(f"Alerta enviada: {message}")
    add_event(f"Alerta: {message}")

def check_ssh(server):
    try:
        ssh_config = SSHConfig()
        user_config_file = os.path.expanduser("~/.ssh/config")
        if os.path.exists(user_config_file):
            with open(user_config_file) as f:
                ssh_config.parse(f)

        host_config = ssh_config.lookup(server['ssh']['hostname'])

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

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

        client.connect(**connect_kwargs)
        return client
    except Exception as e:
        logging.error(f"Error de conexión SSH para {server['name']}: {str(e)}")
        return None

def check_api(api):
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
            response = requests.get(api['url'], timeout=5)
            return response.status_code == 200
    except Exception as e:
        logging.error(f"Error al verificar API {api['name']}: {str(e)}")
        return False

def get_server_info(ssh_client, disks):
    server_info = {}
    
    stdin, stdout, stderr = ssh_client.exec_command("cat /proc/uptime")
    uptime = float(stdout.read().decode().split()[0])
    
    server_info["uptime"] = f"{int(uptime // 86400)} días, {int((uptime % 86400) // 3600)} horas, {int((uptime % 3600) // 60)} minutos"
    
    stdin, stdout, stderr = ssh_client.exec_command("cat /proc/loadavg")
    load = stdout.read().decode().split()[:3]
    server_info["load"] = f"{load[0]}, {load[1]}, {load[2]}"
    
    stdin, stdout, stderr = ssh_client.exec_command("free -m | awk '/Mem:/ {print $3,$2}'")
    mem = stdout.read().decode().split()
    server_info["ram_usage"] = f"{int(mem[0])/int(mem[1])*100:.2f}% ({int(mem[0])} MB / {int(mem[1])} MB)"
    
    stdin, stdout, stderr = ssh_client.exec_command(f"df -h {' '.join(disks)}")
    disk_info = stdout.read().decode().splitlines()[1:]
    for line in disk_info:
        parts = line.split()
        server_info[f"disk_usage_{parts[5].replace('/', '_')}"] = f"{parts[4]} ({parts[2]} / {parts[1]})"
    
    return server_info

def check_resource_state(current_value, resource_name, server_name):
    thresholds = GENERAL_CONFIG['thresholds'][resource_name.split('_')[0]]
    
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
        if thresholds.get('alerts_enabled', True):
            message = f"El {resource_name} de {server_name} ha cambiado a estado {new_state}: {current_value:.2f}%"
            send_teams_alert(message)
        save_state(state_key, new_state)
        logging.info(f"Cambio de estado detectado: {resource_name} de {server_name} a {new_state}")
    else:
        logging.debug(f"No hay cambio de estado para {resource_name} de {server_name}")
    
    return new_state

def check_status():
    status = {}
    
    for server in SERVERS:
        ssh_client = check_ssh(server)
        server_status = ssh_client is not None
        status[f"ssh_{server['name']}"] = server_status
        save_state(f"ssh_{server['name']}", server_status)
        logging.info(f"Estado SSH para {server['name']}: {server_status}")
        
        if server_status:
            server_info = get_server_info(ssh_client, server['disks'])
            status[f"{server['name']}_info"] = server_info
            save_state(f"{server['name']}_info", server_info)
            ssh_client.close()
            
            load_value = float(server_info.get('load', '0').split(',')[0])
            save_state(f"{server['name']}_load", load_value)
            status[f"{server['name']}_load_state"] = check_resource_state(load_value, 'load', server['name'])
            
            ram_usage = float(server_info.get('ram_usage', '0%').split('%')[0])
            save_state(f"{server['name']}_ram", ram_usage)
            status[f"{server['name']}_ram_state"] = check_resource_state(ram_usage, 'ram', server['name'])
            
            for disk in server['disks']:
                disk_key = f"disk_usage_{disk.replace('/', '_')}"
                disk_usage = server_info.get(disk_key, '0%')
                disk_usage_value = float(disk_usage.split('%')[0])
                save_state(f"{server['name']}_{disk_key}", disk_usage_value)
                status[f"{server['name']}_{disk_key}_state"] = check_resource_state(disk_usage_value, 'disk', server['name'])
        else:
            logging.warning(f"No se pudo conectar al servidor {server['name']}")
    
    for api in APIS:
        api_status = check_api(api)
        status[f"api_{api['name']}"] = api_status
        save_state(f"api_{api['name']}", api_status)
        logging.info(f"Estado API para {api['name']}: {api_status}")
        
        state_key = f"api_{api['name']}_state"
        last_state = load_saved_state(state_key)
        if api_status != last_state:
            message = f"El estado de la API {api['name']} ha cambiado a {'activo' if api_status else 'inactivo'}"
            send_teams_alert(message)
            save_state(state_key, api_status)
            logging.info(f"Cambio de estado de API detectado: {message}")
        else:
            logging.debug(f"No hay cambio de estado para la API {api['name']}")
    
    overall_status = get_overall_status(status)
    save_state('overall_status', overall_status)
    status['overall_status'] = overall_status
    
    logging.info(f"Estado general: {overall_status}")
    logging.info(f"Estado completo: {json.dumps(status, indent=2)}")
    
    return status

def get_overall_status(status):
    critical_count = sum(1 for state in status.values() if state == 'critical')
    warning_count = sum(1 for state in status.values() if state == 'warning')
    
    if critical_count > 0:
        return 'Crítico'
    elif warning_count > 0:
        return 'Advertencia'
    else:
        return 'Estable'

def clean_old_events():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE timestamp < date('now', ?)", (f"-{GENERAL_CONFIG['log_retention_days']} days",))
    conn.commit()
    conn.close()

def realizar_comprobaciones():
    logging.info("Realizando comprobaciones...")
    check_status()
    logging.info("Comprobaciones completadas.")

def main():
    init_db()

    teams_webhook = os.getenv('TEAMS_WEBHOOK')
    if not teams_webhook:
        logging.warning("La variable de entorno TEAMS_WEBHOOK no está configurada. Las notificaciones a Teams no funcionarán.")

    if not GENERAL_CONFIG['background_service']['enabled']:
        logging.info("El servicio en segundo plano está desactivado en la configuración.")
        return

    intervalo_comprobacion = GENERAL_CONFIG['background_service']['check_interval']

    logging.info(f"Iniciando servicio en segundo plano. Intervalo de comprobación: {intervalo_comprobacion} minutos")

    realizar_comprobaciones()

    schedule.every(intervalo_comprobacion).minutes.do(realizar_comprobaciones)
    schedule.every().day.at("00:00").do(clean_old_events)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()