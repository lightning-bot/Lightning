# Basic Configuration
token = "insert-token-here"
description = "Lightning+, the successor to Lightning(.js)"
default_prefix = ['.']
database_connection = "postgresql://user:password@host/lightning"
# How many times can commands be spammed before the bot auto-blacklists
spam_count = 5
bot_version = "v2.0B"

# Bot Errors/Logs Channel.
error_channel = 567109464184979502
powerscron_errors = "INSERT_WEBHOOK_URL"
# Channel that sends the powerscron db file every 6 hrs
powerscron_backups = 603389648211017738
# Bug Reports Log Channel
bug_reports_channel = 603389648211017738

# Sends errors to Webhook
webhookurl = "INSERT_LINK_HERE"
# Send Guild Joins and Leaves to a channel
webhook_glog = "INSERT_WEBHOOK_URL"
# Send info on an auto user blacklist
webhook_blacklist_alert = "WEBHOOK_URL"

# List of bot_managers. Store them by ID
bot_managers = [532220480577470464]

# If you forked the repo and want to use the github commands
github_username = ""  # Github Username
github_repo = ""  # Repository Name
github_key = ""  # Personal Access Token (OAUTH Token)
# Guilds that can use Github/GitLab Commands
gh_whitelisted_guilds = [527887739178188830,
                         540978015811928075]

# IP Address or URL of GitLab Instance
gitlab_instance = ""
# Personal Access Token
# https://docs.gitlab.com/ce/user/profile/personal_access_tokens.html
gitlab_token = ""
gitlab_project_id = ""

# TheCatAPI Key (You can get one at thecatapi.com)
catapi_token = ""

# DiscordBotsList Token (DBL)
dbl_token = ""
