import json
import os
import subprocess
from enum import Enum
from json import JSONDecodeError
from typing import List, Set
import logging
from munch import DefaultMunch
from git import Repo, GitCommandError

keywords: Set[str] = {"nexus-module", "nexus-connection"}
names: List[str] = ["nexus-core", "nexus-extend"]


class ActionResult(DefaultMunch):
    def __init__(self, action, message):
        super(ActionResult, self).__init__(None, {
            "action": action,
            "message": message
        })


class NpmVersionType(Enum):
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


class Project:

    def __init__(self, package_ob: dict, root_dir: str, dirs: list, files: list, remote: str, branch: str):
        self.root_directory = root_dir
        self.package_ob = DefaultMunch(None, package_ob)
        self.project_dirs = dirs
        self.project_files = files
        self.repo = None
        self.remote = remote
        self.branch = branch
        self.commits_ahead = []
        self.commits_behind = []

        self._load_git_info()

    @staticmethod
    def is_nexus_project(package_ob: dict) -> bool:
        pm = DefaultMunch(None, package_ob)
        if pm.keywords and len(set(pm.keywords).intersection(keywords)) > 0:
            return True
        else:
            return pm.name in names

    @staticmethod
    def load_npm_package(file: str) -> [dict, None]:

        try:
            with open(file, 'r') as fp:
                package_ob = json.load(fp)
                return package_ob if Project.is_nexus_project(package_ob) else None
        except JSONDecodeError as e:
            logging.error(f'Unable to process {file} because it has a JSON formatting error')
        except FileNotFoundError as e:
            return None

    @staticmethod
    def create_project(root, dirs: list, files: list) -> [dict, None]:
        if "package.json" in files:
            ob = Project.load_npm_package(os.path.join(root, "package.json"))
            if ob:
                return Project(ob, root, dirs, files, remote="nexus", branch="master")

        return None

    def _load_git_info(self):
        assert self.root_directory
        assert self.package_ob

        if not self.repo:
            self.repo = Repo(self.root_directory)

        if self.repo:
            self.commits_behind = [c for c in self.repo.iter_commits(f'{self.branch}..{self.remote}/{self.branch}')]
            self.commits_ahead = [c for c in self.repo.iter_commits(f'{self.remote}/{self.branch}..{self.branch}')]

    def is_dirty(self) -> bool:
        return self.repo.is_dirty()

    def get_name(self):
        return self.package_ob['name']

    def get_version(self):
        return self.package_ob['version']

    def is_module(self):
        return "nexus-module" in self.package_ob['keywords']['@nexus-switchboard/nexus-extend']

    def is_connection(self):
        return "nexus-connection" in self.package_ob['dependencies']['@nexus-switchboard/nexus-extend']

    def is_core(self):
        return self.package_ob['name'] == 'nexus-core'

    def is_extender(self):
        return self.package_ob['name'] == 'nexus-extend'

    def increment_version(self, type: NpmVersionType):
        subprocess.Popen(["npm", "version", type], cwd=self.root_directory)

    def need_push(self):
        return len(self.commits_ahead) > 0

    def need_fetch(self):
        return len(self.commits_behind) > 0

    def commit(self, message: str) -> ActionResult:

        try:
            self.repo.git.add(".")
        except GitCommandError as e:
            logging.error(f'Failed {e.command}:\n{e.stdout}')
        try:
            if self.is_dirty():
                self.repo.git.commit("-m", message)
                return ActionResult(action="complete", message="Committed")
            else:
                return ActionResult(action="none", message="Working directory clean")
        except GitCommandError as e:
            if e.stdout.find("working directory clean") == -1:
                logging.error(f'Failed {e.command}:\n{e.stdout}')
                return ActionResult(action="failed", message=e.stdout)
            else:
                return ActionResult(action="none", message="Nothing to do")

    def push(self) -> ActionResult:

        try:
            self.repo.git.push(self.remote, self.branch)
            return ActionResult(action="pushed", message="Operation completed successfully")
        except GitCommandError as e:
            logging.error(f'Failed {e.command}:\n{e.stdout}')
            return ActionResult(action="failed", message=e.stdout)


class ProjectManager:

    def __init__(self, root_directory: str):
        self.root_directory: str = root_directory
        self.projects: List[Project] = []
        projects_loaded = self._load_projects()

        if projects_loaded == 0:
            logging.error(f'Loaded no projects from ${root_directory}')
        else:
            logging.debug(f'Loaded {projects_loaded} projects')

    def _load_projects(self) -> int:
        assert self.root_directory

        for subdir, dirs, files in os.walk(self.root_directory):
            if 'package.json' in files:
                # we're in an npm package - go ahead and clear out all subdirs (we don't want to descend any further)
                dirs.clear()

                # now try and create a nexus project object.  This will fail if it's not a nexus project.
                proj = Project.create_project(subdir, dirs, files)
                if proj:
                    self.projects.append(proj)

        return len(self.projects)

    def get_projects(self) -> List[Project]:
        return self.projects
