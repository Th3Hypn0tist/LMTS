from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TestTaxonomy:
    category: str
    subcategory: str

    def __post_init__(self) -> None:
        for label, value in (("category", self.category), ("subcategory", self.subcategory)):
            if not value or value != value.strip() or any(char.isspace() for char in value):
                raise ValueError(f"test taxonomy {label} must be a canonical token")

    @property
    def ref(self) -> str:
        return f"{self.category}/{self.subcategory}"


TEST_TAXONOMY: dict[str, TestTaxonomy] = {
    # Core execution capabilities.
    "core.text_generation": TestTaxonomy("core", "generation"),
    "core.workspace_multifile": TestTaxonomy("core", "workspace"),

    # General bot behavior probes. These can be compared across model, bot and composition targets.
    "bot.exact_instruction": TestTaxonomy("bot", "instruction_following"),
    "bot.negative_constraint": TestTaxonomy("bot", "constraints"),
    "bot.missing_information": TestTaxonomy("bot", "uncertainty"),
    "bot.contradiction_detection": TestTaxonomy("bot", "conflict_detection"),
    "bot.no_phantom_action": TestTaxonomy("bot", "grounding"),
    "bot.evidence_before_claim": TestTaxonomy("bot", "grounding"),
    "bot.scope_control": TestTaxonomy("bot", "scope_control"),
    "bot.goal_retention": TestTaxonomy("bot", "goal_management"),
    "bot.format_compliance": TestTaxonomy("bot", "output_contract"),
    "bot.multi_constraint": TestTaxonomy("bot", "constraints"),
    "bot.ambiguity_handling": TestTaxonomy("bot", "uncertainty"),
    "bot.stop_condition": TestTaxonomy("bot", "completion_control"),
    "bot.closed_world_unknown": TestTaxonomy("bot", "grounding"),
    "bot.self_correction": TestTaxonomy("bot", "recovery"),

    # Standalone bot-runtime candidate probes. Restricted to bot subjects.
    "bot_runtime.no_phantom_completion": TestTaxonomy("bot_runtime", "grounding"),
    "bot_runtime.scope_boundary": TestTaxonomy("bot_runtime", "scope_control"),

    # Composition/system candidate probes. Restricted to composition subjects.
    "composition.constraint_integration": TestTaxonomy("composition", "constraint_integration"),
    "composition.conflict_resolution": TestTaxonomy("composition", "conflict_resolution"),

    # Reasoning.
    "reasoning.carwash_transport": TestTaxonomy("reasoning", "goal_reasoning"),
    "reasoning.arithmetic_chain": TestTaxonomy("reasoning", "arithmetic"),
    "reasoning.symbolic_logic": TestTaxonomy("reasoning", "logic"),
    "reasoning.ordering": TestTaxonomy("reasoning", "ordering"),
    "reasoning.dependency_chain": TestTaxonomy("reasoning", "dependency"),
    "reasoning.impossible_constraints": TestTaxonomy("reasoning", "constraints"),

    # Context behavior.
    "context.carwash_goal_persistence": TestTaxonomy("context", "goal_retention"),
    "context.single_needle": TestTaxonomy("context", "retrieval"),
    "context.multi_needle": TestTaxonomy("context", "retrieval"),
    "context.early_retention": TestTaxonomy("context", "retention"),
    "context.conflict_priority": TestTaxonomy("context", "priority"),
    "context.irrelevant_resistance": TestTaxonomy("context", "distractor_resistance"),

    # Input/output robustness.
    "robustness.typo_tolerance": TestTaxonomy("robustness", "input_noise"),
    "robustness.noisy_input": TestTaxonomy("robustness", "input_noise"),
    "robustness.unicode": TestTaxonomy("robustness", "output_fidelity"),
    "robustness.mixed_language": TestTaxonomy("robustness", "language"),
    "robustness.repeated_instruction": TestTaxonomy("robustness", "instruction_stability"),

    # Performance and research.
    "performance.cold_warm": TestTaxonomy("performance", "latency"),
    "performance.repeat_variance": TestTaxonomy("performance", "variance"),
    "research.free_prompt_consistency": TestTaxonomy("research", "consistency"),
}


def taxonomy_for(test_id: str) -> TestTaxonomy:
    try:
        return TEST_TAXONOMY[test_id]
    except KeyError as exc:
        raise ValueError(f"test has no explicit taxonomy: {test_id}") from exc
