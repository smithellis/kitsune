from dataclasses import dataclass
from dataclasses import field as dfield
from datetime import UTC, datetime, timedelta

import bleach
from dateutil import parser
from django.utils.text import slugify
from elasticsearch.dsl import Q as DSLQ

from kitsune.products.models import Product
from kitsune.search import HIGHLIGHT_TAG, SNIPPET_LENGTH
from kitsune.search.base import QueryStrategy, SumoSearch
from kitsune.search.documents import (
    ForumDocument,
    ProfileDocument,
    QuestionDocument,
    WikiDocument,
)
from kitsune.sumo.urlresolvers import reverse
from kitsune.wiki.config import CATEGORIES
from kitsune.wiki.parser import wiki_to_html

QUESTION_DAYS_DELTA = 365 * 2


class RRFQuery:
    def __init__(self, query_dict):
        self.query_dict = query_dict

    def to_dict(self):
        return self.query_dict
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
    highlight = getattr(hit.meta, "highlight", None)
    if highlight:
        return next(iter(highlight.to_dict().values()))[0]
    return None


def strip_html(summary):
    return bleach.clean(
        summary,
        tags=[HIGHLIGHT_TAG],
        strip=True,
    )


@dataclass
class QuestionSearch(SumoSearch):
    """Search over questions."""

    locale: str = "en-US"
    product: Product | None = None

    def get_index(self):
        return QuestionDocument.Index.read_alias

    def get_fields(self):
        """Return enhanced fields based on query intent."""
        boosts = self.get_enhanced_fields()

        return [
            # Enhanced boosting based on query intent
            f"question_title.{self.locale}^{boosts['title_boost']}",
            f"question_content.{self.locale}^{boosts['content_boost']}",
            f"answer_content.{self.locale}^{boosts['summary_boost']}",  # Answers treated as summary
        ]

    def get_settings(self):
        return {
            "field_mappings": {
                "title": f"question_title.{self.locale}",
                "content": [f"question_content.{self.locale}", f"answer_content.{self.locale}"],
                "question": f"question_content.{self.locale}",
                "answer": f"answer_content.{self.locale}",
            },
            "range_allowed": [
                "question_created",
                "question_updated",
                "question_taken_until",
                "question_num_votes",
            ],
        }

    def get_advanced_query_field_names(self):
        """Return list of field names that can be used in advanced queries."""
        return ["title", "content", "question", "answer"]

    def get_base_filters(self):
        """Get base filters that apply to all query types."""
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
        if not self.is_advanced_query():
            filters.append(DSLQ("term", question_is_archived=False))
        if self.product:
            filters.append(DSLQ("term", question_product_id=self.product.id))
        return filters

    def get_semantic_fields(self):
        """Return semantic fields for QuestionSearch."""
        return [
            "question_title_semantic",
            "question_content_semantic",
            "answer_content_semantic",
        ]

    def _apply_filters_to_query(self, query):
        """Apply question-specific filters to a query."""
        return DSLQ(
            "bool",
            filter=self.get_base_filters(),
            must_not=DSLQ("exists", field="updated"),
            must=query
        )

    def build_query(self):
        """Build query using smart hybrid approach based on query strategy."""
        return self.build_smart_hybrid_query()

    def get_highlight_fields_options(self):
        fields = [
            f"question_content.{self.locale}",
            f"answer_content.{self.locale}",
        ]
        return [(field, FVH_HIGHLIGHT_OPTIONS) for field in fields]

    def get_filter(self):
        # Check if we're building an RRF query
        query = self.build_query()
        if isinstance(query, RRFQuery):
            # For RRF queries, filters are already applied inside the retrievers
            return query
        else:
            # Traditional query flow
            return DSLQ(
                "bool",
                filter=self.get_base_filters(),
                must_not=DSLQ("exists", field="updated"),
                must=query
            )

    def make_result(self, hit):
        # generate a summary for search:
        summary = first_highlight(hit)
        if not summary:
            summary = hit.question_content[self.locale][:SNIPPET_LENGTH]
        summary = strip_html(summary)

        # for questions that have no answers, set to None:
        answer_content = getattr(hit, "answer_content", None)

        return {
            "type": "question",
            "url": reverse("questions.details", kwargs={"question_id": hit.question_id}),
            "score": hit.meta.score,
            "title": hit.question_title[self.locale],
            "search_summary": summary,
            "last_updated": datetime.fromisoformat(hit.question_updated),
            "is_solved": hit.question_has_solution,
            "num_answers": len(answer_content[self.locale]) if answer_content else 0,
            "num_votes": hit.question_num_votes,
        }


