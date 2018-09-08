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
import json
from collections import Mapping

import daemon
import daemon.pidfile

# this module "proxies" the django ORM using magic
import db
from gitbored import logger

class GithubFeed(object):

    def __init__(self, dir_path, api_auth):
        self.dir_path = os.path.abspath(dir_path)
        self.api_auth = api_auth
        self.gapi = GitHubAPI(api_auth)

    def update_repos(self):
        updates = []
        # FIXME TODO -- we need to figure out https://developer.github.com/v3/guides/traversing-with-pagination/
        # here and elsewhere.
        url = self.gapi.get_url('/users/{username}/repos'.format(username=self.gapi.username), query='per_page=100')
        repos = self.gapi.get(url)
        logger.debug('considering {} repos...'.format(len(repos)))
        for repo in repos:
            existing_repo = db.Repos.objects.filter(name=repo['name'])
            if existing_repo:
                logger.debug('  ...already have {}, skipping'.format(repo['name']))
                continue
            repo_data = {}
            repo_data['name'] = repo['name']
            repo_data['description'] = repo['description']
            repo_data['owner_login'] = repo['owner']['login']
            repo_data['updated_at'] = repo['updated_at']
            repo_data['html_url'] = repo['html_url']
            logger.debug('  ...updating {}'.format(repo['name']))
            updates.append(db.Repos(**repo_data))
        logger.debug('bulk-updating {} records into Repos'.format(len(updates)))
        db.Repos.objects.bulk_create(updates)

    def update_commits(self):
        url = self.gapi.get_url('/users/{}/events'.format(self.gapi.username))
        events = self.gapi.get(url)
        updates = []
        for event in events:
            if event['type'] != 'PushEvent':
                continue
            commits = event['payload'].get('commits', [])
            logger.debug('examining {} commits'.format(len(commits)))
            for commit in commits:
                commit = flatten(commit)
                if db.Commits.objects.filter(sha=commit['sha']):
                    logger.debug('we already have {}, skipping'.format(commit['sha']))
                    continue
                detail = self.gapi.get(commit['url'])
                commit.update(flatten(detail))
                fields = db.Commits._meta.get_fields()
                kwargs = {}
                logger.debug('calculating values for Commits fields...')
                for field in fields:
                    if field.name in commit:
                        logger.debug('  ...setting {}'.format(field.name))
                        kwargs[field.name] = commit[field.name]
                # FIXME -- unfortunate hack
                logger.info('  ...setting {} (with hack)'.format(field.name))
                repo = kwargs['url'].split('/')[5]
                kwargs['repo'] = repo
                updates.append(db.Commits(**kwargs))
        logger.debug('bulk-updating {} records into Commits'.format(len(updates)))
        db.Commits.objects.bulk_create(updates)

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
            logger.debug('updating GitHub info...')
            self.update_repos()
            self.update_commits()
            logger.debug('sleeping 600s')
            time.sleep(600)


class GitHubAPI(object):
    """A reasonably thin wrapper for the GitHub API. Stores important state stuff and makes life
    easier without imposing anything unreasonable.
    """

    scheme = 'https'
    domain = 'api.github.com'

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

    def get(self, url):
        """Requiring the minimum information possible, "get" a "url", obey rate restrictions and use Etag.
        """
        if url not in self.cache:
            self.cache[url] = {}
        interval = self.cache[url].get('X-Poll-Interval', 60)
        now = time.time()
        last_get = self.cache[url].get('last_get', 0)
        if last_get is not None and now - last_get < interval:
            logger.debug('{} - {} < {} -- returning cache'.format(now, last_get, interval))
            return self.cache[url]['json']

        etag = self.cache[url].get('Etag', None)

        request_headers = HTTPHeaders()
        request_headers['If-None-Match'] = etag
        logger.debug('getting: {}'.format(url))
        response = requests.get(url, auth=self.auth, headers=request_headers)
        self.cache[url]['last_get'] = time.time()
        self.cache[url]['Etag'] = response.headers.get('Etag', None)
        if 'X-Poll-Interval' in response.headers:
            self.cache[url]['X-Poll-Interval'] = float(response.headers['X-Poll-Interval'])

        if response.status_code == 304:
            logger.debug('{}: {} -- returning cache'.format(response.status_code, response.reason))
            return self.cache[url]['json']

        if response.status_code != 200:
            message = '{}: {}'.format(response.status_code, response.reason)
            logger.exception(message)
            raise Exception(message)

        response_json = response.json()
        logger.debug('sucessfully got {} bytes'.format(len(response.content)))  # bytes?
        self.cache[url]['json'] = response_json
        return response_json


def flatten(my_dict, existing_dict=None, key_suffix=''):
    if existing_dict is None:
        existing_dict = {}
    for key, value in my_dict.items():
        if not isinstance(value, Mapping):
            existing_dict[key_suffix + key] = value
        else:
            flatten(value, existing_dict, key_suffix=key+'_')
    return existing_dict


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


if __name__ == '__main__':
    main()
