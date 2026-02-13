import logging

# Create a logger
logger = logging.getLogger('evolution_modules')

# Set the logging level
logger.setLevel(logging.INFO)

# Create a file handler which logs even debug messages
file_handler = logging.FileHandler('genesis.log', mode='a')

# Create a formatter and set the formatter for the file handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add the file handler to the logger
logger.addHandler(file_handler)

# Update all active evolution modules to use the new logger
active_modules = ['module1', 'module2', 'module3']  # Replace with actual module names
for module in active_modules:
    # Assuming each module has a 'logger' attribute
    module.logger = logger

# Test the logger
logger.info('Evolution modules updated to use genesis.log')