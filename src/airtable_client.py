
import json
import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from src.logging_config import LOGGER_NAME


logger = logging.getLogger(LOGGER_NAME)

AIRTABLE_API_URL = "https://api.airtable.com/v0"

REQUEST_TIMEOUT = 30
MAX_RETRIES = 2
RATE_LIMIT_WAIT = 30


class AirtableAPIError(Exception):
    """Base exception for Airtable API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_type: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


class AirtableAuthenticationError(AirtableAPIError):
    """Raised when Airtable authentication fails."""


class AirtablePermissionError(AirtableAPIError):
    """Raised when Airtable permissions are insufficient."""


class AirtableRateLimitError(AirtableAPIError):
    """Raised when Airtable rate limits are exceeded."""


class AirtableNotFoundError(AirtableAPIError):
    """Raised when an Airtable resource cannot be found."""


class AirtableClient:
    """
    Client for interacting with the Airtable Web API.

    Handles authentication, HTTP requests, response parsing,
    pagination, and bounded retries for rate-limit errors.
    """

    def __init__(
        self,
        pat: str | None = None,
        base_id: str | None = None,
        timeout: int = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ):
        load_dotenv()

        self.pat = pat or os.getenv("AIRTABLE_PAT")
        self.base_id = base_id or os.getenv("AIRTABLE_BASE_ID")
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.pat:
            raise ValueError("AIRTABLE_PAT is not configured.")

        if not self.base_id:
            raise ValueError("AIRTABLE_BASE_ID is not configured.")

        if self.timeout <= 0:
            raise ValueError("timeout must be greater than zero.")

        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative.")

        self.headers = {
            "Authorization": f"Bearer {self.pat}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "InvoiceProcessingAutomation/1.0",
        }

    def _build_url(
        self,
        table_name: str,
        record_id: str | None = None,
        params: dict | None = None,
    ) -> str:
        """Build an Airtable API endpoint."""

        if not table_name:
            raise ValueError("table_name cannot be empty.")

        encoded_table = quote(table_name, safe="")

        url = (
            f"{AIRTABLE_API_URL}/"
            f"{self.base_id}/"
            f"{encoded_table}"
        )

        if record_id:
            url += f"/{quote(record_id, safe='')}"

        if params:
            url += f"?{urlencode(params)}"

        return url

    def _parse_error(self, error: HTTPError) -> AirtableAPIError:
        """Convert HTTP errors into safe application exceptions."""

        error_type = None

        try:
            response_data = json.loads(error.read().decode("utf-8"))
            error_type = response_data.get("error", {}).get("type")
        except (ValueError, UnicodeDecodeError, AttributeError):
            pass

        status_code = error.code

        if status_code == 401:
            return AirtableAuthenticationError(
                "Airtable authentication failed.",
                status_code,
                error_type,
            )

        if status_code == 403:
            return AirtablePermissionError(
                "Airtable denied access to the requested resource.",
                status_code,
                error_type,
            )

        if status_code == 404:
            return AirtableNotFoundError(
                "The requested Airtable resource was not found.",
                status_code,
                error_type,
            )

        if status_code == 429:
            return AirtableRateLimitError(
                "Airtable API rate limit exceeded.",
                status_code,
                error_type,
            )

        return AirtableAPIError(
            "Airtable API request failed.",
            status_code,
            error_type,
        )

    
    def _request(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
    ) -> dict:
        """
        Execute an HTTP request against Airtable.

        Only rate-limit responses are automatically retried.
        Other errors are raised immediately.
        """

        # Convert the outgoing Python dictionary into JSON bytes.
        request_body = (
            json.dumps(payload).encode("utf-8")
            if payload is not None
            else None
        )

        for attempt in range(self.max_retries + 1):
            request = Request(
                url=url,
                data=request_body,
                headers=self.headers,
                method=method.upper(),
            )

            try:
                with urlopen(
                    request,
                    timeout=self.timeout,
                ) as response:
                    response_body = response.read()

                if not response_body:
                    return {}

                response_data = json.loads(
                    response_body.decode("utf-8")
                )

                if not isinstance(response_data, dict):
                    logger.error(
                        "Airtable returned an unexpected response format."
                    )

                    raise AirtableAPIError(
                        "Airtable returned an unexpected response format."
                    )

                return response_data

            except HTTPError as error:
                api_error = self._parse_error(error)

                if (
                    isinstance(api_error, AirtableRateLimitError)
                    and api_error.error_type
                    != "PUBLIC_API_BILLING_LIMIT_EXCEEDED"
                    and attempt < self.max_retries
                ):
                    logger.warning(
                        "Airtable rate limit encountered. "
                        "Retrying after %s seconds (attempt %s/%s).",
                        RATE_LIMIT_WAIT,
                        attempt + 1,
                        self.max_retries,
                    )

                    time.sleep(RATE_LIMIT_WAIT)
                    continue

                logger.error(
                    "Airtable request failed (%s).",
                    type(api_error).__name__,
                )

                raise api_error from None

            except TimeoutError:
                logger.error("Airtable request timed out.")

                raise AirtableAPIError(
                    "Airtable request timed out."
                ) from None

            except URLError as error:
                logger.error(
                    "Airtable connection failed (%s).",
                    type(error).__name__,
                )

                raise AirtableAPIError(
                    "Could not connect to Airtable."
                ) from None

            except json.JSONDecodeError:
                logger.error(
                    "Airtable returned an invalid JSON response."
                )

                raise AirtableAPIError(
                    "Airtable returned an invalid JSON response."
                ) from None

        raise AirtableRateLimitError(
            "Airtable retry limit reached.",
            429,
        )


    def list_records(
        self,
        table_name: str,
        page_size: int = 100,
        max_records: int | None = None,
        filter_by_formula: str | None = None,
    ) -> list[dict]:
        """Retrieve records from an Airtable table."""

        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be between 1 and 100.")

        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be greater than zero.")

        records = []
        offset = None

        while True:
            params = {"pageSize": page_size}

            if offset:
                params["offset"] = offset

            if filter_by_formula:
                params["filterByFormula"] = filter_by_formula

            response = self._request(
                "GET",
                self._build_url(table_name, params=params),
            )

            page_records = response.get("records", [])

            if not isinstance(page_records, list):
                raise AirtableAPIError(
                    "Unexpected Airtable records response."
                )

            if not all(isinstance(record, dict) for record in page_records):
                raise AirtableAPIError(
                    "Airtable returned an invalid record format."
                )

            records.extend(page_records)

            if max_records is not None and len(records) >= max_records:
                return records[:max_records]

            offset = response.get("offset")

            if not offset:
                break

        return records

    def create_record(
        self,
        table_name: str,
        fields: dict,
    ) -> dict:
        """Create a new Airtable record."""

        if not fields:
            raise ValueError("fields cannot be empty.")

        response = self._request(
            "POST",
            self._build_url(table_name),
            payload={"fields": fields},
        )

        logger.info("Airtable record created successfully.")

        return response

    def update_record(
        self,
        table_name: str,
        record_id: str,
        fields: dict,
    ) -> dict:
        """Update an existing Airtable record."""

        if not record_id:
            raise ValueError("record_id cannot be empty.")

        if not fields:
            raise ValueError("fields cannot be empty.")

        response = self._request(
            "PATCH",
            self._build_url(
                table_name,
                record_id=record_id,
            ),
            payload={"fields": fields},
        )

        logger.info("Airtable record updated successfully.")

        return response
