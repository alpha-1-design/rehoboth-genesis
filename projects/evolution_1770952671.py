import os
import time
import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor

# Setup Paths
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(os.path.dirname(PROJECT_PATH), "genesis.log")

def log_event(message):
    """Writes system events to the log file for the Dashboard to display."""
    with open(LOG_PATH, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {message}\n")

def execute_evolution(filename):
    """Dynamically loads and runs an evolution module."""
    if filename == os.path.basename(__file__):
        return 

    try:
        module_name = filename[:-3]
        file_path = os.path.join(PROJECT_PATH, filename)
        
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        log_event(f"EXEC: {filename} initialized.")
    except Exception as e:
        log_event(f"ERROR: {filename} failed: {str(e)[:30]}")

def monitor_and_sync():
    """The Heartbeat loop."""
    log_event("SYSTEM START: Rehoboth Genesis Manifest Online")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        while True:
            # Clear old logs if they get too huge (optional investor-ready cleanup)
            if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 50000:
                open(LOG_PATH, 'w').close()

            files = [f for f in os.listdir(PROJECT_PATH) if f.endswith('.py') and f != os.path.basename(__file__)]
            
            log_event(f"SCAN: {len(files)} modules detected.")
            
            if files:
                executor.map(execute_evolution, files)
            
            log_event("HEARTBEAT: All systems nominal.")
            time.sleep(30) # Check every 30 seconds

if __name__ == "__main__":
    try:
        monitor_and_sync()
    except Exception as e:
        log_event(f"CRITICAL: {e}")
        sys.exit(1)

