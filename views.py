from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect
from .models import Repos, Commits, Blurbs

def index(request):
    repos = Repos.objects.order_by('-updated_at')
    repos_ = []
    for repo in repos:
        commits = Commits.objects.filter(repo=repo.name)
        try:
            blurb = Blurbs.objects.get(repo_id=repo.id).blurb
        except Blurbs.DoesNotExist:   # what is the right way...?
            blurb = ''
        repos_.append(
            (repo, commits, blurb)
        )

    context = {
        'repos_list': repos_,
    }
    return render(request, 'gitbored/index.html', context)
