"""
Refactored search module using Strategy Pattern.

This module maintains the same public API as the original search.py
but uses the Strategy Pattern internally for cleaner, more maintainable code.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Self

import bleach
from django.conf import settings
from django.utils.text import slugify
from elasticsearch import RequestError
from elasticsearch.dsl import Q as DSLQ
from elasticsearch.dsl.query import Query

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
from kitsune.search.strategies import (
    HybridSearchStrategy,
    MultiLocaleSearchStrategy,
    RRFQuery,
    SearchStrategy,
    SemanticSearchStrategy,
    TraditionalSearchStrategy,
)
from kitsune.sumo.urlresolvers import reverse
from kitsune.wiki.config import CATEGORIES

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


@dataclass
class StrategyBasedSearch(SumoSearch):
    """Base search class using Strategy Pattern."""

    locale: str = "en-US"
    product: Product | None = None
    strategy: SearchStrategy | None = None

    def __post_init__(self):
        """Initialize with default strategy if none provided."""
        if self.strategy is None:
            # Default to traditional strategy for backward compatibility
            self.strategy = TraditionalSearchStrategy()
        # After this point, strategy is guaranteed to be non-None
        self._strategy: SearchStrategy = self.strategy

    def set_strategy(self, strategy: SearchStrategy):
        """Change search strategy at runtime."""
        self.strategy = strategy
        self._strategy = strategy
        return self

    def get_base_fields(self) -> list[str]:
        """Get base field names for this search type."""
        # To be overridden by subclasses
        return []

    def get_fields(self) -> list[str]:
        """Get all searchable fields using the current strategy."""
        base_fields = self.get_base_fields()
        return self._strategy.get_fields(self.locale, base_fields)

    def build_query(self) -> Query:
        """Build the search query using the current strategy."""
        base_fields = self.get_base_fields()
        return self._strategy.build_query(
            self.query,
            self.locale,
            base_fields,
            self.parse_query,
            self.get_settings()
        )

    def run(self, key: int | slice | None = None) -> Self:
        """Execute search with strategy-specific handling."""
        if key is None:
            key = slice(0, settings.SEARCH_RESULTS_PER_PAGE)

        query = self.build_query()

        # Handle RRF queries differently
        if isinstance(query, RRFQuery):
            return self._run_rrf_search(query, key)

        # Traditional elasticsearch-dsl search
        return super().run(key)

    def _run_rrf_search(self, query: RRFQuery, key: int | slice) -> Self:
        """Execute RRF search using native Elasticsearch client."""
        client = es_client()
        rrf_dict = query.to_dict()
        filters = self._get_filters_only()

        # Apply filters to each retriever
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

        # Build search request body
        body = rrf_dict.copy()

        # Add highlighting
        highlight_fields = {}
        for field, options in self.get_highlight_fields_options():
            highlight_fields[field] = options
        if highlight_fields:
            body["highlight"] = {"fields": highlight_fields}

        # Add pagination
        if isinstance(key, slice):
            body["from"] = key.start or 0
            body["size"] = key.stop - (key.start or 0)
        else:
            body["from"] = key
            body["size"] = 1

        # Execute search
        try:
            result = client.search(index=self.get_index(), body=body, **settings.ES_SEARCH_PARAMS)
        except RequestError as e:
            if self.parse_query:
                self.parse_query = False
                return self.run(key)
            raise e

        # Process results
        self.hits = result["hits"]["hits"]
        total = result["hits"]["total"]
        self.total = total["value"] if isinstance(total, dict) else total
        self.results = [self.make_result(self._convert_hit_to_attrdict(hit)) for hit in self.hits]
        self.last_key = key

        return self

    def _convert_hit_to_attrdict(self, hit):
        """Convert ES hit dict to AttrDict-like object for compatibility."""
        from elasticsearch.dsl.utils import AttrDict

        source = hit.get("_source", {})
        attr_hit = AttrDict(source)

        attr_hit.meta = AttrDict({
            'id': hit["_id"],
            'index': hit["_index"],
            'score': hit["_score"]
        })

        if "highlight" in hit:
            attr_hit.meta.highlight = AttrDict(hit["highlight"])

        return attr_hit

    def _get_filters_only(self):
        """Get filter portion of the query."""
        # To be overridden by subclasses if needed
        return []


@dataclass
class QuestionSearch(StrategyBasedSearch):
    """Search over questions using Strategy Pattern."""

    def get_index(self):
        return QuestionDocument.Index.read_alias

    def get_base_fields(self) -> list[str]:
        """Get base question field names."""
        return ["question_title", "question_content", "answer_content"]

    def get_highlight_fields_options(self):
        return [
            (f"question_title.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            (f"question_content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            (f"answer_content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
        ]

    def get_settings(self):
        return {}

    def is_simple_search(self):
        """Check if this is a simple search query."""
        return not any([
            "field:" in self.query,
            "exact:" in self.query,
            "range:" in self.query,
        ])

    def get_filter(self):
        """Build the filter portion of the query."""
        filters = [
            DSLQ("term", _index=self.get_index()),
            DSLQ("exists", field=f"question_title.{self.locale}"),
            DSLQ(
                "range",
                question_created={
                    "gte": datetime.now(UTC) - timedelta(days=QUESTION_DAYS_DELTA)
                },
            ),
        ]

        if self.is_simple_search():
            filters.append(DSLQ("term", question_is_archived=False))

        if self.product:
            filters.append(DSLQ("term", question_product_id=self.product.id))

        return DSLQ(
            "bool",
            filter=filters,
            must_not=DSLQ("exists", field="updated"),
            must=self.build_query(),
        )

    def _get_filters_only(self):
        """Get just the filter portion without the query."""
        filters = [
            DSLQ("term", _index=self.get_index()),
            DSLQ("exists", field=f"question_title.{self.locale}"),
            DSLQ(
                "range",
                question_created={
                    "gte": datetime.now(UTC) - timedelta(days=QUESTION_DAYS_DELTA)
                },
            ),
        ]

        if self.is_simple_search():
            filters.append(DSLQ("term", question_is_archived=False))

        if self.product:
            filters.append(DSLQ("term", question_product_id=self.product.id))

        return filters

    def make_result(self, hit):
        """Create a result dictionary from a search hit."""
        question_id = hit.question_id
        question_title = hit.question_title
        question_is_solved = hit.question_has_solution
        question_created = hit.question_created
        question_num_answers = hit.meta.id[2:] if hit.meta.id.startswith("a_") else None
        question_num_votes = hit.question_num_votes
        answer_snippet = first_highlight(hit) or hit.question_content
        answer_snippet = strip_html(answer_snippet)

        return {
            "search_summary": answer_snippet,
            "is_solved": question_is_solved,
            "created": question_created,
            "title": question_title,
            "type": "question",
            "url": reverse("questions.details", kwargs={"question_id": question_id}),
            "object": hit,
            "num_answers": question_num_answers,
            "num_votes": question_num_votes,
            "num_votes_past_week": 0,
        }


@dataclass
class WikiSearch(StrategyBasedSearch):
    """Search over wiki documents using Strategy Pattern."""

    def get_index(self):
        return WikiDocument.Index.read_alias

    def get_base_fields(self) -> list[str]:
        """Get base wiki field names."""
        return ["title", "content", "summary", "keywords"]

    def get_highlight_fields_options(self):
        return [
            (f"content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            (f"summary.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
        ]

    def get_settings(self):
        return {"exact": {"field": "slug"}, "category": CATEGORY_EXACT_MAPPING}

    def get_filter(self):
        """Build the filter portion of the query."""
        filters = [
            DSLQ("term", _index=self.get_index()),
            DSLQ("exists", field=f"title.{self.locale}"),
        ]

        if self.product:
            filters.append(DSLQ("term", product_ids=self.product.id))

        return DSLQ("bool", filter=filters, must=self.build_query())

    def _get_filters_only(self):
        """Get just the filter portion without the query."""
        filters = [
            DSLQ("term", _index=self.get_index()),
            DSLQ("exists", field=f"title.{self.locale}"),
        ]

        if self.product:
            filters.append(DSLQ("term", product_ids=self.product.id))

        return filters

    def make_result(self, hit):
        """Create a result dictionary from a search hit."""
        doc_id = hit.doc_id
        if same_base_index(hit.meta.index, WikiDocument.Index.base_name):
            doc_slug = doc_id.get(self.locale, doc_id["en-US"])
        else:
            doc_slug = doc_id

        doc_title = hit.title
        doc_summary = first_highlight(hit) or hit.summary
        doc_summary = strip_html(doc_summary)

        return {
            "title": doc_title.get(self.locale, doc_title["en-US"]),
            "type": "document",
            "search_summary": doc_summary.get(self.locale, doc_summary.get("en-US", "")),
            "url": reverse("wiki.document", args=[doc_slug]),
            "object": hit,
        }


@dataclass
class ProfileSearch(StrategyBasedSearch):
    """Search over user profiles using Strategy Pattern."""

    def get_index(self):
        return ProfileDocument.Index.read_alias

    def get_base_fields(self) -> list[str]:
        """Get base profile field names."""
        return ["username", "name"]

    def get_highlight_fields_options(self):
        return []

    def get_settings(self):
        return {}

    def get_filter(self):
        """Build the filter portion of the query."""
        return DSLQ("bool", must=self.build_query())

    def make_result(self, hit):
        """Create a result dictionary from a search hit."""
        return {
            "type": "user",
            "object": hit,
        }


@dataclass
class ForumSearch(StrategyBasedSearch):
    """Search over forum posts using Strategy Pattern."""

    def get_index(self):
        return ForumDocument.Index.read_alias

    def get_base_fields(self) -> list[str]:
        """Get base forum field names."""
        return ["thread_title", "content"]

    def get_highlight_fields_options(self):
        return [
            ("thread_title", FVH_HIGHLIGHT_OPTIONS),
            ("content", FVH_HIGHLIGHT_OPTIONS),
        ]

    def get_settings(self):
        return {}

    def get_filter(self):
        """Build the filter portion of the query."""
        return DSLQ("bool", must=self.build_query())

    def make_result(self, hit):
        """Create a result dictionary from a search hit."""
        thread_id = hit.thread_id
        post_title = hit.thread_title
        post_content = first_highlight(hit) or hit.content

        return {
            "title": post_title,
            "search_summary": strip_html(post_content),
            "type": "thread",
            "url": reverse("forums.posts", kwargs={"forum_slug": hit.forum_slug, "thread_id": thread_id}),
            "object": hit,
        }


# Create convenient classes for specific search strategies
# These maintain backward compatibility with the original API

class SemanticWikiSearch(WikiSearch):
    """Wiki search using semantic strategy."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = SemanticSearchStrategy()


