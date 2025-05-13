# Elasticsearch 8 Upgrade Steps for `kitsune/search`

This document summarizes the changes made to the `kitsune/search` app to ensure compatibility with Elasticsearch 8.x.

## 1. Authentication and Client Changes
- **`http_auth` → `basic_auth`:**
  - In `es_utils.py`, the Elasticsearch client now uses the `basic_auth` parameter instead of the deprecated `http_auth`.
  - Example: `Elasticsearch(basic_auth=settings.ES_HTTP_AUTH)`

## 2. Analyzer and Filter Definitions
- **Removed `updateable` Parameter:**
  - The `updateable` parameter for analyzers/filters is no longer supported in ES 8. It was removed from `_create_synonym_graph_filter` in `es_utils.py`.

## 3. Refresh Parameter
- **`refresh` Should Be a String:**
  - The `refresh` parameter is now a string (e.g., `"true"`, `"wait_for"`) instead of a boolean. This was updated in both `es_utils.py` and `base.py` for all relevant ES operations.

## 4. Alias and Index Management
- **Alias API Usage Updated:**
  - In `base.py`, alias management now uses `update_aliases` with the correct action structure, as required by ES 8.
  - Example:
    ```python
    client.indices.update_aliases({
        "actions": [
            {"add": {"index": new_index, "alias": alias}},
        ]
    })
    ```

## 5. Management Commands
- **`reload_search_analyzers` API:**
  - In `management/commands/es_init.py`, the `reload_search_analyzers` API now expects a list of indices: `client.indices.reload_search_analyzers(index=[index])`.

## 6. Field and Analyzer Definitions
- **No Deprecated Field Options Found:**
  - All field and analyzer definitions in `fields.py` and `documents.py` were reviewed and are compatible with ES 8.

## 7. Exception Handling
- **Exception Imports:**
  - Exception imports were checked and are compatible with ES 8. No changes were needed.

## 8. General Review
- All usages of the Elasticsearch Python client and DSL were reviewed for deprecated or removed features.
- No n+1 queries were introduced or found in ORM usage.

## 9. Environment and Settings Updates
- **ES_URLS Default Updated:**
  - The default for `ES_URLS` in `settings.py` now includes the scheme: `http://elasticsearch:9200`.
  - Ensure your `.env` file and deployment environment use URLs with a scheme (e.g., `http://elasticsearch:9200`).
  - **This change has been made in your `.env` file as part of the Elasticsearch 8 upgrade process.**
- **Other ES Settings Reviewed:**
  - `ES_CLOUD_ID` and `ES_HTTP_AUTH` were reviewed and are compatible with Elasticsearch 8. No changes needed beyond ensuring correct values in your environment.

## 10. Bulk Indexing Client Arguments
- **Removed `initial_backoff` and `max_retries` from `es_client()` call:**
  - In `es_utils.py`, the `index_objects_bulk` function no longer passes `initial_backoff` and `max_retries` to the `Elasticsearch` client constructor, as these are not valid arguments in the Elasticsearch 8.x Python client. Retry logic should be handled at the bulk helper level if needed.

---

**After these changes, the `kitsune/search` app should be compatible with Elasticsearch 8.x.**

**Recommended:**
- Run the full test suite using the Django test runner to ensure all search functionality works as expected.
- Review the official [Elasticsearch 8 migration guide](https://www.elastic.co/guide/en/elasticsearch/reference/current/breaking-changes-8.0.html) for any additional changes relevant to your deployment.

# Elasticsearch 8.17 Upgrade: Test Suite Changes

## Summary of Changes in `kitsune/search/tests`

1. **Test Base Class Refactor**
   - The base test class `Elastic7TestCase` was renamed and refactored to `ElasticTestCase`.
   - The new class is version-agnostic and compatible with Elasticsearch 8.17.
   - All test files and signal tests that previously used `Elastic7TestCase` now use `ElasticTestCase`.

2. **Test Imports and Inheritance**
   - All imports and class definitions in the test suite were updated to use `ElasticTestCase`.

3. **Direct Elasticsearch API Usage**
   - All usages of Elasticsearch helpers, exceptions, and DSL queries in the tests were reviewed for compatibility with Elasticsearch 8.17.
   - No breaking changes were found in the test code, but all usages should be re-verified if the Elasticsearch Python client is upgraded.

4. **Test Logic and Document Handling**
   - Test logic for document indexing, updating, and deletion was reviewed to ensure compatibility with Elasticsearch 8.17.
   - No deprecated or removed APIs were found in the test code, but document meta and index handling should be re-verified after the upgrade.

5. **Signal and Document Tests**
   - Signal-based tests and document retrieval logic were updated to use the new base class and checked for ES8 compatibility.

## Next Steps
- Run the Django test suite using the Django test runner after upgrading to Elasticsearch 8.17.
- Fix any failing tests that may arise due to changes in Elasticsearch 8 behavior or APIs.
- Review any custom query logic or DSL usage for subtle changes in query syntax or results. 