@dataclass
class WikiSearch(SumoSearch):
    """Search over Knowledge Base articles."""

    locale: str = "en-US"
    product: Product | None = None

    def get_index(self):
        return WikiDocument.Index.read_alias

    def get_fields(self):
        """Return enhanced fields based on query intent."""
        boosts = self.get_enhanced_fields()

        return [
            # Enhanced boosting based on query intent
            f"keywords.{self.locale}^{boosts['keywords_boost']}",
            f"title.{self.locale}^{boosts['title_boost']}",
            f"summary.{self.locale}^{boosts['summary_boost']}",
            f"content.{self.locale}^{boosts['content_boost']}",
        ]

    def get_settings(self):
        return {
            "field_mappings": {
                "title": f"title.{self.locale}",
                "content": f"content.{self.locale}",
            },
            "exact_mappings": {
                "category": CATEGORY_EXACT_MAPPING,
            },
            "range_allowed": [
                "updated",
            ],
        }

    def get_highlight_fields_options(self):
        fields = [
            f"summary.{self.locale}",
            f"content.{self.locale}",
        ]
        return [(field, FVH_HIGHLIGHT_OPTIONS) for field in fields]

    def get_advanced_query_field_names(self):
        """Return list of field names that can be used in advanced queries."""
        return ["title", "content", "category"]

    def get_base_filters(self):
        """Get base filters that apply to all query types."""
        filters = [
            DSLQ("term", _index=self.get_index()),
            DSLQ("exists", field=f"title.{self.locale}"),
        ]
        if self.product:
            filters.append(DSLQ("term", product_ids=self.product.id))
        return filters

    def get_semantic_fields(self):
        """Return semantic fields for WikiSearch."""
        return [
            "title_semantic",
            "content_semantic",
            "summary_semantic",
        ]

    def build_query(self):
        """Build query using smart hybrid approach based on query strategy."""
        return self.build_smart_hybrid_query()


    def get_filter(self):
        # Check if we're building an RRF query
        query = self.build_query()
        if isinstance(query, RRFQuery):
            # For RRF queries, filters are already applied inside the retrievers
            return query
        else:
            # Traditional query flow
            return DSLQ("bool", filter=self.get_base_filters(), must=query)

    def make_result(self, hit):
        # generate a summary for search:
        summary = first_highlight(hit)
        if not summary and hasattr(hit, "summary"):
            summary = getattr(hit.summary, self.locale, None)
        if not summary:
            summary = hit.content[self.locale][:SNIPPET_LENGTH]
        summary = strip_html(summary)

        return {
            "type": "document",
            "url": reverse("wiki.document", args=[hit.slug[self.locale]], locale=self.locale),
            "score": hit.meta.score,
            "title": hit.title[self.locale],
            "search_summary": summary,
            "id": hit.meta.id,
        }


@dataclass
class ProfileSearch(SumoSearch):
    """Search over User Profiles."""

    group_ids: list[int] = dfield(default_factory=list)

    def get_index(self):
        return ProfileDocument.Index.read_alias

    def get_fields(self):
        """Return enhanced fields based on query intent."""
        boosts = self.get_enhanced_fields()

        return [
            f"username^{boosts['title_boost']}",  # Username treated as title
            f"name^{boosts['content_boost']}",     # Name treated as content
        ]

    def get_highlight_fields_options(self):
        return []

    def get_base_filters(self):
        """Get base filters that apply to all query types."""
        filters = [
            DSLQ("term", _index=self.get_index()),
        ]

        if self.group_ids:
            filters.append(
                DSLQ("bool", must_not=DSLQ("terms", group_ids=self.group_ids))
            )

        return filters

    def get_semantic_fields(self):
        """Return semantic fields for ProfileSearch."""
        return []  # Profile search typically doesn't have semantic fields

    def build_query(self):
        """Build query using smart hybrid approach based on query strategy."""
        return self.build_smart_hybrid_query()

    def get_filter(self):
        # Check if we're building an RRF query
        query = self.build_query()
        if isinstance(query, RRFQuery):
            # For RRF queries, filters are already applied inside the retrievers
            return query
        else:
            # Traditional query flow
            return DSLQ(
                "bool",
                filter=self.get_base_filters(),
                must=query
            )

    def make_result(self, hit):
        return {
            "type": "profile",
            "url": reverse("users.profile", kwargs={"username": hit.username}),
            "score": hit.meta.score,
            "title": hit.name or hit.username,
            "search_summary": f"User profile: {hit.name or hit.username}",
            "username": hit.username,
            "name": hit.name,
        }


