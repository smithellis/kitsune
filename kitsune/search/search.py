from dataclasses import dataclass
from dataclasses import field as dfield
from datetime import UTC, datetime, timedelta

import bleach
from dateutil import parser
from django.utils.text import slugify
from elasticsearch.dsl import Q as DSLQ
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


class RRFQuery:
    """Wrapper class for Reciprocal Rank Fusion queries in Elasticsearch."""

    def __init__(self, query_dict):
        self.query_dict = query_dict

    def to_dict(self):
        return self.query_dict


# Constants
QUESTION_DAYS_DELTA = 365 * 2
RRF_CONFIG = {"rank_window_size": 100, "rank_constant": 20}
SEMANTIC_BOOST = {"user_locale": 2.0, "en_us": 1.0}

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
    "dict": {slugify(str(name)): _id for _id, name in CATEGORIES},
    "field": "category",
}


# Utility functions
def first_highlight(hit):
    """Extract first highlight from search hit."""
    if not (highlight := getattr(hit.meta, "highlight", None)):
        return None
    return next(iter(highlight.to_dict().values()))[0]


def strip_html(summary):
    """Strip HTML tags except highlight tags."""
    return bleach.clean(summary, tags=[HIGHLIGHT_TAG], strip=True)


def same_base_index(a, b):
    """Check if the base parts of two index names are the same."""
    return a.split("_")[:-1] == b.split("_")[:-1]


# Base class for semantic search functionality
class SemanticSearchMixin:
    """Mixin providing semantic search capabilities."""

    def get_semantic_fields(self):
        """Return semantic field names for this search type."""
        raise NotImplementedError("Subclasses must implement get_semantic_fields")

    def get_en_us_semantic_fields(self):
        """Return en-US semantic fields for cross-language boost."""
        if self.locale == "en-US":
            return []
        # Replace user locale with en-US in semantic field names
        return [field.replace(f".{self.locale}", ".en-US")
                for field in self.get_semantic_fields()]

    def build_semantic_query(self):
        """Build semantic query with user locale + en-US boost."""
        semantic_queries = [
            DSLQ("semantic", field=field, query=self.query, boost=SEMANTIC_BOOST["user_locale"])
            for field in self.get_semantic_fields()
        ]

        # Add en-US boost for non-English locales
        semantic_queries.extend([
            DSLQ("semantic", field=field, query=self.query, boost=SEMANTIC_BOOST["en_us"])
            for field in self.get_en_us_semantic_fields()
        ])

        return DSLQ("bool", should=semantic_queries, minimum_should_match=1)


# Base class for hybrid search functionality
class HybridSearchMixin(SemanticSearchMixin):
    """Mixin providing hybrid RRF search capabilities."""

    def build_hybrid_rrf_query(self):
        """Build RRF query combining traditional and semantic search."""
        return RRFQuery({
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": self.build_traditional_query_with_filters().to_dict()}},
                        {"standard": {"query": self.build_semantic_query_with_filters().to_dict()}}
                    ],
                    **RRF_CONFIG
                }
            }
        })

    def build_traditional_query(self):
        """Build traditional text-based query with locale preference."""
        return DSLQ(
            "multi_match",
            query=self.query,
            fields=self.get_hybrid_fields(),
            type="best_fields",
            operator=self.default_operator.lower()
        )

    def build_traditional_query_with_filters(self):
        """Build traditional query with filters applied."""
        return DSLQ("bool", filter=self.get_base_filters(), must=self.build_traditional_query())

    def build_semantic_query_with_filters(self):
        """Build semantic query with filters applied."""
        return DSLQ("bool", filter=self.get_base_filters(), must=self.build_semantic_query())

    def build_query(self):
        """Build query - hybrid by default, advanced when syntax detected."""
        if self.is_advanced_query():
            return super().build_query()
        return self.build_hybrid_rrf_query()

    def get_filter(self):
        """Get filter for search execution."""
        if self.is_advanced_query():
            return DSLQ("bool", filter=self.get_base_filters(), must=super().build_query())
        return self.build_hybrid_rrf_query()


