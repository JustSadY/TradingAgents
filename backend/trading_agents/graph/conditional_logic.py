class ConditionalLogic:
    """Graph routing decisions.

    Per-analyst routers (``should_continue_<key>``) are not defined statically here:
    ``analyst_registry.sync_registry_to_graph()`` injects one for every
    registered analyst from its ``@register_analyst`` declaration before the graph is wired.
    Debate and risk discussions are executed imperatively within their respective main nodes.
    """

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
