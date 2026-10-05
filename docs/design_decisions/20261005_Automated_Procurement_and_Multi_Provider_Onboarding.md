# Architecture Decision Record: Automated Procurement and Multi-Provider Onboarding

**Date**: 2026-10-05  
**Status**: Accepted  
**Deciders**: Engineering Team & Product Owner  

## Context
Configuring AI provider integrations requires API keys, admin reports, or local binaries (e.g. Google AI Studio, Anthropic Console, OpenAI Platform, M365 Copilot Admin Center, Ollama runtime). Users frequently struggle to locate the exact procurement URLs, resulting in onboarding friction, misconfigurations, and abandonment.

## Decision
1. **Interactive Procurement Buttons on Provider Hub Cards**:
   - Provide direct 1-click external navigation buttons (`Get Gemini API Key ↗`, `Get Anthropic Key ↗`, `Get OpenAI Key ↗`, `M365 Admin Usage ↗`, `Download Ollama ↗`) rendered directly on each provider card with target URLs (`https://aistudio.google.com/app/apikey`, `https://console.anthropic.com/settings/keys`, `https://platform.openai.com/api-keys`, etc.).
2. **In-Modal Guided Step-by-Step Procurement Banners**:
   - Inside each configuration modal (Gemini, Claude, ChatGPT, Copilot), display a styled callout banner (`.procure-guide-card`) detailing 3 unambiguous steps with direct launch buttons, quickstart docs, and pricing/quotas links.
3. **Backend DPAPI Configuration Endpoints**:
   - Expose dedicated, uniform REST API endpoints (`/api/providers/{provider}/config`) supporting native Windows DPAPI encryption and immediate validation/model interrogation.

## Consequences
- **Positive**: Eliminates user confusion; guides users to official key generation portals in a single click; keeps security uncompromising with Windows DPAPI encryption; maintains zero external dependencies.
- **Negative**: Relies on third-party provider URLs remaining stable over time.
