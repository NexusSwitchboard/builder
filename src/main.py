import click

from os import getcwd

from munch import DefaultMunch

from src.project import ActionResult, ProjectManager, Project, ActionMessage


@click.group()
@click.option('-b', '--branch', required=False, default="master", help="The branch name used for the targeted projects")
@click.option('-o', '--remote', required=False, default="nexus", help="The remote name used for the targeted projects")
@click.option('-r', '--root', required=False, default=None,
              help="The root directory to start looking for nexus packages")
@click.option('-p', '--project', required=False, default=None,
              help="You can specify a single project to target here.  Otherwise all found projects will be targeted")
@click.option('-y', '--projtype', required=False, default=None,
              help="The type of project to run against.  This can be one of the following: 'nexus-module', "
                   "'nexus-connection', 'nexus-app'")
@click.option('--dry-run', is_flag=True, required=False)
@click.pass_context
def cli(ctx, root, project, branch, remote, projtype, dry_run):
    if not ctx.obj:
        ctx.obj = DefaultMunch(None, {})

    ctx.obj.path = root or getcwd()
    ctx.obj.branch = branch
    ctx.obj.remote = remote
    ctx.obj.dry_run = dry_run or False

    click.secho("Nexus Builder", bold=True)
    click.echo("--------------------------")
    click.echo(f"{click.style('path', bold=True, fg='green')}\t\t{ctx.obj.path}")
    click.echo(f"{click.style('dry_run', bold=True, fg='green')}\t\t{ctx.obj.dry_run}")
    click.echo(f"{click.style('project', bold=True, fg='green')}\t\t{project or 'all'}")
    click.echo(f"{click.style('type', bold=True, fg='green')}\t\t{projtype or 'N/A'}")
    click.echo("--------------------------")

    ctx.obj.manager = ProjectManager(ctx.obj.path, branch=ctx.obj.branch, remote=ctx.obj.remote,
                                     dry_run=ctx.obj.dry_run, project=project, projtype=projtype)


@cli.command(name="list")
@click.pass_context
def list_(ctx):
    final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(repr(proj))

    if not len(final_projects):
        click.echo(repr(ActionMessage("list", "Unable to find any nexus projects")))


@cli.command()
@click.option('-m', '--msg', required=True)
@click.pass_context
def commit(ctx, msg):
    final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.commit(msg)
        click.echo(repr(result))


@cli.command()
@click.pass_context
def push(ctx):
    final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.push()
        click.echo(repr(result))


@cli.command()
@click.pass_context
def update(ctx):
    final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.update()
        click.echo(repr(result))


@cli.command()
@click.pass_context
def publish(ctx):
    final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.publish()
        click.echo(repr(result))


@cli.command()
@click.option("-v", "--version_type", type=click.Choice(["patch", "minor", "major"]), default="patch")
@click.pass_context
def version(ctx, version_type):
    final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        result = proj.increment_version(version_type)
        click.echo(repr(result))


@cli.command()
@click.option("-m", "--msg", help="The commit message to use if a commit must be made")
@click.pass_context
def sync(ctx, msg):
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
@click.pass_context
def link(ctx):
    final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        result = proj.link_global()
        click.echo(repr(result))


@cli.command()
@click.option("-t", "--version_type", type=click.Choice(["patch", "minor", "major"]), default="patch")
@click.option("-m", "--msg", type=str)
@click.pass_context
def deploy(ctx, version_type, msg):
    final_projects = ctx.obj.manager.get_projects()

    for proj in final_projects:
        result = proj.deploy(msg=msg, version_type=version_type)
        click.echo(repr(result))


if __name__ == "__main__":
    cli(obj=DefaultMunch(None, {}))