class SemanticQuestionSearch(QuestionSearch):
    """Question search using semantic strategy."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = SemanticSearchStrategy()


class HybridWikiSearch(WikiSearch):
    """Wiki search using hybrid strategy."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = HybridSearchStrategy()


class HybridQuestionSearch(QuestionSearch):
    """Question search using hybrid strategy."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = HybridSearchStrategy()


@dataclass
class CompoundSearch(StrategyBasedSearch):
    """Compound search across multiple document types."""

    def __init__(self, query="", locale="en-US", product=None, strategy=None):
        super().__init__(query=query, locale=locale, product=product, strategy=strategy)
        self.searches = []

    def add(self, search):
        """Add a search to the compound search."""
        self.searches.append(search)
        return self

    def run(self, key=None):
        """Execute all searches in the compound search."""
        results = []
        total = 0

        for search in self.searches:
            search.run(key)
            results.extend(search.results)
            total += search.total

        self.results = results
        self.total = total
        return self


class HybridCompoundSearch(CompoundSearch):
    """Compound search using hybrid strategy."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = HybridSearchStrategy()


# Multi-locale search classes

@dataclass
class MultiLocaleWikiSearch(WikiSearch):
    """Multi-locale wiki search."""
    locales: list[str] | None = None
    primary_locale: str = "en-US"

    def __post_init__(self):
        super().__post_init__()
        if self.locales is None:
            self.locales = [self.locale]
        self.strategy = MultiLocaleSearchStrategy(
            TraditionalSearchStrategy(),
            self.locales,
            self.primary_locale
        )

    def get_fields(self):
        """Get fields for all locales."""
        base_fields = self.get_base_fields()
        all_fields = []
        for locale in self.locales:
            for field in base_fields:
                all_fields.append(f"{field}.{locale}")
        return all_fields


