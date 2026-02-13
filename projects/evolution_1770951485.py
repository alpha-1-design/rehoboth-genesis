import psutil
import time

def monitor_thermals():
    while True:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                for entry in entries:
                    print(f"{entry.label}: {entry.current}°C", end='\r')
        else:
            print("No temperature sensors found")
        time.sleep(1)

if __name__ == "__main__":
    monitor_thermals()