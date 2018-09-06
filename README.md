
# gitbored


[`gitbored`](https://github.com/stnbu/gitbored) is a Django app that displays recent personal GitHub activity in a single fully-customizable, relocatable element, using the GitHub API.

A daemon that fetches and stores data locally is included.

You can see it in action here: https://unintuitive.org/pages/portfolio/

## Usage/Installation

### Installation

Install the package as you would any other python package

    pip install git+https://github.com/stnbu/gitbored.git

Requirements are _not_ handled automatically. You can install them with

```bash
pip install -r /path/to/gitbored/requirements.txt
```

### GitHub API authentication

If you have not already, sign up for and acquire a GitHub authentication token [here](https://github.com/settings/tokens). No write privileges of any kind are required.

The following scopes are sufficient:

```
repo:repo:status
repo:public_repo
user:read:user
```

Create a file at `~/.gitbored/API_AUTH` with contents of the form

```
github-username:api-token
```

(newlines and spaces are ignored)

Of course this file should be readable by the daemon but *security is up to you*. Be careful out there.

### Database changes

Prepare your database schema by running the Django migration tool.

```bash
manage.py makemigrations gitbored && python manage.py migrate
```

(Don't forget to backup your data first!)

### Run the daemon

The daemon _requires_ the presence of the `DJANGO_SETTINGS_MODULE` environment variable. Set it to the name of your site's setting's module (the same value that Django calculates/expects). Note that this is the _module's name_, not its path.

```bash
DJANGO_SETTINGS_MODULE='my_site.settings' gitbored-daemon --daemon /some/path
```

A PID file and a log file will be written to `/some/path` (syslog is used also but may not work on all platforms.) This directory need not be special in any way other than be writable by the user running `gitbored-daemon`.

You may wish to do something fancy like have the web server launch and manage this daemon, although this probably has some security implications. Contributions welcome.

### Modify your `views.py`

Import the function for getting the data (this reads from your database)

```python
from gitbored.views import get_grouped_commits
```

In your view, make the `repos_list` variable available (this variable name is hard-coded)

```python
def my_view(request):

    # ... your existing code, e.g. creating a `context` dict

    context['repos_list'] = get_grouped_commits()

    # ...

    return render(request, 'my_template.html', context)
```

### Modifying your template

In the `<head>` place a conditional to include the CSS

```html
	{% if repos_list %}
	<link rel="stylesheet" type="text/css" href="{% static 'gitbored/style.css' %}">
	{% endif %}
```

Include the `gitbored` template in the body of _your_ template where appropriate

```html
		{% if repos_list %}
		{# requires settings.TEMPLATES['APP_DIRS']==True #}
		{% include "gitbored/index.html" %}
		{% endif %}
```

Known issues, limitations
-------------------------

* _You_ must run the daemon. You may wish to use your OS's "supervisor" or similar.
* Records are never updated, so if a commit or a repository description changes for example, you'll need to go and delete the corresponding row yourself.
* The data stuff is not particularly efficient or smart. Big Data might be problematic.
* It's not very pluggable for a "plug-in" (contributions welcome!)
* You must set `myapp.settings.TEMPLATES['APP_DIRS']=True` or work out access to the template yourself.
* I've had all kinds of problems with syslog. It would be great if it "just worked".
* Automating some install stuff would be nice.
* The daemon requires the presence of the DJANGO_SETTINGS_MODULE environment variable. There might be better ways...
* Your contributions and improvements are conspicuous in their absence...
