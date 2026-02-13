# guardian_core.py

import logging
import psutil
import time
import threading

# Set up logging
logging.basicConfig(filename='genesis.log', level=logging.INFO)
logger = logging.getLogger(__name__)

class GuardianCore:
    def __init__(self):
        self.non_essential_threads = []
        self.paused = False

    def monitor_temperature(self):
        while True:
            temp = psutil.sensors_temperatures()
            if temp:
                core_temp = temp['coretemp'][0].current
                if core_temp > 40:
                    logger.critical(f"System temperature exceeded 40°C: {core_temp}°C")
                    self.pause_non_essential_threads()
            time.sleep(1)

    def pause_non_essential_threads(self):
        if not self.paused:
            self.paused = True
            for thread in self.non_essential_threads:
                thread.pause()

    def register_thread(self, thread):
        self.non_essential_threads.append(thread)

class NonEssentialThread:
    def __init__(self, func):
        self.func = func
        self.paused = False
        self.thread = threading.Thread(target=self.run)

    def run(self):
        while True:
            if not self.paused:
                self.func()
            time.sleep(1)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

def example_non_essential_func():
    print("Non-essential thread running")

# Create guardian core
guardian_core = GuardianCore()

# Create non-essential thread
non_essential_thread = NonEssentialThread(example_non_essential_func)
guardian_core.register_thread(non_essential_thread)

# Start threads
non_essential_thread.thread.start()
threading.Thread(target=guardian_core.monitor_temperature).start()