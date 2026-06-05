from .model_catalog import get_known_models

VALID_MODELS = get_known_models()

def validate_model(provider: str, model: str) -> bool:
    provider_lower = provider.lower()
    if provider_lower not in VALID_MODELS:
        # If provider isn't in our catalog, we can't validate, so we assume OK
        # or we could be strict. For now, let's be flexible for unknown providers.
        return True
    return model in VALID_MODELS[provider_lower]
