import json
import os
import paramiko
import requests
from pymsteams import connectorcard
from dotenv import load_dotenv
import sqlite3
import pytz
from datetime import datetime
from paramiko import SSHConfig, ProxyCommand
import logging  # Añadimos esta importación

load_dotenv()

# Configurar el logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Definir la ruta de la base de datos en un lugar persistente
DB_PATH = os.path.join(os.path.expanduser('~'), 'events.db')

# Definir umbrales para los recursos
load_thresholds = {'warning': 0.7, 'critical': 1.0}
ram_thresholds = {'warning': 70, 'critical': 85}
disk_thresholds = {'warning': 70, 'critical': 85}

def check_ssh(server):
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

        # Agregar logging detallado
        logging.info(f"Intentando conectar a {server['name']} con configuración: {connect_kwargs}")

        # Conectar con un timeout
        client.connect(**connect_kwargs, timeout=10)
        logging.info(f"Conexión SSH exitosa a {server['name']}")
        return client
    except Exception as e:
        logging.error(f"Error de conexión SSH para {server['name']}: {str(e)}")
        return None

def check_api(api):
    # Implementación de check_api
    ...

def add_event(message):
    # Implementación de add_event
    ...

def send_teams_alert(message, general_config):
    """
    Envía una alerta a Microsoft Teams si las notificaciones están habilitadas.
    
    Args:
        message (str): Mensaje de la alerta.
        general_config (dict): Configuración general que incluye la configuración de notificaciones.
    """
    logging.info(f"Intentando enviar alerta: {message}")
    if general_config['notifications']['enabled']:
        teams_webhook = os.getenv('TEAMS_WEBHOOK')
        if teams_webhook:
            try:
                myTeamsMessage = connectorcard(teams_webhook)
                myTeamsMessage.text(message)
                myTeamsMessage.send()
                logging.info(f"Alerta enviada a Teams: {message}")
            except Exception as e:
                logging.error(f"Error al enviar alerta a Teams: {str(e)}")
        else:
            logging.error("No se encontró la URL del webhook de Teams en las variables de entorno.")
    else:
        logging.info("Las notificaciones están desactivadas en la configuración.")
    
    add_event(f"Alerta: {message}")

def get_server_info(ssh_client, disks):
    try:
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
        for disk in disks:
            stdin, stdout, stderr = ssh_client.exec_command(f"df -h {disk}")
            disk_info = stdout.read().decode().splitlines()[1].split()
            server_info[f"disk_usage_{disk.replace('/', '_')}"] = f"{disk_info[4]} ({disk_info[2]} / {disk_info[1]})"
        
        return server_info
    except Exception as e:
        logging.error(f"Error al obtener información del servidor: {str(e)}")
        return None

def check_resource_state(current_value, thresholds, resource_name, last_state):
    # Implementación de check_resource_state
    ...

def save_state(name, state):
    # Implementación de save_state
    ...

def load_saved_state(name):
    # Implementación de load_saved_state
    ...

def check_status(servers, apis, general_config):
    status = {}
    
    for server in servers:
        ssh_client = check_ssh(server)
        server_status = ssh_client is not None
        status[f"ssh_{server['name']}"] = server_status
        
        if server_status:
            try:
                server_info = get_server_info(ssh_client, server['disks'])
                logging.info(f"Información obtenida para {server['name']}: {server_info}")
                
                if server_info is None:
                    logging.error(f"get_server_info devolvió None para {server['name']}")
                    status[f"{server['name']}_info"] = {}
                else:
                    status[f"{server['name']}_info"] = server_info
                    
                    # Actualizar estados de los recursos
                    load = server_info.get('load', '0,0,0').split(',')[0]
                    status[f"{server['name']}_load_state"] = check_resource_state(load, load_thresholds, f"carga del sistema de {server['name']}", load_saved_state(f"{server['name']}_load_state"))
                    
                    ram_usage = server_info.get('ram_usage', '0%')
                    status[f"{server['name']}_ram_state"] = check_resource_state(ram_usage, ram_thresholds, f"uso de RAM de {server['name']}", load_saved_state(f"{server['name']}_ram_state"))
                    
                    for disk in server['disks']:
                        disk_key = f"disk_usage_{disk.replace('/', '_')}"
                        disk_usage = server_info.get(disk_key, '0%')
                        status[f"{server['name']}_{disk_key}_state"] = check_resource_state(disk_usage, disk_thresholds, f"uso de disco {disk} de {server['name']}", load_saved_state(f"{server['name']}_{disk_key}_state"))
                
            except Exception as e:
                logging.error(f"Error al procesar la información del servidor {server['name']}: {str(e)}")
                status[f"{server['name']}_info"] = {}
            
            finally:
                ssh_client.close()
        else:
            logging.error(f"No se pudo establecer conexión SSH con el servidor {server['name']}")
            send_teams_alert(f"No se pudo establecer conexión SSH con el servidor {server['name']}", general_config)
    
    for api in apis:
        try:
            api_status = check_api(api, servers)
            status[f"api_{api['name']}"] = api_status
            if not api_status:
                logging.error(f"La API {api['name']} no está respondiendo")
                send_teams_alert(f"La API {api['name']} no está respondiendo", general_config)
        except Exception as e:
            logging.error(f"Error al comprobar la API {api['name']}: {str(e)}")
            send_teams_alert(f"Error al comprobar la API {api['name']}: {str(e)}", general_config)
            status[f"api_{api['name']}"] = False
    
    # Guardar estados
    for key, value in status.items():
        save_state(key, value)
    
    return status

def check_api(api, servers):
    try:
        if api['requires_ssh']:
            server = next(s for s in servers if s['name'] == api['server'])
            ssh_client = check_ssh(server)
            if ssh_client:
                command = f"curl -s -o /dev/null -w '%{{http_code}}' {api['url']}"
                logging.info(f"Ejecutando comando en {server['name']}: {command}")
                stdin, stdout, stderr = ssh_client.exec_command(command)
                status_code = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                ssh_client.close()
                if error:
                    logging.error(f"Error al ejecutar curl en {server['name']}: {error}")
                logging.info(f"Código de estado para {api['name']}: {status_code}")
                return status_code == "200"
            else:
                logging.error(f"No se pudo establecer conexión SSH con el servidor {server['name']} para comprobar la API {api['name']}")
                return False
        else:
            logging.info(f"Comprobando API {api['name']} en {api['url']}")
            response = requests.get(api['url'], timeout=10)
            logging.info(f"Código de estado para {api['name']}: {response.status_code}")
            return response.status_code == 200
    except Exception as e:
        logging.error(f"Error al comprobar la API {api['name']}: {str(e)}")
        return False

# Otras funciones compartidas...