# Legal and Release Readiness Checklist

Reviewed: 28 September 2026

This is a practical release checklist, not legal advice. It records what the
launcher already does, what has been implemented in 0.9.9, and the few facts
that still need confirmation before a stable public release.

## Completed in the launcher

- [x] Microsoft desktop device-code sign-in uses the approved public App ID.
- [x] Microsoft sign-in checks Minecraft: Java Edition entitlement before an
  account is saved.
- [x] Offline profiles are named accurately and require a previously verified
  Microsoft entitlement on the same installation.
- [x] The launcher package does not contain Minecraft game files. It downloads
  requested files from Mojang and other providers.
- [x] The Mojang/Microsoft non-affiliation disclaimer is visible in the first-run
  notice, About page, readmes, terms, and privacy notice.
- [x] The About page links to the Minecraft EULA, Minecraft Usage Guidelines,
  Microsoft Privacy Statement, launcher terms, privacy notice, third-party
  notices, and BreakBlocks contact route.
- [x] The privacy notice documents local tokens, profiles, instances, playtime,
  logs, downloads, update checks, embedded web-chat site data, and every
  category of external service contacted by the current code.
- [x] There is no analytics, advertising SDK, automatic crash upload, or hidden
  BreakBlocks telemetry in the current source.
- [x] Local configuration is written atomically and is restricted to the current
  user on systems that support POSIX permissions.
- [x] Update packages must be attached to the selected GitHub Release, use
  HTTPS, match the declared size, and pass SHA-256 verification.
- [x] The publishing workflow refuses an unsigned public Windows release and
  verifies the resulting Authenticode signature.
- [x] Bundled Python dependency licences are retained, and public packages gain
  a human-readable third-party notice index.
- [x] The launcher's original source code is licensed under the GNU General
  Public License version 3 only, with the complete licence included in source
  and binary packages.
- [x] Built-in block-style icons are generated project artwork rather than
  copied Minecraft textures.
- [x] Chat is fixed to `https://irc.breakblocks.com/#/connect` and displayed in
  an isolated embedded browser profile. BreakBlocks.com controls sign-in,
  channels, moderation, and session expiry; the launcher stores no chat
  password or token of its own.

## Sheepy confirmations needed

- [ ] **Legal operator/data controller:** confirm the real person, company, or
  other legal entity operating BreakBlocks.com and the launcher, plus its
  country. A brand or domain alone may not identify the controller clearly.
- [ ] **Contact method:** provide a monitored launcher/legal/privacy email
  address. Mojang's Usage Guidelines require a contact method and explicitly
  say chat and forum links are not enough. The current website contact page also
  redirects signed-out visitors to login.
- [ ] **Governing law:** confirm the operator's jurisdiction for the final Terms.
- [ ] **Web-chat service policy:** confirm the minimum age, moderation rules,
  server-side logging, cookie/session retention, and who operates the service
  before a stable public release.
- [ ] **Code-signing identity:** confirm the publisher name that will appear on
  the trusted Windows signing certificate and in release metadata.
- [ ] **Website policy update:** approve the launcher additions in
  `WEBSITE-LEGAL-CHANGES.md` and publish them on BreakBlocks.com.
- [ ] **UK data-protection administration:** use the ICO fee self-assessment for
  the actual operator and processing activities, and document the result.

## Before publishing a stable build

- [ ] Replace the provisional contact/operator wording in `PRIVACY.md` and
  `TERMS.md` with the confirmed details.
- [ ] Put the full non-affiliation disclaimer on the official download page and
  GitHub release description, with the publisher and email contact.
- [ ] Publish matching launcher Terms and Privacy links before distributing the
  binary.
- [ ] Verify that Microsoft Entra/App registration publisher information,
  redirect/device-code settings, and privacy/terms URLs match the public
  operator.
- [ ] Build only from a protected release tag and inspect the source archive.
- [ ] Confirm the Windows signature, timestamp, SHA-256 checksums, update
  manifest, archive contents, and dependency licence bundle.
- [ ] Test removal of a Microsoft profile, deletion of local data, updater
  consent, Offline ownership enforcement, web-chat sign-in persistence, and
  website logout/session removal.
- [ ] Have a qualified lawyer review the final public Terms, privacy notice,
  ownership design, branding, and consumer-law wording for the operator's
  jurisdiction.

## Official reference points

- [Minecraft Usage Guidelines](https://www.minecraft.net/usage-guidelines)
- [Minecraft EULA](https://www.minecraft.net/eula)
- [Microsoft Privacy Statement](https://www.microsoft.com/privacy/privacystatement)
- [BreakBlocks.com Terms](https://www.breakblocks.com/terms)
- [BreakBlocks.com Privacy Policy](https://www.breakblocks.com/privacy-policy)
- [ICO UK GDPR guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/)
