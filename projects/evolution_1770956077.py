import logging
import re
import subprocess
import os

# Define the Whitelist
whitelist = ['127.0.0.1', 'localhost']

# Set up logging configuration
logging.basicConfig(filename='guardian.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_external_ip(ip):
    """
    Check if an IP is external (not in the whitelist)
    """
    return ip not in whitelist

def process_ssh_log(log_line):
    """
    Process SSH log line and log SECURITY ALERT if IP is external
    """
    ssh_pattern = r"ssh.*from (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    match = re.search(ssh_pattern, log_line)
    if match:
        ip = match.group(1)
        if is_external_ip(ip):
            logging.warning(f"SECURITY ALERT: SSH connection from {ip}")

def auto_deploy_critical_logs():
    """
    Auto-deploy CRITICAL logs to the Vault before purging them locally
    """
    critical_pattern = r"CRITICAL.*"
    with open('guardian.log', 'r') as f:
        lines = f.readlines()
        critical_logs = [line for line in lines if re.search(critical_pattern, line)]
        for log in critical_logs:
            # Deploy log to Vault (replace with actual deployment command)
            subprocess.run(["echo", log.strip()])
            # Remove log from local file
            with open('guardian.log', 'w') as f:
                f.write(''.join([line for line in lines if line != log]))

# Example usage
if __name__ == "__main__":
    with open('ssh.log', 'r') as f:
        for line in f:
            process_ssh_log(line)
    auto_deploy_critical_logs()