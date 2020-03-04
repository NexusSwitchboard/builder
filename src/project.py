import json
import os
import subprocess
import click
from json import JSONDecodeError
from typing import List, Set
import semver

import logging
from munch import DefaultMunch, Munch, munchify
from git import Repo, GitCommandError

keywords: Set[str] = {"nexus-module", "nexus-connection", "nexus-app"}
names: List[str] = ["nexus-core", "nexus-extend"]


class ActionMessage(DefaultMunch):
    def __init__(self, action, message):
        super(ActionMessage, self).__init__(None, {
            "action": action,
            "message": message
        })

    def __repr__(self):
        return f'{self.get_type()} {self.action}: {self.message}'

    def get_type(self):
        return "[i]"


class ActionResult(ActionMessage):
    def __init__(self, action, message, success):
        super(ActionResult, self).__init__(action, message)
        self.success = success

    def get_type(self):
        return "[c]" if self.success else "[e]" if self.success is False else "[w]"


class Project:

    def __init__(self, package_ob: dict, root_dir: str,
                 dirs: list, files: list, remote: str, branch: str,
                 dry_run_mode: bool = False):
        self.root_directory = root_dir
        self.package_ob = DefaultMunch(None, package_ob)
        self.project_dirs = dirs
        self.project_files = files
        self.repo = None
        self.remote = remote
        self.branch = branch
        self.remote_valid = False
        self.branch_valid = False
        self.commits_ahead = []
        self.commits_behind = []
        self.dry_run_mode = dry_run_mode
        self._latest_remote_version = None
        self._git_info_loaded = False

        self._load_git_info()

    @staticmethod
    def is_nexus_project(package_ob: dict) -> bool:
        pm = DefaultMunch(None, package_ob)
        if pm.keywords and len(set(pm.keywords).intersection(keywords)) > 0:
            return True
        else:
            # Return true if the approved names are anywhere in the package name.
            return len([p for p in names if pm.name.find(p) > -1]) > 0

    @staticmethod
    def load_npm_package(file: str) -> [dict, None]:

        try:
            with open(file, 'r') as fp:
                package_ob = json.load(fp)
                return package_ob if Project.is_nexus_project(package_ob) else None
        except JSONDecodeError as e:
            pass

        except FileNotFoundError as e:
            return None

        return None

    def __repr__(self):
        out = f"{click.style(self.get_name(), fg='green', bold=True)}\n" \
              f"{click.style('Local/Remote Version:', bold=True)} {self.get_version()} / " \
              f"{self._get_latest_remote_version()}" \
              f"{click.style('Uncommitted Changes:', bold=True)} {'Yes' if self.is_dirty() else 'No'}\n" \
              f"{click.style('Behind/Ahead Remote:', bold=True)} {len(self.commits_behind)}/{len(self.commits_ahead)}"

        return out

    def deploy(self, msg: str = None, version_type: str = "patch"):
        local_version = semver.parse_version_info(self.get_version())
        remote_version = semver.parse_version_info(self._get_latest_remote_version())

        needs_publish = local_version > remote_version
        out_of_date = local_version < remote_version

        is_dirty = self.is_dirty()
        is_ahead = len(self.commits_ahead) > len(self.commits_behind)
        is_behind = len(self.commits_behind) > len(self.commits_ahead)

        commit_required = is_dirty
        push_required = is_ahead and not is_behind
        pull_required = is_behind and not is_ahead
        merge_required = (is_ahead and is_behind) or (pull_required and is_dirty)

        needs_versioning = (push_required or commit_required) and local_version <= remote_version

        if merge_required:
            return ActionResult("deploy", "It looks like your local repo is out of date - "
                                          "do a pull and merge if necessary", False)

        if out_of_date:
            return ActionResult("deploy", "Somehow your local package  version is less than the one "
                                          "deployed to the registry.  Bailing out now while you resolve that...")

        actions_taken = []
        if commit_required:
            click.echo(repr(ActionMessage("deploy", f"{self.get_name()} has uncommitted changes. Committing...")))
            result = self.commit(message=(msg or "nex builder committed"))
            if not result.success:
                return result
            else:
                actions_taken.append("commit")
                push_required = True

        if needs_versioning:
            click.echo(repr(ActionMessage("deploy",
                                          f"{self.get_name()} has the  same version as the currently published one. "
                                          f"Versioning...")))
            result = self.increment_version(version_type)
            if not result.success:
                return result
            else:
                actions_taken.append("versioned")
                needs_publish = True

        if push_required:
            click.echo(repr(ActionMessage("deploy", f"{self.get_name()} local repo is ahead of remote.  Pushing...")))
            result = self.push()
            if not result.success:
                return result
            else:
                actions_taken.append("push")

        if needs_publish:
            click.echo(repr(
                ActionMessage("deploy", f"{self.get_name()} local package version is ahead of remote. Publishing...")))
            result = self.publish()
            if not result.success:
                return result
            else:
                actions_taken.append("publish")

        if len(actions_taken) == 0:
            return ActionResult("deploy", f"No actions needed to be taken to deploy {self.get_name()}", True)
        else:
            return ActionResult("deploy",
                                f"Successfully deployed {self.get_name()} by running these actions: "
                                f"{','.join(actions_taken)} ",
                                True)

    def _load_git_info(self):

        if self._git_info_loaded:
            return

        assert self.root_directory
        assert self.package_ob

        if not self.repo:
            self.repo = Repo(self.root_directory)

        if self.repo:
            self.branch_valid = self.has_branch(self.branch)
            self.remote_valid = self.has_remote(self.remote)

            try:
                if self.branch_valid and self.remote_valid:
                    self.repo.git.fetch()
                    self.commits_behind = [c for c in
                                           self.repo.iter_commits(f'{self.branch}..{self.remote}/{self.branch}')]
                    self.commits_ahead = [c for c in
                                          self.repo.iter_commits(f'{self.remote}/{self.branch}..{self.branch}')]
                    self._git_info_loaded = True
            except GitCommandError as e:
                pass

    def is_dirty(self) -> bool:
        return self.repo.is_dirty()

    def has_keyword(self, kw):
        if "keywords" in self.package_ob and isinstance(self.package_ob.keywords, list):
            return kw in self.package_ob.keywords
        else:
            return False

    def has_branch(self, branch_name):
        for b in self.repo.branches:
            if b.name == branch_name:
                return True

        return False

    def has_remote(self, remote_name):
        for r in self.repo.remotes:
            if r.name == remote_name:
                return True

        return False

    def get_name(self, without_scope=False):
        n: str = self.package_ob['name']
        if without_scope:
            scope_index = n.rfind("/")
            if scope_index != -1:
                return n[scope_index + 1:]

        return n

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

    def _get_latest_remote_version(self) -> str:
        if self._latest_remote_version:
            return self._latest_remote_version

        params = ["npm", "show", self.package_ob.name, "version"]

        ver = self._run_command_for_str(params).decode('utf-8')

        self._latest_remote_version = ver

        return ver

    def increment_version(self, type_: str) -> ActionResult:

        params = ["npm", "version", type_]
        if self.dry_run_mode:
            click.echo(repr(ActionResult("version", "There is no way to dry run the npm version command", None)))

        stdout, stderr, returncode = self._run_command(params)

        if returncode == 0:
            return ActionResult("increment_version", stdout or "Completed successfully", True)
        else:
            logging.error(stderr)
            return ActionResult("increment_version", f"Failed with return code {returncode}", False)

    def publish(self) -> ActionResult:

        params = ["npm", "publish"]
        if self.dry_run_mode:
            params.append("--dry-run")

        stdout, stderr, returncode = self._run_command(params)

        if returncode == 0:
            return ActionResult("publish", stdout or "Completed successfully", True)
        else:
            logging.error(stderr)
            return ActionResult("publish", f"Failed with return code {returncode}", False)

    def update(self) -> ActionResult:
        params = ["npm", "update"]
        if self.dry_run_mode:
            params.append("--dry-run")

        stdout, stderr, returncode = self._run_command(params)

        if returncode == 0:
            return ActionResult("update", stdout or "Completed successfully", True)
        else:
            logging.error(stderr)
            return ActionResult("update", f"Failed with return code {returncode}", False)

    def need_push(self):
        return len(self.commits_ahead) > 0

    def need_fetch(self):
        return len(self.commits_behind) > 0

    def pull(self) -> ActionResult:
        if not self.branch_valid:
            return ActionResult("pull", f"Unable to pull because branch {self.branch} could not be found", False)
        if not self.remote_valid:
            return ActionResult("pull", f"Unable to pull because remote {self.remote} could not be found", False)

        try:
            if len(self.commits_behind) > 0:
                if not self.commits_ahead:
                    self.repo.git.pull(self.remote, self.branch)
                    return ActionResult("pull", "Pull completed successfully", True)
                else:
                    return ActionResult("pull", "Cannot pull while your branch is ahead of remote", False)
            else:
                return ActionResult("pull", "Nothing to do", True)
        except GitCommandError as e:
            return ActionResult(action="pull", message=str(e), success=False)

    def link_global(self):
        params = ["npm", "link"]
        stdout, stderr, returncode = self._run_command(params)

        if returncode == 0:
            return ActionResult("link_global", "Local npm repo now points to local package", True)
        else:
            return ActionResult("link_global", f"Failed with errorcode {returncode}: {stderr}", False)

    def link(self, to) -> ActionResult:
        params = ["npm", "link", to.package_ob.name]
        if self.dry_run_mode:
            params.append("--dry-run")

        stdout, stderr, returncode = self._run_command(params)

        if returncode == 0:
            return ActionResult("link", "Local npm repo now points to local package", True)
        else:
            return ActionResult("link", f"Failed with errorcode {returncode}", False)

    def commit(self, message: str) -> ActionResult:

        try:
            self.repo.git.add(".")
        except GitCommandError as e:
            return ActionResult(action="stage", message=str(e), success=False)

        try:
            if self.is_dirty():
                params = ["-m", message]
                if self.dry_run_mode:
                    params.append("--dry-run")

                self.repo.git.commit(*params)
                return ActionResult(action="commit", message="Operation completed successfully", success=True)

            else:
                return ActionResult(action="commit", message="Nothing to do: working directory clean", success=True)

        except GitCommandError as e:
            if e.stdout.find("working directory clean") == -1:
                return ActionResult(action="commit", message=e.stdout, success=False)
            else:
                return ActionResult(action="commit", message="Nothing to do: working directory clean", success=True)

    def push(self) -> ActionResult:

        try:
            params = [self.remote, self.branch]
            if self.dry_run_mode:
                params.append("--dry-run")

            self.repo.git.push(*params)

            return ActionResult(action="push", message="Operation completed successfully", success=True)
        except GitCommandError as e:
            logging.error(e.stderr)
            return ActionResult(action="push", message=e.stdout, success=False)

    def reset(self):

        try:
            self.repo.git.reset()
            self.repo.git.checkout(".")
            return ActionResult(action="reset", message="Operation completed successfully", success=True)

        except GitCommandError as e:
            return ActionResult(action="reset", message=str(e), success=False)

    def _run_command_for_str(self, command_array):
        return subprocess.check_output(command_array, cwd=self.root_directory)

    def _run_command(self, command_array) -> (str, str):
        p = subprocess.Popen(command_array, cwd=self.root_directory, stderr=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL)
        stdout, stderr = p.communicate()
        return stdout, stderr, p.returncode