@dataclass
class MultiLocaleQuestionSearch(QuestionSearch):
    """Multi-locale question search."""
    locales: list[str] | None = None
    primary_locale: str = "en-US"

    def __post_init__(self):
        super().__post_init__()
        if self.locales is None:
            self.locales = [self.locale]
        self.strategy = MultiLocaleSearchStrategy(
            TraditionalSearchStrategy(),
            self.locales,
            self.primary_locale
        )

    def get_fields(self):
        """Get fields for all locales."""
        base_fields = self.get_base_fields()
        all_fields = []
        for locale in self.locales:
            for field in base_fields:
                all_fields.append(f"{field}.{locale}")
        return all_fields


class MultiLocaleSemanticWikiSearch(MultiLocaleWikiSearch):
    """Multi-locale semantic wiki search."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = MultiLocaleSearchStrategy(
            SemanticSearchStrategy(),
            self.locales,
            self.primary_locale
        )


class MultiLocaleSemanticQuestionSearch(MultiLocaleQuestionSearch):
    """Multi-locale semantic question search."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = MultiLocaleSearchStrategy(
            SemanticSearchStrategy(),
            self.locales,
            self.primary_locale
        )


class MultiLocaleHybridWikiSearch(MultiLocaleWikiSearch):
    """Multi-locale hybrid wiki search."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = MultiLocaleSearchStrategy(
            HybridSearchStrategy(),
            self.locales,
            self.primary_locale
        )


class MultiLocaleHybridQuestionSearch(MultiLocaleQuestionSearch):
    """Multi-locale hybrid question search."""
    def __post_init__(self):
        super().__post_init__()
        self.strategy = MultiLocaleSearchStrategy(
            HybridSearchStrategy(),
            self.locales,
            self.primary_locale
        )


# Maintain backward compatibility by exporting HybridSearch base class
HybridSearch = StrategyBasedSearch
