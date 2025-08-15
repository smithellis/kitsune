"""
Simplified search module with hybrid search as default.

This module provides a clean, DRY search architecture that supports hybrid (semantic + traditional)
search with automatic fallback for advanced syntax.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Self

import bleach
from dateutil import parser
from django.conf import settings
from django.utils.text import slugify
from elasticsearch import RequestError
from elasticsearch.dsl import Q as DSLQ
from elasticsearch.dsl.query import Query
from elasticsearch.dsl.utils import AttrDict
from pyparsing import ParseException

from kitsune.products.models import Product
from kitsune.search import HIGHLIGHT_TAG, SNIPPET_LENGTH
from kitsune.search.base import SumoSearch
from kitsune.search.documents import (
    ForumDocument,
    ProfileDocument,
    QuestionDocument,
    WikiDocument,
)
from kitsune.search.es_utils import es_client
from kitsune.search.parser import Parser
from kitsune.search.parser.operators import (
    AndOperator,
    FieldOperator,
    NotOperator,
    OrOperator,
    SpaceOperator,
)
from kitsune.search.parser.tokens import ExactToken, RangeToken, TermToken
from kitsune.sumo.urlresolvers import reverse
from kitsune.wiki.config import CATEGORIES
from kitsune.wiki.parser import wiki_to_html

log = logging.getLogger("k.search")

QUESTION_DAYS_DELTA = 365 * 2
FVH_HIGHLIGHT_OPTIONS = {
    "type": "fvh",
    "order": "score",
    "number_of_fragments": 1,
    "boundary_scanner": "sentence",
    "fragment_size": SNIPPET_LENGTH,
    "pre_tags": [f"<{HIGHLIGHT_TAG}>"],
    "post_tags": [f"</{HIGHLIGHT_TAG}>"],
}
CATEGORY_EXACT_MAPPING = {
    "dict": {
        slugify(str(name)): _id
        for _id, name in CATEGORIES
    },
    "field": "category",
}


def first_highlight(hit):
    """Get the first highlight from a search hit."""
    highlight = getattr(hit.meta, "highlight", None)
    if highlight:
        return next(iter(highlight.to_dict().values()))[0]
    return None


def strip_html(summary):
    """Strip HTML from summary except highlight tags."""
    return bleach.clean(
        summary,
        tags=[HIGHLIGHT_TAG],
        strip=True,
    )


def same_base_index(a, b):
    """Check if the base parts of two index names are the same."""
    return a.split("_")[:-1] == b.split("_")[:-1]


class RRFQuery(Query):
    """Custom Query wrapper for RRF (Reciprocal Rank Fusion) queries."""
    name = 'rrf'

    def __init__(self, query_dict, **kwargs):
        self._query_dict = query_dict
        super().__init__(**kwargs)

    def to_dict(self):
        return self._query_dict


@dataclass
class SearchContext:
    """Encapsulates all search parameters and context for strategies."""
    query: str = ""
    locales: list[str] = field(default_factory=lambda: ["en-US"])
    document_types: list[str] = field(default_factory=lambda: ["wiki", "questions"])
    primary_locale: str = "en-US"
    product: "Product | None" = None
    parse_query: bool = True

    # Cached values from UnifiedSearch - accessed directly
    fields: list[str] = field(default_factory=list, init=False)
    semantic_fields: list[str] = field(default_factory=list, init=False)
    settings: dict = field(default_factory=dict, init=False)


class SearchStrategy(ABC):
    """Abstract base class for search strategies."""

    def __init__(self, context: SearchContext):
        self.context = context

    @abstractmethod
    def build_query(self):
        """Build the appropriate query for this search strategy."""
        pass

    @abstractmethod
    def supports_advanced_syntax(self) -> bool:
        """Whether this strategy supports advanced query syntax."""
        pass

    def get_fallback_strategy(self) -> "SearchStrategy":
        """Get fallback strategy if this one fails. Default to Traditional."""
        # Import here to avoid circular imports
        return TraditionalSearchStrategy(self.context)


class TraditionalSearchStrategy(SearchStrategy):
    """Traditional BM25 text search strategy."""

    def build_query(self):
        """Build traditional text search query."""
        if not self.context.query:
            return DSLQ("match_all")

        # Handle advanced query parsing
        if self.context.parse_query:
            try:
                parsed = Parser(self.context.query)
                return parsed.elastic_query({
                    "fields": self.context.fields,
                    "settings": self.context.settings
                })
            except ParseException:
                pass

        # For simple queries, use stricter matching
        terms = self.context.query.split()

        # Check for gibberish
        term_token = TermToken(self.context.query)
        if len(terms) == 1 and term_token._is_likely_gibberish(terms[0].lower()):
            return DSLQ("bool", must_not=DSLQ("match_all"))

        # Use multi_match for better relevance with stricter settings
        query_params = {
            "query": self.context.query,
            "fields": self.context.fields,
            "type": "best_fields",  # Prefer documents where all terms appear in same field
            "operator": "AND" if len(terms) <= 3 else "OR",  # Stricter for short queries
        }

        # Stricter minimum_should_match for OR queries
        if query_params["operator"] == "OR" and len(terms) > 1:
            if len(terms) == 2:
                query_params["minimum_should_match"] = "100%"  # Both terms must match
            elif len(terms) == 3:
                query_params["minimum_should_match"] = "75%"   # At least 2 of 3
            else:
                query_params["minimum_should_match"] = "65%"   # Stricter than before

        return DSLQ("multi_match", **query_params)

    def supports_advanced_syntax(self) -> bool:
        """Traditional search supports advanced syntax."""
        return True

    def get_fallback_strategy(self) -> "SearchStrategy":
        """Traditional is the fallback, so return self."""
        return self




class HybridRRFSearchStrategy(SearchStrategy):
    """Hybrid search strategy using Reciprocal Rank Fusion."""

    def build_query(self):
        """Build RRF hybrid query combining semantic and traditional search."""
        if not self.context.query:
            return DSLQ("match_all")

        # Build traditional and semantic sub-queries
        traditional_strategy = TraditionalSearchStrategy(self.context)
        traditional_query = traditional_strategy.build_query()
        semantic_query = self._build_semantic_query()

        # Create RRF query
        rrf_query = {
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": traditional_query.to_dict()}},
                        {"standard": {"query": semantic_query.to_dict()}}
                    ],
                    "rank_window_size": settings.SEARCH_RRF_WINDOW_SIZE if settings.SEARCH_STRICT_RELEVANCE else settings.RRF_WINDOW_MAX_SIZE,
                    "rank_constant": settings.SEARCH_RRF_RANK_CONSTANT if settings.SEARCH_STRICT_RELEVANCE else settings.RRF_RANK_CONSTANT
                }
            }
        }

        return RRFQuery(rrf_query)

    def _build_semantic_query(self):
        """Build semantic search query using semantic fields."""
        if not self.context.query:
            return DSLQ("match_all")

        # Check for gibberish before building semantic queries
        term_token = TermToken(self.context.query)
        if term_token._is_likely_gibberish(self.context.query.lower()):
            # Return a query that matches nothing for gibberish
            return DSLQ("bool", must_not=DSLQ("match_all"))

        semantic_queries = []
        semantic_fields = self.context.semantic_fields

        # Build semantic queries with proper locale handling and boosts
        for locale in self.context.locales:
            for field_name in semantic_fields:
                semantic_field = f"{field_name}_semantic.{locale}"
                boost = self._get_semantic_field_boost(field_name, locale)
                semantic_queries.append(
                    DSLQ("semantic", field=semantic_field, query=self.context.query, boost=boost)
                )

        if not semantic_queries:
            # Fallback to traditional if no semantic fields available
            return TraditionalSearchStrategy(self.context).build_query()

        # Require matches in multiple fields for better relevance
        # For short queries, require more matches
        terms = self.context.query.split()
        if len(terms) <= 2:
            min_should_match = max(2, len(semantic_queries) // 4)  # At least 25% of fields
        else:
            min_should_match = max(1, len(semantic_queries) // 6)  # At least 16% of fields

        return DSLQ("bool", should=semantic_queries, minimum_should_match=min_should_match)

    def _get_semantic_field_boost(self, field: str, locale: str) -> float:
        """Get boost value for semantic fields."""
        locale_boost = 1.5 if locale == self.context.primary_locale else 1.0

        if "title" in field:
            return 6.0 * locale_boost
        elif "summary" in field:
            return 4.0 * locale_boost
        else:
            return 2.0 * locale_boost

    def supports_advanced_syntax(self) -> bool:
        """Hybrid search supports advanced syntax through traditional component."""
        return True


class SearchStrategyFactory:
    """Factory for creating appropriate search strategies."""

    @staticmethod
    def create_strategy(search_mode: str, context: SearchContext, search_instance=None) -> SearchStrategy:
        """Create appropriate search strategy based on mode and query content.

        Only supports hybrid (default) and traditional modes.
        """
        # Check for advanced syntax that requires traditional search
        is_simple = True
        if search_instance is not None and hasattr(search_instance, 'is_simple_search'):
            # Use proper parser-based detection when available
            is_simple = search_instance.is_simple_search()
            log.debug(f"Using search_instance.is_simple_search() for '{context.query}': {is_simple}")
        else:
            # Fallback to string-based detection if search instance not available
            is_simple = not SearchStrategyFactory._has_advanced_syntax(context.query)
            log.debug(f"Using fallback _has_advanced_syntax() for '{context.query}': {is_simple}")

        if not is_simple:
            log.debug(f"Using traditional search for advanced query: {context.query}")
            return TraditionalSearchStrategy(context)

        # Use the specified search mode - only hybrid or traditional
        if search_mode == "traditional":
            return TraditionalSearchStrategy(context)
        else:  # hybrid (default) - includes any invalid mode
            return HybridRRFSearchStrategy(context)

    @staticmethod
    def _has_advanced_syntax(query_text: str | None = None) -> bool:
        """Fallback string-based check for advanced syntax (when proper parsing unavailable)."""
        if not query_text:
            return False

        # Check for field operators (specific fields and generic patterns)
        field_indicators = [
            'field:', 'exact:', 'range:', 'title:', 'content:', 'keywords:',
            'summary:', 'question:', 'answer:'
        ]

        # Check for boolean operators (including NOT at start)
        boolean_indicators = [
            ' AND ', ' OR ', ' NOT '
        ]

        # Check for NOT at the beginning of query
        if query_text.startswith('NOT '):
            return True

        # Also check for quoted phrases
        if '"' in query_text and query_text.count('"') >= 2:
            return True

        # Check all indicators
        return (any(indicator in query_text for indicator in field_indicators) or
                any(indicator in query_text for indicator in boolean_indicators))


@dataclass
class UnifiedSearch(SumoSearch):
    """
    Unified search class that handles all document types and search modes.
    Supports wiki, questions, profiles, and forum documents with hybrid search by default.
    """

    # Core search parameters
    query: str = ""
    search_mode: str = "hybrid"  # "hybrid" or "traditional"
    document_types: list[str] = field(default_factory=lambda: ["wiki", "questions"])
    locales: list[str] = field(default_factory=lambda: ["en-US"])
    primary_locale: str = "en-US"
    product: Product | None = None

    # Legacy compatibility
    locale: str = field(default="", init=False)

    # Cached computations
    _field_boosts: dict = field(default_factory=dict, init=False)
    _fields_cache: list = field(default_factory=list, init=False)
    _semantic_fields_cache: list = field(default_factory=list, init=False)
    _index_cache: str = field(default="", init=False)
    _settings_cache: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        """Initialize search with proper defaults."""
        if self.locale and self.locale not in self.locales:
            self.locales = [self.locale]
            self.primary_locale = self.locale
        elif not self.primary_locale and self.locales:
            self.primary_locale = self.locales[0]

        self.document_types = [dt.lower().rstrip('s') for dt in self.document_types]

        self._precompute_field_boosts()
        self._precompute_fields()
        self._precompute_index()
        self._precompute_settings()

    def get_index(self):
        """Get pre-computed index string for document types."""
        return self._index_cache

    def get_fields(self):
        """Get pre-computed search fields for all configured document types and locales."""
        return self._fields_cache

    def get_highlight_fields_options(self):
        """Get highlight fields for all configured document types and locales."""
        fields = []

        for locale in self.locales:
            if "wiki" in self.document_types:
                fields.extend([
                    (f"summary.{locale}", FVH_HIGHLIGHT_OPTIONS),
                    (f"content.{locale}", FVH_HIGHLIGHT_OPTIONS),
                ])

            if "question" in self.document_types:
                fields.extend([
                    (f"question_content.{locale}", FVH_HIGHLIGHT_OPTIONS),
                    (f"answer_content.{locale}", FVH_HIGHLIGHT_OPTIONS),
                ])

        return fields

    def get_settings(self):
        """Get pre-computed search settings based on document types."""
        return self._settings_cache

    def _create_search_context(self) -> SearchContext:
        """Create SearchContext with cached values for strategies."""
        context = SearchContext(
            query=self.query,
            locales=self.locales,
            document_types=self.document_types,
            primary_locale=self.primary_locale,
            product=self.product,
            parse_query=getattr(self, 'parse_query', True)
        )

        # Copy cached values to context
        context.fields = self._fields_cache
        context.semantic_fields = self._semantic_fields_cache
        context.settings = self._settings_cache

        return context

    def is_simple_search(self, token=None):
        """Determine if the search query is simple (uses ES simple_query_string) or advanced (needs Python parser).

        Simple searches are handled by Elasticsearch's simple_query_string parser and include:
        - Basic terms and phrases
        - Field operators like title:value, content:value (ES handles these)
        - Quoted phrases like \"exact phrase\"
        - Basic boolean operators (ES handles these)

        Advanced searches require our Python parser and include:
        - Complex field operators like field:title:value
        - Exact matching like exact:category:value
        - Range queries like range:date:gte:2021-01-01
        - Complex nesting that ES simple_query_string can't handle
        """
        if token is None:
            if not self.query or not self.query.strip():
                return True

            try:
                parsed = Parser(self.query)
                return self.is_simple_search(parsed.parsed)
            except ParseException:
                # If parsing fails, it's definitely a simple search
                return True

        # These require our Python parser (advanced)
        if isinstance(token, FieldOperator | RangeToken | ExactToken):
            return False

        # These can be handled by ES simple_query_string (simple)
        if isinstance(token, TermToken):
            return True

        # Boolean operators: check if they're simple enough for ES
        if isinstance(token, AndOperator | OrOperator | NotOperator):
            # These are simple if all their arguments are simple
            if hasattr(token, 'arguments'):
                return all(self.is_simple_search(arg) for arg in token.arguments)
            elif hasattr(token, 'argument'):
                return self.is_simple_search(token.argument)

        # SpaceOperator is simple if all its arguments are simple
        if isinstance(token, SpaceOperator):
            return all(self.is_simple_search(arg) for arg in token.arguments)

        # Any other token types are advanced by default
        return False

    def build_query(self) -> Query:
        """Build the appropriate query using Strategy Pattern."""
        if not self.query:
            return DSLQ("match_all")

        # Create context and get appropriate strategy
        context = self._create_search_context()
        strategy = SearchStrategyFactory.create_strategy(self.search_mode, context, self)

        return strategy.build_query()

    def _precompute_field_boosts(self):
        """Pre-compute all field boosts to avoid repeated calculations."""
        field_base_boosts = {
            "title": 6.0,
            "keywords": 8.0,
            "summary": 4.0,
            "content": 2.0,
            "question_title": 2.0,
            "question_content": 1.0,
            "answer_content": 1.0
        }

        for locale in self.locales:
            locale_multiplier = 1.5 if locale == self.primary_locale else 1.0
            for field_name, base_boost in field_base_boosts.items():
                key = f"{field_name}:{locale}"
                self._field_boosts[key] = base_boost * locale_multiplier

    def _precompute_fields(self):
        """Pre-compute field lists to avoid repeated calculations."""
        fields = []
        for locale in self.locales:
            if "wiki" in self.document_types:
                fields.extend([
                    f"keywords.{locale}^{self._get_field_boost('keywords', locale)}",
                    f"title.{locale}^{self._get_field_boost('title', locale)}",
                    f"summary.{locale}^{self._get_field_boost('summary', locale)}",
                    f"content.{locale}^{self._get_field_boost('content', locale)}",
                ])

            if "question" in self.document_types:
                fields.extend([
                    f"question_title.{locale}^{self._get_field_boost('question_title', locale)}",
                    f"question_content.{locale}^{self._get_field_boost('question_content', locale)}",
                    f"answer_content.{locale}^{self._get_field_boost('answer_content', locale)}",
                ])

        if "profile" in self.document_types:
            fields.extend(["username", "name"])

        if "forum" in self.document_types:
            fields.extend(["thread_title", "content"])

        self._fields_cache = fields

        semantic_fields = []
        if "wiki" in self.document_types:
            semantic_fields.extend(["title", "content", "summary"])

        if "question" in self.document_types:
            semantic_fields.extend(["question_title", "question_content", "answer_content"])

        self._semantic_fields_cache = semantic_fields

    def _precompute_index(self):
        """Pre-compute index string to avoid repeated calculations."""
        indices = []
        if "wiki" in self.document_types:
            indices.append(WikiDocument.Index.read_alias)
        if "question" in self.document_types:
            indices.append(QuestionDocument.Index.read_alias)
        if "profile" in self.document_types:
            indices.append(ProfileDocument.Index.read_alias)
        if "forum" in self.document_types:
            indices.append(ForumDocument.Index.read_alias)

        self._index_cache = ",".join(indices) if len(indices) > 1 else indices[0]

    def _precompute_settings(self):
        """Pre-compute settings dict to avoid repeated calculations."""
        settings_dict = {"field_mappings": {}, "range_allowed": []}

        if "wiki" in self.document_types:
            settings_dict["field_mappings"].update({
                "title": [f"title.{locale}" for locale in self.locales],
                "content": [f"content.{locale}" for locale in self.locales],
            })
            settings_dict["exact_mappings"] = {"category": CATEGORY_EXACT_MAPPING}
            settings_dict["range_allowed"].extend(["updated"])

        if "question" in self.document_types:
            settings_dict["field_mappings"].update({
                "question": [f"question_content.{locale}" for locale in self.locales],
                "answer": [f"answer_content.{locale}" for locale in self.locales],
            })
            settings_dict["range_allowed"].extend([
                "question_created", "question_updated", "question_taken_until", "question_num_votes"
            ])

        if "forum" in self.document_types:
            settings_dict["field_mappings"]["title"] = "thread_title"
            settings_dict["range_allowed"].extend(["thread_created", "created", "updated"])

        self._settings_cache = settings_dict

    def _get_field_boost(self, field: str, locale: str) -> float:
        """Get pre-computed boost value for fields."""
        key = f"{field}:{locale}"
        return self._field_boosts.get(key, 1.0)  # Default boost if not found

    def get_filter(self):
        """Get complete filter query including the search query."""
        filters = self._build_filters()
        return DSLQ("bool", filter=filters, must=self.build_query())

    def _build_filters(self):
        """Build filters for all configured document types."""
        doc_type_filters = []

        # Build locale exists queries once and reuse
        locale_exists_queries = {}
        if self.locales:
            locale_exists_queries["wiki"] = DSLQ("bool", should=[
                DSLQ("exists", field=f"title.{locale}") for locale in self.locales
            ], minimum_should_match=1)
            locale_exists_queries["question"] = DSLQ("bool", should=[
                DSLQ("exists", field=f"question_title.{locale}") for locale in self.locales
            ], minimum_should_match=1)

        if "wiki" in self.document_types:
            wiki_filters = [DSLQ("term", _index=WikiDocument.Index.read_alias)]
            if "wiki" in locale_exists_queries:
                wiki_filters.append(locale_exists_queries["wiki"])
            if self.product:
                wiki_filters.append(DSLQ("term", product_ids=self.product.id))
            doc_type_filters.append(DSLQ("bool", filter=wiki_filters))

        if "question" in self.document_types:
            question_filters = [
                DSLQ("term", _index=QuestionDocument.Index.read_alias),
                DSLQ("range", question_created={
                    "gte": datetime.now(UTC) - timedelta(days=QUESTION_DAYS_DELTA)
                }),
                DSLQ("bool", must_not=DSLQ("exists", field="updated")),
            ]
            if "question" in locale_exists_queries:
                question_filters.append(locale_exists_queries["question"])
            if self.product:
                question_filters.append(DSLQ("term", question_product_id=self.product.id))
            doc_type_filters.append(DSLQ("bool", filter=question_filters))

        if "profile" in self.document_types:
            doc_type_filters.append(DSLQ("term", _index=ProfileDocument.Index.read_alias))

        if "forum" in self.document_types:
            doc_type_filters.append(DSLQ("term", _index=ForumDocument.Index.read_alias))

        return [DSLQ("bool", should=doc_type_filters, minimum_should_match=1)] if len(doc_type_filters) > 1 else doc_type_filters

    def run(self, key=None) -> Self:
        """Execute search with hybrid search handling."""
        if key is None:
            # Use stricter page size if strict relevance is enabled
            page_size = 10 if settings.SEARCH_STRICT_RELEVANCE else settings.SEARCH_RESULTS_PER_PAGE
            key = slice(0, page_size)

        query = self.build_query()

        if isinstance(query, RRFQuery):
            return self._run_rrf_search(query, key)

        return super().run(key)  # type: ignore

    def _run_rrf_search(self, query: RRFQuery, key) -> Self:
        """Execute RRF search using native Elasticsearch client."""
        client = es_client()
        rrf_dict = query.to_dict()
        filters = self._build_filters()

        # Dynamically adjust RRF window size based on requested page
        # The window must be large enough to include all requested results
        if isinstance(key, slice):
            requested_end = key.stop or settings.SEARCH_RESULTS_PER_PAGE
        else:
            requested_end = key + 1

        # Set window size to accommodate requested results, capped at configured limit
        max_window = settings.SEARCH_RRF_WINDOW_SIZE if settings.SEARCH_STRICT_RELEVANCE else settings.RRF_WINDOW_MAX_SIZE

        # For strict relevance, we always need the full window to filter properly
        if settings.SEARCH_STRICT_RELEVANCE and settings.SEARCH_MIN_SCORE_THRESHOLD > 0:
            needed_window_size = max_window
        else:
            needed_window_size = min(requested_end, max_window)

        rrf_dict["retriever"]["rrf"]["rank_window_size"] = needed_window_size

        if filters:
            filter_dicts = []
            for f in filters:
                if hasattr(f, 'to_dict'):
                    filter_dicts.append(f.to_dict())
                else:
                    filter_dicts.append(f)

            for retriever in rrf_dict["retriever"]["rrf"]["retrievers"]:
                if "standard" in retriever and "query" in retriever["standard"]:
                    original_query = retriever["standard"]["query"]
                    if hasattr(original_query, 'to_dict'):
                        original_query = original_query.to_dict()

                    retriever["standard"]["query"] = {
                        "bool": {
                            "filter": filter_dicts,
                            "must": original_query
                        }
                    }

        body = rrf_dict.copy()

        highlight_fields = {}
        for field_name, options in self.get_highlight_fields_options():
            highlight_fields[field_name] = options
        if highlight_fields:
            body["highlight"] = {"fields": highlight_fields}

        if isinstance(key, slice):
            body["from"] = key.start or 0
            body["size"] = key.stop - (key.start or 0)
        else:
            body["from"] = key
            body["size"] = 1

        try:
            result = client.search(index=self.get_index(), body=body, **settings.ES_SEARCH_PARAMS)
        except RequestError as e:
            if hasattr(self, 'parse_query') and self.parse_query:  # type: ignore
                self.parse_query = False
                return self.run(key)
            raise e

        self.hits = result["hits"]["hits"]
        total = result["hits"]["total"]
        raw_total = total["value"] if isinstance(total, dict) else total

        # Cap total at the configured window size
        max_window = settings.SEARCH_RRF_WINDOW_SIZE if settings.SEARCH_STRICT_RELEVANCE else settings.RRF_WINDOW_MAX_SIZE

        # Track if results were capped for display purposes
        self.results_capped = raw_total > max_window

        # If strict relevance is enabled, we need to properly handle score filtering
        if settings.SEARCH_STRICT_RELEVANCE and settings.SEARCH_MIN_SCORE_THRESHOLD > 0:
            # For RRF, we need to get ALL results up to window size to count properly
            # Then filter and paginate from the filtered set

            # First, get all results up to window size if we haven't already
            if isinstance(key, slice) and (key.stop - (key.start or 0)) < max_window:
                # We're paginating - need to get all results first to filter properly
                full_body = body.copy()
                full_body["from"] = 0
                full_body["size"] = max_window

                # Get all results up to window size
                full_result = client.search(index=self.get_index(), body=full_body, **settings.ES_SEARCH_PARAMS)
                all_hits = full_result["hits"]["hits"]

                # Filter all hits by score threshold
                filtered_all_hits = [hit for hit in all_hits if hit.get('_score', 0) >= settings.SEARCH_MIN_SCORE_THRESHOLD]

                # Update total to reflect actual filtered count
                self.total = len(filtered_all_hits)

                # Now slice the filtered results for the requested page
                if isinstance(key, slice):
                    start = key.start or 0
                    stop = key.stop or settings.SEARCH_RESULTS_PER_PAGE
                    self.hits = filtered_all_hits[start:stop]
                else:
                    self.hits = filtered_all_hits[key:key+1] if key < len(filtered_all_hits) else []
            else:
                # Not paginating or already have full window - just filter current hits
                filtered_hits = [hit for hit in self.hits if hit.get('_score', 0) >= settings.SEARCH_MIN_SCORE_THRESHOLD]
                self.hits = filtered_hits
                self.total = min(raw_total, max_window)
        else:
            # No strict relevance - use standard approach
            self.total = min(raw_total, max_window)

        self.results = [self.make_result(self._convert_hit_to_attrdict(hit)) for hit in self.hits]
        self.last_key = key

        return self

    def _convert_hit_to_attrdict(self, hit):
        """Convert ES hit dict to AttrDict-like object for compatibility."""
        attr_hit = AttrDict(hit.get("_source", {}))
        attr_hit.meta = AttrDict({
            "id": hit["_id"],
            "index": hit["_index"],
            "score": hit["_score"],
            "highlight": AttrDict(hit["highlight"]) if "highlight" in hit else None
        })
        return attr_hit

    def make_result(self, hit):
        """Route result creation to appropriate handler based on document type."""
        index = hit.meta.index

        if same_base_index(index, WikiDocument.Index.read_alias):
            return self._make_wiki_result(hit)
        elif same_base_index(index, QuestionDocument.Index.read_alias):
            return self._make_question_result(hit)
        elif same_base_index(index, ProfileDocument.Index.read_alias):
            return self._make_profile_result(hit)
        elif same_base_index(index, ForumDocument.Index.read_alias):
            return self._make_forum_result(hit)
        else:
            return {"type": "unknown", "title": "Unknown result"}

    def _get_localized_field(self, hit, field_name, locale):
        """Extract localized field value from hit."""
        field = getattr(hit, field_name, None)
        if field and hasattr(field, locale):
            return getattr(field, locale, "")
        return ""

    def _get_summary(self, hit, content_field, detected_locale):
        """Get summary from highlight or content, stripped of HTML."""
        summary = first_highlight(hit)
        if not summary and hasattr(hit, content_field):
            content = self._get_localized_field(hit, content_field, detected_locale)
            if content:
                summary = content[:SNIPPET_LENGTH]
        return strip_html(summary) if summary else ""

    def _make_wiki_result(self, hit):
        """Create result for wiki document."""
        detected_locale = self._detect_locale(hit, "title")

        # Try summary field first, then content
        summary = first_highlight(hit)
        if not summary:
            summary = self._get_localized_field(hit, "summary", detected_locale)
        if not summary:
            summary = self._get_summary(hit, "content", detected_locale)

        title = self._get_localized_field(hit, "title", detected_locale)
        slug = self._get_localized_field(hit, "slug", detected_locale)

        return {
            "type": "document",
            "url": reverse("wiki.document", args=[slug], locale=detected_locale),
            "score": hit.meta.score,
            "title": title,
            "search_summary": summary,
            "id": hit.meta.id,
            "result_locale": detected_locale,
            "is_fallback_locale": detected_locale != self.primary_locale,
        }

    def _make_question_result(self, hit):
        """Create result for question document."""
        detected_locale = self._detect_locale(hit, "question_title")
        summary = self._get_summary(hit, "question_content", detected_locale)

        # Count answers if available
        answer_content = getattr(hit, "answer_content", None)
        num_answers = 0
        if answer_content and hasattr(answer_content, detected_locale):
            locale_answers = getattr(answer_content, detected_locale, [])
            num_answers = len(locale_answers) if locale_answers else 0

        return {
            "type": "question",
            "url": reverse("questions.details", kwargs={"question_id": hit.question_id}),
            "score": hit.meta.score,
            "title": self._get_localized_field(hit, "question_title", detected_locale),
            "search_summary": summary,
            "last_updated": datetime.fromisoformat(hit.question_updated),
            "is_solved": hit.question_has_solution,
            "num_answers": num_answers,
            "num_votes": hit.question_num_votes,
            "result_locale": detected_locale,
            "is_fallback_locale": detected_locale != self.primary_locale,
        }

    def _make_profile_result(self, hit):
        """Create result for profile document."""
        return {
            "type": "user",
            "avatar": getattr(hit, "avatar", None),
            "username": hit.username,
            "name": getattr(hit, "name", ""),
            "user_id": hit.meta.id,
        }

    def _make_forum_result(self, hit):
        """Create result for forum document."""
        return {
            "type": "thread",
            "title": hit.thread_title,
            "search_summary": strip_html(wiki_to_html(hit.content))[:1000],
            "last_updated": parser.parse(hit.updated),
            "url": reverse(
                "forums.posts",
                kwargs={"forum_slug": hit.forum_slug, "thread_id": hit.thread_id},
            )
            + f"#post-{hit.meta.id}",
        }

    def _detect_locale(self, hit, title_field):
        """Detect which locale this result is in."""
        title_attr = getattr(hit, title_field, None)
        if title_attr:
            for locale in self.locales:
                if hasattr(title_attr, locale) and getattr(title_attr, locale):
                    return locale
        return self.locales[0]


# Factory functions for creating searches
def create_search(query="", document_types=None, search_mode="hybrid", locales=None,
                 primary_locale="en-US", product=None, **kwargs):
    """
    Factory function to create search instances.

    Args:
        query: Search query string
        document_types: List of document types to search ["wiki", "questions", "profiles", "forums"]
        search_mode: "hybrid" or "traditional"
        locales: List of locales to search
        primary_locale: Primary locale for boosting
        product: Product to filter by
        **kwargs: Additional parameters (for backward compatibility)
    """
    # Handle legacy locale parameter
    if 'locale' in kwargs:
        locales = locales or [kwargs['locale']]
        primary_locale = kwargs['locale']

    # Set defaults
    if document_types is None:
        document_types = ["wiki", "questions"]
    if locales is None:
        locales = [primary_locale]

    return UnifiedSearch(
        query=query,
        search_mode=search_mode,
        document_types=document_types,
        locales=locales,
        primary_locale=primary_locale,
        product=product,
    )


def _create_single_type_search(doc_type, query="", search_mode="hybrid", locales=None,
                               primary_locale="en-US", locale="", product=None, **kwargs):
    """Helper for creating single document type searches."""
    if locale and not locales:
        locales = [locale]
        primary_locale = locale
    return create_search(
        query=query,
        document_types=[doc_type],
        search_mode=search_mode,
        locales=locales or [primary_locale],
        primary_locale=primary_locale,
        product=product,
        **kwargs
    )


# Backward compatibility functions
def WikiSearch(query="", search_mode="hybrid", locales=None, primary_locale="en-US",
               locale="", product=None, **kwargs):
    """Backward compatibility: Wiki search."""
    return _create_single_type_search("wiki", query, search_mode, locales,
                                     primary_locale, locale, product, **kwargs)


def QuestionSearch(query="", search_mode="hybrid", locales=None, primary_locale="en-US",
                   locale="", product=None, **kwargs):
    """Backward compatibility: Question search."""
    return _create_single_type_search("questions", query, search_mode, locales,
                                     primary_locale, locale, product, **kwargs)


def ProfileSearch(query="", group_ids=None, **kwargs):
    """Backward compatibility: Profile search."""
    search = create_search(query=query, document_types=["profiles"], search_mode="traditional")
    if group_ids:
        search.group_ids = group_ids
    return search


def ForumSearch(query="", thread_forum_id=None, **kwargs):
    """Backward compatibility: Forum search."""
    search = create_search(query=query, document_types=["forums"], search_mode="traditional")
    if thread_forum_id:
        search.thread_forum_id = thread_forum_id
    return search


def CompoundSearch(query="", search_mode="hybrid", locales=None, primary_locale="en-US",
                   locale="", product=None, **kwargs):
    """Backward compatibility: Compound search."""
    if locale and not locales:
        locales = [locale]
        primary_locale = locale
    return create_search(
        query=query,
        document_types=["wiki", "questions"],
        search_mode=search_mode,
        locales=locales or [primary_locale],
        primary_locale=primary_locale,
        product=product,
        **kwargs
    )


HybridSearch = CompoundSearch
