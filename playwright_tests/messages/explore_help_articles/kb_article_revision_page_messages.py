class KBArticleRevision:
    KB_ARTICLE_REVISION_HEADER = "Review Revision of "
    UNREVIEWED_REVISION_HEADER = " Unreviewed Revision: "
    KB_ARTICLE_REVISION_NO_CURRENT_REV_TEXT = "This document does not have a current revision."
    KB_ARTICLE_REVISION_KEYWORD_HEADER = "Keywords:"
    KB_ARTICLE_REVISION_NO_STATUS = "No"
    KB_ARTICLE_REVISION_YES_STATUS = "Yes"
    KB_REVISION_CANNOT_DELETE_ONLY_REVISION_HEADER = ("Unable to delete only revision of the "
                                                      "document")
    KB_REVISION_CANNOT_DELETE_ONLY_REVISION_SUBHEADER = ("To delete the document, please notify "
                                                         "an admin.")
    KB_REVISION_PREVIEW = "/revision/"
    KB_EDIT_METADATA = "/edit/metadata"

    def get_kb_article_revision_details(self,
                                        revision_id: str,
                                        username: str,
                                        revision_comment: str) -> str:
        return (f"Reviewing Revision {revision_id} by {username}. Back to HistoryRevision Comment:"
                f" {revision_comment}")

    def get_unreviewed_revision_details(self,
                                        revision_id: str,
                                        username: str,
                                        revision_comment: str) -> str:
        return (f"Revision {revision_id} by {username}. Revision Comment: {revision_comment}Review"
                f" Revision {revision_id}")

    def get_article_warning_message(self, username: str):
        return (f"Warning: This page is also being edited by {username}! If you know what you are "
                f"doing, you can edit the document anyway.")
