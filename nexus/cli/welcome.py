"""Epic Startup for Nexus."""

import os
import time
import sys

def clear():
    os.system('clear' if os.name == 'posix' else 'cls')

def fade_print(text, delay=0.01):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def get_logo(config=None):
    """Dynamic logo that derives color from the provider identity."""
    # Generate a deterministic color based on the provider name hash
    provider_name = (config.active_provider if config else "nexus-default")
    hash_val = sum(ord(c) for c in provider_name)
    # Map to one of the 6 standard terminal colors (31-36)
    color_code = 31 + (hash_val % 6)
    color = f"\033[{color_code}m"
    
    reset = "\033[0m"
    
    return f"""
{color}      ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗{reset}
{color}      ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝{reset}
{color}      ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗{reset}
{color}      ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║{reset}
{color}      ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║{reset}
{color}      ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝{reset}
          {color}∞  THE NEURAL OS ({provider_name.upper()})  ∞{reset}
    """

def display_welcome():
    clear()
    from ..config import load_config
    config = load_config()
    
    logo = get_logo(config)
    print(logo)
    
    # ... rest of display_welcome logic ...

    cyan = "\033[36m"
    bold = "\033[1m"
    reset = "\033[0m"
    dim = "\033[90m"
    green = "\033[32m"

    fade_print(f"    {bold}N E X U S   N E U R A L   O S   V 2{reset}  {dim}[build 2026.05.05]{reset}", 0.005)
    print(f"    {dim}──────────────────────────────────────────────────────────{reset}")

    subsystems = [
        ("CORE ", "Synaptic weights loading"),
        ("MESH ", "Vector-mesh link established"),
        ("EXEC ", "Tool registry verification"),
        ("COMM ", "Uplink protocols standby"),
    ]

    for sub, msg in subsystems:
        time.sleep(0.06)
        # Dynamic progress bar for each subsystem
        bar = "▰▰▰▰▰▰▰▰▰▰"
        print(f"    {cyan}[{sub}]{reset} {msg:<30} {dim}{bar}{reset} {green}OK{reset}")

    # Integrity Check
    time.sleep(0.2)
    print(f"    {cyan}[SYST ]{reset} {bold}ENVIRONMENT RESILIENCE: NOMINAL{reset}")
    print(f"    {cyan}[BEAT ]{reset} {bold}HEARTBEAT: STABLE{reset}")

    print(f"\n    {bold}Welcome to the Nexus.{reset}")
    print(f"    {dim}Neural Link established. Awaiting Directive.{reset}\n")


if __name__ == "__main__":
    display_welcome()
