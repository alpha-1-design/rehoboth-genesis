import psutil
import logging
import subprocess
import time
import os

# Set up logging
logging.basicConfig(filename='guardian_core.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_ssh_connections():
    # Get a list of active SSH connections
    ssh_connections = subprocess.check_output(['netstat', '-anp', '|', 'grep', 'ssh']).decode('utf-8').split('\n')

    # Define authorized IPs
    authorized_ips = ['192.168.1.100', '127.0.0.1']

    # Iterate over each connection
    for connection in ssh_connections:
        if connection:
            # Extract the IP address from the connection
            ip_address = connection.split()[-1].split(':')[0]

            # Check if the IP is authorized
            if ip_address not in authorized_ips:
                # Log a SECURITY ALERT
                logging.critical('SECURITY ALERT: Unauthorized SSH connection from IP ' + ip_address)

def check_cpu_usage():
    # Get the current CPU usage
    cpu_usage = psutil.cpu_percent()

    # Check if CPU usage exceeds 90%
    if cpu_usage > 90:
        # Log a warning
        logging.warning('CPU usage exceeded 90%. Pausing evolution_watcher process.')

        # Pause the evolution_watcher process
        os.system('pkill -STOP evolution_watcher')

        # Wait for CPU usage to drop below 80%
        while psutil.cpu_percent() > 80:
            time.sleep(1)

        # Resume the evolution_watcher process
        os.system('pkill -CONT evolution_watcher')

        # Log a message when the process is resumed
        logging.info('CPU usage has dropped below 80%. Resumed evolution_watcher process.')

while True:
    check_ssh_connections()
    check_cpu_usage()
    time.sleep(1)