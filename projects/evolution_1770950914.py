# system_health.py

import psutil

def get_ram_usage():
    """Returns the current RAM usage as a percentage."""
    return psutil.virtual_memory().percent

def get_ram_details():
    """Returns a dictionary containing RAM usage details."""
    mem = psutil.virtual_memory()
    return {
        'total': mem.total / (1024.0 ** 3),
        'available': mem.available / (1024.0 ** 3),
        'used': mem.used / (1024.0 ** 3),
        'percentage': mem.percent
    }

def main():
    ram_usage = get_ram_usage()
    ram_details = get_ram_details()
    
    print(f"RAM Usage: {ram_usage}%")
    print("RAM Details:")
    for key, value in ram_details.items():
        if key == 'percentage':
            print(f"{key.capitalize()}: {value}%")
        else:
            print(f"{key.capitalize()}: {value:.2f} GB")

if __name__ == "__main__":
    main()