@dataclass
class ForumSearch(SumoSearch):
    """Search over Forum Threads."""

    thread_forum_id: int | None = None

    def get_index(self):
        return ForumDocument.Index.read_alias

    def get_fields(self):
        """Return enhanced fields based on query intent."""
        boosts = self.get_enhanced_fields()

        return [
            f"thread_title^{boosts['title_boost']}",
            f"content^{boosts['content_boost']}",
        ]

    def get_settings(self):
        return {
            "field_mappings": {
                "title": "thread_title",
            },
            "range_allowed": [
                "thread_created",
                "created",
                "updated",
            ],
        }

    def get_highlight_fields_options(self):
        return []

    def get_base_filters(self):
        """Get base filters that apply to all query types."""
        filters = [
            # limit scope to the Forum index
            DSLQ("term", _index=self.get_index())
        ]

        if self.thread_forum_id:
            filters.append(DSLQ("term", thread_forum_id=self.thread_forum_id))

        return filters

    def get_semantic_fields(self):
        """Return semantic fields for ForumSearch."""
        return []  # Forum search typically doesn't have semantic fields

    def build_query(self):
        """Build query using smart hybrid approach based on query strategy."""
        return self.build_smart_hybrid_query()

    def get_filter(self):
        # Check if we're building an RRF query
        query = self.build_query()
        if isinstance(query, RRFQuery):
            # For RRF queries, filters are already applied inside the retrievers
            return query
        else:
            # Traditional query flow
            return DSLQ("bool", filter=self.get_base_filters(), must=query)

    def make_result(self, hit):
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


