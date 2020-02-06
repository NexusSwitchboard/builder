from setuptools import setup, find_packages

setup(
    name='nex',
    version='0.0.3',
    packages=find_packages(),
    py_modules=['src'],
    include_package_data=True,
    install_requires=[
        'Click',
        'gitpython',
        'munch'
    ],
    entry_points='''
        [console_scripts]
        nex=src.main:cli
    ''',
)
