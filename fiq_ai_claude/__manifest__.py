# Part of FIQ. See LICENSE file for full copyright and licensing details.
{
    "name": "FIQ AI – Claude (Anthropic) Provider",
    "version": "19.0.1.0.1",
    "category": "Productivity/AI",
    "summary": "Gjør Claude (Anthropic) valgbar som leverandør i Odoos native AI",
    "description": """
FIQ AI – Claude-adapter
=======================
Legger Anthropic/Claude inn som valgbar leverandør i Odoo 19s native AI (modulen `ai`),
så Claude blir hovedmotor for AI-felt, komponering, agenter, server actions og chat.

- Registrerer «Anthropic (Claude)» i leverandør-tabellen (Claude-modellene dukker opp i nedtrekk).
- Ruter kallene til Anthropics **Messages API** (/v1/messages) — IKKE OpenAIs Responses-API,
  som Odoos openai-vei bruker og som Anthropic ikke har.
- Config-drevet base_url (system-param `ai.anthropic_base_url`, default api.anthropic.com/v1)
  → kan flippes til FIQ-gateway senere uten kodeendring.
- Embeddings + transkripsjon forblir OpenAI/Google (Anthropic mangler disse).

Forover-kompatibel: logikken ligger i `services/anthropic.py` (provider+service-splitt) som
speiler Odoo 20s `ai/services/`-arkitektur, så porten til v20 = subklasse baseklassene.
""",
    "author": "FIQ as",
    "website": "https://fiq.no",
    "depends": ["ai"],
    "data": [],
    "license": "OPL-1",
    "installable": True,
    "application": False,
}