@dataclass
class UnifiedRRFSearch(SumoSearch):
    """Unified search using Elasticsearch-level RRF to combine all search types."""

    locale: str = "en-US"
    product: Product | None = None
    group_ids: list[int] = dfield(default_factory=list)
    thread_forum_id: int | None = None
    min_score: float = 0.005

    def get_index(self):
        """Return combined index names for all search types."""
        indices = [
            QuestionDocument.Index.read_alias,
            WikiDocument.Index.read_alias,
            ProfileDocument.Index.read_alias,
            ForumDocument.Index.read_alias,
        ]
        return ",".join(indices)

    def get_fields(self):
        """Return enhanced combined fields based on query intent."""
        boosts = self.get_enhanced_fields()

        return [
            f"question_title.{self.locale}^{boosts['title_boost']}",
            f"question_content.{self.locale}^{boosts['content_boost']}",
            f"answer_content.{self.locale}^{boosts['summary_boost']}",
            f"keywords.{self.locale}^{boosts['keywords_boost']}",
            f"title.{self.locale}^{boosts['title_boost']}",
            f"summary.{self.locale}^{boosts['summary_boost']}",
            f"content.{self.locale}^{boosts['content_boost']}",
            f"username^{boosts['title_boost']}",
            f"name^{boosts['content_boost']}",
            f"thread_title^{boosts['title_boost']}",
        ]

    def get_highlight_fields_options(self):
        """Return combined highlight fields from all content types."""
        return [
            (f"question_content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            (f"answer_content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            (f"content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            (f"summary.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            ("thread_title", FVH_HIGHLIGHT_OPTIONS),
        ]

    def get_base_filters(self):
        """Get base filters that apply to all query types."""
        filters = []

        # Add index-specific filters
        filters.extend([
            # Question filters
            DSLQ("bool", filter=[
                DSLQ("term", _index=QuestionDocument.Index.read_alias),
                DSLQ("exists", field=f"question_title.{self.locale}"),
                DSLQ("term", question_is_archived=False),
                DSLQ("range", question_created={
                    "gte": datetime.now(UTC) - timedelta(days=QUESTION_DAYS_DELTA)
                }),
            ]),

            # Wiki filters
            DSLQ("bool", filter=[
                DSLQ("term", _index=WikiDocument.Index.read_alias),
                DSLQ("exists", field=f"title.{self.locale}"),
            ]),

            # Profile filters
            DSLQ("bool", filter=[
                DSLQ("term", _index=ProfileDocument.Index.read_alias),
            ]),

            # Forum filters
            DSLQ("bool", filter=[
                DSLQ("term", _index=ForumDocument.Index.read_alias),
            ]),
        ])

        # Add product filter if specified
        if self.product:
            filters.extend([
                DSLQ("term", question_product_id=self.product.id),
                DSLQ("term", product=self.product.id),
            ])

        # Add group exclusion for profiles
        if self.group_ids:
            filters.append(
                DSLQ("bool", must_not=DSLQ("terms", group_ids=self.group_ids))
            )

        # Add forum restriction
        if self.thread_forum_id:
            filters.append(DSLQ("term", thread_forum_id=self.thread_forum_id))

        return filters

    def get_semantic_fields(self):
        """Return combined semantic fields from all content types."""
        return [
            "question_title_semantic",
            "question_content_semantic",
            "answer_content_semantic",
            "title_semantic",
            "summary_semantic",
            "content_semantic",
        ]

    def build_query(self):
        """Build unified query using smart hybrid approach."""
        return self.build_smart_hybrid_query()

    def _build_unified_rrf_query(self, strategy: QueryStrategy) -> RRFQuery:
        """Build unified Elasticsearch-level RRF query across all content types."""
        # Get dynamic RRF parameters
        rrf_params = self.get_dynamic_rrf_params()

        # Build individual retrievers for each content type
        retrievers = []

        # Question retriever
        question_traditional = self._build_content_type_query(
            QuestionDocument.Index.read_alias,  # type: ignore[attr-defined]
            [
                f"question_title.{self.locale}^{self.get_enhanced_fields()['title_boost']}",
                f"question_content.{self.locale}^{self.get_enhanced_fields()['content_boost']}",
                f"answer_content.{self.locale}^{self.get_enhanced_fields()['summary_boost']}",
            ],
            [
                "question_title_semantic",
                "question_content_semantic",
                "answer_content_semantic",
            ],
            strategy
        )
        retrievers.append({"standard": {"query": question_traditional.to_dict()}})

        # Wiki retriever
        wiki_traditional = self._build_content_type_query(
            WikiDocument.Index.read_alias,  # type: ignore[attr-defined]
            [
                f"title.{self.locale}^{self.get_enhanced_fields()['title_boost']}",
                f"summary.{self.locale}^{self.get_enhanced_fields()['summary_boost']}",
                f"content.{self.locale}^{self.get_enhanced_fields()['content_boost']}",
                f"keywords.{self.locale}^{self.get_enhanced_fields()['keywords_boost']}",
            ],
            [
                "title_semantic",
                "summary_semantic",
                "content_semantic",
            ],
            strategy
        )
        retrievers.append({"standard": {"query": wiki_traditional.to_dict()}})

        # Profile retriever (no semantic fields)
        profile_traditional = self._build_content_type_query(
            ProfileDocument.Index.read_alias,  # type: ignore[attr-defined]
            [
                f"username^{self.get_enhanced_fields()['title_boost']}",
                f"name^{self.get_enhanced_fields()['content_boost']}",
            ],
            [],  # No semantic fields for profiles
            strategy
        )
        retrievers.append({"standard": {"query": profile_traditional.to_dict()}})

        # Forum retriever (no semantic fields)
        forum_traditional = self._build_content_type_query(
            ForumDocument.Index.read_alias,  # type: ignore[attr-defined]
            [
                f"thread_title^{self.get_enhanced_fields()['title_boost']}",
                f"content^{self.get_enhanced_fields()['content_boost']}",
            ],
            [],  # No semantic fields for forums
            strategy
        )
        retrievers.append({"standard": {"query": forum_traditional.to_dict()}})

        # Build RRF query
        rrf_query = {
            "retriever": {
                "rrf": {
                    "retrievers": retrievers,
                    "rank_window_size": rrf_params["window_size"],
                    "rank_constant": rrf_params["rank_constant"]
                }
            }
        }

        return RRFQuery(rrf_query)

    def _build_content_type_query(self, index: str, fields: list[str], semantic_fields: list[str], strategy: QueryStrategy):
        """Build query for a specific content type."""
        # Base filters for this content type
        base_filters = [DSLQ("term", _index=index)]

        # Add content-type specific filters
        if "question" in index:
            base_filters.extend([
                DSLQ("exists", field=f"question_title.{self.locale}"),
                DSLQ("term", question_is_archived=False),
                DSLQ("range", question_created={
                    "gte": datetime.now(UTC) - timedelta(days=QUESTION_DAYS_DELTA)
                }),
            ])
            if self.product:
                base_filters.append(DSLQ("term", question_product_id=self.product.id))
        elif "wiki" in index:
            base_filters.append(DSLQ("exists", field=f"title.{self.locale}"))
            if self.product:
                base_filters.append(DSLQ("term", product=self.product.id))
        elif "profile" in index and self.group_ids:
            base_filters.append(DSLQ("bool", must_not=DSLQ("terms", group_ids=self.group_ids)))
        elif "forum" in index and self.thread_forum_id:
            base_filters.append(DSLQ("term", thread_forum_id=self.thread_forum_id))

        # Build traditional query
        traditional_query = DSLQ(
            "simple_query_string",
            query=self.query,
            fields=fields,
            minimum_should_match="30%",
            flags="PHRASE"
        )

        # Apply filters
        filtered_traditional = DSLQ("bool", filter=base_filters, must=traditional_query)

        # For hybrid strategies, combine with semantic if available
        if strategy.value.startswith("hybrid") and semantic_fields:
            require_text_match = self.should_require_text_match()

            semantic_queries = [
                DSLQ("semantic", field=field_name, query=self.query)
                for field_name in semantic_fields
            ]
            combined_semantic = DSLQ("bool", should=semantic_queries, minimum_should_match=1)
            filtered_semantic = DSLQ("bool", filter=base_filters, must=combined_semantic)

            if require_text_match:
                # Require traditional match for semantic results
                return DSLQ("bool", must=filtered_semantic, filter=filtered_traditional)
            else:
                # Allow semantic-only results
                return DSLQ("bool", should=[filtered_traditional, filtered_semantic], minimum_should_match=1)

        return filtered_traditional

    def build_smart_hybrid_query(self):
        """Override to use unified RRF approach."""
        strategy = self.get_query_strategy()

        # For advanced structured queries, use traditional approach
        if strategy == QueryStrategy.ADVANCED_STRUCTURED:
            return self._build_traditional_unified_query()

        # For all other queries, use unified RRF
        return self._build_unified_rrf_query(strategy)

    def _build_traditional_unified_query(self):
        """Build traditional query for advanced/structured queries."""
        # Use query_string for field operators
        query = DSLQ(
            "query_string",
            query=self.query,
            fields=self.get_fields()
        )

        # Apply all base filters
        return DSLQ("bool", filter=self.get_base_filters(), must=query)

    def get_filter(self):
        """Return the unified query with all filters applied."""
        return self.build_query()

    def make_result(self, hit):
        """Create result based on the hit's index type."""
        index = hit.meta.index

        if "question" in index:
            return self._make_question_result(hit)
        elif "wiki" in index:
            return self._make_wiki_result(hit)
        elif "profile" in index:
            return self._make_profile_result(hit)
        elif "forum" in index:
            return self._make_forum_result(hit)
        else:
            return self._make_default_result(hit)

    def _make_question_result(self, hit):
        """Create result for question documents."""
        summary = first_highlight(hit) or hit.question_content[self.locale][:SNIPPET_LENGTH]
        summary = strip_html(summary)

        answer_content = getattr(hit, "answer_content", None)
        return {
            "type": "question",
            "url": reverse("questions.details", kwargs={"question_id": hit.question_id}),
            "score": hit.meta.score,
            "title": hit.question_title[self.locale],
            "search_summary": summary,
            "last_updated": datetime.fromisoformat(hit.question_updated),
            "is_solved": hit.question_has_solution,
            "num_answers": len(answer_content[self.locale]) if answer_content else 0,
            "num_votes": hit.question_num_votes,
        }

    def _make_wiki_result(self, hit):
        """Create result for wiki documents."""
        summary = first_highlight(hit) or getattr(hit, f"summary.{self.locale}", "")[:SNIPPET_LENGTH]
        summary = strip_html(summary)

        return {
            "type": "document",
            "url": reverse("wiki.document", kwargs={"document_slug": hit.slug}),
            "score": hit.meta.score,
            "title": hit.title[self.locale],
            "search_summary": summary,
            "last_updated": datetime.fromisoformat(hit.updated),
            "product": getattr(hit, "product", ""),
            "topic": getattr(hit, "topic", ""),
        }

    def _make_profile_result(self, hit):
        """Create result for profile documents."""
        return {
            "type": "profile",
            "url": reverse("users.profile", kwargs={"username": hit.username}),
            "score": hit.meta.score,
            "title": hit.name or hit.username,
            "search_summary": f"User profile: {hit.name or hit.username}",
            "username": hit.username,
            "name": hit.name,
        }

    def _make_forum_result(self, hit):
        """Create result for forum documents."""
        summary = strip_html(wiki_to_html(hit.content))[:1000]

        return {
            "type": "thread",
            "title": hit.thread_title,
            "search_summary": summary,
            "last_updated": parser.parse(hit.updated),
            "url": reverse(
                "forums.posts",
                kwargs={"forum_slug": hit.forum_slug, "thread_id": hit.thread_id},
            ) + f"#post-{hit.meta.id}",
        }

    def _make_default_result(self, hit):
        """Create default result for unknown document types."""
        return {
            "type": "document",
            "title": getattr(hit, "title", "Unknown"),
            "url": "#",
            "score": getattr(hit.meta, "score", 0),
            "search_summary": getattr(hit, "content", "")[:200],
        }
