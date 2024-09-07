import schedule
import time
from dashboard import check_status

def job():
    print("Ejecutando comprobación de estado...")
    check_status()

schedule.every(1).minutes.do(job)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    run_scheduler()