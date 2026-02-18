"""Feedbacks app integration tools — read-only access to feedbacks DB."""

from __future__ import annotations

from typing import Any

from agent1.tools.base import BaseTool


class FeedbacksGetCustomerResponsesTool(BaseTool):
    name = "feedbacks_get_customer_responses"
    description = "Get all survey responses for a customer by email. Returns sentiment, ratings, comments, task status, Freshdesk ticket ID."
    input_schema = {
        "type": "object",
        "properties": {
            "customer_email": {"type": "string", "description": "Customer's email address"},
        },
        "required": ["customer_email"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        customer_email = kwargs["customer_email"]
        from agent1.common.db import get_feedbacks_pool

        pool = await get_feedbacks_pool()
        if pool is None:
            return {"responses": [], "message": "Feedbacks DB not configured"}

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT sr.id, sr."customerEmail", sr."customerName", sr.sentiment,
                       sr."taskType", sr."taskStatus", sr."freshdeskTicketId",
                       sr."countryCode", sr."createdAt",
                       a."ratingValue", a."textValue", a."yesNoValue"
                FROM "SurveyResponse" sr
                LEFT JOIN "Answer" a ON a."responseId" = sr.id
                WHERE sr."customerEmail" = $1
                ORDER BY sr."createdAt" DESC
                LIMIT 50
                """,
                customer_email,
            )
        return {"responses": [dict(r) for r in rows]}


class FeedbacksGetRecentComplaintsTool(BaseTool):
    name = "feedbacks_get_recent_complaints"
    description = "Get recent negative survey responses (sentiment=negative). Filterable by country, date range."
    input_schema = {
        "type": "object",
        "properties": {
            "country_code": {"type": "string", "description": "Filter by country code (e.g., DE, US)"},
            "days": {"type": "integer", "default": 7, "description": "Look back N days"},
            "limit": {"type": "integer", "default": 20},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agent1.common.db import get_feedbacks_pool

        pool = await get_feedbacks_pool()
        if pool is None:
            return {"complaints": [], "message": "Feedbacks DB not configured"}

        days = int(kwargs.get("days", 7))
        limit = min(int(kwargs.get("limit", 20)), 100)
        country = kwargs.get("country_code")

        async with pool.acquire() as conn:
            params: list = [days, limit]
            country_filter = ""
            if country:
                country_filter = ' AND sr."countryCode" = $3'
                params.append(country)

            rows = await conn.fetch(
                f"""
                SELECT sr.id, sr."customerEmail", sr."customerName", sr.sentiment,
                       sr."taskType", sr."taskStatus", sr."freshdeskTicketId",
                       sr."countryCode", sr."createdAt"
                FROM "SurveyResponse" sr
                WHERE sr.sentiment = 'negative'
                  AND sr."createdAt" > NOW() - make_interval(days => $1)
                {country_filter}
                ORDER BY sr."createdAt" DESC
                LIMIT $2
                """,
                *params,
            )
        return {"complaints": [dict(r) for r in rows]}


class FeedbacksGetCsatSummaryTool(BaseTool):
    name = "feedbacks_get_csat_summary"
    description = "Get aggregated CSAT stats by country and time period."
    input_schema = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "default": 30, "description": "Look back N days"},
            "country_code": {"type": "string", "description": "Filter by country code"},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agent1.common.db import get_feedbacks_pool

        pool = await get_feedbacks_pool()
        if pool is None:
            return {"summary": {}, "message": "Feedbacks DB not configured"}

        days = int(kwargs.get("days", 30))

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT sr."countryCode",
                       COUNT(*) as total,
                       COUNT(*) FILTER (WHERE sr.sentiment = 'positive') as positive,
                       COUNT(*) FILTER (WHERE sr.sentiment = 'negative') as negative,
                       ROUND(AVG(a."ratingValue")::numeric, 2) as avg_rating
                FROM "SurveyResponse" sr
                LEFT JOIN "Answer" a ON a."responseId" = sr.id AND a."ratingValue" IS NOT NULL
                WHERE sr."createdAt" > NOW() - make_interval(days => $1)
                GROUP BY sr."countryCode"
                ORDER BY total DESC
                """,
                days,
            )
        return {"summary": [dict(r) for r in rows]}


class FeedbacksGetTrustpilotReviewsTool(BaseTool):
    name = "feedbacks_get_trustpilot_reviews"
    description = "Get Trustpilot reviews. Filter by stars, status, defendable flag."
    input_schema = {
        "type": "object",
        "properties": {
            "max_stars": {"type": "integer", "description": "Maximum stars (e.g., 2 for negative reviews)"},
            "status": {"type": "string", "description": "Review status filter"},
            "defendable_only": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "default": 20},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agent1.common.db import get_feedbacks_pool

        pool = await get_feedbacks_pool()
        if pool is None:
            return {"reviews": [], "message": "Feedbacks DB not configured"}

        limit = kwargs.get("limit", 20)
        max_stars = kwargs.get("max_stars")
        status = kwargs.get("status")
        defendable_only = kwargs.get("defendable_only", False)

        async with pool.acquire() as conn:
            conditions = []
            params = []
            idx = 1

            if max_stars is not None:
                conditions.append(f"stars <= ${idx}")
                params.append(max_stars)
                idx += 1
            if status:
                conditions.append(f"status = ${idx}")
                params.append(status)
                idx += 1
            if defendable_only:
                conditions.append('"isDefendable" = true')

            where = " AND ".join(conditions) if conditions else "1=1"

            rows = await conn.fetch(
                f"""
                SELECT id, "trustpilotId", title, text, stars, language,
                       "reviewerName", "reviewerCountry", "reviewCreatedAt",
                       "isDefendable", "defendableReason", status, priority,
                       "generatedResponse", "taskStatus"
                FROM "TrustpilotReview"
                WHERE {where}
                ORDER BY "reviewCreatedAt" DESC
                LIMIT {limit}
                """,
                *params,
            )
        return {"reviews": [dict(r) for r in rows]}
