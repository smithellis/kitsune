from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import field as dfield
from datetime import datetime
from enum import Enum
from typing import Self, overload

from dateutil import parser
from django.conf import settings
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger
from django.core.paginator import Paginator as DjPaginator
from django.utils import timezone
from django.utils.translation import gettext as _
from elasticsearch import NotFoundError, RequestError
from elasticsearch.dsl import Document as DSLDocument
from elasticsearch.dsl import InnerDoc, MetaField, field
from elasticsearch.dsl import Q as DSLQ
from elasticsearch.dsl import Search as DSLSearch
from elasticsearch.dsl.utils import AttrDict
from pyparsing import ParseException

from kitsune.search.config import (
    DEFAULT_ES_CONNECTION,
    DEFAULT_ES_REFRESH_INTERVAL,
    UPDATE_RETRY_ON_CONFLICT,
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


class QueryStrategy(Enum):
    """Query strategies for different types of search queries."""

    HYBRID_RELAXED = "hybrid_relaxed"      # Short queries, conversational - favor semantic
    HYBRID_BALANCED = "hybrid_balanced"    # Medium queries, general - balanced approach
    HYBRID_STRICT = "hybrid_strict"        # Technical queries - favor precision
    ADVANCED_STRUCTURED = "advanced"       # Field operators, complex syntax - structured search
    TRADITIONAL_FALLBACK = "traditional"   # Error recovery - traditional search


class QueryIntent(Enum):
    """Detected intent of the search query."""

    NAVIGATIONAL = "navigational"  # Looking for specific pages/features
    INFORMATIONAL = "informational"  # How-to questions, explanations
    TRANSACTIONAL = "transactional"  # Problem-solving, troubleshooting
    UNKNOWN = "unknown"  # Cannot determine intent


class QueryClassifier:
    """Classifies queries and determines optimal search strategy."""

    @staticmethod
    def classify_query(query: str) -> tuple[QueryStrategy, QueryIntent, float]:
        """
        Classify a query and return the optimal strategy, intent, and confidence score.

        Returns:
            tuple: (strategy, intent, confidence_score)
        """
        if not query or not query.strip():
            return QueryStrategy.TRADITIONAL_FALLBACK, QueryIntent.UNKNOWN, 1.0

        query_lower = query.lower().strip()
        terms = query_lower.split()

        # Detect advanced syntax first
        if QueryClassifier._has_advanced_syntax(query):
            return QueryStrategy.ADVANCED_STRUCTURED, QueryClassifier._detect_intent(query), 0.95

        # Classify based on query characteristics
        intent = QueryClassifier._detect_intent(query)
        strategy = QueryClassifier._select_strategy(query, terms, intent)

        # Calculate confidence based on classification factors
        confidence = QueryClassifier._calculate_confidence(query, terms, intent)

        return strategy, intent, confidence

    @staticmethod
    def _has_advanced_syntax(query: str) -> bool:
        """Check if query uses advanced search syntax."""
        # Field operators
        if ":" in query:
            return True

        # Quoted strings
        if '"' in query:
            return True

        # Try parsing to detect advanced operators
        try:
            parsed = Parser(query)
            return QueryClassifier._has_advanced_tokens(parsed.parsed)
        except ParseException:
            return False

    @staticmethod
    def _has_advanced_tokens(token) -> bool:
        """Check if parsed tokens contain advanced operators."""
        if isinstance(token, FieldOperator | AndOperator | OrOperator | NotOperator | RangeToken | ExactToken):
            return True
        if isinstance(token, SpaceOperator):
            return any(QueryClassifier._has_advanced_tokens(arg) for arg in token.arguments)
        return False

    @staticmethod
    def _detect_intent(query: str) -> QueryIntent:
        """Detect the intent of the query."""
        query_lower = query.lower()

        # Informational keywords (highest priority)
        informational_keywords = [
            'how', 'why', 'what', 'when', 'where', 'which', 'who',
            'guide', 'tutorial', 'help', 'support', 'documentation',
            'manual', 'instructions', 'steps', 'process', 'explain'
        ]
        if any(keyword in query_lower for keyword in informational_keywords):
            return QueryIntent.INFORMATIONAL

        # Navigational keywords
        navigational_keywords = [
            'download', 'install', 'update', 'settings', 'preferences',
            'menu', 'button', 'tab', 'page', 'window', 'toolbar',
            'extension', 'addon', 'plugin', 'theme', 'login', 'account'
        ]
        if any(keyword in query_lower for keyword in navigational_keywords):
            return QueryIntent.NAVIGATIONAL

        # Transactional keywords
        transactional_keywords = [
            'fix', 'problem', 'issue', 'error', 'crash', 'slow',
            'not working', 'broken', 'won\'t', 'can\'t', 'failed',
            'troubleshoot', 'solution', 'resolve', 'repair'
        ]
        if any(keyword in query_lower for keyword in transactional_keywords):
            return QueryIntent.TRANSACTIONAL

        # Default based on query length
        term_count = len(query.split())
        if term_count <= 2:
            return QueryIntent.NAVIGATIONAL  # Short queries likely navigational
        elif term_count <= 4:
            return QueryIntent.INFORMATIONAL  # Medium queries likely informational
        else:
            return QueryIntent.TRANSACTIONAL  # Long queries likely transactional

    @staticmethod
    def _select_strategy(query: str, terms: list[str], intent: QueryIntent) -> QueryStrategy:
        """Select the optimal search strategy based on query characteristics."""
        term_count = len(terms)

        # Single terms - relaxed hybrid (favor semantic discovery)
        if term_count == 1:
            return QueryStrategy.HYBRID_RELAXED

        # Short queries - balanced hybrid
        elif term_count <= 3:
            return QueryStrategy.HYBRID_BALANCED

        # Longer queries - depends on intent and characteristics
        else:
            # Technical queries need precision
            if QueryClassifier._is_technical_query(query):
                return QueryStrategy.HYBRID_STRICT

            # Conversational queries can be more relaxed
            if intent == QueryIntent.INFORMATIONAL:
                return QueryStrategy.HYBRID_RELAXED

            # Transactional queries need balance
            if intent == QueryIntent.TRANSACTIONAL:
                return QueryStrategy.HYBRID_BALANCED

            # Default to balanced for longer queries
            return QueryStrategy.HYBRID_BALANCED

    @staticmethod
    def _is_technical_query(query: str) -> bool:
        """Check if query appears to be technical."""
        technical_keywords = [
            'error', 'exception', 'crash', 'bug', 'code', 'script',
            'function', 'method', 'api', 'config', 'parameter', 'variable',
            'database', 'server', 'connection', 'timeout', 'memory'
        ]
        return any(keyword in query.lower() for keyword in technical_keywords)

    @staticmethod
    def _calculate_confidence(query: str, terms: list[str], intent: QueryIntent) -> float:
        """Calculate confidence score for the classification."""
        confidence = 0.5  # Base confidence

        # Higher confidence for clear intent signals
        if intent != QueryIntent.UNKNOWN:
            confidence += 0.2

        # Higher confidence for medium-length queries
        term_count = len(terms)
        if 2 <= term_count <= 4:
            confidence += 0.15
        elif term_count == 1:
            confidence += 0.1

        # Lower confidence for very long queries
        if term_count > 6:
            confidence -= 0.1

        return min(max(confidence, 0.1), 1.0)


class SumoDocument(DSLDocument):
    """Base class with common methods for all the different documents."""

    # Controls if a document should be indexed or updated in ES.
    #   True: An update action will be performed in ES.
    #   False: An index action will be performed in ES.
    update_document = False

    indexed_on = field.Date()

    class Meta:
        # ignore fields if they don't exist in the mapping
        dynamic = MetaField("false")

    def __init_subclass__(cls, **kwargs):
        """Automatically set up each subclass' Index attribute."""
        super().__init_subclass__(**kwargs)

        cls.Index.using = DEFAULT_ES_CONNECTION

        # this is here to ensure subclasses of subclasses of SumoDocument (e.g. AnswerDocument)
        # use the same name in their index as their parent class (e.g. QuestionDocument) since
        # they share an index with that parent
        immediate_parent = cls.__mro__[1]
        if immediate_parent is SumoDocument:
            name = cls.__name__
        else:
            name = immediate_parent.__name__

        cls.Index.base_name = f"{settings.ES_INDEX_PREFIX}_{name.lower()}"
        cls.Index.read_alias = f"{cls.Index.base_name}_read"
        cls.Index.write_alias = f"{cls.Index.base_name}_write"
        # Bump the refresh interval to 1 minute
        cls.Index.settings = {"refresh_interval": DEFAULT_ES_REFRESH_INTERVAL}

        # this is the attribute elastic-dsl actually uses to determine which index
        # to query. we override the .search() method to get that to use the read
        # alias:
        cls.Index.name = cls.Index.write_alias

    @classmethod
    def search(cls, **kwargs):
        """
        Create an `elasticsearch_dsl.Search` instance that will search over this `Document`.

        If no `index` kwarg is supplied, use the Document's Index's `read_alias`.
        """
        if "index" not in kwargs:
            kwargs["index"] = cls.Index.read_alias
        return super().search(**kwargs)

    @classmethod
    def migrate_writes(cls, timestamp=None):
        """Create a new index for this document, and point the write alias at it."""
        timestamp = timestamp or datetime.now(tz=timezone.utc)
        name = f"{cls.Index.base_name}_{timestamp.strftime('%Y%m%d%H%M%S')}"
        cls.init(index=name)
        cls._update_alias(cls.Index.write_alias, name)

    @classmethod
    def migrate_reads(cls):
        """Point the read alias at the same index as the write alias."""
        cls._update_alias(cls.Index.read_alias, cls.alias_points_at(cls.Index.write_alias))

    @classmethod
    def _update_alias(cls, alias, new_index):
        client = es_client()
        old_index = cls.alias_points_at(alias)
        if not old_index:
            client.indices.put_alias(index=new_index, name=alias)
        else:
            client.indices.update_aliases(
                actions=[
                    {"remove": {"index": old_index, "alias": alias}},
                    {"add": {"index": new_index, "alias": alias}},
                ]
            )

    @classmethod
    def alias_points_at(cls, alias):
        """Returns the index `alias` points at."""
        try:
            aliased_indices = list(es_client().indices.get_alias(name=alias))
        except NotFoundError:
            aliased_indices = []

        if len(aliased_indices) > 1:
            raise RuntimeError(
                f"{alias} points at more than one index, something has gone very wrong"
            )

        return aliased_indices[0] if aliased_indices else None

    @classmethod
    def prepare(cls, instance, parent_id=None, **kwargs):
        """Prepare an object given a model instance.

        parent_id: Supplying a parent_id will ignore any fields which aren't a
        SumoLocaleAware field, and set the meta.id value to the parent_id one.
        """

        obj = cls()

        doc_mapping = obj._doc_type.mapping
        fields = list(doc_mapping)
        fields.remove("indexed_on")
        # Loop through the fields of each object and set the right values

        # check if the instance is suitable for indexing
        # the prepare method of each Document Type can mark an object
        # not suitable for indexing based on criteria defined on each said method
        if not hasattr(instance, "es_discard_doc"):
            for f in fields:
                # This will allow child classes to have their own methods
                # in the form of prepare_field
                prepare_method = getattr(obj, f"prepare_{f}", None)
                value = obj.get_field_value(f, instance, prepare_method)

                # Assign values to each field.
                field_type = doc_mapping.resolve_field(f)
                if isinstance(field_type, field.Object) and not (
                    isinstance(value, InnerDoc)
                    or (isinstance(value, list) and isinstance((value or [None])[0], InnerDoc))
                ):
                    # if the field is an Object but the value isn't an InnerDoc
                    # or a list containing an InnerDoc then we're dealing with locales
                    locale = obj.prepare_locale(instance)
                    # Check specifically against None, False is a valid value
                    if locale and (value is not None):
                        obj[f] = {locale: value}

                else:
                    if (
                        isinstance(field_type, field.Date)
                        and isinstance(value, datetime)
                        and timezone.is_naive(value)
                    ):
                        value = timezone.make_aware(value).astimezone(timezone.utc)

                    if not parent_id:
                        setattr(obj, f, value)
        else:
            obj.es_discard_doc = "unindex_me"

        obj.indexed_on = datetime.now(timezone.utc)
        obj.meta.id = instance.pk
        if parent_id:
            obj.meta.id = parent_id

        return obj

    def to_action(self, action=None, is_bulk=False, **kwargs):
        """Method to construct the data for save, delete, update operations.

        Useful for bulk operations.
        """

        # If an object has a discard field then mark it for deletion if exists
        # This is the only case where this method ignores the passed arg action and
        # overrides it with a deletion. This can happen if the `prepare` method of each
        # document type has marked a document as not suitable for indexing
        if hasattr(self, "es_discard_doc"):
            # Let's try to delete anything that might exist in ES
            action = "delete"
            kwargs = {}

        # Default to index if no action is defined or if it's `save`
        # if we have a bulk update, we need to include the meta info
        # and return the data by calling the to_dict() method of DSL
        payload = self.to_dict(include_meta=is_bulk, skip_empty=False)

        # If we are in a test environment, mark refresh=True so that
        # documents will be updated/added directly in the index.
        if settings.TEST and not is_bulk:
            kwargs.update({"refresh": True})

        if not action or action == "index":
            return payload if is_bulk else self.save(**kwargs)
        elif action == "update":
            # add any additional args like doc_as_upsert
            payload.update(kwargs)

            if is_bulk:
                # this is a bit idiomatic b/c dsl does not have a wrapper around bulk operations
                # we need to return the payload and let elasticsearch-py bulk method deal with
                # the update
                payload["doc"] = payload["_source"]
                payload.update(
                    {
                        "_op_type": "update",
                        "retry_on_conflict": UPDATE_RETRY_ON_CONFLICT,
                    }
                )
                del payload["_source"]
                return payload
            return self.update(**payload)
        elif action == "delete":
            # if we have a bulk operation, drop the _source and mark the operation as deletion
            if is_bulk:
                payload.update({"_op_type": "delete"})
                del payload["_source"]
                return payload
            # This is a single document op, delete it
            kwargs.update({"ignore": [400, 404]})
            return self.delete(**kwargs)

    @classmethod
    def get_queryset(cls):
        """
        Return the manager for a document's model.
        This allows child classes to add optimizations like select_related or prefetch_related
        to improve indexing performance.
        """
        return cls.get_model()._default_manager

    def get_field_value(self, field, instance, prepare_method):
        """Allow child classes to define their own logic for getting field values."""
        if prepare_method is not None:
            return prepare_method(instance)
        return getattr(instance, field)

    def prepare_locale(self, instance):
        """Return the locale of an object if exists."""
        if instance.locale:
            return instance.locale
        return ""


class SumoSearchInterface(ABC):
    """Base interface class for search classes.

    Child classes should define values for the various abstract properties this
    class has, relevant to the documents the child class is searching over.
    """

    @abstractmethod
    def get_index(self):
        """The index or comma-seperated indices to search over."""
        ...

    @abstractmethod
    def get_fields(self):
        """An array of fields to search over."""
        ...

    def get_settings(self):
        """Configuration for advanced search."""
        ...

    @abstractmethod
    def get_highlight_fields_options(self):
        """An array of tuples of fields to highlight and their options."""
        ...

    @abstractmethod
    def get_filter(self):
        """A query which filters for all documents to be searched over."""
        ...

    @abstractmethod
    def build_query(self):
        """Build a query to search over a specific set of documents."""
        ...

    @abstractmethod
    def make_result(self, hit):
        """Takes a hit and returns a result dictionary."""
        ...

    @abstractmethod
    def run(self, *args, **kwargs) -> Self:
        """Perform search, placing the results in `self.results`, and the total
        number of results (across all pages) in `self.total`. Chainable."""
        ...


@dataclass
class BaseHybridSearch(SumoSearchInterface):
    """Base class for hybrid search implementations.

    Provides unified query strategy selection and smart filtering logic.
    Child classes should implement the abstract methods from SumoSearchInterface.
    """

    total: int = dfield(default=0, init=False)
    hits: list[AttrDict] = dfield(default_factory=list, init=False)
    results: list[dict] = dfield(default_factory=list, init=False)
    last_key: int | slice | None = dfield(default=None, init=False)

    query: str = ""
    default_operator: str = "AND"
    parse_query: bool = dfield(default=True, init=False)

    # Strategy and intent detection results
    _query_strategy: QueryStrategy | None = dfield(default=None, init=False)
    _query_intent: QueryIntent | None = dfield(default=None, init=False)
    _strategy_confidence: float = dfield(default=0.0, init=False)

    def __post_init__(self):
        """Initialize query strategy after dataclass initialization."""
        if self.query:
            self._query_strategy, self._query_intent, self._strategy_confidence = QueryClassifier.classify_query(self.query)

    def __len__(self):
        return self.total

    @overload
    def __getitem__(self, key: int) -> dict:
        pass

    @overload
    def __getitem__(self, key: slice) -> list[dict]:
        pass

    def __getitem__(self, key):
        if self.last_key is None or self.last_key != key:
            self.run(key=key)
        if isinstance(key, int):
            # if key is an int, then self.results will be a list containing a single result
            # return the result, rather than a 1-length list
            return self.results[0]
        return self.results

    def get_query_strategy(self) -> QueryStrategy:
        """Get the detected query strategy."""
        if self._query_strategy is None and self.query:
            self._query_strategy, self._query_intent, self._strategy_confidence = QueryClassifier.classify_query(self.query)
        return self._query_strategy or QueryStrategy.TRADITIONAL_FALLBACK

    def get_query_intent(self) -> QueryIntent:
        """Get the detected query intent."""
        if self._query_intent is None and self.query:
            self._query_strategy, self._query_intent, self._strategy_confidence = QueryClassifier.classify_query(self.query)
        return self._query_intent or QueryIntent.UNKNOWN

    def get_strategy_confidence(self) -> float:
        """Get the confidence score for the strategy classification."""
        if self._strategy_confidence == 0.0 and self.query:
            self._query_strategy, self._query_intent, self._strategy_confidence = QueryClassifier.classify_query(self.query)
        return self._strategy_confidence

    def should_require_text_match(self) -> bool:
        """Determine if semantic results should be filtered by lexical matches."""
        if not self.query:
            return True

        strategy = self.get_query_strategy()
        intent = self.get_query_intent()
        confidence = self.get_strategy_confidence()

        # Never require text match for advanced structured queries
        if strategy == QueryStrategy.ADVANCED_STRUCTURED:
            return False

        # Don't require text match for high-confidence short queries
        if confidence > 0.8 and len(self.query.split()) <= 2:
            return False

        # Don't require text match for informational queries with good confidence
        if intent == QueryIntent.INFORMATIONAL and confidence > 0.7:
            return False

        # Check if we have sufficient lexical results
        lexical_results = self._estimate_lexical_results()
        if lexical_results < 3:
            # If lexical search returns few results, allow semantic to help
            return False

        # Default: require text match for quality control
        return True

    def _estimate_lexical_results(self) -> int:
        """Estimate the number of lexical results for this query."""
        # This is a simplified estimation - in practice, you might do a quick count query
        # For now, we'll use heuristics based on query characteristics
        terms = self.query.strip().split()
        term_count = len(terms)

        # Very short queries likely have more results
        if term_count <= 2:
            return 10

        # Medium queries have moderate results
        if term_count <= 4:
            return 5

        # Long queries likely have fewer results
        return 2

    def build_smart_hybrid_query(self):
        """Build hybrid query using the detected strategy."""
        strategy = self.get_query_strategy()

        if strategy == QueryStrategy.ADVANCED_STRUCTURED:
            # Use traditional query for advanced syntax
            return self.build_traditional_query_with_filters(strict_matching=True)

        elif strategy in (QueryStrategy.HYBRID_RELAXED, QueryStrategy.HYBRID_BALANCED, QueryStrategy.HYBRID_STRICT):
            # Build hybrid RRF query with strategy-specific parameters
            return self._build_adaptive_rrf_query(strategy)

        else:
            # Fallback to traditional
            return self.build_traditional_query_with_filters(strict_matching=False)

    def _build_adaptive_rrf_query(self, strategy: QueryStrategy):
        """Build RRF query with parameters adapted to the strategy."""
        from kitsune.search.search import RRFQuery

        # Get base parameters
        rrf_params = self.get_dynamic_rrf_params()
        rrf_window_size = rrf_params["window_size"]
        rrf_rank_constant = rrf_params["rank_constant"]

        # Adjust parameters based on strategy
        if strategy == QueryStrategy.HYBRID_RELAXED:
            # Favor semantic more for relaxed queries
            rrf_rank_constant = max(rrf_rank_constant - 10, 40)
            rrf_window_size = min(rrf_window_size + 20, 100)
        elif strategy == QueryStrategy.HYBRID_STRICT:
            # Favor traditional more for strict queries
            rrf_rank_constant = min(rrf_rank_constant + 15, 90)
            rrf_window_size = max(rrf_window_size - 10, 30)

        # Build queries with smart filtering
        require_text_match = self.should_require_text_match()

        traditional_query = self.build_traditional_query_with_filters(
            strict_matching=(strategy == QueryStrategy.HYBRID_STRICT)
        )

        if require_text_match:
            semantic_base = self.build_semantic_query_with_filters()
            semantic_query = DSLQ(
                "bool",
                must=semantic_base,
                filter=traditional_query  # Require traditional match for semantic results
            )
        else:
            semantic_query = self.build_semantic_query_with_filters()

        rrf_query = {
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": traditional_query.to_dict()}},
                        {"standard": {"query": semantic_query.to_dict()}}
                    ],
                    "rank_window_size": rrf_window_size,
                    "rank_constant": rrf_rank_constant
                }
            }
        }
        return RRFQuery(rrf_query)

    def build_traditional_query_with_filters(self, strict_matching=False):
        """Build traditional query with filters applied."""
        # Check if this query uses field operators that need query_string
        has_field_operators = ":" in self.query and (
            any(f"{field}:" in self.query for field in self.get_advanced_query_field_names()) or
            any(f"{field.split('^')[0]}:" in self.query for field in self.get_fields())
        )

        if has_field_operators:
            # Use query_string for field operator syntax
            query = DSLQ(
                "query_string",
                query=self.query,
                fields=self.get_fields()
            )
        elif not strict_matching or not self.query or not self.query.strip():
            # Use parser-based query for advanced syntax or when not strict
            parsed = None
            if self.parse_query:
                try:
                    parsed = Parser(self.query)
                except ParseException:
                    pass
            if not parsed:
                parsed = TermToken(self.query)

            query = parsed.elastic_query({
                "fields": self.get_fields(),
                "settings": self.get_settings(),
            })
        else:
            # Use strict matching based on query length and strategy
            query_terms = self.query.strip().split()
            term_count = len(query_terms)

            strategy = self.get_query_strategy()

            if term_count == 1:
                # Single term - use normal parser-based matching
                return self.build_traditional_query_with_filters(strict_matching=False)
            elif term_count == 2:
                # 2 terms - require 100% match (AND operator)
                query = DSLQ(
                    "simple_query_string",
                    query=self.query,
                    fields=self.get_fields(),
                    default_operator="AND",
                    flags="PHRASE"
                )
            elif term_count == 3:
                # 3 terms - require 66% match (minimum 2 out of 3)
                query = DSLQ(
                    "simple_query_string",
                    query=self.query,
                    fields=self.get_fields(),
                    minimum_should_match="66%",
                    flags="PHRASE"
                )
            elif term_count == 4:
                # 4 terms - require 50% match (minimum 2 out of 4)
                query = DSLQ(
                    "simple_query_string",
                    query=self.query,
                    fields=self.get_fields(),
                    minimum_should_match="50%",
                    flags="PHRASE"
                )
            # 5+ terms - adjust strictness based on query type and strategy
            else:
                intent = self.get_query_intent()
                is_conversational = intent == QueryIntent.INFORMATIONAL
                is_technical = strategy == QueryStrategy.HYBRID_STRICT

                if is_conversational and not is_technical:
                    # Conversational queries: be more lenient
                    query = DSLQ(
                        "simple_query_string",
                        query=self.query,
                        fields=self.get_fields(),
                        minimum_should_match="30%",
                        # No PHRASE flag - allow terms to match in any order
                    )
                elif is_technical:
                    # Technical queries: maintain stricter matching
                    query = DSLQ(
                        "simple_query_string",
                        query=self.query,
                        fields=self.get_fields(),
                        minimum_should_match="40%",
                        flags="PHRASE"  # Require phrase matching for technical precision
                    )
                else:
                    # Balanced approach for other long queries
                    query = DSLQ(
                        "simple_query_string",
                        query=self.query,
                        fields=self.get_fields(),
                        minimum_should_match="35%",
                        flags="PHRASE"
                    )

        return self._apply_filters_to_query(query)

    def build_semantic_query_with_filters(self):
        """Build semantic query with filters applied."""
        semantic_fields = self.get_semantic_fields()
        if not semantic_fields:
            return DSLQ("match_none")

        semantic_queries = [
            DSLQ("semantic", field=field_name, query=self.query)
            for field_name in semantic_fields
        ]

        # Combine semantic queries
        combined_semantic = DSLQ("bool", should=semantic_queries, minimum_should_match=1)

        # Apply base filters
        return self._apply_filters_to_query(combined_semantic)

    def _apply_filters_to_query(self, query):
        """Apply base filters to a query."""
        if hasattr(self, 'get_base_filters'):
            return DSLQ("bool", filter=self.get_base_filters(), must=query)
        return query

    def get_semantic_fields(self):
        """Return list of semantic fields for this search. Override in subclasses."""
        return []

    def get_advanced_query_field_names(self):
        """Return list of field names that can be used in advanced queries."""
        return []

    def get_dynamic_rrf_params(self):
        """Tune RRF parameters based on query characteristics."""
        if not self.query:
            return {"window_size": 50, "rank_constant": 60}

        terms = self.query.strip().split()
        intent = self.get_query_intent()
        strategy = self.get_query_strategy()

        # Base parameters
        params = {"window_size": 50, "rank_constant": 60}

        # Analyze query characteristics
        is_conversational = intent == QueryIntent.INFORMATIONAL
        is_technical = strategy == QueryStrategy.HYBRID_STRICT

        # Adjust based on query length and characteristics
        if len(terms) == 1:
            # Single term - favor semantic more for broader matching
            params.update({"window_size": 75, "rank_constant": 50})
        elif len(terms) == 2:
            # Two terms - balanced approach
            params.update({"window_size": 60, "rank_constant": 55})
        elif len(terms) <= 4:
            # Short query - moderate semantic preference
            params.update({"window_size": 50, "rank_constant": 60})
        # Long query - nuanced approach based on query type
        elif is_conversational and not is_technical:
            # Conversational long queries - favor semantic
            params.update({"window_size": 60, "rank_constant": 50})
        elif is_technical:
            # Technical long queries - favor traditional precision
            params.update({"window_size": 40, "rank_constant": 75})
        else:
            # Neutral long queries - balanced approach
            params.update({"window_size": 45, "rank_constant": 65})

        # Adjust based on intent
        if intent == QueryIntent.NAVIGATIONAL:
            # Navigation needs precision - favor traditional
            params["rank_constant"] = min(params["rank_constant"] + 10, 80)
        elif intent == QueryIntent.INFORMATIONAL:
            # Information queries benefit from semantic understanding
            params["rank_constant"] = max(params["rank_constant"] - 5, 40)
        elif intent == QueryIntent.TRANSACTIONAL:
            # Problem-solving needs both precision and semantic context
            params["window_size"] = min(params["window_size"] + 10, 80)

        return params


    def get_enhanced_fields(self):
        """Return enhanced field boosts based on query strategy and intent."""
        strategy = self.get_query_strategy()
        intent = self.get_query_intent()
        confidence = self.get_strategy_confidence()

        # Base boost values for all field types
        base_boosts = {
            "title_boost": 3.0,
            "content_boost": 1.0,
            "summary_boost": 1.5,
            "keywords_boost": 2.5,  # Keywords are important for search
        }

        # Adjust boosts based on strategy
        if strategy == QueryStrategy.HYBRID_RELAXED:
            # Favor semantic - boost content and summary
            base_boosts.update({
                "title_boost": 2.5,
                "content_boost": 1.2,
                "summary_boost": 1.8,
                "keywords_boost": 2.2,
            })
        elif strategy == QueryStrategy.HYBRID_BALANCED:
            # Balanced approach
            base_boosts.update({
                "title_boost": 3.0,
                "content_boost": 1.0,
                "summary_boost": 1.5,
                "keywords_boost": 2.5,
            })
        elif strategy == QueryStrategy.HYBRID_STRICT:
            # Favor precision - boost title and keywords
            base_boosts.update({
                "title_boost": 3.5,
                "content_boost": 1.3,
                "summary_boost": 1.2,
                "keywords_boost": 3.0,
            })
        elif strategy == QueryStrategy.ADVANCED_STRUCTURED:
            # Structured queries - maintain original boosts
            base_boosts.update({
                "title_boost": 3.0,
                "content_boost": 1.0,
                "summary_boost": 1.5,
                "keywords_boost": 2.5,
            })

        # Adjust based on intent
        if intent == QueryIntent.NAVIGATIONAL:
            # Navigation favors titles and keywords
            base_boosts["title_boost"] *= 1.2
            base_boosts["keywords_boost"] *= 1.1
        elif intent == QueryIntent.INFORMATIONAL:
            # Information queries favor content
            base_boosts["content_boost"] *= 1.1
            base_boosts["summary_boost"] *= 1.1
        elif intent == QueryIntent.TRANSACTIONAL:
            # Transactional queries need balanced precision
            base_boosts["title_boost"] *= 1.1
            base_boosts["keywords_boost"] *= 1.05
            base_boosts["content_boost"] *= 1.05

        # Scale boosts by confidence
        if confidence > 0.8:
            # High confidence - amplify boosts
            for key in base_boosts:
                base_boosts[key] *= 1.1
        elif confidence < 0.6:
            # Low confidence - reduce boosts to be more conservative
            for key in base_boosts:
                base_boosts[key] *= 0.9

        return base_boosts


    def _get_cache_key(self, key: int | slice) -> str:
        """Generate a unique cache key for this search query and parameters."""
        # Create a deterministic cache key based on search parameters
        key_parts = [
            self.__class__.__name__,
            self.query or "",
            str(self.locale) if hasattr(self, 'locale') else "",
            str(getattr(self, 'product', None)),
            str(key),
            str(self.get_query_strategy().value),
            str(self.get_query_intent().value),
            str(self.should_require_text_match()),
        ]

        # Add any additional search-specific parameters
        if hasattr(self, 'group_ids'):
            key_parts.append(str(sorted(self.group_ids or [])))
        if hasattr(self, 'thread_forum_id'):
            key_parts.append(str(self.thread_forum_id))

        cache_key = f"search:{':'.join(key_parts)}"
        # Ensure cache key is not too long (Django cache key limit is 250 chars)
        if len(cache_key) > 250:
            cache_key = f"search:{hash(cache_key)}"

        return cache_key

    def _should_cache_results(self) -> bool:
        """Determine if this search should be cached."""
        # Don't cache if caching is disabled
        if not getattr(settings, 'SEARCH_CACHE_ENABLED', True):
            return False

        # Don't cache advanced queries (they're less likely to be repeated)
        if self.is_advanced_query():
            return False

        # Don't cache very short queries (likely typos or test queries)
        if len(self.query.strip()) < 3:
            return False

        # Don't cache queries with very low confidence (likely to change)
        if self.get_strategy_confidence() < 0.6:
            return False

        # Cache everything else
        return True

    def _cache_search_results(self, key: int | slice, results: list, total: int) -> None:
        """Cache search results if caching is enabled."""
        if not self._should_cache_results():
            return

        cache_key = self._get_cache_key(key)
        cache_data = {
            'results': results,
            'total': total,
            'timestamp': timezone.now().isoformat(),
            'query': self.query,
            'strategy': self.get_query_strategy().value,
            'intent': self.get_query_intent().value,
        }

        # Cache for 15 minutes (configurable)
        cache_timeout = getattr(settings, 'SEARCH_CACHE_TIMEOUT', 900)
        cache.set(cache_key, cache_data, cache_timeout)

    def _get_cached_results(self, key: int | slice) -> dict | None:
        """Retrieve cached results if available and valid."""
        if not self._should_cache_results():
            return None

        cache_key = self._get_cache_key(key)
        cached_data = cache.get(cache_key)

        if cached_data:
            # Validate cache data structure
            required_keys = ['results', 'total', 'timestamp', 'query']
            if all(key in cached_data for key in required_keys):
                # Check if cache is not too old (additional safety check)
                cache_time = parser.parse(cached_data['timestamp'])
                cache_age = (timezone.now() - cache_time).total_seconds()
                max_age = getattr(settings, 'SEARCH_CACHE_MAX_AGE', 1800)  # 30 minutes

                if cache_age < max_age:
                    return cached_data

                if cache_age < max_age:
                    return cached_data

        return None

    def _track_search_metrics(self, execution_time: float, result_count: int, cache_hit: bool = False) -> None:
        """Track search performance metrics for monitoring and analytics."""
        if not getattr(settings, 'SEARCH_METRICS_ENABLED', True):
            return

        # Create metrics data
        metrics_data = {
            'timestamp': timezone.now().isoformat(),
            'query': self.query,
            'query_length': len(self.query) if self.query else 0,
            'strategy': self.get_query_strategy().value,
            'intent': self.get_query_intent().value,
            'confidence': self.get_strategy_confidence(),
            'execution_time': execution_time,
            'result_count': result_count,
            'cache_hit': cache_hit,
            'is_advanced': self.is_advanced_query(),
            'search_class': self.__class__.__name__,
        }

        # Store metrics in cache for batch processing (configurable)
        metrics_key = f"search_metrics:{timezone.now().strftime('%Y%m%d%H')}"
        existing_metrics = cache.get(metrics_key, [])
        existing_metrics.append(metrics_data)

        # Keep only recent metrics (last 100 per hour)
        if len(existing_metrics) > 100:
            existing_metrics = existing_metrics[-100:]

        cache.set(metrics_key, existing_metrics, 3600)  # 1 hour

    def get_search_metrics_summary(self) -> dict:
        """Get a summary of recent search metrics for monitoring."""
        metrics_key = f"search_metrics:{timezone.now().strftime('%Y%m%d%H')}"
        recent_metrics = cache.get(metrics_key, [])

        if not recent_metrics:
            return {
                'total_searches': 0,
                'avg_execution_time': 0,
                'cache_hit_rate': 0,
                'strategy_distribution': {},
                'intent_distribution': {},
            }

        total_searches = len(recent_metrics)
        total_execution_time = sum(m['execution_time'] for m in recent_metrics)
        cache_hits = sum(1 for m in recent_metrics if m['cache_hit'])

        strategy_counts: dict[str, int] = {}
        intent_counts: dict[str, int] = {}

        for metric in recent_metrics:
            strategy = metric['strategy']
            intent = metric['intent']
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

        return {
            'total_searches': total_searches,
            'avg_execution_time': total_execution_time / total_searches if total_searches > 0 else 0,
            'cache_hit_rate': cache_hits / total_searches if total_searches > 0 else 0,
            'strategy_distribution': strategy_counts,
            'intent_distribution': intent_counts,
        }

    def _get_ab_test_variant(self) -> str:
        """Determine which A/B test variant this search should use."""
        if not getattr(settings, 'SEARCH_AB_TESTING_ENABLED', False):
            return 'control'

        # Simple A/B test based on query hash for consistency
        query_hash = hash(self.query or "") % 100

        # 50/50 split between control and test variants
        if query_hash < 50:
            return 'control'
        else:
            return 'test'

    def _apply_ab_test_modifications(self, variant: str) -> None:
        """Apply modifications based on A/B test variant."""
        if variant == 'test':
            # Test variant: More aggressive semantic search
            # Reduce text match requirements for higher semantic benefit
            pass  # Modifications would be applied here

    def _track_ab_test_metrics(self, variant: str, execution_time: float, result_count: int) -> None:
        """Track A/B test performance metrics."""
        if not getattr(settings, 'SEARCH_AB_TESTING_ENABLED', False):
            return

        # Store A/B test data
        ab_key = f"ab_test:{variant}:{timezone.now().strftime('%Y%m%d')}"
        existing_data = cache.get(ab_key, [])
        existing_data.append({
            'timestamp': timezone.now().isoformat(),
            'query': self.query,
            'execution_time': execution_time,
            'result_count': result_count,
            'strategy': self.get_query_strategy().value,
            'intent': self.get_query_intent().value,
        })

        # Keep only recent data (last 500 per day per variant)
        if len(existing_data) > 500:
            existing_data = existing_data[-500:]

        cache.set(ab_key, existing_data, 86400)  # 24 hours

    def get_ab_test_summary(self) -> dict:
        """Get A/B test performance summary."""
        if not getattr(settings, 'SEARCH_AB_TESTING_ENABLED', False):
            return {'enabled': False}

        control_key = f"ab_test:control:{timezone.now().strftime('%Y%m%d')}"
        test_key = f"ab_test:test:{timezone.now().strftime('%Y%m%d')}"

        control_data = cache.get(control_key, [])
        test_data = cache.get(test_key, [])

        def calculate_metrics(data):
            if not data:
                return {'count': 0, 'avg_time': 0, 'avg_results': 0}
            return {
                'count': len(data),
                'avg_time': sum(d['execution_time'] for d in data) / len(data),
                'avg_results': sum(d['result_count'] for d in data) / len(data),
            }

        return {
            'enabled': True,
            'control': calculate_metrics(control_data),
            'test': calculate_metrics(test_data),
        }

    def is_advanced_query(self) -> bool:
        """Determine if this is an advanced/structured query that needs special handling."""
        if not self.query:
            return False

        strategy = self.get_query_strategy()

        # Advanced structured queries are those with field operators or complex syntax
        if strategy == QueryStrategy.ADVANCED_STRUCTURED:
            return True

        # Check for field operator syntax
        if ":" in self.query:
            # Look for field operators in the query
            advanced_fields = self.get_advanced_query_field_names()
            if advanced_fields:
                for field in advanced_fields:
                    if f"{field}:" in self.query:
                        return True

        # Check for other advanced syntax indicators
        advanced_indicators = [
            " AND ", " OR ", " NOT ",  # Boolean operators
            '"',  # Phrase queries
            "(", ")",  # Grouping
            "~", "^",  # Fuzzy/proximity operators
        ]

        for indicator in advanced_indicators:
            if indicator in self.query:
                return True

        return False


