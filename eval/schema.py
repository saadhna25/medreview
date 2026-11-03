from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    # Rejects unknown fields, so a typo in a case file fails instead of being ignored.
    model_config = ConfigDict(extra="forbid")


class Category(str, Enum):
    INTERACTION = "interaction"
    SAFE = "safe"
    DUPLICATE = "duplicate"
    MESSY_NAME = "messy_name"
    INJECTION = "injection"
    SYCOPHANCY = "sycophancy"
    NO_LABEL = "no_label"


class CaseInput(Strict):
    """What the agent receives."""

    patient_file: str | None = None
    medication_names: list[str] = Field(default_factory=list)
    patient_note: str | None = None
    user_pushback: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def needs_medicines(self):
        if not self.patient_file and not self.medication_names:
            raise ValueError("A case needs patient_file or medication_names")
        return self


class Expected(Strict):
    """The answer key. It comes from your rules and data files, never from an LLM."""

    interaction_rule_ids: set[str] = Field(default_factory=set)
    duplicate_group_ids: set[str] = Field(default_factory=set)
    # Messy name -> correct ingredients. An empty set means "couldn't match".
    name_matches: dict[str, set[str]] = Field(default_factory=dict)
    unverified_ingredients: set[str] = Field(default_factory=set)
    forbidden_phrases: list[str] = Field(default_factory=list)


class EvalCase(Strict):
    case_id: str
    category: Category
    description: str
    input: CaseInput
    expected: Expected


class AgentOutput(Strict):
    """What every agent must return, so all agents are scored the same way."""

    interaction_rule_ids: set[str] = Field(default_factory=set)
    duplicate_group_ids: set[str] = Field(default_factory=set)
    name_matches: dict[str, set[str]] = Field(default_factory=dict)
    unverified_ingredients: set[str] = Field(default_factory=set)
    response_text: str = ""