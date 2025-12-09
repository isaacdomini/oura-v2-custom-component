"""Webhook support for Oura Ring integration."""
from __future__ import annotations

import logging
from typing import Any
import secrets

from aiohttp import ClientSession, ClientResponseError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.components import webhook

from .const import DOMAIN, WEBHOOK_API_URL

_LOGGER = logging.getLogger(__name__)


class OuraWebhookManager:
    """Manage Oura webhook subscriptions."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: OAuth2Session,
        entry_id: str,
    ) -> None:
        """Initialize the webhook manager."""
        self.hass = hass
        self.session = session
        self.entry_id = entry_id
        self._client_session: ClientSession | None = None

    @property
    def client_session(self) -> ClientSession:
        """Get aiohttp client session."""
        if self._client_session is None:
            self._client_session = async_get_clientsession(self.hass)
        return self._client_session

    async def async_register_webhook(self, webhook_id: str) -> bool:
        """Register a webhook with Oura API.
        
        Args:
            webhook_id: The webhook ID to use for this integration instance
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure we have a valid token
            await self.session.async_ensure_token_valid()
            
            if not self.session.valid_token or not self.session.token:
                _LOGGER.error("OAuth session has no valid token for webhook registration")
                return False
            
            token = self.session.token
            if 'access_token' not in token:
                _LOGGER.error("OAuth token missing access_token for webhook registration")
                return False
            
            # Build the webhook URL that Oura will call
            webhook_url = webhook.async_generate_url(self.hass, webhook_id)
            
            headers = {
                "Authorization": f"Bearer {token['access_token']}",
                "Content-Type": "application/json",
            }
            
            # Subscribe to all data types that Oura supports
            # According to Oura API docs, we need to register separately for each data type
            data_types = [
                "daily_sleep",
                "daily_readiness",
                "daily_activity",
                "sleep",  # Detailed sleep data
                "workout",
                "tag",
            ]
            
            _LOGGER.info("Registering Oura webhook: %s", webhook_url)
            
            success_count = 0
            for data_type in data_types:
                data = {
                    "callback_url": webhook_url,
                    "event_type": "create",
                    "data_type": data_type,
                }
                
                try:
                    async with self.client_session.post(
                        WEBHOOK_API_URL,
                        headers=headers,
                        json=data,
                    ) as response:
                        response.raise_for_status()
                        result = await response.json()
                        _LOGGER.debug("Registered webhook for %s: %s", data_type, result.get("id"))
                        success_count += 1
                except ClientResponseError as err:
                    # Log but continue - some data types might not be available
                    _LOGGER.debug(
                        "Could not register webhook for %s (HTTP %s): %s",
                        data_type,
                        err.status,
                        str(err),
                    )
            
            if success_count > 0:
                _LOGGER.info("Webhook registered successfully for %d data types", success_count)
                return True
            else:
                _LOGGER.error("Failed to register webhook for any data types")
                return False
                
        except ClientResponseError as err:
            _LOGGER.error(
                "Failed to register webhook (HTTP %s): %s",
                err.status,
                str(err),
            )
            return False
        except Exception as err:
            _LOGGER.error("Unexpected error registering webhook: %s", str(err))
            return False

    async def async_unregister_webhook(self, webhook_id: str) -> bool:
        """Unregister a webhook from Oura API.
        
        Args:
            webhook_id: The webhook ID to unregister
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure we have a valid token
            await self.session.async_ensure_token_valid()
            
            if not self.session.valid_token or not self.session.token:
                _LOGGER.warning("OAuth session has no valid token for webhook unregistration")
                return False
            
            token = self.session.token
            if 'access_token' not in token:
                _LOGGER.warning("OAuth token missing access_token for webhook unregistration")
                return False
            
            headers = {
                "Authorization": f"Bearer {token['access_token']}",
            }
            
            _LOGGER.info("Unregistering Oura webhook")
            
            # List all subscriptions first
            async with self.client_session.get(
                WEBHOOK_API_URL,
                headers=headers,
            ) as response:
                response.raise_for_status()
                subscriptions = await response.json()
                
                # Find and delete subscriptions that match our webhook URL
                webhook_url = webhook.async_generate_url(self.hass, webhook_id)
                
                for subscription in subscriptions.get("data", []):
                    if subscription.get("callback_url") == webhook_url:
                        subscription_id = subscription.get("id")
                        if subscription_id:
                            delete_url = f"{WEBHOOK_API_URL}/{subscription_id}"
                            async with self.client_session.delete(
                                delete_url,
                                headers=headers,
                            ) as delete_response:
                                delete_response.raise_for_status()
                                _LOGGER.info("Webhook unregistered successfully")
                
                return True
                
        except ClientResponseError as err:
            if err.status == 404:
                _LOGGER.debug("Webhook not found (already deleted)")
                return True
            _LOGGER.warning(
                "Failed to unregister webhook (HTTP %s): %s",
                err.status,
                str(err),
            )
            return False
        except Exception as err:
            _LOGGER.warning("Unexpected error unregistering webhook: %s", str(err))
            return False


async def async_handle_webhook(
    hass: HomeAssistant,
    webhook_id: str,
    request: Any,
) -> None:
    """Handle incoming webhook from Oura.
    
    Args:
        hass: Home Assistant instance
        webhook_id: The webhook ID
        request: The incoming webhook request
    """
    try:
        # Parse the webhook payload
        data = await request.json()
        
        _LOGGER.debug("Received Oura webhook: %s", data)
        
        # Find the coordinator for this webhook
        entry_id = None
        for entry_id_candidate, coordinator in hass.data.get(DOMAIN, {}).items():
            # Check if this coordinator has the matching webhook_id
            if hasattr(coordinator, "webhook_id") and coordinator.webhook_id == webhook_id:
                entry_id = entry_id_candidate
                break
        
        if not entry_id:
            _LOGGER.warning("Received webhook for unknown entry ID")
            return
        
        coordinator = hass.data[DOMAIN][entry_id]
        
        # Trigger an immediate data refresh
        _LOGGER.info("Webhook received, triggering data refresh")
        await coordinator.async_request_refresh()
        
    except Exception as err:
        _LOGGER.error("Error handling webhook: %s", err)


def generate_webhook_id(entry_id: str) -> str:
    """Generate a unique webhook ID for this config entry.
    
    Args:
        entry_id: The config entry ID
        
    Returns:
        A unique webhook ID
    """
    # Generate a secure random webhook ID
    # Include the entry_id to make it easier to identify which integration instance
    random_part = secrets.token_hex(16)
    return f"{DOMAIN}_{entry_id}_{random_part}"
