"""
Search strategies using the Strategy Pattern for different search modes.

This module implements different search strategies (traditional, semantic, hybrid)
that can be used interchangeably by search classes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from elasticsearch.dsl import Q as DSLQ
from pyparsing import ParseException

from kitsune.search.parser import Parser
from kitsune.search.parser.tokens import TermToken


class SearchStrategy(ABC):
    """Abstract base class for search strategies."""

    @abstractmethod
    def build_query(self, query_text: str, locale: str, base_fields: list[str],
                   parse_query: bool = True, advanced_settings: dict[str, Any] | None = None) -> Any:
        """
        Build the Elasticsearch query.

        Args:
            query_text: The search query string
            locale: The locale to search in
            base_fields: Base field names without locale suffix
            parse_query: Whether to parse advanced query syntax
            advanced_settings: Additional settings for query parsing

        Returns:
            An Elasticsearch query object
        """
        pass

    @abstractmethod
    def get_fields(self, locale: str, base_fields: list[str]) -> list[str]:
        """
        Get the fields to search based on strategy.

        Args:
            locale: The locale to search in
            base_fields: Base field names without locale suffix

        Returns:
            List of field names with appropriate locale suffixes
        """
        pass

    def get_field_boosts(self, locale: str, base_fields: list[str]) -> dict[str, float]:
        """
        Get field boost values for the strategy.

        Args:
            locale: The locale to search in
            base_fields: Base field names without locale suffix

        Returns:
            Dictionary mapping field names to boost values
        """
        return {}

    def should_fallback(self, results: list[dict], total: int) -> bool:
        """
        Determine if fallback to another strategy is needed.

        Args:
            results: Search results
            total: Total number of results

        Returns:
            True if fallback is needed, False otherwise
        """
        return False


class TraditionalSearchStrategy(SearchStrategy):
    """Traditional text-based search strategy."""

    def build_query(self, query_text: str, locale: str, base_fields: list[str],
                   parse_query: bool = True, advanced_settings: dict[str, Any] | None = None) -> DSLQ:
        """Build traditional text search query."""
        if advanced_settings is None:
            advanced_settings = {}

        fields = self.get_fields(locale, base_fields)

        # Handle advanced query parsing
        if parse_query:
            try:
                parsed = Parser(query_text)
                return parsed.elastic_query({
                    "fields": fields,
                    "settings": advanced_settings
                })
            except ParseException:
                pass

        # Fallback to simple query
        parsed_token = TermToken(query_text)
        return parsed_token.elastic_query({
            "fields": fields,
            "settings": advanced_settings
        })

    def get_fields(self, locale: str, base_fields: list[str]) -> list[str]:
        """Return traditional text fields with locale suffix."""
        return [f"{field}.{locale}" for field in base_fields]

    def get_field_boosts(self, locale: str, base_fields: list[str]) -> dict[str, float]:
        """Get boost values for traditional fields."""
        boosts = {}
        for field in base_fields:
            locale_field = f"{field}.{locale}"
            # Apply standard boost values based on field type
            if "title" in field:
                boosts[locale_field] = 8.0
            elif "keywords" in field or "tag" in field:
                boosts[locale_field] = 4.0
            elif "summary" in field:
                boosts[locale_field] = 2.0
            else:
                boosts[locale_field] = 1.0
        return boosts


class SemanticSearchStrategy(SearchStrategy):
    """Semantic search strategy using E5 multilingual model."""

    def build_query(self, query_text: str, locale: str, base_fields: list[str],
                   parse_query: bool = True, advanced_settings: dict[str, Any] | None = None) -> DSLQ:
        """Build semantic search query."""
        if advanced_settings is None:
            advanced_settings = {}

        # For semantic search, we need both traditional and semantic fields
        all_fields = self.get_fields(locale, base_fields)

        # Handle advanced query parsing (though semantic search typically doesn't use it)
        if parse_query:
            try:
                parsed = Parser(query_text)
                return parsed.elastic_query({
                    "fields": all_fields,
                    "settings": advanced_settings
                })
            except ParseException:
                pass

        # Build semantic queries
        semantic_queries = []
        boosts = self.get_field_boosts(locale, base_fields)

        for field in base_fields:
            # Add semantic field queries
            semantic_field = f"{field}_semantic.{locale}"
            semantic_queries.append(
                DSLQ("semantic",
                     field=semantic_field,
                     query=query_text,
                     boost=boosts.get(semantic_field, 1.0))
            )

            # Also include traditional text queries for fallback
            text_field = f"{field}.{locale}"
            semantic_queries.append(
                DSLQ("match",
                     **{text_field: {"query": query_text, "boost": boosts.get(text_field, 1.0)}})
            )

        return DSLQ("bool", should=semantic_queries)

    def get_fields(self, locale: str, base_fields: list[str]) -> list[str]:
        """Return both semantic and traditional fields."""
        semantic_fields = [f"{field}_semantic.{locale}" for field in base_fields]
        traditional_fields = [f"{field}.{locale}" for field in base_fields]
        return semantic_fields + traditional_fields

    def get_field_boosts(self, locale: str, base_fields: list[str]) -> dict[str, float]:
        """Get boost values for semantic fields."""
        boosts = {}
        for field in base_fields:
            semantic_field = f"{field}_semantic.{locale}"
            text_field = f"{field}.{locale}"

            # Semantic fields get slightly higher boosts
            if "title" in field:
                boosts[semantic_field] = 10.0
                boosts[text_field] = 8.0
            elif "keywords" in field or "tag" in field:
                boosts[semantic_field] = 5.0
                boosts[text_field] = 4.0
            elif "summary" in field:
                boosts[semantic_field] = 3.0
                boosts[text_field] = 2.0
            else:
                boosts[semantic_field] = 1.5
                boosts[text_field] = 1.0

        return boosts

    def should_fallback(self, results: list[dict], total: int) -> bool:
        """Check if semantic scores are too low and fallback is needed."""
        if total == 0 or not results:
            return False

        # Extract max score from results
        max_score = 0
        for result in results:
            if isinstance(result, dict):
                score = result.get("score", 0)
            elif hasattr(result, "meta") and hasattr(result.meta, "score"):
                score = result.meta.score
            else:
                score = 0
            max_score = max(max_score, score)

        # Check against semantic threshold
        from kitsune.search.config import SEMANTIC_SEARCH_MIN_SCORE
        return max_score < SEMANTIC_SEARCH_MIN_SCORE


@dataclass
class RRFQuery:
    """Reciprocal Rank Fusion query for hybrid search."""
    retrievers: list[dict[str, Any]]
    rank_window_size: int = 100
    rank_constant: int = 20

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Elasticsearch."""
        return {
            "retriever": {
                "rrf": {
                    "retrievers": self.retrievers,
                    "rank_window_size": self.rank_window_size,
                    "rank_constant": self.rank_constant
                }
            }
        }


