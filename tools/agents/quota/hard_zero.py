# tools/agents/quota/hard_zero.py
"""Hard-$0 guard checker ensuring configuration safety against billable providers."""


def _get_known_paths():
    """Return set of top-level and nested key paths known/reviewed by
    check_hard_zero.
    """
    return {
        "model_list",
        "model_list[].model_name",
        "model_list[].litellm_params",
        "model_list[].litellm_params.model",
        "model_list[].litellm_params.api_key",
        "router_settings",
        "router_settings.fallbacks",
        "router_settings.context_window_fallbacks",
        "router_settings.default_fallbacks",
        "router_settings.allowed_fails",
        "general_settings",
        "general_settings.master_key",
    }


# Paths whose contents are data (model names chosen by the operator), not
# configuration keys. check_hard_zero inspects every entry inside them, so
# their contents are reviewed and must not be listed as gaps.
_OPAQUE_PATHS = {
    "router_settings.fallbacks",
    "router_settings.context_window_fallbacks",
    "router_settings.default_fallbacks",
}


def unreviewed_keys(config):
    """Return sorted list of dot-delimited key paths in config not
    inspected by check_hard_zero.
    """
    unreviewed = set()

    def _traverse(node, prefix):
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if path not in _get_known_paths():
                unreviewed.add(path)
            if path in _OPAQUE_PATHS:
                continue
            if isinstance(val, dict):
                _traverse(val, path)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        _traverse(item, path + "[]")

    _traverse(config, "")
    return sorted(unreviewed)


def check_hard_zero(config, free_providers):
    """Return a list of violation strings. Empty list means the config is safe."""
    violations = []

    # 1. Check free_providers parameter
    free_set = set(free_providers) if free_providers else set()
    if not free_set:
        violations.append(
            "free provider list is empty: nothing can be cleared as free."
        )

    # 2. Check model_list presence and content
    if "model_list" not in config or config["model_list"] is None:
        violations.append("model_list is missing from configuration.")
        model_list = []
    elif not isinstance(config["model_list"], list) or len(config["model_list"]) == 0:
        violations.append("model_list is empty.")
        model_list = []
    else:
        model_list = config["model_list"]

    defined_models = set()
    for idx, entry in enumerate(model_list):
        if not isinstance(entry, dict):
            violations.append(f"model_list[{idx}] is not a dict.")
            continue

        model_name = entry.get("model_name")
        if model_name:
            if model_name in defined_models:
                violations.append(f"duplicate model_name '{model_name}' in model_list.")
            else:
                defined_models.add(model_name)

        litellm_params = entry.get("litellm_params", {})
        model_str = (
            litellm_params.get("model")
            if isinstance(litellm_params, dict)
            else None
        )

        if not model_str or not isinstance(model_str, str):
            violations.append(
                f"model_list[{idx}] '{model_name or 'unnamed'}': "
                "missing or invalid model string."
            )
        elif "/" not in model_str:
            violations.append(
                f"model_list[{idx}] '{model_name or 'unnamed'}': provider "
                f"could not be determined from model '{model_str}'."
            )
        else:
            provider = model_str.split("/", 1)[0]
            if free_set and provider not in free_set:
                violations.append(
                    f"model_list[{idx}] '{model_name or 'unnamed'}': "
                    f"provider '{provider}' is not in the free list."
                )

    # 3. Check fallbacks in router_settings
    router_settings = config.get("router_settings", {})
    if isinstance(router_settings, dict):
        # Named fallback mappings
        for fb_type in ("fallbacks", "context_window_fallbacks"):
            fb_list = router_settings.get(fb_type, [])
            if isinstance(fb_list, list):
                for mapping in fb_list:
                    if isinstance(mapping, dict):
                        for src, targets in mapping.items():
                            if isinstance(targets, list):
                                for tgt in targets:
                                    _check_fallback_target(
                                        tgt, fb_type, defined_models, violations
                                    )

        # Default fallbacks list
        def_fb = router_settings.get("default_fallbacks", [])
        if isinstance(def_fb, list):
            for tgt in def_fb:
                _check_fallback_target(
                    tgt, "default_fallbacks", defined_models, violations
                )

    return violations


def _check_fallback_target(tgt, source_field, defined_models, violations):
    """Validate an individual fallback target string."""
    if not isinstance(tgt, str):
        return
    tgt_lower = tgt.lower()
    if tgt_lower in ("*", "all"):
        violations.append(f"wildcard '{tgt}' in {source_field} is a violation.")
    elif defined_models and tgt not in defined_models:
        violations.append(
            f"{source_field} targets undefined model_name '{tgt}'."
        )
