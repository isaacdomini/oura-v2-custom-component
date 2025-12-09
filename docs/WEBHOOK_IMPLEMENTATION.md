# Webhook Implementation Guide

## Overview

The Oura Ring v2 integration now supports webhooks for real-time data updates. This document describes the webhook implementation and how to use it.

## Features

### User Benefits

- **Real-time updates**: Data appears in Home Assistant immediately when your ring syncs with Oura
- **Reduced API usage**: No constant polling, data is fetched only when changes occur
- **Better responsiveness**: Sensors update as soon as Oura processes new data
- **Automatic fallback**: If webhooks fail, the integration falls back to polling mode

### Technical Implementation

#### Architecture

1. **Webhook Manager** (`webhook.py`):
   - Manages webhook registration/unregistration with Oura API
   - Generates secure webhook IDs per integration instance
   - Handles multiple data type subscriptions (sleep, activity, readiness, etc.)

2. **Webhook Handler**:
   - Receives incoming webhook events from Oura
   - Validates the webhook ID
   - Triggers immediate data refresh in the coordinator

3. **Configuration Flow**:
   - Adds "Use webhooks" option in integration settings
   - Defaults to disabled for backward compatibility
   - Can be changed at any time through the options flow

#### Webhook Registration

When webhooks are enabled, the integration:

1. Generates a unique, secure webhook ID using `secrets.token_hex()`
2. Registers the webhook handler with Home Assistant's webhook component
3. Subscribes to multiple data types with the Oura API:
   - `daily_sleep` - Daily sleep summaries
   - `daily_readiness` - Readiness scores
   - `daily_activity` - Activity summaries
   - `sleep` - Detailed sleep data
   - `workout` - Workout data
   - `tag` - Tags and notes

4. Stores the webhook ID in the config entry for persistence

#### Webhook Cleanup

When the integration is unloaded or webhooks are disabled:

1. Queries Oura API for all active subscriptions
2. Finds subscriptions matching the webhook URL
3. Deletes each subscription
4. Unregisters the webhook handler from Home Assistant

## Usage

### Enabling Webhooks

1. Go to **Settings** → **Devices & Services**
2. Find "Oura Ring" and click **CONFIGURE**
3. Enable "Use webhooks for real-time updates"
4. Click **SUBMIT**

The integration will reload and register the webhook with Oura.

### Requirements

For webhooks to work, your Home Assistant instance must be:

- Accessible from the internet (Oura needs to send HTTP requests to it)
- Using HTTPS (required by Oura API)

**Home Assistant Cloud (Nabu Casa)** automatically meets these requirements.

For self-hosted setups:
- Configure a reverse proxy with SSL/TLS
- Set up port forwarding
- Use a domain name or DuckDNS

### Verifying Webhook Status

Check the Home Assistant logs for:

```
Webhook registered successfully for X data types
```

You can also check the [Oura Developer Portal](https://developer.ouraring.com/applications) to see active webhook subscriptions.

## Troubleshooting

### Webhooks Not Working

1. **Check Home Assistant accessibility**:
   - Verify your instance has a public URL
   - Test accessing it from outside your network
   
2. **Check logs**:
   ```
   Settings → System → Logs
   ```
   Look for webhook registration messages

3. **Verify Oura API status**:
   - Check the Oura Developer Portal for webhook subscription status
   - Look for delivery failures or errors

4. **Fallback to polling**:
   - If webhooks don't work, disable them in the integration options
   - The integration will use polling mode instead

### Common Issues

**"Failed to register webhook"**
- Home Assistant is not accessible from the internet
- OAuth token is invalid or expired
- Oura API is temporarily unavailable

**"Received webhook for unknown entry ID"**
- Webhook ID mismatch (should auto-resolve on restart)
- Multiple integration instances may have conflicting IDs

**No webhook events received**
- Home Assistant firewall blocking incoming connections
- Reverse proxy not configured correctly
- Oura API having delivery issues

## API Details

### Oura Webhook API

**Endpoint**: `https://api.ouraring.com/v2/webhook/subscription`

**Registration Request**:
```json
{
  "callback_url": "https://your-ha-instance.com/api/webhook/webhook_id",
  "event_type": "create",
  "data_type": "daily_sleep"
}
```

**Response**:
```json
{
  "id": "subscription_id",
  "callback_url": "https://your-ha-instance.com/api/webhook/webhook_id",
  "event_type": "create",
  "data_type": "daily_sleep",
  "expiration_time": null
}
```

### Webhook Payload

When data changes, Oura sends:

```json
{
  "event_type": "create",
  "data_type": "daily_sleep",
  "user_id": "user_id",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

The integration responds by fetching the latest data from the API.

## Development Notes

### Code Structure

```
custom_components/oura/
├── __init__.py          # Webhook setup/teardown in async_setup_entry/async_unload_entry
├── webhook.py           # OuraWebhookManager and async_handle_webhook
├── const.py             # CONF_USE_WEBHOOKS, CONF_WEBHOOK_ID, WEBHOOK_API_URL
├── config_flow.py       # Options flow with webhook toggle
└── coordinator.py       # Webhook-related attributes
```

### Testing

Tests are in `tests/test_webhook.py`:
- Webhook ID generation
- Registration success/failure scenarios
- Unregistration scenarios
- Webhook event handling

### Future Enhancements

Possible improvements:
- Webhook health monitoring and auto-recovery
- Detailed webhook delivery statistics
- Per-data-type webhook configuration
- Webhook event logging for debugging

## References

- [Oura API v2 Documentation](https://cloud.ouraring.com/v2/docs)
- [Oura Webhook Documentation](https://cloud.ouraring.com/v2/docs#tag/Webhook-Subscription-Routes)
- [Home Assistant Webhook Component](https://www.home-assistant.io/integrations/webhook/)
