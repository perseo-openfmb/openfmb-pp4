# Author: Kevin Martinez
# Refactor and Documentation: Gemini-3.0
# Date: 2026-02-07
# Generate a library for OpenFMB API
# This library will provide functions to interact with the OpenFMB API

import requests
import logging
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID

# Configuration for logging (User can override this)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OpenFMB-Client")

class OpenFMBError(Exception):
    """Base exception for OpenFMB API errors with optional context."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def __str__(self) -> str:
        if self.status_code is not None:
            return f"{self.message} (status_code={self.status_code})"
        return self.message

class OpenFMBClient:
    """
    A client for interacting with the OpenFMB Async API.
    Designed for control applications requiring historical and real-time data.
    """

    def __init__(self, base_url: str, timeout: int = 5):
        """
        Args:
            base_url (str): The root URL of the API (e.g., 'http://localhost:8000')
            timeout (int): Request timeout in seconds. Critical for control loops
                           to avoid hanging indefinitely.
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        # Optimization: Connection pooling is handled automatically by Session

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Internal method to handle HTTP requests and errors uniformly."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(method, url, params=params, timeout=self.timeout)
            response.raise_for_status() # Raises HTTPError for 4xx/5xx codes
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout connecting to {url}")
            raise OpenFMBError(
                f"Request timed out after {self.timeout}s.",
                status_code=408,
                payload={"url": url, "timeout": self.timeout},
            )
            
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection failed to {url}")
            raise OpenFMBError(
                "Could not connect to the OpenFMB API.",
                payload={"url": url},
            )
            
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            error_payload: Optional[Dict[str, Any]]
            try:
                error_payload = e.response.json()
            except ValueError:
                error_payload = {"detail": e.response.text}

            logger.error(f"HTTP Error {status_code}: {e.response.text}")
            raise OpenFMBError(
                f"API Error: {status_code}",
                status_code=status_code,
                payload=error_payload,
            )
            
        except ValueError:
            logger.error("Invalid JSON received")
            raise OpenFMBError(
                "API returned invalid JSON.",
                payload={"url": url},
            )

    def get_last_state(self, device_uuid: Union[str, UUID]) -> Dict[str, Any]:
        """
        Retrieves the latest measurement for a specific device.

        Args:
            device_uuid: The unique ID of the device (string or UUID object).

        Returns:
            Dict containing timestamp, uuid, and data payload.
        """
        endpoint = f"/devices/{str(device_uuid)}/last-state"
        data = self._request("GET", endpoint)
        
        # Unpack the specific key as per your API definition
        return data.get("latest_measurement", {})

    def get_historical_data(
        self, 
        device_uuid: Union[str, UUID], 
        limit: int = 100, 
        start: Optional[datetime] = None, 
        end: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves historical data for time-series analysis.

        Args:
            device_uuid: The unique ID of the device.
            limit: Max number of records (1-5000).
            start: Start datetime (inclusive).
            end: End datetime (inclusive).

        Returns:
            List of measurement dictionaries.
        """
        endpoint = f"/devices/{str(device_uuid)}/historical"
        params = {"limit": limit}

        # Handle datetime serialization automatically for the user
        if start:
            params["start"] = start.isoformat()
        if end:
            params["end"] = end.isoformat()

        response = self._request("GET", endpoint, params=params)
        return response.get("measurements", [])

    def check_health(self) -> bool:
        """Verifies if the API and Database are responsive."""
        try:
            res = self._request("GET", "/test-db")
            return "database_version" in res
        except OpenFMBError:
            return False

    def get_devices(self) -> Dict[str, Any]:
        """
        Retrieves the list of device UUIDs from the API.

        Returns:
            Dict with count and device_uuids fields.
        """
        return self._request("GET", "/devices")