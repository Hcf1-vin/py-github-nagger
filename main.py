from github import Github
import json
import logging
import os
import requests
import time
import yaml

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.yml")


def read_config():
    try:
        logging.info(f"Reading {config_file}")
        with open(config_file) as file:
            config = yaml.load(file, Loader=yaml.FullLoader)
        logging.info(f"Read {config_file}")
        return config
    except Exception as e:
        logging.error(f"{e}")


config = read_config()
github_token = config["github_token"]

logging.info(f"Creating github client")
g = Github(github_token)


def sleepy_time(seconds=2):
    # Added sleep to prevent failure due to GitHub api rate limits
    logging.info(f"Sleeping for {seconds} seconds")
    time.sleep(seconds)


def get_username():
    logging.info(f"Getting username")
    user = g.get_user()
    logging.info(f"Returning username: {user.login}")
    return user.login


def get_org():
    logging.info(f"Getting org name")
    org = g.get_organization(config["org_name"])
    logging.info(f"Returning org name: {org.login}")
    return org.login


def get_org_repos():
    logging.info(f"Searching for repositories for my org")
    repositories = g.search_repositories(query="org:" + get_org())

    non_forks_report_list = list()

    for repo in repositories:
        if repo.fork is False:
            logging.info(f"Appending {repo.full_name} to repo list")
            non_forks_report_list.append(repo.full_name)

    logging.info(f"Returning list of repositories")
    return non_forks_report_list


def search_my_prs(repo_list, username):

    main_pr_dict = dict()
    logging.info(f"Looping over all repositories")
    for repo_name in repo_list:
        sleepy_time()
        logging.info(
            f"Searching for issues created by {username} where repo={repo_name} and type=pr"
        )
        issues = g.search_issues(
            "",
            repo=repo_name,
            state="open",
            author=username,
            type="pr",
        )

        for i in issues:
            logging.info(f"Looping over all pull requests found by search")
            pr_dict = dict()

            if repo_name not in main_pr_dict:
                main_pr_dict[repo_name] = list()

            pr_dict["repo_name"] = repo_name
            pr_dict["pr_title"] = i.title
            pr_dict["pr_number"] = i.number

            pr_url = construct_pr_url(repo_name, i.number)
            pr_dict["pr_url"] = pr_url

            if pr_url not in config["exclude"]:
                logging.info(f"Adding {pr_url} to main_pr_dict")
                main_pr_dict[repo_name].append(pr_dict)

        sleepy_time()

    logging.info(f"Returning main_pr_dict dict")
    return main_pr_dict


def construct_pr_url(repo_name, pr_number):
    logging.info(f"Constructing pr url")
    pr_url = "https://github.com/" + repo_name + "/pull/" + str(pr_number)
    logging.info(f"Returning {pr_url}")
    return pr_url


def construct_slack_body(pr_results):
    logging.info(f"Constructing slack message body")
    main_message_body = config["slack"]["pre_message"] + "\n\n"

    for repo in pr_results:
        main_message_body = main_message_body + "*" + repo + "*" + "\n"

        for pr in pr_results[repo]:

            main_message_body = main_message_body + "\u2022" + " " + pr["pr_url"] + "\n"

        main_message_body = main_message_body + "\n"

    main_message_body = main_message_body + "\n" + config["slack"]["post_message"]

    logging.info(f"Returning slack message body")
    return main_message_body


def send_slack(message_body):

    slack_headers = {"Content-Type": "application/json"}

    slack_url = config["slack"]["url"]

    logging.info("Constructing slack playload")
    slack_data = {}
    slack_data["icon_emoji"] = config["slack"]["icon_emoji"]
    slack_data["channel"] = config["slack"]["channel"]
    slack_data["username"] = config["slack"]["username"]
    slack_data["text"] = message_body

    logging.info("json dump slack payload and encode as utf-8")
    slack_encode = json.dumps(slack_data).encode("utf-8")

    try:
        logging.info(
            f"Posting  message to Slack channel {slack_data['channel']} as {slack_data['username']}"
        )
        response = requests.post(slack_url, data=slack_encode, headers=slack_headers)
    except Exception as e:
        logging.error(str(e))

    logging.info(f"Slack response text: {response.text}")
    logging.info(f"Slack response code: {response.status_code}")

    if response.status_code != 200:
        logging.error("Slack message failed")
    else:
        logging.info("Slack message sent")


def get_remaining_rate_limit():
    logging.info("Getting API rate limits")
    rates = g.get_rate_limit()
    logging.info(rates)


if __name__ == "__main__":
    get_remaining_rate_limit()

    username = get_username()

    repo_list = get_org_repos()

    pr_results = search_my_prs(repo_list, username)

    message_body = construct_slack_body(pr_results)

    send_slack(message_body)
