from django.db import models
from docutils import core


class Repos(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    owner_login = models.TextField(blank=True, null=True)
    updated_at = models.TextField(blank=True, null=True)
    html_url = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'repos'

    def __str__(self):
        return self.name


class Commits(models.Model):
    repo = models.TextField()
    sha = models.TextField(unique=True, primary_key=True)
    commit_message = models.TextField(blank=True, null=True)
    author_login = models.TextField(blank=True, null=True)
    html_url = models.TextField(blank=True, null=True)

    @property
    def message_html(self):
        parts = core.publish_parts(
            source=self.commit_message,
            writer_name='html')
        return parts['body_pre_docinfo'] + parts['fragment']

    class Meta:
        managed = False
        db_table = 'commits'


class Blurbs(models.Model):
    repo_id = models.OneToOneField(
        Repos,
        on_delete=models.DO_NOTHING,
        primary_key=True,
    )
    blurb = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'blurbs'
