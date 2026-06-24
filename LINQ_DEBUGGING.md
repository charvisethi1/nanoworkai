# Linq Connection Debugging Guide

## Overview
This guide helps diagnose and fix Linq Blue integration issues in production.

## Quick Health Check

### 1. Check Linq API Health
Visit your production API health endpoint:
```bash
curl https://your-api.onrender.com/health/linq
```

Expected healthy response:
```json
{
  "linq_api_key_set": true,
  "linq_api_key_length": 64,
  "linq_base_url": "https://api.linqapp.com/api/partner/v3",
  "api_reachable": "yes",
  "authentication": "ok",
  "chats_count": 5,
  "status": "healthy"
}
```

### 2. Check Environment Variables in Render

Go to Render Dashboard → Your Service → Environment

Required variables:
- `LINQ_API_KEY` - Your Linq Partner API key
- `LINQ_BASE_URL` - Should be `https://api.linqapp.com/api/partner/v3`

If missing:
1. Get API key from https://app.linqapp.com/settings/api
2. Add to Render environment variables
3. Redeploy the service

## Log Inspection

### Key Log Patterns to Search For

#### 1. Webhook Receipt
Look for: `[Linq webhook] Received request from`

This confirms webhooks are reaching your server. If missing:
- Check webhook URL in Linq dashboard
- Verify firewall/security settings
- Test webhook with curl

#### 2. Message Processing
Look for: `[process_message] ENTRY`

If webhook is received but this is missing:
- Check async queue is processing
- Look for exceptions in FastAPI middleware

#### 3. Message Extraction
Look for: `[process_message] Extracted`

If this shows `chat=NONE` or `phone=NONE`:
- Linq payload structure changed
- Check payload format in logs

#### 4. Database Operations
Look for: `[handle_waitlist] Entry fetched`

If this fails:
- Supabase connection issue
- Check `/health/supabase` endpoint
- Verify SUPABASE_URL and SUPABASE_SERVICE_KEY

#### 5. Message Sending
Look for: `[send_linq_message] ENTRY`

If present but messages don't arrive:
- Check for `LINQ_API_KEY not set` error
- Look for HTTP error codes (401, 403, etc.)
- Check network connectivity from Render

## Common Issues & Fixes

### Issue 1: No logs at all
**Symptom:** Complete silence, no webhook logs

**Diagnosis:**
```bash
# Test webhook endpoint directly
curl -X POST https://your-api.onrender.com/webhook/linq \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "message.received",
    "data": {
      "parts": [{"value": "test"}],
      "chat": {"id": "test-chat"},
      "sender_handle": {"handle": "+1234567890"}
    }
  }'
```

**Fixes:**
- Update webhook URL in Linq dashboard
- Check Render logs for startup errors
- Verify service is running and healthy

### Issue 2: Webhooks received but no processing
**Symptom:** `[Linq webhook] Received request` but no `[process_message] ENTRY`

**Diagnosis:** Check for exceptions in background task processing

**Fixes:**
- Look for Python exceptions in logs
- Check FastAPI BackgroundTasks are working
- Restart the service

### Issue 3: LINQ_API_KEY not set
**Symptom:** Error: `LINQ_API_KEY environment variable is not configured`

**Fixes:**
1. Go to Render Dashboard → Environment
2. Add `LINQ_API_KEY=your_key_here`
3. Click "Save Changes"
4. Service will auto-redeploy

### Issue 4: 401 Unauthorized from Linq API
**Symptom:** `/health/linq` shows `authentication: failed`

**Fixes:**
1. Get new API key from https://app.linqapp.com/
2. Update LINQ_API_KEY in Render
3. Verify you're using Partner API key (not personal key)

### Issue 5: Messages not sending
**Symptom:** Processing works but users don't receive messages

**Diagnosis:**
```bash
# Check Linq health
curl https://your-api.onrender.com/health/linq
```

**Fixes:**
- Check chat_id is being extracted correctly
- Verify LINQ_BASE_URL includes `/api/partner/v3`
- Look for rate limiting (429 errors)
- Check Linq account status

### Issue 6: Database connection errors
**Symptom:** `Failed to get waitlist entry` errors

**Diagnosis:**
```bash
# Check Supabase connectivity
curl https://your-api.onrender.com/health/supabase
```

**Fixes:**
- Verify SUPABASE_URL and SUPABASE_SERVICE_KEY
- Check Supabase project is not paused
- Verify network connectivity to Supabase

## Log Levels

The application uses structured logging. Set `LOG_LEVEL` environment variable:

- `DEBUG` - Full payload dumps, all operations
- `INFO` - Normal operation logs (default, recommended)
- `WARNING` - Only warnings and errors
- `ERROR` - Only errors

For production debugging, use `INFO` level.

## Render Log Access

### Via Dashboard
1. Go to Render Dashboard
2. Click your service
3. Click "Logs" tab
4. Use search/filter

### Via API
```bash
# Get recent logs
curl "https://api.render.com/v1/services/YOUR_SERVICE_ID/logs" \
  -H "Authorization: Bearer YOUR_RENDER_API_KEY"
```

### Searching Logs
```bash
# In Render logs, search for:
[Linq webhook]           # Webhook receipt
[process_message]        # Message processing
[handle_waitlist]        # Flow state machine
[send_linq_message]      # Outbound messages
ERROR                    # All errors
ABORT                    # Critical failures
```

## Testing in Production

### Send Test Message
Send a text to your Linq number from a phone. Expected logs:
```
[Linq webhook] Received request from
[Linq webhook] message.received | chat=... phone=...
[process_message] ENTRY
[process_message] Extracted | chat=... phone=...
[process_message] PROCESSING
[handle_waitlist] ENTRY
[send_linq_message] ENTRY
Delivered message chat=... text='...'
```

### Manual Webhook Test
```bash
curl -X POST https://your-api.onrender.com/webhook/linq \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "event_type": "message.received",
  "data": {
    "id": "test-msg-123",
    "parts": [{"type": "text", "value": "hi"}],
    "chat": {"id": "test-chat-id"},
    "sender_handle": {"handle": "+15551234567"}
  }
}
EOF
```

## Support Checklist

When reporting issues, include:
1. Output of `/health/linq`
2. Output of `/health/supabase`
3. Last 100 lines of logs containing `[Linq` or `[process_message]`
4. Timestamp of test message
5. Phone number used for testing (last 4 digits only)
6. Render service ID

## Enhanced Logging Added

The following logging improvements were added to help diagnose silent failures:

### api.py - Webhook Entry Point
- Request source IP logging
- Full payload preview (first 500 chars)
- Event type tracking
- Missing field detection (chat_id, phone)
- Intent classification logging
- Queue operations logging

### tasks.py - Message Processing
- Entry point logging with payload structure
- Field extraction logging
- Missing data detection
- Processing stage markers
- Collaboration routing logging
- Control intent logging

### waitlist_flow.py - State Machine
- Entry logging with state
- Database fetch logging
- State transitions
- Error context for DB failures

### services.py - Linq API Client
- Environment variable validation
- URL construction logging
- Payload preview before send
- Comprehensive error categorization

All logs use structured format with clear markers for grep/search.
