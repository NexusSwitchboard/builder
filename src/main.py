import click

from os import getcwd

from munch import DefaultMunch
from typing import List

from src.project import ProjectManager, Project


@click.group()
@click.option('--root', required=False)
@click.option('--project', required=False)
@click.option('--dry-run', is_flag=True, required=False)
@click.pass_context
def cli(ctx, root, project, dry_run):
    if not ctx.obj:
        ctx.obj=DefaultMunch(None, {})

    ctx.obj.path = root or getcwd()
    ctx.obj.manager = ProjectManager(ctx.obj.path, dry_run=dry_run)
    ctx.obj.project = ctx.obj.manager.find_by_name(project) if project else None
    ctx.obj.dry_run = dry_run or False


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


@cli.command()
@click.option('--msg', required=True)
@click.pass_context
def commit(ctx, msg):
    final_projects = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    click.echo(f'Staging and committing all projects')
    click.echo(f'-----------')

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

    click.echo(f'Pushing all projects to remote')
    click.echo(f'-----------')
    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')
        result = proj.push()
        click.echo(repr(result))


@cli.command()
@click.option("--version_type", type=click.Choice(["patch", "minor", "major"]), default="patch")
@click.pass_context
def version(ctx, version_type):
    final_projects: List[Project] = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    click.echo(f'Pushing all projects to remote')
    click.echo(f'-----------')
    for proj in final_projects:
        result = proj.increment_version(version_type)
        click.echo(repr(result))


@cli.command()
@click.option("--version_type", type=click.Choice(["patch", "minor", "major"]), default="patch")
@click.option("--commit_message", type=str)
@click.pass_context
def deploy(ctx, version_type, commit_message):
    final_projects: List[Project] = []
    if ctx.obj.project:
        final_projects.append(ctx.obj.project)
    else:
        final_projects = ctx.obj.manager.get_projects()

    click.echo(f'Deploying packages' + ("" if not ctx.obj.dry_run else "[Dry Run Mode]"))
    click.echo(f'-----------')
    for proj in final_projects:
        click.echo(f'{proj.get_name()}:')

        if proj.is_dirty() and not commit_message:
            click.echo(f'Skipped because there is uncommitted code and no commit message')
            continue
        elif proj.is_dirty():
            click.echo(f'\t[i] Uncommitted and staged changes.  Committing with given commit message...')
            result = proj.commit(commit_message)
            click.echo(repr(result))

            if result.success:
                click.echo(f'\t[i] Pushing changes...')
                result = proj.push()
                click.echo(repr(result))
                if not result.success:
                    continue
            else:
                continue
        else:
            click.echo(f'\t[i] No uncommitted changes detected so skipping commit and push...')

        if version_type:
            click.echo(f'\t[i] Version type given so attempting to increment version...')
            result = proj.increment_version(version_type)
            click.echo(repr(result))
            if not result.success:
                continue
        else:
            click.echo(f'\t[i] No version type given so skipping version increment...')

        click.echo(f'\t[i] Publishing current version to NPM registry...')
        result = proj.publish()
        click.echo(repr(result))

        if ctx.obj.dry_run:
            click.echo(f'\t[i] Resetting local repo because in dry run mode...')
            click.echo(repr(proj.reset()))


if __name__ == "__main__":
    cli(obj=DefaultMunch(None, {}))
