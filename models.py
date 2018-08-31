from django.db import models

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
    #repo = models.ForeignKey('Repos', on_delete=models.DO_NOTHING, db_column='repo', primary_key=True)
    repo = models.TextField()
    sha = models.TextField(unique=True, primary_key=True)
    commit_message = models.TextField(blank=True, null=True)
    author_login = models.TextField(blank=True, null=True)
    html_url = models.TextField(blank=True, null=True)

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
        
