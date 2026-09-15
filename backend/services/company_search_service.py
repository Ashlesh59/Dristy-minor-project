"""
services/company_search_service.py
--------------------------------------------------------------------------
Local Company & Security search engine.
Executes indexed, joined database queries with 5-tier deterministic ranking
and literal SQL LIKE wildcard escaping.
--------------------------------------------------------------------------
"""

import re
from typing import Dict, Any, List, Optional
from sqlalchemy import case, or_

from database.db import db
from models.company import Company
from models.security import Security
from services.importer.normalizer import normalize_company_name


def escape_like(s: str) -> str:
    """Escapes SQL LIKE wildcards (%, _) and the escape backslash."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class CompanySearchService:
    @staticmethod
    def search(
        query: str,
        country: Optional[str] = None,
        exchange: Optional[str] = None,
        asset_type: Optional[str] = None,
        limit: int = 10,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Searches companies joined with securities using local SQLite tables.
        Returns ranked matching items with deterministic tie-breaking.
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        # Bound limit between 1 and 20
        limit = max(1, min(limit, 20))

        # Filter normalizations
        norm_country = country.strip().upper() if country and country.strip() else None
        norm_exchange = exchange.strip().upper() if exchange and exchange.strip() else None
        norm_asset_type = asset_type.strip().title() if asset_type and asset_type.strip() else None

        # Base joined query
        base_query = db.session.query(Company, Security).join(
            Security, Security.company_id == Company.id
        )

        # Active status filters
        if active_only:
            base_query = base_query.filter(Security.is_active.is_(True)).filter(
                Company.is_active.is_(True)
            )

        # Exchange, country, asset_type filters
        if norm_exchange:
            base_query = base_query.filter(Security.exchange == norm_exchange)
        if norm_country:
            base_query = base_query.filter(Company.country == norm_country)
        if norm_asset_type:
            base_query = base_query.filter(Security.asset_type == norm_asset_type)

        # 1-character query rule: exact symbol match only
        if len(clean_q) == 1:
            if not clean_q.isalnum():
                return []
            base_query = base_query.filter(Security.symbol == clean_q.upper())
            base_query = base_query.order_by(Security.symbol.asc(), Security.series.asc())
            rows = base_query.limit(limit).all()
            return [CompanySearchService._format_result(c, s) for c, s in rows]

        # >= 2 characters: multi-field matching with 5-tier ranking
        clean_norm = normalize_company_name(clean_q)
        escaped_raw = escape_like(clean_q)
        escaped_upper = escape_like(clean_q.upper())
        escaped_norm = escape_like(clean_norm)

        # Match criteria (OR condition)
        match_filter = or_(
            Security.symbol == clean_q.upper(),
            Security.symbol.like(f"{escaped_upper}%", escape="\\"),
            Security.symbol.like(f"%{escaped_upper}%", escape="\\"),
            Company.normalized_name == clean_norm,
            Company.normalized_name.like(f"{escaped_norm}%", escape="\\"),
            Company.normalized_name.like(f"%{escaped_norm}%", escape="\\"),
            Company.display_name.like(f"%{escaped_raw}%", escape="\\"),
            Company.legal_name.like(f"%{escaped_raw}%", escape="\\"),
            Security.isin.like(f"{escaped_upper}%", escape="\\"),
        )
        base_query = base_query.filter(match_filter)

        # 5-tier SQL ranking expression
        rank_expr = case(
            # Rank 1: Exact symbol match
            (Security.symbol == clean_q.upper(), 1),
            # Rank 2: Exact company name match
            (Company.normalized_name == clean_norm, 2),
            # Rank 3: Symbol prefix match
            (Security.symbol.like(f"{escaped_upper}%", escape="\\"), 3),
            # Rank 4: Company name prefix match
            (Company.normalized_name.like(f"{escaped_norm}%", escape="\\"), 4),
            # Rank 5: Partial name or ISIN match
            else_=5,
        )

        # Deterministic ordering: rank, symbol, series, company ID
        base_query = base_query.order_by(
            rank_expr.asc(),
            Security.symbol.asc(),
            Security.series.asc(),
            Company.id.asc(),
        )

        rows = base_query.limit(limit).all()
        return [CompanySearchService._format_result(c, s) for c, s in rows]

    @staticmethod
    def _format_result(company: Company, security: Security) -> Dict[str, Any]:
        return {
            "company_id": company.id,
            "security_id": security.id,
            "company_name": company.display_name,
            "symbol": security.symbol,
            "exchange": security.exchange,
            "series": security.series,
            "isin": security.isin,
            "country": company.country,
            "currency": security.currency,
            "asset_type": security.asset_type,
            "is_active": bool(security.is_active and company.is_active),
        }
