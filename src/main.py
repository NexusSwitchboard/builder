import click

from os import getcwd

from munch import DefaultMunch
from typing import List

from src.project import ActionResult, ProjectManager, Project, ActionMessage


@click.group()
@click.option('-b', '--branch', required=False, default="master", help="The branch name used for the targeted projects")
@click.option('-o', '--remote', required=False, default="nexus", help="The remote name used for the targeted projects")
@click.option('-r', '--root', required=False, default=None,
              help="The root directory to start looking for nexus packages")
@click.option('-p', '--project', required=False, default=None,
              help="You can specify a single project to target here.  Otherwise all found projects will be targeted")
@click.option('--dry-run', is_flag=True, required=False)
@click.pass_context
def cli(ctx, root, project, branch, remote, dry_run):
    if not ctx.obj:
        ctx.obj = DefaultMunch(None, {})

    ctx.obj.path = root or getcwd()
    ctx.obj.branch = branch
    ctx.obj.remote = remote
    ctx.obj.dry_run = dry_run or False

    ctx.obj.manager = ProjectManager(ctx.obj.path, branch=ctx.obj.branch, remote=ctx.obj.remote,
                                     dry_run=ctx.obj.dry_run)

    ctx.obj.project = ctx.obj.manager.find_by_name(project) if project else None

    click.secho("Nexus Builder", bold=True)
    click.echo("--------------------------")
    click.echo(f"{click.style('path', bold=True, fg='green')}\t\t{ctx.obj.path}")
    click.echo(f"{click.style('dry_run', bold=True, fg='green')}\t\t{ctx.obj.dry_run}")
    click.echo(f"{click.style('project', bold=True, fg='green')}\t\t{project or 'all'}")
    click.echo("--------------------------")


@cli.command(name="list")
@click.pass_context
def list_(ctx):
    final_projects = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()} - v{proj.get_version()} -> {"Dirty" if proj.is_dirty() else "Clean"}, '
                   f'Behind Remote: {len(proj.commits_behind)}, Ahead of Remote: {len(proj.commits_ahead)}')
        click.echo(f'{proj.}')

    if not len(final_projects):
        click.echo(repr(ActionMessage("list", "Unable to find any nexus projects")))


@cli.command()
@click.option('-m', '--msg', required=True)
@click.pass_context
def commit(ctx, msg):
    final_projects = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.commit(msg)
        click.echo(repr(result))


@cli.command()
@click.pass_context
def push(ctx):
    final_projects = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.push()
        click.echo(repr(result))


@cli.command()
@click.pass_context
def update(ctx):
    final_projects = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.update()
        click.echo(repr(result))


@cli.command()
@click.pass_context
def publish(ctx):
    final_projects = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.publish()
        click.echo(repr(result))


@cli.command()
@click.option("-v", "--version_type", type=click.Choice(["patch", "minor", "major"]), default="patch")
@click.pass_context
def version(ctx, version_type):
    final_projects: List[Project] = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        result = proj.increment_version(version_type)
        click.echo(repr(result))


@cli.command()
@click.option("m", "--msg", help="The commit message to use if a commit must be made")
@click.pass_context
def sync(ctx, msg):
    final_projects: List[Project] = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    succeeded = 0
    for proj in final_projects:

        if proj.is_dirty():
            click.echo(repr(ActionMessage("sync", "Committing local changes...")))
            result = proj.commit(msg)
            if not result.success:
                continue

        if proj.need_fetch():
            click.echo(repr(ActionMessage("sync", "Pulling from remote...")))
            result = proj.pull()
            if not result.success:
                continue

        if proj.need_push():
            click.echo(repr(ActionMessage("sync", "Pushing to remote...")))
            result = proj.push()
            if not result.success:
                continue

        succeeded += 1

    click.echo(
        repr(ActionResult("sync", f"Completed sync with {succeeded} out of {len(final_projects)} succeeding", True)))


@cli.command()
@click.option("--to", help="Link the given --project to the project given in this parameter")
@click.pass_context
def link(ctx, to):
    if not ctx.obj.project:
        click.echo(repr(ActionResult("link",
                                     "You must specify a -p/--project which acts as the source project. "
                                     " As in, link --project to --to.", False)))
        return

    to_proj = ctx.obj.manager.find_by_name(to)
    from_proj = ctx.obj.project

    if not to_proj:
        click.echo(repr(ActionResult("link", f"Unable to find {to} project", False)))
        return

    result = to_proj.link_global()
    if result.success:
        result = from_proj.link(to_proj)
        click.echo(repr(result))
    else:
        click.echo(repr(result))


@cli.command()
@click.option("-t", "--version_type", type=click.Choice(["patch", "minor", "major"]), default="patch")
@click.option("-m", "--msg", type=str)
@click.pass_context
def deploy(ctx, version_type, msg):
    final_projects: List[Project] = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')

        if proj.is_dirty() and not msg:
            click.echo(f'Skipped because there is uncommitted code and no commit message')
            continue
        elif proj.is_dirty():
            click.echo(f'[i] Uncommitted and staged changes.  Committing with given commit message...')
            result = proj.commit(msg)
            click.echo(repr(result))

            if result.success:
                click.echo(f'[i] Pushing changes...')
                result = proj.push()
                click.echo(repr(result))
                if not result.success:
                    continue
            else:
                continue
        else:
            click.echo(f'[i] No uncommitted changes detected so skipping commit and push...')

        if version_type:
            click.echo(f'[i] Version type given so attempting to increment version...')
            result = proj.increment_version(version_type)
            click.echo(repr(result))
            if not result.success:
                continue
        else:
            click.echo(f'[i] No version type given so skipping version increment...')

        click.echo(f'[i] Publishing current version to NPM registry...')
        result = proj.publish()
        click.echo(repr(result))

        if ctx.obj.dry_run:
            click.echo(f'[i] Resetting local repo because in dry run mode...')
            click.echo(repr(proj.reset()))


if __name__ == "__main__":
    cli(obj=DefaultMunch(None, {}))
