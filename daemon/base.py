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

import daemon
import daemon.pidfile
from sqlalchemy import String, ForeignKey
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
    ('repo', ((String, ForeignKey('repos.name')), {'nullable': False})),
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
