from setuptools import setup

setup(
    name='shepard_cli',
    version='1.0',
    description='Friendly command line interface for managing and interacting with shepard architectures!',
    author='Jacob Mevorach',
    author_email='jacob@ginkgobioworks.com',
    url='https://github.com/ginkgobioworks/shepard',
    packages=['shepard_cli'],
    entry_points = {'console_scripts': ['shepard_cli=shepard_cli.cli:run']},
    python_requires='>=3.6'
)

