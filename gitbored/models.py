from django.db import models
from docutils import core

class Commits(models.Model):
    
    repo = models.TextField(max_length=80)
    sha = models.TextField(max_length=42, unique=True)
    url = models.URLField()
    distinct = models.BooleanField()
    message = models.CharField(max_length=4095, blank=True, null=True)
    author_name = models.EmailField(blank=True, null=True)
    author_email = models.TextField(blank=True, null=True)
    author_login = models.TextField(max_length=60)
    author_html_url = models.URLField()
    html_url = models.URLField()
    author_date = models.TextField(max_length=30)
    
    @property
    def message_html(self):
        parts = core.publish_parts(
            source=self.message,
            writer_name='html')
        return parts['body_pre_docinfo'] + parts['fragment']

    class Meta:
        app_label = 'gitbored'

class Repos(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    owner_login = models.TextField(blank=True, null=True)
    updated_at = models.TextField(blank=True, null=True)
    html_url = models.TextField(blank=True, null=True)

    class Meta:
        app_label = 'gitbored'

    def __str__(self):
        return self.name

class Blurbs(models.Model):
    repo_id = models.OneToOneField(
        Repos,
        on_delete=models.DO_NOTHING,
        primary_key=True,
    )
    blurb = models.TextField(blank=True, null=True)

    class Meta:
        app_label = 'gitbored'
