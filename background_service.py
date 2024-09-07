import time
import schedule
import logging
from dashboard import check_status, DB_PATH, clean_old_events, cargar_configuraciones
import os

# Configurar el logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def realizar_comprobaciones():
    logging.info("Realizando comprobaciones...")
    status = check_status()
    logging.info("Comprobaciones completadas.")

def main():
    # Cargar configuraciones iniciales
    SERVERS, APIS, GENERAL_CONFIG = cargar_configuraciones()

    # Verificar la configuración del webhook de Teams
    teams_webhook = os.getenv('TEAMS_WEBHOOK')
    if not teams_webhook:
        logging.warning("La variable de entorno TEAMS_WEBHOOK no está configurada. Las notificaciones a Teams no funcionarán.")

    if not GENERAL_CONFIG['background_service']['enabled']:
        logging.info("El servicio en segundo plano está desactivado en la configuración.")
        return

    intervalo_comprobacion = GENERAL_CONFIG['background_service']['check_interval']
    dias_retencion_logs = GENERAL_CONFIG['log_retention_days']

    logging.info(f"Iniciando servicio en segundo plano. Intervalo de comprobación: {intervalo_comprobacion} minutos")

    # Realizar una comprobación inmediata al iniciar
    realizar_comprobaciones()

    schedule.every(intervalo_comprobacion).minutes.do(realizar_comprobaciones)
    schedule.every().day.at("00:00").do(clean_old_events)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()