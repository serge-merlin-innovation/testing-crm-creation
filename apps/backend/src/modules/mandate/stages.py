from enum import StrEnum


class DealStage(StrEnum):
    CONFLICT_REVIEW = "conflict_review"
    PREPARATION = "preparation"
    MARKETING = "marketing"
    INFORMATION_MEMORANDUM = "information_memorandum"
    INDICATIVE_OFFERS = "indicative_offers"
    DUE_DILIGENCE = "due_diligence"
    BINDING_OFFERS = "binding_offers"
    SPA_NEGOTIATION = "spa_negotiation"
    SIGNING = "signing"
    CLOSING = "closing"
    CLOSED_WON = "closed_won"
    ABORTED = "aborted"


SELL_SIDE_STAGES: tuple[DealStage, ...] = tuple(DealStage)


def stages_for(mandate_type: str) -> tuple[DealStage, ...]:
    """Every mandate type runs on the sell-side list in v1 (DEAL-01, derived)."""
    return SELL_SIDE_STAGES
