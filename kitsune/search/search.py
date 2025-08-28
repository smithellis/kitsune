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
from kitsune.search.parser.tokens import ExactToken, RangeToken
from kitsune.sumo.urlresolvers import reverse
from kitsune.wiki.config import CATEGORIES
from kitsune.wiki.parser import wiki_to_html

QUESTION_DAYS_DELTA = 365 * 2


class RRFQuery:
    """Wrapper for Elasticsearch RRF (Reciprocal Rank Fusion) queries."""

    def __init__(self, query_dict):
        self.query_dict = query_dict

    def to_dict(self):
        return self.query_dict
FVH_HIGHLIGHT_OPTIONS = {
    "type": "fvh",
    # order highlighted fragments by their relevance:
    "order": "score",
    # only get one fragment per field:
    "number_of_fragments": 1,
    # split fragments at the end of sentences:
    "boundary_scanner": "sentence",
    # return fragments roughly this size:
    "fragment_size": SNIPPET_LENGTH,
    # add these tags before/after the highlighted sections:
    "pre_tags": [f"<{HIGHLIGHT_TAG}>"],
    "post_tags": [f"</{HIGHLIGHT_TAG}>"],
}
CATEGORY_EXACT_MAPPING = {
    "dict": {
        # `name` is lazy, using str() to force evaluation:
        slugify(str(name)): _id
        for _id, name in CATEGORIES
    },
    "field": "category",
}


def first_highlight(hit):
    highlight = getattr(hit.meta, "highlight", None)
    if highlight:
        # `highlight` is of type AttrDict, which is internal to elasticsearch_dsl
        # when converted to a dict, it's like:
        # `{ 'es_field_name' : ['highlight1', 'highlight2'], 'field2': ... }`
        # so here we're getting the first item in the first value in that dict:
        return next(iter(highlight.to_dict().values()))[0]
    return None


def strip_html(summary):
    return bleach.clean(
        summary,
        tags=[HIGHLIGHT_TAG],
        strip=True,
    )


def same_base_index(a, b):
    """Check if the base parts of two index names are the same."""
    return a.split("_")[:-1] == b.split("_")[:-1]


@dataclass
class QuestionSearch(SumoSearch):
    """Search over questions."""

    locale: str = "en-US"
    product: Product | None = None

    def get_index(self):
        return QuestionDocument.Index.read_alias

    def get_fields(self):
        return [
            # ^x boosts the score from that field by x amount
            f"question_title.{self.locale}^2",
            f"question_content.{self.locale}",
            f"answer_content.{self.locale}",
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

    def is_advanced_query(self, token=None):
        """Check if query uses advanced search syntax."""
        if token is None:
            if not self.query or not self.query.strip():
                return False

            # Quick check for field operators (field:value syntax)
            if ":" in self.query:
                # Check if it's a field operator by looking for known field prefixes
                for field in ["title", "content", "question", "answer"]:
                    if f"{field}:" in self.query:
                        return True

            # Check for quoted strings (exact match syntax)
            if '"' in self.query:
                return True

            try:
                parsed = Parser(self.query)
                return self.is_advanced_query(parsed.parsed)
            except ParseException:
                return False

        # Advanced operators and tokens
        if isinstance(
            token, FieldOperator | AndOperator | OrOperator | NotOperator | RangeToken | ExactToken
        ):
            return True

        # SpaceOperator may contain advanced tokens
        if isinstance(token, SpaceOperator):
            return any(self.is_advanced_query(arg) for arg in token.arguments)

        return False

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
        """Build query - use hybrid RRF for simple queries, traditional for advanced."""
        if self.is_advanced_query():
            # Advanced query - use traditional parser
            return super().build_query()
        else:
            # Simple query - use hybrid RRF
            return self.build_hybrid_rrf_query()

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
        return [
            # ^x boosts the score from that field by x amount
            f"keywords.{self.locale}^8",
            f"title.{self.locale}^6",
            f"summary.{self.locale}^4",
            f"content.{self.locale}^2",
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

    def is_advanced_query(self, token=None):
        """Check if query uses advanced search syntax."""
        if token is None:
            if not self.query or not self.query.strip():
                return False

            # Quick check for field operators (field:value syntax)
            if ":" in self.query:
                # Check if it's a field operator by looking for known field prefixes
                for field in ["title", "content", "category"]:
                    if f"{field}:" in self.query:
                        return True

            # Check for quoted strings (exact match syntax)
            if '"' in self.query:
                return True

            try:
                parsed = Parser(self.query)
                return self.is_advanced_query(parsed.parsed)
            except ParseException:
                return False

        # Advanced operators and tokens
        if isinstance(
            token, FieldOperator | AndOperator | OrOperator | NotOperator | RangeToken | ExactToken
        ):
            return True

        # SpaceOperator may contain advanced tokens
        if isinstance(token, SpaceOperator):
            return any(self.is_advanced_query(arg) for arg in token.arguments)

        return False

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
        """Build query - use hybrid RRF for simple queries, traditional for advanced."""
        if self.is_advanced_query():
            # Advanced query - use traditional parser
            return super().build_query()
        else:
            # Simple query - use hybrid RRF
            return self.build_hybrid_rrf_query()

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
        return ["username", "name"]

    def get_highlight_fields_options(self):
        return []

    def get_filter(self):
        return DSLQ(
            "boosting",
            positive=self.build_query(),
            negative=DSLQ(
                "bool",
                must_not=DSLQ("terms", group_ids=self.group_ids),
            ),
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
    """Search over User Profiles."""

    thread_forum_id: int | None = None

    def get_index(self):
        return ForumDocument.Index.read_alias

    def get_fields(self):
        return ["thread_title", "content"]

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

    def get_filter(self):
        # Add default filters:
        filters = [
            # limit scope to the Forum index
            DSLQ("term", _index=self.get_index())
        ]

        if self.thread_forum_id:
            filters.append(DSLQ("term", thread_forum_id=self.thread_forum_id))
        return DSLQ("bool", filter=filters, must=self.build_query())

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
class CompoundSearch(SumoSearch):
    """Combine a number of SumoSearch classes into one search."""

    _children: list[SumoSearch] = dfield(default_factory=list, init=False)
    _parse_query: bool = True

    @property  # type: ignore
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

    def _from_children(self, name):
        """
        Get an attribute from all children.

        Will flatten lists.
        """
        value = []

        for child in self._children:
            attr = getattr(child, name)()
            if isinstance(attr, list):
                # if the attribute's value is itself a list, unpack it
                value = [*value, *attr]
            else:
                value.append(attr)
        return value

    def get_index(self):
        return ",".join(self._from_children("get_index"))

    def get_fields(self):
        return self._from_children("get_fields")

    def get_highlight_fields_options(self):
        return self._from_children("get_highlight_fields_options")

    def get_filter(self):
        # `should` with `minimum_should_match=1` acts like an OR filter
        return DSLQ("bool", should=self._from_children("get_filter"), minimum_should_match=1)

    def make_result(self, hit):
        index = hit.meta.index
        for child in self._children:
            if same_base_index(index, child.get_index()):
                return child.make_result(hit)
