import click

from os.path import dirname

from project import ProjectManager

projects = ProjectManager(dirname(dirname(__file__)))


@click.group()
def cli():
    pass


@cli.command()
def list_projects():
    global projects
    for proj in projects.get_projects():
        click.echo(f'{proj.get_name()} - v{proj.get_version()} -> {"Dirty" if proj.is_dirty() else "Clean"}, '
                   f'Behind Remote: {len(proj.commits_behind)}, Ahead of Remote: {len(proj.commits_ahead)}')


@cli.command()
@click.option('--msg', required=True)
def commit(msg):
    global projects
    click.echo(f'Staging and committing all projects')
    click.echo(f'-----------')
    for proj in projects.get_projects():
        click.echo(f'{proj.get_name()}:')
        result = proj.commit(msg)
        click.echo(f'\t{result.action}: {result.message}\n')


@cli.command()
def push():
    global projects
    click.echo(f'Pushing all projects to remote')
    click.echo(f'-----------')
    for proj in projects.get_projects():
        click.echo(f'{proj.get_name()}:')
        result = proj.push()
        click.echo(f'\t{result.action}: {result.message}\n')


if __name__ == "__main__":
    cli()
