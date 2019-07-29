# Basic Configuration
token = "insert-token-here"
description  = "Lightning+, the successor to Lightning(.js)"

# List Cogs that should be loaded on start
cogs = ['cogs.comics', 'cogs.owner', 'cogs.moderation', 'cogs.logger', 
'cogs.extras', 'cogs.mod_userlog', 'cogs.setup',
'cogs.weeb', 'cogs.info', 'cogs.mod_note', 'cogs.fun', 'cogs.toggle_roles', 
'cogs.lockdown', 'cogs.memes', 'cogs.common', 'cogs.misc',
'cogs.lightning-hub', 'cogs.timers', 'cogs.powerscrona', 'cogs.emoji']

# Bot Errors/Logs Channel. 
error_channel = 567109464184979502
powerscron_errors = 575708612454907924
# Channel that sends the powerscron db file every 6 hrs
powerscron_backups = 603389648211017738

#Sends errors to Webhook
webhookurl = "INSERT_LINK_HERE"

# Bot Owner ID
owner_id = "INSERT_ID_HERE"

# If you forked the repo and want to use the github commands
github_username = "" # Github Username
github_repo = "" # Repository Name
github_key = "" # Personal Access Token (OAUTH Token)
gh_whitelisted_guilds = [527887739178188830,
                         540978015811928075] # Guilds that can use Github Commands

# TheCatAPI Key (You can get one at thecatapi.com)
catapi_token = ""