class HybridSearchStrategy(SearchStrategy):
    """Hybrid search strategy using RRF to combine traditional and semantic search."""

    def __init__(self, rank_window_size: int = 100, rank_constant: int = 20):
        """
        Initialize hybrid search strategy.

        Args:
            rank_window_size: RRF rank window size parameter
            rank_constant: RRF rank constant parameter
        """
        self.traditional = TraditionalSearchStrategy()
        self.semantic = SemanticSearchStrategy()
        self.rank_window_size = rank_window_size
        self.rank_constant = rank_constant

    def build_query(self, query_text: str, locale: str, base_fields: list[str],
                   parse_query: bool = True, advanced_settings: dict[str, Any] | None = None) -> RRFQuery | DSLQ:
        """Build RRF query combining traditional and semantic search."""
        if advanced_settings is None:
            advanced_settings = {}

        # Check if query has advanced syntax that requires traditional search
        if parse_query and self._has_advanced_syntax(query_text):
            # Fall back to traditional search for advanced queries
            return self.traditional.build_query(
                query_text, locale, base_fields, parse_query, advanced_settings
            )

        # Build text retriever
        text_query = self.traditional.build_query(
            query_text, locale, base_fields, False, advanced_settings  # Don't parse for RRF
        )

        # Build semantic retriever
        semantic_queries = []
        semantic_boosts = self.semantic.get_field_boosts(locale, base_fields)

        for field in base_fields:
            semantic_field = f"{field}_semantic.{locale}"
            semantic_queries.append(
                DSLQ("semantic",
                     field=semantic_field,
                     query=query_text,
                     boost=semantic_boosts.get(semantic_field, 1.0))
            )

        semantic_query = DSLQ("bool", should=semantic_queries)

        # Create RRF query
        return RRFQuery(
            retrievers=[
                {"standard": {"query": text_query}},
                {"standard": {"query": semantic_query}}
            ],
            rank_window_size=self.rank_window_size,
            rank_constant=self.rank_constant
        )

    def get_fields(self, locale: str, base_fields: list[str]) -> list[str]:
        """Return combined traditional and semantic fields."""
        traditional = self.traditional.get_fields(locale, base_fields)
        semantic_only = [f"{field}_semantic.{locale}" for field in base_fields]
        return list(set(traditional + semantic_only))

    def get_field_boosts(self, locale: str, base_fields: list[str]) -> dict[str, float]:
        """Get combined boost values."""
        # Combine boosts from both strategies
        traditional_boosts = self.traditional.get_field_boosts(locale, base_fields)
        semantic_boosts = self.semantic.get_field_boosts(locale, base_fields)

        # Merge the dictionaries
        all_boosts = traditional_boosts.copy()
        all_boosts.update(semantic_boosts)
        return all_boosts

    def should_fallback(self, results: list[dict], total: int) -> bool:
        """Check if hybrid search should fall back to traditional."""
        # Use the same logic as semantic search for consistency
        return self.semantic.should_fallback(results, total)

    def _has_advanced_syntax(self, query_text: str) -> bool:
        """Check if query contains advanced syntax that requires traditional search."""
        advanced_indicators = [
            'field:', 'exact:', 'range:',
            ' AND ', ' OR ', ' NOT ',
            '"'  # Quoted phrases might need special handling
        ]
        return any(indicator in query_text for indicator in advanced_indicators)


