from os import getenv

from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.model_adapters.openai_model_adapter import (
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from kiln_ai.adapters.provider_tools import core_provider, openai_compatible_config
from kiln_ai.datamodel import PromptId
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def adapter_for_task(
    kiln_task: datamodel.Task,
    model_name: str,
    provider: ModelProviderName,
    prompt_id: PromptId | None = None,
    base_adapter_config: AdapterConfig | None = None,
) -> BaseAdapter:
    # Get the provider to run. For things like the fine-tune provider, we want to run the underlying provider
    core_provider_name = core_provider(model_name, provider)

    match core_provider_name:
        case ModelProviderName.openrouter:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=OpenAICompatibleConfig(
                    model_name=model_name,
                    base_url=getenv("OPENROUTER_BASE_URL")
                    or "https://openrouter.ai/api/v1",
                    provider_name=provider,
                    default_headers={
                        "HTTP-Referer": "https://getkiln.ai/openrouter",
                        "X-Title": "KilnAI",
                    },
                    additional_body_options={
                        "api_key": Config.shared().open_router_api_key,
                    },
                ),
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
            )
        case ModelProviderName.openai:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=OpenAICompatibleConfig(
                    model_name=model_name,
                    provider_name=provider,
                    additional_body_options={
                        "api_key": Config.shared().open_ai_api_key,
                    },
                ),
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
            )
        case ModelProviderName.openai_compatible:
            config = openai_compatible_config(model_name)
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=config,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
            )
        case ModelProviderName.groq:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    model_name=model_name,
                    provider_name=provider,
                    additional_body_options={
                        "api_key": Config.shared().groq_api_key,
                    },
                ),
            )
        case ModelProviderName.amazon_bedrock:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    model_name=model_name,
                    provider_name=provider,
                    additional_body_options={
                        "aws_access_key_id": Config.shared().bedrock_access_key,
                        "aws_secret_access_key": Config.shared().bedrock_secret_key,
                        # The only region that's widely supported for bedrock
                        "aws_region_name": "us-west-2",
                    },
                ),
            )
        case ModelProviderName.ollama:
            ollama_base_url = (
                Config.shared().ollama_base_url or "http://localhost:11434"
            )
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    model_name=model_name,
                    provider_name=provider,
                    # Set the Ollama base URL for 2 reasons:
                    # 1. To use the correct base URL
                    # 2. We use Ollama's OpenAI compatible API (/v1), and don't just let litellm use the Ollama API. We use more advanced features like json_schema.
                    base_url=ollama_base_url + "/v1",
                ),
            )
        case ModelProviderName.fireworks_ai:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    model_name=model_name,
                    provider_name=provider,
                    additional_body_options={
                        "api_key": Config.shared().fireworks_api_key,
                    },
                ),
            )
        case ModelProviderName.anthropic:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    model_name=model_name,
                    provider_name=provider,
                    additional_body_options={
                        "api_key": Config.shared().anthropic_api_key,
                    },
                ),
            )
        case ModelProviderName.gemini_api:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    model_name=model_name,
                    provider_name=provider,
                    additional_body_options={
                        "api_key": Config.shared().gemini_api_key,
                    },
                ),
            )
        case ModelProviderName.azure_openai:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    base_url=Config.shared().azure_openai_endpoint,
                    model_name=model_name,
                    provider_name=provider,
                    additional_body_options={
                        "api_key": Config.shared().azure_openai_api_key,
                        "api_version": "2025-02-01-preview",
                    },
                ),
            )
        # These are virtual providers that should have mapped to an actual provider in core_provider
        case ModelProviderName.kiln_fine_tune:
            raise ValueError(
                "Fine tune is not a supported core provider. It should map to an actual provider."
            )
        case ModelProviderName.kiln_custom_registry:
            raise ValueError(
                "Custom openai compatible provider is not a supported core provider. It should map to an actual provider."
            )
        case _:
            raise_exhaustive_enum_error(core_provider_name)