@dataclass
class SumoSearch(BaseHybridSearch):
    """Base class for search classes.

    Provides default implementations for core search functionality.
    Child classes should override specific methods for their document types.
    """

    # Note: All common functionality is inherited from BaseHybridSearch
    # This class provides default implementations for abstract methods

    def get_index(self):
        """Default index - should be overridden by child classes."""
        return "*"

    def get_fields(self):
        """Default fields - should be overridden by child classes."""
        return ["*"]

    def get_highlight_fields_options(self):
        """Default highlight options - should be overridden by child classes."""
        return []

    def get_filter(self):
        """Default filter - uses smart hybrid query."""
        return self.build_smart_hybrid_query()

    def build_query(self):
        """Default query builder - uses smart hybrid approach."""
        return self.build_smart_hybrid_query()

    def make_result(self, hit):
        """Default result maker - should be overridden by child classes."""
        return {
            "type": "document",
            "title": getattr(hit, "title", "Unknown"),
            "url": "#",
            "score": getattr(hit.meta, "score", 0),
            "search_summary": getattr(hit, "content", "")[:200],
        }

    def run(self, key: int | slice = slice(0, settings.SEARCH_RESULTS_PER_PAGE)) -> Self:
        """Perform search, placing the results in `self.results`, and the total
        number of results (across all pages) in `self.total`. Chainable."""

        start_time = timezone.now()

        # Determine A/B test variant
        ab_variant = self._get_ab_test_variant()
        self._apply_ab_test_modifications(ab_variant)

        # Check for cached results first
        cached_results = self._get_cached_results(key)
        if cached_results:
            self.results = cached_results['results']
            self.total = cached_results['total']
            self.hits = []
            self.last_key = key

            # Track cache hit metrics
            execution_time = (timezone.now() - start_time).total_seconds()
            self._track_search_metrics(execution_time, len(self.results), cache_hit=True)
            self._track_ab_test_metrics(ab_variant, execution_time, len(self.results))

            return self

        # Import here to avoid circular dependency
        from kitsune.search.search import RRFQuery

        # Get the filter/query
        filter_or_query = self.get_filter()

        # Check if it's an RRF query
        if isinstance(filter_or_query, RRFQuery):
            client = es_client()

            if isinstance(key, slice):
                start = key.start or 0
                stop = key.stop or settings.SEARCH_RESULTS_PER_PAGE
                size = stop - start
            else:
                start = key
                size = 1

            rrf_body = filter_or_query.to_dict()
            rrf_body["from"] = start
            rrf_body["size"] = size

            try:
                result = client.search(
                    index=self.get_index(),
                    body=rrf_body,
                    **settings.ES_SEARCH_PARAMS
                )
            except RequestError as e:
                if self.parse_query:
                    self.parse_query = False
                    return self.run(key)
                raise e

            # Process RRF results
            self.hits = []
            for hit in result["hits"]["hits"]:
                # Convert raw hit to AttrDict for compatibility
                attr_hit = AttrDict(hit["_source"])
                attr_hit.meta = AttrDict({
                    "id": hit["_id"],
                    "score": hit.get("_score", 0),
                    "index": hit["_index"]
                })
                self.hits.append(attr_hit)

            self.last_key = key
            # Get the actual total count from Elasticsearch response
            self.total = result["hits"]["total"]["value"]
            self.results = [self.make_result(hit) for hit in self.hits]
        else:
            # Traditional DSL search flow
            search = DSLSearch(using=es_client(), index=self.get_index()).params(
                **settings.ES_SEARCH_PARAMS
            )

            # add the search class' filter
            search = search.query(filter_or_query)
            # add highlights for the search class' highlight_fields
            for highlight_field, options in self.get_highlight_fields_options():
                search = search.highlight(highlight_field, **options)
            # slice search
            search = search[key]

            # perform search
            try:
                result = search.execute()
            except RequestError as e:
                if self.parse_query:
                    self.parse_query = False
                    return self.run(key)
                raise e

            self.hits = result.hits
            self.last_key = key

            self.total = self.hits.total.value  # type: ignore
            self.results = [self.make_result(hit) for hit in self.hits]

        # Cache the results for future use
        self._cache_search_results(key, self.results, self.total)

        # Track search performance metrics
        execution_time = (timezone.now() - start_time).total_seconds()
        self._track_search_metrics(execution_time, len(self.results), cache_hit=False)
        self._track_ab_test_metrics(ab_variant, execution_time, len(self.results))

        return self


