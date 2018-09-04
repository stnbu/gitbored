# -*- mode: python; coding: utf-8 -*-
"""Fetch GitHub data via the GitHub API, write it to a local database (sqlite3). Features daemonization.
"""

import os
import sys
import time
import datetime
import pytz
import urllib
from requests.auth import HTTPBasicAuth
import logging
import logging.handlers
from dateutil.parser import parse as parse_dt
import requests
from requests.structures import CaseInsensitiveDict as HTTPHeaders

import daemon
import daemon.pidfile
from sqlalchemy import String
from mutils import simple_alchemy, rest

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


repos_schema = [
    ('name', String),
    ('description', String),
    ('owner_login', String),
    ('updated_at', String),
    ('html_url', String),
]

commits_schema = [
    ('repo', String),
    ('sha', ((String,), {'primary_key': True})),
    ('commit_message', String),
    ('author_login', String),
    ('html_url', String),
]


class GithubFeed(object):

    _session = None

    @classmethod
    def get_db_session(cls, dir_path):
        if cls._session is not None:
            return cls._session
        db_path = os.path.join(os.path.abspath(dir_path), 'db.sqlite3')
        cls._session = simple_alchemy.get_session(db_path)
        return cls._session

    def __init__(self, dir_path, api_auth):
        self.dir_path = os.path.abspath(dir_path)
        self.api_auth = api_auth
        self.repos = simple_alchemy.get_table_class('repos', schema=repos_schema)
        self.commits = simple_alchemy.get_table_class('commits', schema=commits_schema, include_id=False)

    def get_repos(self):
        username, api_token = self.api_auth
        auth = HTTPBasicAuth(username, api_token)
        location = '/users/{username}/repos'.format(username=username)
        url = urllib.parse.urlunparse(('https', 'api.github.com', location, '', '', ''))
        data = rest.get_json(url, auth=auth)
        public_repos = [r for r in data if not r['private']]
        repos = sorted(public_repos, key=lambda r: parse_dt(r['updated_at']), reverse=True)[:5]
        logger.debug('got {} repo records'.format(len(repos)))
        return repos

    def update_repos(self, repos):
        session = self.get_db_session(self.dir_path)
        updates = []
        for repo in repos:
            # ZZZ FIXME HACK... We want to update, not just skip existing 'repo'
            existing_repo = session.query(self.repos).filter_by(name=repo['name']).first()
            if existing_repo:
                continue
            repo_data = {}
            repo_data['name'] = repo['name']
            repo_data['description'] = repo['description']
            repo_data['owner_login'] = repo['owner']['login']
            repo_data['updated_at'] = repo['updated_at']
            repo_data['html_url'] = repo['html_url']
            updates.append(self.repos(**repo_data))
        session.add_all(updates)
        session.commit()

    def update_commits(self, repos):
        username, api_token = self.api_auth
        auth = HTTPBasicAuth(username, api_token)
        location = '/users/{username}/repos'.format(username=username)
        url = urllib.parse.urlunparse(('https', 'api.github.com', location, '', '', ''))
        now = datetime.datetime.now(tz=pytz.UTC)
        since = now - datetime.timedelta(days=365)
        since = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        session = self.get_db_session(self.dir_path)
        updates = []
        for repo in repos:
            location = '/repos/{username}/{repo}/commits'.format(username=username, repo=repo['name'])
            query = 'since={since}'.format(since=since)
            url = urllib.parse.urlunparse(('https', 'api.github.com', location, '', query, ''))
            commits = rest.get_json(url, auth=auth)
            logger.debug('got {} commits for repo {}'.format(len(commits), repo['name']))
            commit_data = {}
            # TODO: how are they ordered? Get the most recent...
            for commit in commits:
                existing_commit = session.query(self.commits).filter_by(sha=commit['sha']).first()
                if existing_commit:
                    continue
                commit_data['repo'] = repo['name']
                commit_data['sha'] = commit['sha']
                commit_data['commit_message'] = commit['commit']['message']
                commit_data['author_login'] = commit['author']['login']
                commit_data['html_url'] = commit['html_url']
                updates.append(self.commits(**commit_data))
        session.add_all(updates)
        session.commit()

    def worker(self):
        """Fetch and update github data every 600s
        """
        def exception_handler(type_, value, tb):
            logger.exception('uncaught exception on line {}; {}: {}'.format(
                tb.tb_lineno,
                type_.__name__,
                value,
            ))
            sys.__excepthook__(type_, value, tb)
        sys.excepthook = exception_handler

        fh = logging.FileHandler(os.path.join(self.dir_path, 'gitbored-daemon.log'))
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)

        while True:
            data = self.get_repos()
            self.update_repos(data)
            self.update_commits(data)
            logger.debug('sleeping 600s')
            time.sleep(600)