class MultiLocaleSearchStrategy(SearchStrategy):
    """Strategy wrapper for multi-locale searches."""

    def __init__(self, base_strategy: SearchStrategy, locales: list[str],
                 primary_locale: str):
        """
        Initialize multi-locale strategy.

        Args:
            base_strategy: The underlying search strategy to use
            locales: List of locales to search in
            primary_locale: The primary locale for boosting
        """
        self.base_strategy = base_strategy
        self.locales = locales if locales else [primary_locale]
        self.primary_locale = primary_locale

    def build_query(self, query_text: str, locale: str, base_fields: list[str],
                   parse_query: bool = True, advanced_settings: dict[str, Any] | None = None) -> Any:
        """Build query across multiple locales."""
        # For multi-locale, we build queries for each locale and combine
        queries = []

        for search_locale in self.locales:
            locale_query = self.base_strategy.build_query(
                query_text, search_locale, base_fields, parse_query, advanced_settings
            )

            # Apply boost to primary locale
            if search_locale == self.primary_locale and hasattr(locale_query, 'boost'):
                locale_query = locale_query.params(boost=1.5)

            queries.append(locale_query)

        # Combine queries with should clause
        if len(queries) == 1:
            return queries[0]

        return DSLQ("bool", should=queries)

    def get_fields(self, locale: str, base_fields: list[str]) -> list[str]:
        """Get fields for all locales."""
        all_fields = []
        for search_locale in self.locales:
            locale_fields = self.base_strategy.get_fields(search_locale, base_fields)
            all_fields.extend(locale_fields)
        return list(set(all_fields))

    def get_field_boosts(self, locale: str, base_fields: list[str]) -> dict[str, float]:
        """Get field boosts for all locales."""
        all_boosts = {}
        for search_locale in self.locales:
            locale_boosts = self.base_strategy.get_field_boosts(search_locale, base_fields)

            # Apply additional boost to primary locale
            if search_locale == self.primary_locale:
                locale_boosts = {k: v * 1.5 for k, v in locale_boosts.items()}

            all_boosts.update(locale_boosts)

        return all_boosts

    def should_fallback(self, results: list[dict], total: int) -> bool:
        """Delegate fallback check to base strategy."""
        return self.base_strategy.should_fallback(results, total)
