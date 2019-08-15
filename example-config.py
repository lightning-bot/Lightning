# Basic Configuration
token = "insert-token-here"
description  = "Lightning+, the successor to Lightning(.js)"
default_prefix = ['.']

# List Cogs that should be loaded on start
cogs = ['cogs.comics', 'cogs.common', 'cogs.emoji', 'cogs.fun', 
'cogs.git', 'cogs.lightning-hub', 'cogs.lockdown',
'cogs.logger', 'cogs.memes', 'cogs.meta', 'cogs.mod_note', 'cogs.mod_userlog', 
'cogs.moderation', 'cogs.owner', 'cogs.powerscrona', 'cogs.setup',
'cogs.timers', 'cogs.toggle_roles', 'cogs.utility', 'cogs.weeb'] #, 'cogs.tags'

# Bot Errors/Logs Channel. 
error_channel = 567109464184979502
powerscron_errors = "INSERT_WEBHOOK_URL"
# Channel that sends the powerscron db file every 6 hrs
powerscron_backups = 603389648211017738

#Sends errors to Webhook
webhookurl = "INSERT_LINK_HERE"
# Send Guild Joins and Leaves to a channel
webhook_glog = "INSERT_WEBHOOK_URL"

# Bot Owner ID
owner_id = "INSERT_ID_HERE"

# If you forked the repo and want to use the github commands
github_username = "" # Github Username
github_repo = "" # Repository Name
github_key = "" # Personal Access Token (OAUTH Token)
gh_whitelisted_guilds = [527887739178188830,
                         540978015811928075] # Guilds that can use Github/GitLab Commands

# IP Address or URL of GitLab Instance
gitlab_instance = ""
gitlab_token = "" # Personal Access Token 
                  # https://docs.gitlab.com/ce/user/profile/personal_access_tokens.html
gitlab_project_id = ""

# TheCatAPI Key (You can get one at thecatapi.com)
catapi_token = ""

# DiscordBotsList Token (DBL)
dbl_token = ""