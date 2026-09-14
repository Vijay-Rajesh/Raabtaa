# WhatsApp Cloud API Integration

This guide is for the developer responsible for connecting SafeReach to Meta
WhatsApp Cloud API. SafeReach sends WhatsApp notifications through
`app/services/whatsapp_service.py`; application routes and the notification
service should not call Meta directly.

## What is required

Create or use a Meta Developer application with the WhatsApp product enabled
and collect:

1. A WhatsApp Business Account (WABA) ID.
2. A WhatsApp sender phone number ID.
3. A valid Meta Graph API access token with permission to send WhatsApp
   messages.
4. A public HTTPS webhook URL if delivery-status callbacks are required.
5. A private webhook verification token chosen by the developer.

The access token and verification token are different values. The Meta access
token authorizes outbound API calls; `WHATSAPP_VERIFY_TOKEN` is only used to
verify the webhook handshake.

## Environment configuration

Copy `.env.example` to `.env` and fill the values locally. Never commit `.env`
or paste tokens into documentation, pull requests, logs, or chat.

```dotenv
WHATSAPP_ACCESS_TOKEN=<Meta access token>
WHATSAPP_PHONE_NUMBER_ID=<sender phone number ID>
WHATSAPP_BUSINESS_ACCOUNT_ID=<WABA ID>
WHATSAPP_API_VERSION=v20.0
WHATSAPP_VERIFY_TOKEN=<private webhook verification value>
WHATSAPP_MOCK_MODE=false
```

For local development, keep `WHATSAPP_MOCK_MODE=true`. Mock mode prints the
message and creates an application delivery record but does not contact Meta
and cannot deliver to a handset.

Restart the FastAPI process after changing environment variables because
settings are loaded when the application starts.

## Recipient requirements

- Store phone numbers in international E.164 format, for example
  `+923240251086`, not `03240251086`.
- The recipient must be a WhatsApp-enabled number.
- During development, the recipient may need to be added as a test recipient
  in the Meta WhatsApp dashboard.
- The sender phone number must be registered and available in the WABA.

## Meta setup sequence

1. Create a Meta App at the Meta for Developers dashboard.
2. Add the WhatsApp product.
3. Select or create the WhatsApp Business Account.
4. Register a sender phone number and copy its phone number ID.
5. Generate a long-lived or system-user access token with the required
   WhatsApp messaging permissions.
6. Add the sender and test recipients in the WhatsApp API configuration.
7. Put the values in the local `.env`.
8. Set `WHATSAPP_MOCK_MODE=false`.
9. Restart the API and send a controlled test notification.

## Message rules

SafeReach currently sends:

- A one-time welcome message to a newly registered user.
- A one-time welcome message to a newly added family member.
- SOS, arrival, late, deviation, and other safety notifications afterward.

The backend stores `welcome_message_sent_at` on users and family members. Before
dispatching a non-welcome notification, the notification service attempts the
recipient's welcome message if that timestamp is empty. A successful welcome is
persisted before the follow-up alert is sent. If the welcome provider fails,
the safety alert continues and the welcome can be retried later.

Free-form text messages are subject to Meta's customer-service conversation
window. For messages sent outside that window, use an approved template with
`send_template_message()` and configure the template in Meta Business
Manager. Do not assume a successful HTTP response means the recipient has
read the message; use webhook statuses for sent, delivered, read, and failed
states.

## Webhook configuration

The webhook needs:

- A public HTTPS URL routed to the SafeReach webhook endpoint.
- The same private value in Meta and `WHATSAPP_VERIFY_TOKEN`.
- Subscription to WhatsApp message/status events.

Keep webhook verification separate from the API access token. Never use an
`EAAP...` access token as the verification token.

## Testing checklist

### Mock test

```dotenv
WHATSAPP_MOCK_MODE=true
```

Trigger registration, add a family member, and trigger SOS. The API logs
`MOCK WHATSAPP SENT`; no handset message is expected.

### Live test

```dotenv
WHATSAPP_MOCK_MODE=false
```

Confirm all of the following:

- The API starts without missing-credential errors.
- The recipient is in E.164 format.
- The first Meta response contains a real WhatsApp message ID (`wamid...`),
  not `mock-...`.
- A `whatsapp_messages` row is created with the provider ID.
- The `notifications` row changes to `sent`.
- Webhook callbacks update delivery/read/failure status when configured.

Run the backend tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `401 Authentication Error` | Expired, revoked, malformed, or incorrectly scoped access token |
| `Recipient phone number not valid` | Local format, non-WhatsApp number, or unapproved test recipient |
| Mock output appears in terminal | `WHATSAPP_MOCK_MODE=true` |
| `mock-...` message ID | Mock mode; Meta was not called |
| HTTP success but no delivery | Provider accepted the request; inspect webhook status and recipient eligibility |
| Free-form message rejected | Outside Meta's service window; use an approved template |
| Welcome appears repeatedly | Delivery did not succeed, so `welcome_message_sent_at` was not persisted |

## Security requirements

- Revoke any token that has been exposed.
- Use a secret manager in staging/production.
- Do not log access tokens, full authorization headers, or message payloads
  containing unnecessary personal data.
- Use HTTPS for webhooks.
- Restrict webhook verification and validate Meta signatures where supported.
- Keep mock mode enabled in tests and local development unless a deliberate
  live test is being performed.
