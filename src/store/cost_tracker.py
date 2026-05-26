"""LLM cost tracking — records token usage and estimates cost."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PRICING_USD_PER_1M = {
    "claude-haiku-4-5-20251001-thinking": {"input": 0.8, "output": 4.0},
    "claude-opus-4-6-thinking": {"input": 15.0, "output": 75.0},
}


async def track_llm_usage(
    model: str,
    purpose: str,
    input_tokens: int,
    output_tokens: int,
    target_number: int | None = None,
) -> None:
    """Record LLM usage to the database."""
    pricing = PRICING_USD_PER_1M.get(model, {"input": 1.0, "output": 5.0})
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

    try:
        from src.store.db import get_session
        from src.store.models import LLMUsage

        async with get_session() as session:
            usage = LLMUsage(
                model=model,
                purpose=purpose,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                target_number=target_number,
            )
            session.add(usage)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to track LLM usage: {e}")


async def get_cost_summary(days: int = 30) -> dict:
    """Get cost summary for the dashboard."""
    from datetime import datetime, timedelta
    from sqlalchemy import select, func

    since = datetime.utcnow() - timedelta(days=days)

    try:
        from src.store.db import get_session
        from src.store.models import LLMUsage

        async with get_session() as session:
            result = await session.execute(
                select(
                    func.sum(LLMUsage.cost_usd),
                    func.sum(LLMUsage.input_tokens),
                    func.sum(LLMUsage.output_tokens),
                    func.count(),
                ).where(LLMUsage.created_at >= since)
            )
            row = result.one()
            return {
                "total_cost_usd": round(row[0] or 0, 4),
                "total_input_tokens": row[1] or 0,
                "total_output_tokens": row[2] or 0,
                "total_calls": row[3] or 0,
                "period_days": days,
            }
    except Exception:
        return {"total_cost_usd": 0, "total_calls": 0, "period_days": days}
