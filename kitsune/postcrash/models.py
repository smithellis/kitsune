from django.db import models

from kitsune.sumo.models import ModelBase
from kitsune.wiki.models import Document


class Signature(ModelBase):
    signature = models.CharField(max_length=255, db_index=True, unique=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)

    def __str__(self):
        return "<{}> {}".format(self.signature, self.document.title)

    def get_absolute_url(self):
        doc = self.document.get_absolute_url().lstrip("/")
        _, _, url = doc.partition("/")
        return "/" + url
