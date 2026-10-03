# BreakBlocks Launcher Privacy Notice

Last updated: 3 October 2026

This notice applies to the BreakBlocks Launcher desktop application. The
[BreakBlocks.com Privacy Policy](https://www.breakblocks.com/privacy-policy)
applies separately when you use the BreakBlocks website, forums, API, or other
online services.

## Who to contact

The launcher is maintained for the BreakBlocks community. For privacy questions
or requests, use the [BreakBlocks contact form](https://www.breakblocks.com/contact).
Before a stable public release, the maintainers will add the confirmed legal
operator name and a monitored privacy email address here.

## Information stored on your device

The launcher stores the following information locally so that it can provide the
features you choose to use:

- Microsoft profile name, Minecraft profile ID, skin image, access tokens,
  refresh token, Minecraft access token, token expiry, and the time ownership
  was verified;
- Offline profile name and locally generated UUID;
- instance names, game versions, loaders, memory settings, icons, installed
  mods, launch history, and playtime;
- launcher preferences, update settings, and web-chat cookies, cache, and site
  storage kept in the launcher's dedicated browser profile;
- downloaded Minecraft, Java, loader, mod, and launcher-update files; and
- launcher and Minecraft log files; and
- local recovery snapshots and instance exports, including mod configuration
  files and optional exported worlds and screenshots.

Microsoft tokens and authenticated web-chat cookies are credentials. Do not
share `launcher.json`, the `web-chat-profile` directory, diagnostic archives,
screenshots containing sign-in codes, or your launcher data folder.
Removing a profile from the launcher removes its stored tokens from the launcher
configuration. You can view the active folder with **Settings → Open data
folder**.

Recovery snapshots stay on your device and are not uploaded automatically.
Exports omit launcher accounts, tokens, chat sessions and known mod account
stores. Other mod configs can still contain personal settings. Share exported
setups only after reviewing their contents; do not share private recovery
snapshots as support logs.

## Information sent over the internet

The launcher has no advertising, analytics, tracking SDK, or automatic crash
reporting. It does not upload your launcher logs, instance list, playtime, or
Microsoft tokens to BreakBlocks.

The launcher connects directly to other services when needed:

| Service | Purpose | Information normally sent |
| --- | --- | --- |
| Microsoft identity, Xbox Live, and Minecraft Services | Device-code sign-in, token refresh, ownership check, profile, and skin | Network address, app identifier, OAuth tokens, Xbox/Minecraft account data, and request metadata |
| Mojang/Minecraft download services | Version catalogues, game libraries, assets, and client downloads | Network address, user agent, and requested files |
| Adoptium, Fabric, Quilt, Forge, and NeoForge | Java runtimes, loader metadata, and loader files | Network address, user agent, Minecraft version, and requested files |
| Modrinth, GitHub, Meteor, and configured mod sources | Mod search, metadata, downloads, and update checks | Network address, user agent, search terms, project/version identifiers, and requested files |
| GitHub Releases | Launcher update checks and downloads | Network address, user agent, update channel, and requested release files |
| BreakBlocks web chat | Authenticated community chat | Network address, BreakBlocks login/session information, cookies, channels, messages, and website request metadata |

Those services process information under their own terms and privacy notices.
The launcher opens Patreon, YouTube, GitHub, Discord, BreakBlocks, and other
external links in your normal browser; the destination website then controls
its own data collection.

## BreakBlocks web chat

Opening the Chat page loads `https://irc.breakblocks.com/#/connect` inside an
embedded browser. BreakBlocks.com handles the login form, account checks, IRC
connection, channels, messages, moderation, and server-side retention. The
launcher does not receive or log the password entered into that website.

The embedded browser uses a dedicated persistent profile in
`web-chat-profile`. Cookies and other site data remain there so the website can
keep you signed in across launcher restarts. The website may still expire or
revoke a session. Use the website's own **Log out** control to end the session,
or delete the profile directory after closing the launcher to remove all local
web-chat site data.

## Retention and deletion

Local information remains on your device until you remove the relevant profile
or instance, clear the files, or uninstall the launcher and delete its data
folder. Each instance retains its three newest launch logs; older launch logs are
replaced automatically. `launcher.log` remains until you delete it. Downloaded
game and mod files remain until the related instance or shared data is removed.
The five newest recovery snapshots are kept for each instance; older snapshots
are replaced after a successful new backup. Removing an instance also removes
its local recovery snapshots. Exported ZIPs remain wherever you saved them
until you delete them.

Third-party services set their own retention periods. If you send logs or other
information to BreakBlocks for support, the website privacy policy and the
support process apply to that copy.

## Security

Sign-in uses Microsoft's device-code flow, so the launcher does not ask for or
receive your Microsoft password. Network requests use HTTPS or TLS where the
service supports it. On Linux, the launcher restricts its configuration file
and data directory to the current operating-system user. Anyone who can access
your operating-system account may still be able to access locally stored
launcher information, so use a protected user account and disk encryption.

Launcher updates must come from the configured GitHub Release, use HTTPS, match
the declared file size, and pass a SHA-256 check before installation. Windows
builds are unsigned, so the Windows publisher is not verified by a certificate.

## Children

BreakBlocks online services are intended for people aged 13 or older, or the
higher minimum age required where they live. A parent or guardian should manage
Microsoft family settings and supervise use where required. Do not use web chat
if you are below the age allowed by the service.

## Your choices and rights

You can remove launcher profiles and instances through the interface, disable
automatic update checks, choose not to open web chat, sign out through the
website, and delete remaining local files from the data folder. For information
held by Microsoft, GitHub, Modrinth, or another third party, contact that
service directly.

Where data protection law applies to information received by BreakBlocks, you
may have rights to access, correct, erase, restrict, port, or object to its use,
and to complain to your local data-protection authority. Use the contact link
above to make a request.

## Changes

This notice will be updated when the launcher's data practices change. The date
at the top shows the latest revision.
