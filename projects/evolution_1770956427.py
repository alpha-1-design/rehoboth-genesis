import logging

# Create a logger
logger = logging.getLogger('genesis')
logger.setLevel(logging.INFO)

# Create a file handler and set to append mode
handler = logging.FileHandler('genesis.log', 'a')
handler.setLevel(logging.INFO)

# Create a formatter and add a unique prefix
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(handler)

def log_evolution(prefix, message):
    logger.info(f"[{prefix}] {message}")

# Example usage:
log_evolution("GUARDIAN", "Evolved to level 2")
log_evolution("PREDATOR", "Evolved to level 3")