# Implementation Plan - Live Carta Ingestion Testing

The goal is to test whether the agent can successfully extract data from the user's live Carta account (logged in Chrome) instead of the sandbox environment.

## User Review Required

> [!IMPORTANT]
> **1. Remote Debugging Port (9222):** The agent connects to Chrome via the Chrome DevTools Protocol (CDP) on port `9222`. For the agent to interact with your live session, Chrome must be launched with remote debugging enabled.
> 
> **2. Environment Variables:** To direct the agent to the live site, we must configure the target base URLs in the `.env` file.
> 
> **3. Target Company Name:** You will need to specify a company that actually exists in your live Carta portfolio by updating the `TARGET_COMPANY` variable in the `.env` file.

---

## Proposed Changes

### Configuration Updates

#### [MODIFY] [.env](file:///c:/Users/iaman/Vscode%20Pycharm/openclaw_carta/.env)
- Add base URLs to target the live domain instead of playground sandbox:
  ```env
  CARTA_LOGIN_BASE_URL=https://login.carta.com
  CARTA_APP_BASE_URL=https://app.carta.com
  CARTA_API_BASE_URL=https://app.carta.com/api
  TARGET_COMPANY=Your Live Company Name
  ```

---

### Code Enhancements for Dynamic Domain Support

To prevent requests from leaking to the sandbox domain, we must resolve hardcoded strings across the repository.

#### [MODIFY] [url_builder.py](file:///c:/Users/iaman/Vscode%20Pycharm/openclaw_carta/services/providers/carta/api/url_builder.py)
- Import `settings` and dynamically assign `APP_BASE_URL` and `API_BASE_URL` from settings.

#### [MODIFY] [org_discovery.py](file:///c:/Users/iaman/Vscode%20Pycharm/openclaw_carta/services/providers/carta/discovery/org_discovery.py)
- Import `URLBuilder` and replace hardcoded `https://app.playground.carta.team` URLs with `URLBuilder.build_api_url()` and `URLBuilder.API_BASE_URL`.

#### [MODIFY] [start_persistent_browser.py](file:///c:/Users/iaman/Vscode%20Pycharm/openclaw_carta/scripts/start_persistent_browser.py)
- Import `settings` and launch Chrome pointing initially to the dynamic `settings.login_base_url` instead of hardcoded sandbox credentials login page.

#### [MODIFY] [provider.py](file:///c:/Users/iaman/Vscode%20Pycharm/openclaw_carta/services/providers/carta/provider.py)
- Soften route validation in `_ensure_authenticated` (e.g. check for `/investors/` but log a warning instead of throwing an error, in case the landing page is different on live Carta).

---

## Verification Plan

### Automated/Manual Verification Steps
1. **User Action:** Update `.env` with a company name that exists in their live account (e.g. replacing `MangoCart, Inc.`).
2. **User Action:** Launch Chrome on port 9222 with remote debugging enabled. They can do this by running `python scripts/start_persistent_browser.py` which will open the live login page, then manually complete the login/2FA.
3. **Model Action:** Execute a run of the crawler target targeting the live company:
   `python test_integration.py` or run a single-run test targeting that company.
4. **Validation:** Verify that the agent resolves the organization, traverses portfolio pages, captures live requests, and compiles extracted files in `output/exports/`.
