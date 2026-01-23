import base64
import io
import json
from io import BytesIO
from urllib.parse import urlparse
from app.services.openai_cua_common.env_utils import get_int_env, get_float_env

import requests
from PIL import Image

from app.core.config import settings


import os
import time
from requests import RequestException, Timeout, HTTPError
from celery.exceptions import SoftTimeLimitExceeded

BLOCKED_DOMAINS = [
    "maliciousbook.com",
    "evilvideos.com",
    "darkwebforum.com",
    "shadytok.com",
    "suspiciouspins.com",
    "ilanbigio.com",
]


def pp(obj):
    
    print(json.dumps(obj, indent=4))


def show_image(base_64_image):
    image_data = base64.b64decode(base_64_image)
    image = Image.open(BytesIO(image_data))
    image.show()


def calculate_image_dimensions(base_64_image):
    image_data = base64.b64decode(base_64_image)
    image = Image.open(io.BytesIO(image_data))
    return image.size


def sanitize_message(msg: dict) -> dict:
    """Return a copy of the message with image_url omitted for computer_call_output messages."""
    if msg.get("type") == "computer_call_output":
        output = msg.get("output", {})
        if isinstance(output, dict):
            sanitized = msg.copy()
            sanitized["output"] = {**output, "image_url": "[omitted]"}
            return sanitized
    return msg


def create_response(**kwargs):
    from celery.exceptions import SoftTimeLimitExceeded
    
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    if settings.OPENAI_ORG:
        headers["Openai-Organization"] = settings.OPENAI_ORG

    # Use custom timeout if provided, otherwise use default
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT_SECONDS)

    try:
        response = requests.post(url, headers=headers, json=kwargs, timeout=timeout)

        if response.status_code != 200:
            print(f"Error: {response.status_code} {response.text}")

        return response.json()
    except SoftTimeLimitExceeded:
        raise
    except Exception as e:
        print(f"Error in create_response: {e}")
        raise

def _load_timeout() -> float:
    raw_value = os.getenv("OPENAI_REQUEST_TIMEOUT", "60")
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return 60.0


DEFAULT_TIMEOUT_SECONDS = _load_timeout()
def create_advanced_response(**kwargs):
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    if settings.OPENAI_ORG:
        headers["Openai-Organization"] = settings.OPENAI_ORG

    max_retries = get_int_env("OPENAI_REQUEST_MAX_RETRIES", 3)
    base_delay = get_float_env("OPENAI_REQUEST_RETRY_BACKOFF", 1.0)
    retry_statuses = {429, 500, 502, 503, 504}

    def _format_error(exc: RequestException) -> str:
        status = getattr(exc.response, "status_code", "unknown")
        body = ""
        if getattr(exc, "response", None) is not None:
            try:
                body = exc.response.text
            except SoftTimeLimitExceeded:
                raise
            except Exception:
                body = "[unavailable]"
        return f"OpenAI response request failed (status {status}): {body or exc}"

    attempt = 0
    while True:
        try:
            response = requests.post(
                url,
                headers=headers,
                json=kwargs,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except Timeout as exc:
            if attempt >= max_retries - 1:
                raise TimeoutError(
                    f"OpenAI response request timed out after {DEFAULT_TIMEOUT_SECONDS:.0f}s"
                ) from exc
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
        except HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status in retry_statuses and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
            else:
                raise RuntimeError(_format_error(exc)) from exc
        except RequestException as exc:
            raise RuntimeError(_format_error(exc)) from exc
        attempt += 1

    return {}

def check_blocklisted_url(url: str) -> None:
    """Raise ValueError if the given URL (including subdomains) is in the blocklist."""
    hostname = urlparse(url).hostname or ""
    if any(
        hostname == blocked or hostname.endswith(f".{blocked}")
        for blocked in BLOCKED_DOMAINS
    ):
        raise ValueError(f"Blocked URL: {url}")
