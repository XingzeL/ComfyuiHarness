"""Configuration specific to this example workflow."""
from dataclasses import dataclass


@dataclass
class RunConfig:
    checkpoint: str
    positive: str
    negative: str = ""
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg: float = 7.0
    sampler: str = "euler"
    scheduler: str = "normal"
    seed: int | None = None
    filename_prefix: str = ""

    @classmethod
    def from_dict(cls, value):
        return cls(**value)