@dataclass
class QuestionSearch(HybridSearchMixin, SumoSearch):
    """Search over questions."""

    locale: str = "en-US"
    product: Product | None = None

    def get_index(self):
        return QuestionDocument.Index.read_alias

    def get_fields(self):
        return [
            f"question_title.{self.locale}^2",
            f"question_content.{self.locale}",
            f"answer_content.{self.locale}",
        ]

    def get_semantic_fields(self):
        return [
            f"question_title_semantic.{self.locale}",
            f"question_content_semantic.{self.locale}",
            f"answer_content_semantic.{self.locale}",
        ]

    def get_hybrid_fields(self):
        """Return fields for hybrid search, favoring user locale over en-US."""
        base_fields = [
            f"question_title.{self.locale}^3",
            f"question_content.{self.locale}^2",
            f"answer_content.{self.locale}^2",
        ]

        if self.locale != "en-US":
            base_fields.extend([
                "question_title.en-US^1.5",
                "question_content.en-US^1",
                "answer_content.en-US^1",
            ])

        return base_fields

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

    def is_simple_search(self, token=None):
        """Determine if the search query is simple (no advanced operators) or advanced."""
        if token is None:
            if not self.query or not self.query.strip():
                return True
            try:
                return self.is_simple_search(Parser(self.query).parsed)
            except ParseException:
                return True

        # Check for advanced operators/tokens
        advanced_types = (FieldOperator, AndOperator, OrOperator, NotOperator, RangeToken, ExactToken)
        if isinstance(token, advanced_types):
            return False

        if isinstance(token, TermToken):
            return True

        if isinstance(token, SpaceOperator):
            return all(self.is_simple_search(arg) for arg in token.arguments)

        return False

    def get_base_filters(self):
        """Get the base filters for this search."""
        filters = [
            DSLQ("term", _index=self.get_index()),
            DSLQ("exists", field=f"question_title.{self.locale}"),
            DSLQ("range", question_created={
                "gte": datetime.now(UTC) - timedelta(days=QUESTION_DAYS_DELTA)
            }),
            DSLQ("bool", must_not=DSLQ("exists", field="updated")),  # Exclude AnswerDocuments
        ]

        if self.is_simple_search():
            filters.append(DSLQ("term", question_is_archived=False))

        if self.product:
            filters.append(DSLQ("term", question_product_id=self.product.id))

        return filters

    def get_highlight_fields_options(self):
        return [
            (f"question_content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            (f"answer_content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
        ]

    def make_result(self, hit):
        summary = first_highlight(hit) or hit.question_content[self.locale][:SNIPPET_LENGTH]
        answer_content = getattr(hit, "answer_content", None)

        return {
            "type": "question",
            "url": reverse("questions.details", kwargs={"question_id": hit.question_id}),
            "score": hit.meta.score,
            "title": hit.question_title[self.locale],
            "search_summary": strip_html(summary),
            "last_updated": datetime.fromisoformat(hit.question_updated),
            "is_solved": hit.question_has_solution,
            "num_answers": len(answer_content[self.locale]) if answer_content else 0,
            "num_votes": hit.question_num_votes,
        }


@dataclass
class WikiSearch(HybridSearchMixin, SumoSearch):
    """Search over Knowledge Base articles."""

    locale: str = "en-US"
    product: Product | None = None

    def get_index(self):
        return WikiDocument.Index.read_alias

    def get_fields(self):
        return [
            f"keywords.{self.locale}^8",
            f"title.{self.locale}^6",
            f"summary.{self.locale}^4",
            f"content.{self.locale}^2",
        ]

    def get_semantic_fields(self):
        return [
            f"title_semantic.{self.locale}",
            f"content_semantic.{self.locale}",
            f"summary_semantic.{self.locale}",
        ]

    def get_hybrid_fields(self):
        """Return fields for hybrid search, favoring user locale over en-US."""
        base_fields = [
            f"keywords.{self.locale}^8",
            f"title.{self.locale}^6",
            f"summary.{self.locale}^4",
            f"content.{self.locale}^2",
        ]

        if self.locale != "en-US":
            base_fields.extend([
                "keywords.en-US^4",
                "title.en-US^3",
                "summary.en-US^2",
                "content.en-US^1",
            ])

        return base_fields

    def get_settings(self):
        return {
            "field_mappings": {
                "title": f"title.{self.locale}",
                "content": f"content.{self.locale}",
            },
            "exact_mappings": {
                "category": CATEGORY_EXACT_MAPPING,
            },
            "range_allowed": ["updated"],
        }

    def get_base_filters(self):
        """Get the base filters for this search."""
        filters = [
            DSLQ("term", _index=self.get_index()),
            DSLQ("exists", field=f"title.{self.locale}"),
        ]

        if self.product:
            filters.append(DSLQ("term", product_ids=self.product.id))

        return filters

    def get_highlight_fields_options(self):
        return [
            (f"summary.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
            (f"content.{self.locale}", FVH_HIGHLIGHT_OPTIONS),
        ]

    def make_result(self, hit):
        summary = (first_highlight(hit) or
                  getattr(hit.summary, self.locale, None) or
                  hit.content[self.locale][:SNIPPET_LENGTH])

        return {
            "type": "document",
            "url": reverse("wiki.document", args=[hit.slug[self.locale]], locale=self.locale),
            "score": hit.meta.score,
            "title": hit.title[self.locale],
            "search_summary": strip_html(summary),
            "id": hit.meta.id,
        }


@dataclass
class ProfileSearch(SumoSearch):
    """Search over User Profiles."""

    group_ids: list[int] = dfield(default_factory=list)

    def get_index(self):
        return ProfileDocument.Index.read_alias

    def get_fields(self):
        return ["username", "name"]

    def get_highlight_fields_options(self):
        return []

    def get_filter(self):
        return DSLQ(
            "boosting",
            positive=self.build_query(),
            negative=DSLQ("bool", must_not=DSLQ("terms", group_ids=self.group_ids)),
            negative_boost=0.5,
        )

    def make_result(self, hit):
        return {
            "type": "user",
            "avatar": getattr(hit, "avatar", None),
            "username": hit.username,
            "name": getattr(hit, "name", ""),
            "user_id": hit.meta.id,
        }


@dataclass
class ForumSearch(SumoSearch):
    """Search over Forum posts."""

    thread_forum_id: int | None = None

    def get_index(self):
        return ForumDocument.Index.read_alias

    def get_fields(self):
        return ["thread_title", "content"]

    def get_settings(self):
        return {
            "field_mappings": {"title": "thread_title"},
            "range_allowed": ["thread_created", "created", "updated"],
        }

    def get_highlight_fields_options(self):
        return []

    def get_filter(self):
        filters = [DSLQ("term", _index=self.get_index())]

        if self.thread_forum_id:
            filters.append(DSLQ("term", thread_forum_id=self.thread_forum_id))

        return DSLQ("bool", filter=filters, must=self.build_query())

    def make_result(self, hit):
        return {
            "type": "thread",
            "title": hit.thread_title,
            "search_summary": strip_html(wiki_to_html(hit.content))[:1000],
            "last_updated": parser.parse(hit.updated),
            "url": (reverse("forums.posts",
                          kwargs={"forum_slug": hit.forum_slug, "thread_id": hit.thread_id}) +
                   f"#post-{hit.meta.id}"),
        }


@dataclass
class CompoundSearch(SumoSearch):
    """Combine multiple SumoSearch classes into one search."""

    _children: list[SumoSearch] = dfield(default_factory=list, init=False)

    def __post_init__(self):
        super().__post_init__()
        self._parse_query = True

    @property  # type: ignore[misc]
    def parse_query(self):
        return self._parse_query

    @parse_query.setter
    def parse_query(self, value):
        """Set value of parse_query across all children."""
        self._parse_query = value
        for child in self._children:
            child.parse_query = value

    def add(self, child):
        """Add a SumoSearch instance to search over. Chainable."""
        self._children.append(child)
        return self

    def is_advanced_query(self):
        """Check if any child considers this an advanced query."""
        return any(getattr(child, 'is_advanced_query', lambda: False)()
                  for child in self._children)

    def _from_children(self, method_name):
        """Get an attribute from all children and flatten lists."""
        result = []
        for child in self._children:
            attr = getattr(child, method_name)()
            result.extend(attr if isinstance(attr, list) else [attr])
        return result

    def get_index(self):
        return ",".join(self._from_children("get_index"))

    def get_fields(self):
        return self._from_children("get_fields")

    def get_highlight_fields_options(self):
        return self._from_children("get_highlight_fields_options")

    def get_filter(self):
        if self.is_advanced_query():
            return DSLQ("bool", should=self._from_children("get_filter"), minimum_should_match=1)
        return self._build_compound_hybrid_query()

    def _build_compound_hybrid_query(self):
        """Build a compound hybrid query combining multiple document types."""
        traditional_queries = []
        semantic_queries = []

        for child in self._children:
            if hasattr(child, 'build_traditional_query_with_filters'):
                traditional_queries.append(child.build_traditional_query_with_filters())
            if hasattr(child, 'build_semantic_query_with_filters'):
                semantic_queries.append(child.build_semantic_query_with_filters())

        return RRFQuery({
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": DSLQ("bool", should=traditional_queries, minimum_should_match=1).to_dict()}},
                        {"standard": {"query": DSLQ("bool", should=semantic_queries, minimum_should_match=1).to_dict()}}
                    ],
                    **RRF_CONFIG
                }
            }
        })

    def make_result(self, hit):
        index = hit.meta.index
        for child in self._children:
            if same_base_index(index, child.get_index()):
                return child.make_result(hit)
