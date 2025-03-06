import logging
import sys

def setup_logging():
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Create console handler with formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)
    
    # Configure uvicorn logger
    uvicorn_logger = logging.getLogger('uvicorn')
    uvicorn_logger.setLevel(logging.DEBUG)
    uvicorn_logger.addHandler(console_handler)
    
    # Configure uvicorn.error logger
    uvicorn_error_logger = logging.getLogger('uvicorn.error')
    uvicorn_error_logger.setLevel(logging.DEBUG)
    uvicorn_error_logger.addHandler(console_handler) 