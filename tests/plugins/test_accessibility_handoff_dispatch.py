import json


def test_model_tool_dispatch_passes_clarify_callback_to_accessibility_handoff():
    from model_tools import handle_function_call
    from tools.registry import registry
    from plugins.accessibility_handoff import register

    if registry.get_entry("accessibility_handoff") is None:
        class Ctx:
            def register_tool(self, **kwargs):
                registry.register(**kwargs)
        register(Ctx())

    def callback(question, choices):
        assert choices is None
        assert "Reply with exactly one letter: A, B, or C." in question
        return "A"

    result = json.loads(handle_function_call(
        "accessibility_handoff",
        {
            "question": "Human verification needed.",
            "choices": ["click checkbox", "reload challenge", "switch to audio"],
            "require_headed_browser": False,
        },
        clarify_callback=callback,
    ))

    assert result == {"selected": "A", "choice": "click checkbox"}
