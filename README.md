# Lightning.py
[![Discord](https://img.shields.io/discord/527887739178188830.svg)](https://discord.gg/cDPGuYd)
[![Pipeline Status](https://img.shields.io/gitlab/pipeline/lightning-bot/Lightning?label=Pipeline&logo=GitLab)](https://gitlab.com/lightning-bot/Lightning/pipelines/latest)

Lightning is a multi-purpose bot.

To find Lightning's commands, run the help command.

---

## Features & Changelogs

A list of features can be found below or at https://lightning-bot.gitlab.io. Changelogs can be found at the support server (https://discord.gg/cDPGuYd) in the changelogs channel.

---
**Moderation Tools**

- Warnings
  - With optional punishments, such as kicking the user once the user has reached a certain amount of warns.
  - The ability to remove warns from users.
  - As a note, warnings are guild specific.
- Ban
  - You can also temporarily ban members for a specified time, just use the timeban command!
- Mute
  - You can also temporarily mute members too with the timemute command!
  - The mute and tempmute commands only assign a role and make it sticky, it's not a channel permission modifier. You'll need to setup those perms yourself.
- Kick
- Purge messages from a channel.
  - If you want to cleanup responses from Lightning, use the clean command.
- Channel Lockdown
  - This sets the channel permissions as `@everyone` can't send messages. To undo the lock command, use the unlock command to allow `@everyone` to send messages in the channel.
  - The hlock command does what the regular lock command does, but it also removes read message permission for `@everyone`. To undo a hard lockdown, use the hunlock command.
- Mod Logging

**Configuration**

- Custom Prefixes
    - Custom prefixes are guild specific and are limited to 5 different custom prefixes.
- Mod Roles
    - If you don't trust your moderators with certain permissions, this is for you!
  - Mod roles allow members with a configured role to have permissions in the bot without needing the actual role permission itself! For more information on mod roles, go to [https://lightning-bot.gitlab.io/config/settings/#moderation-roles](https://lightning-bot.gitlab.io/config/settings/#moderation-roles).
- Logging
  - You can specify what your guild wants to log in a channel.
    - __Supported Logging__:
      - Moderation logs
      - Role change logs
      - Member join and leave logs
        - Bot Additions
  - To disable logging, just run the setup command!
- Auto Roles
  - Have you wanted to have members get a certain role on joining your server? Well, now you can with auto roles! To add an automatic role, use the `config autorole set` command. For more information, use the `help config autorole` command.

**Other Features Include**:

- Emoji Management
- Memes
- Reminders
- Image Manipulation
- Message Snipes
- Nintendo Console Update Alerts

and more!

---
[![DBL (top.gg)](https://top.gg/api/widget/status/532220480577470464.svg)](https://top.gg/bot/532220480577470464)
[![DBL (top.gg)](https://top.gg/api/widget/owner/532220480577470464.svg)](https://top.gg/bot/532220480577470464)
## Invite

If you want to invite Lightning to your guild, use this link https://discordapp.com/oauth2/authorize?client_id=532220480577470464&scope=bot&permissions=2013637846. (Select permissions as needed.)

---
## License
AGPL v3 with additional terms 7b and 7c in effect.
```
# Lightning.py - The Successor to Lightning.js
# Copyright (C) 2019 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version
```
## Credits 

This bot uses parts and ideas from other Discord Bots:

- [Kirigiri](https://git.catgirlsin.space/noirscape/kirigiri) by Noirscape. (For staff role database layout)
- [Robocop-NG](https://github.com/reswitched/robocop-ng) by Ave and TomGER. (Some of the moderation Commands)
- [Kurisu](https://github.com/nh-server/Kurisu) by ihaveahax/ihaveamac and 916253. (For the compact logging format)
- [RoboDanny](https://github.com/Rapptz/RoboDanny) by Rapptz/Danny. (For Ideas, Unban Handler, Paginators, and other things)


Extended special thanks to:

- aspargas2
- OthersCallMeGhost