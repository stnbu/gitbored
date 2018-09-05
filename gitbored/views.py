from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect
from .models import Repos, Commits, Blurbs

def get_grouped_commits():
    """Return a list of the format

    `[(repo, blurb, [commit, commit, ...], ...]`

    Each list of commits belongs to the corresponding `repo` (and `blurb`). The tuples are then sorted by
    the date of the first commit in the list of commits.
    """
    # a temporary dict used to group commits by repo
    by_repo = {}
    for commit in Commits.objects.all():
        by_repo.setdefault(commit.repo, [])
        by_repo[commit.repo].append(commit)
    # the list that we will return
    grouped_commits = []
    for commits in by_repo.values():
        if not commits:
            continue
        repo = Repos.objects.filter(name=commits[0].repo).first()
        if repo:
            blurb = Blurbs.objects.filter(repo_id=repo.id).first()
        else:
            blurb = None
        # sort the commits by date
        commits = sorted(commits,
                         key=lambda c: c.author_date,
                         reverse=True)
        grouped_commits.append((repo, blurb, commits))

    # sort the tuples by the date of the first commit
    grouped_commits = sorted(grouped_commits,
                             key=lambda x: x[2][0].author_date,
                             reverse=True)
    print(len(grouped_commits))

    return grouped_commits


def index(request):
    context = {
        'repos_list': get_grouped_commits(),
    }
    return render(request, 'gitbored/index.html', context)