def main():
    """gitbored-daemon command line interface. Usage:

        gitbored-daemon [--daemon] <dir_path>

    <dir_path> should be writable and will contain both logs and the sqlite database file.
    """

    if len(sys.argv) == 1:
        # Are needs are not complex enough to justify argprse...
        print('usage: {} [--daemon] <directory>'.format(os.path.basename(__file__)))
        sys.exit(1)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)

    if '--daemon' in sys.argv:
        script_name, _, dir_path = sys.argv
        daemonize = True
    else:
        script_name, dir_path = sys.argv
        daemonize = False

    dir_path = os.path.abspath(dir_path)
    api_auth_file = os.path.join(os.path.expanduser('~/.gitbored'), 'API_AUTH')

    try:
        logger.debug('reading {}'.format(api_auth_file))
        api_auth = open(api_auth_file).read().strip().split(':')
    except FileNotFoundError:
        message = (
            'api_auth_file not found. Please create a file {} with the format:\n'
            '\n'
            '<github_user>:<github_api_key>\n'
            '\n'
            '(setting permissions appropriately)\n'.format(api_auth_file)
        )
        print(message)
        raise

    if daemonize:
        logger.debug('daemonizing')
        with daemon.DaemonContext(
                working_directory=dir_path,
                pidfile=daemon.pidfile.PIDLockFile(os.path.join(dir_path, 'pid')),
        ):
            gf = GithubFeed(dir_path, api_auth)
            gf.worker()
    else:
        logger.debug('not daemonizing')
        gf = GithubFeed(dir_path, api_auth)
        gf.worker()


class GitHubAPI(object):
    """A reasonably thin wrapper for the GitHub API. Stores important state stuff and makes life
    easier without imposing anything unreasonable.
    """

    scheme = 'https'
    domain = 'api.github.com'
    # last_get is meant to help comply with GitHub's API rate restrictions. the interval may be per-location.
    # either way, we do the conservative thing and make it class-wide
    last_get = None

    def __init__(self, auth):
        self.username, _ = auth
        self.auth = HTTPBasicAuth(*auth)
        self.cache = HTTPHeaders()
        logger.debug('created {}'.format(self))

    def __str__(self):
        return self.username

    def get_url(self, location, query=''):
        """Based on the supplied `location` and `query`, use `urlunparse` as a sort of "gauntlet" that we get a valid URL.
        """
        return urllib.parse.urlunparse((
            self.scheme,
            self.domain,
            location,
            '',
            query,
            ''
        ))

    def get(self, location, query=''):
        """Requiring the minimum information possible, "get" a "location", obey rate restrictions and use Etag.
        """
        if url not in self.cache:
            self.cache[url] = {}
        interval = self.cache[location].get('X-Poll-Interval', 60)
        now = time.time()
        if self.last_get is not None and now - self.last_get < interval:
            logger.debug('{} - {} < {} -- returning cache'.format(now, self.last_get, interval))
            return self.cache[location]['json']

        etag = self.cache[location].get('Etag', None)

        request_headers = HTTPHeaders()
        request_headers['If-None-Match'] = etag
        logger.debug('getting: {}'.format(url))
        response = requests.get(url, auth=self.auth, headers=request_headers)
        self.last_get = time.time()
        self.cache[location]['Etag'] = response.headers.get('Etag', None)
        if 'X-Poll-Interval' in response.headers:
            self.cache[location]['X-Poll-Interval'] = float(response.headers['X-Poll-Interval'])

        if response.status_code == 304:
            logger.debug('{}: {} -- returning cache'.format(response.status_code, response.reason))
            return self.cache[location]['json']

        if response.status_code != 200:
            message = '{}: {}'.format(response.status_code, response.reason)
            logger.exception(message)
            raise Exception(message)

        response_json = response.json()
        logger.debug('sucessfully got {} bytes'.format(len(response.content)))  # bytes?
        self.cache[location]['json'] = response_json
        return response_json


if __name__ == '__main__':

    from time import sleep
    api_auth_file = os.path.join(os.path.expanduser('~/.gitbored'), 'API_AUTH')
    auth = open(api_auth_file).read().strip().split(':')
    a = GitHubAPI(auth=auth)
    while True:
        url = a.get_url('/users/{}/events'.format(a.username))
        r = a.get(url)
        import ipdb
        ipdb.set_trace()
        time.sleep(61)
