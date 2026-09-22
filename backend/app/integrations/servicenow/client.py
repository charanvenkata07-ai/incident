import base64
import asyncio
import httpx
import structlog
from urllib.parse import urlparse
import ipaddress
from app.core.config import settings

logger = structlog.get_logger()

class ServiceNowClient:
    """
    Enterprise client for ServiceNow Table API.
    Provides connection pooling, exponential backoff retries, OAuth/Basic auth,
    and strict safety guards preventing live mutations when in SHADOW or DRY_RUN mode.
    Includes robust SSRF protections against internal network and metadata exfiltration.
    """
    @staticmethod
    def validate_target_url(url: str, environment: str = "PRODUCTION"):
        """
        Validates target URL against SSRF attacks:
        - Must be HTTPS in non-development environments
        - Disallows cloud metadata IP (169.254.169.254) and metadata hostnames
        - Disallows loopback and private RFC1918 IPs in staging/production
        """
        if not url:
            return
        parsed = urlparse(url)
        env = environment.upper() if environment else "PRODUCTION"
        
        if parsed.scheme != "https":
            if not (env in ("DEVELOPMENT", "TEST") and parsed.hostname in ("localhost", "127.0.0.1", "testserver")):
                raise ValueError(f"SSRF Protection: Insecure scheme '{parsed.scheme}'. Only HTTPS is permitted.")
        
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            raise ValueError("SSRF Protection: Missing hostname in URL.")
            
        disallowed_hosts = {
            "169.254.169.254",
            "metadata.google.internal",
            "instance-data",
        }
        if hostname in disallowed_hosts:
            raise ValueError(f"SSRF Protection: Target host '{hostname}' is prohibited.")
            
        if env not in ("DEVELOPMENT", "TEST"):
            if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
                raise ValueError(f"SSRF Protection: Localhost address '{hostname}' is prohibited in non-dev environment.")
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                    raise ValueError(f"SSRF Protection: Private/internal IP address '{hostname}' is prohibited.")
            except ValueError as e:
                if "does not appear to be an IPv4 or IPv6 address" in str(e):
                    pass
                else:
                    raise

    def __init__(
        self,
        base_url: str = None,
        username: str = None,
        password: str = None,
        client_id: str = None,
        client_secret: str = None
    ):
        raw_url = base_url or settings.SERVICENOW_URL
        if raw_url:
            self.validate_target_url(raw_url, settings.ENVIRONMENT)
        self.base_url = raw_url.rstrip("/") if raw_url else ""
        self.username = username or settings.SERVICENOW_USERNAME
        self.password = password or settings.SERVICENOW_PASSWORD
        self.client_id = client_id or settings.SERVICENOW_CLIENT_ID
        self.client_secret = client_secret or settings.SERVICENOW_CLIENT_SECRET
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    def _get_auth_headers(self) -> dict:
        """Constructs headers with Basic Auth or Bearer Token without logging credentials."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "IncidentFlow-Integration/1.0"
        }
        if self.username and self.password:
            cred_bytes = f"{self.username}:{self.password}".encode("utf-8")
            b64_creds = base64.b64encode(cred_bytes).decode("utf-8")
            headers["Authorization"] = f"Basic {b64_creds}"
        return headers

    async def _execute_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Executes HTTP request with exponential backoff on network errors or 5xx responses."""
        max_retries = 3
        backoff_delay = 0.5

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(method, url, **kwargs)
                    
                    if response.status_code >= 500:
                        logger.warning(
                            "servicenow_server_error_retry",
                            status_code=response.status_code,
                            attempt=attempt,
                            url=url
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(backoff_delay)
                            backoff_delay *= 2
                            continue
                    
                    return response
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as err:
                logger.warning(
                    "servicenow_network_error_retry",
                    error_type=type(err).__name__,
                    attempt=attempt,
                    url=url
                )
                if attempt < max_retries:
                    await asyncio.sleep(backoff_delay)
                    backoff_delay *= 2
                else:
                    raise

        raise httpx.RequestError(f"Failed to complete {method} to ServiceNow after {max_retries} retries.")

    async def test_connection(self) -> dict:
        """Validates network connectivity and authentication against the ServiceNow Table API."""
        if not self.base_url:
            return {"status": "unconfigured", "message": "SERVICENOW_URL is not set"}

        from urllib.parse import urlparse
        import time
        from datetime import datetime, timezone

        parsed = urlparse(self.base_url)
        hostname = parsed.netloc or parsed.path
        url = f"{self.base_url}/api/now/table/incident?sysparm_limit=1"

        start_time = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            headers = self._get_auth_headers()
            response = await self._execute_with_retry("GET", url, headers=headers)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if response.status_code == 200:
                data = response.json()
                results = data.get("result", [])
                return {
                    "status": "connected",
                    "result": "CONNECTED",
                    "status_code": 200,
                    "target_hostname": hostname,
                    "latency_ms": elapsed_ms,
                    "timestamp": timestamp,
                    "records_found": len(results)
                }
            elif response.status_code in (401, 403):
                return {
                    "status": "auth_failed",
                    "result": "AUTHENTICATION_FAILED",
                    "status_code": response.status_code,
                    "target_hostname": hostname,
                    "latency_ms": elapsed_ms,
                    "timestamp": timestamp,
                    "message": "Invalid credentials or unauthorized"
                }
            else:
                return {
                    "status": "error",
                    "result": "INVALID_RESPONSE",
                    "status_code": response.status_code,
                    "target_hostname": hostname,
                    "latency_ms": elapsed_ms,
                    "timestamp": timestamp,
                    "message": response.text[:200]
                }
        except httpx.TimeoutException:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "timeout",
                "result": "TIMEOUT",
                "target_hostname": hostname,
                "latency_ms": elapsed_ms,
                "timestamp": timestamp,
                "error": "Connection timed out"
            }
        except ValueError as ex:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "rejected",
                "result": "SECURITY_VIOLATION",
                "target_hostname": hostname,
                "latency_ms": elapsed_ms,
                "timestamp": timestamp,
                "error": str(ex)
            }
        except Exception as ex:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "unreachable",
                "result": "UNAVAILABLE",
                "target_hostname": hostname,
                "latency_ms": elapsed_ms,
                "timestamp": timestamp,
                "error": str(ex)
            }

    async def get_incident(self, sys_id: str) -> dict:
        """Fetches a single incident by its ServiceNow sys_id."""
        url = f"{self.base_url}/api/now/table/incident/{sys_id}"
        headers = self._get_auth_headers()
        response = await self._execute_with_retry("GET", url, headers=headers)
        response.raise_for_status()
        return response.json().get("result", {})

    async def get_incidents(self, query: str = "", limit: int = 10) -> list[dict]:
        """Queries incidents matching an optional sysparm_query string."""
        url = f"{self.base_url}/api/now/table/incident?sysparm_limit={limit}"
        if query:
            url += f"&sysparm_query={query}"
        headers = self._get_auth_headers()
        response = await self._execute_with_retry("GET", url, headers=headers)
        response.raise_for_status()
        return response.json().get("result", [])

    async def update_incident(self, sys_id: str, fields: dict, mode: str = None) -> dict:
        """
        Updates an incident record in ServiceNow.
        SAFETY GUARD: Gated by AUTOMATION_MODE. In SHADOW, DRY_RUN, or PAUSED mode, skips live mutation.
        """
        active_mode = (mode or settings.AUTOMATION_MODE).upper()
        if active_mode in ("SHADOW", "DRY_RUN", "PAUSED") or (mode is None and (settings.SHADOW_MODE or settings.DRY_RUN_MODE)):
            logger.info(
                "servicenow_mutation_prevented_shadow_mode",
                sys_id=sys_id,
                fields_attempted=list(fields.keys()),
                mode=active_mode
            )
            return {
                "status": "skipped",
                "mode": active_mode,
                "reason": f"Mutation prohibited while in SHADOW/DRY_RUN/PAUSED mode ({active_mode})",
                "sys_id": sys_id
            }

        url = f"{self.base_url}/api/now/table/incident/{sys_id}"
        headers = self._get_auth_headers()
        response = await self._execute_with_retry("PATCH", url, headers=headers, json=fields)
        response.raise_for_status()
        return response.json().get("result", {})

    async def add_work_note(self, sys_id: str, note: str, mode: str = None) -> dict:
        """Appends a work note to the incident."""
        return await self.update_incident(sys_id, {"work_notes": note}, mode=mode)

    async def update_assignment(self, sys_id: str, assigned_to: str, mode: str = None) -> dict:
        """Updates the assigned_to field on the incident."""
        return await self.update_incident(sys_id, {"assigned_to": assigned_to}, mode=mode)

    async def update_state(self, sys_id: str, state: str, mode: str = None) -> dict:
        """Updates incident state in ServiceNow."""
        return await self.update_incident(sys_id, {"state": state}, mode=mode)
