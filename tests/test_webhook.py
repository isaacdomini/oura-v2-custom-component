"""Tests for Oura Ring webhook support."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from homeassistant.core import HomeAssistant
from custom_components.oura.webhook import (
    OuraWebhookManager,
    async_handle_webhook,
    generate_webhook_id,
)
from custom_components.oura.const import DOMAIN


@pytest.fixture
def mock_oauth2_session() -> MagicMock:
    """Mock OAuth2Session for testing."""
    session = MagicMock()
    session.async_ensure_token_valid = AsyncMock()
    session.valid_token = True
    session.token = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
    }
    return session


@pytest.fixture
def mock_webhook_manager(mock_oauth2_session) -> OuraWebhookManager:
    """Create a mock webhook manager."""
    hass = MagicMock(spec=HomeAssistant)
    manager = OuraWebhookManager(hass, mock_oauth2_session, "test_entry_id")
    return manager


class TestWebhookGeneration:
    """Test webhook ID generation."""

    def test_generate_webhook_id(self):
        """Test that webhook IDs are generated correctly."""
        entry_id = "test_entry_123"
        webhook_id = generate_webhook_id(entry_id)
        
        assert webhook_id.startswith(f"{DOMAIN}_{entry_id}_")
        assert len(webhook_id) > len(f"{DOMAIN}_{entry_id}_")
    
    def test_generate_webhook_id_unique(self):
        """Test that generated webhook IDs are unique."""
        entry_id = "test_entry_123"
        webhook_id_1 = generate_webhook_id(entry_id)
        webhook_id_2 = generate_webhook_id(entry_id)
        
        assert webhook_id_1 != webhook_id_2


class TestOuraWebhookManager:
    """Test the OuraWebhookManager class."""

    @pytest.mark.asyncio
    async def test_register_webhook_success(self, mock_webhook_manager):
        """Test successful webhook registration."""
        webhook_id = "test_webhook_id"
        
        # Mock the HTTP response
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"id": "subscription_123"})
        
        mock_session = MagicMock()
        mock_session.post = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock()
            )
        )
        
        with patch.object(mock_webhook_manager, "client_session", mock_session):
            with patch("custom_components.oura.webhook.webhook.async_generate_url", return_value="http://test.local/webhook"):
                result = await mock_webhook_manager.async_register_webhook(webhook_id)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_register_webhook_no_token(self, mock_oauth2_session):
        """Test webhook registration fails without valid token."""
        hass = MagicMock(spec=HomeAssistant)
        manager = OuraWebhookManager(hass, mock_oauth2_session, "test_entry_id")
        
        # Simulate no valid token
        mock_oauth2_session.valid_token = False
        
        result = await manager.async_register_webhook("test_webhook_id")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_unregister_webhook_success(self, mock_webhook_manager):
        """Test successful webhook unregistration."""
        webhook_id = "test_webhook_id"
        
        # Mock the list response
        mock_list_response = AsyncMock()
        mock_list_response.raise_for_status = MagicMock()
        mock_list_response.json = AsyncMock(return_value={
            "data": [
                {
                    "id": "subscription_123",
                    "callback_url": "http://test.local/webhook"
                }
            ]
        })
        
        # Mock the delete response
        mock_delete_response = AsyncMock()
        mock_delete_response.raise_for_status = MagicMock()
        
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_list_response),
                __aexit__=AsyncMock()
            )
        )
        mock_session.delete = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_delete_response),
                __aexit__=AsyncMock()
            )
        )
        
        with patch.object(mock_webhook_manager, "client_session", mock_session):
            with patch("custom_components.oura.webhook.webhook.async_generate_url", return_value="http://test.local/webhook"):
                result = await mock_webhook_manager.async_unregister_webhook(webhook_id)
        
        assert result is True


class TestWebhookHandler:
    """Test webhook handling."""

    @pytest.mark.asyncio
    async def test_handle_webhook_triggers_refresh(self):
        """Test that webhook handling triggers a coordinator refresh."""
        hass = MagicMock(spec=HomeAssistant)
        webhook_id = "test_webhook_id"
        
        # Mock coordinator
        mock_coordinator = MagicMock()
        mock_coordinator.async_request_refresh = AsyncMock()
        mock_coordinator.entry = MagicMock()
        mock_coordinator.entry.data = {"webhook_id": webhook_id}
        
        # Set up hass data
        hass.data = {
            DOMAIN: {
                "test_entry_id": mock_coordinator
            }
        }
        
        # Mock request
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"event": "data.update"})
        
        # Handle webhook
        await async_handle_webhook(hass, webhook_id, mock_request)
        
        # Verify refresh was called
        mock_coordinator.async_request_refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_webhook_unknown_id(self):
        """Test handling webhook with unknown ID."""
        hass = MagicMock(spec=HomeAssistant)
        hass.data = {DOMAIN: {}}
        
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"event": "data.update"})
        
        # Should not raise an exception
        await async_handle_webhook(hass, "unknown_webhook_id", mock_request)