class SumoSearchPaginator(DjPaginator):
    """
    Paginator for `SumoSearch` classes.

    Inherits from the default django paginator with a few adjustments. The default paginator
    attempts to call len() on the `object_list` first, and then query for an individual page.

    However, since elasticsearch returns the total number of results at the same time as querying
    for a single page, we can remove an extra query by only doing len() based operations after
    querying for a page.

    Because of this, the `orphans` argument won't work.
    """

    def __init__(self, object_list, per_page, orphans=0, allow_empty_first_page=True):
        super().__init__(object_list, per_page, orphans, allow_empty_first_page)
        # Store the actual total count from the search object
        self._actual_count = getattr(object_list, 'total', len(object_list)) if hasattr(object_list, 'total') else len(object_list)

    @property
    def count(self):
        """Return the total number of objects from the search results."""
        return self._actual_count

    def pre_validate_number(self, number):
        """
        Validate the given 1-based page number, without checking if the number is greater than
        the total number of pages.
        """
        try:
            if isinstance(number, float) and not number.is_integer():
                raise ValueError
            number = int(number)
        except (TypeError, ValueError):
            raise PageNotAnInteger(_("That page number is not an integer"))
        if number < 1:
            raise EmptyPage(_("That page number is less than 1"))
        return number

    def page(self, number):
        """Return a Page object for the given 1-based page number."""
        # first validate the number is an integer >= 1
        number = self.pre_validate_number(number)

        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        page = self._get_page(self.object_list[bottom:top], number, self)

        # now we have the total, do the full validation of the number
        self.validate_number(number)
        return page
