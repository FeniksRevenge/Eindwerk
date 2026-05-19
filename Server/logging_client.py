"""
Logging client for sending logs to the Logging Service
Handles graceful failures if logging service is unavailable
"""

import json
import os
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class LoggingServiceClient:
    """Client for sending logs to the centralized logging service"""
    
    def __init__(
        self,
        service_name: str,
        logging_service_url: Optional[str] = None,
        timeout: int = 2
    ):
        """
        Initialize the logging client
        
        Args:
            service_name: Name of this service (e.g., 'main-api')
            logging_service_url: URL of the logging service
            timeout: Request timeout in seconds
        """
        self.service_name = service_name
        self.logging_service_url = (
            logging_service_url 
            or os.getenv('LOGGING_SERVICE_URL', 'http://localhost:5001')
        )
        self.timeout = timeout
        self.available = True
    
    def send_log(
        self,
        level: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a log entry to the logging service
        
        Args:
            level: Log level (INFO, WARNING, ERROR, DEBUG, CRITICAL)
            message: Log message
            metadata: Optional metadata dict
        
        Returns:
            bool: True if successful, False if failed or service unavailable
        """
        if not self.available:
            return False
        
        try:
            payload = {
                'service': self.service_name,
                'level': level.upper(),
                'message': message,
                'metadata': metadata or {}
            }
            
            response = requests.post(
                f'{self.logging_service_url}/api/logs',
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code in [201, 200]:
                return True
            else:
                logger.debug(
                    f"Logging service returned {response.status_code}: "
                    f"{response.text}"
                )
                return False
                
        except requests.exceptions.Timeout:
            logger.debug(
                f"Logging service timeout ({self.timeout}s)"
            )
            self.available = False
            return False
        except requests.exceptions.ConnectionError:
            logger.debug(
                f"Cannot connect to logging service at "
                f"{self.logging_service_url}"
            )
            self.available = False
            return False
        except Exception as e:
            logger.debug(f"Error sending log: {e}")
            return False
    
    def log_info(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Log an info message"""
        return self.send_log('INFO', message, metadata)
    
    def log_warning(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Log a warning message"""
        return self.send_log('WARNING', message, metadata)
    
    def log_error(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Log an error message"""
        return self.send_log('ERROR', message, metadata)
    
    def log_debug(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Log a debug message"""
        return self.send_log('DEBUG', message, metadata)
    
    def log_api_request(
        self,
        method: str,
        path: str,
        status_code: int,
        response_time_ms: float,
        user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log an API request
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path
            status_code: HTTP status code
            response_time_ms: Response time in milliseconds
            user_id: Optional user ID
            metadata: Optional additional metadata
        """
        full_metadata = {
            'method': method,
            'path': path,
            'status_code': status_code,
            'response_time_ms': response_time_ms,
            'user_id': user_id,
            **(metadata or {})
        }
        
        message = f"{method} {path} - {status_code} ({response_time_ms:.2f}ms)"
        return self.send_log('INFO', message, full_metadata)


_logging_client: Optional[LoggingServiceClient] = None


def get_logging_client() -> LoggingServiceClient:
    """Get or create the global logging client"""
    global _logging_client
    if _logging_client is None:
        _logging_client = LoggingServiceClient('main-api')
    return _logging_client


def init_logging_client(service_name: str = 'main-api') -> LoggingServiceClient:
    """Initialize the global logging client"""
    global _logging_client
    _logging_client = LoggingServiceClient(service_name)
    logger.info(f"Logging client initialized for service: {service_name}")
    return _logging_client
