# Panel de Control de Sistemas Melmacia

Este proyecto es un panel de control para monitorear el estado de los servidores y APIs de Melmacia. Proporciona una interfaz web para visualizar el estado de los sistemas en tiempo real.

## Características

- Monitoreo en tiempo real de servidores y APIs
- Visualización de uso de recursos (CPU, RAM, disco)
- Registro de eventos y alertas
- Interfaz web responsive
- Actualización automática de datos
- Notificaciones a Microsoft Teams

## Requisitos

- Python 3.7+
- pip (gestor de paquetes de Python)
- Acceso SSH a los servidores a monitorear

## Instalación

1. Clona este repositorio:
   ```
   git clone https://github.com/tu-usuario/melmacia-system-dashboard.git
   cd melmacia-system-dashboard
   ```

2. Crea un entorno virtual e instala las dependencias:
   ```
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Configura las variables de entorno:
   Crea un archivo `.env` en la raíz del proyecto y añade:
   ```
   TEAMS_WEBHOOK=https://outlook.office.com/webhook/...
   ```

4. Configura los servidores y APIs a monitorear:
   Edita los archivos en la carpeta `config/`:
   - `servers.json`: Lista de servidores
   - `apis.json`: Lista de APIs
   - `general.json`: Configuración general del dashboard

## Configuración

### Añadir un nuevo servidor

Para añadir un nuevo servidor al monitoreo, sigue estos pasos:

1. Abre el archivo `config/servers.json`.

2. Añade una nueva entrada al array JSON con la siguiente estructura:

   ```json
   {
     "name": "NombreDelServidor",
     "ssh": {
       "hostname": "NombreDelHost"
     },
     "disks": ["/", "/data"]
   }
   ```

   Donde:
   - `"name"`: Es el nombre identificativo del servidor.
   - `"ssh"`: Contiene la información de conexión SSH.
     - `"hostname"`: Es el nombre del host definido en el archivo SSH config.
   - `"disks"`: Es un array con las rutas de los discos a monitorear.

3. Guarda el archivo `servers.json`.

4. Reinicia el servicio de monitoreo para que los cambios surtan efecto.

### Añadir una nueva API

Para añadir una nueva API al monitoreo, sigue estos pasos:

1. Abre el archivo `config/apis.json`.

2. Añade una nueva entrada al array JSON con la siguiente estructura:

   ```json
   {
     "name": "NombreDeLaAPI",
     "server": "NombreDelServidor",
     "requires_ssh": true/false,
     "url": "URLDeLaAPI"
   }
   ```

   Donde:
   - `"name"`: Es el nombre identificativo de la API.
   - `"server"`: Es el nombre del servidor asociado a la API.
   - `"requires_ssh"`: Indica si se requiere una conexión SSH para acceder a la API (true o false).
   - `"url"`: Es la URL de la API.

3. Guarda el archivo `apis.json`.

4. Reinicia el servicio de monitoreo para que los cambios surtan efecto.

### Configuración General

Para configurar la general, edita el archivo `config/general.json`:

```json
{
  "refresh_interval": 10,
  "notification_interval": 300,
  "teams_webhook": "https://outlook.office.com/webhook/..."
}
```

Donde:
- `"refresh_interval"`: Es el intervalo de tiempo en segundos entre cada actualización de datos.
- `"notification_interval"`: Es el intervalo de tiempo en segundos entre cada notificación de alerta.
- `"teams_webhook"`: Es la URL del webhook de Microsoft Teams para enviar notificaciones.

## Uso

1. Configura las claves SSH:
   ```
   # Copia tus claves SSH al directorio del proyecto
   scp ~/.ssh/id_rsa* /ruta/al/proyecto/melmacia-system-dashboard/

   # Configura el archivo SSH config
   mkdir -p ~/.ssh
   touch ~/.ssh/config
   
   # Añade la configuración necesaria para cada servidor, por ejemplo:
   echo "Host servidor1
     HostName 192.168.1.100
     User usuario
     IdentityFile /ruta/al/proyecto/melmacia-system-dashboard/id_rsa" >> ~/.ssh/config
   ```

2. Inicia el servidor Flask:
   ```
   python dashboard.py
   ```

   El servidor se iniciará en el puerto especificado en `config/general.json` (por defecto, 9000).

3. Inicia el servicio en segundo plano:
   ```
   python background_service.py
   ```

4. Abre un navegador y visita `http://localhost:9000` (o el puerto que hayas configurado)

## Funcionamiento

El sistema funciona de la siguiente manera:

1. `dashboard.py` inicia un servidor Flask que sirve la interfaz web.
2. `background_service.py` ejecuta comprobaciones periódicas en segundo plano.
3. El frontend realiza peticiones periódicas al backend para obtener datos actualizados.
4. Los datos se muestran en tiempo real en la interfaz web.
5. Las alertas se envían a Microsoft Teams cuando se detectan problemas.

## Estructura del Proyecto

- `dashboard.py`: Punto de entrada de la aplicación
- `templates/`: Plantillas HTML para la interfaz web
- `static/`: Archivos estáticos (CSS, JS)
- `config/`: Archivos de configuración JSON
- `requirements.txt`: Dependencias del proyecto