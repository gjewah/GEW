# Part of FIQ. See LICENSE file for full copyright and licensing details.
"""
Odoo 19-glue: wirer ClaudeProvider inn i Odoos native AI (`ai`-modulen) uten å endre core.

Odoo 19 har leverandør-logikken hardkodet i `ai.utils.llm_providers.PROVIDERS` (en liste) og i
`ai.utils.llm_api_service.LLMApiService` (base_url / nøkkel / dispatch). Vi utvider disse ved import.

NB: På Odoo 20 er dette omskrevet til `ai/services/` (AIProvider + AIApiService som subklasses);
da erstattes hele denne fila av to subklasser — selve Messages-API-oversettingen i
`services/anthropic.py` gjenbrukes uendret. Se [[fiq-odoo-native-ai-claude]].
"""
import logging
import os

from odoo.exceptions import UserError
from odoo.addons.ai.utils import llm_providers as _lp
from odoo.addons.ai.utils.llm_api_service import LLMApiService

from ..services.anthropic import ClaudeProvider

_logger = logging.getLogger(__name__)


def _register_provider():
    """Append «Anthropic (Claude)» til PROVIDERS (idempotent)."""
    if any(getattr(p, "name", None) == ClaudeProvider.NAME for p in _lp.PROVIDERS):
        return
    _lp.PROVIDERS.append(_lp.Provider(
        ClaudeProvider.NAME,
        ClaudeProvider.DISPLAY_NAME,
        ClaudeProvider.EMBEDDING_MODEL,
        dict(ClaudeProvider.EMBEDDING_CONFIG),
        list(ClaudeProvider.LLMS),
        # Odoo 19 la til et SJETTE felt i Provider (addons/ai/utils/llm_providers.py:14,
        # deprecated_models: list[str]). Uten det feiler modulen ved IMPORT med
        # "Provider.__new__() missing 1 required positional argument" - og da faller
        # hele installasjonen, ikke bare denne modulen. Odoo sender selv [] for sine
        # egne leverandoerer. getattr med fallback saa den taaler at ClaudeProvider
        # faar feltet senere.
        list(getattr(ClaudeProvider, "DEPRECATED_MODELS", [])),
    ))
    _logger.info("FIQ AI Claude: registrerte leverandør '%s' med %d modeller",
                 ClaudeProvider.NAME, len(ClaudeProvider.LLMS))


def _patch_service():
    """Utvid LLMApiService for anthropic-leverandøren (idempotent)."""
    if getattr(LLMApiService, "_fiq_anthropic_patched", False):
        return

    _orig_init = LLMApiService.__init__
    _orig_get_token = LLMApiService._get_api_token
    _orig_request_llm = LLMApiService._request_llm
    _orig_build_tcr = LLMApiService._build_tool_call_response

    def __init__(self, env, provider="openai"):
        if provider == ClaudeProvider.NAME:
            try:
                _orig_init(self, env, provider)
            except Exception:  # noqa: BLE001 — core kjenner ikke anthropic; vi setter alt selv
                pass
            self.env = env
            self.provider = provider
            base = env["ir.config_parameter"].sudo().get_param(ClaudeProvider.BASEURL_PARAM) \
                or ClaudeProvider.API_URL
            self.base_url = base.rstrip("/")
        else:
            _orig_init(self, env, provider)

    def _get_api_token(self):
        if getattr(self, "provider", None) == ClaudeProvider.NAME:
            key = self.env["ir.config_parameter"].sudo().get_param(ClaudeProvider.KEY_PARAM) \
                or os.getenv("ANTHROPIC_API_KEY")
            if key:
                return key
            raise UserError(self.env._(
                "Ingen API-nøkkel satt for Anthropic. Sett systemparameteren '%s'.",
                ClaudeProvider.KEY_PARAM,
            ))
        return _orig_get_token(self)

    def _request_llm(self, *args, **kwargs):
        if getattr(self, "provider", None) == ClaudeProvider.NAME:
            return self._request_llm_anthropic(*args, **kwargs)
        return _orig_request_llm(self, *args, **kwargs)

    def _request_llm_anthropic(self, llm_model, system_prompts, user_prompts, tools=None,
                               files=None, schema=None, temperature=0.2, inputs=(),
                               web_grounding=False):
        icp = self.env["ir.config_parameter"].sudo()
        try:
            max_tokens = int(icp.get_param(ClaudeProvider.MAXTOKENS_PARAM,
                                           ClaudeProvider.DEFAULT_MAX_TOKENS))
        except (TypeError, ValueError):
            max_tokens = ClaudeProvider.DEFAULT_MAX_TOKENS
        inputs = list(inputs or [])
        body = ClaudeProvider.build_message_body(
            llm_model, system_prompts, user_prompts, tools, files, schema, inputs, max_tokens,
        )
        headers = ClaudeProvider.build_headers(self._get_api_token())
        _logger.info("FIQ AI Claude: kall %s (%d melding(er), %d verktøy)",
                     llm_model, len(body.get("messages", [])), len(body.get("tools", [])))
        llm_response = self._request(
            method="post", endpoint="/messages", headers=headers, body=body,
        )
        return ClaudeProvider.parse_message_response(llm_response, inputs)

    def _build_tool_call_response(self, tool_call_id, return_value):
        if getattr(self, "provider", None) == ClaudeProvider.NAME:
            return ClaudeProvider.build_tool_result(tool_call_id, return_value)
        return _orig_build_tcr(self, tool_call_id, return_value)

    LLMApiService.__init__ = __init__
    LLMApiService._get_api_token = _get_api_token
    LLMApiService._request_llm = _request_llm
    LLMApiService._request_llm_anthropic = _request_llm_anthropic
    LLMApiService._build_tool_call_response = _build_tool_call_response
    LLMApiService._fiq_anthropic_patched = True
    _logger.info("FIQ AI Claude: LLMApiService patchet for Anthropic Messages API")


# Kjør ved import (modul-lasting) — `ai` er lastet først via depends.
_register_provider()
_patch_service()
