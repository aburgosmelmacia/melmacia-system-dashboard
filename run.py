from app import app
from scheduler import run_scheduler
import threading
import os

if __name__ == "__main__":
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        # Inicia el programador solo en el proceso principal
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.daemon = True  # Permite que el hilo se cierre cuando el programa principal termina
        scheduler_thread.start()

    # Inicia el servidor Flask
    app.run(debug=True)