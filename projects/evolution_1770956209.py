import psutil
import time
import os
import signal
import logging

# Set up logging
logging.basicConfig(filename='resource_reclaimer.log', level=logging.INFO)

def get_running_processes():
    """Return a list of running python processes"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
        try:
            if proc.info['name'] == 'python.exe' or proc.info['name'] == 'python':
                processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return processes

def monitor_process(proc):
    """Monitor a process and kill it if it uses more than 15% CPU for over 2 minutes"""
    cpu_usage = proc.cpu_percent()
    start_time = time.time()
    while True:
        time.sleep(1)
        cpu_usage = proc.cpu_percent()
        if cpu_usage > 15:
            if time.time() - start_time > 120:
                try:
                    os.kill(proc.pid, signal.SIGTERM)
                    logging.info(f"RESOURCE RECLAIMED: Process {proc.pid} killed due to high CPU usage")
                except OSError as e:
                    logging.error(f"Error killing process {proc.pid}: {e}")
                break
        else:
            start_time = time.time()

def main():
    while True:
        processes = get_running_processes()
        for proc in processes:
            if proc.exe() and 'app.py' not in proc.exe() and 'manifest' not in proc.exe():
                if proc.cpu_percent() > 15:
                    monitor_process(proc)

if __name__ == "__main__":
    main()