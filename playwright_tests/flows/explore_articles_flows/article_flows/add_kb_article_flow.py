from playwright.sync_api import Page
from typing import Any
from playwright_tests.core.testutilities import TestUtilities
from playwright_tests.flows.explore_articles_flows.article_flows.add_kb_media_flow import \
    AddKbMediaFlow
from playwright_tests.messages.explore_help_articles.kb_article_page_messages import (
    KBArticlePageMessages)
from playwright_tests.pages.explore_help_articles.articles.kb_article_page import KBArticlePage
from playwright_tests.pages.explore_help_articles.articles.kb_article_review_revision_page import \
    KBArticleReviewRevisionPage
from playwright_tests.pages.explore_help_articles.articles.kb_article_show_history_page import \
    KBArticleShowHistoryPage
from playwright_tests.pages.explore_help_articles.articles.kb_edit_article_page import \
    EditKBArticlePage
from playwright_tests.pages.explore_help_articles.articles.submit_kb_article_page import (
    SubmitKBArticlePage)


class AddKbArticleFlow(TestUtilities, SubmitKBArticlePage, AddKbMediaFlow, KBArticlePage,
                       KBArticleShowHistoryPage, KBArticleReviewRevisionPage, EditKBArticlePage):

    def __init__(self, page: Page):
        super().__init__(page)

    def submit_simple_kb_article(self,
                                 article_title=None,
                                 article_slug=None,
                                 article_category=None,
                                 allow_discussion=True,
                                 allow_translations=True,
                                 selected_relevancy=True,
                                 selected_topics=True,
                                 search_summary=None,
                                 article_content=None,
                                 article_content_image='',
                                 submit_article=True,
                                 is_template=False,
                                 expiry_date=None,
                                 restricted_to_groups: list[str] = None,
                                 single_group="",
                                 approve_first_revision=False
                                 ) -> dict[str, Any]:
        self._page.goto(KBArticlePageMessages.CREATE_NEW_KB_ARTICLE_STAGE_URL)

        kb_article_test_data = super().kb_article_test_data

        if restricted_to_groups is not None:
            for group in restricted_to_groups:
                super()._add_and_select_restrict_visibility_group(group)
        if single_group != "":
            super()._add_and_select_restrict_visibility_group(single_group)

        if article_title is None:
            if is_template:
                kb_article_title = (kb_article_test_data["kb_template_title"] + self.
                                    generate_random_number(0, 5000))
            else:
                kb_article_title = (kb_article_test_data["kb_article_title"] + self.
                                    generate_random_number(0, 5000))
        else:
            kb_article_title = article_title

        if kb_article_title != "":
            super()._add_text_to_article_form_title_field(
                kb_article_title
            )

        if (article_slug is not None) and (article_slug != ""):
            kb_article_slug = article_slug
            super()._add_text_to_article_slug_field(kb_article_slug)

        if article_category is None:
            if is_template:
                article_category = kb_article_test_data["kb_template_category"]
                super()._select_category_option_by_text(
                    article_category
                )
            else:
                article_category = kb_article_test_data["category_options"]
                super()._select_category_option_by_text(article_category)
        else:
            super()._select_category_option_by_text(article_category)

        if not allow_translations:
            super()._check_allow_translations_checkbox()

        relevancy = kb_article_test_data["relevant_to_option"]
        if selected_relevancy is True:
            super()._click_on_a_relevant_to_option_checkbox(
                relevancy
            )

        article_topic = [
            kb_article_test_data["selected_parent_topic"],
            kb_article_test_data["selected_child_topic"]
        ]

        # Adding Article topic
        if selected_topics is True:
            super()._click_on_a_particular_parent_topic(
                article_topic[0]
            )
            super()._click_on_a_particular_child_topic_checkbox(
                article_topic[0],
                article_topic[1],
            )

        # Interacting with Allow Discussion checkbox
        if (allow_discussion is True) and (super(

        )._is_allow_discussion_on_article_checkbox_checked() is False):
            super()._check_allow_discussion_on_article_checkbox()
        elif (allow_discussion is False) and (super(

        )._is_allow_discussion_on_article_checkbox_checked() is True):
            super()._check_allow_discussion_on_article_checkbox()

        super()._add_text_to_related_documents_field(kb_article_test_data["related_documents"])
        super()._add_text_to_keywords_field(kb_article_test_data["keywords"])

        if search_summary is None:
            super()._add_text_to_search_result_summary_field(
                kb_article_test_data["search_result_summary"]
            )

        if not super()._is_content_textarea_displayed():
            super()._click_on_toggle_syntax_highlight_option()

        if article_content is None:
            super()._add_text_to_content_textarea(kb_article_test_data["article_content"])

        if article_content_image != '':
            super()._click_on_insert_media_button()
            super().add_media_to_kb_article(
                file_type="Image",
                file_name=article_content_image
            )

        if expiry_date is not None:
            super()._add_text_to_expiry_date_field(expiry_date)

        # We need to evaluate in order to fetch the slug field value
        slug = self._page.evaluate(
            'document.getElementById("id_slug").value'
        )

        first_revision_id = None
        if submit_article is True:
            # If title and slug are empty we are not reaching the description field.
            if ((article_title != '') and (article_slug != '') and (
                    search_summary is None) and (article_content is None)):
                super()._click_on_submit_for_review_button()
                super()._add_text_to_changes_description_field(
                    kb_article_test_data["changes_description"]
                )
                super()._click_on_changes_submit_button()
                try:
                    first_revision_id = super()._get_last_revision_id()
                except IndexError:
                    print("Chances are that the form was not submitted successfully")
            else:
                super()._click_on_submit_for_review_button()

        article_url = super()._get_article_page_url()

        if approve_first_revision:
            super()._click_on_show_history_option()
            self.approve_kb_revision(first_revision_id)

        return {"article_title": kb_article_title,
                "article_content": kb_article_test_data["article_content"],
                "article_content_html": kb_article_test_data['article_content_html_rendered'],
                "article_slug": slug,
                "article_child_topic": kb_article_test_data["selected_child_topic"],
                "article_category": article_category,
                "article_relevancy": relevancy,
                "article_topic": article_topic,
                "article_review_description": kb_article_test_data["changes_description"],
                "keyword": kb_article_test_data["keywords"],
                "search_results_summary": kb_article_test_data["search_result_summary"],
                "expiry_date": kb_article_test_data["expiry_date"],
                "article_url": article_url,
                "first_revision_id": first_revision_id
                }

    def approve_kb_revision(self, revision_id: str,
                            revision_needs_change=False,
                            ready_for_l10n=False):
        if (KBArticlePageMessages.KB_ARTICLE_HISTORY_URL_ENDPOINT not in
                super()._get_current_page_url()):
            super()._click_on_show_history_option()

        super()._click_on_review_revision(
            revision_id
        )
        super()._click_on_approve_revision_button()

        if revision_needs_change:
            if not super()._is_needs_change_checkbox_checked():
                super()._click_on_needs_change_checkbox()
            super()._add_text_to_needs_change_comment(
                super().kb_revision_test_data['needs_change_message']
            )

        if ready_for_l10n:
            super()._check_ready_for_localization_checkbox()

        super()._click_accept_revision_accept_button()

    def submit_new_kb_revision(self,
                               keywords=None,
                               search_result_summary=None,
                               content=None,
                               expiry_date=None,
                               changes_description=None,
                               is_admin=False,
                               approve_revision=False
                               ) -> dict[str, Any]:

        super()._click_on_edit_article_option()

        # Only admin accounts can update article keywords.
        if is_admin:
            # Keywords step.
            if keywords is None:
                super()._fill_edit_article_keywords_field(
                    self.kb_article_test_data['updated_keywords']
                )
            else:
                super()._fill_edit_article_keywords_field(keywords)

        # Search Result Summary step.
        if search_result_summary is None:
            super()._fill_edit_article_search_result_summary_field(
                self.kb_article_test_data['updated_search_result_summary']
            )
        else:
            super()._fill_edit_article_search_result_summary_field(search_result_summary)

        # Content step.
        if content is None:
            super()._fill_edit_article_content_field(
                self.kb_article_test_data['updated_article_content']
            )
        else:
            super()._fill_edit_article_content_field(content)

        # Expiry date step.
        if expiry_date is None:
            super()._fill_edit_article_expiry_date(
                self.kb_article_test_data['updated_expiry_date']
            )
        else:
            super()._fill_edit_article_expiry_date(expiry_date)

        # Submitting for preview steps
        super()._click_submit_for_review_button()

        if changes_description is None:
            super()._fill_edit_article_changes_panel_comment(
                self.kb_article_test_data['changes_description']
            )
        else:
            super()._fill_edit_article_changes_panel_comment(changes_description)

        super()._click_edit_article_changes_panel_submit_button()

        revision_id = super()._get_last_revision_id()

        if approve_revision:
            self.approve_kb_revision(revision_id)

        return {"revision_id": revision_id,
                "changes_description": self.kb_article_test_data['changes_description']
                }
