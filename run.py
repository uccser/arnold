import os
import sys
import logging
import base64
import yaml
from shutil import rmtree
from utils import (
    run_shell,
    read_secrets,
    display_elapsed_time,
    get_crowdin_api_key,
)
from translation import (
    update_source_message_file,
    push_source_files,
    build_project,
    pull_translations,
)
from link_checker import check_links
import argparse
import github
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler, setup_logging
from google.auth.exceptions import DefaultCredentialsError
from timeit import default_timer as timer

DEFAULT_WORKING_DIRECTORY = os.getcwd()
PROJECT_DIRECTORY = "projects"
GITHUB_BOT_EMAIL = "33709036+uccser-bot@users.noreply.github.com"
GITHUB_BOT_NAME = "UCCSER Bot"
REQUIRED_SECRETS = [
    ["GITHUB_TOKEN", "OAuth token to use for GitHub API requests"],
]
PROJECT_CONFIG_FILE = ".arnold.yaml"
SEPERATOR_WIDTH = 60
MAJOR_SEPERATOR = "=" * SEPERATOR_WIDTH
MINOR_SEPERATOR = "-" * SEPERATOR_WIDTH
ALL_TASKS_KEYWORD = "all"
TASKS = [
    "link-checker",
    "update-source-message-files",
    "push-source-files",
    "build-project",
    "pull-translations",
]
TASK_KEYWORDS = dict()
for keyword in TASKS:
    TASK_KEYWORDS[keyword] = [keyword, ALL_TASKS_KEYWORD]

logging.getLogger().setLevel(logging.INFO)
try:
    client = google.cloud.logging.Client()
    client.setup_logging(log_level=logging.INFO)
except DefaultCredentialsError:
    logging.info("Only logging locally.")

# From https://stackoverflow.com/a/16993115
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical("Uncaught exception!", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

class Project:

    def __init__(self, config, repo, bot, secrets, parent_directory, cli_args):
        self.config = config
        self.repo = repo
        self.name = repo.name
        self.bot = bot
        self.secrets = secrets
        self.parent_directory = parent_directory
        self.cli_args = cli_args
        self.directory = os.path.join(parent_directory, self.name)
        self.start_time = timer()

    def display_elapsed_time(self):
        display_elapsed_time(self.start_time)
        self.start_time = timer()

    def clone(self):
        """Clone the repository, deleting any existing installations."""
        if not self.cli_args.skip_clone:
            if os.path.isdir(self.directory):
                logging.info("Existing repository detected! Deleting existing directory...")
                run_shell(["sudo", "rm", "-r", self.directory])
            run_shell(["git", "clone", self.repo.ssh_url])

    def run(self):
        if self.cli_args.task in TASK_KEYWORDS["link-checker"] and self.config.get("broken-link-checker"):
            check_links(self)
            self.display_elapsed_time()

        if self.config.get("translation"):
            self.crowdin_api_key = get_crowdin_api_key(self.name, self.secrets)
            if self.cli_args.task in TASK_KEYWORDS["update-source-message-files"]:
                update_source_message_file(self)
                self.display_elapsed_time()
            if self.cli_args.task in TASK_KEYWORDS["push-source-files"]:
                push_source_files(self)
                self.display_elapsed_time()
            if self.cli_args.task in TASK_KEYWORDS["build-project"]:
                build_project(self)
                self.display_elapsed_time()
            if self.cli_args.task in TASK_KEYWORDS["pull-translations"]:
                pull_translations(self)
                self.display_elapsed_time()


def main():
    start_time = timer()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "task",
        help="The task to run"
    )
    parser.add_argument(
        "-c",
        "--skip-clone",
        help="Skip cloning repositories",
        action="store_true"
    )
    parser.add_argument(
        "-r",
        "--repo",
        help="Run only on the given repository",
        action="store"
    )
    args = parser.parse_args()
    if args.skip_clone:
        logging.info("Skip cloning repositories turned on.\n")

    secrets = read_secrets(REQUIRED_SECRETS)

    if not os.path.exists(PROJECT_DIRECTORY):
        os.makedirs(PROJECT_DIRECTORY)
    os.chdir(PROJECT_DIRECTORY)
    directory_of_projects = os.path.abspath(os.getcwd())

    github_env = github.Github(secrets["GITHUB_TOKEN"])
    uccser = github_env.get_user("uccser")
    bot = github_env.get_user("uccser-bot")
    if args.repo:
        uccser_repos = [uccser.get_repo(args.repo)]
    else:
        uccser_repos = uccser.get_repos()

    for repo in uccser_repos:
        os.chdir(directory_of_projects)
        logging.info("{0}\n{1}\n{2}".format(MAJOR_SEPERATOR, repo.full_name, MINOR_SEPERATOR))
        try:
            config_file = repo.get_contents(PROJECT_CONFIG_FILE)
            logging.info("Config file for Arnold detected.")
        except github.GithubException:
            config_file = None
            logging.info("Config file for Arnold not detected.")
        if config_file:
            logging.info("Reading Arnold config.")
            try:
                config = yaml.load(base64.b64decode(config_file.content).decode("utf-8"))
            except yaml.YAMLError:
                logging.error("Error! YAML file invalid.")
                # TODO: Log issue on repo
            if config:
                project = Project(config, repo, bot, secrets, directory_of_projects, args)
                project.clone()
                os.chdir(project.directory)
                setup_git_account()
                project.run()
        logging.info("{0}\n".format(MAJOR_SEPERATOR))
    display_elapsed_time(start_time)


def setup_git_account():
    """Set the name and email account of the git account."""
    run_shell(["git", "config", "--global", "user.name", GITHUB_BOT_NAME])
    run_shell(["git", "config", "--global", "user.email", GITHUB_BOT_EMAIL])


if __name__ == "__main__":
    main()