class ProjectManager:

    def __init__(self, root_directory: str, branch: str, remote: str,
                 dry_run: bool = False, project: Project = None, projtype: str = None):
        self.root_directory: str = root_directory
        self.projects: List[Project] = []
        self.branch = branch
        self.remote = remote
        self.filter = Munch({
            "project": project,
            "projtype": projtype
        })

        self._load_projects(dry_run)

    def _load_projects(self, dry_run: bool = False) -> int:
        assert self.root_directory

        gatheredProjects = []
        for subdir, dirs, files in os.walk(self.root_directory):
            if 'package.json' in files:

                if '.git' not in dirs:
                    # don't bother with any projects that are not git initialized
                    continue

                ob = Project.load_npm_package(os.path.join(subdir, "package.json"))
                if not ob:
                    # The package.json could not be loaded.
                    continue

                ob = DefaultMunch(None, ob)
                if self.filter.project and ob.name and \
                        (ob.name not in self.filter.project) and \
                        (self.filter.project not in ob.name):
                    # the filter is looking for a single project by a certain name.
                    continue

                if self.filter.projtype and not ob.keywords:
                    # if there's no keywords and one is specified in the filter then skip
                    continue

                if self.filter.projtype and ob.keywords and (self.filter.projtype not in ob.keywords):
                    # the filter is looking for a certain project type
                    continue

                # Now we can load the project assuming all the last checks passed.
                gatheredProjects.append(Munch({
                    "ob": ob.copy(),
                    "subdir": subdir,
                    "dirs": dirs.copy(),
                    "files": files.copy()
                }))

                # we're in an npm package - go ahead and clear out all subdirs (we don't want to descend any further)
                dirs.clear()

        with click.progressbar(gatheredProjects, label=f"Loading {len(gatheredProjects)} projects:") as bar:
            for p in bar:
                proj = Project(p.ob, p.subdir, p.dirs, p.files, remote=self.remote,
                               branch=self.branch, dry_run_mode=dry_run)
                if proj:
                    self.projects.append(proj)

        return len(self.projects)

    def get_projects(self) -> List[Project]:
        return self.projects

    def find_by_name(self, name: str) -> Project:
        matching = [p for p in self.projects if p.get_name(without_scope=True) == name]
        return None if len(matching) == 0 else matching[0]
