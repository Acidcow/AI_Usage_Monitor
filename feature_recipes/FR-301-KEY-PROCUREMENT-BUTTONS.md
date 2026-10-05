# Feature Recipe FR-301: Automated Key Procurement Buttons & Step-by-Step Guides

## 1. Goal
Add prominent, interactive buttons and visual guidance to automagically direct users to official provider portals to procure API keys (Google AI Studio for Gemini, Anthropic Console for Claude, OpenAI Platform for ChatGPT, M365 Admin for Copilot, and Ollama Hub for local models).

## 2. Technical Requirements
1. **Interactive Procurement Buttons on Provider Hub Cards**:
   - Google Gemini: Link to `https://aistudio.google.com/app/apikey` (Get Gemini API Key ↗), plus links to documentation and pricing.
   - Claude (Anthropic): Link to `https://console.anthropic.com/settings/keys` (Get Anthropic Key ↗), plus usage/costs.
   - ChatGPT / OpenAI: Link to `https://platform.openai.com/api-keys` (Get OpenAI Key ↗), plus usage dashboard.
   - M365 Copilot: Link to `https://admin.microsoft.com/#/reportsUsage/CopilotActivity` and `https://copilotstudio.microsoft.com`.
   - Ollama Local: Link to `https://ollama.com/download` and `https://ollama.com/library`.
2. **In-Modal Step-by-Step Procurement Banners**:
   - Provide a prominent, styled callout banner in each configuration modal with numbered steps (1. Click button to open portal, 2. Generate key, 3. Paste below).
   - High-contrast `.btn-procure` button with visual icon, hover glow, and `target="_blank" rel="noopener noreferrer"`.
3. **Desktop Native & Browser Integration**:
   - Open target URLs in the user's default browser with full security attributes.
   - Provide fallback system URL opening helper if requested via desktop API (`/api/system/open-url`).

## 3. Verification Criteria
- All buttons render clearly with glowing visual hierarchy.
- Clicking buttons opens official vendor key generation pages directly in new browser tabs.
- Modals include guidance with zero ambiguity.
