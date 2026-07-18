# PulmoCare AI v1.0
## Pulmonology (Chest Medicine) Health Intelligence Platform

## CRITICAL PULMONARY EMERGENCY DISCLAIMER
- **Acute severe asthma** (silent chest, blue lips, exhaustion): 112/999/911 IMMEDIATELY
- **Tension pneumothorax** (sudden chest pain + breathlessness + low BP): Immediate needle decompression needed
- **Massive haemoptysis** (large-volume coughing up blood): Risk of asphyxiation, emergency assessment
- **ARDS / massive pulmonary embolism**: Intensive care emergency
- All content is AI-generated educational research only — NOT medical advice

## Quick Start (Windows)
1. Extract ZIP to any folder
2. Double-click **START_PulmoCare_AI.bat**
3. Auto-installs everything (2-5 min first time)
4. Browser opens at **http://localhost:5110**
5. Accept disclaimer and begin

## Security — AES-256-GCM + Software Safety Hardening
- API keys AES-256-GCM encrypted client-side before localStorage
- PBKDF2 key derivation (100,000 iterations) from device fingerprint
- XSS protection: escapeHtml(), escapeFilename(), sanitizeAIResponse()
- Backend rate limiting (30 req/60s), input sanitisation/bounding, provider whitelist
- No hardcoded secrets — all API keys from environment or client-supplied at runtime
- Opaque, non-enumerable file and report identifiers (UUID-based)
- Opaque error handling — no internal stack traces returned to client

## 6 AI Providers (All Real API Calls)
| Provider | Model | Get Key |
|---|---|---|
| Claude (Anthropic) | claude-sonnet-4-20250514 | console.anthropic.com |
| ChatGPT (OpenAI) | gpt-4o | platform.openai.com/api-keys |
| Gemini (Google) | gemini-2.0-flash | aistudio.google.com/apikey |
| Grok (xAI) | grok-2-latest | console.x.ai |
| DeepSeek | deepseek-chat | platform.deepseek.com/api_keys |
| Mistral AI | mistral-large-latest | console.mistral.ai/api-keys |

## Ambiguity Resolver
Query 2-6 AIs simultaneously (parallel) — synthesised best answer generated automatically.
Click **⚡ Ambiguity Resolver** in the Chat panel.

## Sections (16 Panels)
- **Conditions** — 20+ dropdown (airway disease, infections, ILD/occupational, malignancy, pleural, emergencies)
- **Asthma** — 3 tabs: Diagnosis/control, GINA management, acute exacerbation
- **COPD** — GOLD ABE assessment, bronchodilator therapy, biomass smoke risk, exacerbations
- **Tuberculosis** — 3 tabs: India burden, presentation/diagnosis, treatment (NTEP)
- **Interstitial Lung Disease** — IPF, CTD-associated ILD, occupational pneumoconiosis
- **Respiratory Infections** — CAP (CURB-65), acute bronchitis, antibiotic stewardship
- **Lung Cancer** — Red flag symptoms, molecular testing, staging
- **Pleural Disease** — Effusion (Light's criteria), pneumothorax
- **Pulmonary Function Tests** — 6-row reference table (spirometry, DLCO, ABG, HRCT, CTPA)
- **Emergency** — Acute severe asthma, tension pneumothorax, massive haemoptysis, ARDS
- **India Context** — Air pollution burden, NTEP TB elimination, occupational lung disease
- **Assessment** — Symptom-based AI research with smoking/exposure history field

## India Pulmonology Resources
- NTEP: National TB Elimination Programme (tbcindia.gov.in)
- AIIMS Pulmonology: aiims.edu | Ni-kshay Poshan Yojana: TB nutritional support
- PM-JAY: respiratory procedure insurance coverage
- Emergency: **112**

## Clinical Sources
GOLD | GINA | ATS/ERS | WHO | NICE | NTEP | PubMed

*PulmoCare AI — For research and educational purposes only. Not medical advice.*
*PULMONARY EMERGENCY: 112 (India) / 999 (UK) / 911 (US)*
